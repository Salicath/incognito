from datetime import date
from pathlib import Path

import yaml
import pytest
from fastapi.testclient import TestClient

from backend.core.config import AppConfig
from backend.core.profile import Profile, ProfileVault, SmtpConfig


@pytest.fixture
def app_dir(tmp_path):
    brokers_dir = tmp_path / "brokers"
    brokers_dir.mkdir()
    broker = {
        "name": "Test Broker",
        "domain": "testbroker.com",
        "category": "data_broker",
        "dpo_email": "dpo@testbroker.com",
        "removal_method": "email",
        "country": "DE",
        "gdpr_applies": True,
        "verification_required": False,
        "language": "en",
        "last_verified": "2026-03-01",
    }
    (brokers_dir / "test-broker.yaml").write_text(yaml.dump(broker))
    return tmp_path


@pytest.fixture
def config(app_dir):
    return AppConfig(data_dir=app_dir)


@pytest.fixture
def client(config):
    vault = ProfileVault(config.vault_path)
    profile = Profile(
        full_name="Test", previous_names=[], date_of_birth=date(1990, 1, 1),
        emails=["t@t.com"], phones=[], addresses=[],
    )
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="t@t.com", password="p")
    vault.save(profile, smtp, "password")

    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    c.post("/api/auth/unlock", json={"password": "password"})
    return c


def test_create_request(client):
    response = client.post(
        "/api/requests",
        json={"broker_id": "testbroker-com", "request_type": "erasure"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "created"
    assert data["broker_id"] == "testbroker-com"


def test_list_requests(client):
    client.post("/api/requests", json={"broker_id": "testbroker-com", "request_type": "access"})
    client.post("/api/requests", json={"broker_id": "testbroker-com", "request_type": "erasure"})

    response = client.get("/api/requests")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_get_request_detail(client):
    create_resp = client.post(
        "/api/requests",
        json={"broker_id": "testbroker-com", "request_type": "erasure"},
    )
    req_id = create_resp.json()["id"]

    response = client.get(f"/api/requests/{req_id}")
    assert response.status_code == 200
    assert response.json()["id"] == req_id


def test_get_request_events(client):
    create_resp = client.post(
        "/api/requests",
        json={"broker_id": "testbroker-com", "request_type": "erasure"},
    )
    req_id = create_resp.json()["id"]

    response = client.get(f"/api/requests/{req_id}/events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) >= 1
    assert events[0]["event_type"] == "created"


def test_update_request_status(client):
    create_resp = client.post(
        "/api/requests",
        json={"broker_id": "testbroker-com", "request_type": "erasure"},
    )
    req_id = create_resp.json()["id"]

    response = client.post(
        f"/api/requests/{req_id}/transition",
        json={"action": "mark_sent"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "sent"


def test_dashboard_stats(client):
    client.post("/api/requests", json={"broker_id": "testbroker-com", "request_type": "erasure"})

    response = client.get("/api/requests/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["total"] == 1
    assert stats["created"] == 1


def test_requests_requires_auth(config):
    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    response = c.get("/api/requests")
    assert response.status_code == 401
