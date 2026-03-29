
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from backend.api.deps import SessionStore
from backend.core.profile import Profile, ProfileVault, SmtpConfig


def create_setup_router(
    vault: ProfileVault,
    session_store: SessionStore,
    *,
    secure_cookies: bool = False,
) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["setup"])

    class SetupRequest(BaseModel):
        password: str
        profile: Profile
        smtp: SmtpConfig | None = None

    @r.post("/setup")
    def setup(req: SetupRequest, response: Response):
        if len(req.password) < 8:
            raise HTTPException(
                status_code=400,
                detail="Password must be at least 8 characters",
            )

        try:
            vault.create_initial(req.profile, req.smtp, req.password)
        except FileExistsError:
            raise HTTPException(status_code=400, detail="Already initialized") from None

        # Derive key for session (don't store raw password)
        derived_key, salt = vault.derive_key_from_file(req.password)
        token = session_store.create(derived_key, salt)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            samesite="strict",
            secure=secure_cookies,
        )
        return {"status": "initialized"}

    return r
