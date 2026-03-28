import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.models import Base, Request, RequestEvent, RequestStatus, RequestType, ScanResult


def make_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_create_request():
    engine = make_engine()
    with Session(engine) as session:
        req = Request(
            id=str(uuid.uuid4()),
            broker_id="acxiom",
            request_type=RequestType.ERASURE,
            status=RequestStatus.CREATED,
        )
        session.add(req)
        session.commit()
        session.refresh(req)

        assert req.status == RequestStatus.CREATED
        assert req.request_type == RequestType.ERASURE
        assert req.broker_id == "acxiom"
        assert req.created_at is not None
        assert req.sent_at is None
        assert req.deadline_at is None


def test_create_request_event():
    engine = make_engine()
    with Session(engine) as session:
        req_id = str(uuid.uuid4())
        req = Request(
            id=req_id,
            broker_id="acxiom",
            request_type=RequestType.ACCESS,
            status=RequestStatus.CREATED,
        )
        session.add(req)
        session.flush()

        event = RequestEvent(
            request_id=req_id,
            event_type="status_change",
            details="created -> sent",
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        assert event.request_id == req_id
        assert event.event_type == "status_change"
        assert event.created_at is not None


def test_create_scan_result():
    engine = make_engine()
    with Session(engine) as session:
        result = ScanResult(
            source="peoplesearch.example.com",
            broker_id="example-broker",
            found_data='{"name": "Test User", "email": "test@example.com"}',
        )
        session.add(result)
        session.commit()
        session.refresh(result)

        assert result.actioned is False
        assert result.broker_id == "example-broker"
        assert result.scanned_at is not None


def test_request_status_values():
    assert RequestStatus.CREATED == "created"
    assert RequestStatus.SENT == "sent"
    assert RequestStatus.ACKNOWLEDGED == "acknowledged"
    assert RequestStatus.COMPLETED == "completed"
    assert RequestStatus.REFUSED == "refused"
    assert RequestStatus.OVERDUE == "overdue"
    assert RequestStatus.ESCALATED == "escalated"
    assert RequestStatus.MANUAL_ACTION_NEEDED == "manual_action_needed"


def test_request_type_values():
    assert RequestType.ACCESS == "access"
    assert RequestType.ERASURE == "erasure"
    assert RequestType.FOLLOW_UP == "follow_up"
    assert RequestType.ESCALATION_WARNING == "escalation_warning"
    assert RequestType.DPA_COMPLAINT == "dpa_complaint"
