from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.core.request import RequestManager
from backend.db.models import Base, RequestEvent, RequestStatus, RequestType


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_find_overdue_detects_past_deadline():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("broker1", RequestType.ACCESS)
    mgr.mark_sent(req.id)

    # Set deadline to yesterday
    req.deadline_at = datetime.now(UTC) - timedelta(days=1)
    session.commit()

    overdue = mgr.find_overdue()
    assert len(overdue) == 1


def test_find_overdue_ignores_within_deadline():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("broker1", RequestType.ACCESS)
    mgr.mark_sent(req.id)

    # Deadline is in the future (default)
    overdue = mgr.find_overdue()
    assert len(overdue) == 0


def test_mark_overdue_transitions():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("broker1", RequestType.ACCESS)
    mgr.mark_sent(req.id)
    mgr.mark_overdue(req.id)

    session.refresh(req)
    assert req.status == RequestStatus.OVERDUE

    events = session.query(RequestEvent).filter_by(request_id=req.id).all()
    event_types = [e.event_type for e in events]
    assert "overdue" in event_types
