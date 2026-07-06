import logging
from pathlib import Path
from typing import cast

from fastapi import APIRouter, Cookie, HTTPException

from backend.api.deps import SessionStore
from backend.core.config import AppConfig
from backend.core.controller import ControllerRegistry, account_email_ok, build_kit
from backend.core.profile import ProfileVault
from backend.core.request import RequestManager
from backend.core.template import TemplateRenderer
from backend.db.models import (
    EmailDirection,
    EmailMessage,
    Request,
    RequestStatus,
    RequestType,
)
from backend.senders.email import EmailSender

log = logging.getLogger("incognito.controllers")


def create_controllers_router(
    vault: ProfileVault,
    session_store: SessionStore,
    controller_registry: ControllerRegistry,
    db_session_factory,
    config: AppConfig,
) -> APIRouter:
    r = APIRouter(prefix="/api/controllers", tags=["controllers"])

    def _renderer() -> TemplateRenderer:
        repo_templates = Path(__file__).parent.parent.parent / "templates"
        templates_dir = config.data_dir / "templates"
        if not templates_dir.exists():
            templates_dir = repo_templates
        return TemplateRenderer(templates_dir, fallback_dir=repo_templates)

    def _latest_request(db, controller_id: str) -> Request | None:
        return cast(
            "Request | None",
            db.query(Request)
            .filter(
                Request.broker_id == controller_id,
                Request.request_type == RequestType.ERASURE,
            )
            .order_by(Request.created_at.desc())
            .first(),
        )

    def _serialize_request(req: Request | None) -> dict | None:
        if req is None:
            return None
        return {
            "id": req.id,
            "status": req.status.value,
            "sent_at": req.sent_at.isoformat() if req.sent_at else None,
            "deadline_at": req.deadline_at.isoformat() if req.deadline_at else None,
            "created_at": req.created_at.isoformat() if req.created_at else None,
        }

    @r.get("")
    def list_controllers(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = db_session_factory()
        try:
            out = []
            for c in controller_registry.controllers:
                item = c.model_dump()
                item["request"] = _serialize_request(_latest_request(db, c.id))
                out.append(item)
            return out
        finally:
            db.close()

    @r.post("/{controller_id}/request")
    async def create_controller_request(
        controller_id: str, session: str | None = Cookie(default=None)
    ) -> dict:
        """Opt-in erasure for one platform.

        Email-viable controllers get the request sent immediately; form-only
        ones enter MANUAL_ACTION_NEEDED and the user files the returned kit.
        """
        key, _salt = session_store.validate(session)
        controller = controller_registry.get(controller_id)
        if controller is None:
            raise HTTPException(status_code=404, detail="Controller not found")

        profile, smtp, _ = vault.load_with_key(key)
        if controller.email_viable and smtp is None:
            raise HTTPException(
                status_code=400,
                detail="SMTP not configured. Add SMTP settings before sending requests.",
            )

        db = db_session_factory()
        try:
            existing = _latest_request(db, controller.id)
            req = None
            if existing and existing.status == RequestStatus.CREATED:
                # A previous send failed — retry on the same request
                req = existing
            elif existing and existing.status != RequestStatus.COMPLETED:
                raise HTTPException(
                    status_code=409,
                    detail=f"An active request already exists ({existing.status.value})",
                )

            mgr = RequestManager(db, config.gdpr_deadline_days)
            if req is None:
                req = mgr.create(controller.id, RequestType.ERASURE)
            renderer = _renderer()
            kit = build_kit(controller, profile, req.id[:8].upper(), renderer)

            # Platforms that only accept requests from the account's own email
            # (Reddit) fall back to the manual kit when the SMTP identity is
            # not one of the user's addresses — an auto-send would be rejected.
            manual_reason = None
            if not controller.email_viable:
                manual_reason = "Form-only controller — file the kit via the web form"
            elif smtp is not None and not account_email_ok(controller, profile, smtp):
                manual_reason = (
                    "Platform requires the request to come from your account email "
                    f"({smtp.username} is not among your profile emails) — send the "
                    "kit yourself from the right mailbox"
                )

            if manual_reason is not None:
                if req.status == RequestStatus.CREATED:
                    mgr.mark_manual_action_needed(req.id, manual_reason)
                return {
                    "request_id": req.id,
                    "status": "manual_action_needed",
                    "kit": kit,
                    "reason": manual_reason,
                }

            assert smtp is not None  # guarded before request creation
            sender = EmailSender(smtp)
            result = await sender.send(
                to_email=controller.privacy_email,
                rendered_text=kit["request_text"],
                request_id=req.id,
                cc=controller.cc_emails or None,
            )
            if result.status.value != "success":
                # Request stays CREATED; blast send-all can't sweep it up because
                # controllers are not in the broker registry.
                raise HTTPException(
                    status_code=502, detail=f"Send failed: {result.message}"
                )

            req.message_id = f"<{req.id}@incognito.local>"
            db.add(
                EmailMessage(
                    request_id=req.id,
                    message_id=req.message_id,
                    direction=EmailDirection.OUTBOUND,
                    from_address=smtp.username,
                    to_address=controller.privacy_email,
                    subject=f"GDPR Erasure Request [REF-{req.id[:8].upper()}]",
                    body_text=kit["request_text"],
                )
            )
            mgr.mark_sent(req.id)
            log.info("Controller erasure sent to %s (%s)", controller.name, req.id)
            return {"request_id": req.id, "status": "sent", "kit": kit}
        finally:
            db.close()

    @r.get("/{controller_id}/kit")
    def get_kit(controller_id: str, session: str | None = Cookie(default=None)) -> dict:
        key, _salt = session_store.validate(session)
        controller = controller_registry.get(controller_id)
        if controller is None:
            raise HTTPException(status_code=404, detail="Controller not found")

        db = db_session_factory()
        try:
            req = _latest_request(db, controller.id)
            if req is None or req.status == RequestStatus.COMPLETED:
                raise HTTPException(status_code=404, detail="No active request")
            profile, _, _ = vault.load_with_key(key)
            renderer = _renderer()
            kit = build_kit(controller, profile, req.id[:8].upper(), renderer)
            return {"request_id": req.id, "kit": kit}
        finally:
            db.close()

    return r
