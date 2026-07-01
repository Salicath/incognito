"""Tests for the cpr_lever track — registry, state transitions, API, blast integration."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.core.broker import BrokerRegistry
from backend.core.cpr_lever import (
    CprLever,
    CprLeverRegistry,
    compute_expiry,
    covered_broker_ids,
    effective_status,
)

PROJECT_ROOT = Path(__file__).parent.parent.parent
LEVERS_PATH = PROJECT_ROOT / "brokers" / "cpr_levers.yaml"


def _lever(**overrides) -> CprLever:
    base = {
        "lever_id": "test_lever",
        "name": "Test",
        "description": "d",
        "url": "https://example.com",
        "requires_mitid": True,
        "expires_after_days": 365,
        "cascade_broker_ids": ["krak-dk"],
    }
    base.update(overrides)
    return CprLever.model_validate(base)


class TestRegistry:
    def test_loads_seed_file(self):
        reg = CprLeverRegistry.load(LEVERS_PATH)
        assert len(reg.levers) == 6
        assert reg.get("dk_cpr_navnebeskyttelse") is not None

    def test_missing_file_gives_empty_registry(self, tmp_path):
        reg = CprLeverRegistry.load(tmp_path / "nope.yaml")
        assert reg.levers == []

    def test_cascade_ids_resolve_to_real_brokers(self):
        brokers = BrokerRegistry.load(PROJECT_ROOT / "brokers")
        levers = CprLeverRegistry.load(LEVERS_PATH)
        for lever in levers.levers:
            for bid in lever.cascade_broker_ids:
                assert brokers.get(bid) is not None, f"{lever.lever_id}: unknown broker {bid}"

    def test_mutual_exclusions_reference_real_levers(self):
        levers = CprLeverRegistry.load(LEVERS_PATH)
        for lever in levers.levers:
            for other in lever.mutual_exclusion:
                assert levers.get(other) is not None

    def test_broker_registry_skips_levers_file(self):
        brokers = BrokerRegistry.load(PROJECT_ROOT / "brokers")
        assert all("cpr_lever" not in b.id for b in brokers.brokers)


class TestTransitions:
    def test_expiry_computed_from_days(self):
        activated = datetime(2026, 7, 1, tzinfo=UTC)
        assert compute_expiry(_lever(), activated) == activated + timedelta(days=365)

    def test_persistent_lever_never_expires(self):
        assert compute_expiry(_lever(expires_after_days=None), datetime.now(UTC)) is None

    def test_active_far_from_expiry_stays_active(self):
        expires = datetime.now(UTC) + timedelta(days=200)
        assert effective_status("active", expires) == "active"

    def test_active_within_30_days_becomes_renewal_due(self):
        expires = datetime.now(UTC) + timedelta(days=10)
        assert effective_status("active", expires) == "renewal_due"

    def test_active_past_expiry_becomes_expired(self):
        expires = datetime.now(UTC) - timedelta(days=1)
        assert effective_status("active", expires) == "expired"

    def test_naive_datetime_treated_as_utc(self):
        expires = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        assert effective_status("active", expires) == "expired"

    def test_deferred_passes_through(self):
        assert effective_status("user_deferred", None) == "user_deferred"

    def test_persistent_active_stays_active(self):
        assert effective_status("active", None) == "active"


class TestCoverage:
    def test_active_lever_covers_cascade(self):
        reg = CprLeverRegistry([_lever()])
        states = {"test_lever": ("active", datetime.now(UTC) + timedelta(days=100))}
        assert covered_broker_ids(reg, states) == {"krak-dk"}

    def test_expired_lever_stops_covering(self):
        reg = CprLeverRegistry([_lever()])
        states = {"test_lever": ("active", datetime.now(UTC) - timedelta(days=1))}
        assert covered_broker_ids(reg, states) == set()

    def test_unconfirmed_lever_covers_nothing(self):
        reg = CprLeverRegistry([_lever()])
        assert covered_broker_ids(reg, {}) == set()


class TestApi:
    def test_requires_auth(self, config, seeded_vault):
        from fastapi.testclient import TestClient

        from backend.main import create_app

        client = TestClient(create_app(config))
        assert client.get("/api/cpr-levers").status_code == 401

    def test_list_levers_initial_state(self, authenticated_client):
        resp = authenticated_client.get("/api/cpr-levers")
        assert resp.status_code == 200
        levers = resp.json()
        assert len(levers) == 6
        assert all(lv["status"] == "new" for lv in levers)
        nav = next(lv for lv in levers if lv["lever_id"] == "dk_cpr_navnebeskyttelse")
        assert len(nav["cascade"]) == 4
        assert nav["cascade"][0]["name"]  # resolved broker names

    def test_confirm_sets_active_with_expiry(self, authenticated_client):
        resp = authenticated_client.post("/api/cpr-levers/dk_cpr_navnebeskyttelse/confirm")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["expires_at"] is not None

        levers = authenticated_client.get("/api/cpr-levers").json()
        nav = next(lv for lv in levers if lv["lever_id"] == "dk_cpr_navnebeskyttelse")
        assert nav["status"] == "active"

    def test_confirm_persistent_lever_has_no_expiry(self, authenticated_client):
        resp = authenticated_client.post("/api/cpr-levers/dk_krak_selvbetjening/confirm")
        assert resp.status_code == 200
        assert resp.json()["expires_at"] is None

    def test_mutual_exclusion_blocks_conflicting_confirm(self, authenticated_client):
        authenticated_client.post("/api/cpr-levers/dk_cpr_navnebeskyttelse/confirm")
        resp = authenticated_client.post("/api/cpr-levers/dk_robinsonlisten/confirm")
        assert resp.status_code == 409

        levers = authenticated_client.get("/api/cpr-levers").json()
        robinson = next(lv for lv in levers if lv["lever_id"] == "dk_robinsonlisten")
        assert robinson["active_conflicts"] == ["dk_cpr_navnebeskyttelse"]

    def test_defer_records_note(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/cpr-levers/dk_robinsonlisten/defer", json={"note": "prefer navnebeskyttelse"}
        )
        assert resp.status_code == 200

        levers = authenticated_client.get("/api/cpr-levers").json()
        robinson = next(lv for lv in levers if lv["lever_id"] == "dk_robinsonlisten")
        assert robinson["status"] == "user_deferred"
        assert robinson["user_note"] == "prefer navnebeskyttelse"

    def test_unknown_lever_404(self, authenticated_client):
        assert authenticated_client.post("/api/cpr-levers/nope/confirm").status_code == 404
        assert (
            authenticated_client.post("/api/cpr-levers/nope/defer", json={}).status_code == 404
        )

    def test_expired_lever_reported_expired(self, authenticated_client):
        from backend.db.models import CprLeverState

        authenticated_client.post("/api/cpr-levers/dk_cpr_navnebeskyttelse/confirm")

        factory = authenticated_client.app.state.db_session_factory
        db = factory()
        try:
            state = db.get(CprLeverState, "dk_cpr_navnebeskyttelse")
            state.expires_at = datetime.now(UTC) - timedelta(days=2)
            db.commit()
        finally:
            db.close()

        levers = authenticated_client.get("/api/cpr-levers").json()
        nav = next(lv for lv in levers if lv["lever_id"] == "dk_cpr_navnebeskyttelse")
        assert nav["status"] == "expired"


class TestBlastIntegration:
    def test_blast_skips_lever_covered_brokers(self, authenticated_client):
        authenticated_client.post("/api/cpr-levers/dk_cpr_navnebeskyttelse/confirm")

        resp = authenticated_client.post(
            "/api/blast/create", json={"request_type": "erasure", "dry_run": True}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["covered_by_lever"] == 4
        created_ids = {r["broker_id"] for r in data["requests"]}
        assert "krak-dk" not in created_ids
        assert "degulesider-dk" not in created_ids

    def test_blast_without_levers_covers_nothing(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/blast/create", json={"request_type": "erasure", "dry_run": True}
        )
        assert resp.json()["covered_by_lever"] == 0
