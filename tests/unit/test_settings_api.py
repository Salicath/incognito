
import pytest
from fastapi.testclient import TestClient

from backend.core.config import AppConfig
from backend.core.profile import Profile, ProfileVault, SmtpConfig


@pytest.fixture
def config(tmp_path):
    brokers_dir = tmp_path / "brokers"
    brokers_dir.mkdir()
    return AppConfig(data_dir=tmp_path)


@pytest.fixture
def client_with_smtp(config):
    vault = ProfileVault(config.vault_path)
    profile = Profile(full_name="Test", emails=["test@test.com"])
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="test@test.com", password="p")
    vault.save(profile, smtp, "password")

    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    c.post("/api/auth/unlock", json={"password": "password"})
    return c


@pytest.fixture
def client_no_smtp(config):
    vault = ProfileVault(config.vault_path)
    profile = Profile(full_name="Test", emails=["test@test.com"])
    vault.save(profile, None, "password")

    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    c.post("/api/auth/unlock", json={"password": "password"})
    return c


def test_get_info(client_with_smtp):
    resp = client_with_smtp.get("/api/settings/info")
    assert resp.status_code == 200
    assert "broker_count" in resp.json()
    assert "version" in resp.json()


def test_get_smtp_configured(client_with_smtp):
    resp = client_with_smtp.get("/api/settings/smtp")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["host"] == "smtp.test.com"
    assert "password" not in data


def test_get_smtp_not_configured(client_no_smtp):
    resp = client_no_smtp.get("/api/settings/smtp")
    assert resp.status_code == 200
    assert resp.json()["configured"] is False


def test_update_smtp(client_no_smtp):
    resp = client_no_smtp.post("/api/settings/smtp", json={
        "smtp": {"host": "smtp.new.com", "port": 465, "username": "new@test.com", "password": "newpass"},
    })
    assert resp.status_code == 200

    # Verify it was saved
    resp = client_no_smtp.get("/api/settings/smtp")
    assert resp.json()["configured"] is True
    assert resp.json()["host"] == "smtp.new.com"


def test_update_profile(client_with_smtp):
    resp = client_with_smtp.post("/api/settings/profile", json={
        "profile": {"full_name": "Updated Name", "emails": ["updated@test.com"]},
    })
    assert resp.status_code == 200

    # Verify
    resp = client_with_smtp.get("/api/profile")
    assert resp.json()["full_name"] == "Updated Name"


def test_test_smtp_not_configured(client_no_smtp):
    resp = client_no_smtp.post("/api/settings/test-smtp")
    assert resp.status_code == 400
    assert "SMTP" in resp.json()["detail"]
