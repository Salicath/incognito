"""Comprehensive tests for run_follow_ups() — GDPR deadline enforcement logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.core.broker import Broker, BrokerRegistry, RemovalMethod
from backend.core.profile import Profile, SmtpConfig
from backend.core.request import RequestManager
from backend.core.scheduler import run_follow_ups
from backend.core.template import TemplateRenderer
from backend.db.models import (
    Base,
    EmailDirection,
    EmailMessage,
    Request,
    RequestEvent,
    RequestStatus,
    RequestType,
)
from backend.senders.base import SenderResult, SenderStatus

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def make_profile() -> Profile:
    return Profile(full_name="Test User", emails=["test@example.com"])


def make_smtp() -> SmtpConfig:
    return SmtpConfig(host="smtp.test.com", port=587, username="test@test.com", password="pw")


def make_broker(name: str = "Test Broker", domain: str = "testbroker.com") -> Broker:
    return Broker(
        name=name,
        domain=domain,
        category="data_broker",
        dpo_email=f"dpo@{domain}",
        removal_method=RemovalMethod.EMAIL,
        country="DE",
        gdpr_applies=True,
        verification_required=False,
        language="en",
        last_verified="2026-03-28",
    )


def make_renderer() -> TemplateRenderer:
    templates_dir = Path(__file__).parent.parent.parent / "templates"
    return TemplateRenderer(templates_dir)


def _create_sent_request(
    session: Session,
    broker_id: str,
    *,
    deadline_offset_days: int = 30,
    sent_offset_days: int = 0,
) -> Request:
    """Create a request in SENT status with configurable deadline and sent_at."""
    mgr = RequestManager(session)
    req = mgr.create(broker_id, RequestType.ERASURE)
    mgr.mark_sent(req.id)

    now = datetime.now(UTC)
    req.sent_at = now - timedelta(days=sent_offset_days)
    req.deadline_at = now + timedelta(days=deadline_offset_days)
    session.commit()
    return req


def _create_overdue_request(session: Session, broker_id: str) -> Request:
    """Create a request already in OVERDUE status."""
    req = _create_sent_request(session, broker_id, deadline_offset_days=-1)
    mgr = RequestManager(session)
    mgr.mark_overdue(req.id)
    return req


def _success_result() -> SenderResult:
    return SenderResult(status=SenderStatus.SUCCESS, message="Sent")


def _failure_result() -> SenderResult:
    return SenderResult(status=SenderStatus.FAILURE, message="SMTP error")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marks_overdue_requests():
    """SENT request past deadline is marked OVERDUE by run_follow_ups."""
    session = make_session()
    broker = make_broker()
    registry = BrokerRegistry([broker])

    req = _create_sent_request(session, broker.id, deadline_offset_days=-1)

    result = await run_follow_ups(
        session=session,
        profile=make_profile(),
        smtp=None,
        broker_registry=registry,
        renderer=make_renderer(),
    )

    session.refresh(req)
    assert req.status == RequestStatus.OVERDUE
    assert result.newly_overdue == 1


@pytest.mark.asyncio
async def test_ignores_requests_within_deadline():
    """SENT request whose deadline is still in the future stays SENT."""
    session = make_session()
    broker = make_broker()
    registry = BrokerRegistry([broker])

    req = _create_sent_request(session, broker.id, deadline_offset_days=10)

    result = await run_follow_ups(
        session=session,
        profile=make_profile(),
        smtp=None,
        broker_registry=registry,
        renderer=make_renderer(),
    )

    session.refresh(req)
    assert req.status == RequestStatus.SENT
    assert result.newly_overdue == 0


@pytest.mark.asyncio
async def test_sends_follow_up_email():
    """OVERDUE request gets a follow-up email; event and counter recorded."""
    session = make_session()
    broker = make_broker()
    registry = BrokerRegistry([broker])
    smtp = make_smtp()

    req = _create_overdue_request(session, broker.id)

    with patch(
        "backend.core.scheduler.EmailSender.send",
        new_callable=AsyncMock,
        return_value=_success_result(),
    ) as mock_send:
        result = await run_follow_ups(
            session=session,
            profile=make_profile(),
            smtp=smtp,
            broker_registry=registry,
            renderer=make_renderer(),
        )

    # Verify send was called with correct broker email and request_id
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args
    assert call_kwargs.kwargs["to_email"] == broker.dpo_email
    assert call_kwargs.kwargs["request_id"] == req.id

    # Verify follow_up_sent event was created
    events = session.query(RequestEvent).filter_by(request_id=req.id).all()
    event_types = [e.event_type for e in events]
    assert "follow_up_sent" in event_types

    assert result.follow_ups_sent == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_skips_follow_up_if_already_sent():
    """No duplicate follow-up if follow_up_sent event already exists."""
    session = make_session()
    broker = make_broker()
    registry = BrokerRegistry([broker])
    smtp = make_smtp()

    req = _create_overdue_request(session, broker.id)

    # Manually create the follow_up_sent event
    event = RequestEvent(
        request_id=req.id,
        event_type="follow_up_sent",
        details="Already sent",
    )
    session.add(event)
    session.commit()

    with patch(
        "backend.core.scheduler.EmailSender.send",
        new_callable=AsyncMock,
        return_value=_success_result(),
    ) as mock_send:
        result = await run_follow_ups(
            session=session,
            profile=make_profile(),
            smtp=smtp,
            broker_registry=registry,
            renderer=make_renderer(),
            escalation_days=7,
        )

    # follow_up_sent exists but escalation_sent does not, and the
    # follow_up_sent event was just created (< 7 days ago), so no escalation
    # either. send() should NOT have been called.
    mock_send.assert_not_called()
    assert result.follow_ups_sent == 0
    assert result.escalations_sent == 0


@pytest.mark.asyncio
async def test_sends_escalation_after_delay():
    """Escalation sent when follow-up was sent >= escalation_days ago."""
    session = make_session()
    broker = make_broker()
    registry = BrokerRegistry([broker])
    smtp = make_smtp()

    req = _create_overdue_request(session, broker.id)

    # Create a follow_up_sent event from 8 days ago
    follow_up_event = RequestEvent(
        request_id=req.id,
        event_type="follow_up_sent",
        details="Follow-up sent",
    )
    session.add(follow_up_event)
    session.commit()
    # Backdate the event
    follow_up_event.created_at = datetime.now(UTC) - timedelta(days=8)
    session.commit()

    with patch(
        "backend.core.scheduler.EmailSender.send",
        new_callable=AsyncMock,
        return_value=_success_result(),
    ) as mock_send:
        result = await run_follow_ups(
            session=session,
            profile=make_profile(),
            smtp=smtp,
            broker_registry=registry,
            renderer=make_renderer(),
            escalation_days=7,
        )

    # Escalation email should have been sent
    mock_send.assert_called_once()
    assert result.escalations_sent == 1

    # Request should be marked ESCALATED
    session.refresh(req)
    assert req.status == RequestStatus.ESCALATED

    # escalation_sent event should exist
    events = session.query(RequestEvent).filter_by(request_id=req.id).all()
    event_types = [e.event_type for e in events]
    assert "escalation_sent" in event_types


@pytest.mark.asyncio
async def test_skips_escalation_if_too_soon():
    """No escalation if follow-up was sent only 3 days ago (< escalation_days)."""
    session = make_session()
    broker = make_broker()
    registry = BrokerRegistry([broker])
    smtp = make_smtp()

    req = _create_overdue_request(session, broker.id)

    follow_up_event = RequestEvent(
        request_id=req.id,
        event_type="follow_up_sent",
        details="Follow-up sent",
    )
    session.add(follow_up_event)
    session.commit()
    follow_up_event.created_at = datetime.now(UTC) - timedelta(days=3)
    session.commit()

    with patch(
        "backend.core.scheduler.EmailSender.send",
        new_callable=AsyncMock,
        return_value=_success_result(),
    ) as mock_send:
        result = await run_follow_ups(
            session=session,
            profile=make_profile(),
            smtp=smtp,
            broker_registry=registry,
            renderer=make_renderer(),
            escalation_days=7,
        )

    mock_send.assert_not_called()
    assert result.escalations_sent == 0
    assert result.follow_ups_sent == 0


@pytest.mark.asyncio
async def test_no_follow_up_without_smtp():
    """With smtp=None, overdue marking works but no emails are sent."""
    session = make_session()
    broker = make_broker()
    registry = BrokerRegistry([broker])

    # One past-deadline request (will become overdue)
    req_past = _create_sent_request(session, broker.id, deadline_offset_days=-5)

    # One already-overdue request (would normally get a follow-up email)
    broker2 = make_broker(name="Other Broker", domain="other.com")
    registry = BrokerRegistry([broker, broker2])
    _create_overdue_request(session, broker2.id)

    result = await run_follow_ups(
        session=session,
        profile=make_profile(),
        smtp=None,
        broker_registry=registry,
        renderer=make_renderer(),
    )

    # Overdue marking still works
    session.refresh(req_past)
    assert req_past.status == RequestStatus.OVERDUE
    assert result.newly_overdue == 1

    # But no emails were sent
    assert result.follow_ups_sent == 0
    assert result.escalations_sent == 0

    # No EmailMessage records created
    email_count = session.query(EmailMessage).count()
    assert email_count == 0


@pytest.mark.asyncio
async def test_stores_outbound_email_message():
    """Successful follow-up creates an OUTBOUND EmailMessage record."""
    session = make_session()
    broker = make_broker()
    registry = BrokerRegistry([broker])
    smtp = make_smtp()

    req = _create_overdue_request(session, broker.id)

    with patch(
        "backend.core.scheduler.EmailSender.send",
        new_callable=AsyncMock,
        return_value=_success_result(),
    ):
        await run_follow_ups(
            session=session,
            profile=make_profile(),
            smtp=smtp,
            broker_registry=registry,
            renderer=make_renderer(),
        )

    emails = session.query(EmailMessage).filter_by(request_id=req.id).all()
    assert len(emails) == 1

    email = emails[0]
    assert email.direction == EmailDirection.OUTBOUND
    assert email.to_address == broker.dpo_email
    assert email.from_address == smtp.username
    assert "Follow-Up" in email.subject
    assert email.body_text  # non-empty rendered template


@pytest.mark.asyncio
async def test_collects_errors_without_stopping():
    """Send failure on first request doesn't prevent second request from being attempted."""
    session = make_session()
    broker_a = make_broker(name="Broker A", domain="broker-a.com")
    broker_b = make_broker(name="Broker B", domain="broker-b.com")
    registry = BrokerRegistry([broker_a, broker_b])
    smtp = make_smtp()

    _create_overdue_request(session, broker_a.id)
    _create_overdue_request(session, broker_b.id)

    # First call raises, second succeeds
    mock_send = AsyncMock(
        side_effect=[Exception("SMTP connection refused"), _success_result()],
    )

    with patch("backend.core.scheduler.EmailSender.send", mock_send):
        result = await run_follow_ups(
            session=session,
            profile=make_profile(),
            smtp=smtp,
            broker_registry=registry,
            renderer=make_renderer(),
        )

    # Both requests were attempted
    assert mock_send.call_count == 2

    # One succeeded, one failed
    assert result.follow_ups_sent == 1
    assert len(result.errors) == 1
    assert "Broker" in result.errors[0]
