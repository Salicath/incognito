"""Tests for the notification settings API endpoints."""


def test_get_notification_status_not_configured(authenticated_client):
    resp = authenticated_client.get("/api/settings/notifications")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["url"] is None


def test_test_notification_not_configured(authenticated_client):
    resp = authenticated_client.post("/api/settings/notifications/test")
    assert resp.status_code == 400
    assert "not configured" in resp.json()["detail"].lower()


def test_notification_status_configured(config, seeded_vault):
    """When INCOGNITO_NOTIFY_URL is set, status shows configured."""
    from fastapi.testclient import TestClient

    from backend.core.config import AppConfig
    from backend.main import create_app

    config_with_notify = AppConfig(
        data_dir=config.data_dir,
        notify_url="https://ntfy.sh/test-topic",
    )
    app = create_app(config_with_notify)
    client = TestClient(app)
    client.post("/api/auth/unlock", json={"password": "test_password"})

    resp = client.get("/api/settings/notifications")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["url"] == "https://ntfy.sh/test-topic"
