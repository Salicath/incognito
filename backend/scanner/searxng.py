"""SearXNG meta-search backend (self-hosted sidecar).

When INCOGNITO_SEARXNG_URL is set, discovery scans query the local SearXNG
instance's JSON API instead of scraping DDG HTML — no CAPTCHA exposure and
meta-search coverage across engines. The instance must enable the json output
format and disable the limiter (see deploy/searxng-settings.yml); requesting
an unset format returns 403.

Delisting re-verification deliberately stays on DDG (`verify_delisted_urls`):
it checks the Bing-surface RTBF filter specifically, which DDG resells.
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger("incognito.searxng")


async def search_searxng(
    query: str, client: httpx.AsyncClient, base_url: str,
) -> list[dict]:
    """Search a SearXNG instance; returns [{url, title, snippet}]."""
    url = f"{base_url.rstrip('/')}/search"
    try:
        resp = await client.get(
            url, params={"q": query, "format": "json"}, timeout=20.0,
        )
        if resp.status_code == 403:
            raise RuntimeError(
                "SearXNG returned 403 — enable the json format in settings.yml "
                "(search.formats) and disable the limiter"
            )
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": r.get("content", ""),
            }
            for r in data.get("results", [])
        ]
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"SearXNG search failed: {type(exc).__name__}") from exc
