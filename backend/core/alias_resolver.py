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
) -> tuple[str, str | None]:
    """Return (smtp_to_address, alias_email_or_None).

    Falls back to the real recipient on any SimpleLogin failure — an erasure
    request going out from the real mailbox is far better than one not going
    out at all.
    """
    if not api_key or not allow_alias:
        return recipient, None

    existing = (
        db.query(BrokerAlias).filter(BrokerAlias.broker_id == broker_id).first()
    )
    if existing is not None and existing.disabled_at is None:
        return existing.reverse_alias_address, existing.alias_email

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

    db.add(BrokerAlias(
        broker_id=broker_id,
        alias_id=alias_id,
        alias_email=alias_email,
        reverse_alias_address=reverse,
        contact_id=contact_id or None,
    ))
    db.commit()
    log.info("Minted alias %s for %s", alias_email, broker_id)
    return reverse, alias_email
