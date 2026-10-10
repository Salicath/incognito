from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from backend.core.profile import Profile


@dataclass
class ScanHit:
    broker_domain: str
    broker_name: str
    query: str
    snippet: str
    url: str


@dataclass
class ScanReport:
    hits: list[ScanHit] = field(default_factory=list)
    checked: int = 0
    errors: list[str] = field(default_factory=list)


_MAX_CONSECUTIVE_FAILURES = 3  # each already retried after a backoff
_BLOCK_BACKOFF_SECONDS = 200
_SEARXNG_DELAY_SECONDS = 8
_SITES_PER_QUERY = 8


async def _search_ddg(
    query: str, client: httpx.AsyncClient, region: str | None = None,
) -> list[dict]:
    """Search DuckDuckGo HTML and extract results.

    region ("kl", e.g. "dk-da"): only region-scoped queries reliably carry the
    EU-market RTBF filter, so delisting verification sets it — but the broker
    discovery scan must NOT, or Danish ranking bias silently costs recall on
    US people-search queries.
    """
    url = "https://html.duckduckgo.com/html/"
    data = {"q": query}
    if region:
        data["kl"] = region
    try:
        resp = await client.post(
            url,
            data=data,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) "
                    "Gecko/20100101 Firefox/128.0"
                ),
            },
            follow_redirects=True,
            timeout=15.0,
        )
        resp.raise_for_status()
        html = resp.text

        results = []
        # Extract result snippets - DDG HTML uses class="result__snippet" and class="result__url"
        # Simple regex extraction
        snippets = re.findall(
            r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</span>',
            html,
            re.DOTALL,
        )
        for href, title, snippet in snippets:
            # Clean HTML tags from snippet and title
            clean_snippet = re.sub(r"<[^>]+>", "", snippet).strip()
            clean_title = re.sub(r"<[^>]+>", "", title).strip()
            # DDG wraps URLs in a redirect, extract the actual URL
            actual_url = href
            if "uddg=" in href:
                match = re.search(r"uddg=([^&]+)", href)
                if match:
                    from urllib.parse import unquote
                    actual_url = unquote(match.group(1))
            results.append({
                "url": actual_url,
                "title": clean_title,
                "snippet": clean_snippet,
            })
        return results
    except Exception as exc:
        raise RuntimeError(f"DuckDuckGo search failed: {type(exc).__name__}") from exc


async def scan_profile(
    profile: Profile,
    broker_domains: list[tuple[str, str]],  # list of (domain, name)
    on_progress: Callable[[int, int], None] | None = None,
    searxng_url: str | None = None,
) -> ScanReport:
    """
    Scan for the user's data across broker sites.

    Uses the self-hosted SearXNG sidecar when searxng_url is set (JSON API,
    no CAPTCHA exposure); falls back to scraping DDG HTML otherwise.

    broker_domains: list of (domain, broker_name) tuples
    on_progress: optional callback(checked, total) for progress updates
    """
    report = ScanReport()

    # Name + several broker sites per query: one query per broker (229 from a
    # home IP) gets every engine to block or CAPTCHA us partway through.
    queries: list[tuple[str, list[tuple[str, str]]]] = []
    for i in range(0, len(broker_domains), _SITES_PER_QUERY):
        batch = broker_domains[i:i + _SITES_PER_QUERY]
        sites = " OR ".join(f"site:{d}" for d, _ in batch)
        queries.append((f'"{profile.full_name}" ({sites})', batch))

    # Also search for email addresses (not site-specific, broader scan)
    for email in profile.emails:
        queries.append((f'"{email}"', [("*", "General")]))

    total = len(queries)

    consecutive_failures = 0
    async with httpx.AsyncClient() as client:

        async def search(q: str) -> list[dict]:
            if searxng_url:
                from backend.scanner.searxng import search_searxng
                return await search_searxng(q, client, searxng_url)
            return await _search_ddg(q, client)

        for i, (query, targets) in enumerate(queries):
            try:
                try:
                    results = await search(query)
                except RuntimeError:
                    # Engines suspend a flagged IP for ~3 min (SearXNG's
                    # suspended_time=180): wait it out once, then retry.
                    await asyncio.sleep(_BLOCK_BACKOFF_SECONDS)
                    results = await search(query)
            except RuntimeError as e:
                report.errors.append(str(e))
                results = []
                consecutive_failures += 1
                if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    # Blocked (DDG answers 403 once an IP is flagged) — every
                    # remaining query would fail too, and the empty result
                    # must not read as "no data found".
                    hint = (
                        "Retry later — engine suspensions lift after minutes to hours."
                        if searxng_url else
                        "Set INCOGNITO_SEARXNG_URL (deploy/searxng.container) or retry later."
                    )
                    report.errors.append(
                        f"Stopped after {consecutive_failures} failed searches in a row — "
                        f"the search engines are blocking this IP. {hint}"
                    )
                    break
            else:
                consecutive_failures = 0
            report.checked += 1

            for result in results:
                url = result.get("url", "")
                # Attribute the hit to the batch's broker whose site it is on.
                # General (bare-email) queries accept every result — the email
                # appearing anywhere is itself the exposure.
                match = next(((d, n) for d, n in targets if d == "*" or d in url), None)
                if match:
                    domain, broker_name = match
                    report.hits.append(ScanHit(
                        broker_domain=domain if domain != "*" else _extract_domain(url),
                        broker_name=(
                            broker_name if broker_name != "General" else _extract_domain(url)
                        ),
                        query=query,
                        snippet=result.get("snippet", "")[:200],
                        url=url,
                    ))

            if on_progress:
                on_progress(i + 1, total)

            # Pace queries: Google flags "unusual traffic" after a fast burst
            await asyncio.sleep(_SEARXNG_DELAY_SECONDS if searxng_url else 1.5)

    # Deduplicate hits by domain
    seen = set()
    unique_hits = []
    for hit in report.hits:
        key = hit.broker_domain
        if key not in seen:
            seen.add(key)
            unique_hits.append(hit)
    report.hits = unique_hits

    return report


def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else url
