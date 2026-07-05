from types import SimpleNamespace

from backend.scanner.newsletter import (
    build_hit,
    build_report_from_messages,
    is_one_click,
    parse_list_unsubscribe,
)


def test_parse_extracts_https_and_mailto():
    header = "<mailto:unsub@list.example?subject=unsubscribe>, <https://list.example/u/abc>"
    https, mailto, subj = parse_list_unsubscribe(header)
    assert https == "https://list.example/u/abc"
    assert mailto == "unsub@list.example"
    assert subj == "unsubscribe"


def test_parse_https_only():
    https, mailto, subj = parse_list_unsubscribe("<https://x.example/unsub?token=t>")
    assert https == "https://x.example/unsub?token=t"
    assert mailto is None


def test_parse_url_decodes_mailto_subject():
    https, mailto, subj = parse_list_unsubscribe("<mailto:u@x.example?subject=Unsubscribe%20me>")
    assert subj == "Unsubscribe me"


def test_is_one_click_exact_value():
    assert is_one_click("List-Unsubscribe=One-Click") is True
    assert is_one_click("list-unsubscribe = one-click") is True
    assert is_one_click("something-else") is False
    assert is_one_click(None) is False


def test_build_hit_one_click_requires_https_and_post_header():
    hit = build_hit(
        from_header="Acme News <news@acme.example>",
        subject="Weekly digest",
        lu_header="<https://acme.example/u/1>, <mailto:u@acme.example>",
        lup_header="List-Unsubscribe=One-Click",
    )
    assert hit is not None
    assert hit.one_click is True
    assert hit.sender_domain == "acme.example"
    assert hit.sender_name == "Acme News"
    assert hit.unsub_https == "https://acme.example/u/1"


def test_build_hit_no_one_click_without_post_header():
    hit = build_hit(
        from_header="news@acme.example",
        subject="x",
        lu_header="<https://acme.example/u/1>",
        lup_header=None,
    )
    assert hit is not None
    assert hit.one_click is False


def test_build_hit_none_without_unsubscribe_header():
    assert build_hit("a@b.example", "s", None, None) is None
    assert build_hit("a@b.example", "s", "no-brackets-here", None) is None


def _msg(from_, subject, lu=None, lup=None):
    headers = {}
    if lu is not None:
        headers["list-unsubscribe"] = (lu,)
    if lup is not None:
        headers["list-unsubscribe-post"] = (lup,)
    return SimpleNamespace(from_=from_, subject=subject, headers=headers)


def test_report_dedupes_by_sender_domain():
    one_click = "List-Unsubscribe=One-Click"
    messages = [
        _msg("news@acme.example", "Latest", "<https://acme.example/u/1>", one_click),
        _msg("promo@acme.example", "Sale", "<https://acme.example/u/2>", one_click),
        _msg("hello@other.example", "Hi", "<mailto:u@other.example>"),
        _msg("noheader@thing.example", "No unsub"),  # skipped, no List-Unsubscribe
    ]
    report = build_report_from_messages(messages)
    assert report.checked == 4
    domains = sorted(h.sender_domain for h in report.hits)
    assert domains == ["acme.example", "other.example"]
