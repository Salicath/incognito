"""time_locked + restriction_only tracks — registries, expiry math, API, scheduler."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.core.restriction_only import RestrictionRegistry
from backend.core.time_locked import (
    TimeLockedRegistry,
    check_time_locked_expiries,
    compute_fires_at,
)
from backend.db.models import Base, TimeLockedState, TimeLockedStatus

PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def tl_registry() -> TimeLockedRegistry:
    return TimeLockedRegistry.load(PROJECT_ROOT / "brokers" / "time_locked.yaml")


@pytest.fixture
def ro_registry() -> RestrictionRegistry:
    return RestrictionRegistry.load(PROJECT_ROOT / "brokers" / "restriction_only.yaml")


# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------


def test_time_locked_registry_loads(tl_registry):
    assert len(tl_registry.entries) == 5
    bank = tl_registry.get("dk-bank-hvidvask")
    assert bank.expiry.years == 5
    assert not bank.expiry.from_fiscal_year_end
    # PLAN's "5y+1mo" was wrong: the month is escalation tolerance, not fire date
    assert bank.escalation_after_days == 30
    assert "LBK 433" in bank.legal_basis  # never the defective LBK 1463/2025
    # a limitation period is not a statutory retention duty — the letter must
    # make a different legal claim for these two
    assert bank.basis_kind == "retention_duty"
    assert tl_registry.get("dk-insurer-foraeldelse").basis_kind == "limitation"
    assert tl_registry.get("dk-employer-post-employment").basis_kind == "limitation"


def test_restriction_registry_loads(ro_registry):
    assert len(ro_registry.entries) == 9
    # Skat has no computable expiry — it must live here, not in time_locked
    assert ro_registry.get("dk-skat-restriction-only") is not None
    tele = ro_registry.get("telelogning")
    assert "2027" in tele.why_undeletable  # annually-renewed rules carry a marker
    mitid = [e.id for e in ro_registry.entries if e.requires_mitid]
    assert "sundhedsjournalen" in mitid


def test_broker_registry_ignores_statutory_yamls():
    from backend.core.broker import BrokerRegistry

    registry = BrokerRegistry.load(PROJECT_ROOT / "brokers")
    assert registry.get("dk-bank-hvidvask") is None
    assert registry.get("sundhedsjournalen") is None


# ---------------------------------------------------------------------------
# Expiry math
# ---------------------------------------------------------------------------


def test_bank_fires_at_exactly_five_years(tl_registry):
    bank = tl_registry.get("dk-bank-hvidvask")
    assert compute_fires_at(bank, date(2024, 3, 15)) == date(2029, 3, 15)


def test_leap_day_maps_forward_to_mar_1(tl_registry):
    # Feb 28 would fire a day before the period indisputably lapsed — handing
    # the bank a technically-correct refusal of the letter's central claim
    bank = tl_registry.get("dk-bank-hvidvask")
    assert compute_fires_at(bank, date(2024, 2, 29)) == date(2029, 3, 1)


def test_bogfoering_runs_from_fiscal_year_end(tl_registry):
    bog = tl_registry.get("dk-company-bogfoering")
    # invoice 2024-03-15 -> FY ends 2024-12-31 -> +5y -> fires 2030-01-01
    assert compute_fires_at(bog, date(2024, 3, 15)) == date(2030, 1, 1)


def test_insurer_conservative_toggle(tl_registry):
    ins = tl_registry.get("dk-insurer-foraeldelse")
    assert compute_fires_at(ins, date(2024, 1, 1)) == date(2027, 1, 1)
    assert compute_fires_at(ins, date(2024, 1, 1), conservative=True) == date(2034, 1, 1)


# ---------------------------------------------------------------------------
# Scheduler check
# ---------------------------------------------------------------------------


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_check_fires_matured_holds_once(tl_registry):
    db = _session()
    db.add(TimeLockedState(
        entry_id="dk-bank-hvidvask",
        institution="Danske Bank",
        trigger_date=datetime(2020, 1, 1, tzinfo=UTC),
        fires_at=datetime.now(UTC) - timedelta(days=1),
        status=TimeLockedStatus.ARMED,
    ))
    db.add(TimeLockedState(
        entry_id="dk-telco-billing",
        trigger_date=datetime(2025, 1, 1, tzinfo=UTC),
        fires_at=datetime.now(UTC) + timedelta(days=400),
        status=TimeLockedStatus.ARMED,
    ))
    db.commit()

    with patch("backend.core.time_locked.notify") as mock_notify:
        result = check_time_locked_expiries(db, tl_registry)
    assert result.fired == ["dk-bank-hvidvask"]
    assert mock_notify.call_count == 1
    assert "Danske Bank" in mock_notify.call_args.args[1]

    # idempotent: second run fires nothing
    with patch("backend.core.time_locked.notify") as mock_notify:
        result = check_time_locked_expiries(db, tl_registry)
    assert result.fired == []
    mock_notify.assert_not_called()
    db.close()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def test_list_time_locked(authenticated_client):
    resp = authenticated_client.get("/api/statutory/time-locked")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    assert all(e["holds"] == [] for e in data)


def test_arm_and_dismiss_flow(authenticated_client):
    resp = authenticated_client.post(
        "/api/statutory/time-locked/dk-bank-hvidvask/arm",
        json={"trigger_date": "2024-03-15", "institution": "Danske Bank"},
    )
    assert resp.status_code == 200
    hold = resp.json()
    assert hold["fires_at"] == "2029-03-15"
    assert hold["status"] == "armed"

    listing = authenticated_client.get("/api/statutory/time-locked").json()
    bank = next(e for e in listing if e["id"] == "dk-bank-hvidvask")
    assert len(bank["holds"]) == 1

    resp = authenticated_client.post(
        f"/api/statutory/time-locked/holds/{hold['id']}/dismiss"
    )
    assert resp.json()["status"] == "dismissed"


def test_arm_with_past_expiry_fires_immediately(authenticated_client):
    resp = authenticated_client.post(
        "/api/statutory/time-locked/dk-bank-hvidvask/arm",
        json={"trigger_date": "2019-01-01", "institution": "Old Bank"},
    )
    assert resp.json()["status"] == "fired"


def test_kit_for_fired_hold(authenticated_client):
    hold = authenticated_client.post(
        "/api/statutory/time-locked/dk-bank-hvidvask/arm",
        json={"trigger_date": "2019-01-01", "institution": "Old Bank"},
    ).json()
    resp = authenticated_client.get(f"/api/statutory/time-locked/holds/{hold['id']}/kit")
    assert resp.status_code == 200
    kit = resp.json()
    text = kit["request_text"]
    assert "artikel 17" in text  # Danish template
    assert "Hvidvaskloven" in text
    assert "2024-01-01" in text  # fires_at = trigger + 5y
    assert "lovpligtige opbevaringsperiode" in text  # retention-duty claim
    assert kit["escalation_after_days"] == 30
    # UI guidance must never leak into the outgoing letter — it is English,
    # addressed to the user, and self-undermining
    assert "guaranteed win" not in text
    assert "The statute itself mandates" not in text


def test_limitation_kit_makes_the_limitation_claim(authenticated_client):
    """Insurer/employer retention rests on limitation, not a retention duty —
    asserting a lapsed 'lovpligtig opbevaringsperiode' would be legally wrong
    and let the DPO refute the letter's premise."""
    hold = authenticated_client.post(
        "/api/statutory/time-locked/dk-insurer-foraeldelse/arm",
        json={"trigger_date": "2019-01-01", "institution": "Old Insurer"},
    ).json()
    assert hold["status"] == "fired"
    text = authenticated_client.get(
        f"/api/statutory/time-locked/holds/{hold['id']}/kit"
    ).json()["request_text"]
    assert "forældelsesfrist" in text.lower()
    assert "ikke rejst, anerkendt eller varslet krav" in text
    assert "lovpligtige opbevaringsperiode" not in text


def test_kit_survives_customized_templates_dir(authenticated_client, config):
    """A user templates dir predating this release lacks the new template —
    the renderer must fall back to the repo copy instead of 500ing."""
    (config.data_dir / "templates").mkdir(exist_ok=True)
    hold = authenticated_client.post(
        "/api/statutory/time-locked/dk-bank-hvidvask/arm",
        json={"trigger_date": "2019-01-01"},
    ).json()
    resp = authenticated_client.get(f"/api/statutory/time-locked/holds/{hold['id']}/kit")
    assert resp.status_code == 200


def test_arm_rejects_out_of_range_dates(authenticated_client):
    for bad in ("0224-03-15", "9999-01-01"):
        resp = authenticated_client.post(
            "/api/statutory/time-locked/dk-bank-hvidvask/arm",
            json={"trigger_date": bad},
        )
        assert resp.status_code == 400, bad


def test_web_follow_up_fires_matured_holds(authenticated_client, config):
    """Server-only deployments have no CLI timer — the web follow-up endpoint
    must fire armed holds too."""
    hold = authenticated_client.post(
        "/api/statutory/time-locked/dk-bank-hvidvask/arm",
        json={"trigger_date": "2025-01-01", "institution": "Web Bank"},
    ).json()
    assert hold["status"] == "armed"

    from backend.db.session import init_db

    db = init_db(config.db_path)()
    try:
        state = db.get(TimeLockedState, hold["id"])
        state.fires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()
    finally:
        db.close()

    with patch("backend.core.time_locked.notify"):
        resp = authenticated_client.post("/api/blast/follow-up")
    assert resp.status_code == 200
    assert resp.json()["time_locked_fired"] == 1

    listing = authenticated_client.get("/api/statutory/time-locked").json()
    bank = next(e for e in listing if e["id"] == "dk-bank-hvidvask")
    assert bank["holds"][0]["status"] == "fired"


def test_broker_loader_warns_on_reserved_stem_broker_file(tmp_path):
    import yaml as _yaml

    from backend.core.broker import BrokerRegistry

    (tmp_path / "time_locked.yaml").write_text(_yaml.dump({
        "name": "My Custom Broker", "domain": "custom.dk",
        "category": "data_broker", "dpo_email": "dpo@custom.dk",
        "removal_method": "email", "country": "DK", "gdpr_applies": True,
        "verification_required": False, "language": "da",
        "last_verified": "2026-01-01",
    }))
    with patch("backend.core.broker.log") as mock_log:
        registry = BrokerRegistry.load(tmp_path)
    assert registry.brokers == []
    assert any(
        "reserved registry filename" in str(call)
        for call in mock_log.warning.call_args_list
    )


def test_kit_refused_while_armed(authenticated_client):
    hold = authenticated_client.post(
        "/api/statutory/time-locked/dk-bank-hvidvask/arm",
        json={"trigger_date": "2025-01-01"},
    ).json()
    assert hold["status"] == "armed"
    resp = authenticated_client.get(f"/api/statutory/time-locked/holds/{hold['id']}/kit")
    assert resp.status_code == 400


def test_arm_validation(authenticated_client):
    assert authenticated_client.post(
        "/api/statutory/time-locked/nope/arm", json={"trigger_date": "2024-01-01"},
    ).status_code == 404
    assert authenticated_client.post(
        "/api/statutory/time-locked/dk-bank-hvidvask/arm",
        json={"trigger_date": "not-a-date"},
    ).status_code == 400


def test_restriction_only_endpoint(authenticated_client):
    resp = authenticated_client.get("/api/statutory/restriction-only")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 9
    sundhed = next(e for e in data if e["id"] == "sundhedsjournalen")
    assert sundhed["requires_mitid"] is True
    assert "Privatmarkering" in sundhed["mitigation"]


def test_retention_lapsed_uses_its_own_event_type(tl_registry):
    """A matured hold is an action prompt, not a 'request_overdue' warning."""
    from backend.core.notifier import EventType

    db = _session()
    db.add(TimeLockedState(
        entry_id="dk-bank-hvidvask",
        trigger_date=datetime(2020, 1, 1, tzinfo=UTC),
        fires_at=datetime.now(UTC) - timedelta(days=1),
        status=TimeLockedStatus.ARMED,
    ))
    db.commit()

    with patch("backend.core.time_locked.notify") as mock_notify:
        check_time_locked_expiries(db, tl_registry)
    assert mock_notify.call_args.args[0] is EventType.RETENTION_LAPSED
    db.close()
