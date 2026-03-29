"""Tests for the scan API endpoints (POST /api/scan/start, GET /api/scan/status, etc.)."""

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.core.config import AppConfig
from backend.core.profile import Profile, ProfileVault, SmtpConfig


@pytest.fixture
def app_dir(tmp_path):
    brokers_dir = tmp_path / "brokers"
    brokers_dir.mkdir()
    for i in range(3):
        broker = {
            "name": f"Test Broker {i}",
            "domain": f"broker{i}.com",
            "category": "data_broker",
            "dpo_email": f"dpo@broker{i}.com",
            "removal_method": "email",
            "country": "DE",
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
        emails=["test@example.com"],
        phones=[],
        addresses=[],
    )
    smtp = SmtpConfig(
        host="smtp.test.com", port=587, username="test@test.com", password="p"
    )
    vault.save(profile, smtp, "password")

    from backend.main import create_app

    app = create_app(config)
    c = TestClient(app)
    c.post("/api/auth/unlock", json={"password": "password"})
    return c


@pytest.fixture
def unauthenticated_client(config):
    """A TestClient that has NOT logged in."""
    vault = ProfileVault(config.vault_path)
    profile = Profile(
        full_name="Test User",
        previous_names=[],
        date_of_birth=date(1990, 1, 1),
        emails=["test@example.com"],
        phones=[],
        addresses=[],
    )
    smtp = SmtpConfig(
        host="smtp.test.com", port=587, username="test@test.com", password="p"
    )
    vault.save(profile, smtp, "password")

    from backend.main import create_app

    app = create_app(config)
    return TestClient(app)


# --- Auth tests ---


def test_scan_start_requires_auth(unauthenticated_client):
    """POST /api/scan/start without auth returns 401."""
    resp = unauthenticated_client.post("/api/scan/start")
    assert resp.status_code == 401


def test_account_scan_requires_auth(unauthenticated_client):
    """POST /api/scan/accounts/start without auth returns 401."""
    resp = unauthenticated_client.post("/api/scan/accounts/start")
    assert resp.status_code == 401


# --- Status / results when idle ---


def test_scan_status_returns_not_running(client):
    """GET /api/scan/status returns running=False when no scan active."""
    resp = client.get("/api/scan/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["running"] is False
    assert data["progress"] == 0
    assert data["total"] == 0
    assert data["error"] is None


def test_scan_results_empty_initially(client):
    """GET /api/scan/results returns has_results=False before any scan."""
    resp = client.get("/api/scan/results")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_results"] is False
    assert data["hits"] == []
    assert data["checked"] == 0


# --- Starting a scan ---


def test_scan_start_returns_total(client):
    """POST /api/scan/start returns status and total count.

    The total should be len(brokers) + len(profile.emails).
    We mock scan_profile so the background task doesn't do real HTTP.
    """
    with patch(
        "backend.api.scan.scan_profile",
        new_callable=AsyncMock,
    ):
        resp = client.post("/api/scan/start")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    # 3 brokers + 1 email = 4
    assert data["total"] == 4


def test_scan_conflict_when_running(client):
    """Starting a scan while one is already running returns 409."""
    # Start a first scan (mocked so it stays "running" via the state dict)
    with patch(
        "backend.api.scan.scan_profile",
        new_callable=AsyncMock,
    ) as mock_scan:
        # Make the mock never complete so state stays running
        async def slow_scan(*args, **kwargs):
            from backend.scanner.duckduckgo import ScanReport

            return ScanReport(checked=0, hits=[])

        mock_scan.side_effect = slow_scan
        resp1 = client.post("/api/scan/start")
        assert resp1.status_code == 200

        # The background task runs synchronously in TestClient,
        # so we need to manipulate state directly to simulate a running scan.
        # Access the app's scan router state through the scan_profile mock.

    # To properly test conflict, we need to reach into the module-level state.
    # The scan router is created fresh per app, so we access it via the app.
    # Since the background task already ran, state is running=False.
    # We'll start two scans: first one runs (mocked), second one should conflict
    # while first is still "running".
    # Because TestClient runs background tasks synchronously, we must
    # manually set the state to simulate a running scan.

    # Get the scan router's _state by patching scan_profile to not finish
    with patch(
        "backend.api.scan.scan_profile",
        new_callable=AsyncMock,
    ):
        # First, start a scan so state is initialized
        client.post("/api/scan/start")

    # Now manipulate the app's internal state to simulate a running scan.
    # The scan router stores state in closure variables, which the /status
    # endpoint reads. We can verify by checking status shows not running,
    # then re-posting after forcing running=True.

    # Since closure state is inaccessible from outside, the reliable way to
    # test 409 is to start a scan where the background task sets running=True
    # but we intercept before it can set running=False.
    # In TestClient, background tasks run synchronously after the handler.
    # So we make scan_profile raise before setting running=False.

    # Actually, the cleanest approach: patch scan_profile so it never returns
    # (the _run_scan wrapper sets running=False in `finally`).
    # Since we can't prevent `finally`, we instead test by making two
    # rapid POST calls where the second sees running=True.

    # The realistic way: use the status endpoint to force state via a
    # side-effect that sets running=True before the second call.

    # Simplest: patch time.time in the scan module so started_at is recent
    # and running appears True when we check.
    # Let's test it by issuing the second request inside the scan_profile mock
    # (before it returns, state is still running=True).

    responses = []

    async def capture_second_call(*args, **kwargs):
        from backend.scanner.duckduckgo import ScanReport

        # While we're "running", try to start another scan
        resp2 = client.post("/api/scan/start")
        responses.append(resp2)
        return ScanReport(checked=0, hits=[])

    with patch(
        "backend.api.scan.scan_profile",
        new_callable=AsyncMock,
        side_effect=capture_second_call,
    ):
        client.post("/api/scan/start")

    assert len(responses) == 1
    assert responses[0].status_code == 409
    assert "already running" in responses[0].json()["detail"]


# --- Scan history ---


def test_scan_history_returns_results(client, config):
    """GET /api/scan/history returns recent scan results from DB."""
    from backend.db.models import ScanResult
    from backend.db.session import init_db

    db_factory = init_db(config.db_path)
    db = db_factory()
    try:
        result = ScanResult(
            source="duckduckgo",
            broker_id="broker0.com",
            found_data=json.dumps(
                {"broker_domain": "broker0.com", "snippet": "Test User found"}
            ),
        )
        db.add(result)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/scan/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    first = data["results"][0]
    assert first["source"] == "duckduckgo"
    assert first["broker_id"] == "broker0.com"
    assert first["actioned"] is False


# --- Breach check ---


def test_breach_check_requires_hibp_key(client, config):
    """POST /api/scan/breaches/start returns 400 when no HIBP key configured."""
    # Ensure no hibp_key.txt exists
    key_path = config.data_dir / "hibp_key.txt"
    if key_path.exists():
        key_path.unlink()

    resp = client.post("/api/scan/breaches/start")
    assert resp.status_code == 400
    assert "HIBP API key not configured" in resp.json()["detail"]


# --- Rescan ---


def test_rescan_returns_report(client):
    """GET /api/scan/rescan returns the rescan report format.

    When no scan has been run yet, it should return has_results=False.
    """
    resp = client.get("/api/scan/rescan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_results"] is False
    assert data["reappeared"] == []
    assert data["new_exposures"] == []
    assert data["total_checked"] == 0
