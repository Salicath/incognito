"""Newsletter / mailing-list discovery via IMAP List-Unsubscribe headers.

Scans the inbox for RFC 2369 `List-Unsubscribe` (+ RFC 8058
`List-Unsubscribe-Post`) headers. Each distinct sender that offers an
unsubscribe route is a controller processing the user's address for
marketing — surfaced as an exposure whose removal action is an unsubscribe
(one-click POST when RFC 8058 signals it, mailto otherwise).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from email.utils import parseaddr
from urllib.parse import unquote

_ANGLE = re.compile(r"<([^>]+)>")


@dataclass
class NewsletterHit:
    sender: str
    sender_name: str
    sender_domain: str
    one_click: bool
    unsub_https: str | None
    unsub_mailto: str | None
    unsub_mailto_subject: str | None
    subject: str


@dataclass
class NewsletterReport:
    hits: list[NewsletterHit] = field(default_factory=list)
    checked: int = 0
    errors: list[str] = field(default_factory=list)


def parse_list_unsubscribe(header: str | None) -> tuple[str | None, str | None, str | None]:
    """Extract (https_url, mailto_addr, mailto_subject) from a List-Unsubscribe header.

    Picks the first https URI and the first mailto URI; honours a `?subject=` on
    the mailto per RFC 6068.
    """
    https: str | None = None
    mailto: str | None = None
    mailto_subject: str | None = None
    for raw in _ANGLE.findall(header or ""):
        uri = raw.strip()
        low = uri.lower()
        if low.startswith("https://") and https is None:
            https = uri
        elif low.startswith("mailto:") and mailto is None:
            addr = uri[len("mailto:"):]
            if "?" in addr:
                addr, query = addr.split("?", 1)
                for part in query.split("&"):
                    if part.lower().startswith("subject="):
                        mailto_subject = unquote(part[len("subject="):])
            mailto = addr
    return https, mailto, mailto_subject


def is_one_click(post_header: str | None) -> bool:
    """RFC 8058: the header value is literally `List-Unsubscribe=One-Click`."""
    if not post_header:
        return False
    return post_header.lower().replace(" ", "") == "list-unsubscribe=one-click"


def _domain_of(email_addr: str) -> str:
    return email_addr.split("@")[-1].lower() if "@" in email_addr else email_addr.lower()


def _first_header(headers: dict, name: str) -> str | None:
    vals = headers.get(name)
    return vals[0] if vals else None


def build_hit(
    from_header: str,
    subject: str | None,
    lu_header: str | None,
    lup_header: str | None,
) -> NewsletterHit | None:
    if not lu_header:
        return None
    https, mailto, msubj = parse_list_unsubscribe(lu_header)
    if not https and not mailto:
        return None
    name, addr = parseaddr(from_header or "")
    domain = _domain_of(addr)
    # RFC 8058 §3.1: one-click requires the List-Unsubscribe-Post header AND an https URI.
    one_click = is_one_click(lup_header) and https is not None
    return NewsletterHit(
        sender=addr,
        sender_name=name or domain,
        sender_domain=domain,
        one_click=one_click,
        unsub_https=https,
        unsub_mailto=mailto,
        unsub_mailto_subject=msubj,
        subject=subject or "",
    )


def build_report_from_messages(messages) -> NewsletterReport:
    """Build a report from imap_tools-like messages, deduped by sender domain.

    Each message exposes `.headers` (dict of lowercased header -> tuple of values),
    `.from_` (str), and `.subject` (str). Newest-first input keeps the first hit
    per domain as the representative.
    """
    report = NewsletterReport()
    seen: set[str] = set()
    for msg in messages:
        report.checked += 1
        headers = getattr(msg, "headers", None) or {}
        hit = build_hit(
            from_header=getattr(msg, "from_", "") or "",
            subject=getattr(msg, "subject", "") or "",
            lu_header=_first_header(headers, "list-unsubscribe"),
            lup_header=_first_header(headers, "list-unsubscribe-post"),
        )
        if hit is None or not hit.sender_domain or hit.sender_domain in seen:
            continue
        seen.add(hit.sender_domain)
        report.hits.append(hit)
    return report


async def scan_newsletters(imap_config, limit: int = 300) -> NewsletterReport:
    """Connect to IMAP and scan the newest `limit` messages for unsubscribe headers."""
    import ssl as ssl_mod

    from imap_tools import MailBox, MailBoxStartTls

    try:
        ssl_ctx = ssl_mod.create_default_context()
        if imap_config.host in ("127.0.0.1", "localhost", "::1"):
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl_mod.CERT_NONE

        mb: MailBox | MailBoxStartTls
        if imap_config.starttls:
            mb = MailBoxStartTls(host=imap_config.host, port=imap_config.port, ssl_context=ssl_ctx)
        else:
            mb = MailBox(host=imap_config.host, port=imap_config.port, ssl_context=ssl_ctx)

        with mb.login(imap_config.username, imap_config.password, imap_config.folder) as mailbox:
            messages = list(
                mailbox.fetch(limit=limit, reverse=True, mark_seen=False, headers_only=True)
            )
        return build_report_from_messages(messages)
    except Exception as exc:
        report = NewsletterReport()
        report.errors.append(f"{type(exc).__name__}: IMAP connection or scan failed")
        return report
