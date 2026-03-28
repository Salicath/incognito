from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import Cookie, HTTPException


class SessionStore:
    def __init__(self, timeout_minutes: int):
        self._timeout_minutes = timeout_minutes
        self._sessions: dict[str, tuple[str, datetime]] = {}

    def create(self, password: str) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = (password, datetime.now(timezone.utc))
        return token

    def validate(self, token: str | None) -> str:
        if token is None:
            raise HTTPException(status_code=401, detail="Not authenticated")

        entry = self._sessions.get(token)
        if entry is None:
            raise HTTPException(status_code=401, detail="Invalid session")

        password, last_access = entry
        elapsed = (datetime.now(timezone.utc) - last_access).total_seconds()
        if elapsed > self._timeout_minutes * 60:
            del self._sessions[token]
            raise HTTPException(status_code=401, detail="Session expired")

        self._sessions[token] = (password, datetime.now(timezone.utc))
        return password

    def destroy(self, token: str | None) -> None:
        if token and token in self._sessions:
            del self._sessions[token]
