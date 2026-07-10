from __future__ import annotations

import asyncio
import enum
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from backend.core.profile import ImapConfig
from backend.db.models import (
    EmailDirection,
    EmailMessage,
    Request,
    RequestEvent,
    RequestStatus,
)

log = logging.getLogger("incognito.imap")

_REF_PATTERN = re.compile(r"\[REF-([A-Z0-9]{8})\]")


class MatchTier(enum.StrEnum):
    MESSAGE_ID = "message_id"
    REFERENCE_CODE = "reference_code"
    DOMAIN_ONLY = "domain_only"
    # RTBF decisions are form-triggered mail (no threading, no REF echo):
    # matched by decision-sender domain + the tracked URL appearing in the body
    DELISTING_DECISION = "delisting_decision"
    # Reply forwarded by SimpleLogin: the alias it was delivered to identifies
    # the broker. High confidence — we minted the alias for exactly one broker.
    ALIAS = "alias"


@dataclass(frozen=True)
class MatchResult:
    request_id: str
    tier: MatchTier


def _extract_domain(email_address: str) -> str:
    """Extract domain from an email address."""
    addr = email_address.strip()
    if "<" in addr and addr.endswith(">"):
        addr = addr[addr.rfind("<") + 1:-1]
    return addr.rsplit("@", 1)[-1].strip().lower()


# A poller can run for weeks; leak signals are drained by the API, not unbounded.
_MAX_LEAK_SIGNALS = 500


def _domain_matches_broker(sender_domain: str, owner_domain: str) -> bool:
    """Is `sender_domain` plausibly the broker itself?

    Accept the domain and any subdomain of it, so mail.spokeo.com is not a
    leak. `owner_domain` must be the broker's REAL domain — reconstructing it
    from the slug id is wrong for hyphenated domains (data-axle.com slugifies
    to "data-axle-com", which would reverse to "data.axle.com").
    """
    return sender_domain == owner_domain or sender_domain.endswith("." + owner_domain)


def match_reply(
    in_reply_to: str,
    references: str,
    subject: str,
    from_address: str,
    outbound_message_ids: dict[str, str],
    broker_domains: set[str],
    ref_code_map: dict[str, str] | None = None,
    domain_request_map: dict[str, str] | None = None,
) -> MatchResult | None:
    # Tier 1: Message-ID threading
    if in_reply_to and in_reply_to.strip() in outbound_message_ids:
        return MatchResult(
            request_id=outbound_message_ids[in_reply_to.strip()],
            tier=MatchTier.MESSAGE_ID,
        )

    if references:
        for ref_id in references.split():
            ref_id = ref_id.strip()
            if ref_id in outbound_message_ids:
                return MatchResult(
                    request_id=outbound_message_ids[ref_id],
                    tier=MatchTier.MESSAGE_ID,
                )

    # Tier 2: Subject reference code + domain validation
    if ref_code_map:
        match = _REF_PATTERN.search(subject)
        if match:
            code = match.group(1)
            if code in ref_code_map:
                sender_domain = _extract_domain(from_address)
                if sender_domain in broker_domains:
                    return MatchResult(
                        request_id=ref_code_map[code],
                        tier=MatchTier.REFERENCE_CODE,
                    )

    # Tier 3: Sender domain match (low confidence)
    if domain_request_map:
        sender_domain = _extract_domain(from_address)
        if sender_domain in domain_request_map:
            return MatchResult(
                request_id=domain_request_map[sender_domain],
                tier=MatchTier.DOMAIN_ONLY,
            )

    return None


class ImapPoller:
    def __init__(
        self,
        imap_config: ImapConfig,
        db_session_factory: sessionmaker,
        broker_domains: set[str],
        tier3_exclude: set[str] | None = None,
        broker_id_domains: dict[str, str] | None = None,
    ):
        self._config = imap_config
        self._db_factory = db_session_factory
        self._broker_domains = broker_domains
        # id -> real domain, for the leak check. Falls back to slug reversal
        # when absent, which is only correct for hyphen-free domains.
        self._broker_id_domains = broker_id_domains or {}
        # Request targets whose domains also send routine mail (controllers:
        # Netflix receipts, Amazon orders, ...) — domain-only matching would
        # file that noise onto the legal thread, so they get tiers 1-2 only.
        self._tier3_exclude = tier3_exclude or set()
        self._running = False
        self._task: asyncio.Task | None = None
        self.last_check: datetime | None = None
        self.last_error: str | None = None
        self.matched_count = 0
        self.unmatched_count = 0
        # aliases that received mail from someone other than their broker
        self.leak_signals: list[dict] = []

    def _build_lookup_maps(self, db: Session):
        active_statuses = {RequestStatus.SENT, RequestStatus.OVERDUE, RequestStatus.ESCALATED}
        requests = db.query(Request).filter(Request.status.in_(active_statuses)).all()

        outbound_ids: dict[str, str] = {}
        ref_code_map: dict[str, str] = {}
        domain_request_map: dict[str, str] = {}
        delisting_open: list[dict] = []

        # alias -> (broker_id, request_id). A SimpleLogin forward carries the
        # broker's real address only when the user opted into the envelope
        # headers, so the alias is the reliable hook.
        from backend.db.models import BrokerAlias

        alias_broker: dict[str, str] = {
            a.alias_email.lower(): a.broker_id
            for a in db.query(BrokerAlias).all()
        }
        alias_request_map: dict[str, str] = {}

        # Every outbound Message-ID we have EVER stamped, status-independent.
        # The leak check consults this, not `outbound_ids`: after the first
        # reply auto-ACKs, the request leaves the active-status maps, and a
        # second ticketing reply on the same thread must not be leak-branded.
        all_outbound_ids: set[str] = {
            mid for (mid,) in db.query(Request.message_id)
            .filter(Request.message_id.isnot(None))
        }
        all_outbound_ids.update(
            mid for (mid,) in db.query(EmailMessage.message_id)
            .filter(
                EmailMessage.direction == EmailDirection.OUTBOUND,
                EmailMessage.message_id.isnot(None),
            )
        )

        for req in requests:
            if req.message_id:
                outbound_ids[req.message_id] = req.id
            ref_code = req.id.split("-")[0].upper()[:8]
            ref_code_map[ref_code] = req.id
            if req.broker_id not in self._tier3_exclude:
                domain_request_map[req.broker_id.replace("-", ".")] = req.id
            if req.broker_id.startswith("delisting-"):
                delisting_open.append({
                    "request_id": req.id,
                    "broker_id": req.broker_id,
                    "target_url": req.target_url or "",
                })

        # The alias identifies the broker, not the thread — when a broker has
        # several active requests (erasure + access), file onto the newest.
        by_recency = sorted(
            requests, key=lambda r: r.sent_at or r.created_at, reverse=True,
        )
        for alias, broker_id in alias_broker.items():
            for req in by_recency:
                if req.broker_id == broker_id:
                    alias_request_map[alias] = req.id
                    break

        return (
            outbound_ids, ref_code_map, domain_request_map, delisting_open,
            alias_request_map, alias_broker, all_outbound_ids,
        )

    @staticmethod
    def _match_delisting_decision(
        from_address: str, body: str, delisting_open: list[dict],
    ) -> MatchResult | None:
        """Match a form-triggered RTBF decision email to a tracked request.

        Auto-acknowledge requires BOTH an exact known decision-sender address
        and the tracked URL in the body. Domain-wide matching is forbidden
        here: Google Alerts / "Results about you" notifications quote the
        same URL from @google.com senders and must never stop the Art. 12(3)
        clock. Bing sends nothing machine-recognizable — always user-confirmed.
        """
        from backend.core.delisting import DECISION_SENDER_ADDRESSES

        addr = from_address.strip().lower()
        if "<" in addr and addr.endswith(">"):
            addr = addr[addr.rfind("<") + 1:-1]

        for r in delisting_open:
            if addr not in DECISION_SENDER_ADDRESSES.get(r["broker_id"], set()):
                continue
            url = r["target_url"].rstrip("/")
            if url and url in body:
                return MatchResult(
                    request_id=r["request_id"], tier=MatchTier.DELISTING_DECISION,
                )
        return None

    @staticmethod
    def _record_leak(db, alias: str, broker_id: str, sender: str, msg) -> None:
        """File a leak as an exposure so it lands in the triage inbox.

        Keyed (source, broker_id, url=mailto:sender) so repeat spam from the
        same sender refreshes one row rather than resurrecting a dismissal.
        Never let a bookkeeping failure lose the reply we are mid-way through
        processing.
        """
        from backend.core.rescan import save_scan_results

        try:
            # Keyed (source, broker_id, mailto:<sender DOMAIN>): VERP campaigns
            # vary the local part per message, and a full-address key would
            # mint one exposure per spam mail and resurrect dismissals. The
            # full sender is kept as evidence in the data.
            sender_domain = _extract_domain(sender)
            new = save_scan_results(
                db,
                [{
                    "broker_domain": broker_id,
                    "url": f"mailto:{sender_domain}",
                    "sender": sender,
                    # Triage language, not an accusation: the signal proves an
                    # unexpected sender, not who is culpable. The user's own
                    # confirmation — ideally after the Art. 15(1)(c) answer —
                    # produces the complaint-grade wording.
                    "title": f"Unexpected sender on the alias for {broker_id}",
                    "snippet": (
                        f"Alias {alias} was disclosed only to {broker_id}, but "
                        f"received mail from {sender} "
                        f"(subject: {(msg.subject or '')[:120]!r})."
                    ),
                }],
                source="alias_leak",
            )
            if new:
                from backend.core.notifier import EventType, notify

                notify(
                    EventType.NEW_EXPOSURE,
                    f"Unexpected sender on {broker_id}'s alias",
                    f"Alias {alias} received mail from {sender} — only "
                    f"{broker_id} was told this address.",
                )
        except Exception as exc:  # noqa: BLE001 - never drop the reply over this
            # The caller keeps using this session — leave it clean.
            db.rollback()
            log.error("Failed to record alias leak for %s: %s", broker_id, exc)

    def process_message(self, msg, *, _lookup_maps=None) -> MatchResult | None:
        db = self._db_factory()
        try:
            if _lookup_maps is not None:
                (
                    outbound_ids, ref_code_map, domain_request_map, delisting_open,
                    alias_request_map, alias_broker, all_outbound_ids,
                ) = _lookup_maps
            else:
                (
                    outbound_ids, ref_code_map, domain_request_map, delisting_open,
                    alias_request_map, alias_broker, all_outbound_ids,
                ) = self._build_lookup_maps(db)

            in_reply_to = ""
            references = ""
            if hasattr(msg, "headers") and msg.headers:
                in_reply_to_vals = msg.headers.get("in-reply-to", ("",))
                in_reply_to = in_reply_to_vals[0] if in_reply_to_vals else ""
                ref_vals = msg.headers.get("references", ("",))
                references = ref_vals[0] if ref_vals else ""

            if isinstance(msg.from_, str):
                from_addr = msg.from_
            else:
                from_addr = str(msg.from_) if msg.from_ else ""
            if isinstance(msg.to, (list, tuple)) and msg.to:
                to_addr = msg.to[0]
            else:
                to_addr = str(msg.to) if msg.to else ""

            body_text = msg.text or ""

            # SimpleLogin forwards rewrite From: to an sl.co reverse-alias, which
            # would defeat the domain-based tiers. Recover the real sender when
            # the user enabled the envelope headers; always recover the alias.
            from backend.core.alias import (
                alias_from_headers,
                original_author_from_headers,
                original_sender_from_headers,
            )

            raw_headers = getattr(msg, "headers", None) or {}
            delivered_alias = alias_from_headers(raw_headers)
            envelope_sender = original_sender_from_headers(raw_headers)
            author = original_author_from_headers(raw_headers)
            # For matching, the author is what tier-2 wants: an ESP-sent
            # broker reply has MAIL FROM at the ESP but the broker as author.
            effective_from = author or envelope_sender or from_addr

            result = match_reply(
                in_reply_to=in_reply_to,
                references=references,
                subject=msg.subject or "",
                from_address=effective_from,
                outbound_message_ids=outbound_ids,
                broker_domains=self._broker_domains,
                ref_code_map=ref_code_map,
                domain_request_map=domain_request_map,
            )

            # Leak signal: mail reached an alias we minted for broker X, but the
            # sender is demonstrably not X. Only broker X was ever told this
            # address, so the alias itself is the evidence of a leak or resale.
            #
            # Requires `real_sender`. On a SimpleLogin forward the From: is
            # rewritten to a reverse-alias at SimpleLogin's own domain, and the
            # envelope-from header that recovers the true sender is opt-in
            # upstream. Judging leakage off the rewritten From: would brand every
            # ordinary broker reply as a resale. No real sender, no verdict.
            # Suppression: a message that threads to one of our own outbound
            # Message-IDs is the broker speaking through whatever pipeline it
            # uses (OneTrust, Zendesk, an ESP) — only the broker's mail system
            # ever holds the full Message-ID UUID (the subject REF code
            # exposes 8 of its 32 hex chars). Brand no leak on our own thread.
            threads_to_us = bool(
                (in_reply_to and in_reply_to.strip() in all_outbound_ids)
                or any(r in all_outbound_ids for r in (references or "").split())
            )

            # A verdict needs at least one recovered sender, and EVERY
            # recovered sender must mismatch the broker: Envelope-From alone
            # is an ESP bounce domain for ESP-sent mail, so a genuine broker
            # reply would otherwise be branded.
            sender_candidates = [s for s in (author, envelope_sender) if s]
            is_leak = False
            if (
                sender_candidates and delivered_alias
                and delivered_alias in alias_broker and not threads_to_us
            ):
                owner = alias_broker[delivered_alias]
                owner_domain = self._broker_id_domains.get(
                    owner, owner.replace("-", ".")
                )
                candidate_domains = [
                    d for d in (_extract_domain(s) for s in sender_candidates) if d
                ]
                if candidate_domains and not any(
                    _domain_matches_broker(d, owner_domain)
                    for d in candidate_domains
                ):
                    is_leak = True
                    shown_sender = author or envelope_sender or ""
                    log.warning(
                        "Alias %s (minted for %s) received mail from %s — "
                        "unexpected sender",
                        delivered_alias, owner, shown_sender,
                    )
                    signal = {"alias": delivered_alias, "broker_id": owner,
                              "sender": shown_sender}
                    # Leak mail stays unread, so every poll re-processes it —
                    # don't grow a duplicate signal per cycle.
                    if (
                        signal not in self.leak_signals
                        and len(self.leak_signals) < _MAX_LEAK_SIGNALS
                    ):
                        self.leak_signals.append(signal)
                    self._record_leak(db, delivered_alias, owner, shown_sender, msg)

            # Alias tier: the alias was minted for exactly one broker, so it
            # identifies the request even when the sender is unrecognisable.
            # It does NOT prove the broker replied — a known-unrelated sender is
            # a leak, not a reply, and must not be filed against the thread.
            # Deliberately not an auto-ACK tier (see the ACK guard below): with
            # the envelope headers off, spam to the alias is indistinguishable
            # from a reply, and an auto-ACK would stop the Art. 12(3) clock.
            if result is None and delivered_alias and not is_leak:
                req_id = alias_request_map.get(delivered_alias)
                if req_id:
                    result = MatchResult(request_id=req_id, tier=MatchTier.ALIAS)

            if result is None and delisting_open:
                result = self._match_delisting_decision(
                    from_addr, body_text, delisting_open,
                )

            if result is None:
                self.unmatched_count += 1
                return None
            email_record = EmailMessage(
                request_id=result.request_id,
                message_id=in_reply_to or f"<unknown-{msg.uid}@imap>",
                in_reply_to=in_reply_to or None,
                direction=EmailDirection.INBOUND,
                from_address=from_addr,
                to_address=to_addr,
                subject=msg.subject or "",
                body_text=body_text,
                received_at=msg.date if msg.date else datetime.now(UTC),
            )
            db.add(email_record)

            if result.tier in (
                MatchTier.MESSAGE_ID, MatchTier.REFERENCE_CODE,
                MatchTier.DELISTING_DECISION,
            ):
                req = db.get(Request, result.request_id)
                valid = (RequestStatus.SENT, RequestStatus.OVERDUE, RequestStatus.ESCALATED)
                if req and req.status in valid:
                    req.status = RequestStatus.ACKNOWLEDGED
                    req.response_at = datetime.now(UTC)
                    if body_text and len(body_text) > 2000:
                        req.response_body = body_text[:2000] + "\n...[truncated]"
                    else:
                        req.response_body = body_text or ""
                    req.updated_at = datetime.now(UTC)

                    event = RequestEvent(
                        request_id=result.request_id,
                        event_type="response_detected",
                        details=f"Reply detected via {result.tier.value} from {from_addr}",
                    )
                    db.add(event)

            self.matched_count += 1
            db.commit()

            if result.tier in (
                MatchTier.MESSAGE_ID, MatchTier.REFERENCE_CODE,
                MatchTier.DELISTING_DECISION,
            ):
                from backend.core.notifier import EventType, notify
                notify(
                    EventType.REPLY_RECEIVED,
                    f"Reply from {from_addr}",
                    f"Broker replied to request {result.request_id[:8].upper()} "
                    f"(matched via {result.tier.value}).",
                )

            return result
        finally:
            db.close()

    async def poll_once(self) -> int:
        import ssl as ssl_mod

        from imap_tools import AND, MailBox, MailBoxStartTls, MailMessageFlags

        processed = 0
        try:
            ssl_ctx = ssl_mod.create_default_context()
            if self._config.host in ("127.0.0.1", "localhost", "::1"):
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl_mod.CERT_NONE

            mb: MailBox | MailBoxStartTls
            if self._config.starttls:
                mb = MailBoxStartTls(
                    host=self._config.host,
                    port=self._config.port,
                    ssl_context=ssl_ctx,
                )
            else:
                mb = MailBox(host=self._config.host, port=self._config.port, ssl_context=ssl_ctx)

            with mb.login(
                self._config.username, self._config.password, self._config.folder,
            ) as mailbox:
                # Build lookup maps once per poll cycle instead of per message
                lookup_db = self._db_factory()
                try:
                    lookup_maps = self._build_lookup_maps(lookup_db)
                finally:
                    lookup_db.close()

                for msg in mailbox.fetch(AND(seen=False), mark_seen=False):
                    result = self.process_message(msg, _lookup_maps=lookup_maps)
                    if result is not None and msg.uid:
                        mailbox.flag(msg.uid, MailMessageFlags.SEEN, True)
                    processed += 1
            self.last_error = None
        except Exception as exc:
            # Sanitize error — IMAP exceptions may include credentials
            err_type = type(exc).__name__
            self.last_error = f"{err_type}: connection or authentication failed"
            log.error("IMAP poll failed: %s", exc)

        self.last_check = datetime.now(UTC)
        return processed

    async def _run_loop(self):
        self._running = True
        log.info(
            "IMAP poller started (interval=%dm, folder=%s)",
            self._config.poll_interval_minutes,
            self._config.folder,
        )
        while self._running:
            await self.poll_once()
            await asyncio.sleep(self._config.poll_interval_minutes * 60)

    def start(self):
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
