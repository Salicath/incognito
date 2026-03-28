from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.core.config import AppConfig


@pytest.fixture
def config(tmp_path):
    return AppConfig(data_dir=tmp_path)


@pytest.fixture
def client(config):
    from backend.main import create_app

    app = create_app(config)
    return TestClient(app)


def test_setup_creates_profile(client, config):
    response = client.post(
        "/api/setup",
        json={
            "password": "master_password",
            "profile": {
                "full_name": "Malte Example",
                "previous_names": [],
                "date_of_birth": "1990-01-15",
                "emails": ["malte@example.com"],
                "phones": [],
                "addresses": [],
            },
            "smtp": {
                "host": "smtp.gmail.com",
                "port": 587,
                "username": "malte@example.com",
                "password": "app_password",
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "initialized"
    assert config.vault_path.exists()


def test_setup_rejects_if_already_initialized(client, config):
    setup_data = {
        "password": "master_password",
        "profile": {
            "full_name": "Test",
            "previous_names": [],
            "date_of_birth": "1990-01-01",
            "emails": ["t@t.com"],
            "phones": [],
            "addresses": [],
        },
        "smtp": {
            "host": "smtp.test.com",
            "port": 587,
            "username": "t@t.com",
            "password": "p",
        },
    }
    client.post("/api/setup", json=setup_data)
    response = client.post("/api/setup", json=setup_data)
    assert response.status_code == 400


def test_setup_validates_profile(client):
    response = client.post(
        "/api/setup",
        json={
            "password": "master_password",
            "profile": {
                "full_name": "",
                "previous_names": [],
                "date_of_birth": "invalid-date",
                "emails": [],
                "phones": [],
                "addresses": [],
            },
            "smtp": {
                "host": "smtp.test.com",
                "port": 587,
                "username": "t@t.com",
                "password": "p",
            },
        },
    )
    assert response.status_code == 422
