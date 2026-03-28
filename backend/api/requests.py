from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import SessionStore
from backend.core.request import InvalidTransitionError, RequestManager
from backend.db.models import Request, RequestEvent, RequestStatus, RequestType


def create_requests_router(
    db_session_factory, session_store: SessionStore, gdpr_deadline_days: int
) -> APIRouter:
    r = APIRouter(prefix="/api/requests", tags=["requests"])

    class CreateRequest(BaseModel):
        broker_id: str
        request_type: RequestType

    class TransitionRequest(BaseModel):
        action: str
        details: str | None = None

    def _get_db() -> Session:
        return db_session_factory()

    @r.get("/stats")
    def stats(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = _get_db()
        try:
            all_requests = db.query(Request).all()
            counts = {}
            for status in RequestStatus:
                counts[status.value] = sum(1 for req in all_requests if req.status == status)
            counts["total"] = len(all_requests)
            return counts
        finally:
            db.close()

    @r.get("")
    def list_requests(
        status: str | None = None,
        session: str | None = Cookie(default=None),
    ):
        session_store.validate(session)
        db = _get_db()
        try:
            query = db.query(Request)
            if status:
                query = query.filter(Request.status == status)
            requests = query.order_by(Request.created_at.desc()).all()
            return [
                {
                    "id": req.id,
                    "broker_id": req.broker_id,
                    "request_type": req.request_type.value,
                    "status": req.status.value,
                    "sent_at": req.sent_at.isoformat() if req.sent_at else None,
                    "deadline_at": req.deadline_at.isoformat() if req.deadline_at else None,
                    "created_at": req.created_at.isoformat() if req.created_at else None,
                }
                for req in requests
            ]
        finally:
            db.close()

    @r.post("")
    def create_request(body: CreateRequest, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = _get_db()
        try:
            mgr = RequestManager(db, gdpr_deadline_days)
            req = mgr.create(body.broker_id, body.request_type)
            return {
                "id": req.id,
                "broker_id": req.broker_id,
                "request_type": req.request_type.value,
                "status": req.status.value,
            }
        finally:
            db.close()

    @r.get("/{request_id}")
    def get_request(request_id: str, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = _get_db()
        try:
            req = db.get(Request, request_id)
            if req is None:
                raise HTTPException(status_code=404, detail="Request not found")
            return {
                "id": req.id,
                "broker_id": req.broker_id,
                "request_type": req.request_type.value,
                "status": req.status.value,
                "sent_at": req.sent_at.isoformat() if req.sent_at else None,
                "deadline_at": req.deadline_at.isoformat() if req.deadline_at else None,
                "response_at": req.response_at.isoformat() if req.response_at else None,
                "response_body": req.response_body,
                "created_at": req.created_at.isoformat() if req.created_at else None,
            }
        finally:
            db.close()

    @r.get("/{request_id}/events")
    def get_events(request_id: str, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = _get_db()
        try:
            events = (
                db.query(RequestEvent)
                .filter_by(request_id=request_id)
                .order_by(RequestEvent.id)
                .all()
            )
            return [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "details": e.details,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ]
        finally:
            db.close()

    @r.post("/{request_id}/transition")
    def transition(
        request_id: str, body: TransitionRequest, session: str | None = Cookie(default=None)
    ):
        session_store.validate(session)
        db = _get_db()
        try:
            mgr = RequestManager(db, gdpr_deadline_days)
            action_map = {
                "mark_sent": mgr.mark_sent,
                "mark_acknowledged": lambda rid: mgr.mark_acknowledged(rid, body.details or ""),
                "mark_completed": mgr.mark_completed,
                "mark_refused": lambda rid: mgr.mark_refused(rid, body.details or ""),
                "mark_overdue": mgr.mark_overdue,
                "mark_escalated": mgr.mark_escalated,
                "mark_manual_action_needed": lambda rid: mgr.mark_manual_action_needed(
                    rid, body.details or ""
                ),
            }
            fn = action_map.get(body.action)
            if fn is None:
                raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")
            try:
                req = fn(request_id)
            except InvalidTransitionError as e:
                raise HTTPException(status_code=400, detail=str(e))
            return {"id": req.id, "status": req.status.value}
        finally:
            db.close()

    return r
