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


def test_edpb_cef_cited_only_when_controller_refused(authenticated_client):
    """EDPB CEF-2025 findings rebut a refusal — citing them against silence
    would be a non-sequitur in a real Art. 77 complaint."""
    created = authenticated_client.post("/api/controllers/meta-com/request").json()
    rid = created["request_id"]
    authenticated_client.post(f"/api/requests/{rid}/transition", json={"action": "mark_sent"})

    # overdue (silence), not refused -> no EDPB block
    authenticated_client.post(f"/api/requests/{rid}/transition", json={"action": "mark_overdue"})
    authenticated_client.post(f"/api/requests/{rid}/transition", json={"action": "mark_escalated"})
    resp = authenticated_client.post(f"/api/blast/generate-complaint/{rid}")
    assert "10. februar 2026" not in resp.json()["complaint_text"]

    # now a refusal -> EDPB block appears
    created2 = authenticated_client.post("/api/controllers/x-com/request").json()
    rid2 = created2["request_id"]
    authenticated_client.post(f"/api/requests/{rid2}/transition", json={"action": "mark_sent"})
    authenticated_client.post(
        f"/api/requests/{rid2}/transition",
        json={"action": "mark_acknowledged", "details": "ack"},
    )
    authenticated_client.post(
        f"/api/requests/{rid2}/transition",
        json={"action": "mark_refused", "details": "Art. 17(3)(b) applies"},
    )
    authenticated_client.post(f"/api/requests/{rid2}/transition", json={"action": "mark_escalated"})
    resp2 = authenticated_client.post(f"/api/blast/generate-complaint/{rid2}")
    text2 = resp2.json()["complaint_text"]
    assert "10. februar 2026" in text2          # EDPB CEF report date
    assert "anonymisering" in text2.lower()


def test_procedural_regulation_line_is_date_and_scope_gated(authenticated_client):
    """Reg (EU) 2025/2518 applies only to cross-border processing and only to
    complaints lodged on/after 2027-04-02 (Art. 36 + 37(2))."""
    from datetime import date
    from unittest.mock import patch

    created = authenticated_client.post("/api/controllers/meta-com/request").json()
    rid = created["request_id"]
    for action in ("mark_sent", "mark_overdue", "mark_escalated"):
        authenticated_client.post(f"/api/requests/{rid}/transition", json={"action": action})

    # today (pre-2027) -> absent
    resp = authenticated_client.post(f"/api/blast/generate-complaint/{rid}")
    assert "2025/2518" not in resp.json()["complaint_text"]

    # on/after the application date, for an IE-lead cross-border controller -> present
    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2027, 4, 2)

    with patch("backend.api.blast._date", FakeDate):
        resp = authenticated_client.post(f"/api/blast/generate-complaint/{rid}")
    text = resp.json()["complaint_text"]
    assert "2025/2518" in text
    assert "15 måneder" in text


def test_edpb_block_absent_when_controller_only_acknowledged(authenticated_client):
    """An acknowledgement sets response_body too. Keying the EDPB block on it
    would make the complaint assert the controller 'relies on an exception
    under Art. 17(3)' when they merely replied 'we received your request' —
    a false statement of fact in an Art. 77 filing."""
    created = authenticated_client.post("/api/controllers/meta-com/request").json()
    rid = created["request_id"]
    authenticated_client.post(f"/api/requests/{rid}/transition", json={"action": "mark_sent"})
    authenticated_client.post(
        f"/api/requests/{rid}/transition",
        json={"action": "mark_acknowledged", "details": "We have received your request."},
    )
    # then they go silent and it escalates
    authenticated_client.post(
        f"/api/requests/{rid}/transition", json={"action": "mark_completed"}
    )

    # rebuild an escalated-after-acknowledgement path via a second controller
    created2 = authenticated_client.post("/api/controllers/x-com/request").json()
    rid2 = created2["request_id"]
    authenticated_client.post(f"/api/requests/{rid2}/transition", json={"action": "mark_sent"})
    authenticated_client.post(
        f"/api/requests/{rid2}/transition",
        json={"action": "mark_acknowledged", "details": "Received, we are looking into it."},
    )
    authenticated_client.post(
        f"/api/requests/{rid2}/transition", json={"action": "mark_manual_action_needed"}
    )

    resp = authenticated_client.post(f"/api/blast/generate-complaint/{rid2}")
    text = resp.json()["complaint_text"]
    assert "10. februar 2026" not in text   # no EDPB rebuttal
    assert "artikel 17, stk. 3" not in text  # no "relies on an exception" claim


# ---------------------------------------------------------------------------
# Alias track wiring (see docs/tracks/alias.md)
# ---------------------------------------------------------------------------


def _enable_aliasing(client):
    assert client.post(
        "/api/settings/simplelogin", json={"api_key": "sl-key"}
    ).status_code == 200


def _fake_simplelogin():
    sl = patch("backend.core.alias_resolver.SimpleLoginClient")
    m = sl.start()
    m.return_value.create_alias = AsyncMock(return_value=(7, "abc@aleeas.com"))
    m.return_value.create_reverse_alias = AsyncMock(
        return_value=(42, "reply+x@simplelogin.co")
    )
    return sl


def test_controller_send_goes_to_the_reverse_alias(authenticated_client):
    """amazon-de has no CC and no account-email requirement — it gets an alias,
    so eu-privacy@amazon.de never learns the real mailbox."""
    _enable_aliasing(authenticated_client)
    sl = _fake_simplelogin()
    try:
        with patch(
            "backend.api.controllers.EmailSender.send", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = SenderResult(status=SenderStatus.SUCCESS, message="ok")
            resp = authenticated_client.post("/api/controllers/amazon-de/request")
    finally:
        sl.stop()

    assert resp.status_code == 200
    assert mock_send.await_args.kwargs["to_email"] == "reply+x@simplelogin.co"


def test_cc_controllers_are_not_aliased(authenticated_client):
    """github-com CCs dpo@github.com. A reverse-alias delivers only to its one
    contact, so the CC would be served straight from the real mailbox — which
    leaks the address the alias exists to hide. Don't alias; send as before."""
    _enable_aliasing(authenticated_client)
    sl = _fake_simplelogin()
    try:
        with patch(
            "backend.api.controllers.EmailSender.send", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = SenderResult(status=SenderStatus.SUCCESS, message="ok")
            resp = authenticated_client.post("/api/controllers/github-com/request")
    finally:
        sl.stop()

    assert resp.status_code == 200
    assert mock_send.await_args.kwargs["to_email"] == "privacy@github.com"


def test_no_simplelogin_key_means_unchanged_sending(authenticated_client):
    with patch(
        "backend.api.controllers.EmailSender.send", new_callable=AsyncMock
    ) as mock_send:
        mock_send.return_value = SenderResult(status=SenderStatus.SUCCESS, message="ok")
        resp = authenticated_client.post("/api/controllers/amazon-de/request")
    assert resp.status_code == 200
    assert mock_send.await_args.kwargs["to_email"] == "eu-privacy@amazon.de"
