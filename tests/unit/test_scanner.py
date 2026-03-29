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
