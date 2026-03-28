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
    for i in range(5):
        broker = {
            "name": f"Test Broker {i}",
            "domain": f"broker{i}.com",
            "category": "data_broker",
            "dpo_email": f"dpo@broker{i}.com",
            "removal_method": "email",
            "country": "US",
            "gdpr_applies": True,
            "verification_required": False,
            "language": "en",
            "last_verified": "2026-03-01",
        }
        (brokers_dir / f"broker{i}.yaml").write_text(yaml.dump(broker))
    return tmp_path


@pytest.fixture
def config(app_dir):
    return AppConfig(data_dir=app_dir)


@pytest.fixture
def client(config):
    vault = ProfileVault(config.vault_path)
    profile = Profile(
        full_name="Test User",
        previous_names=[],
        date_of_birth=date(1990, 1, 1),
        emails=["test@test.com"],
        phones=[],
        addresses=[],
    )
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="test@test.com", password="p")
    vault.save(profile, smtp, "password")

    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    c.post("/api/auth/unlock", json={"password": "password"})
    return c


def test_blast_dry_run(client):
    response = client.post("/api/blast/create", json={
        "request_type": "access",
        "dry_run": True,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is True
    assert data["created"] == 5
    assert data["skipped"] == 0
    assert data["total_brokers"] == 5
    assert len(data["requests"]) == 5
    assert data["requests"][0]["status"] == "would_create"


def test_blast_create(client):
    response = client.post("/api/blast/create", json={
        "request_type": "erasure",
        "dry_run": False,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == 5
    assert data["dry_run"] is False
    assert data["requests"][0]["status"] == "created"
    assert "request_id" in data["requests"][0]


def test_blast_skips_existing(client):
    # First blast
    client.post("/api/blast/create", json={"request_type": "access", "dry_run": False})

    # Second blast should skip all
    response = client.post("/api/blast/create", json={"request_type": "access", "dry_run": False})
    data = response.json()
    assert data["created"] == 0
    assert data["skipped"] == 5


def test_blast_different_types_dont_skip(client):
    # Create access requests
    client.post("/api/blast/create", json={"request_type": "access", "dry_run": False})

    # Erasure requests should NOT be skipped
    response = client.post("/api/blast/create", json={"request_type": "erasure", "dry_run": False})
    data = response.json()
    assert data["created"] == 5
    assert data["skipped"] == 0


def test_blast_requires_auth(config):
    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    response = c.post("/api/blast/create", json={"request_type": "access"})
    assert response.status_code == 401


def test_send_all_requires_smtp(config):
    """Test that sending fails gracefully when SMTP is not configured."""
    vault = ProfileVault(config.vault_path)
    profile = Profile(
        full_name="Test", previous_names=[], date_of_birth=date(1990, 1, 1),
        emails=["t@t.com"], phones=[], addresses=[],
    )
    # Save WITHOUT smtp
    vault.save(profile, None, "password")

    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    c.post("/api/auth/unlock", json={"password": "password"})

    response = c.post("/api/blast/send-all")
    assert response.status_code == 400
    assert "SMTP" in response.json()["detail"]
