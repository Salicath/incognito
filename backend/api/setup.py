from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from backend.api.deps import SessionStore
from backend.core.profile import Profile, ProfileVault, SmtpConfig


def create_setup_router(vault: ProfileVault, session_store: SessionStore) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["setup"])

    class SetupRequest(BaseModel):
        password: str
        profile: Profile
        smtp: SmtpConfig | None = None

    @r.post("/setup")
    def setup(req: SetupRequest, response: Response):
        if vault.exists():
            raise HTTPException(status_code=400, detail="Already initialized")

        vault.save(req.profile, req.smtp, req.password)

        token = session_store.create(req.password)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            samesite="strict",
            secure=False,
        )
        return {"status": "initialized"}

    return r
