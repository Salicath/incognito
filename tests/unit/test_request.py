from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.core.request import InvalidTransitionError, RequestManager
from backend.db.models import Base, RequestEvent, RequestStatus, RequestType


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_create_request():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    assert req.status == RequestStatus.CREATED
    assert req.broker_id == "acxiom"

    events = session.query(RequestEvent).filter_by(request_id=req.id).all()
    assert len(events) == 1
    assert events[0].event_type == "created"


def test_transition_created_to_sent():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)

    session.refresh(req)
    assert req.status == RequestStatus.SENT
    assert req.sent_at is not None
    assert req.deadline_at is not None
    assert (req.deadline_at - req.sent_at).days == 30


def test_transition_sent_to_acknowledged():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)
    mgr.mark_acknowledged(req.id, "We received your request")

    session.refresh(req)
    assert req.status == RequestStatus.ACKNOWLEDGED
    assert req.response_at is not None
    assert req.response_body == "We received your request"


def test_transition_acknowledged_to_completed():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)
    mgr.mark_acknowledged(req.id, "Processing")
    mgr.mark_completed(req.id)

    session.refresh(req)
    assert req.status == RequestStatus.COMPLETED


def test_transition_acknowledged_to_refused():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)
    mgr.mark_acknowledged(req.id, "Processing")
    mgr.mark_refused(req.id, "Exemption under Art. 17(3)")

    session.refresh(req)
    assert req.status == RequestStatus.REFUSED
    assert "Art. 17(3)" in req.response_body


def test_mark_overdue():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)
    mgr.mark_overdue(req.id)

    session.refresh(req)
    assert req.status == RequestStatus.OVERDUE


def test_mark_escalated():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)
    mgr.mark_overdue(req.id)
    mgr.mark_escalated(req.id)

    session.refresh(req)
    assert req.status == RequestStatus.ESCALATED


def test_mark_manual_action_needed():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_manual_action_needed(req.id, "CAPTCHA detected on opt-out form")

    session.refresh(req)
    assert req.status == RequestStatus.MANUAL_ACTION_NEEDED


def test_invalid_transition_raises():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)

    with pytest.raises(InvalidTransitionError):
        mgr.mark_completed(req.id)  # can't go from CREATED to COMPLETED


def test_find_overdue_requests():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)

    # Manually set deadline in the past
    req.deadline_at = datetime.now(UTC) - timedelta(days=1)
    session.commit()

    overdue = mgr.find_overdue()
    assert len(overdue) == 1
    assert overdue[0].id == req.id


def test_event_trail():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)
    mgr.mark_acknowledged(req.id, "Got it")
    mgr.mark_completed(req.id)

    events = session.query(RequestEvent).filter_by(request_id=req.id).order_by(RequestEvent.id).all()
    types = [e.event_type for e in events]
    assert types == ["created", "sent", "acknowledged", "completed"]
