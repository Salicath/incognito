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


def test_alias_leak_guidance_survives_a_broker_match(client, config):
    """Leak rows carry the registry broker's id, so the broker matches — but
    the actionable path for a leak is the Art. 15(1)(c) ladder, not the no-op
    "create erasure request" (that request is already SENT)."""
    eid = _seed(config, "alias_leak", {
        "broker_domain": "broker0-com",
        "url": "mailto:promo@casino-spam.ru",
    })
    data = client.get("/api/scan/exposures").json()
    row = next(e for e in data["exposures"] if e["id"] == eid)
    assert row["matched_broker"] is not None      # the broker IS matched
    assert row["guidance"] is not None            # and guidance still renders
    assert "nexpected sender" in row["guidance"]["title"]


def test_delisting_kit_rejects_a_mailto_url(client, config):
    """Alias-leak rows carry mailto: URLs — an RTBF filing for an email
    address is junk legal process."""
    eid = _seed(config, "alias_leak", {
        "broker_domain": "broker0-com",
        "url": "mailto:promo@casino-spam.ru",
    })
    resp = client.get(f"/api/scan/exposures/{eid}/delisting-kit")
    assert resp.status_code == 400


def test_delisting_request_rejects_a_mailto_url(client, config):
    """The POST is what actually creates the tracked request and starts the
    Art. 12(3) clock — it must reject a non-http target even from a stale or
    direct client, not just rely on the frontend gate."""
    from backend.db.models import Request
    from backend.db.session import init_db

    eid = _seed(config, "alias_leak", {
        "broker_domain": "broker0-com",
        "url": "mailto:promo@casino-spam.ru",
    })
    resp = client.post(
        f"/api/scan/exposures/{eid}/delisting-request", json={"engine": "google"},
    )
    assert resp.status_code == 400

    db = init_db(config.db_path)()
    try:
        assert db.query(Request).count() == 0
    finally:
        db.close()


def _seed_alias_leak_with_alias_row(config):
    """An alias_leak exposure plus the BrokerAlias row it points at."""
    from datetime import UTC, datetime

    from backend.db.models import BrokerAlias
    from backend.db.session import init_db

    eid = _seed(config, "alias_leak", {
        "broker_domain": "broker0-com",
        "sender": "promo@casino-spam.ru",
        "url": "mailto:casino-spam.ru",
    })
    db = init_db(config.db_path)()
    try:
        db.add(BrokerAlias(
            broker_id="broker0-com", alias_id=7, alias_email="abc@aleeas.com",
            reverse_alias_address="reply+x@simplelogin.co",
            created_at=datetime.now(UTC),
        ))
        db.commit()
    finally:
        db.close()
    return eid


def test_disable_alias_toggles_upstream_and_marks_the_row(client, config):
    """The leak card's 'disable this alias' action: SimpleLogin toggle + local
    disabled_at, so chases stop and the broker can never reach the user."""
    from unittest.mock import AsyncMock, patch

    from backend.db.models import BrokerAlias
    from backend.db.session import init_db

    client.post("/api/settings/simplelogin", json={"api_key": "sl-test-key"})
    eid = _seed_alias_leak_with_alias_row(config)

    with patch(
        "backend.core.alias.SimpleLoginClient.disable_alias",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_disable:
        resp = client.post(f"/api/scan/exposures/{eid}/disable-alias")

    assert resp.status_code == 200
    assert resp.json()["alias_email"] == "abc@aleeas.com"
    mock_disable.assert_awaited_once()

    db = init_db(config.db_path)()
    try:
        row = db.query(BrokerAlias).filter_by(broker_id="broker0-com").one()
        assert row.disabled_at is not None
    finally:
        db.close()


def test_disable_alias_retries_when_toggle_reports_still_enabled(client, config):
    """SimpleLogin's endpoint is a /toggle, not an idempotent disable. If the
    alias was already disabled upstream, the first toggle ENABLES it (returns
    False) — the endpoint must toggle back to reach the disabled state, not
    blindly stamp disabled_at while it forwards."""
    from unittest.mock import AsyncMock, patch

    from backend.db.models import BrokerAlias
    from backend.db.session import init_db

    client.post("/api/settings/simplelogin", json={"api_key": "sl-test-key"})
    eid = _seed_alias_leak_with_alias_row(config)

    with patch(
        "backend.core.alias.SimpleLoginClient.disable_alias",
        new_callable=AsyncMock,
        side_effect=[False, True],       # enabled it, then disabled it
    ) as mock_disable:
        resp = client.post(f"/api/scan/exposures/{eid}/disable-alias")

    assert resp.status_code == 200
    assert mock_disable.await_count == 2
    db = init_db(config.db_path)()
    try:
        row = db.query(BrokerAlias).filter_by(broker_id="broker0-com").one()
        assert row.disabled_at is not None
    finally:
        db.close()


def test_disable_alias_that_cannot_reach_disabled_state_is_a_502(client, config):
    from unittest.mock import AsyncMock, patch

    from backend.db.models import BrokerAlias
    from backend.db.session import init_db

    client.post("/api/settings/simplelogin", json={"api_key": "sl-test-key"})
    eid = _seed_alias_leak_with_alias_row(config)

    with patch(
        "backend.core.alias.SimpleLoginClient.disable_alias",
        new_callable=AsyncMock,
        return_value=False,              # never reaches disabled
    ):
        resp = client.post(f"/api/scan/exposures/{eid}/disable-alias")

    assert resp.status_code == 502
    db = init_db(config.db_path)()
    try:
        assert db.query(BrokerAlias).filter_by(broker_id="broker0-com").one().disabled_at is None
    finally:
        db.close()


def test_disable_alias_actions_the_exposure(client, config):
    """A successful disable resolves the leak — the dashboard badge and the
    needs_triage filter must stop flagging it."""
    from unittest.mock import AsyncMock, patch

    client.post("/api/settings/simplelogin", json={"api_key": "sl-test-key"})
    eid = _seed_alias_leak_with_alias_row(config)

    with patch(
        "backend.core.alias.SimpleLoginClient.disable_alias",
        new_callable=AsyncMock, return_value=True,
    ):
        client.post(f"/api/scan/exposures/{eid}/disable-alias")

    row = next(
        e for e in client.get("/api/scan/exposures").json()["exposures"]
        if e["id"] == eid
    )
    assert row["disposition"] == "actioned"
    assert client.get("/api/requests/stats").json()["alias_leaks_pending"] == 0


def test_disable_alias_upstream_failure_does_not_mark_locally(client, config):
    """If the SimpleLogin toggle fails, the alias still forwards — marking it
    disabled locally would stop chases while the spam continues."""
    from unittest.mock import AsyncMock, patch

    from backend.core.alias import AliasError
    from backend.db.models import BrokerAlias
    from backend.db.session import init_db

    client.post("/api/settings/simplelogin", json={"api_key": "sl-test-key"})
    eid = _seed_alias_leak_with_alias_row(config)

    with patch(
        "backend.core.alias.SimpleLoginClient.disable_alias",
        new_callable=AsyncMock,
        side_effect=AliasError("upstream down"),
    ):
        resp = client.post(f"/api/scan/exposures/{eid}/disable-alias")

    assert resp.status_code == 502
    db = init_db(config.db_path)()
    try:
        row = db.query(BrokerAlias).filter_by(broker_id="broker0-com").one()
        assert row.disabled_at is None
    finally:
        db.close()


def test_disable_alias_rejects_non_leak_rows_and_missing_key(client, config):
    eid = _seed(config, "duckduckgo", {"broker_name": "Blog", "url": "https://x.example/a"})
    assert client.post(f"/api/scan/exposures/{eid}/disable-alias").status_code == 400

    # alias_leak row but no stored SimpleLogin key -> can't toggle upstream
    leak_eid = _seed_alias_leak_with_alias_row(config)
    resp = client.post(f"/api/scan/exposures/{leak_eid}/disable-alias")
    assert resp.status_code == 400


def test_stats_count_pending_alias_leaks(client, config):
    _seed(config, "alias_leak", {
        "broker_domain": "broker0-com", "url": "mailto:spam.ru", "sender": "a@spam.ru",
    })
    _seed(config, "duckduckgo", {"broker_name": "Blog", "url": "https://x.example/a"})
    stats = client.get("/api/requests/stats").json()
    assert stats["alias_leaks_pending"] == 1


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
