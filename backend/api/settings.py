from typing import Optional

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel

from backend.api.deps import SessionStore
from backend.core.broker import BrokerRegistry
from backend.core.config import AppConfig
from backend.core.profile import Profile, ProfileVault, SmtpConfig


def create_settings_router(
    vault: ProfileVault,
    session_store: SessionStore,
    broker_registry: BrokerRegistry,
    config: AppConfig,
) -> APIRouter:
    r = APIRouter(prefix="/api/settings", tags=["settings"])

    class UpdateProfileRequest(BaseModel):
        profile: Profile

    class UpdateSmtpRequest(BaseModel):
        smtp: SmtpConfig

    @r.get("/info")
    def get_info(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        return {
            "broker_count": len(broker_registry.brokers),
            "data_dir": str(config.data_dir),
            "version": "0.1.0",
        }

    @r.get("/smtp")
    def get_smtp_status(session: str | None = Cookie(default=None)):
        password = session_store.validate(session)
        _, smtp = vault.load(password)
        if smtp is None:
            return {"configured": False}
        return {
            "configured": True,
            "host": smtp.host,
            "port": smtp.port,
            "username": smtp.username,
            # Don't return the password
        }

    @r.post("/smtp")
    def update_smtp(body: UpdateSmtpRequest, session: str | None = Cookie(default=None)):
        password = session_store.validate(session)
        profile, _ = vault.load(password)
        vault.save(profile, body.smtp, password)
        return {"status": "updated"}

    @r.post("/profile")
    def update_profile(body: UpdateProfileRequest, session: str | None = Cookie(default=None)):
        password = session_store.validate(session)
        _, smtp = vault.load(password)
        vault.save(body.profile, smtp, password)
        return {"status": "updated"}

    @r.post("/test-smtp")
    async def test_smtp(session: str | None = Cookie(default=None)):
        password = session_store.validate(session)
        profile, smtp = vault.load(password)
        if smtp is None:
            raise HTTPException(status_code=400, detail="SMTP not configured")

        from backend.senders.email import EmailSender
        sender = EmailSender(smtp)
        result = await sender.send(
            to_email=smtp.username,  # Send test to self
            rendered_text=f"Subject: Incognito SMTP Test\n\nThis is a test email from Incognito. If you received this, your SMTP configuration is working correctly.",
        )
        if result.status.value == "success":
            return {"status": "success", "message": f"Test email sent to {smtp.username}"}
        else:
            raise HTTPException(status_code=400, detail=f"SMTP test failed: {result.message}")

    return r
