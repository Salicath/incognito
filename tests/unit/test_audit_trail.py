"""Tests for audit trail export and health endpoints."""
import uuid
from datetime import UTC, datetime


def test_audit_trail_json_empty(authenticated_client):
    resp = authenticated_client.get("/api/requests/export/audit-trail")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_requests"] == 0
    assert data["trail"] == []
    assert "generated_at" in data


def test_audit_trail_json_with_data(config, seeded_vault):
    from fastapi.testclient import TestClient

    from backend.db.models import Request, RequestStatus, RequestType
    from backend.main import create_app

    app = create_app(config)
    client = TestClient(app)
    client.post("/api/auth/unlock", json={"password": "test_password"})

    db = app.state.db_session_factory()
    try:
        req = Request(
            id=str(uuid.uuid4()),
            broker_id="test-broker",
            request_type=RequestType.ERASURE,
            status=RequestStatus.SENT,
            sent_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(req)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/requests/export/audit-trail")
    data = resp.json()
    assert data["total_requests"] == 1
    assert data["trail"][0]["broker_id"] == "test-broker"
    assert data["trail"][0]["status"] == "sent"


def test_audit_trail_csv(config, seeded_vault):
    from fastapi.testclient import TestClient

    from backend.db.models import Request, RequestStatus, RequestType
    from backend.main import create_app

    app = create_app(config)
    client = TestClient(app)
    client.post("/api/auth/unlock", json={"password": "test_password"})

    db = app.state.db_session_factory()
    try:
        db.add(Request(
            id=str(uuid.uuid4()),
            broker_id="csv-broker",
            request_type=RequestType.ERASURE,
            status=RequestStatus.COMPLETED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ))
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/requests/export/audit-trail?output_format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "csv-broker" in resp.text
    assert "request_id" in resp.text  # header row


def test_audit_trail_requires_auth(config, seeded_vault):
    from fastapi.testclient import TestClient

    from backend.main import create_app

    client = TestClient(create_app(config))
    resp = client.get("/api/requests/export/audit-trail")
    assert resp.status_code == 401


def test_health_endpoint(config, seeded_vault):
    from fastapi.testclient import TestClient

    from backend.main import create_app

    client = TestClient(create_app(config))
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] == "ok"
    assert data["vault"] == "ok"
    assert data["brokers"] > 0
    assert data["version"] == "0.3.0"


def test_health_not_initialized(config):
    from fastapi.testclient import TestClient

    from backend.main import create_app

    client = TestClient(create_app(config))
    resp = client.get("/api/health")
    data = resp.json()
    assert data["vault"] == "not_initialized"
