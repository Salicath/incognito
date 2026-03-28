from __future__ import annotations

import asyncio
import re
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


async def _search_ddg(query: str, client: httpx.AsyncClient) -> list[dict]:
    """Search DuckDuckGo HTML and extract results."""
    url = "https://html.duckduckgo.com/html/"
    try:
        resp = await client.post(
            url,
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"},
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
    except Exception:
        return []


async def scan_profile(
    profile: Profile,
    broker_domains: list[tuple[str, str]],  # list of (domain, name)
    on_progress: callable | None = None,
) -> ScanReport:
    """
    Scan DuckDuckGo for the user's data across broker sites.

    broker_domains: list of (domain, broker_name) tuples
    on_progress: optional callback(checked, total) for progress updates
    """
    report = ScanReport()

    # Build queries: name + each broker domain
    queries = []
    for domain, broker_name in broker_domains:
        # Search for exact name match on the broker's site
        queries.append((f'"{profile.full_name}" site:{domain}', domain, broker_name))

    # Also search for email addresses (not site-specific, broader scan)
    for email in profile.emails:
        queries.append((f'"{email}"', "*", "General"))

    total = len(queries)

    async with httpx.AsyncClient() as client:
        for i, (query, domain, broker_name) in enumerate(queries):
            results = await _search_ddg(query, client)
            report.checked += 1

            for result in results:
                # For site-specific queries, all results are hits
                # For general queries, check if the result is from a known broker
                if domain == "*" or domain in result.get("url", ""):
                    report.hits.append(ScanHit(
                        broker_domain=domain if domain != "*" else _extract_domain(result["url"]),
                        broker_name=broker_name if broker_name != "General" else _extract_domain(result["url"]),
                        query=query,
                        snippet=result.get("snippet", "")[:200],
                        url=result.get("url", ""),
                    ))

            if on_progress:
                on_progress(i + 1, total)

            # Rate limit: be polite to DDG
            await asyncio.sleep(1.5)

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
