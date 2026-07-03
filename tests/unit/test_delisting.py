from backend.core.delisting import REASONS, build_delisting_kit


def test_kit_has_google_bing_brave_engines():
    kit = build_delisting_kit("https://x.example/page", ["Jane Doe"], "outdated")
    keys = {e["key"] for e in kit["engines"]}
    assert {"google", "bing", "brave"} <= keys
    google = next(e for e in kit["engines"] if e["key"] == "google")
    assert google["action"] == "form"
    assert google["target"].startswith("https://")
    assert google["id_required"] is True
    brave = next(e for e in kit["engines"] if e["key"] == "brave")
    assert brave["action"] == "email"
    assert "@" in brave["target"]


def test_justification_mentions_name_and_article_17():
    kit = build_delisting_kit("https://x.example/p", ["Jane Doe"], "outdated")
    j = kit["justification"]
    assert "Jane Doe" in j
    assert "17" in j  # Article 17 GDPR
    assert "out of date" in j.lower()


def test_reason_defaults_when_unknown():
    kit = build_delisting_kit("https://x.example/p", ["Jane Doe"], "nonsense")
    assert kit["reason"] in REASONS


def test_each_reason_produces_distinct_text():
    texts = {
        r: build_delisting_kit("https://x/p", ["N"], r)["justification"]
        for r in REASONS
    }
    assert len(set(texts.values())) == len(REASONS)


def test_danish_locale_justification():
    kit = build_delisting_kit("https://x.example/p", ["Jens Hansen"], "inaccurate", locale="da")
    j = kit["justification"]
    assert "Jens Hansen" in j
    assert "artikel 17" in j.lower()


def test_coverage_note_mentions_resellers():
    kit = build_delisting_kit("https://x.example/p", ["Jane Doe"], "outdated")
    note = kit["coverage_note"].lower()
    assert "duckduckgo" in note or "resell" in note


def test_empty_name_queries_is_tolerated():
    kit = build_delisting_kit("https://x.example/p", [], "outdated")
    assert kit["justification"]  # still produces text, just without a name
