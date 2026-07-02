"""Tests for the Wayback CDX scanner (ghost-profile detection) and its API."""

from unittest.mock import patch

import httpx

from backend.scanner.wayback import (
    PROFILE_URL_PATTERNS,
    WaybackHit,
    WaybackReport,
    check_wayback_profiles,
    usernames_from_profile,
)


class TestUsernameDerivation:
    def test_explicit_usernames_win(self):
        assert usernames_from_profile(["myhandle"], ["other@example.com"]) == ["myhandle"]

    def test_falls_back_to_email_local_parts(self):
        assert usernames_from_profile([], ["salicath@pm.me", "old.name@gmail.com"]) == [
            "salicath",
            "old.name",
        ]

    def test_dedupes_and_lowercases(self):
        assert usernames_from_profile(["Foo", "foo", " FOO "], []) == ["foo"]

    def test_filters_short_candidates(self):
        assert usernames_from_profile([], ["ab@example.com"]) == []


def _cdx_handler(archived_urls: dict[str, list[list[str]]]):
    """MockTransport handler: returns CDX rows for exact `url` params, else empty."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = request.url.params.get("url")
        rows = archived_urls.get(url)
        if not rows:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[["timestamp", "original", "statuscode"], *rows])

    return handler


class TestScanner:
    async def _scan(self, usernames, handler, monkeypatch):
        monkeypatch.setattr("backend.scanner.wayback.REQUEST_DELAY_SECONDS", 0)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await check_wayback_profiles(usernames, client=client)

    async def test_archived_profile_becomes_hit(self, monkeypatch):
        handler = _cdx_handler({
            "twitter.com/ghostuser": [
                ["20150101000000", "https://twitter.com/ghostuser", "200"],
                ["20190615000000", "https://twitter.com/ghostuser", "200"],
            ],
        })
        report = await self._scan(["ghostuser"], handler, monkeypatch)

        assert len(report.hits) == 1
        hit = report.hits[0]
        assert hit.platform == "Twitter/X"
        assert hit.username == "ghostuser"
        assert hit.snapshots == 2
        assert hit.first_snapshot == "20150101"
        assert hit.last_snapshot == "20190615"
        assert hit.archive_url == (
            "https://web.archive.org/web/20190615000000/https://twitter.com/ghostuser"
        )
        assert report.checked == len(PROFILE_URL_PATTERNS)
        assert report.errors == []

    async def test_never_archived_yields_no_hits(self, monkeypatch):
        report = await self._scan(["nobody"], _cdx_handler({}), monkeypatch)
        assert report.hits == []
        assert report.checked == len(PROFILE_URL_PATTERNS)

    async def test_progress_callback_fires(self, monkeypatch):
        monkeypatch.setattr("backend.scanner.wayback.REQUEST_DELAY_SECONDS", 0)
        seen = []
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_cdx_handler({}))
        ) as client:
            await check_wayback_profiles(
                ["someone"], on_progress=lambda c, t: seen.append((c, t)), client=client
            )
        assert seen[-1] == (len(PROFILE_URL_PATTERNS), len(PROFILE_URL_PATTERNS))

    async def test_rate_limit_stops_scan_with_partial_results(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429)

        report = await self._scan(["someone"], handler, monkeypatch)
        assert report.hits == []
        assert any("Rate limited" in e for e in report.errors)
        # stopped early, did not hammer the endpoint
        assert report.checked < len(PROFILE_URL_PATTERNS)

    async def test_multiple_usernames_checked(self, monkeypatch):
        handler = _cdx_handler({
            "github.com/alpha": [["20200101000000", "https://github.com/alpha", "200"]],
            "reddit.com/user/beta": [["20210101000000", "https://reddit.com/user/beta", "200"]],
        })
        report = await self._scan(["alpha", "beta"], handler, monkeypatch)
        assert {h.username for h in report.hits} == {"alpha", "beta"}
        assert report.checked == 2 * len(PROFILE_URL_PATTERNS)


class TestApi:
    def test_requires_auth(self, config, seeded_vault):
        from fastapi.testclient import TestClient

        from backend.main import create_app

        client = TestClient(create_app(config))
        assert client.post("/api/scan/wayback/start").status_code == 401
        assert client.get("/api/scan/wayback/status").status_code == 401
        assert client.get("/api/scan/wayback/results").status_code == 401

    def test_status_idle(self, authenticated_client):
        resp = authenticated_client.get("/api/scan/wayback/status")
        assert resp.status_code == 200
        assert resp.json()["running"] is False

    def test_results_empty_initially(self, authenticated_client):
        resp = authenticated_client.get("/api/scan/wayback/results")
        assert resp.json() == {
            "hits": [], "checked": 0, "has_results": False, "usernames": [],
        }

    def test_start_falls_back_to_email_local_part(self, authenticated_client):
        report = WaybackReport(usernames=["test"], checked=15)
        with patch(
            "backend.scanner.wayback.check_wayback_profiles", return_value=report
        ) as mock_scan:
            resp = authenticated_client.post("/api/scan/wayback/start")
            assert resp.status_code == 200
            # profile email is test@example.com -> local part "test"
            assert resp.json()["usernames"] == ["test"]
            mock_scan.assert_called_once()

    def test_start_with_explicit_usernames(self, authenticated_client):
        report = WaybackReport(usernames=["alpha", "beta"], checked=30)
        with patch("backend.scanner.wayback.check_wayback_profiles", return_value=report):
            resp = authenticated_client.post(
                "/api/scan/wayback/start", params={"usernames": "Alpha, beta"}
            )
            assert resp.status_code == 200
            assert resp.json()["usernames"] == ["alpha", "beta"]

    def test_start_rejects_too_many_usernames(self, authenticated_client):
        many = ",".join(f"user{i}" for i in range(11))
        resp = authenticated_client.post(
            "/api/scan/wayback/start", params={"usernames": many}
        )
        assert resp.status_code == 400

    def test_results_after_scan(self, authenticated_client):
        report = WaybackReport(
            usernames=["test"],
            hits=[
                WaybackHit(
                    platform="GitHub",
                    username="test",
                    url="https://github.com/test",
                    snapshots=3,
                    first_snapshot="20180101",
                    last_snapshot="20220505",
                    archive_url="https://web.archive.org/web/20220505000000/https://github.com/test",
                )
            ],
            checked=15,
        )
        with patch("backend.scanner.wayback.check_wayback_profiles", return_value=report):
            authenticated_client.post("/api/scan/wayback/start")

        resp = authenticated_client.get("/api/scan/wayback/results")
        data = resp.json()
        assert data["has_results"] is True
        assert data["hits"][0]["platform"] == "GitHub"
        assert data["hits"][0]["snapshots"] == 3
