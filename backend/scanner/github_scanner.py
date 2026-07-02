"""GitHub Code Search scanner — leaked-identifier detection.

Surfaces your email/phone committed to public code: old `.env` files,
config, gists, backup dumps. GitHub's code search API requires a PAT
and is rate-limited to ~10 requests/minute, so identifiers are queried
sequentially with a pacing delay.

Docs: https://docs.github.com/en/rest/search/search#search-code
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

SEARCH_URL = "https://api.github.com/search/code"

# Code search allows ~10 requests/minute; 7s between queries stays under it.
REQUEST_DELAY_SECONDS = 7.0
# Only report the most relevant matches per identifier.
MAX_RESULTS_PER_IDENTIFIER = 20


@dataclass
class GithubHit:
    identifier: str  # the email/phone that matched
    repository: str  # owner/repo
    path: str  # file path within the repo
    url: str  # html_url to the matching file


@dataclass
class GithubReport:
    identifiers: list[str]
    hits: list[GithubHit] = field(default_factory=list)
    checked: int = 0
    errors: list[str] = field(default_factory=list)
    rate_limited: bool = False


async def _search_code(
    client: httpx.AsyncClient, token: str, identifier: str
) -> list[dict]:
    resp = await client.get(
        SEARCH_URL,
        params={"q": f'"{identifier}"', "per_page": MAX_RESULTS_PER_IDENTIFIER},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


async def check_github_exposure(
    identifiers: list[str],
    token: str,
    on_progress=None,
    client: httpx.AsyncClient | None = None,
) -> GithubReport:
    """Search public GitHub code for each identifier (exact-match query)."""
    report = GithubReport(identifiers=identifiers)
    if not token:
        report.errors.append("GitHub token not configured")
        return report

    total = len(identifiers)
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        for i, identifier in enumerate(identifiers):
            try:
                items = await _search_code(client, token, identifier)
                for item in items:
                    repo = item.get("repository", {}).get("full_name", "")
                    report.hits.append(
                        GithubHit(
                            identifier=identifier,
                            repository=repo,
                            path=item.get("path", ""),
                            url=item.get("html_url", ""),
                        )
                    )
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (403, 429):
                    report.rate_limited = True
                    report.errors.append(
                        "GitHub rate limit hit — partial results. Retry in a minute."
                    )
                    break
                if status == 401:
                    report.errors.append("GitHub token rejected (401) — check the PAT.")
                    break
                report.errors.append(f"{identifier}: HTTP {status}")
            except Exception as e:
                report.errors.append(f"{identifier}: {e}")

            report.checked = i + 1
            if on_progress:
                on_progress(i + 1, total)
            if i + 1 < total:
                await asyncio.sleep(REQUEST_DELAY_SECONDS)
    finally:
        if own_client:
            await client.aclose()

    return report


def identifiers_from_profile(emails: list[str], phones: list[str]) -> list[str]:
    """Deduped emails + phones worth searching (skip trivially short values)."""
    seen: set[str] = set()
    result = []
    for value in [*emails, *phones]:
        value = value.strip()
        if len(value) >= 6 and value not in seen:
            seen.add(value)
            result.append(value)
    return result
