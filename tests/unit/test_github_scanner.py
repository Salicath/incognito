"""Tests for the GitHub Code Search scanner and its API + settings token."""

from unittest.mock import patch

import httpx

from backend.scanner.github_scanner import (
    GithubHit,
    GithubReport,
    check_github_exposure,
    identifiers_from_profile,
)


class TestIdentifierDerivation:
    def test_combines_emails_and_phones(self):
        assert identifiers_from_profile(["a@example.com"], ["+4512345678"]) == [
            "a@example.com",
            "+4512345678",
        ]

    def test_dedupes(self):
        assert identifiers_from_profile(["a@example.com", "a@example.com"], []) == [
            "a@example.com"
        ]

    def test_skips_short_values(self):
        assert identifiers_from_profile([], ["12345"]) == []


def _code_handler(matches: dict[str, list[dict]]):
    """MockTransport handler keyed by the quoted `q` param value."""

    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("q", "").strip('"')
        items = matches.get(q, [])
        return httpx.Response(200, json={"items": items})

    return handler


def _item(repo: str, path: str, url: str) -> dict:
    return {"repository": {"full_name": repo}, "path": path, "html_url": url}


class TestScanner:
    async def _scan(self, identifiers, handler, monkeypatch, token="ghp_test"):
        monkeypatch.setattr("backend.scanner.github_scanner.REQUEST_DELAY_SECONDS", 0)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await check_github_exposure(identifiers, token, client=client)

    async def test_no_token_short_circuits(self):
        report = await check_github_exposure(["a@example.com"], "")
        assert report.hits == []
        assert any("not configured" in e for e in report.errors)

    async def test_match_becomes_hit(self, monkeypatch):
        handler = _code_handler({
            "leak@example.com": [
                _item("acme/config", ".env", "https://github.com/acme/config/blob/main/.env"),
            ],
        })
        report = await self._scan(["leak@example.com"], handler, monkeypatch)
        assert len(report.hits) == 1
        hit = report.hits[0]
        assert hit.repository == "acme/config"
        assert hit.path == ".env"
        assert hit.identifier == "leak@example.com"
        assert report.errors == []

    async def test_no_match_no_hits(self, monkeypatch):
        report = await self._scan(["clean@example.com"], _code_handler({}), monkeypatch)
        assert report.hits == []
        assert report.checked == 1

    async def test_progress_callback(self, monkeypatch):
        monkeypatch.setattr("backend.scanner.github_scanner.REQUEST_DELAY_SECONDS", 0)
        seen = []
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(_code_handler({}))
        ) as client:
            await check_github_exposure(
                ["a@example.com", "b@example.com"],
                "ghp_test",
                on_progress=lambda c, t: seen.append((c, t)),
                client=client,
            )
        assert seen[-1] == (2, 2)

    async def test_rate_limit_stops_with_partial(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403)

        report = await self._scan(
            ["a@example.com", "b@example.com"], handler, monkeypatch
        )
        assert report.rate_limited is True
        assert any("rate limit" in e.lower() for e in report.errors)
        assert report.checked < 2

    async def test_bad_token_reports_401(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401)

        report = await self._scan(["a@example.com"], handler, monkeypatch)
        assert any("401" in e for e in report.errors)


class TestTokenSettings:
    def test_token_lifecycle(self, authenticated_client):
        assert authenticated_client.get("/api/settings/github").json()["configured"] is False

        resp = authenticated_client.post(
            "/api/settings/github", json={"api_key": "ghp_abcdefghij1234567890"}
        )
        assert resp.status_code == 200

        status = authenticated_client.get("/api/settings/github").json()
        assert status["configured"] is True
        assert "..." in status["key_preview"]

        assert authenticated_client.delete("/api/settings/github").status_code == 200
        assert authenticated_client.get("/api/settings/github").json()["configured"] is False

    def test_empty_token_rejected(self, authenticated_client):
        resp = authenticated_client.post("/api/settings/github", json={"api_key": "  "})
        assert resp.status_code == 400

    def test_requires_auth(self, config, seeded_vault):
        from fastapi.testclient import TestClient

        from backend.main import create_app

        client = TestClient(create_app(config))
        assert client.get("/api/settings/github").status_code == 401


class TestApi:
    def test_requires_auth(self, config, seeded_vault):
        from fastapi.testclient import TestClient

        from backend.main import create_app

        client = TestClient(create_app(config))
        assert client.post("/api/scan/github/start").status_code == 401
        assert client.get("/api/scan/github/status").status_code == 401
        assert client.get("/api/scan/github/results").status_code == 401

    def test_start_without_token_400(self, authenticated_client):
        resp = authenticated_client.post("/api/scan/github/start")
        assert resp.status_code == 400

    def test_results_empty_initially(self, authenticated_client):
        assert authenticated_client.get("/api/scan/github/results").json() == {
            "hits": [], "checked": 0, "has_results": False, "identifiers": [],
        }

    def test_start_and_results(self, authenticated_client):
        authenticated_client.post(
            "/api/settings/github", json={"api_key": "ghp_abcdefghij1234567890"}
        )
        report = GithubReport(
            identifiers=["test@example.com"],
            hits=[
                GithubHit(
                    identifier="test@example.com",
                    repository="acme/leak",
                    path="config/.env",
                    url="https://github.com/acme/leak/blob/main/config/.env",
                )
            ],
            checked=1,
        )
        with patch(
            "backend.scanner.github_scanner.check_github_exposure", return_value=report
        ) as mock_scan:
            resp = authenticated_client.post("/api/scan/github/start")
            assert resp.status_code == 200
            # profile has an email and a phone; both are searchable identifiers
            assert "test@example.com" in resp.json()["identifiers"]
            mock_scan.assert_called_once()

        data = authenticated_client.get("/api/scan/github/results").json()
        assert data["has_results"] is True
        assert data["hits"][0]["repository"] == "acme/leak"
