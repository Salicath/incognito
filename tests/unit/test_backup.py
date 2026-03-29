
import pytest
from fastapi.testclient import TestClient

from backend.core.config import AppConfig
from backend.core.profile import Profile, ProfileVault, SmtpConfig


@pytest.fixture
def config(tmp_path):
    return AppConfig(data_dir=tmp_path)


@pytest.fixture
def client(config):
    vault = ProfileVault(config.vault_path)
    profile = Profile(full_name="Backup Test", emails=["backup@test.com"])
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="test@test.com", password="p")
    vault.save(profile, smtp, "password")

    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    c.post("/api/auth/unlock", json={"password": "password"})
    return c


def test_export_backup(client):
    resp = client.post(
        "/api/settings/backup/export",
        json={"password": "password"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "vault" in data
    assert "database" in data


def test_export_backup_wrong_password(client):
    resp = client.post(
        "/api/settings/backup/export",
        json={"password": "wrong"},
    )
    assert resp.status_code == 401


def test_export_backup_no_password(client):
    resp = client.post("/api/settings/backup/export", json={})
    assert resp.status_code == 422  # validation error — password required


def test_import_backup(client, config):
    # Export first
    resp = client.post(
        "/api/settings/backup/export",
        json={"password": "password"},
    )
    backup = resp.json()

    # Import with password
    backup["password"] = "password"
    resp = client.post("/api/settings/backup/import", json=backup)
    assert resp.status_code == 200
    assert resp.json()["status"] == "imported"


def test_import_backup_wrong_password(client, config):
    resp = client.post(
        "/api/settings/backup/export",
        json={"password": "password"},
    )
    backup = resp.json()

    backup["password"] = "wrong"
    resp = client.post("/api/settings/backup/import", json=backup)
    assert resp.status_code == 401
