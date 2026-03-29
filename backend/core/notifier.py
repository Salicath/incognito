"""Push notifications via Ntfy, Gotify, or generic webhooks.

Configure with INCOGNITO_NOTIFY_URL:
  Ntfy:    https://ntfy.sh/my-incognito-topic
  Gotify:  https://gotify.example.com/message?token=XXX
  Webhook: https://example.com/webhook (receives JSON POST)
"""

import enum
import logging
from urllib.parse import urlparse

import httpx

log = logging.getLogger("incognito.notifier")

_instance: "Notifier | None" = None


class EventType(enum.StrEnum):
    REPLY_RECEIVED = "reply_received"
    REQUEST_OVERDUE = "request_overdue"
    ESCALATION_SENT = "escalation_sent"
    DATA_REAPPEARED = "data_reappeared"
    NEW_EXPOSURE = "new_exposure"
    BLAST_COMPLETE = "blast_complete"
    FOLLOW_UP_COMPLETE = "follow_up_complete"


# Map event types to Ntfy priorities and tags
_NTFY_META: dict[EventType, tuple[str, str]] = {
    EventType.REPLY_RECEIVED: ("3", "incoming_envelope"),
    EventType.REQUEST_OVERDUE: ("4", "warning"),
    EventType.ESCALATION_SENT: ("4", "rotating_light"),
    EventType.DATA_REAPPEARED: ("5", "bangbang"),
    EventType.NEW_EXPOSURE: ("4", "eyes"),
    EventType.BLAST_COMPLETE: ("3", "outbox_tray"),
    EventType.FOLLOW_UP_COMPLETE: ("3", "calendar"),
}


def init_notifier(url: str) -> None:
    """Initialize the global notifier. Call once at startup."""
    global _instance
    if url:
        _instance = Notifier(url)


def notify(event: EventType, title: str, body: str) -> None:
    """Send a notification if configured. Safe to call even when not configured."""
    if _instance:
        _instance.send(event, title, body)


class Notifier:
    """Sends push notifications for privacy-relevant events."""

    def __init__(self, notify_url: str):
        self._url = notify_url.rstrip("/")
        self._kind = self._detect_kind()
        log.info("Notifications enabled via %s", self._kind)

    def _detect_kind(self) -> str:
        parsed = urlparse(self._url)
        hostname = parsed.hostname or ""
        if "gotify" in hostname or "/message" in parsed.path:
            return "gotify"
        if "ntfy" in hostname or parsed.path.count("/") == 1:
            return "ntfy"
        return "webhook"

    def send(self, event: EventType, title: str, body: str) -> None:
        """Send a notification. Never raises — logs errors instead."""
        try:
            if self._kind == "ntfy":
                self._send_ntfy(event, title, body)
            elif self._kind == "gotify":
                self._send_gotify(event, title, body)
            else:
                self._send_webhook(event, title, body)
            log.debug("Notification sent: %s — %s", event, title)
        except Exception:
            log.warning("Failed to send notification: %s", title, exc_info=True)

    def _send_ntfy(self, event: EventType, title: str, body: str) -> None:
        priority, tags = _NTFY_META.get(event, ("3", "bell"))
        httpx.post(
            self._url,
            content=body.encode(),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": tags,
            },
            timeout=10,
        )

    def _send_gotify(self, event: EventType, title: str, body: str) -> None:
        priority, _ = _NTFY_META.get(event, ("3", "bell"))
        httpx.post(
            self._url,
            json={
                "title": title,
                "message": body,
                "priority": int(priority),
            },
            timeout=10,
        )

    def _send_webhook(self, event: EventType, title: str, body: str) -> None:
        httpx.post(
            self._url,
            json={
                "event": event.value,
                "title": title,
                "body": body,
            },
            timeout=10,
        )
