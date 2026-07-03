import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.scanner.maigret_scanner import (
    MaigretReport,
    _parse_report,
    check_maigret,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "maigret_simple_report.json"


def test_parse_report_extracts_found_sites():
    data = json.loads(FIXTURE.read_text())
    hits = _parse_report(data, username="soxoj")
    assert hits, "fixture should contain at least one found site"
    assert all(h.username == "soxoj" for h in hits)
    assert all(h.url for h in hits)
    by_service = {h.service: h for h in hits}
    assert "GitHub" in by_service
    assert by_service["GitHub"].url == "https://github.com/soxoj"
    # tags come from the nested status dict
    assert "coding" in by_service["GitHub"].tags


@pytest.mark.asyncio
async def test_check_maigret_missing_binary():
    report = await check_maigret("soxoj", binary="/nonexistent/maigret")
    assert isinstance(report, MaigretReport)
    assert report.hits == []
    assert report.errors and "not installed" in report.errors[0].lower()


@pytest.mark.asyncio
async def test_check_maigret_parses_subprocess_output():
    fixture = json.loads(FIXTURE.read_text())

    async def fake_run(username, top_sites, timeout, binary, folder):
        (Path(folder) / f"report_{username}_simple.json").write_text(json.dumps(fixture))
        return 0, "", ""

    with (
        patch("backend.scanner.maigret_scanner._resolve_binary", return_value="/usr/bin/maigret"),
        patch("backend.scanner.maigret_scanner._run_maigret", new=AsyncMock(side_effect=fake_run)),
    ):
        report = await check_maigret("soxoj", top_sites=15)
    assert report.username == "soxoj"
    assert report.hits
    assert report.errors == []


@pytest.mark.asyncio
async def test_check_maigret_handles_nonzero_exit():
    async def fake_run(username, top_sites, timeout, binary, folder):
        return 1, "", "maigret crashed"

    with (
        patch("backend.scanner.maigret_scanner._resolve_binary", return_value="/usr/bin/maigret"),
        patch("backend.scanner.maigret_scanner._run_maigret", new=AsyncMock(side_effect=fake_run)),
    ):
        report = await check_maigret("soxoj")
    assert report.hits == []
    assert report.errors
