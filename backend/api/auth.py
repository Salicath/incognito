import logging

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel

from backend.api.deps import LoginRateLimiter, SessionStore
from backend.core.profile import ProfileVault

log = logging.getLogger("incognito.auth")


def create_auth_router(
    vault: ProfileVault,
    session_store: SessionStore,
    rate_limiter: LoginRateLimiter,
) -> APIRouter:
    r = APIRouter(prefix="/api/auth", tags=["auth"])

    class UnlockRequest(BaseModel):
        password: str

    @r.get("/status")
    def status():
        return {"initialized": vault.exists()}

    @r.post("/unlock")
    def unlock(req: UnlockRequest, request: Request, response: Response):
        if not vault.exists():
            raise HTTPException(status_code=400, detail="Not initialized")

        client_ip = request.client.host if request.client else "unknown"
        rate_limiter.check(client_ip)

        try:
            derived_key, salt = vault.derive_key_from_file(req.password)
            vault.load_with_key(derived_key)
        except Exception:
            rate_limiter.record_failure(client_ip)
            log.warning("Failed unlock attempt from %s", client_ip)
            raise HTTPException(status_code=401, detail="Wrong password") from None

        rate_limiter.record_success(client_ip)
        token = session_store.create(derived_key, salt)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            samesite="strict",
            secure=False,
        )
        log.info("Vault unlocked from %s", client_ip)
        return {"status": "unlocked"}

    @r.post("/lock")
    def lock(response: Response, session: str | None = Cookie(default=None)):
        session_store.destroy(session)
        response.delete_cookie("session")
        log.info("Session locked")
        return {"status": "locked"}

    return r
