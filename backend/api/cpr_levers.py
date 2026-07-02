import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel

from backend.api.deps import SessionStore
from backend.core.broker import BrokerRegistry
from backend.core.cpr_lever import CprLeverRegistry, compute_expiry, effective_status
from backend.db.models import CprLeverState, CprLeverStatus

log = logging.getLogger("incognito.api.cpr_levers")


class DeferRequest(BaseModel):
    note: str = ""


def create_cpr_levers_router(
    lever_registry: CprLeverRegistry,
    broker_registry: BrokerRegistry,
    session_store: SessionStore,
    db_session_factory,
) -> APIRouter:
    r = APIRouter(prefix="/api/cpr-levers", tags=["cpr-levers"])

    def _states(db) -> dict[str, CprLeverState]:
        return {s.lever_id: s for s in db.query(CprLeverState).all()}

    def _serialize(lever, state: CprLeverState | None, states: dict[str, CprLeverState]):
        stored = state.status.value if state else "new"
        expires_at = state.expires_at if state else None
        status = effective_status(stored, expires_at)

        activated_at = state.activated_at if state else None
        cascade = [
            {"broker_id": bid, "name": b.name if (b := broker_registry.get(bid)) else bid}
            for bid in lever.cascade_broker_ids
        ]
        conflicts = [
            other_id
            for other_id in lever.mutual_exclusion
            if (other := states.get(other_id))
            and effective_status(other.status.value, other.expires_at)
            in ("active", "renewal_due")
        ]
        return {
            "lever_id": lever.lever_id,
            "name": lever.name,
            "description": lever.description,
            "url": lever.url,
            "requires_mitid": lever.requires_mitid,
            "expires_after_days": lever.expires_after_days,
            "notes": lever.notes,
            "status": status,
            "activated_at": activated_at.isoformat() if activated_at else None,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "user_note": state.user_note if state else "",
            "cascade": cascade,
            "active_conflicts": conflicts,
        }

    @r.get("")
    def list_levers(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = db_session_factory()
        try:
            states = _states(db)
            return [_serialize(lv, states.get(lv.lever_id), states) for lv in lever_registry.levers]
        finally:
            db.close()

    @r.post("/{lever_id}/confirm")
    def confirm_lever(lever_id: str, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        lever = lever_registry.get(lever_id)
        if lever is None:
            raise HTTPException(status_code=404, detail="Lever not found")

        db = db_session_factory()
        try:
            states = _states(db)
            for other_id in lever.mutual_exclusion:
                other = states.get(other_id)
                if other and effective_status(other.status.value, other.expires_at) in (
                    "active",
                    "renewal_due",
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=f"Conflicts with active lever '{other_id}' (CPR registry rule)",
                    )

            now = datetime.now(UTC)
            state = states.get(lever_id) or CprLeverState(lever_id=lever_id)
            state.status = CprLeverStatus.ACTIVE
            state.activated_at = now
            state.expires_at = compute_expiry(lever, now)
            state.reminder_stage = 0
            db.merge(state)
            db.commit()
            return {
                "status": "active",
                "activated_at": now.isoformat(),
                "expires_at": state.expires_at.isoformat() if state.expires_at else None,
            }
        finally:
            db.close()

    @r.post("/{lever_id}/defer")
    def defer_lever(
        lever_id: str, body: DeferRequest, session: str | None = Cookie(default=None)
    ):
        session_store.validate(session)
        if lever_registry.get(lever_id) is None:
            raise HTTPException(status_code=404, detail="Lever not found")

        db = db_session_factory()
        try:
            state = db.get(CprLeverState, lever_id) or CprLeverState(lever_id=lever_id)
            state.status = CprLeverStatus.USER_DEFERRED
            state.activated_at = None
            state.expires_at = None
            state.user_note = body.note
            db.merge(state)
            db.commit()
            return {"status": "user_deferred"}
        finally:
            db.close()

    return r
