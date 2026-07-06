"""SearXNG sidecar scanner backend."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.core.profile import Profile
from backend.scanner.searxng import search_searxng


class FakeResp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._resp


async def test_parses_results():
    client = FakeClient(FakeResp(payload={
        "results": [
            {"url": "https://krak.dk/p/1", "title": "Test User", "content": "profile"},
            {"url": "https://other.dk/x", "title": "t"},
        ]
    }))
    results = await search_searxng("q", client, "http://127.0.0.1:8888/")
    assert results[0] == {
        "url": "https://krak.dk/p/1", "title": "Test User", "snippet": "profile",
    }
    assert results[1]["snippet"] == ""  # missing content tolerated
    url, kwargs = client.calls[0]
    assert url == "http://127.0.0.1:8888/search"  # trailing slash normalized
    assert kwargs["params"] == {"q": "q", "format": "json"}


async def test_403_explains_json_format():
    client = FakeClient(FakeResp(status_code=403))
    with pytest.raises(RuntimeError, match="json format"):
        await search_searxng("q", client, "http://127.0.0.1:8888")


async def test_errors_wrapped():
    class Boom:
        async def get(self, *a, **k):
            raise ConnectionError("nope")

    with pytest.raises(RuntimeError, match="SearXNG search failed"):
        await search_searxng("q", Boom(), "http://127.0.0.1:8888")


async def test_scan_profile_uses_searxng_when_configured():
    from backend.scanner.duckduckgo import scan_profile

    profile = Profile(full_name="Test User", emails=["t@example.com"])
    with patch(
        "backend.scanner.searxng.search_searxng", new_callable=AsyncMock
    ) as mock_sx, patch(
        "backend.scanner.duckduckgo._search_ddg", new_callable=AsyncMock
    ) as mock_ddg, patch("asyncio.sleep", new_callable=AsyncMock):
        mock_sx.return_value = [
            {"url": "https://broker0.com/p", "title": "t", "snippet": "s"},
        ]
        report = await scan_profile(
            profile, [("broker0.com", "Broker 0")],
            searxng_url="http://127.0.0.1:8888",
        )
    assert mock_sx.await_count == 2  # site query + email query
    mock_ddg.assert_not_awaited()
    assert report.hits and report.hits[0].broker_domain == "broker0.com"


async def test_scan_profile_defaults_to_ddg():
    from backend.scanner.duckduckgo import scan_profile

    profile = Profile(full_name="Test User", emails=[])
    with patch(
        "backend.scanner.duckduckgo._search_ddg", new_callable=AsyncMock
    ) as mock_ddg, patch("asyncio.sleep", new_callable=AsyncMock):
        mock_ddg.return_value = []
        await scan_profile(profile, [("broker0.com", "Broker 0")])
    mock_ddg.assert_awaited()
