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

# Engines that search the open web. SearXNG's general category also holds
# instant-answer engines (wikipedia, currency, translators) that never answer
# a site: query, so they must not count as "an engine answered".
_WEB_ENGINES = {
    "google", "google cse", "bing", "brave", "duckduckgo", "startpage",
    "mojeek", "qwant", "yahoo", "presearch",
}
# base_url -> enabled web engines. shortcut: cached for the process lifetime,
# restart Incognito after changing SearXNG's engine settings.
_enabled_cache: dict[str, set[str]] = {}


async def _enabled_web_engines(client, base_url: str) -> set[str]:
    if base_url not in _enabled_cache:
        try:
            resp = await client.get(f"{base_url}/config", timeout=10.0)
            engines = resp.json().get("engines", [])
            enabled = {
                e["name"] for e in engines
                if e.get("enabled") and e.get("name") in _WEB_ENGINES
            }
        except Exception:  # noqa: BLE001 - unknown config: decide per response
            return set()
        if not enabled:
            return set()  # don't cache "unknown"
        _enabled_cache[base_url] = enabled
    return _enabled_cache[base_url]


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
        blocked = data.get("unresponsive_engines") or []
        blocked_names = {e[0] for e in blocked if e}
        enabled = await _enabled_web_engines(client, base_url.rstrip("/"))
        # SearXNG answers 200 with an empty list when every engine is
        # suspended — that is "couldn't search", not "no exposure". One web
        # engine answering (even with nothing) makes the empty list real.
        # Without /config we can't tell, so any suspension counts as failure.
        all_down = blocked_names >= enabled if enabled else bool(blocked_names)
        if not data.get("results") and all_down:
            raise RuntimeError(
                "SearXNG: no engine answered ("
                + ", ".join(f"{e[0]}: {e[1]}" for e in blocked if len(e) == 2)
                + ")"
            )
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
