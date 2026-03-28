import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.core.profile import SmtpConfig
from backend.senders.base import SenderResult, SenderStatus
from backend.senders.email import EmailSender


@pytest.fixture
def smtp_config():
    return SmtpConfig(
        host="smtp.test.com",
        port=587,
        username="test@test.com",
        password="test_password",
    )


def test_sender_result_model():
    result = SenderResult(status=SenderStatus.SUCCESS, message="Sent OK")
    assert result.status == SenderStatus.SUCCESS

    fail = SenderResult(status=SenderStatus.FAILURE, message="Connection refused")
    assert fail.status == SenderStatus.FAILURE


def test_email_sender_parse_subject_body():
    text = "Subject: Test Subject\n\nBody line 1\nBody line 2"
    subject, body = EmailSender._parse_rendered(text)
    assert subject == "Test Subject"
    assert "Body line 1" in body
    assert "Body line 2" in body


def test_email_sender_parse_no_subject():
    text = "No subject header here\nJust body text"
    subject, body = EmailSender._parse_rendered(text)
    assert subject == "GDPR Request"
    assert "No subject header here" in body


@pytest.mark.asyncio
async def test_email_sender_send_success(smtp_config):
    sender = EmailSender(smtp_config)

    with patch("backend.senders.email.SMTP") as mock_smtp_cls:
        mock_smtp = AsyncMock()
        mock_smtp_cls.return_value = mock_smtp
        mock_smtp.__aenter__ = AsyncMock(return_value=mock_smtp)
        mock_smtp.__aexit__ = AsyncMock(return_value=False)

        result = await sender.send(
            to_email="dpo@broker.com",
            rendered_text="Subject: Test\n\nBody here",
        )

    assert result.status == SenderStatus.SUCCESS


@pytest.mark.asyncio
async def test_email_sender_send_failure(smtp_config):
    sender = EmailSender(smtp_config)

    with patch("backend.senders.email.SMTP") as mock_smtp_cls:
        mock_smtp_cls.side_effect = ConnectionError("Connection refused")

        result = await sender.send(
            to_email="dpo@broker.com",
            rendered_text="Subject: Test\n\nBody here",
        )

    assert result.status == SenderStatus.FAILURE
    assert "Connection refused" in result.message
