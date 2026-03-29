import pytest
from fastapi.testclient import TestClient
from backend.main import create_app


@pytest.fixture
def client(config, seeded_vault):
    app = create_app(config)
    client = TestClient(app)
    client.post("/api/auth/unlock", json={"password": "test_password"})
    return client


def test_get_imap_not_configured(client):
    res = client.get("/api/settings/imap")
    assert res.status_code == 200
    assert res.json()["configured"] is False


def test_save_and_get_imap(client):
    res = client.post("/api/settings/imap", json={
        "imap": {"host": "imap.proton.me", "port": 993, "username": "user@proton.me", "password": "bridge-pw"}
    })
    assert res.status_code == 200
    res = client.get("/api/settings/imap")
    data = res.json()
    assert data["configured"] is True
    assert data["host"] == "imap.proton.me"
    assert "password" not in data


def test_delete_imap(client):
    client.post("/api/settings/imap", json={
        "imap": {"host": "imap.proton.me", "port": 993, "username": "user@proton.me", "password": "bridge-pw"}
    })
    res = client.delete("/api/settings/imap")
    assert res.status_code == 200
    res = client.get("/api/settings/imap")
    assert res.json()["configured"] is False
