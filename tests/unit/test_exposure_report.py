"""Tests for the exposure report endpoint."""
import uuid
from datetime import UTC, datetime

from backend.db.models import Request, RequestStatus, RequestType


def test_exposure_report_empty(authenticated_client):
    resp = authenticated_client.get("/api/requests/report/exposure")
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"] == 0
    assert data["grade"] == "F"
    assert data["summary"]["total_brokers_contacted"] == 0
    assert data["brokers"] == []


def test_exposure_report_with_requests(config, seeded_vault):
    """Report calculates score based on request statuses."""
    from fastapi.testclient import TestClient

    from backend.main import create_app

    app = create_app(config)
    client = TestClient(app)
    client.post("/api/auth/unlock", json={"password": "test_password"})

    # Create requests directly in DB
    db_factory = app.state.db_session_factory
    db = db_factory()
    try:
        # 2 completed, 1 sent, 1 acknowledged
        for i, status in enumerate([
            RequestStatus.COMPLETED,
            RequestStatus.COMPLETED,
            RequestStatus.SENT,
            RequestStatus.ACKNOWLEDGED,
        ]):
            req = Request(
                id=str(uuid.uuid4()),
                broker_id=f"broker-{i}",
                request_type=RequestType.ERASURE,
                status=status,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            if status in (RequestStatus.SENT, RequestStatus.ACKNOWLEDGED,
                          RequestStatus.COMPLETED):
                req.sent_at = datetime.now(UTC)
            db.add(req)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/requests/report/exposure")
    assert resp.status_code == 200
    data = resp.json()

    assert data["summary"]["total_brokers_contacted"] == 4
    assert data["summary"]["completed"] == 2
    assert data["summary"]["in_progress"] == 2
    # Score: (2*100 + 2*40) / 4 = 70
    assert data["score"] == 70
    assert data["grade"] == "B"
    assert len(data["brokers"]) == 4


def test_exposure_report_all_completed(config, seeded_vault):
    """All completed = score 100, grade A."""
    from fastapi.testclient import TestClient

    from backend.main import create_app

    app = create_app(config)
    client = TestClient(app)
    client.post("/api/auth/unlock", json={"password": "test_password"})

    db_factory = app.state.db_session_factory
    db = db_factory()
    try:
        for i in range(3):
            req = Request(
                id=str(uuid.uuid4()),
                broker_id=f"broker-{i}",
                request_type=RequestType.ERASURE,
                status=RequestStatus.COMPLETED,
                sent_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(req)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/requests/report/exposure")
    data = resp.json()
    assert data["score"] == 100
    assert data["grade"] == "A"


def test_exposure_report_requires_auth(config, seeded_vault):
    from fastapi.testclient import TestClient

    from backend.main import create_app
    app = create_app(config)
    client = TestClient(app)
    resp = client.get("/api/requests/report/exposure")
    assert resp.status_code == 401
