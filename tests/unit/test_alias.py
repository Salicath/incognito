"""Alias track — SimpleLogin client, resolver, IMAP alias matching, leak signal."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.core.alias import (
    AliasError,
    SimpleLoginClient,
    alias_from_headers,
    original_sender_from_headers,
)
from backend.core.alias_resolver import resolve_recipient
from backend.db.models import (
    Base,
    BrokerAlias,
    EmailMessage,
    Request,
    RequestStatus,
    RequestType,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _Client:
    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._responses.pop(0)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


async def test_create_alias_and_reverse_alias():
    sl = SimpleLoginClient("key123")
    client = _Client(
        _Resp(payload={"id": 7, "alias": "abc@aleeas.com"}),
        _Resp(payload={"id": 42, "reverse_alias_address": "reply+x@sl.co"}),
    )
    alias_id, alias_email = await sl.create_alias(client, note="incognito: spokeo-com")
    assert (alias_id, alias_email) == (7, "abc@aleeas.com")

    contact_id, reverse = await sl.create_reverse_alias(client, 7, "dpo@spokeo.com")
    assert (contact_id, reverse) == (42, "reply+x@sl.co")

    # SimpleLogin uses a bare "Authentication" header, not "Authorization"
    _, kwargs = client.calls[0]
    assert kwargs["headers"]["Authentication"] == "key123"
    assert client.calls[1][0].endswith("/api/aliases/7/contacts")


async def test_free_plan_403_is_a_clear_error():
    sl = SimpleLoginClient("key")
    client = _Client(_Resp(status_code=403))
    with pytest.raises(AliasError, match="Premium"):
        await sl.create_alias(client, note="x")


async def test_bad_key_401():
    sl = SimpleLoginClient("nope")
    client = _Client(_Resp(status_code=401))
    with pytest.raises(AliasError, match="API key"):
        await sl.create_alias(client, note="x")


# ---------------------------------------------------------------------------
# Header parsing — the load-bearing detail
# ---------------------------------------------------------------------------


def test_envelope_to_is_the_reliable_hook():
    # X-SimpleLogin-Envelope-To is set unconditionally by SimpleLogin
    hdrs = {"x-simplelogin-envelope-to": ("Abc@Aleeas.com",)}
    assert alias_from_headers(hdrs) == "abc@aleeas.com"


def test_envelope_from_is_optional_enrichment():
    """Envelope-From only exists if the user enabled include_header_email_header.
    Depending on it would work locally and silently fail on a real mailbox."""
    assert original_sender_from_headers({}) is None
    assert original_sender_from_headers({"x-simplelogin-envelope-to": ("a@b.c",)}) is None
    hdrs = {"x-simplelogin-envelope-from": ("dpo@spokeo.com",)}
    assert original_sender_from_headers(hdrs) == "dpo@spokeo.com"


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


async def test_no_key_means_unchanged_behaviour():
    db = _session()
    to, alias = await resolve_recipient(db, None, "spokeo-com", "dpo@spokeo.com")
    assert (to, alias) == ("dpo@spokeo.com", None)
    assert db.query(BrokerAlias).count() == 0
    db.close()


async def test_send_from_account_email_platforms_are_never_aliased():
    """Reddit rejects requests not sent from the account's verified address."""
    db = _session()
    to, alias = await resolve_recipient(
        db, "key", "reddit-com", "redditdatarequests@reddit.com", allow_alias=False,
    )
    assert to == "redditdatarequests@reddit.com"
    assert alias is None
    assert db.query(BrokerAlias).count() == 0
    db.close()


async def test_alias_minted_once_and_reused():
    db = _session()
    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        inst = sl_cls.return_value
        inst.create_alias = AsyncMock(return_value=(7, "abc@aleeas.com"))
        inst.create_reverse_alias = AsyncMock(return_value=(42, "reply+x@sl.co"))

        to1, alias1 = await resolve_recipient(db, "key", "spokeo-com", "dpo@spokeo.com")
        to2, alias2 = await resolve_recipient(db, "key", "spokeo-com", "dpo@spokeo.com")

    assert to1 == to2 == "reply+x@sl.co"
    assert alias1 == alias2 == "abc@aleeas.com"
    assert db.query(BrokerAlias).count() == 1          # not re-minted
    assert inst.create_alias.await_count == 1
    db.close()


async def test_simplelogin_failure_falls_back_to_real_recipient():
    """An erasure request sent from the real mailbox beats one never sent."""
    db = _session()
    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        sl_cls.return_value.create_alias = AsyncMock(side_effect=AliasError("down"))
        to, alias = await resolve_recipient(db, "key", "spokeo-com", "dpo@spokeo.com")
    assert to == "dpo@spokeo.com"
    assert alias is None
    assert db.query(BrokerAlias).count() == 0
    db.close()


async def test_httpx_error_also_falls_back():
    db = _session()
    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        sl_cls.return_value.create_alias = AsyncMock(side_effect=httpx.ConnectError("x"))
        to, _ = await resolve_recipient(db, "key", "spokeo-com", "dpo@spokeo.com")
    assert to == "dpo@spokeo.com"
    db.close()


# ---------------------------------------------------------------------------
# IMAP: ALIAS match tier + leak signal
# ---------------------------------------------------------------------------


def _poller_with_alias(db_factory, *, broker_id="spokeo-com"):
    from backend.core.imap import ImapConfig, ImapPoller

    db = db_factory()
    db.add(Request(
        id="req-alias-001",
        broker_id=broker_id,
        request_type=RequestType.ERASURE,
        status=RequestStatus.SENT,
        message_id="<req-alias-001@incognito.local>",
        sent_at=datetime.now(UTC),
        deadline_at=datetime.now(UTC),
    ))
    db.add(BrokerAlias(
        broker_id=broker_id,
        alias_id=7,
        alias_email="abc@aleeas.com",
        reverse_alias_address="reply+x@simplelogin.co",
    ))
    db.commit()
    db.close()

    return ImapPoller(
        imap_config=ImapConfig(host="localhost", username="u", password="p"),
        db_session_factory=db_factory,
        broker_domains={"spokeo.com"},
    )


def _msg(headers, from_, subject="Re: your request", text="ok"):
    m = MagicMock()
    m.headers = headers
    m.subject = subject
    m.from_ = from_
    m.to = ("abc@aleeas.com",)
    m.text = text
    m.date = datetime.now(UTC)
    m.uid = "1"
    return m


def test_alias_tier_matches_when_sender_is_unrecognisable():
    """The SimpleLogin forward hides the broker behind a reverse-alias.
    Only the alias identifies the request."""
    from backend.core.imap import MatchTier

    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",)},
        from_="reply+garbage@simplelogin.co",
    )
    result = poller.process_message(msg)

    assert result is not None
    assert result.tier == MatchTier.ALIAS
    assert result.request_id == "req-alias-001"

    # The reply is filed against the thread...
    db = db_factory()
    emails = db.query(EmailMessage).filter_by(request_id="req-alias-001").all()
    assert len(emails) == 1


def test_alias_tier_does_not_auto_acknowledge():
    """An alias match proves WHICH request, not that the broker replied.

    With the envelope headers off, spam delivered to the alias is
    indistinguishable from a broker reply. Auto-acknowledging would stop the
    Art. 12(3) clock on the strength of a spam message. Same reasoning as
    DOMAIN_ONLY and the Bing delisting decisions: file it, let the user judge.
    """
    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",)},
        from_="reply+garbage@simplelogin.co",
    )
    poller.process_message(msg)

    req = db_factory().get(Request, "req-alias-001")
    assert req.status == RequestStatus.SENT
    assert req.response_at is None


def test_ordinary_broker_reply_is_not_flagged_as_a_leak():
    """Regression: without the opt-in envelope-from header the From: is a
    SimpleLogin reverse-alias. Judging leakage off that domain would brand
    every legitimate broker reply as a resale."""
    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",)},
        from_="reply+garbage@simplelogin.co",
    )
    poller.process_message(msg)

    assert poller.leak_signals == []


def test_broker_reply_with_envelope_from_is_not_a_leak():
    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("dpo@spokeo.com",)},
        from_="reply+garbage@simplelogin.co",
    )
    poller.process_message(msg)
    assert poller.leak_signals == []


def test_subdomain_of_the_broker_is_not_a_leak():
    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("noreply@mail.spokeo.com",)},
        from_="reply+garbage@simplelogin.co",
    )
    poller.process_message(msg)
    assert poller.leak_signals == []


def test_unrelated_sender_on_a_broker_alias_is_a_leak_signal():
    """The whole point of the alias: only spokeo-com ever knew this address."""
    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("promo@casino-spam.ru",)},
        from_="reply+garbage@simplelogin.co",
        subject="You won!",
    )
    result = poller.process_message(msg)

    assert poller.leak_signals == [{
        "alias": "abc@aleeas.com",
        "broker_id": "spokeo-com",
        "sender": "promo@casino-spam.ru",
    }]

    # Regression: the alias tier must not claim this spam as a broker reply.
    # If it does, the leak is silently refiled as correspondence on the request.
    assert result is None
    db = db_factory()
    assert db.query(EmailMessage).filter_by(request_id="req-alias-001").count() == 0


def test_lookalike_domain_is_still_a_leak():
    """spokeo.com.evil.ru must not pass the suffix check."""
    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("x@spokeo.com.evil.ru",)},
        from_="reply+garbage@simplelogin.co",
    )
    poller.process_message(msg)
    assert len(poller.leak_signals) == 1


def test_leak_signals_are_bounded():
    from backend.core.imap import _MAX_LEAK_SIGNALS

    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)
    poller.leak_signals = [{"x": i} for i in range(_MAX_LEAK_SIGNALS)]

    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("promo@casino-spam.ru",)},
        from_="reply+garbage@simplelogin.co",
    )
    poller.process_message(msg)
    assert len(poller.leak_signals) == _MAX_LEAK_SIGNALS


def test_leak_is_filed_as_an_exposure_for_triage():
    from backend.db.models import ScanResult

    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("promo@casino-spam.ru",)},
        from_="reply+garbage@simplelogin.co",
    )
    with patch("backend.core.notifier.notify"):
        poller.process_message(msg)

    rows = db_factory().query(ScanResult).filter_by(source="alias_leak").all()
    assert len(rows) == 1
    assert rows[0].broker_id == "spokeo-com"
    assert rows[0].disposition is None          # lands in the triage inbox


def test_repeat_spam_does_not_resurrect_a_dismissed_leak():
    from backend.db.models import ScanResult

    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)
    hdrs = {"in-reply-to": ("",), "references": ("",),
            "x-simplelogin-envelope-to": ("abc@aleeas.com",),
            "x-simplelogin-envelope-from": ("promo@casino-spam.ru",)}

    with patch("backend.core.notifier.notify"):
        poller.process_message(_msg(hdrs, from_="reply+g@simplelogin.co"))

    db = db_factory()
    row = db.query(ScanResult).filter_by(source="alias_leak").one()
    row.disposition = "dismissed"
    db.commit()

    with patch("backend.core.notifier.notify"):
        poller.process_message(_msg(hdrs, from_="reply+g@simplelogin.co"))

    rows = db_factory().query(ScanResult).filter_by(source="alias_leak").all()
    assert len(rows) == 1
    assert rows[0].disposition == "dismissed"


def test_recording_failure_does_not_lose_the_message():
    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    with patch(
        "backend.core.rescan.save_scan_results", side_effect=RuntimeError("db down")
    ):
        msg = _msg(
            {"in-reply-to": ("",), "references": ("",),
             "x-simplelogin-envelope-to": ("abc@aleeas.com",),
             "x-simplelogin-envelope-from": ("promo@casino-spam.ru",)},
            from_="reply+garbage@simplelogin.co",
        )
        poller.process_message(msg)   # must not raise

    assert len(poller.leak_signals) == 1
