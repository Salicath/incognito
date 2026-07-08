import httpx
import pytest

from backend.core.unsubscribe import is_safe_url, one_click_unsubscribe


def test_is_safe_url_rejects_non_https():
    assert is_safe_url("http://8.8.8.8/unsub") is False
    assert is_safe_url("mailto:u@x.example") is False
    assert is_safe_url("ftp://8.8.8.8/x") is False


def test_is_safe_url_rejects_private_and_loopback():
    assert is_safe_url("https://127.0.0.1/unsub") is False
    assert is_safe_url("https://10.0.0.5/unsub") is False
    assert is_safe_url("https://192.168.1.1/unsub") is False
    assert is_safe_url("https://169.254.1.1/unsub") is False


def test_is_safe_url_rejects_cgnat_shared_space():
    # 100.64.0.0/10 (CGNAT / Tailscale) is non-global but has is_private=False —
    # the is_global guard is what rejects it.
    assert is_safe_url("https://100.64.0.1/unsub") is False
    assert is_safe_url("https://100.127.255.254/unsub") is False


def test_is_safe_url_allows_public_ip():
    # IP literal — getaddrinfo does not hit the network.
    assert is_safe_url("https://8.8.8.8/unsub") is True


@pytest.mark.asyncio
async def test_one_click_posts_exact_body_and_succeeds_on_2xx():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content"] = request.content
        captured["ctype"] = request.headers.get("content-type")
        captured["method"] = request.method
        return httpx.Response(200)

    ok, detail = await one_click_unsubscribe(
        "https://8.8.8.8/unsub",
        transport=httpx.MockTransport(handler),
    )
    assert ok is True
    assert captured["content"] == b"List-Unsubscribe=One-Click"
    assert captured["ctype"] == "application/x-www-form-urlencoded"
    assert captured["method"] == "POST"


@pytest.mark.asyncio
async def test_one_click_fails_on_non_2xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    ok, detail = await one_click_unsubscribe(
        "https://8.8.8.8/unsub",
        transport=httpx.MockTransport(handler),
    )
    assert ok is False
    assert "500" in detail


@pytest.mark.asyncio
async def test_one_click_refuses_unsafe_url():
    ok, detail = await one_click_unsubscribe("https://127.0.0.1/unsub")
    assert ok is False
    assert "safe" in detail.lower()
