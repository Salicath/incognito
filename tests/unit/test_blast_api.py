from datetime import date

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.core.config import AppConfig
from backend.core.profile import Profile, ProfileVault, SmtpConfig


@pytest.fixture
def app_dir(tmp_path):
    brokers_dir = tmp_path / "brokers"
    brokers_dir.mkdir()
    for i in range(5):
        broker = {
            "name": f"Test Broker {i}",
            "domain": f"broker{i}.com",
            "category": "data_broker",
            "dpo_email": f"dpo@broker{i}.com",
            "removal_method": "email",
            "country": "US",
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
        emails=["test@test.com"],
        phones=[],
        addresses=[],
    )
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="test@test.com", password="p")
    vault.save(profile, smtp, "password")

    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    c.post("/api/auth/unlock", json={"password": "password"})
    return c


def test_blast_dry_run(client):
    response = client.post("/api/blast/create", json={
        "request_type": "access",
        "dry_run": True,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is True
    assert data["created"] == 5
    assert data["skipped"] == 0
    assert data["total_brokers"] == 5
    assert len(data["requests"]) == 5
    assert data["requests"][0]["status"] == "would_create"


def test_blast_create(client):
    response = client.post("/api/blast/create", json={
        "request_type": "erasure",
        "dry_run": False,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == 5
    assert data["dry_run"] is False
    assert data["requests"][0]["status"] == "created"
    assert "request_id" in data["requests"][0]


def test_blast_skips_existing(client):
    # First blast
    client.post("/api/blast/create", json={"request_type": "access", "dry_run": False})

    # Second blast should skip all
    response = client.post("/api/blast/create", json={"request_type": "access", "dry_run": False})
    data = response.json()
    assert data["created"] == 0
    assert data["skipped"] == 5


def test_blast_different_types_dont_skip(client):
    # Create access requests
    client.post("/api/blast/create", json={"request_type": "access", "dry_run": False})

    # Erasure requests should NOT be skipped
    response = client.post("/api/blast/create", json={"request_type": "erasure", "dry_run": False})
    data = response.json()
    assert data["created"] == 5
    assert data["skipped"] == 0


def test_blast_requires_auth(config):
    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    response = c.post("/api/blast/create", json={"request_type": "access"})
    assert response.status_code == 401


def _unlocked_client(config):
    vault = ProfileVault(config.vault_path)
    profile = Profile(
        full_name="Test User", previous_names=[], date_of_birth=date(1990, 1, 1),
        emails=["test@test.com"], phones=[], addresses=[],
    )
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="test@test.com", password="p")
    vault.save(profile, smtp, "password")

    from backend.main import create_app
    c = TestClient(create_app(config))
    c.post("/api/auth/unlock", json={"password": "password"})
    return c


def _seed_alias_row(config, broker_id):
    from backend.db.models import BrokerAlias
    from backend.db.session import init_db

    db = init_db(config.db_path)()
    try:
        db.add(BrokerAlias(
            broker_id=broker_id, alias_id=7, alias_email="abc@aleeas.com",
            reverse_alias_address="reply+x@simplelogin.co",
            recipient=f"dpo@{broker_id.removesuffix('-com')}.com",
        ))
        db.commit()
    finally:
        db.close()


def test_send_all_sends_to_the_reverse_alias(app_dir):
    """The 228-broker blast is the track's core promise — the loop must SMTP
    to the reverse-alias for aliased brokers and fall back to the real DPO
    address (not crash) when SimpleLogin fails for the rest."""
    from unittest.mock import AsyncMock, patch

    from backend.core.alias import AliasError
    from backend.senders.base import SenderResult, SenderStatus

    config = AppConfig(data_dir=app_dir, rate_limit_per_hour=3_600_000)
    client = _unlocked_client(config)
    client.post("/api/settings/simplelogin", json={"api_key": "sl-test-key"})
    _seed_alias_row(config, "broker0-com")
    client.post("/api/blast/create", json={"request_type": "erasure", "dry_run": False})

    with patch(
        "backend.senders.email.EmailSender.send",
        new_callable=AsyncMock,
        return_value=SenderResult(status=SenderStatus.SUCCESS, message="Sent"),
    ) as mock_send, patch(
        "backend.core.alias_resolver.SimpleLoginClient",
    ) as sl_cls:
        sl_cls.return_value.create_alias = AsyncMock(side_effect=AliasError("down"))
        resp = client.post("/api/blast/send-all")

    assert resp.status_code == 200
    assert resp.json()["sent"] == 5
    sent_to = [c.kwargs["to_email"] for c in mock_send.call_args_list]
    assert "reply+x@simplelogin.co" in sent_to     # aliased broker: the alias
    assert "dpo@broker1.com" in sent_to            # mint failure: real fallback
    assert "dpo@broker0.com" not in sent_to        # real address never used


def test_follow_up_route_chases_through_the_alias(app_dir):
    """Route-level guard for the 3.1 fix: an aliased thread chased via the
    real app must go to the reverse-alias — with NO SimpleLogin key stored,
    because reuse is a DB lookup and must survive key removal."""
    from datetime import UTC, datetime, timedelta
    from unittest.mock import AsyncMock, patch

    from backend.core.request import RequestManager
    from backend.db.models import RequestType
    from backend.db.session import init_db
    from backend.senders.base import SenderResult, SenderStatus

    config = AppConfig(data_dir=app_dir)
    client = _unlocked_client(config)
    _seed_alias_row(config, "broker0-com")

    db = init_db(config.db_path)()
    try:
        mgr = RequestManager(db)
        req = mgr.create("broker0-com", RequestType.ERASURE)
        mgr.mark_sent(req.id)
        req.sent_at = datetime.now(UTC) - timedelta(days=40)
        req.deadline_at = datetime.now(UTC) - timedelta(days=10)
        db.commit()
    finally:
        db.close()

    with patch(
        "backend.core.scheduler.EmailSender.send",
        new_callable=AsyncMock,
        return_value=SenderResult(status=SenderStatus.SUCCESS, message="Sent"),
    ) as mock_send:
        resp = client.post("/api/blast/follow-up")

    assert resp.status_code == 200
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["to_email"] == "reply+x@simplelogin.co"


def test_send_all_commit_failure_fails_one_broker_not_the_blast(app_dir):
    """send-all uses one session for the whole loop: a genuinely failed flush
    on broker A must be rolled back or every later broker dies on
    PendingRollbackError and one bad row fails the entire blast."""
    from unittest.mock import AsyncMock, patch

    from backend.core.request import RequestManager
    from backend.db.models import ScanResult
    from backend.senders.base import SenderResult, SenderStatus

    config = AppConfig(data_dir=app_dir, rate_limit_per_hour=3_600_000)
    client = _unlocked_client(config)
    client.post("/api/blast/create", json={"request_type": "erasure", "dry_run": False})

    real_mark_sent = RequestManager.mark_sent
    calls = {"n": 0}

    def flaky_mark_sent(self, request_id):
        calls["n"] += 1
        if calls["n"] == 1:
            # Dirty the session with a genuinely failing flush (NOT NULL
            # violation), the way a real mid-loop DB error leaves it.
            self._session.add(ScanResult(source=None, broker_id="", found_data=""))
            self._session.flush()
        return real_mark_sent(self, request_id)

    with patch(
        "backend.senders.email.EmailSender.send",
        new_callable=AsyncMock,
        return_value=SenderResult(status=SenderStatus.SUCCESS, message="Sent"),
    ), patch.object(RequestManager, "mark_sent", flaky_mark_sent):
        resp = client.post("/api/blast/send-all")

    assert resp.status_code == 200
    statuses = [r["status"] for r in resp.json()["results"]]
    assert statuses.count("error") == 1       # only the poisoned broker
    assert statuses.count("sent") == 4        # the rest of the blast survives


def test_send_all_requires_smtp(config):
    """Test that sending fails gracefully when SMTP is not configured."""
    vault = ProfileVault(config.vault_path)
    profile = Profile(
        full_name="Test", previous_names=[], date_of_birth=date(1990, 1, 1),
        emails=["t@t.com"], phones=[], addresses=[],
    )
    # Save WITHOUT smtp
    vault.save(profile, None, "password")

    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    c.post("/api/auth/unlock", json={"password": "password"})

    response = c.post("/api/blast/send-all")
    assert response.status_code == 400
    assert "SMTP" in response.json()["detail"]
