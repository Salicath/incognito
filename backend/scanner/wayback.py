"""Wayback Machine CDX scanner — ghost-profile detection.

The CDX index is searchable by URL, not page content, so this scanner
checks whether known profile-URL shapes for the user's usernames were
ever archived. A hit on a URL that is dead today means personal data
survives in the archive even after account deletion — actionable via
Internet Archive's removal request process (info@archive.org).

Free, no API key. See https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

CDX_URL = "https://web.archive.org/cdx/search/cdx"

# Platform profile-URL shapes checked per username.
PROFILE_URL_PATTERNS: list[tuple[str, str]] = [
    ("Twitter/X", "twitter.com/{u}"),
    ("Instagram", "instagram.com/{u}"),
    ("Facebook", "facebook.com/{u}"),
    ("Reddit", "reddit.com/user/{u}"),
    ("GitHub", "github.com/{u}"),
    ("LinkedIn", "linkedin.com/in/{u}"),
    ("TikTok", "tiktok.com/@{u}"),
    ("YouTube", "youtube.com/@{u}"),
    ("Medium", "medium.com/@{u}"),
    ("Pinterest", "pinterest.com/{u}"),
    ("Tumblr", "{u}.tumblr.com"),
    ("Keybase", "keybase.io/{u}"),
    ("Flickr", "flickr.com/people/{u}"),
    ("Mastodon", "mastodon.social/@{u}"),
    ("About.me", "about.me/{u}"),
]

# Politeness delay between CDX queries; the endpoint rate-limits bursts
# aggressively at the IP level (observed 429s on single requests).
REQUEST_DELAY_SECONDS = 1.5
RATE_LIMIT_BACKOFF_SECONDS = 20


@dataclass
class WaybackHit:
    platform: str
    username: str
    url: str  # original archived URL
    snapshots: int
    first_snapshot: str  # YYYYMMDD
    last_snapshot: str  # YYYYMMDD
    archive_url: str  # link to the most recent snapshot


@dataclass
class WaybackReport:
    usernames: list[str]
    hits: list[WaybackHit] = field(default_factory=list)
    checked: int = 0
    errors: list[str] = field(default_factory=list)


async def _query_cdx(client: httpx.AsyncClient, url: str) -> list[list[str]]:
    """Return CDX rows (without the header row) for a URL, [] if never archived."""
    resp = await client.get(
        CDX_URL,
        params={
            "url": url,
            "output": "json",
            "fl": "timestamp,original,statuscode",
            "filter": "statuscode:200",
            "collapse": "digest",
            "limit": "500",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[1:] if rows else []


async def check_wayback_profiles(
    usernames: list[str], on_progress=None, client: httpx.AsyncClient | None = None
) -> WaybackReport:
    """Check the Wayback Machine for archived profile pages for each username."""
    report = WaybackReport(usernames=usernames)
    checks = [
        (platform, username, pattern.format(u=username))
        for username in usernames
        for platform, pattern in PROFILE_URL_PATTERNS
    ]
    total = len(checks)
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0, headers={"User-Agent": "incognito-selfscan"})

    async def _query_with_retry(url: str) -> list[list[str]]:
        try:
            return await _query_cdx(client, url)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 429:
                raise
            retry_after = e.response.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else 0
            await asyncio.sleep(min(max(delay, RATE_LIMIT_BACKOFF_SECONDS), 60))
            return await _query_cdx(client, url)

    try:
        for i, (platform, username, url) in enumerate(checks):
            try:
                rows = await _query_with_retry(url)
                if rows:
                    timestamps = sorted(row[0] for row in rows)
                    last = timestamps[-1]
                    original = rows[-1][1]
                    report.hits.append(
                        WaybackHit(
                            platform=platform,
                            username=username,
                            url=original,
                            snapshots=len(rows),
                            first_snapshot=timestamps[0][:8],
                            last_snapshot=last[:8],
                            archive_url=f"https://web.archive.org/web/{last}/{original}",
                        )
                    )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    report.errors.append("Rate limited by web.archive.org — partial results")
                    break
                report.errors.append(f"{platform} ({username}): HTTP {e.response.status_code}")
            except Exception as e:
                report.errors.append(f"{platform} ({username}): {e}")

            report.checked = i + 1
            if on_progress:
                on_progress(i + 1, total)
            if i + 1 < total:
                await asyncio.sleep(REQUEST_DELAY_SECONDS)
    finally:
        if own_client:
            await client.aclose()

    return report


def usernames_from_profile(usernames: list[str], emails: list[str]) -> list[str]:
    """Explicit usernames, falling back to email local-parts (deduped, len >= 3)."""
    candidates = list(usernames)
    if not candidates:
        candidates = [e.split("@")[0] for e in emails]
    seen: set[str] = set()
    result = []
    for c in candidates:
        c = c.strip().lower()
        if len(c) >= 3 and c not in seen:
            seen.add(c)
            result.append(c)
    return result
