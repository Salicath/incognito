from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.db.models import Request, RequestEvent, RequestStatus, RequestType


class InvalidTransitionError(Exception):
    pass


_VALID_TRANSITIONS: dict[RequestStatus, set[RequestStatus]] = {
    RequestStatus.CREATED: {RequestStatus.SENT, RequestStatus.MANUAL_ACTION_NEEDED},
    RequestStatus.SENT: {
        RequestStatus.ACKNOWLEDGED,
        RequestStatus.OVERDUE,
        RequestStatus.MANUAL_ACTION_NEEDED,
    },
    RequestStatus.ACKNOWLEDGED: {
        RequestStatus.COMPLETED,
        RequestStatus.REFUSED,
        RequestStatus.MANUAL_ACTION_NEEDED,
    },
    RequestStatus.REFUSED: {RequestStatus.ESCALATED},
    RequestStatus.OVERDUE: {RequestStatus.ESCALATED, RequestStatus.ACKNOWLEDGED},
    RequestStatus.ESCALATED: {RequestStatus.ACKNOWLEDGED, RequestStatus.COMPLETED},
    RequestStatus.MANUAL_ACTION_NEEDED: {RequestStatus.SENT, RequestStatus.COMPLETED},
}


class RequestManager:
    def __init__(self, session: Session, gdpr_deadline_days: int = 30):
        self._session = session
        self._deadline_days = gdpr_deadline_days

    def _transition(self, request_id: str, new_status: RequestStatus, details: str | None = None):
        req = self._session.get(Request, request_id)
        if req is None:
            raise ValueError(f"Request {request_id} not found")

        allowed = _VALID_TRANSITIONS.get(req.status, set())
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from {req.status.value} to {new_status.value}"
            )

        old_status = req.status
        req.status = new_status
        req.updated_at = datetime.now(UTC)

        event = RequestEvent(
            request_id=request_id,
            event_type=new_status.value,
            details=details or f"{old_status.value} -> {new_status.value}",
        )
        self._session.add(event)
        self._session.commit()

        return req

    def create(self, broker_id: str, request_type: RequestType) -> Request:
        req = Request(
            id=str(uuid.uuid4()),
            broker_id=broker_id,
            request_type=request_type,
            status=RequestStatus.CREATED,
        )
        self._session.add(req)

        event = RequestEvent(
            request_id=req.id,
            event_type="created",
            details=f"Created {request_type.value} request for {broker_id}",
        )
        self._session.add(event)
        self._session.commit()

        return req

    def mark_sent(self, request_id: str) -> Request:
        req = self._transition(request_id, RequestStatus.SENT, "Request sent")
        now = datetime.now(UTC)
        req.sent_at = now
        req.deadline_at = now + timedelta(days=self._deadline_days)
        self._session.commit()
        return req

    def mark_acknowledged(self, request_id: str, response_body: str) -> Request:
        req = self._transition(request_id, RequestStatus.ACKNOWLEDGED, response_body)
        req.response_at = datetime.now(UTC)
        req.response_body = response_body
        self._session.commit()
        return req

    def mark_completed(self, request_id: str) -> Request:
        return self._transition(request_id, RequestStatus.COMPLETED, "Deletion confirmed")

    def mark_refused(self, request_id: str, reason: str) -> Request:
        req = self._transition(request_id, RequestStatus.REFUSED, reason)
        req.response_body = reason
        self._session.commit()
        return req

    def mark_overdue(self, request_id: str) -> Request:
        return self._transition(request_id, RequestStatus.OVERDUE, "GDPR deadline passed")

    def mark_escalated(self, request_id: str) -> Request:
        return self._transition(request_id, RequestStatus.ESCALATED, "Escalated")

    def mark_manual_action_needed(self, request_id: str, reason: str) -> Request:
        return self._transition(request_id, RequestStatus.MANUAL_ACTION_NEEDED, reason)

    def find_overdue(self) -> list[Request]:
        now = datetime.now(UTC)
        return (
            self._session.query(Request)
            .filter(
                Request.status == RequestStatus.SENT,
                Request.deadline_at < now,
            )
            .all()
        )
