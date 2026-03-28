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
        "language": "de",
        "last_verified": "2026-03-01",
        "notes": "Test",
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


def test_list_brokers(client):
    response = client.get("/api/brokers")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test Broker"
    assert data[0]["id"] == "testbroker-com"


def test_get_broker_by_id(client):
    response = client.get("/api/brokers/testbroker-com")
    assert response.status_code == 200
    assert response.json()["name"] == "Test Broker"


def test_get_broker_not_found(client):
    response = client.get("/api/brokers/nonexistent")
    assert response.status_code == 404


def test_brokers_requires_auth(config):
    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    response = c.get("/api/brokers")
    assert response.status_code == 401
