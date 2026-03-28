# tests/integration/test_full_flow.py
"""Integration test: full flow from setup to request creation."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.core.config import AppConfig


@pytest.fixture
def app_dir(tmp_path):
    import shutil
    brokers_src = Path(__file__).parent.parent.parent / "brokers"
    brokers_dst = tmp_path / "brokers"
    shutil.copytree(brokers_src, brokers_dst)
    return tmp_path


@pytest.fixture
def config(app_dir):
    return AppConfig(data_dir=app_dir)


@pytest.fixture
def client(config):
    from backend.main import create_app
    app = create_app(config)
    return TestClient(app)


def test_full_setup_to_request_flow(client):
    # 1. Check not initialized
    resp = client.get("/api/auth/status")
    assert resp.json()["initialized"] is False

    # 2. Run setup
    resp = client.post("/api/setup", json={
        "password": "test_password_123",
        "profile": {
            "full_name": "Integration Test User",
            "previous_names": [],
            "date_of_birth": "1990-06-15",
            "emails": ["integration@test.com"],
            "phones": ["+49 170 0000000"],
            "addresses": [{
                "street": "Teststraße 1",
                "city": "Berlin",
                "postal_code": "10115",
                "country": "DE",
            }],
        },
        "smtp": {
            "host": "smtp.test.com",
            "port": 587,
            "username": "integration@test.com",
            "password": "smtp_password",
        },
    })
    assert resp.status_code == 200

    # 3. Check initialized
    resp = client.get("/api/auth/status")
    assert resp.json()["initialized"] is True

    # 4. Get profile (should be authenticated from setup)
    resp = client.get("/api/profile")
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Integration Test User"

    # 5. List brokers
    resp = client.get("/api/brokers")
    assert resp.status_code == 200
    brokers = resp.json()
    assert len(brokers) >= 6

    # 6. Create an erasure request
    broker_id = brokers[0]["id"]
    resp = client.post("/api/requests", json={
        "broker_id": broker_id,
        "request_type": "erasure",
    })
    assert resp.status_code == 200
    req_id = resp.json()["id"]
    assert resp.json()["status"] == "created"

    # 7. Check stats
    resp = client.get("/api/requests/stats")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["created"] == 1

    # 8. Transition to sent
    resp = client.post(f"/api/requests/{req_id}/transition", json={
        "action": "mark_sent",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"

    # 9. Check events
    resp = client.get(f"/api/requests/{req_id}/events")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 2
    assert events[0]["event_type"] == "created"
    assert events[1]["event_type"] == "sent"

    # 10. Lock and verify auth required
    client.post("/api/auth/lock")
    resp = client.get("/api/profile")
    assert resp.status_code == 401

    # 11. Re-unlock
    resp = client.post("/api/auth/unlock", json={"password": "test_password_123"})
    assert resp.status_code == 200

    resp = client.get("/api/profile")
    assert resp.status_code == 200
