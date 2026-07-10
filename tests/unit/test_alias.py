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
# Resolver — reuse-only mode (chases must never switch identity mid-thread)
# ---------------------------------------------------------------------------


async def test_reuse_only_returns_real_recipient_when_no_alias_exists():
    """No alias row means the original send went from the real mailbox
    (pre-alias request, carve-out, or SimpleLogin fallback). A chase must not
    mint a fresh identity mid-thread."""
    db = _session()
    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        to, alias = await resolve_recipient(
            db, "key", "spokeo-com", "dpo@spokeo.com", mint=False,
        )
    assert (to, alias) == ("dpo@spokeo.com", None)
    assert db.query(BrokerAlias).count() == 0
    sl_cls.assert_not_called()
    db.close()


async def test_reuse_only_uses_the_existing_alias():
    db = _session()
    db.add(BrokerAlias(
        broker_id="spokeo-com", alias_id=7, alias_email="abc@aleeas.com",
        reverse_alias_address="reply+x@sl.co",
    ))
    db.commit()
    to, alias = await resolve_recipient(
        db, "key", "spokeo-com", "dpo@spokeo.com", mint=False,
    )
    assert (to, alias) == ("reply+x@sl.co", "abc@aleeas.com")
    db.close()


async def test_disabled_alias_skips_new_sends_but_chases_go_to_real_recipient():
    """A NEW send (mint) must not resurrect a disabled alias — it returns the
    skip sentinel. A chase (mint=False) only reaches the resolver for a thread
    NOT sent via this alias (the scheduler suppresses aliased threads per
    request first), so it falls back to the real recipient. Neither path
    touches SimpleLogin or clears disabled_at."""
    db = _session()
    db.add(BrokerAlias(
        broker_id="spokeo-com", alias_id=7, alias_email="abc@aleeas.com",
        reverse_alias_address="reply+x@sl.co", disabled_at=datetime.now(UTC),
    ))
    db.commit()
    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        send = await resolve_recipient(db, "key", "spokeo-com", "dpo@spokeo.com")
        chase = await resolve_recipient(
            db, "key", "spokeo-com", "dpo@spokeo.com", mint=False,
        )
    assert send == (None, None)                     # new send: skip
    assert chase == ("dpo@spokeo.com", None)        # chase: real recipient
    sl_cls.assert_not_called()
    assert db.query(BrokerAlias).one().disabled_at is not None
    db.close()


async def test_existing_alias_is_reused_even_without_the_api_key():
    """Removing the SimpleLogin key must not switch identity on live threads:
    Settings promises "existing aliases keep working", and a chase from the
    real mailbox on an aliased thread is the exact leak fix 3.1 removed.
    Reuse is a DB lookup — it needs no API at all."""
    db = _session()
    db.add(BrokerAlias(
        broker_id="spokeo-com", alias_id=7, alias_email="abc@aleeas.com",
        reverse_alias_address="reply+x@sl.co",
    ))
    db.commit()

    to, alias = await resolve_recipient(db, None, "spokeo-com", "dpo@spokeo.com")
    assert (to, alias) == ("reply+x@sl.co", "abc@aleeas.com")
    to, alias = await resolve_recipient(
        db, None, "spokeo-com", "dpo@spokeo.com", mint=False,
    )
    assert (to, alias) == ("reply+x@sl.co", "abc@aleeas.com")
    db.close()


# ---------------------------------------------------------------------------
# Resolver — the stored contact must track the registry's dpo_email
# ---------------------------------------------------------------------------


async def test_changed_recipient_gets_a_new_contact_on_the_same_alias():
    """The reverse-alias is bound to the contact address at mint time. After
    `brokers update` corrects a DPO address, reuse must add a contact for the
    new address on the SAME alias (identity preserved; contact creation is
    idempotent upstream) — or mail keeps flowing to the dead address forever."""
    db = _session()
    db.add(BrokerAlias(
        broker_id="spokeo-com", alias_id=7, alias_email="abc@aleeas.com",
        reverse_alias_address="reply+old@sl.co", contact_id=41,
        recipient="privacy@spokeo.com",
    ))
    db.commit()

    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        inst = sl_cls.return_value
        inst.create_alias = AsyncMock()
        inst.create_reverse_alias = AsyncMock(return_value=(43, "reply+new@sl.co"))
        to, alias = await resolve_recipient(db, "key", "spokeo-com", "dpo@spokeo.com")

    inst.create_alias.assert_not_called()          # same alias, no re-mint
    assert inst.create_reverse_alias.await_args.args[1:] == (7, "dpo@spokeo.com")
    assert (to, alias) == ("reply+new@sl.co", "abc@aleeas.com")
    row = db.query(BrokerAlias).one()
    assert row.recipient == "dpo@spokeo.com"
    assert row.contact_id == 43
    assert row.reverse_alias_address == "reply+new@sl.co"
    db.close()


async def test_unchanged_recipient_makes_no_api_call():
    db = _session()
    db.add(BrokerAlias(
        broker_id="spokeo-com", alias_id=7, alias_email="abc@aleeas.com",
        reverse_alias_address="reply+x@sl.co", recipient="dpo@spokeo.com",
    ))
    db.commit()
    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        to, alias = await resolve_recipient(db, "key", "spokeo-com", "dpo@spokeo.com")
    sl_cls.assert_not_called()
    assert (to, alias) == ("reply+x@sl.co", "abc@aleeas.com")
    db.close()


async def test_legacy_row_without_recipient_heals_with_zero_network_io():
    """Pre-column rows have recipient NULL. Healing must NOT call SimpleLogin —
    a blanket contact call here fires on every legacy alias on the first
    post-migration blast (200 aliases * 20s timeout). Assume the existing
    contact is current and backfill the record for free."""
    db = _session()
    db.add(BrokerAlias(
        broker_id="spokeo-com", alias_id=7, alias_email="abc@aleeas.com",
        reverse_alias_address="reply+x@sl.co",
    ))
    db.commit()

    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        to, alias = await resolve_recipient(db, "key", "spokeo-com", "dpo@spokeo.com")

    sl_cls.assert_not_called()                          # zero I/O
    assert (to, alias) == ("reply+x@sl.co", "abc@aleeas.com")
    assert db.query(BrokerAlias).one().recipient == "dpo@spokeo.com"

    # Healed: a later reuse is a pure lookup too.
    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        await resolve_recipient(db, "key", "spokeo-com", "dpo@spokeo.com")
    sl_cls.assert_not_called()
    db.close()


async def test_contact_update_failure_falls_back_to_the_stored_reverse():
    """A failed contact update must not block the send — the stored reverse
    still reaches the OLD address, which beats not sending at all."""
    db = _session()
    db.add(BrokerAlias(
        broker_id="spokeo-com", alias_id=7, alias_email="abc@aleeas.com",
        reverse_alias_address="reply+old@sl.co", recipient="privacy@spokeo.com",
    ))
    db.commit()
    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        sl_cls.return_value.create_reverse_alias = AsyncMock(
            side_effect=AliasError("quota"),
        )
        to, alias = await resolve_recipient(db, "key", "spokeo-com", "dpo@spokeo.com")
    assert (to, alias) == ("reply+old@sl.co", "abc@aleeas.com")
    assert db.query(BrokerAlias).one().recipient == "privacy@spokeo.com"
    db.close()


async def test_chases_never_update_contacts_even_when_the_recipient_changed():
    """mint=False (and keyless) resolution is a pure DB lookup — a chase must
    not mutate SimpleLogin state mid-thread."""
    db = _session()
    db.add(BrokerAlias(
        broker_id="spokeo-com", alias_id=7, alias_email="abc@aleeas.com",
        reverse_alias_address="reply+old@sl.co", recipient="privacy@spokeo.com",
    ))
    db.commit()
    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        to1, _ = await resolve_recipient(
            db, "key", "spokeo-com", "dpo@spokeo.com", mint=False,
        )
        to2, _ = await resolve_recipient(db, None, "spokeo-com", "dpo@spokeo.com")
    sl_cls.assert_not_called()
    assert to1 == to2 == "reply+old@sl.co"
    db.close()


# ---------------------------------------------------------------------------
# Resolver — re-minting over a disabled row (UNIQUE broker_id)
# ---------------------------------------------------------------------------


async def test_disabled_alias_is_not_resurrected_by_a_send():
    """A send for a broker whose alias was deliberately disabled must NOT mint
    a fresh alias and clear disabled_at — that silently reverts the user's
    cut-off. It returns the skip sentinel; the caller declines to contact."""
    db = _session()
    db.add(BrokerAlias(
        broker_id="spokeo-com", alias_id=7, alias_email="old@aleeas.com",
        reverse_alias_address="reply+old@sl.co", contact_id=41,
        disabled_at=datetime.now(UTC),
    ))
    db.commit()

    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        result = await resolve_recipient(db, "key", "spokeo-com", "dpo@spokeo.com")

    assert result == (None, None)
    sl_cls.assert_not_called()
    row = db.query(BrokerAlias).one()
    assert row.disabled_at is not None          # still disabled
    assert row.alias_email == "old@aleeas.com"  # untouched
    db.close()


async def test_persist_failure_rolls_back_and_still_sends_via_the_alias():
    """A DB failure after a successful mint must neither poison the session
    for the rest of the blast nor leak the real mailbox — the alias exists
    upstream, so use it unpersisted."""
    from sqlalchemy.exc import OperationalError

    db = _session()
    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        inst = sl_cls.return_value
        inst.create_alias = AsyncMock(return_value=(7, "abc@aleeas.com"))
        inst.create_reverse_alias = AsyncMock(return_value=(42, "reply+x@sl.co"))
        with patch.object(
            db, "commit",
            side_effect=OperationalError("stmt", None, Exception("db locked")),
        ):
            to, alias = await resolve_recipient(db, "key", "spokeo-com", "dpo@spokeo.com")
        assert (to, alias) == ("reply+x@sl.co", "abc@aleeas.com")

        # The session survives: the next broker in the blast still resolves.
        inst.create_alias = AsyncMock(return_value=(9, "def@aleeas.com"))
        inst.create_reverse_alias = AsyncMock(return_value=(43, "reply+y@sl.co"))
        to2, alias2 = await resolve_recipient(db, "key", "krak-dk", "dpo@krak.dk")

    assert (to2, alias2) == ("reply+y@sl.co", "def@aleeas.com")
    assert db.query(BrokerAlias).count() == 1
    db.close()


async def test_persist_failure_returns_the_concurrent_winner():
    """Two concurrent resolves for the same broker both mint; the loser's
    commit hits UNIQUE(broker_id). It must adopt the winner's identity so
    both sends and all future reuse agree on ONE alias for the broker."""
    from sqlalchemy import insert
    from sqlalchemy.exc import OperationalError

    db = _session()
    engine = db.get_bind()

    def winner_lands_then_commit_fails():
        with engine.begin() as conn:
            conn.execute(insert(BrokerAlias).values(
                broker_id="spokeo-com", alias_id=99,
                alias_email="winner@aleeas.com",
                reverse_alias_address="reply+winner@sl.co",
                created_at=datetime.now(UTC),
            ))
        raise OperationalError("stmt", None, Exception("unique race"))

    with patch("backend.core.alias_resolver.SimpleLoginClient") as sl_cls:
        inst = sl_cls.return_value
        inst.create_alias = AsyncMock(return_value=(7, "loser@aleeas.com"))
        inst.create_reverse_alias = AsyncMock(return_value=(42, "reply+loser@sl.co"))
        with patch.object(db, "commit", side_effect=winner_lands_then_commit_fails):
            to, alias = await resolve_recipient(db, "key", "spokeo-com", "dpo@spokeo.com")

    assert (to, alias) == ("reply+winner@sl.co", "winner@aleeas.com")
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


def test_hyphenated_broker_domain_reply_is_not_a_leak():
    """data-axle.com slugifies to "data-axle-com"; naive slug reversal compares
    the sender against "data.axle.com" and brands the broker's own compliance
    reply a leak — a false accusation wired into Art. 77 complaint material."""
    from backend.core.imap import ImapConfig, ImapPoller

    db_factory = _make_db()
    db = db_factory()
    db.add(Request(
        id="req-axle-001", broker_id="data-axle-com",
        request_type=RequestType.ERASURE, status=RequestStatus.SENT,
        message_id="<req-axle-001@incognito.local>",
        sent_at=datetime.now(UTC), deadline_at=datetime.now(UTC),
    ))
    db.add(BrokerAlias(
        broker_id="data-axle-com", alias_id=8, alias_email="axl@aleeas.com",
        reverse_alias_address="reply+axl@simplelogin.co",
    ))
    db.commit()
    db.close()

    poller = ImapPoller(
        imap_config=ImapConfig(host="localhost", username="u", password="p"),
        db_session_factory=db_factory,
        broker_domains={"data-axle.com"},
        broker_id_domains={"data-axle-com": "data-axle.com"},
    )
    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("axl@aleeas.com",),
         "x-simplelogin-envelope-from": ("privacyteam@data-axle.com",)},
        from_="reply+garbage@simplelogin.co",
    )
    poller.process_message(msg)
    assert poller.leak_signals == []


def test_threaded_ticketing_reply_is_not_branded_a_leak():
    """The OneTrust/Zendesk class: brokers answer through DSAR-processor
    domains. Only the broker's own mail pipeline can quote our full outbound
    Message-ID (the subject REF code exposes just 8 of 32 hex chars), so a
    reply that threads to it is the broker speaking — not a leak."""
    from backend.core.imap import MatchTier

    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    msg = _msg(
        {"in-reply-to": ("<req-alias-001@incognito.local>",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("dsar-reply@zendesk.com",)},
        from_="reply+garbage@simplelogin.co",
    )
    result = poller.process_message(msg)

    assert poller.leak_signals == []
    assert result is not None
    assert result.tier == MatchTier.MESSAGE_ID
    req = db_factory().get(Request, "req-alias-001")
    assert req.status == RequestStatus.ACKNOWLEDGED   # the reply still ACKs


def test_second_threaded_reply_after_ack_is_not_a_leak():
    """The suppression must consult Message-IDs status-independently: after the
    first reply auto-ACKs, the request leaves the active-status maps, and a
    follow-up ticket email on the same thread must not be leak-branded."""
    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    db = db_factory()
    req = db.get(Request, "req-alias-001")
    req.status = RequestStatus.ACKNOWLEDGED
    db.commit()
    db.close()

    msg = _msg(
        {"in-reply-to": ("<req-alias-001@incognito.local>",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("dsar-reply@zendesk.com",)},
        from_="reply+garbage@simplelogin.co",
    )
    poller.process_message(msg)
    assert poller.leak_signals == []


def test_ref_code_reply_through_the_alias_still_auto_acknowledges():
    """alias.md: recover the real sender from the envelope header when present.
    Its load-bearing effect is tier-2: a fresh ticketing reply carrying our
    [REF-XXXXXXXX] with a broker-domain envelope-from must auto-ACK even though
    SimpleLogin rewrote the visible From: to a reverse-alias."""
    from backend.core.imap import ImapConfig, ImapPoller, MatchTier

    db_factory = _make_db()
    db = db_factory()
    db.add(Request(
        id="abcd1234-5678-4abc-9def-0123456789ab", broker_id="spokeo-com",
        request_type=RequestType.ERASURE, status=RequestStatus.SENT,
        message_id="<abcd1234-5678-4abc-9def-0123456789ab@incognito.local>",
        sent_at=datetime.now(UTC), deadline_at=datetime.now(UTC),
    ))
    db.add(BrokerAlias(
        broker_id="spokeo-com", alias_id=7, alias_email="abc@aleeas.com",
        reverse_alias_address="reply+x@simplelogin.co",
    ))
    db.commit()
    db.close()

    poller = ImapPoller(
        imap_config=ImapConfig(host="localhost", username="u", password="p"),
        db_session_factory=db_factory,
        broker_domains={"spokeo.com"},
    )
    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("dpo@spokeo.com",)},
        from_="reply+garbage@simplelogin.co",
        subject="Your request [REF-ABCD1234]",
    )
    result = poller.process_message(msg)

    assert result is not None
    assert result.tier == MatchTier.REFERENCE_CODE
    req = db_factory().get(Request, "abcd1234-5678-4abc-9def-0123456789ab")
    assert req.status == RequestStatus.ACKNOWLEDGED


def test_esp_broker_reply_that_threads_is_not_a_leak():
    """A genuine reply via an ESP has MAIL FROM at the ESP's bounce domain, so
    the envelope alone can't vouch for it. What CAN: it threads to our own
    outbound Message-ID (unspoofable). Threaded ESP mail is the broker, not a
    leak — and it still auto-ACKs via tier-1."""
    from backend.core.imap import MatchTier

    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    msg = _msg(
        {"in-reply-to": ("<req-alias-001@incognito.local>",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("bounce-77@sendgrid.net",)},
        from_="reply+garbage@simplelogin.co",
    )
    result = poller.process_message(msg)

    assert poller.leak_signals == []
    assert result is not None and result.tier == MatchTier.MESSAGE_ID


def test_unthreaded_esp_mail_is_flagged_not_auto_acknowledged():
    """The security-conservative choice: an ESP-domain sender we can't attribute
    (no threading) is treated as an unexpected sender to triage — NOT auto-ACKed
    off a spoofable From: header or a low-entropy REF code, which would silently
    stop the Art. 12(3) clock. A missed auto-file surfaces as a visible card,
    not a silently dropped reply."""
    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("bounce-77@sendgrid.net",)},
        from_="reply+garbage@simplelogin.co",
        subject="Your request [REF-REQALIA0]",
    )
    with patch("backend.core.notifier.notify"):
        result = poller.process_message(msg)

    assert len(poller.leak_signals) == 1        # unexpected-sender triage
    assert result is None                        # not filed onto the thread
    req = db_factory().get(Request, "req-alias-001")
    assert req.status == RequestStatus.SENT      # clock untouched


def test_spoofed_author_at_broker_domain_does_not_suppress_a_leak():
    """Regression guard for the review: the message From:/Original-From header
    is attacker-controlled. A spammer who bought the alias sets From:
    anything@spokeo.com while sending from their own server — the leak verdict
    keys on the SPF-checked envelope, so the spoof cannot hide the leak."""
    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("spammer@casino-spam.ru",),
         "x-simplelogin-original-from": ("dpo@spokeo.com",)},   # forged
        from_="reply+garbage@simplelogin.co",
    )
    with patch("backend.core.notifier.notify"):
        result = poller.process_message(msg)

    assert len(poller.leak_signals) == 1
    assert poller.leak_signals[0]["sender"] == "spammer@casino-spam.ru"
    assert result is None                        # not filed as broker reply


def test_cross_broker_spam_is_not_filed_onto_the_other_brokers_thread():
    """Broker B buys A's list and spams the alias minted for A. B has its own
    active request, so tier-3 domain matching WOULD file this onto B's legal
    thread — pollution the user might attach to a DPA complaint. The alias is
    the authority for aliased mail, so tier-3 is off: it's a leak against A and
    nothing else."""
    from backend.core.imap import ImapConfig, ImapPoller
    from backend.db.models import EmailMessage as EmailMsg

    db_factory = _make_db()
    db = db_factory()
    db.add(Request(
        id="req-broker-b-01", broker_id="brokerb-com",
        request_type=RequestType.ERASURE, status=RequestStatus.SENT,
        message_id="<req-broker-b-01@incognito.local>",
        sent_at=datetime.now(UTC), deadline_at=datetime.now(UTC),
    ))
    db.add(Request(
        id="req-broker-a-01", broker_id="spokeo-com",
        request_type=RequestType.ERASURE, status=RequestStatus.SENT,
        message_id="<req-broker-a-01@incognito.local>",
        sent_at=datetime.now(UTC), deadline_at=datetime.now(UTC),
    ))
    db.add(BrokerAlias(
        broker_id="spokeo-com", alias_id=7, alias_email="abc@aleeas.com",
        reverse_alias_address="reply+x@simplelogin.co",
    ))
    db.commit()
    db.close()

    poller = ImapPoller(
        imap_config=ImapConfig(host="localhost", username="u", password="p"),
        db_session_factory=db_factory,
        broker_domains={"spokeo.com", "brokerb.com"},
        broker_id_domains={"spokeo-com": "spokeo.com", "brokerb-com": "brokerb.com"},
    )
    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("sales@brokerb.com",)},
        from_="reply+garbage@simplelogin.co",
    )
    with patch("backend.core.notifier.notify"):
        result = poller.process_message(msg)

    assert result is None                              # not filed anywhere
    assert poller.leak_signals[0]["broker_id"] == "spokeo-com"
    db = db_factory()
    assert db.query(EmailMsg).filter_by(request_id="req-broker-b-01").count() == 0


def test_leak_exposure_is_triage_not_an_accusation():
    """The signal proves an unexpected sender, not culpability — 'leaked or
    sold' language would flow straight into Art. 77 complaint material."""
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

    row = db_factory().query(ScanResult).filter_by(source="alias_leak").one()
    import json as _json
    data = _json.loads(row.found_data)
    assert "leaked or sold" not in data["title"]
    assert "nexpected sender" in data["title"]
    assert data["sender"] == "promo@casino-spam.ru"    # full evidence kept


def test_migrated_leak_key_does_not_resurrect_a_dismissed_leak():
    """The dedup key moved from mailto:<full-sender> to mailto:<domain>. A
    pre-upgrade dismissed leak (keyed on the full address) must be rewritten to
    the domain key by the migration, or the first post-upgrade poll re-mints it
    as a fresh needs_triage row. Simulate the rewritten row and reprocess."""
    import json as _json

    from backend.db.models import ScanResult

    db_factory = _make_db()
    db = db_factory()
    # A migrated row: url already rewritten to the domain form, disposition kept.
    db.add(ScanResult(
        source="alias_leak", broker_id="spokeo-com",
        found_data=_json.dumps({
            "broker_domain": "spokeo-com",
            "url": "mailto:casino-spam.ru",
            "sender": "bounce-1@casino-spam.ru",
            "title": "Unexpected sender on the alias for spokeo-com",
        }),
        disposition="dismissed", actioned=True,
    ))
    db.commit()
    db.close()

    poller = _poller_with_alias(db_factory)
    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",),
         "x-simplelogin-envelope-from": ("bounce-2@casino-spam.ru",)},
        from_="reply+garbage@simplelogin.co",
    )
    with patch("backend.core.notifier.notify"):
        poller.process_message(msg)

    rows = db_factory().query(ScanResult).filter_by(source="alias_leak").all()
    assert len(rows) == 1                       # refreshed, not resurrected
    assert rows[0].disposition == "dismissed"


def test_verp_spam_dedupes_to_one_exposure_per_sender_domain():
    """VERP campaigns vary the local part per message; keying the exposure on
    the full address would mint a fresh row + notification per spam mail and
    resurrect dismissals."""
    from backend.db.models import ScanResult

    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    for local in ("bounce-1", "bounce-2"):
        msg = _msg(
            {"in-reply-to": ("",), "references": ("",),
             "x-simplelogin-envelope-to": ("abc@aleeas.com",),
             "x-simplelogin-envelope-from": (f"{local}@casino-spam.ru",)},
            from_="reply+garbage@simplelogin.co",
        )
        with patch("backend.core.notifier.notify"):
            poller.process_message(msg)

    rows = db_factory().query(ScanResult).filter_by(source="alias_leak").all()
    assert len(rows) == 1


def test_reprocessed_leak_mail_does_not_duplicate_the_signal():
    """Leak mail is left unread, so every poll re-processes it — the in-memory
    signal list must not grow a duplicate per cycle."""
    db_factory = _make_db()
    poller = _poller_with_alias(db_factory)

    hdrs = {"in-reply-to": ("",), "references": ("",),
            "x-simplelogin-envelope-to": ("abc@aleeas.com",),
            "x-simplelogin-envelope-from": ("promo@casino-spam.ru",)}
    with patch("backend.core.notifier.notify"):
        poller.process_message(_msg(hdrs, from_="reply+g@simplelogin.co"))
        poller.process_message(_msg(hdrs, from_="reply+g@simplelogin.co"))

    assert len(poller.leak_signals) == 1


def test_alias_tier_files_onto_the_most_recent_active_request():
    """One broker can hold several active requests (erasure + access). The
    alias identifies the broker, not the thread — file onto the newest active
    request instead of whichever the query returned first."""
    from datetime import timedelta

    from backend.core.imap import ImapConfig, ImapPoller, MatchTier

    db_factory = _make_db()
    db = db_factory()
    old = Request(
        id="req-old-0001", broker_id="spokeo-com",
        request_type=RequestType.ACCESS, status=RequestStatus.SENT,
        message_id="<req-old-0001@incognito.local>",
        sent_at=datetime.now(UTC) - timedelta(days=40),
        deadline_at=datetime.now(UTC),
    )
    new = Request(
        id="req-new-0002", broker_id="spokeo-com",
        request_type=RequestType.ERASURE, status=RequestStatus.SENT,
        message_id="<req-new-0002@incognito.local>",
        sent_at=datetime.now(UTC),
        deadline_at=datetime.now(UTC),
    )
    db.add(old)
    db.add(new)
    db.add(BrokerAlias(
        broker_id="spokeo-com", alias_id=7, alias_email="abc@aleeas.com",
        reverse_alias_address="reply+x@simplelogin.co",
    ))
    db.commit()
    db.close()

    poller = ImapPoller(
        imap_config=ImapConfig(host="localhost", username="u", password="p"),
        db_session_factory=db_factory,
        broker_domains={"spokeo.com"},
    )
    msg = _msg(
        {"in-reply-to": ("",), "references": ("",),
         "x-simplelogin-envelope-to": ("abc@aleeas.com",)},
        from_="reply+garbage@simplelogin.co",
    )
    result = poller.process_message(msg)

    assert result is not None
    assert result.tier == MatchTier.ALIAS
    assert result.request_id == "req-new-0002"


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
