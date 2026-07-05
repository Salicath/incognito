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

    # exposure marked actioned
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
