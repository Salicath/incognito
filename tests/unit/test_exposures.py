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


def test_unsubscribe_one_click_actions_exposure(client, config, monkeypatch):
    from unittest.mock import AsyncMock

    import backend.core.unsubscribe as unsub

    monkeypatch.setattr(
        unsub, "one_click_unsubscribe", AsyncMock(return_value=(True, "Unsubscribed (HTTP 200)"))
    )
    eid = _seed(config, "newsletter:acme.example", {
        "broker_name": "Acme News", "sender_domain": "acme.example",
        "one_click": True, "unsub_https": "https://acme.example/u/1",
    })
    resp = client.post(f"/api/scan/exposures/{eid}/unsubscribe")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["disposition"] == "actioned"


def test_unsubscribe_rejects_non_newsletter(client, config):
    eid = _seed(config, "duckduckgo", {"broker_name": "Spokeo", "url": "https://spokeo.com/x"})
    resp = client.post(f"/api/scan/exposures/{eid}/unsubscribe")
    assert resp.status_code == 400


def test_delisting_kit_for_web_search_exposure(client, config):
    eid = _seed(config, "duckduckgo", {"broker_name": "Blog", "url": "https://blog.example/jane"})
    resp = client.get(f"/api/scan/exposures/{eid}/delisting-kit?reason=outdated")
    assert resp.status_code == 200
    kit = resp.json()
    assert kit["url"] == "https://blog.example/jane"
    assert {e["key"] for e in kit["engines"]} >= {"google", "bing", "brave"}
    assert "Test User" in kit["justification"]  # profile full_name


def test_delisting_kit_400_when_no_url(client, config):
    eid = _seed(config, "duckduckgo", {"broker_name": "NoUrl"})
    resp = client.get(f"/api/scan/exposures/{eid}/delisting-kit")
    assert resp.status_code == 400


def test_unsubscribe_bare_link_is_manual(client, config):
    eid = _seed(config, "newsletter:x.example", {
        "broker_name": "X", "sender_domain": "x.example",
        "one_click": False, "unsub_https": "https://x.example/u", "unsub_mailto": None,
    })
    resp = client.post(f"/api/scan/exposures/{eid}/unsubscribe")
    assert resp.status_code == 400


def test_aggregates_across_sources_with_labels(client, config):
    _seed(config, "duckduckgo", {"broker_name": "Spokeo", "url": "https://spokeo.com/x"})
    _seed(config, "userscan:test@example.com", {"service": "Spotify", "url": "spotify.com"})
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
    assert by_source["userscan"]["source_label"] == "Account"
    assert by_source["wayback"]["source_label"] == "Web archive"
    assert by_source["github"]["source_label"] == "Code leak"
    # title resolves from source-specific fields
    assert by_source["userscan"]["title"] == "Spotify"
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


def _seed_broker0(config):
    return _seed(config, "duckduckgo", {
        "broker_name": "Test Broker", "broker_domain": "broker0.com",
        "url": "https://broker0.com/x",
    })


def _seed_github(config):
    return _seed(config, "github", {
        "broker_name": "GitHub: acme/leak", "broker_domain": "github.com",
        "url": "https://github.com/x",
    })


def test_matched_broker_surfaced_for_registry_domain(client, config):
    # broker0.com is in the test registry (conftest-style fixture above)
    _seed_broker0(config)
    _seed_github(config)

    exposures = {e["title"]: e for e in client.get("/api/scan/exposures").json()["exposures"]}
    assert exposures["Test Broker"]["matched_broker"]["broker_id"] == "broker0-com"
    # github.com is not a broker in the registry
    assert exposures["GitHub: acme/leak"]["matched_broker"] is None


def test_create_request_from_exposure(client, config):
    eid = _seed_broker0(config)

    resp = client.post(f"/api/scan/exposures/{eid}/create-request")
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    assert body["broker_id"] == "broker0-com"
    assert body["disposition"] == "actioned"

    # exposure is now actioned with an explanatory note
    e = client.get("/api/scan/exposures").json()["exposures"][0]
    assert e["disposition"] == "actioned"
    assert "Erasure request created" in e["note"]

    # a real request now exists
    reqs = client.get("/api/requests").json()
    assert any(r["broker_id"] == "broker0-com" for r in reqs)


def test_create_request_is_idempotent(client, config):
    eid = _seed_broker0(config)

    first = client.post(f"/api/scan/exposures/{eid}/create-request").json()
    second = client.post(f"/api/scan/exposures/{eid}/create-request").json()
    assert first["created"] is True
    assert second["created"] is False
    assert first["request_id"] == second["request_id"]


def test_create_request_no_broker_match_400(client, config):
    eid = _seed_github(config)
    resp = client.post(f"/api/scan/exposures/{eid}/create-request")
    assert resp.status_code == 400


def test_create_request_makes_new_request_when_prior_completed(client, config):
    # Reappeared data: the prior erasure COMPLETED, rescan found the broker
    # again. A new erasure must fire, not a link to the dead request.
    from backend.core.request import RequestManager
    from backend.db.session import init_db

    eid = _seed_broker0(config)
    first = client.post(f"/api/scan/exposures/{eid}/create-request").json()

    db = init_db(config.db_path)()
    try:
        mgr = RequestManager(db)
        rid = first["request_id"]
        mgr.mark_sent(rid)
        mgr.mark_acknowledged(rid, "ok")
        mgr.mark_completed(rid)
    finally:
        db.close()

    second_eid = _seed_broker0(config)
    second = client.post(f"/api/scan/exposures/{second_eid}/create-request").json()
    assert second["created"] is True
    assert second["request_id"] != first["request_id"]


def test_guidance_present_for_unmatched_absent_for_matched(client, config):
    _seed_broker0(config)   # maps to a registry broker
    _seed_github(config)    # no registry broker

    exposures = {e["title"]: e for e in client.get("/api/scan/exposures").json()["exposures"]}
    # matched broker -> create-request path, no manual guidance
    assert exposures["Test Broker"]["guidance"] is None
    # unmatched -> source-specific guidance with steps + links
    g = exposures["GitHub: acme/leak"]["guidance"]
    assert g is not None
    assert g["steps"] and g["links"]
