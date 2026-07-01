"""CPR lever track — Danish upstream protections that cascade to multiple brokers.

Unlike the broker track, the tool cannot perform these actions: they require
MitID on borger.dk / opdater.krak.dk. The tool surfaces the lever, the user
confirms completion, and the tool tracks expiry + renewal reminders.
See docs/tracks/cpr_lever.md for the full state machine.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel

log = logging.getLogger("incognito.cpr_lever")

RENEWAL_WARNING_DAYS = 30


class CprLever(BaseModel):
    lever_id: str
    name: str
    description: str
    url: str
    requires_mitid: bool
    expires_after_days: int | None = None  # None = persistent
    cascade_broker_ids: list[str] = []
    mutual_exclusion: list[str] = []
    notes: str | None = None


class CprLeverRegistry:
    def __init__(self, levers: list[CprLever]):
        self.levers = levers
        self._by_id = {lv.lever_id: lv for lv in levers}

    def get(self, lever_id: str) -> CprLever | None:
        return self._by_id.get(lever_id)

    @classmethod
    def load(cls, path: Path) -> CprLeverRegistry:
        if not path.exists():
            return cls([])
        try:
            data = yaml.safe_load(path.read_text())
            levers = [CprLever.model_validate(lv) for lv in data.get("levers", [])]
        except Exception as e:
            log.warning("Failed to load CPR levers from %s: %s", path, e)
            return cls([])
        return cls(levers)


def compute_expiry(lever: CprLever, activated_at: datetime) -> datetime | None:
    if lever.expires_after_days is None:
        return None
    return activated_at + timedelta(days=lever.expires_after_days)


def effective_status(stored_status: str, expires_at: datetime | None) -> str:
    """Derive the current status from the stored one, applying time transitions.

    ACTIVE -> RENEWAL_DUE at T-30d, -> EXPIRED at T=0. Statuses that don't
    depend on time pass through unchanged.
    """
    if stored_status not in ("active", "renewal_due") or expires_at is None:
        return stored_status
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    if now >= expires_at:
        return "expired"
    if now >= expires_at - timedelta(days=RENEWAL_WARNING_DAYS):
        return "renewal_due"
    return "active"


def covered_broker_ids(
    registry: CprLeverRegistry, states: dict[str, tuple[str, datetime | None]]
) -> set[str]:
    """Broker ids covered by a currently active (or renewal-due) lever.

    `states` maps lever_id -> (stored_status, expires_at). Expired levers
    stop covering their cascade so the pipeline re-includes those brokers.
    """
    covered: set[str] = set()
    for lever in registry.levers:
        stored = states.get(lever.lever_id)
        if stored is None:
            continue
        status = effective_status(stored[0], stored[1])
        if status in ("active", "renewal_due"):
            covered.update(lever.cascade_broker_ids)
    return covered
