"""Controller track API — opt-in request creation, kit, send, complaint routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from backend.senders.base import SenderResult, SenderStatus


def test_list_controllers(authenticated_client):
    resp = authenticated_client.get("/api/controllers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 16
    by_id = {c["id"]: c for c in data}
    assert by_id["meta-com"]["email_viable"] is False
    assert by_id["github-com"]["email_viable"] is True
    assert all(c["request"] is None for c in data)
    # form-only records must not leak an email into the UI payload
    assert by_id["meta-com"]["privacy_email"] == ""


def test_form_only_request_creates_kit(authenticated_client):
    resp = authenticated_client.post("/api/controllers/meta-com/request")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "manual_action_needed"
    assert "Meta Platforms Ireland" in data["kit"]["request_text"]
    assert data["kit"]["form_url"].startswith("https://help.meta.com")

    # surfaces on the list with an active request now
    listing = authenticated_client.get("/api/controllers").json()
    meta = next(c for c in listing if c["id"] == "meta-com")
    assert meta["request"]["status"] == "manual_action_needed"


def test_duplicate_active_request_rejected(authenticated_client):
    assert authenticated_client.post("/api/controllers/meta-com/request").status_code == 200
    resp = authenticated_client.post("/api/controllers/meta-com/request")
    assert resp.status_code == 409


def test_unknown_controller_404(authenticated_client):
    resp = authenticated_client.post("/api/controllers/nope/request")
    assert resp.status_code == 404


def test_kit_endpoint_returns_kit_for_active_request(authenticated_client):
    created = authenticated_client.post("/api/controllers/x-com/request").json()
    resp = authenticated_client.get("/api/controllers/x-com/kit")
    assert resp.status_code == 200
    kit = resp.json()["kit"]
    assert "X Internet Unlimited Company" in kit["request_text"]
    assert created["request_id"] == resp.json()["request_id"]


def test_kit_endpoint_404_without_request(authenticated_client):
    assert authenticated_client.get("/api/controllers/meta-com/kit").status_code == 404


def test_mark_filed_via_transition(authenticated_client):
    created = authenticated_client.post("/api/controllers/meta-com/request").json()
    resp = authenticated_client.post(
        f"/api/requests/{created['request_id']}/transition",
        json={"action": "mark_sent"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"

    listing = authenticated_client.get("/api/controllers").json()
    meta = next(c for c in listing if c["id"] == "meta-com")
    assert meta["request"]["status"] == "sent"
    assert meta["request"]["deadline_at"] is not None


def test_email_viable_request_sends(authenticated_client):
    with patch(
        "backend.api.controllers.EmailSender.send", new_callable=AsyncMock
    ) as mock_send:
        mock_send.return_value = SenderResult(status=SenderStatus.SUCCESS, message="ok")
        resp = authenticated_client.post("/api/controllers/github-com/request")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "sent"
    assert mock_send.await_args.kwargs["to_email"] == "privacy@github.com"
    assert mock_send.await_args.kwargs["cc"] == ["dpo@github.com"]
    sent_text = mock_send.await_args.kwargs["rendered_text"]
    assert "GitHub B.V." in sent_text


def test_email_send_failure_leaves_request_created(authenticated_client):
    with patch(
        "backend.api.controllers.EmailSender.send", new_callable=AsyncMock
    ) as mock_send:
        mock_send.return_value = SenderResult(status=SenderStatus.FAILURE, message="boom")
        resp = authenticated_client.post("/api/controllers/github-com/request")
    assert resp.status_code == 502
    listing = authenticated_client.get("/api/controllers").json()
    github = next(c for c in listing if c["id"] == "github-com")
    assert github["request"]["status"] == "created"


def test_failed_send_can_be_retried(authenticated_client):
    with patch(
        "backend.api.controllers.EmailSender.send", new_callable=AsyncMock
    ) as mock_send:
        mock_send.return_value = SenderResult(status=SenderStatus.FAILURE, message="boom")
        assert authenticated_client.post("/api/controllers/github-com/request").status_code == 502
    with patch(
        "backend.api.controllers.EmailSender.send", new_callable=AsyncMock
    ) as mock_send:
        mock_send.return_value = SenderResult(status=SenderStatus.SUCCESS, message="ok")
        resp = authenticated_client.post("/api/controllers/github-com/request")
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"
    # the retry reused the failed request instead of creating a second one
    reqs = [
        r for r in authenticated_client.get("/api/requests").json()
        if r["broker_id"] == "github-com"
    ]
    assert len(reqs) == 1
    assert reqs[0]["status"] == "sent"


def test_send_from_account_email_mismatch_falls_back_to_kit(authenticated_client):
    # sample_smtp username (test@test.com) is not among profile emails
    # (test@example.com) — Reddit would reject an auto-send, so the request
    # must fall back to the manual kit instead of burning the one email shot.
    with patch(
        "backend.api.controllers.EmailSender.send", new_callable=AsyncMock
    ) as mock_send:
        resp = authenticated_client.post("/api/controllers/reddit-com/request")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "manual_action_needed"
    assert "account email" in data["reason"]
    mock_send.assert_not_awaited()


def test_request_detail_works_for_controller_request(authenticated_client):
    created = authenticated_client.post("/api/controllers/meta-com/request").json()
    resp = authenticated_client.get(f"/api/requests/{created['request_id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["broker"]["name"].startswith("Meta")
    assert data["broker"]["removal_method"] == "web_form"


def test_stats_broker_count_excludes_controllers(authenticated_client):
    from pathlib import Path

    from backend.core.broker import BrokerRegistry

    project_brokers = Path(__file__).parent.parent.parent / "brokers"
    expected = len(BrokerRegistry.load(project_brokers).brokers)
    stats = authenticated_client.get("/api/requests/stats").json()
    assert stats["broker_count"] == expected


def test_complaint_for_controller_routes_to_residence_dpa(authenticated_client):
    created = authenticated_client.post("/api/controllers/meta-com/request").json()
    rid = created["request_id"]
    authenticated_client.post(
        f"/api/requests/{rid}/transition", json={"action": "mark_sent"}
    )
    authenticated_client.post(
        f"/api/requests/{rid}/transition", json={"action": "mark_overdue"}
    )
    authenticated_client.post(
        f"/api/requests/{rid}/transition", json={"action": "mark_escalated"}
    )
    resp = authenticated_client.post(f"/api/blast/generate-complaint/{rid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dpa"]["short_name"] == "Datatilsynet"
    # Datatilsynet complaint renders in Danish, lead-SA paragraph included
    assert "IE DPC" in data["complaint_text"]
    assert "artikel 56" in data["complaint_text"]
    assert "Meta Platforms Ireland" in data["complaint_text"]
    # no follow-up was ever sent (form-only) — the complaint must not claim one
    assert "rykker" not in data["complaint_text"]
    assert "ikke modtaget noget materielt svar" in data["complaint_text"]


def test_controller_requests_show_names_in_requests_list(authenticated_client):
    authenticated_client.post("/api/controllers/meta-com/request")
    resp = authenticated_client.get("/api/requests")
    assert resp.status_code == 200
    meta_reqs = [r for r in resp.json() if r["broker_id"] == "meta-com"]
    assert meta_reqs and meta_reqs[0]["broker_name"].startswith("Meta")


def test_blast_excludes_controllers(authenticated_client):
    resp = authenticated_client.post(
        "/api/blast/create", json={"request_type": "erasure", "dry_run": True}
    )
    assert resp.status_code == 200
    broker_ids = {r["broker_id"] for r in resp.json()["requests"]}
    assert "meta-com" not in broker_ids
    assert "github-com" not in broker_ids
