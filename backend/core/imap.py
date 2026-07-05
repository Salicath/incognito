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


@dataclass(frozen=True)
class MatchResult:
    request_id: str
    tier: MatchTier


def _extract_domain(email_address: str) -> str:
    """Extract domain from an email address."""
    return email_address.rsplit("@", 1)[-1].lower()


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
    ):
        self._config = imap_config
        self._db_factory = db_session_factory
        self._broker_domains = broker_domains
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

    def _build_lookup_maps(self, db: Session):
        active_statuses = {RequestStatus.SENT, RequestStatus.OVERDUE, RequestStatus.ESCALATED}
        requests = db.query(Request).filter(Request.status.in_(active_statuses)).all()

        outbound_ids: dict[str, str] = {}
        ref_code_map: dict[str, str] = {}
        domain_request_map: dict[str, str] = {}
        delisting_open: list[dict] = []

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

        return outbound_ids, ref_code_map, domain_request_map, delisting_open

    @staticmethod
    def _match_delisting_decision(
        from_address: str, body: str, delisting_open: list[dict],
    ) -> MatchResult | None:
        """Match a form-triggered RTBF decision email to a tracked request.

        Strong (auto-acknowledge): sender is the engine's decision domain and
        the tracked URL appears in the body — Google enumerates requested URLs
        in its decision mail. Weak (attach-only, Bing): Bing replies carry no
        case number and no URLs, so a microsoft.com mail attaches to the single
        open Bing request without transitioning; the user confirms.
        """
        from backend.core.delisting import DECISION_SENDER_DOMAINS

        sender_domain = _extract_domain(from_address)
        candidates = [
            r for r in delisting_open
            if any(
                sender_domain == d or sender_domain.endswith("." + d)
                for d in DECISION_SENDER_DOMAINS.get(r["broker_id"], set())
            )
        ]
        if not candidates:
            return None

        for r in candidates:
            url = r["target_url"].rstrip("/")
            if url and url in body:
                return MatchResult(
                    request_id=r["request_id"], tier=MatchTier.DELISTING_DECISION,
                )

        bing = [r for r in candidates if r["broker_id"] == "delisting-bing"]
        if len(bing) == 1:
            return MatchResult(
                request_id=bing[0]["request_id"], tier=MatchTier.DOMAIN_ONLY,
            )
        return None

    def process_message(self, msg, *, _lookup_maps=None) -> MatchResult | None:
        db = self._db_factory()
        try:
            if _lookup_maps is not None:
                outbound_ids, ref_code_map, domain_request_map, delisting_open = _lookup_maps
            else:
                (
                    outbound_ids, ref_code_map, domain_request_map, delisting_open,
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

            result = match_reply(
                in_reply_to=in_reply_to,
                references=references,
                subject=msg.subject or "",
                from_address=from_addr,
                outbound_message_ids=outbound_ids,
                broker_domains=self._broker_domains,
                ref_code_map=ref_code_map,
                domain_request_map=domain_request_map,
            )

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
