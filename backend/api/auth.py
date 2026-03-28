from fastapi import APIRouter, Response, Cookie, HTTPException
from pydantic import BaseModel

from backend.api.deps import SessionStore
from backend.core.profile import ProfileVault


def create_auth_router(vault: ProfileVault, session_store: SessionStore) -> APIRouter:
    r = APIRouter(prefix="/api/auth", tags=["auth"])

    class UnlockRequest(BaseModel):
        password: str

    @r.get("/status")
    def status():
        return {"initialized": vault.exists()}

    @r.post("/unlock")
    def unlock(req: UnlockRequest, response: Response):
        if not vault.exists():
            raise HTTPException(status_code=400, detail="Not initialized")
        try:
            vault.load(req.password)
        except Exception:
            raise HTTPException(status_code=401, detail="Wrong password")

        token = session_store.create(req.password)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            samesite="strict",
            secure=False,
        )
        return {"status": "unlocked"}

    @r.post("/lock")
    def lock(response: Response, session: str | None = Cookie(default=None)):
        session_store.destroy(session)
        response.delete_cookie("session")
        return {"status": "locked"}

    return r
