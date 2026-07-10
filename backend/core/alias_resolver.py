"""Resolve the address to actually SMTP for a given recipient.

With aliasing enabled, each broker gets its own alias and we send to that
broker's reverse-alias; SimpleLogin rewrites the sender so the broker only ever
sees the alias. Without a key configured, nothing changes.

Carve-out: platforms that require the request to come from the account's own
verified address (Reddit) must never be aliased — they reject anything else.
The controller registry already carries `send_from_account_email` for this.
"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy.exc import SQLAlchemyError

from backend.core.alias import AliasError, SimpleLoginClient
from backend.db.models import BrokerAlias

log = logging.getLogger("incognito.alias_resolver")


async def resolve_recipient(
    db,
    api_key: str | None,
    broker_id: str,
    recipient: str,
    *,
    allow_alias: bool = True,
    mint: bool = True,
) -> tuple[str | None, str | None]:
    """Return (smtp_to_address, alias_email_or_None).

    Returns **(None, None) to mean "do not send"** — the broker's alias was
    deliberately disabled (a leak cut-off). Contacting it via the real mailbox
    would hand a proven-leaky recipient the very address the alias hid, and
    silently re-minting would revert the user's decision. Callers must skip.

    Falls back to the real recipient on any SimpleLogin failure — an erasure
    request going out from the real mailbox is far better than one not going
    out at all.

    `mint=False` is reuse-only, for follow-ups/escalations: a chase must use
    the same sending identity as the original send. Minting mid-thread would
    switch identity on the broker (or on a delisting engine the user filed
    with from their own mail client) and orphan the conversation.

    Reuse needs no API key: sending TO a reverse-alias is plain SMTP, and
    SimpleLogin keeps forwarding regardless of what keys we hold. Removing
    the key must stop new minting, not switch identity on live threads.
    """
    if not allow_alias:
        return recipient, None

    existing = (
        db.query(BrokerAlias).filter(BrokerAlias.broker_id == broker_id).first()
    )
    if existing is not None and existing.disabled_at is not None:
        if mint:
            # A NEW send must not resurrect a deliberately disabled alias —
            # that would silently revert the user's cut-off. Skip.
            return None, None
        # A chase (mint=False) only reaches here for a thread NOT sent through
        # this alias: the scheduler suppresses genuinely-aliased threads per
        # request (their outbound recorded the alias as sender) before calling
        # us. So fall back to the real recipient for the real-mailbox thread.
        return recipient, None
    if existing is not None:
        if existing.recipient is None:
            # Pre-column row: assume the existing contact is current and heal
            # the record with zero network I/O. A blanket API call here would
            # fire on EVERY legacy alias on the first post-migration blast.
            try:
                existing.recipient = recipient
                db.commit()
            except SQLAlchemyError:
                db.rollback()
        elif mint and api_key and existing.recipient != recipient:
            # The reverse-alias is bound to the contact address it was minted
            # for. When the registry's dpo_email moves (brokers update), add a
            # contact for the new address on the SAME alias — identity
            # preserved, mail reaches the current address. Contact creation is
            # idempotent upstream (200 + existed=true).
            client = SimpleLoginClient(api_key)
            try:
                async with httpx.AsyncClient() as http:
                    contact_id, reverse = await client.create_reverse_alias(
                        http, existing.alias_id, recipient
                    )
            except (AliasError, httpx.HTTPError) as exc:
                # The stored reverse still reaches the OLD address, which
                # beats not sending at all.
                log.warning(
                    "Contact update failed for %s (%s) — using the stored "
                    "reverse-alias", broker_id, exc,
                )
                return existing.reverse_alias_address, existing.alias_email
            try:
                existing.contact_id = contact_id or None
                existing.reverse_alias_address = reverse
                existing.recipient = recipient
                db.commit()
            except SQLAlchemyError:
                db.rollback()
            return reverse, existing.alias_email
        return existing.reverse_alias_address, existing.alias_email
    if not api_key or not mint:
        return recipient, None

    client = SimpleLoginClient(api_key)
    try:
        async with httpx.AsyncClient() as http:
            alias_id, alias_email = await client.create_alias(
                http, note=f"incognito: {broker_id}"
            )
            contact_id, reverse = await client.create_reverse_alias(
                http, alias_id, recipient
            )
    except (AliasError, httpx.HTTPError) as exc:
        log.warning(
            "Alias creation failed for %s (%s) — sending from the real mailbox",
            broker_id, exc,
        )
        return recipient, None

    try:
        # existing is always None here: enabled rows returned above, disabled
        # rows returned the skip sentinel — so this is a fresh INSERT.
        db.add(BrokerAlias(
            broker_id=broker_id,
            alias_id=alias_id,
            alias_email=alias_email,
            reverse_alias_address=reverse,
            contact_id=contact_id or None,
            recipient=recipient,
        ))
        db.commit()
    except SQLAlchemyError as exc:
        # A dirty session here would poison every later broker in the blast.
        db.rollback()
        # UNIQUE violation usually means a concurrent resolve won the race —
        # adopt its identity so all sends and future reuse agree on ONE alias.
        winner = (
            db.query(BrokerAlias).filter(BrokerAlias.broker_id == broker_id).first()
        )
        if winner is not None and winner.disabled_at is None:
            return winner.reverse_alias_address, winner.alias_email
        # Genuine persistence failure: the alias exists upstream, so still
        # send through it — only reuse and ALIAS-tier matching degrade.
        log.warning(
            "Could not persist alias %s for %s (%s) — using it unpersisted",
            alias_email, broker_id, exc,
        )
        return reverse, alias_email
    log.info("Minted alias %s for %s", alias_email, broker_id)
    return reverse, alias_email
