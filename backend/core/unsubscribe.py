"""RFC 8058 one-click unsubscribe action.

Performs the one-click POST verified against RFC 8058 §3.2: POST the literal
body `List-Unsubscribe=One-Click` (application/x-www-form-urlencoded) to the
HTTPS unsubscribe URI, with no cookies/auth and no redirect following. Gated on
an SSRF guard because the target URL originates from inbound mail.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

_ONE_CLICK_BODY = b"List-Unsubscribe=One-Click"
_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}


def is_safe_url(url: str) -> bool:
    """Reject anything that isn't a public-internet HTTPS endpoint.

    Guards against SSRF: the URL comes from an email header. HTTPS only; every
    resolved address must be a public unicast IP (no loopback/private/link-local/
    reserved/multicast). Note: this resolves at check time; a determined
    DNS-rebinding attacker could still shift the address before the request —
    acceptable for a single-user, user-initiated action.
    """
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme != "https" or not p.hostname:
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443, proto=socket.IPPROTO_TCP)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        # is_global rejects everything non-public in one check, incl. CGNAT/
        # shared space 100.64.0.0/10 (Tailscale) that the individual flags miss.
        if (
            not ip.is_global
            or ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


async def one_click_unsubscribe(
    url: str,
    timeout: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
    _skip_safety: bool = False,
) -> tuple[bool, str]:
    """POST the RFC 8058 one-click body. Returns (ok, human-readable detail)."""
    if not _skip_safety and not is_safe_url(url):
        return False, "Unsubscribe URL is not a safe public HTTPS endpoint"
    try:
        async with httpx.AsyncClient(
            follow_redirects=False, timeout=timeout, transport=transport
        ) as client:
            resp = await client.post(url, content=_ONE_CLICK_BODY, headers=_HEADERS)
    except Exception as e:
        return False, f"Unsubscribe request failed: {type(e).__name__}"
    if 200 <= resp.status_code < 300:
        return True, f"Unsubscribed (HTTP {resp.status_code})"
    return False, f"Unsubscribe endpoint returned HTTP {resp.status_code}"
