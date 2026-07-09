from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.core.config import AppConfig
from backend.core.profile import Profile, ProfileVault, SmtpConfig


@pytest.fixture
def app_dir(tmp_path):
    return tmp_path


@pytest.fixture
def config(app_dir):
    return AppConfig(data_dir=app_dir)


@pytest.fixture
def seeded_vault(config):
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
    vault.save(profile, smtp, "master_password")
    return vault


@pytest.fixture
def client(config, seeded_vault):
    from backend.main import create_app

    app = create_app(config)
    return TestClient(app)


def test_unlock_success(client):
    response = client.post("/api/auth/unlock", json={"password": "master_password"})
    assert response.status_code == 200
    assert "session" in response.cookies


def test_unlock_wrong_password(client):
    response = client.post("/api/auth/unlock", json={"password": "wrong"})
    assert response.status_code == 401


def test_protected_endpoint_without_auth(client):
    response = client.get("/api/profile")
    assert response.status_code == 401


def test_protected_endpoint_with_auth(client):
    client.post("/api/auth/unlock", json={"password": "master_password"})
    response = client.get("/api/profile")
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Test User"


def test_lock(client):
    client.post("/api/auth/unlock", json={"password": "master_password"})
    response = client.post("/api/auth/lock")
    assert response.status_code == 200

    response = client.get("/api/profile")
    assert response.status_code == 401


def test_setup_status_not_initialized(config):
    from backend.main import create_app

    app = create_app(config)
    client = TestClient(app)
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.json()["initialized"] is False


def test_setup_status_initialized(client):
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.json()["initialized"] is True


def test_rate_limiting_after_failed_attempts(client):
    # 5 failures should trigger a lockout
    for _ in range(5):
        resp = client.post("/api/auth/unlock", json={"password": "wrong"})
        assert resp.status_code == 401

    # 6th attempt should be rate limited
    resp = client.post("/api/auth/unlock", json={"password": "wrong"})
    assert resp.status_code == 429
    assert "Too many failed attempts" in resp.json()["detail"]

    # Even correct password should be blocked during lockout
    resp = client.post("/api/auth/unlock", json={"password": "master_password"})
    assert resp.status_code == 429


# --- proxy-aware rate-limit keying ---

def _req(peer: str, xff: str | None = None):
    from unittest.mock import Mock
    r = Mock()
    r.client = Mock(host=peer)
    r.headers = {"x-forwarded-for": xff} if xff else {}
    return r


def test_client_ip_direct_bind_uses_peer():
    from backend.api.auth import client_ip_for
    # no trusted proxy configured -> XFF is attacker-controlled, ignore it
    assert client_ip_for(_req("10.0.0.9", xff="1.2.3.4"), trusted_proxy_header="") == "10.0.0.9"


def test_client_ip_behind_proxy_uses_rightmost_xff():
    from backend.api.auth import client_ip_for
    # our trusted proxy appends the peer it saw; earlier hops are spoofable
    req = _req("172.18.0.2", xff="1.2.3.4, 203.0.113.7")
    assert client_ip_for(req, trusted_proxy_header="Remote-User") == "203.0.113.7"


def test_client_ip_spoofed_xff_cannot_pin_lockout_on_victim():
    # The attacker sets XFF to the victim's IP to burn the victim's rate-limit
    # budget. A real proxy APPENDS the peer it saw, so the attacker's own IP is
    # rightmost and the lockout lands on the attacker, not the victim.
    from backend.api.auth import client_ip_for
    req = _req("172.18.0.2", xff="victim-ip, 198.51.100.42")
    assert client_ip_for(req, trusted_proxy_header="Remote-User") == "198.51.100.42"


def test_client_ip_no_xff_falls_back_to_peer():
    from backend.api.auth import client_ip_for
    assert client_ip_for(_req("172.18.0.2"), trusted_proxy_header="Remote-User") == "172.18.0.2"


def test_proxy_lockout_is_per_client_not_per_proxy(tmp_path, sample_profile, sample_smtp):
    """Behind a reverse proxy, one attacker's failures must not lock out everyone."""
    from fastapi.testclient import TestClient

    from backend.core.config import AppConfig
    from backend.core.profile import ProfileVault
    from backend.main import create_app

    cfg = AppConfig(data_dir=tmp_path, trusted_proxy_header="Remote-User")
    ProfileVault(cfg.vault_path).save(sample_profile, sample_smtp, "correct-pw")
    client = TestClient(create_app(cfg))

    attacker = {"X-Forwarded-For": "10.0.0.1, 198.51.100.42"}
    victim = {"X-Forwarded-For": "10.0.0.1, 203.0.113.7"}

    # burn the attacker's budget (5 failures -> locked out)
    for _ in range(5):
        client.post("/api/auth/unlock", json={"password": "wrong"}, headers=attacker)
    assert client.post(
        "/api/auth/unlock", json={"password": "wrong"}, headers=attacker
    ).status_code == 429

    # the victim, arriving through the same proxy, is unaffected
    resp = client.post("/api/auth/unlock", json={"password": "correct-pw"}, headers=victim)
    assert resp.status_code == 200
