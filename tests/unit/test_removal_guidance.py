"""Tests for source-specific removal guidance."""

from backend.core.removal_guidance import guidance_for


def _shape_ok(g):
    assert isinstance(g["title"], str) and g["title"]
    assert isinstance(g["steps"], list) and all(isinstance(s, str) for s in g["steps"])
    assert g["steps"]
    assert isinstance(g["links"], list)
    for link in g["links"]:
        assert link["label"] and link["url"].startswith("http")


def test_github_guidance_mentions_repo_and_docs():
    g = guidance_for("github", {"repository": "acme/leak"})
    _shape_ok(g)
    assert "acme/leak" in g["title"]
    assert any("git-filter-repo" in s for s in g["steps"])
    assert any("docs.github.com" in link["url"] for link in g["links"])


def test_wayback_guidance_points_at_archive_email():
    g = guidance_for("wayback", {"url": "https://web.archive.org/x"})
    _shape_ok(g)
    assert any("info@archive.org" in s for s in g["steps"])


def test_holehe_guidance_uses_service_name():
    g = guidance_for("holehe:me@example.com", {"service": "Spotify"})
    _shape_ok(g)
    assert "Spotify" in g["title"]


def test_websearch_guidance_covers_delisting():
    g = guidance_for("duckduckgo", {"url": "https://x"})
    _shape_ok(g)
    assert any("delist" in s.lower() for s in g["steps"])


def test_source_suffix_is_stripped():
    assert guidance_for("holehe:anything", {}) is not None


def test_unknown_source_returns_none():
    assert guidance_for("mystery", {}) is None


def test_none_data_is_tolerated():
    g = guidance_for("github", None)
    _shape_ok(g)
    assert "the repository" in g["title"]
