
from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel

from backend.api.deps import SessionStore
from backend.core.broker import BrokerRegistry, RemovalMethod
from backend.core.config import AppConfig
from backend.core.profile import ProfileVault
from backend.core.request import RequestManager
from backend.core.template import TemplateRenderer
from backend.db.models import Request, RequestStatus, RequestType


def create_blast_router(
    vault: ProfileVault,
    session_store: SessionStore,
    broker_registry: BrokerRegistry,
    db_session_factory,
    config: AppConfig,
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

            created = []
            skipped = []

            for broker in broker_registry.brokers:
                if broker.id in existing_broker_ids:
                    skipped.append(broker.id)
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

            return {
                "dry_run": body.dry_run,
                "created": len(created),
                "skipped": len(skipped),
                "total_brokers": len(broker_registry.brokers),
                "requests": created,
            }
        finally:
            db.close()

    @r.post("/send-all")
    async def send_all_pending(session: str | None = Cookie(default=None)) -> dict:
        """Send all pending (created) requests via email."""
        password = session_store.validate(session)
        profile, smtp = vault.load(password)

        if smtp is None:
            raise HTTPException(
                status_code=400,
                detail="SMTP not configured. Add SMTP settings before sending requests.",
            )

        from backend.senders.email import EmailSender

        templates_dir = config.data_dir / "templates"
        if not templates_dir.exists():
            from pathlib import Path
            templates_dir = Path(__file__).parent.parent.parent / "templates"

        renderer = TemplateRenderer(templates_dir)
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

            for req in pending:
                broker = broker_registry.get(req.broker_id)
                if broker is None:
                    results.append({
                        "broker_id": req.broker_id,
                        "status": "skipped",
                        "reason": "broker not found",
                    })
                    continue

                # Only send to email-based brokers for now
                if broker.removal_method != RemovalMethod.EMAIL:
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

                result = await sender.send(
                    to_email=broker.dpo_email,
                    rendered_text=rendered,
                )

                if result.status.value == "success":
                    mgr.mark_sent(req.id)
                    sent += 1
                    results.append({
                        "broker_id": req.broker_id,
                        "broker_name": broker.name,
                        "status": "sent",
                        "email": broker.dpo_email,
                    })
                else:
                    failed += 1
                    results.append({
                        "broker_id": req.broker_id,
                        "broker_name": broker.name,
                        "status": "failed",
                        "reason": result.message,
                    })

                # Rate limit
                import asyncio
                await asyncio.sleep(0.5)

            return {
                "sent": sent,
                "failed": failed,
                "manual": sum(1 for r in results if r.get("status") == "manual"),
                "total": len(pending),
                "results": results,
            }
        finally:
            db.close()

    @r.post("/follow-up")
    async def run_follow_up(session: str | None = Cookie(default=None)) -> dict:
        """Check deadlines and send follow-ups/escalations."""
        password = session_store.validate(session)
        profile, smtp = vault.load(password)

        from pathlib import Path

        from backend.core.scheduler import run_follow_ups
        from backend.core.template import TemplateRenderer

        templates_dir = Path(__file__).parent.parent.parent / "templates"
        renderer = TemplateRenderer(templates_dir)

        db = db_session_factory()
        try:
            result = await run_follow_ups(
                session=db,
                profile=profile,
                smtp=smtp,
                broker_registry=broker_registry,
                renderer=renderer,
                gdpr_deadline_days=config.gdpr_deadline_days,
            )
            return {
                "newly_overdue": result.newly_overdue,
                "follow_ups_sent": result.follow_ups_sent,
                "escalations_sent": result.escalations_sent,
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
        password = session_store.validate(session)
        profile, _ = vault.load(password)

        from pathlib import Path

        from backend.core.dpa import get_dpa_for_country

        db = db_session_factory()
        try:
            req = db.get(Request, request_id)
            if req is None:
                raise HTTPException(status_code=404, detail="Request not found")

            broker = broker_registry.get(req.broker_id)
            if broker is None:
                raise HTTPException(status_code=404, detail="Broker not found")

            dpa = get_dpa_for_country(broker.country)

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
                broker_email=broker.dpo_email,
                original_date=req.sent_at.strftime("%Y-%m-%d") if req.sent_at else "unknown",
                dpa_name=dpa_name,
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
