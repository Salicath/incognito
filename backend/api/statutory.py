import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel

from backend.api.deps import SessionStore
from backend.core.config import AppConfig
from backend.core.profile import ProfileVault
from backend.core.restriction_only import RestrictionRegistry
from backend.core.template import TemplateRenderer
from backend.core.time_locked import TimeLockedRegistry, compute_fires_at
from backend.db.models import TimeLockedState, TimeLockedStatus

log = logging.getLogger("incognito.statutory")


class ArmRequest(BaseModel):
    trigger_date: str  # ISO date
    institution: str = ""
    conservative: bool = False


def create_statutory_router(
    vault: ProfileVault,
    session_store: SessionStore,
    time_locked_registry: TimeLockedRegistry,
    restriction_registry: RestrictionRegistry,
    db_session_factory,
    config: AppConfig,
) -> APIRouter:
    r = APIRouter(prefix="/api/statutory", tags=["statutory"])

    def _serialize_state(s: TimeLockedState) -> dict:
        return {
            "id": s.id,
            "entry_id": s.entry_id,
            "institution": s.institution,
            "trigger_date": s.trigger_date.date().isoformat(),
            "fires_at": s.fires_at.date().isoformat(),
            "conservative": s.conservative,
            "status": s.status.value,
        }

    @r.get("/time-locked")
    def list_time_locked(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = db_session_factory()
        try:
            states = db.query(TimeLockedState).all()
            by_entry: dict[str, list[dict]] = {}
            for s in states:
                by_entry.setdefault(s.entry_id, []).append(_serialize_state(s))
            out = []
            for e in time_locked_registry.entries:
                item = e.model_dump()
                item["holds"] = by_entry.get(e.id, [])
                out.append(item)
            return out
        finally:
            db.close()

    @r.post("/time-locked/{entry_id}/arm")
    def arm(
        entry_id: str, body: ArmRequest, session: str | None = Cookie(default=None),
    ):
        session_store.validate(session)
        entry = time_locked_registry.get(entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Entry not found")
        try:
            trigger = datetime.fromisoformat(body.trigger_date).date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid trigger_date") from None
        # Trigger events are (near-)past events; a typo like 0224-03-15 would
        # otherwise arm a hold that fires instantly with a nonsense letter.
        from datetime import date as _date
        from datetime import timedelta as _timedelta
        if not (_date(1970, 1, 1) <= trigger <= _date.today() + _timedelta(days=366)):
            raise HTTPException(
                status_code=400,
                detail="trigger_date must be between 1970 and one year from now",
            )

        fires = compute_fires_at(entry, trigger, conservative=body.conservative)
        db = db_session_factory()
        try:
            state = TimeLockedState(
                entry_id=entry.id,
                institution=body.institution.strip(),
                trigger_date=datetime(trigger.year, trigger.month, trigger.day, tzinfo=UTC),
                fires_at=datetime(fires.year, fires.month, fires.day, tzinfo=UTC),
                conservative=body.conservative,
                status=(
                    TimeLockedStatus.FIRED
                    if fires <= datetime.now(UTC).date()
                    else TimeLockedStatus.ARMED
                ),
            )
            db.add(state)
            db.commit()
            # Arming with an already-lapsed trigger fires immediately — the
            # scheduler only notifies ARMED→FIRED transitions, so notify here
            # or this hold's "send now" prompt would never surface.
            if state.status == TimeLockedStatus.FIRED:
                from backend.core.notifier import EventType, notify
                label = entry.name
                who = f" ({state.institution})" if state.institution else ""
                notify(
                    EventType.REQUEST_OVERDUE,
                    f"Statutory retention already lapsed: {label}{who}",
                    "The retention period blocking erasure has already matured — "
                    "send the Art. 17 now (kit on the Statutory page).",
                )
            return _serialize_state(state)
        finally:
            db.close()

    @r.post("/time-locked/holds/{hold_id}/dismiss")
    def dismiss(hold_id: int, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = db_session_factory()
        try:
            state = db.get(TimeLockedState, hold_id)
            if state is None:
                raise HTTPException(status_code=404, detail="Hold not found")
            state.status = TimeLockedStatus.DISMISSED
            db.commit()
            return _serialize_state(state)
        finally:
            db.close()

    @r.get("/time-locked/holds/{hold_id}/kit")
    def kit(hold_id: int, session: str | None = Cookie(default=None)):
        """Art. 17 text citing the matured retention duty — assist-only; the
        holder is the user's own bank/insurer/employer, not a registry entry."""
        key, _salt = session_store.validate(session)
        db = db_session_factory()
        try:
            state = db.get(TimeLockedState, hold_id)
            if state is None:
                raise HTTPException(status_code=404, detail="Hold not found")
            if state.status != TimeLockedStatus.FIRED:
                raise HTTPException(
                    status_code=400,
                    detail=f"Retention has not lapsed yet ({state.status.value})",
                )
            entry = time_locked_registry.get(state.entry_id)
            if entry is None:
                raise HTTPException(status_code=404, detail="Entry not found")

            profile, _, _ = vault.load_with_key(key)
            repo_templates = Path(__file__).parent.parent.parent / "templates"
            templates_dir = config.data_dir / "templates"
            if not templates_dir.exists():
                templates_dir = repo_templates
            renderer = TemplateRenderer(templates_dir, fallback_dir=repo_templates)
            text = renderer.render_localized(
                "time_locked_erasure",
                "da",
                profile=profile,
                entry=entry,
                trigger_date=state.trigger_date.date().isoformat(),
                fires_at=state.fires_at.date().isoformat(),
            )
            return {
                "hold": _serialize_state(state),
                "request_text": text,
                "escalation_after_days": entry.escalation_after_days,
            }
        finally:
            db.close()

    @r.get("/restriction-only")
    def list_restriction_only(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        return [e.model_dump() for e in restriction_registry.entries]

    return r
