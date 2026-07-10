import logging
from datetime import date as _date  # module-level so the 2027 gate is testable

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel

from backend.api.deps import SessionStore
from backend.core.broker import BrokerRegistry, RemovalMethod
from backend.core.config import AppConfig
from backend.core.controller import RegistryUnion
from backend.core.cpr_lever import CprLeverRegistry, covered_broker_ids
from backend.core.profile import ProfileVault
from backend.core.request import RequestManager
from backend.core.template import TemplateRenderer
from backend.db.models import Request, RequestStatus, RequestType

log = logging.getLogger("incognito.blast")


def create_blast_router(
    vault: ProfileVault,
    session_store: SessionStore,
    broker_registry: BrokerRegistry,
    db_session_factory,
    config: AppConfig,
    lever_registry: CprLeverRegistry | None = None,
    controller_registry=None,
    delisting_registry=None,
) -> APIRouter:
    r = APIRouter(prefix="/api/blast", tags=["blast"])

    class BlastRequest(BaseModel):
        request_type: str  # "access" or "erasure"
        dry_run: bool = True

    class BlastResult(BaseModel):
        created: int
        skipped: int  # already has a pending/sent request
        total_brokers: int
        requests: list[dict]

    @r.post("/create")
    def create_blast(
        body: BlastRequest,
        session: str | None = Cookie(default=None),
    ) -> dict:
        """Create requests for all brokers that don't already have an active request."""
        session_store.validate(session)

        request_type = RequestType.ACCESS if body.request_type == "access" else RequestType.ERASURE

        db = db_session_factory()
        try:
            mgr = RequestManager(db, config.gdpr_deadline_days)

            # Find brokers that already have active requests of this type
            existing = db.query(Request).filter(
                Request.request_type == request_type,
                Request.status.in_([
                    RequestStatus.CREATED,
                    RequestStatus.SENT,
                    RequestStatus.ACKNOWLEDGED,
                ]),
            ).all()
            existing_broker_ids = {req.broker_id for req in existing}

            # Brokers already covered by an active CPR lever need no Art. 17 send
            lever_covered: set[str] = set()
            if lever_registry and lever_registry.levers:
                from backend.db.models import CprLeverState
                lever_states = {
                    s.lever_id: (s.status.value, s.expires_at)
                    for s in db.query(CprLeverState).all()
                }
                lever_covered = covered_broker_ids(lever_registry, lever_states)

            created = []
            skipped = []
            covered = []

            for broker in broker_registry.brokers:
                if broker.id in existing_broker_ids:
                    skipped.append(broker.id)
                    continue

                if broker.id in lever_covered:
                    covered.append(broker.id)
                    continue

                if body.dry_run:
                    created.append({
                        "broker_id": broker.id,
                        "broker_name": broker.name,
                        "dpo_email": broker.dpo_email,
                        "request_type": request_type.value,
                        "status": "would_create",
                    })
                else:
                    req = mgr.create(broker.id, request_type)
                    created.append({
                        "broker_id": broker.id,
                        "broker_name": broker.name,
                        "dpo_email": broker.dpo_email,
                        "request_type": request_type.value,
                        "status": "created",
                        "request_id": req.id,
                    })

            log.info(
                "Blast %s: %d created, %d skipped (dry_run=%s)",
                body.request_type, len(created), len(skipped), body.dry_run,
            )
            return {
                "dry_run": body.dry_run,
                "created": len(created),
                "skipped": len(skipped),
                "covered_by_lever": len(covered),
                "total_brokers": len(broker_registry.brokers),
                "requests": created,
            }
        finally:
            db.close()

    @r.post("/send-all")
    async def send_all_pending(session: str | None = Cookie(default=None)) -> dict:
        """Send all pending (created) requests via email."""
        key, salt = session_store.validate(session)
        profile, smtp, _ = vault.load_with_key(key)

        if smtp is None:
            raise HTTPException(
                status_code=400,
                detail="SMTP not configured. Add SMTP settings before sending requests.",
            )

        from pathlib import Path

        from backend.core.alias_resolver import resolve_recipient
        from backend.core.secrets import read_secret
        from backend.db.models import EmailDirection
        from backend.db.models import EmailMessage as EmailMessageModel
        from backend.senders.email import EmailSender

        # Absent a key, resolve_recipient is a no-op and we send as before.
        sl_key = read_secret(vault, config.data_dir, key, salt, "simplelogin")
        repo_templates = Path(__file__).parent.parent.parent / "templates"
        templates_dir = config.data_dir / "templates"
        if not templates_dir.exists():
            templates_dir = repo_templates

        renderer = TemplateRenderer(templates_dir, fallback_dir=repo_templates)
        sender = EmailSender(smtp)

        db = db_session_factory()
        try:
            mgr = RequestManager(db, config.gdpr_deadline_days)

            pending = db.query(Request).filter(
                Request.status == RequestStatus.CREATED,
            ).all()

            sent = 0
            failed = 0
            results = []

            import asyncio

            for req in pending:
                try:
                    broker = broker_registry.get(req.broker_id)
                    if broker is None:
                        results.append({
                            "broker_id": req.broker_id,
                            "status": "skipped",
                            "reason": "broker not found",
                        })
                        continue

                    # Non-email brokers: try web form automation, else manual
                    if broker.removal_method != RemovalMethod.EMAIL:
                        if broker.removal_method == RemovalMethod.WEB_FORM:
                            from pathlib import Path

                            from backend.senders.web import WebFormSender

                            forms_dir = Path(__file__).parent.parent.parent / "brokers" / "forms"
                            web_sender = WebFormSender(profile, forms_dir)
                            web_result = await web_sender.send(
                                broker.domain, broker.removal_url or broker.domain,
                                request_id=req.id,
                            )
                            if web_result.status.value == "success":
                                mgr.mark_sent(req.id)
                                sent += 1
                                results.append({
                                    "broker_id": req.broker_id,
                                    "broker_name": broker.name,
                                    "status": "sent",
                                    "method": "web_form",
                                })
                                delay = 3600 / max(config.rate_limit_per_hour, 1)
                                await asyncio.sleep(delay)
                                continue

                        url = broker.removal_url or broker.domain
                        method = broker.removal_method
                        reason = f"Broker requires {method} — visit {url}"
                        mgr.mark_manual_action_needed(req.id, reason)
                        results.append({
                            "broker_id": req.broker_id,
                            "status": "manual",
                            "reason": f"requires {method}",
                        })
                        continue

                    # Determine template and language
                    if req.request_type == RequestType.ACCESS:
                        template_name = "access_request"
                    else:
                        template_name = "erasure_request"

                    rendered = renderer.render_localized(
                        template_name,
                        broker.language,
                        profile=profile,
                        reference_id=req.id[:8].upper(),
                        broker_name=broker.name,
                    )

                    # With aliasing on, we SMTP to the broker's reverse-alias and
                    # SimpleLogin rewrites the sender, so the broker never learns
                    # the real mailbox. Falls back to dpo_email on any failure.
                    smtp_to, alias_email = await resolve_recipient(
                        db, sl_key, req.broker_id, broker.dpo_email,
                    )

                    result = await sender.send(
                        to_email=smtp_to,
                        rendered_text=rendered,
                        request_id=req.id,
                    )

                    if result.status.value == "success":
                        # Store message_id on request
                        req.message_id = f"<{req.id}@incognito.local>"

                        # Store outbound email record
                        outbound_record = EmailMessageModel(
                            request_id=req.id,
                            message_id=req.message_id,
                            direction=EmailDirection.OUTBOUND,
                            from_address=alias_email or smtp.username,
                            to_address=broker.dpo_email,
                            subject=f"GDPR Request [REF-{req.id[:8].upper()}]",
                            body_text=rendered,
                        )
                        db.add(outbound_record)

                        mgr.mark_sent(req.id)
                        sent += 1
                        results.append({
                            "broker_id": req.broker_id,
                            "broker_name": broker.name,
                            "status": "sent",
                            "email": broker.dpo_email,
                            "sent_as": alias_email,
                        })
                    else:
                        failed += 1
                        results.append({
                            "broker_id": req.broker_id,
                            "broker_name": broker.name,
                            "status": "failed",
                            "reason": result.message,
                        })

                    # Rate limit: space emails according to configured hourly limit
                    delay = 3600 / max(config.rate_limit_per_hour, 1)
                    log.info("Sent to %s, waiting %.0fs (rate: %d/hr)",
                             broker.dpo_email, delay, config.rate_limit_per_hour)
                    await asyncio.sleep(delay)
                except Exception as e:
                    # One session serves the whole blast — roll back or this
                    # broker's dirty state fails every broker after it.
                    db.rollback()
                    log.error("Error processing broker %s: %s", req.broker_id, e)
                    failed += 1
                    results.append({
                        "broker_id": req.broker_id,
                        "status": "error",
                        "reason": str(e),
                    })

            manual = sum(1 for r in results if r.get("status") == "manual")
            log.info(
                "Send-all: %d sent, %d failed, %d manual, %d total",
                sent, failed, manual, len(pending),
            )

            from backend.core.notifier import EventType, notify
            notify(
                EventType.BLAST_COMPLETE,
                f"Blast complete: {sent} sent",
                f"{sent} requests sent, {failed} failed, {manual} require manual action.",
            )

            return {
                "sent": sent,
                "failed": failed,
                "manual": manual,
                "total": len(pending),
                "results": results,
            }
        finally:
            db.close()

    @r.post("/follow-up")
    async def run_follow_up(session: str | None = Cookie(default=None)) -> dict:
        """Check deadlines and send follow-ups/escalations."""
        key, _salt = session_store.validate(session)
        profile, smtp, _ = vault.load_with_key(key)

        from pathlib import Path

        from backend.core.scheduler import run_follow_ups
        from backend.core.template import TemplateRenderer

        templates_dir = Path(__file__).parent.parent.parent / "templates"
        renderer = TemplateRenderer(templates_dir)

        # Renewal ladders and statutory holds must fire from the WEB follow-up
        # too — server-only deployments have no CLI timer.
        from backend.core.cpr_lever import CprLeverRegistry, check_lever_renewals
        from backend.core.time_locked import (
            TimeLockedRegistry,
            check_time_locked_expiries,
        )

        repo_brokers = Path(__file__).parent.parent.parent / "brokers"

        def _brokers_file(name: str) -> Path:
            p = config.brokers_dir / name
            return p if p.exists() else repo_brokers / name

        # Controller/delisting requests need follow-ups too — resolve via the union
        lookup_registry: BrokerRegistry | RegistryUnion = broker_registry
        if controller_registry is not None:
            lookup_registry = RegistryUnion(
                broker_registry, controller_registry, delisting=delisting_registry,
            )

        db = db_session_factory()
        try:
            result = await run_follow_ups(
                session=db,
                profile=profile,
                smtp=smtp,
                broker_registry=lookup_registry,
                renderer=renderer,
                gdpr_deadline_days=config.gdpr_deadline_days,
            )
            renewals = check_lever_renewals(
                db, CprLeverRegistry.load(_brokers_file("cpr_levers.yaml")),
            )
            fired = check_time_locked_expiries(
                db, TimeLockedRegistry.load(_brokers_file("time_locked.yaml")),
            )
            if result.newly_overdue or result.follow_ups_sent or result.escalations_sent:
                from backend.core.notifier import EventType, notify
                parts = []
                if result.newly_overdue:
                    parts.append(f"{result.newly_overdue} newly overdue")
                if result.follow_ups_sent:
                    parts.append(f"{result.follow_ups_sent} follow-ups sent")
                if result.escalations_sent:
                    parts.append(f"{result.escalations_sent} escalations sent")
                notify(
                    EventType.FOLLOW_UP_COMPLETE,
                    "Follow-up check complete",
                    ", ".join(parts) + ".",
                )

            return {
                "newly_overdue": result.newly_overdue,
                "follow_ups_sent": result.follow_ups_sent,
                "escalations_sent": result.escalations_sent,
                "lever_renewals_due": len(renewals.renewal_due) + len(renewals.escalated),
                "levers_expired": len(renewals.expired),
                "time_locked_fired": len(fired.fired),
                "errors": result.errors,
            }
        finally:
            db.close()

    @r.post("/generate-complaint/{request_id}")
    def generate_complaint(
        request_id: str,
        session: str | None = Cookie(default=None),
    ) -> dict:
        """Generate a DPA complaint for an escalated request."""
        key, _salt = session_store.validate(session)
        profile, _, _ = vault.load_with_key(key)

        from pathlib import Path

        from backend.core.dpa import get_dpa_for_request

        db = db_session_factory()
        try:
            req = db.get(Request, request_id)
            if req is None:
                raise HTTPException(status_code=404, detail="Request not found")

            broker = broker_registry.get(req.broker_id)
            if broker is None and controller_registry is not None:
                broker = controller_registry.get(req.broker_id)
            if broker is None and delisting_registry is not None:
                broker = delisting_registry.get(req.broker_id)
            if broker is None:
                raise HTTPException(status_code=404, detail="Broker not found")

            dpa = get_dpa_for_request(broker, config.user_country)

            # Controllers/delisting: the complaint goes to the residence SA —
            # pass the facts as variables so each locale template renders its
            # own translated jurisdiction paragraph. The two tracks use
            # DIFFERENT blocks: the controller wording ("has no establishment
            # in the EU") is literally true for Snap but would be false for
            # Google, which has EU establishments — just none that controls
            # Search RTBF processing. Delisting therefore gets its own
            # processing-scoped Art. 55/56 wording, plus the URL and the
            # name-query scope (CJEU C-131/12) and the actual filing channel.
            controller_vars: dict = {}
            if broker.category == "controller":
                controller_vars = {
                    "controller_entity": getattr(broker, "eu_entity", ""),
                    "controller_country": getattr(broker, "entity_country", ""),
                    "controller_lead_sa": getattr(broker, "lead_dpa", ""),
                    "controller_no_eu": getattr(broker, "no_eu_establishment", False),
                    "controller_art27_rep": getattr(broker, "art27_rep", None) or "",
                }
            elif broker.category == "delisting":
                controller_vars = {
                    "delisting_url": req.target_url or "",
                    "delisting_query": profile.full_name,
                    "delisting_controller": getattr(broker, "eu_entity", ""),
                    "delisting_channel": "email" if broker.dpo_email else "form",
                    "delisting_no_oss": getattr(broker, "no_eu_establishment", False),
                    "delisting_country": getattr(broker, "entity_country", ""),
                    "delisting_lead_sa": getattr(broker, "lead_dpa", ""),
                }

            # EDPB CEF-2025 rebuttal ammunition, but only when the controller
            # actually REFUSED. Never key this on response_body: a mere
            # acknowledgement sets it too (mark_acknowledged / the IMAP poller),
            # and the block asserts the controller "relies on an exception under
            # Article 17(3)" — a false statement of fact in an Art. 77 complaint.
            # REFUSED -> ESCALATED loses the status, so check the event history.
            from backend.db.models import RequestEvent as _RequestEvent

            edpb_cef = req.status == RequestStatus.REFUSED or (
                db.query(_RequestEvent)
                .filter(
                    _RequestEvent.request_id == req.id,
                    _RequestEvent.event_type == RequestStatus.REFUSED.value,
                )
                .count()
                > 0
            )

            # Reg (EU) 2025/2518's admissibility + 15-month rules apply ONLY to
            # cross-border processing (Art. 4(1)) and ONLY to complaints lodged
            # on/after 2 April 2027 (Art. 36 + Art. 37(2)). A national Art. 55
            # case — Google Search RTBF, Snap, any no-EU-establishment target —
            # is not cross-border, so it must never carry these lines.
            no_eu = getattr(broker, "no_eu_establishment", False)
            lead_sa = getattr(broker, "lead_dpa", "")
            entity_country = getattr(broker, "entity_country", "")
            cross_border = bool(
                broker.category in ("controller", "delisting")
                and not no_eu
                and lead_sa
                and entity_country
                and entity_country.upper() != config.user_country.upper()
            )
            proc_reg = cross_border and _date.today() >= _date(2027, 4, 2)

            # Only claim a follow-up/final warning was sent if one actually was
            # (form-only controllers are never chased by email).
            from backend.db.models import RequestEvent
            followed_up = (
                db.query(RequestEvent)
                .filter(
                    RequestEvent.request_id == req.id,
                    RequestEvent.event_type == "follow_up_sent",
                )
                .count()
            ) > 0

            # Render the complaint template
            templates_dir = Path(__file__).parent.parent.parent / "templates"
            renderer = TemplateRenderer(templates_dir)

            dpa_name = dpa["short_name"] if dpa else "the relevant supervisory authority"
            dpa_language = dpa["language"] if dpa else "en"

            complaint = renderer.render_localized(
                "dpa_complaint",
                dpa_language,
                profile=profile,
                reference_id=req.id[:8].upper(),
                broker_name=broker.name,
                broker_email=broker.dpo_email or getattr(broker, "erasure_form_url", ""),
                original_date=req.sent_at.strftime("%Y-%m-%d") if req.sent_at else "unknown",
                dpa_name=dpa_name,
                followed_up=followed_up,
                edpb_cef=edpb_cef,
                proc_reg=proc_reg,
                **controller_vars,
            )

            return {
                "complaint_text": complaint,
                "dpa": dpa,
                "broker": {
                    "name": broker.name,
                    "domain": broker.domain,
                    "dpo_email": broker.dpo_email,
                    "country": broker.country,
                },
                "request_id": request_id,
            }
        finally:
            db.close()

    @r.get("/dpa-list")
    def list_dpas(session: str | None = Cookie(default=None)):
        """List all known DPAs."""
        session_store.validate(session)
        from backend.core.dpa import DPA_REGISTRY
        return DPA_REGISTRY

    return r
