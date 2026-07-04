"""Controller track — registry, kit rendering, DPA routing, scheduler guard."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.core.broker import Broker, BrokerRegistry, RemovalMethod
from backend.core.controller import (
    ControllerRegistry,
    RegistryUnion,
    build_kit,
)
from backend.core.dpa import get_dpa_for_request
from backend.core.profile import Profile, SmtpConfig
from backend.core.request import RequestManager
from backend.core.scheduler import run_follow_ups
from backend.core.template import TemplateRenderer
from backend.db.models import Base, RequestType

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONTROLLERS_YAML = PROJECT_ROOT / "brokers" / "controllers.yaml"
TEMPLATES_DIR = PROJECT_ROOT / "templates"


@pytest.fixture
def registry() -> ControllerRegistry:
    return ControllerRegistry.load(CONTROLLERS_YAML)


@pytest.fixture
def profile() -> Profile:
    return Profile(full_name="Test User", emails=["test@example.com"])


@pytest.fixture
def renderer() -> TemplateRenderer:
    return TemplateRenderer(TEMPLATES_DIR)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_loads_all_controllers(registry):
    assert len(registry.controllers) == 16
    ids = [c.id for c in registry.controllers]
    assert len(set(ids)) == 16


def test_registry_get_by_id_and_domain(registry):
    meta = registry.get("meta-com")
    assert meta is not None
    assert meta.eu_entity.startswith("Meta Platforms Ireland")
    assert registry.get_by_domain("reddit.com").name == "Reddit"
    assert registry.get("does-not-exist") is None


def test_email_viable_implies_email_present(registry):
    for c in registry.controllers:
        if c.email_viable:
            assert c.privacy_email, f"{c.name}: email_viable without privacy_email"
            assert c.contact_kind in ("privacy_email", "dpo_email")
        else:
            assert c.contact_kind == "form_only"
            assert c.erasure_form_url, f"{c.name}: form_only without erasure_form_url"
            assert not c.privacy_email, f"{c.name}: form_only must not carry an email"


def test_broker_compat_properties(registry):
    amazon = registry.get("amazon-de")
    assert amazon.dpo_email == "eu-privacy@amazon.de"
    assert amazon.country == "LU"
    assert amazon.category == "controller"


def test_no_eu_establishment_flag(registry):
    snap = registry.get_by_domain("snapchat.com")
    assert snap.no_eu_establishment is True
    assert snap.art27_rep
    others = [c for c in registry.controllers if c.no_eu_establishment]
    assert others == [snap]


def test_broker_registry_does_not_load_controllers():
    broker_registry = BrokerRegistry.load(PROJECT_ROOT / "brokers")
    assert broker_registry.get("meta-com") is None
    assert broker_registry.get_by_domain("snapchat.com") is None


def test_registry_missing_file_returns_empty(tmp_path):
    registry = ControllerRegistry.load(tmp_path / "nope.yaml")
    assert registry.controllers == []


# ---------------------------------------------------------------------------
# Registry union (shared machinery lookup)
# ---------------------------------------------------------------------------


def test_registry_union_resolves_both(registry):
    broker = Broker(
        name="B", domain="b.com", category="data_broker", dpo_email="dpo@b.com",
        removal_method=RemovalMethod.EMAIL, country="DE", gdpr_applies=True,
        verification_required=False, language="en", last_verified="2026-01-01",
    )
    union = RegistryUnion(BrokerRegistry([broker]), registry)
    assert union.get("b-com").name == "B"
    assert union.get("github-com").name == "GitHub"
    assert union.get_by_domain("spotify.com").name == "Spotify"
    assert union.get("missing") is None
    names = {b.name for b in union.brokers}
    assert {"B", "GitHub", "Spotify"} <= names


# ---------------------------------------------------------------------------
# Kit rendering
# ---------------------------------------------------------------------------


def test_kit_addresses_the_eu_entity(registry, profile, renderer):
    kit = build_kit(registry.get("meta-com"), profile, "ABCD1234", renderer)
    assert "Meta Platforms Ireland Limited" in kit["request_text"]
    assert "ABCD1234" in kit["request_text"]
    assert kit["form_url"] == "https://help.meta.com/support/privacy/"
    assert kit["form_instructions"]
    assert kit["prerequisites"]


def test_kit_demands_content_erasure_for_reddit(registry, profile, renderer):
    kit = build_kit(registry.get_by_domain("reddit.com"), profile, "ABCD1234", renderer)
    assert "posts" in kit["request_text"].lower()
    assert "content" in kit["request_text"].lower()


def test_kit_flags_special_category_for_strava(registry, profile, renderer):
    kit = build_kit(registry.get_by_domain("strava.com"), profile, "ABCD1234", renderer)
    assert "Article 9" in kit["request_text"]


def test_kit_plain_controller_has_no_special_blocks(registry, profile, renderer):
    kit = build_kit(registry.get_by_domain("spotify.com"), profile, "ABCD1234", renderer)
    assert "Article 9" not in kit["request_text"]
    assert "Spotify AB" in kit["request_text"]


# ---------------------------------------------------------------------------
# DPA routing
# ---------------------------------------------------------------------------


def _make_broker(country: str) -> Broker:
    return Broker(
        name="B", domain="b.com", category="data_broker", dpo_email="dpo@b.com",
        removal_method=RemovalMethod.EMAIL, country=country, gdpr_applies=True,
        verification_required=False, language="en", last_verified="2026-01-01",
    )


def test_broker_routing_unchanged_by_residence():
    dpa = get_dpa_for_request(_make_broker("DE"), user_country="DK")
    assert dpa["short_name"] == "BfDI"


def test_controller_routes_to_residence_dpa(registry):
    meta = registry.get("meta-com")  # IE establishment
    dpa = get_dpa_for_request(meta, user_country="DK")
    assert dpa["short_name"] == "Datatilsynet"


def test_controller_no_eu_establishment_routes_to_residence(registry):
    snap = registry.get_by_domain("snapchat.com")
    dpa = get_dpa_for_request(snap, user_country="DK")
    assert dpa["short_name"] == "Datatilsynet"


def test_controller_gb_entity_routes_to_ico(registry):
    ctrl = registry.get("meta-com").model_copy(update={"entity_country": "GB"})
    dpa = get_dpa_for_request(ctrl, user_country="DK")
    assert dpa["short_name"] == "ICO"


# ---------------------------------------------------------------------------
# Scheduler guard: overdue form-only controller requests must not attempt email
# ---------------------------------------------------------------------------


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


async def test_follow_up_skips_form_only_controller(registry, profile, renderer):
    session = _make_session()
    mgr = RequestManager(session)
    req = mgr.create("meta-com", RequestType.ERASURE)
    mgr.mark_manual_action_needed(req.id, "form-only controller")
    mgr.mark_sent(req.id)
    db_req = session.get(type(req), req.id)
    db_req.deadline_at = datetime.now(UTC) - timedelta(days=1)
    session.commit()

    union = RegistryUnion(BrokerRegistry([]), registry)
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="t@t.com", password="pw")
    with patch(
        "backend.core.scheduler.EmailSender.send", new_callable=AsyncMock
    ) as mock_send:
        result = await run_follow_ups(
            session=session, profile=profile, smtp=smtp,
            broker_registry=union, renderer=renderer,
        )
    assert result.newly_overdue == 1
    assert result.errors == []
    mock_send.assert_not_awaited()
    session.close()


async def test_follow_up_still_emails_viable_controller(registry, profile, renderer):
    session = _make_session()
    mgr = RequestManager(session)
    req = mgr.create("github-com", RequestType.ERASURE)
    mgr.mark_sent(req.id)
    db_req = session.get(type(req), req.id)
    db_req.deadline_at = datetime.now(UTC) - timedelta(days=1)
    session.commit()

    union = RegistryUnion(BrokerRegistry([]), registry)
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="t@t.com", password="pw")
    from backend.senders.base import SenderResult, SenderStatus

    with patch(
        "backend.core.scheduler.EmailSender.send", new_callable=AsyncMock
    ) as mock_send:
        mock_send.return_value = SenderResult(status=SenderStatus.SUCCESS, message="ok")
        result = await run_follow_ups(
            session=session, profile=profile, smtp=smtp,
            broker_registry=union, renderer=renderer,
        )
    assert result.follow_ups_sent == 1
    assert mock_send.await_args.kwargs["to_email"] == "privacy@github.com"
    session.close()
