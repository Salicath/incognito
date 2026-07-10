"""SimpleLogin alias client — a distinct sending identity per recipient.

Every Art. 17 email used to carry the user's real mailbox to 228 brokers. An
alias per broker removes that disclosure and turns any inbound spam into
evidence of which broker leaked the address. See docs/tracks/alias.md.

Sending *as* an alias is not direct SMTP: SimpleLogin issues a per-contact
"reverse alias" and rewrites mail sent to it. Endpoints and auth header
verified against the SimpleLogin source, 2026-07-09.
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger("incognito.alias")

SIMPLELOGIN_API = "https://app.simplelogin.io"

# Headers SimpleLogin stamps on forwarded mail. Envelope-To is unconditional;
# Envelope-From only when the user enables include_header_email_header, so it is
# enrichment, never a dependency. Envelope-From carries the SMTP MAIL FROM,
# which SimpleLogin SPF-checks at receipt — far harder to forge than the
# message From: header, so it is what security decisions key on. (The spoofable
# Original-From header is deliberately not consumed.)
HDR_ENVELOPE_TO = "x-simplelogin-envelope-to"
HDR_ENVELOPE_FROM = "x-simplelogin-envelope-from"
HDR_TYPE = "x-simplelogin-type"


class AliasError(RuntimeError):
    """SimpleLogin rejected the request (bad key, free plan, quota)."""


class SimpleLoginClient:
    def __init__(self, api_key: str, base_url: str = SIMPLELOGIN_API):
        self._key = api_key
        self._base = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        # SimpleLogin uses a bare "Authentication" header, not "Authorization".
        return {"Authentication": self._key, "Content-Type": "application/json"}

    async def _post(self, client: httpx.AsyncClient, path: str, payload: dict) -> dict:
        resp = await client.post(
            f"{self._base}{path}", json=payload, headers=self._headers(), timeout=20.0
        )
        if resp.status_code == 401:
            raise AliasError("SimpleLogin rejected the API key")
        if resp.status_code == 403:
            # verbatim upstream message: "Please upgrade to create a reverse-alias"
            raise AliasError(
                "SimpleLogin requires a Premium plan for this operation "
                "(reverse-alias / custom alias)"
            )
        if resp.status_code >= 400:
            raise AliasError(f"SimpleLogin error {resp.status_code}")
        data = resp.json()
        if not isinstance(data, dict):
            raise AliasError("SimpleLogin returned an unexpected payload")
        return data

    async def create_alias(
        self, client: httpx.AsyncClient, note: str,
    ) -> tuple[int, str]:
        """Create a random alias. Returns (alias_id, alias_email)."""
        data = await self._post(client, "/api/alias/random/new", {"note": note})
        alias_id = data.get("id")
        alias_email = data.get("alias")
        if not alias_id or not alias_email:
            raise AliasError("SimpleLogin returned no alias")
        return int(alias_id), str(alias_email)

    async def create_reverse_alias(
        self, client: httpx.AsyncClient, alias_id: int, recipient: str,
    ) -> tuple[int, str]:
        """Register the recipient as a contact. Returns (contact_id, reverse_alias_address).

        Mail sent to the reverse-alias from the owning mailbox reaches `recipient`
        with the alias as the visible sender.
        """
        data = await self._post(
            client, f"/api/aliases/{alias_id}/contacts", {"contact": recipient}
        )
        addr = data.get("reverse_alias_address")
        if not addr:
            raise AliasError("SimpleLogin returned no reverse_alias_address")
        return int(data.get("id", 0)), str(addr)

    async def disable_alias(self, client: httpx.AsyncClient, alias_id: int) -> bool:
        """Toggle an alias off — the broker can no longer reach the user."""
        data = await self._post(client, f"/api/aliases/{alias_id}/toggle", {})
        return not bool(data.get("enabled", False))


def alias_from_headers(headers: dict) -> str | None:
    """The alias a forwarded message was delivered to, if any.

    Keyed on X-SimpleLogin-Envelope-To because that header is set
    unconditionally; the sender-recovery headers are opt-in upstream.
    """
    if not headers:
        return None
    value = headers.get(HDR_ENVELOPE_TO)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return value.strip().lower() if value else None


def original_sender_from_headers(headers: dict) -> str | None:
    """The SMTP MAIL FROM behind a SimpleLogin forward — best effort.

    Only present when the user enabled `include_header_email_header`. Callers
    must tolerate None rather than treating its absence as "no sender". For
    ESP-sent mail this is the ESP's bounce domain, not the broker's — which is
    why a mismatch is treated as an *unexpected sender* to triage, not proof.
    """
    if not headers:
        return None
    value = headers.get(HDR_ENVELOPE_FROM)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return value.strip() if value else None
