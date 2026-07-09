import logging

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel

from backend.api.deps import LoginRateLimiter, SessionStore
from backend.core.profile import ProfileVault

log = logging.getLogger("incognito.auth")


def client_ip_for(request: Request, trusted_proxy_header: str = "") -> str:
    """The IP to key login rate-limiting on.

    Direct binds: the socket peer. Behind a reverse proxy every request has the
    proxy's IP, so five failures from anyone would lock out the real user —
    take the client IP from X-Forwarded-For instead.

    Only when `trusted_proxy_header` is configured (the operator asserting a
    proxy fronts us), and only the RIGHTMOST entry: proxies append the peer
    they saw, so the last hop is the one our trusted proxy observed. Earlier
    entries are attacker-controlled and must never be trusted.

    Assumes exactly one trusted hop. If you set `trusted_proxy_header` without
    actually putting a proxy in front, a client controls the whole header and
    can forge this value — don't.
    """
    peer = request.client.host if request.client else "unknown"
    if not trusted_proxy_header:
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return peer
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    return hops[-1] if hops else peer


def create_auth_router(
    vault: ProfileVault,
    session_store: SessionStore,
    rate_limiter: LoginRateLimiter,
    *,
    secure_cookies: bool = False,
    trusted_proxy_header: str = "",
) -> APIRouter:
    r = APIRouter(prefix="/api/auth", tags=["auth"])

    class UnlockRequest(BaseModel):
        password: str

    @r.get("/status")
    def status(request: Request):
        result: dict = {"initialized": vault.exists()}
        if trusted_proxy_header:
            proxy_user = request.headers.get(trusted_proxy_header)
            result["proxy_auth"] = proxy_user is not None
        return result

    @r.post("/unlock")
    def unlock(req: UnlockRequest, request: Request, response: Response):
        if not vault.exists():
            raise HTTPException(status_code=400, detail="Not initialized")

        client_ip = client_ip_for(request, trusted_proxy_header)
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
            secure=secure_cookies,
            path="/",
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
