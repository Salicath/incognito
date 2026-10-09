from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from backend.core.profile import Profile
from backend.scanner.duckduckgo import ScanHit, ScanReport, _extract_domain, scan_profile


def test_extract_domain():
    assert _extract_domain("https://www.spokeo.com/search?q=test") == "spokeo.com"
    assert _extract_domain("https://example.com/path") == "example.com"


@pytest.fixture
def profile():
    return Profile(
        full_name="Test User",
        previous_names=[],
        date_of_birth=date(1990, 1, 1),
        emails=["test@example.com"],
        phones=[],
        addresses=[],
    )


@pytest.mark.asyncio
async def test_scan_profile_with_mock(profile):
    mock_results = [{
        "url": "https://www.spokeo.com/Test-User",
        "title": "Test User",
        "snippet": "Found profile for Test User",
    }]

    with (
        patch("backend.scanner.duckduckgo._search_ddg",
              new_callable=AsyncMock, return_value=mock_results),
        patch("backend.scanner.duckduckgo.asyncio.sleep",
              new_callable=AsyncMock),
    ):
        report = await scan_profile(
            profile,
            [("spokeo.com", "Spokeo")],
        )

    assert report.checked >= 1
    assert isinstance(report, ScanReport)


@pytest.mark.asyncio
async def test_scan_empty_results(profile):
    with (
        patch("backend.scanner.duckduckgo._search_ddg",
              new_callable=AsyncMock, return_value=[]),
        patch("backend.scanner.duckduckgo.asyncio.sleep",
              new_callable=AsyncMock),
    ):
        report = await scan_profile(profile, [("example.com", "Example")])

    assert len(report.hits) == 0
    assert report.checked >= 1


def test_scan_hit_model():
    hit = ScanHit(
        broker_domain="spokeo.com",
        broker_name="Spokeo",
        query='"Test User" site:spokeo.com',
        snippet="Found profile",
        url="https://spokeo.com/Test-User",
    )
    assert hit.broker_domain == "spokeo.com"


@pytest.mark.asyncio
async def test_scan_stops_when_search_engine_blocks(profile):
    """DDG 403s every query once an IP is flagged — stop early and say so,
    instead of 229 silent failures that render as "no data found"."""
    brokers = [(f"b{i}.com", f"B{i}") for i in range(100)]
    failing = AsyncMock(side_effect=RuntimeError("DuckDuckGo search failed: HTTPStatusError"))
    with (
        patch("backend.scanner.duckduckgo._search_ddg", failing),
        patch("backend.scanner.duckduckgo.asyncio.sleep", new_callable=AsyncMock),
    ):
        report = await scan_profile(profile, brokers)

    assert failing.await_count == 5
    assert "blocking this IP" in report.errors[-1]
    assert report.hits == []


@pytest.mark.asyncio
async def test_batched_query_attributes_hit_to_the_right_broker(profile):
    """Several brokers share one OR-query; a hit belongs to the site it is on."""
    brokers = [("krak.dk", "Krak"), ("118.dk", "118"), ("spokeo.com", "Spokeo")]
    search = AsyncMock(side_effect=[
        [{"url": "https://www.118.dk/person/test-user", "title": "t", "snippet": "s"}],
        [],  # email query
    ])
    with (
        patch("backend.scanner.duckduckgo._search_ddg", search),
        patch("backend.scanner.duckduckgo.asyncio.sleep", new_callable=AsyncMock),
    ):
        report = await scan_profile(profile, brokers)

    first_query = search.await_args_list[0].args[0]
    assert first_query == '"Test User" (site:krak.dk OR site:118.dk OR site:spokeo.com)'
    assert [(h.broker_domain, h.broker_name) for h in report.hits] == [("118.dk", "118")]
