"""Delisting lifecycle — tracked RTBF requests per (URL, engine)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.core.broker import BrokerRegistry
from backend.core.controller import ControllerRegistry, RegistryUnion
from backend.core.delisting import DelistingRegistry


@pytest.fixture
def client(config):
    from datetime import date

    from backend.core.profile import Profile, ProfileVault, SmtpConfig

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


def _seed_url_exposure(config, url="https://example.com/malte-profile"):
    from backend.db.models import ScanResult
    from backend.db.session import init_db

    factory = init_db(config.db_path)
    db = factory()
    try:
        row = ScanResult(
            source="web_search",
            broker_id="example.com",
            found_data=json.dumps({"url": url, "snippet": "hit"}),
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_delisting_registry_targets():
    reg = DelistingRegistry()
    assert {t.id for t in reg.targets} == {
        "delisting-google", "delisting-bing", "delisting-brave",
    }
    google = reg.get("delisting-google")
    assert google.dpo_email == ""  # form-only: no email chase, Step-3 escalation
    assert google.domain == "google.com"
    brave = reg.get("delisting-brave")
    assert brave.dpo_email == "privacy@brave.com"  # chase-able by email
    assert reg.get_by_domain("bing.com").name.startswith("Bing")


def test_union_resolves_delisting_targets():
    union = RegistryUnion(
        BrokerRegistry([]), ControllerRegistry([]), delisting=DelistingRegistry(),
    )
    assert union.get("delisting-google").category == "delisting"
    names = {b.name for b in union.brokers}
    assert "Google delisting (RTBF)" in names


# ---------------------------------------------------------------------------
# Filing flow
# ---------------------------------------------------------------------------


def test_file_delisting_request_starts_clock(client, config):
    eid = _seed_url_exposure(config)
    resp = client.post(
        f"/api/scan/exposures/{eid}/delisting-request", json={"engine": "google"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "sent"
    assert data["target_url"].startswith("https://example.com/")

    # kit reflects the tracked request
    kit = client.get(f"/api/scan/exposures/{eid}/delisting-kit").json()
    assert kit["requests"]["google"]["status"] == "sent"
    assert kit["requests"]["google"]["deadline_at"] is not None
    assert "bing" not in kit["requests"]

    # requests list resolves the pseudo-target name and carries the URL
    reqs = client.get("/api/requests").json()
    delisting = [r for r in reqs if r["broker_id"] == "delisting-google"]
    assert delisting and delisting[0]["broker_name"] == "Google delisting (RTBF)"
    assert delisting[0]["target_url"] == data["target_url"]

    # detail endpoint works for the pseudo-target
    detail = client.get(f"/api/requests/{data['request_id']}").json()
    assert detail["broker"]["removal_method"] == "web_form"
    assert detail["target_url"] == data["target_url"]

    # Google alone does NOT action the exposure — Bing covers the other half
    # of the market; the inbox must keep prompting until both are filed
    exposures = client.get("/api/scan/exposures").json()["exposures"]
    row = next(e for e in exposures if e["id"] == eid)
    assert row["disposition"] != "actioned"
    assert "still to file: bing" in row["note"]

    client.post(
        f"/api/scan/exposures/{eid}/delisting-request", json={"engine": "bing"},
    )
    exposures = client.get("/api/scan/exposures").json()["exposures"]
    row = next(e for e in exposures if e["id"] == eid)
    assert row["disposition"] == "actioned"


def test_duplicate_filing_rejected_per_engine(client, config):
    eid = _seed_url_exposure(config)
    assert client.post(
        f"/api/scan/exposures/{eid}/delisting-request", json={"engine": "google"},
    ).status_code == 200
    assert client.post(
        f"/api/scan/exposures/{eid}/delisting-request", json={"engine": "google"},
    ).status_code == 409
    # a different engine for the same URL is fine
    assert client.post(
        f"/api/scan/exposures/{eid}/delisting-request", json={"engine": "bing"},
    ).status_code == 200


def test_unknown_engine_404(client, config):
    eid = _seed_url_exposure(config)
    resp = client.post(
        f"/api/scan/exposures/{eid}/delisting-request", json={"engine": "yandex"},
    )
    assert resp.status_code == 404


def test_exposure_without_url_400(client, config):
    from backend.db.models import ScanResult
    from backend.db.session import init_db

    factory = init_db(config.db_path)
    db = factory()
    try:
        row = ScanResult(source="hibp", broker_id="", found_data=json.dumps({"breach": "X"}))
        db.add(row)
        db.commit()
        eid = row.id
    finally:
        db.close()
    resp = client.post(
        f"/api/scan/exposures/{eid}/delisting-request", json={"engine": "google"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# IMAP decision-email matching
# ---------------------------------------------------------------------------


def _open(request_id, broker_id, url):
    return {"request_id": request_id, "broker_id": broker_id, "target_url": url}


def test_google_decision_matches_on_allowlisted_sender_and_body_url():
    from backend.core.imap import ImapPoller, MatchTier

    open_reqs = [_open("r1", "delisting-google", "https://example.com/malte/")]
    m = ImapPoller._match_delisting_decision(
        "removals@google.com",
        "We have decided to block the following URL: https://example.com/malte",
        open_reqs,
    )
    assert m is not None
    assert m.request_id == "r1"
    assert m.tier == MatchTier.DELISTING_DECISION


def test_google_alerts_quoting_the_url_must_not_match():
    """A Google Alert / Results-about-you mail quoting the tracked URL would
    otherwise auto-ACK the request and silently disarm the Art. 12(3) chase."""
    from backend.core.imap import ImapPoller

    open_reqs = [_open("r1", "delisting-google", "https://example.com/malte")]
    for sender in (
        "googlealerts-noreply@google.com",
        "resultsaboutyou-noreply@google.com",
        "noreply@google.com",
    ):
        m = ImapPoller._match_delisting_decision(
            sender, "New result for you: https://example.com/malte", open_reqs,
        )
        assert m is None, sender


def test_google_mail_without_url_is_ignored():
    from backend.core.imap import ImapPoller

    open_reqs = [_open("r1", "delisting-google", "https://example.com/malte")]
    m = ImapPoller._match_delisting_decision(
        "removals@google.com", "We received your request", open_reqs,
    )
    assert m is None  # decisions list URLs; no URL -> user confirms


def test_bing_mail_never_auto_matches():
    """Bing sends nothing machine-recognizable; domain-wide matching would
    file Microsoft security codes onto the legal thread and mark them SEEN."""
    from backend.core.imap import ImapPoller

    open_reqs = [_open("r2", "delisting-bing", "https://example.com/malte")]
    for sender in (
        "someone@microsoft.com",
        "account-security-noreply@accountprotection.microsoft.com",
    ):
        m = ImapPoller._match_delisting_decision(
            sender, "About your recent request https://example.com/malte", open_reqs,
        )
        assert m is None, sender


def test_sender_with_display_name_is_parsed():
    from backend.core.imap import ImapPoller, MatchTier

    open_reqs = [_open("r1", "delisting-google", "https://example.com/malte")]
    m = ImapPoller._match_delisting_decision(
        "Google Removals <removals@google.com>",
        "Decision on https://example.com/malte",
        open_reqs,
    )
    assert m is not None and m.tier == MatchTier.DELISTING_DECISION


def test_unrelated_sender_no_match():
    from backend.core.imap import ImapPoller

    open_reqs = [_open("r1", "delisting-google", "https://example.com/malte")]
    m = ImapPoller._match_delisting_decision(
        "spam@evil.com", "https://example.com/malte", open_reqs,
    )
    assert m is None


def test_reply_matching_sets_cover_all_tracks():
    """main.py and cli.py must share one construction — they drifted once."""
    from backend.core.controller import reply_matching_sets

    controllers = ControllerRegistry.load(
        __import__("pathlib").Path(__file__).parent.parent.parent
        / "brokers" / "controllers.yaml"
    )
    domains, exclude, id_domains = reply_matching_sets(
        BrokerRegistry([]), controllers, DelistingRegistry(),
    )
    assert {"brave.com", "bing.com", "google.com", "snap.com"} <= domains
    assert "delisting-google" in exclude and "meta-com" in exclude
    assert id_domains["delisting-google"] == "google.com"


# ---------------------------------------------------------------------------
# Complaint
# ---------------------------------------------------------------------------


def test_delisting_complaint_names_google_llc_and_url(client, config):
    eid = _seed_url_exposure(config)
    created = client.post(
        f"/api/scan/exposures/{eid}/delisting-request", json={"engine": "google"},
    ).json()
    rid = created["request_id"]
    client.post(f"/api/requests/{rid}/transition", json={"action": "mark_overdue"})
    client.post(f"/api/requests/{rid}/transition", json={"action": "mark_escalated"})

    resp = client.post(f"/api/blast/generate-complaint/{rid}")
    assert resp.status_code == 200
    data = resp.json()
    # Google Search RTBF is a national Art. 55 case: residence SA decides itself
    assert data["dpa"]["short_name"] == "Datatilsynet"
    text = data["complaint_text"]
    assert "Google LLC" in text
    assert "artikel 55" in text  # Danish processing-scoped Art. 55 paragraph
    assert created["target_url"] in text
    assert "C-131/12" in text
    # must NOT assert Google has no EU establishment at all — that is false
    # (Google Ireland exists); only the Search-RTBF processing lacks one
    assert "ingen etablering i EU" not in text
    assert "for denne behandling" in text
    # contact field must not be blank: form engines fall back to the form URL
    assert "reportcontent.google.com" in text


def test_brave_complaint_states_email_channel(client, config):
    eid = _seed_url_exposure(config)
    created = client.post(
        f"/api/scan/exposures/{eid}/delisting-request", json={"engine": "brave"},
    ).json()
    rid = created["request_id"]
    client.post(f"/api/requests/{rid}/transition", json={"action": "mark_overdue"})
    client.post(f"/api/requests/{rid}/transition", json={"action": "mark_escalated"})

    text = client.post(f"/api/blast/generate-complaint/{rid}").json()["complaint_text"]
    # Brave filings go by email — the complaint must not claim a form was used
    assert "e-mail" in text
    assert "formular" not in text


def test_kit_carries_verify_links(client, config):
    eid = _seed_url_exposure(config)
    kit = client.get(f"/api/scan/exposures/{eid}/delisting-kit").json()
    assert "pws=0" in kit["verify"]["google"]
    assert "mkt=da-DK" in kit["verify"]["bing"]
    assert kit["verify"]["results_about_you"].startswith("https://myactivity.google.com")


# ---------------------------------------------------------------------------
# Rescan re-verification
# ---------------------------------------------------------------------------


def test_rescan_flags_resurfaced_delisted_url():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from backend.core.request import RequestManager
    from backend.core.rescan import check_for_reappearances
    from backend.db.models import Base, RequestType

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    mgr = RequestManager(session)
    req = mgr.create(
        "delisting-google", RequestType.ERASURE,
        target_url="https://example.com/malte-profile/",
    )
    mgr.mark_manual_action_needed(req.id, "filed")
    mgr.mark_sent(req.id)
    mgr.mark_acknowledged(req.id, "granted")
    mgr.mark_completed(req.id)

    hits = [{
        "broker_domain": "example.com",
        "broker_name": "example.com",
        "snippet": "profile of Malte",
        "url": "https://example.com/malte-profile",  # same URL, no trailing slash
    }]
    with patch("backend.core.notifier.notify"):
        report = check_for_reappearances(session, hits)
    assert len(report.reappeared) == 1
    assert "delisting-google" in report.reappeared[0].broker_name
    session.close()


async def test_verify_delisted_urls_flags_resurfaced_variant():
    """Bare name queries must catch a resurfaced delisted URL even when the
    scheme/www form differs — the broker rescan is site:-scoped and blind here."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from backend.core.profile import Profile
    from backend.core.request import RequestManager
    from backend.core.rescan import verify_delisted_urls
    from backend.db.models import Base, RequestType

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    mgr = RequestManager(session)
    req = mgr.create(
        "delisting-google", RequestType.ERASURE,
        target_url="https://www.politiken.dk/article123",
    )
    mgr.mark_manual_action_needed(req.id, "filed")
    mgr.mark_sent(req.id)
    mgr.mark_acknowledged(req.id, "granted")
    mgr.mark_completed(req.id)

    async def fake_search(query, client, region=None):
        assert region == "dk-da"  # RTBF filter is market-scoped
        assert query == '"Test User"'
        return [
            {"url": "http://politiken.dk/article123/", "title": "t", "snippet": "s"},
            {"url": "https://other.dk/x", "title": "t", "snippet": "s"},
        ]

    with patch("backend.scanner.duckduckgo._search_ddg", fake_search), patch(
        "backend.core.notifier.notify"
    ):
        alerts = await verify_delisted_urls(
            session, Profile(full_name="Test User", emails=["t@t.com"]),
        )
    assert len(alerts) == 1
    assert "delisting-google" in alerts[0].broker_name
    session.close()


async def test_verify_delisted_urls_no_completed_requests_is_free():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from backend.core.profile import Profile
    from backend.core.rescan import verify_delisted_urls
    from backend.db.models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    with patch("backend.scanner.duckduckgo._search_ddg") as mock_search:
        alerts = await verify_delisted_urls(
            session, Profile(full_name="Test User", emails=["t@t.com"]),
        )
    assert alerts == []
    mock_search.assert_not_called()  # no queries when nothing is delisted
    session.close()


async def test_ddg_region_only_set_when_requested():
    """The broker discovery scan must stay region-neutral — forcing dk-da
    region-biases US people-search queries and silently costs recall."""
    from backend.scanner.duckduckgo import _search_ddg

    captured = {}

    class FakeResp:
        text = "<html></html>"

        def raise_for_status(self):
            pass

    class FakeClient:
        async def post(self, url, **kwargs):
            captured.update(kwargs)
            return FakeResp()

    await _search_ddg("q", FakeClient())
    assert "kl" not in captured["data"]
    await _search_ddg("q", FakeClient(), region="dk-da")
    assert captured["data"]["kl"] == "dk-da"


def test_rescan_ignores_unrelated_urls_for_delisting():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from backend.core.request import RequestManager
    from backend.core.rescan import check_for_reappearances
    from backend.db.models import Base, RequestType

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    mgr = RequestManager(session)
    req = mgr.create(
        "delisting-google", RequestType.ERASURE, target_url="https://example.com/a",
    )
    mgr.mark_manual_action_needed(req.id, "filed")
    mgr.mark_sent(req.id)
    mgr.mark_acknowledged(req.id, "granted")
    mgr.mark_completed(req.id)

    hits = [{"broker_domain": "example.com", "url": "https://example.com/other"}]
    with patch("backend.core.notifier.notify"):
        report = check_for_reappearances(session, hits)
    assert report.reappeared == []
    session.close()


# ---------------------------------------------------------------------------
# Scheduler integration
# ---------------------------------------------------------------------------


async def test_form_only_delisting_escalates_after_window():
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from backend.core.profile import Profile, SmtpConfig
    from backend.core.request import RequestManager
    from backend.core.scheduler import run_follow_ups
    from backend.core.template import TemplateRenderer
    from backend.db.models import Base, Request, RequestEvent, RequestStatus, RequestType

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    mgr = RequestManager(session)
    req = mgr.create("delisting-google", RequestType.ERASURE, target_url="https://x.com/p")
    mgr.mark_manual_action_needed(req.id, "filed via form")
    mgr.mark_sent(req.id)
    mgr.mark_overdue(req.id)
    ev = (
        session.query(RequestEvent)
        .filter(RequestEvent.request_id == req.id, RequestEvent.event_type == "overdue")
        .one()
    )
    ev.created_at = datetime.now(UTC) - timedelta(days=8)
    session.commit()

    union = RegistryUnion(
        BrokerRegistry([]), ControllerRegistry([]), delisting=DelistingRegistry(),
    )
    renderer = TemplateRenderer(Path(__file__).parent.parent.parent / "templates")
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="t@t.com", password="p")
    with patch(
        "backend.core.scheduler.EmailSender.send", new_callable=AsyncMock
    ) as mock_send:
        result = await run_follow_ups(
            session=session,
            profile=Profile(full_name="T", emails=["t@t.com"]),
            smtp=smtp,
            broker_registry=union,
            renderer=renderer,
        )
    assert result.escalated_no_email == 1
    mock_send.assert_not_awaited()
    assert session.get(Request, req.id).status == RequestStatus.ESCALATED
    session.close()


async def test_brave_delisting_gets_email_follow_up():
    from datetime import UTC, datetime, timedelta
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from backend.core.profile import Profile, SmtpConfig
    from backend.core.request import RequestManager
    from backend.core.scheduler import run_follow_ups
    from backend.core.template import TemplateRenderer
    from backend.db.models import Base, RequestType
    from backend.senders.base import SenderResult, SenderStatus

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    mgr = RequestManager(session)
    req = mgr.create("delisting-brave", RequestType.ERASURE, target_url="https://x.com/p")
    mgr.mark_manual_action_needed(req.id, "emailed by user")
    mgr.mark_sent(req.id)
    db_req = session.get(type(req), req.id)
    db_req.deadline_at = datetime.now(UTC) - timedelta(days=1)
    session.commit()

    union = RegistryUnion(
        BrokerRegistry([]), ControllerRegistry([]), delisting=DelistingRegistry(),
    )
    renderer = TemplateRenderer(Path(__file__).parent.parent.parent / "templates")
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="t@t.com", password="p")
    with patch(
        "backend.core.scheduler.EmailSender.send", new_callable=AsyncMock
    ) as mock_send:
        mock_send.return_value = SenderResult(status=SenderStatus.SUCCESS, message="ok")
        result = await run_follow_ups(
            session=session,
            profile=Profile(full_name="T", emails=["t@t.com"]),
            smtp=smtp,
            broker_registry=union,
            renderer=renderer,
        )
    assert result.follow_ups_sent == 1
    assert mock_send.await_args.kwargs["to_email"] == "privacy@brave.com"
    session.close()


def test_ddg_region_follows_user_country():
    """Delisting is market-scoped (C-507/17) — a GB user's RTBF filter applies
    to the UK market, so re-verification must not query the DK region."""
    from backend.core.rescan import ddg_region_for_country

    assert ddg_region_for_country("DK") == "dk-da"
    assert ddg_region_for_country("GB") == "uk-en"
    assert ddg_region_for_country("de") == "de-de"      # case-insensitive
    assert ddg_region_for_country("") == "dk-da"        # fallback
    assert ddg_region_for_country("ZZ") == "dk-da"      # unknown -> fallback


def test_google_art55_never_cites_procedural_regulation(client, config):
    """Reg (EU) 2025/2518's admissibility/15-month rules are for CROSS-BORDER
    processing. Google Search RTBF is a national Art. 55 case against Google
    LLC — the line must stay out even after the 2027 application date."""
    from datetime import date
    from unittest.mock import patch

    eid = _seed_url_exposure(config)
    created = client.post(
        f"/api/scan/exposures/{eid}/delisting-request", json={"engine": "google"},
    ).json()
    rid = created["request_id"]
    client.post(f"/api/requests/{rid}/transition", json={"action": "mark_overdue"})
    client.post(f"/api/requests/{rid}/transition", json={"action": "mark_escalated"})

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2030, 1, 1)  # long after the application date

    with patch("backend.api.blast._date", FakeDate):
        resp = client.post(f"/api/blast/generate-complaint/{rid}")
    text = resp.json()["complaint_text"]
    assert "2025/2518" not in text
    assert "artikel 55" in text  # still the national-competence wording
