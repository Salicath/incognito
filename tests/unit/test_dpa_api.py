"""Tests for DPA list and complaint generation endpoints."""
import uuid
from datetime import UTC, datetime


def test_dpa_list(authenticated_client):
    resp = authenticated_client.get("/api/blast/dpa-list")
    assert resp.status_code == 200
    data = resp.json()
    assert "DE" in data
    assert "FR" in data
    assert data["DE"]["short_name"] == "BfDI"


def test_generate_complaint_not_found(authenticated_client):
    resp = authenticated_client.post("/api/blast/generate-complaint/nonexistent")
    assert resp.status_code == 404


def test_generate_complaint(config, seeded_vault):
    from fastapi.testclient import TestClient

    from backend.db.models import Request, RequestStatus, RequestType
    from backend.main import create_app

    app = create_app(config)
    client = TestClient(app)
    client.post("/api/auth/unlock", json={"password": "test_password"})

    # Create an escalated request for a known broker
    db = app.state.db_session_factory()
    try:
        req_id = str(uuid.uuid4())
        req = Request(
            id=req_id,
            broker_id="acxiom-de",
            request_type=RequestType.ERASURE,
            status=RequestStatus.ESCALATED,
            sent_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(req)
        db.commit()
    finally:
        db.close()

    resp = client.post(f"/api/blast/generate-complaint/{req_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "complaint_text" in data
    assert "dpa" in data
    assert data["dpa"]["short_name"] == "BfDI"
    assert "Acxiom" in data["broker"]["name"]
