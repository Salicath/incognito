"""Tests for the notification system."""
from unittest.mock import patch

from backend.core.notifier import EventType, Notifier, init_notifier, notify


def test_notifier_detect_ntfy():
    n = Notifier("https://ntfy.sh/my-topic")
    assert n._kind == "ntfy"


def test_notifier_detect_ntfy_self_hosted():
    n = Notifier("https://push.example.com/incognito")
    assert n._kind == "ntfy"


def test_notifier_detect_gotify():
    n = Notifier("https://gotify.example.com/message?token=abc")
    assert n._kind == "gotify"


def test_notifier_detect_webhook():
    n = Notifier("https://example.com/hooks/privacy/alert")
    assert n._kind == "webhook"


@patch("backend.core.notifier.httpx.post")
def test_ntfy_sends_correct_headers(mock_post):
    n = Notifier("https://ntfy.sh/my-topic")
    n.send(EventType.REPLY_RECEIVED, "Test Title", "Test body")

    mock_post.assert_called_once()
    call = mock_post.call_args
    assert call.kwargs["headers"]["Title"] == "Test Title"
    assert call.kwargs["headers"]["Priority"] == "3"
    assert call.kwargs["headers"]["Tags"] == "incoming_envelope"
    assert call.kwargs["content"] == b"Test body"


@patch("backend.core.notifier.httpx.post")
def test_ntfy_high_priority_for_reappearance(mock_post):
    n = Notifier("https://ntfy.sh/topic")
    n.send(EventType.DATA_REAPPEARED, "Alert", "Data found again")

    call = mock_post.call_args
    assert call.kwargs["headers"]["Priority"] == "5"
    assert call.kwargs["headers"]["Tags"] == "bangbang"


@patch("backend.core.notifier.httpx.post")
def test_gotify_sends_json(mock_post):
    n = Notifier("https://gotify.example.com/message?token=abc")
    n.send(EventType.BLAST_COMPLETE, "Done", "10 sent")

    call = mock_post.call_args
    assert call.kwargs["json"]["title"] == "Done"
    assert call.kwargs["json"]["message"] == "10 sent"
    assert call.kwargs["json"]["priority"] == 3


@patch("backend.core.notifier.httpx.post")
def test_webhook_sends_json_with_event(mock_post):
    n = Notifier("https://example.com/hooks/privacy/alert")
    n.send(EventType.NEW_EXPOSURE, "New", "Found on broker.com")

    call = mock_post.call_args
    assert call.kwargs["json"]["event"] == "new_exposure"
    assert call.kwargs["json"]["title"] == "New"
    assert call.kwargs["json"]["body"] == "Found on broker.com"


@patch("backend.core.notifier.httpx.post", side_effect=Exception("network error"))
def test_send_never_raises(mock_post):
    """Notifications must never crash the calling code."""
    n = Notifier("https://ntfy.sh/topic")
    # Should not raise
    n.send(EventType.REPLY_RECEIVED, "Test", "body")


def test_notify_without_init():
    """notify() is safe to call even when not initialized."""
    import backend.core.notifier as mod
    old = mod._instance
    mod._instance = None
    try:
        notify(EventType.BLAST_COMPLETE, "test", "body")  # should not raise
    finally:
        mod._instance = old


@patch("backend.core.notifier.httpx.post")
def test_init_and_notify(mock_post):
    import backend.core.notifier as mod
    old = mod._instance
    try:
        init_notifier("https://ntfy.sh/test-topic")
        notify(EventType.BLAST_COMPLETE, "Blast done", "5 sent")
        mock_post.assert_called_once()
    finally:
        mod._instance = old


def test_init_notifier_empty_url():
    """Empty URL should not create a notifier."""
    import backend.core.notifier as mod
    old = mod._instance
    try:
        mod._instance = None
        init_notifier("")
        assert mod._instance is None
    finally:
        mod._instance = old
