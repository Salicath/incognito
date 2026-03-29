from __future__ import annotations

import secrets
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import HTTPException


class LoginRateLimiter:
    """Blocks login attempts after too many failures within a time window."""

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 300,
        lockout_seconds: int = 600,
    ):
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._lockout_seconds = lockout_seconds
        self._attempts: defaultdict[str, list[datetime]] = defaultdict(list)
        self._lockouts: dict[str, datetime] = {}

    def check(self, key: str) -> None:
        """Raise 429 if the key is locked out."""
        now = datetime.now(UTC)

        # Check active lockout
        locked_until = self._lockouts.get(key)
        if locked_until and now < locked_until:
            remaining = int((locked_until - now).total_seconds())
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed attempts. Try again in {remaining} seconds.",
            )
        elif locked_until:
            # Lockout expired — clear it
            del self._lockouts[key]
            self._attempts.pop(key, None)

    def record_failure(self, key: str) -> None:
        """Record a failed attempt. Lock out if threshold exceeded."""
        now = datetime.now(UTC)
        cutoff = now.timestamp() - self._window_seconds

        # Prune old attempts
        self._attempts[key] = [
            t for t in self._attempts[key] if t.timestamp() > cutoff
        ]
        self._attempts[key].append(now)

        if len(self._attempts[key]) >= self._max_attempts:
            from datetime import timedelta
            self._lockouts[key] = now + timedelta(seconds=self._lockout_seconds)

    def record_success(self, key: str) -> None:
        """Clear attempts on successful login."""
        self._attempts.pop(key, None)
        self._lockouts.pop(key, None)


class SessionStore:
    """Stores session tokens mapped to derived encryption keys (never raw passwords)."""

    MAX_SESSIONS = 3

    def __init__(self, timeout_minutes: int):
        self._timeout_minutes = timeout_minutes
        # Maps token -> (derived_key, salt, last_access)
        self._sessions: dict[str, tuple[bytes, bytes, datetime]] = {}

    def _cleanup_expired(self) -> None:
        """Remove expired sessions."""
        now = datetime.now(UTC)
        expired = [
            tok for tok, (_, _, last) in self._sessions.items()
            if (now - last).total_seconds() > self._timeout_minutes * 60
        ]
        for tok in expired:
            del self._sessions[tok]

    def create(self, derived_key: bytes, salt: bytes) -> str:
        self._cleanup_expired()
        # Evict oldest session if at limit
        while len(self._sessions) >= self.MAX_SESSIONS:
            oldest = min(self._sessions, key=lambda t: self._sessions[t][2])
            del self._sessions[oldest]
        token = secrets.token_urlsafe(32)
        self._sessions[token] = (derived_key, salt, datetime.now(UTC))
        return token

    def validate(self, token: str | None) -> tuple[bytes, bytes]:
        """Validate session and return (derived_key, salt)."""
        if token is None:
            raise HTTPException(status_code=401, detail="Not authenticated")

        entry = self._sessions.get(token)
        if entry is None:
            raise HTTPException(status_code=401, detail="Invalid session")

        derived_key, salt, last_access = entry
        elapsed = (datetime.now(UTC) - last_access).total_seconds()
        if elapsed > self._timeout_minutes * 60:
            del self._sessions[token]
            raise HTTPException(status_code=401, detail="Session expired")

        self._sessions[token] = (derived_key, salt, datetime.now(UTC))
        return derived_key, salt

    def destroy(self, token: str | None) -> None:
        if token and token in self._sessions:
            del self._sessions[token]
