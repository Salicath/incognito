"""time_locked track — Danish statutory retention holds.

Some holders (banks under hvidvaskloven, insurers under forældelsesloven)
cannot erase until a statutory period lapses. The user arms an entry with the
trigger date (relationship ended, last invoice due, ...); the tool computes
fires_at and raises an Art. 17 kit the day the retention duty matures — for
the bank/telco entries the statute itself mandates deletion at that point, so
the request enforces a matured duty. See docs/tracks/time_locked.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel

from backend.core.notifier import EventType, notify

log = logging.getLogger("incognito.time_locked")


class ExpiryRule(BaseModel):
    years: int
    from_fiscal_year_end: bool = False
    conservative_years: int | None = None


class TimeLockedEntry(BaseModel):
    id: str
    name: str
    holder_type: str
    legal_basis: str
    trigger_label: str
    expiry: ExpiryRule
    escalation_after_days: int = 0
    art17_note: str
    notes: str | None = None


class TimeLockedRegistry:
    def __init__(self, entries: list[TimeLockedEntry]):
        self.entries = entries
        self._by_id = {e.id: e for e in entries}

    def get(self, entry_id: str) -> TimeLockedEntry | None:
        return self._by_id.get(entry_id)

    @classmethod
    def load(cls, path: Path) -> TimeLockedRegistry:
        if not path.exists():
            return cls([])
        try:
            data = yaml.safe_load(path.read_text())
            entries = [
                TimeLockedEntry.model_validate(e) for e in data.get("entries", [])
            ]
        except Exception as e:
            log.warning("Failed to load time_locked entries from %s: %s", path, e)
            return cls([])
        return cls(entries)


def _add_years(d: date, years: int) -> date:
    """Same month/day N years on; Feb 29 maps to Feb 28."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def compute_fires_at(
    entry: TimeLockedEntry, trigger: date, conservative: bool = False,
) -> date:
    """When the holder's retention duty matures for a user-entered trigger date.

    from_fiscal_year_end (bogføringsloven): the period runs from the end of
    the trigger's fiscal year (assumed 31 Dec), and the request fires the day
    AFTER it lapses.
    """
    years = entry.expiry.years
    if conservative and entry.expiry.conservative_years:
        years = entry.expiry.conservative_years
    if entry.expiry.from_fiscal_year_end:
        fiscal_end = date(trigger.year, 12, 31)
        return _add_years(fiscal_end, years) + timedelta(days=1)
    return _add_years(trigger, years)


@dataclass
class TimeLockedCheckResult:
    fired: list[str] = field(default_factory=list)


def check_time_locked_expiries(db, registry: TimeLockedRegistry) -> TimeLockedCheckResult:
    """Follow-up-time job: move armed holds whose date arrived to FIRED, once."""
    from backend.db.models import TimeLockedState, TimeLockedStatus

    result = TimeLockedCheckResult()
    now = datetime.now(UTC)
    armed = (
        db.query(TimeLockedState)
        .filter(TimeLockedState.status == TimeLockedStatus.ARMED)
        .all()
    )
    dirty = False
    for state in armed:
        fires_at = state.fires_at
        if fires_at.tzinfo is None:
            fires_at = fires_at.replace(tzinfo=UTC)
        if now < fires_at:
            continue
        entry = registry.get(state.entry_id)
        state.status = TimeLockedStatus.FIRED
        dirty = True
        result.fired.append(state.entry_id)
        label = entry.name if entry else state.entry_id
        who = f" ({state.institution})" if state.institution else ""
        notify(
            EventType.REQUEST_OVERDUE,
            f"Statutory retention lapsed: {label}{who}",
            "The retention period blocking erasure has matured — send the "
            "Art. 17 now (kit on the Statutory page).",
        )
    if dirty:
        db.commit()
    return result
