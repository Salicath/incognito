from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.core.config import AppConfig
from backend.core.profile import Address, Profile, ProfileVault, SmtpConfig


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
