from __future__ import annotations

import logging
from email.message import EmailMessage

from aiosmtplib import SMTP

from backend.core.profile import SmtpConfig
from backend.senders.base import SenderResult, SenderStatus

log = logging.getLogger("incognito.email")


class EmailSender:
    def __init__(self, smtp_config: SmtpConfig):
        self._config = smtp_config

    @staticmethod
    def _sanitize_header(value: str) -> str:
        """Strip CR/LF from a header value.

        Header content can originate untrusted — a newsletter's List-Unsubscribe
        mailto carries a `?subject=` we render verbatim. A percent-encoded CRLF
        there is an email header-injection attempt; EmailMessage rejects it with
        an unhandled ValueError (a 500), so neutralize it before we get there.
        """
        return value.replace("\r", " ").replace("\n", " ").strip()

    @staticmethod
    def _parse_rendered(text: str) -> tuple[str, str]:
        lines = text.strip().split("\n")
        if lines and lines[0].startswith("Subject:"):
            subject = lines[0][len("Subject:"):].strip()
            body = "\n".join(lines[1:]).strip()
            return subject or "GDPR Request", body
        return "GDPR Request", text.strip()

    def build_message(
        self, to_email: str, rendered_text: str, request_id: str | None = None,
        cc: list[str] | None = None,
    ) -> EmailMessage:
        subject, body = self._parse_rendered(rendered_text)

        if request_id:
            ref_code = request_id.split("-")[0].upper()[:8]
            subject = f"{subject} [REF-{ref_code}]"

        msg = EmailMessage()
        msg["From"] = self._config.username
        msg["To"] = self._sanitize_header(to_email)
        if cc:
            msg["Cc"] = ", ".join(self._sanitize_header(c) for c in cc)
        msg["Subject"] = self._sanitize_header(subject)
        msg.set_content(body)

        if request_id:
            msg["Message-ID"] = f"<{request_id}@incognito.local>"

        return msg

    async def send(
        self, to_email: str, rendered_text: str, request_id: str | None = None,
        cc: list[str] | None = None,
    ) -> SenderResult:
        msg = self.build_message(to_email, rendered_text, request_id, cc=cc)

        try:
            async with SMTP(
                hostname=self._config.host,
                port=self._config.port,
                start_tls=True,
            ) as smtp:
                await smtp.login(self._config.username, self._config.password)
                await smtp.send_message(msg)

            return SenderResult(status=SenderStatus.SUCCESS, message=f"Sent to {to_email}")
        except Exception as exc:
            log.error("SMTP send to %s failed: %s", to_email, exc)
            return SenderResult(
                status=SenderStatus.FAILURE,
                message=f"Failed to send to {to_email}. Check SMTP settings.",
            )
