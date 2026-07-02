"""Tests for the exposure triage inbox API (aggregates scan hits, sets disposition)."""

import json
from datetime import date

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.core.config import AppConfig
from backend.core.profile import Profile, ProfileVault, SmtpConfig


@pytest.fixture
def config(tmp_path):
    brokers_dir = tmp_path / "brokers"
    brokers_dir.mkdir()
    broker = {
        "name": "Test Broker",
        "domain": "broker0.com",
        "category": "data_broker",
        "dpo_email": "dpo@broker0.com",
        "removal_method": "email",
        "country": "DE",
        "gdpr_applies": True,
        "verification_required": False,
        "language": "en",
        "last_verified": "2026-03-01",
    }
    (brokers_dir / "broker0.yaml").write_text(yaml.dump(broker))
    return AppConfig(data_dir=tmp_path)


@pytest.fixture
def client(config):
    vault = ProfileVault(config.vault_path)
    profile = Profile(
        full_name="Test User",
        emails=["test@example.com"],
        phones=[],
        addresses=[],
        date_of_birth=date(1990, 1, 1),
    )
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="t@t.com", password="p")
    vault.save(profile, smtp, "password")

    from backend.main import create_app

    app = create_app(config)
    c = TestClient(app)
    c.post("/api/auth/unlock", json={"password": "password"})
    return c


def _seed(config, source, data):
    from backend.db.models import ScanResult
    from backend.db.session import init_db

    factory = init_db(config.db_path)
    db = factory()
    try:
        row = ScanResult(source=source, broker_id=data.get("broker_domain", ""),
                         found_data=json.dumps(data))
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def test_requires_auth(config):
    from backend.main import create_app

    ProfileVault(config.vault_path).save(
        Profile(full_name="T", emails=["t@t.com"]),
        SmtpConfig(host="h", port=587, username="u", password="p"),
        "password",
    )
    c = TestClient(create_app(config))
    assert c.get("/api/scan/exposures").status_code == 401
    assert c.post("/api/scan/exposures/1/disposition", json={}).status_code == 401


def test_empty_inbox(client):
    data = client.get("/api/scan/exposures").json()
    assert data["exposures"] == []
    assert data["summary"]["total"] == 0
    assert data["summary"]["needs_triage"] == 0


def test_aggregates_across_sources_with_labels(client, config):
    _seed(config, "duckduckgo", {"broker_name": "Spokeo", "url": "https://spokeo.com/x"})
    _seed(config, "holehe:test@example.com", {"service": "Spotify", "url": "spotify.com"})
    _seed(config, "wayback", {
        "broker_name": "Wayback: GitHub", "url": "https://web.archive.org/x",
        "username": "me", "snapshots": 3,
    })
    _seed(config, "github", {
        "broker_name": "GitHub: acme/leak", "url": "https://github.com/acme/leak",
        "identifier": "test@example.com", "path": ".env",
    })

    data = client.get("/api/scan/exposures").json()
    assert data["summary"]["total"] == 4
    assert data["summary"]["needs_triage"] == 4

    by_source = {e["source"]: e for e in data["exposures"]}
    assert by_source["duckduckgo"]["source_label"] == "Web search"
    assert by_source["holehe"]["source_label"] == "Account"
    assert by_source["wayback"]["source_label"] == "Web archive"
    assert by_source["github"]["source_label"] == "Code leak"
    # title resolves from source-specific fields
    assert by_source["holehe"]["title"] == "Spotify"
    assert all(e["disposition"] is None for e in data["exposures"])


def test_set_and_reset_disposition(client, config):
    eid = _seed(config, "github", {"broker_name": "GitHub: acme/leak", "url": "https://github.com/x"})

    resp = client.post(
        f"/api/scan/exposures/{eid}/disposition",
        json={"disposition": "actioned", "note": "opened issue #4"},
    )
    assert resp.status_code == 200
    assert resp.json()["disposition"] == "actioned"

    data = client.get("/api/scan/exposures").json()
    assert data["summary"]["actioned"] == 1
    assert data["summary"]["needs_triage"] == 0
    e = data["exposures"][0]
    assert e["disposition"] == "actioned"
    assert e["note"] == "opened issue #4"

    # reset back to triage
    resp = client.post(f"/api/scan/exposures/{eid}/disposition", json={"disposition": None})
    assert resp.status_code == 200
    data = client.get("/api/scan/exposures").json()
    assert data["summary"]["needs_triage"] == 1
    assert data["summary"]["actioned"] == 0


def test_legally_impossible_counts(client, config):
    eid = _seed(config, "duckduckgo", {"broker_name": "Statstidende", "url": "https://x"})
    client.post(
        f"/api/scan/exposures/{eid}/disposition",
        json={"disposition": "legally_impossible", "note": "Arkivloven 75y"},
    )
    summary = client.get("/api/scan/exposures").json()["summary"]
    assert summary["legally_impossible"] == 1


def test_invalid_disposition_rejected(client, config):
    eid = _seed(config, "github", {"broker_name": "x", "url": "y"})
    resp = client.post(
        f"/api/scan/exposures/{eid}/disposition", json={"disposition": "banana"}
    )
    assert resp.status_code == 400


def test_unknown_exposure_404(client):
    resp = client.post("/api/scan/exposures/99999/disposition", json={"disposition": "actioned"})
    assert resp.status_code == 404


def test_note_too_long_rejected(client, config):
    eid = _seed(config, "github", {"broker_name": "x", "url": "y"})
    resp = client.post(
        f"/api/scan/exposures/{eid}/disposition",
        json={"disposition": "actioned", "note": "z" * 2001},
    )
    assert resp.status_code == 400
