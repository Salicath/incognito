
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


def test_export_no_longer_leaks_plaintext_hibp_key(client):
    resp = client.post("/api/settings/backup/export", json={"password": "password"})
    # secrets travel encrypted inside `vault`, never as a plaintext field
    assert "hibp_key" not in resp.json()


def test_secret_survives_backup_roundtrip(client, config):
    # store a token, then export
    client.post("/api/settings/github", json={"api_key": "ghp_roundtrip_token"})
    backup = client.post(
        "/api/settings/backup/export", json={"password": "password"}
    ).json()

    # wipe the token, confirm it's gone
    client.delete("/api/settings/github")
    assert client.get("/api/settings/github").json()["configured"] is False

    # importing the backup restores it (carried inside the encrypted vault)
    backup["password"] = "password"
    assert client.post("/api/settings/backup/import", json=backup).status_code == 200
    assert client.get("/api/settings/github").json()["configured"] is True


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


def test_export_captures_uncheckpointed_wal_writes(client, config):
    # WAL mode keeps recent commits in the -wal file. The export must checkpoint
    # first, or a just-created request is silently missing from the backup.
    import base64
    import json as _json

    from backend.core.request import RequestManager
    from backend.db.models import RequestType
    from backend.db.session import init_db

    db = init_db(config.db_path)()
    try:
        RequestManager(db).create("fresh-broker-com", RequestType.ERASURE)
    finally:
        db.close()  # committed to WAL, not necessarily checkpointed

    resp = client.post("/api/settings/backup/export", json={"password": "password"})
    db_bytes = base64.b64decode(_json.loads(resp.content)["database"])
    assert b"fresh-broker-com" in db_bytes


def test_import_clears_stale_wal(client, config):
    # A leftover -wal beside the replaced db would be replayed over it. Import
    # must delete it.
    resp = client.post("/api/settings/backup/export", json={"password": "password"})
    backup = resp.json()
    backup["password"] = "password"

    wal = config.db_path.with_name(config.db_path.name + "-wal")
    wal.write_bytes(b"stale-wal-frames")
    assert wal.exists()

    resp = client.post("/api/settings/backup/import", json=backup)
    assert resp.status_code == 200
    assert not wal.exists()
