from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from backend.core.broker import BrokerRegistry

if TYPE_CHECKING:
    from backend.core.controller import RegistryUnion
from backend.core.profile import Profile, SmtpConfig
from backend.core.request import RequestManager
from backend.core.template import TemplateRenderer
from backend.db.models import EmailDirection, EmailMessage, Request, RequestEvent, RequestStatus
from backend.senders.email import EmailSender


def _ensure_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (SQLite drops tzinfo on roundtrip)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


@dataclass
class FollowUpResult:
    newly_overdue: int = 0
    follow_ups_sent: int = 0
    escalations_sent: int = 0
    escalated_no_email: int = 0  # no email channel — DPA complaint is the only chase
    errors: list[str] = field(default_factory=list)


async def run_follow_ups(
    session: Session,
    profile: Profile,
    smtp: SmtpConfig | None,
    broker_registry: BrokerRegistry | RegistryUnion,
    renderer: TemplateRenderer,
    gdpr_deadline_days: int = 30,
    escalation_days: int = 7,
) -> FollowUpResult:
    """
    Check all requests and handle overdue/escalation logic.

    1. SENT requests past deadline → mark OVERDUE
    2. OVERDUE requests → send follow-up email (if SMTP configured)
    3. Requests overdue for escalation_days after being marked overdue → send escalation warning
    """
    result = FollowUpResult()
    mgr = RequestManager(session, gdpr_deadline_days)
    now = datetime.now(UTC)

    # Step 1: Find and mark overdue requests
    overdue_requests = mgr.find_overdue()
    for req in overdue_requests:
        try:
            mgr.mark_overdue(req.id)
            result.newly_overdue += 1
        except Exception as e:
            # One session serves the whole run — a dirty state here would
            # fail every request after this one.
            session.rollback()
            result.errors.append(f"Failed to mark {req.broker_id} as overdue: {e}")

    from backend.db.models import BrokerAlias

    # A disabled alias means the user cut off contact with that broker —
    # chasing from the real mailbox would hand it exactly the address the
    # alias hid. Such requests take the no-email-channel path (step 3).
    disabled_alias_ids = {
        a.broker_id
        for a in session.query(BrokerAlias)
        .filter(BrokerAlias.disabled_at.isnot(None))
    }

    # Orphaned requests (broker left the registry) can never be chased or
    # escalated automatically — surface them instead of skipping forever.
    for req in (
        session.query(Request).filter(Request.status == RequestStatus.OVERDUE).all()
    ):
        if broker_registry.get(req.broker_id) is None:
            result.errors.append(
                f"Request {req.id[:8].upper()} references unknown broker "
                f"{req.broker_id} — not in the registry; chase it manually"
            )

    # Step 2: Send follow-ups for OVERDUE requests that haven't had a follow-up yet
    if smtp is not None:
        from backend.core.alias_resolver import resolve_recipient

        sender = EmailSender(smtp)

        all_overdue = (
            session.query(Request)
            .filter(Request.status == RequestStatus.OVERDUE)
            .all()
        )

        # Pre-fetch all events for overdue requests in a single query
        overdue_ids = [req.id for req in all_overdue]
        all_events = (
            session.query(RequestEvent)
            .filter(RequestEvent.request_id.in_(overdue_ids))
            .all()
        ) if overdue_ids else []
        events_by_request: dict[str, list[RequestEvent]] = {}
        for ev in all_events:
            events_by_request.setdefault(ev.request_id, []).append(ev)

        for req in all_overdue:
            broker = broker_registry.get(req.broker_id)
            # Form-only controllers have no email address to chase, and
            # disabled-alias brokers must not be contacted at all — both
            # escalate via the DPA complaint instead. Unknown brokers were
            # already reported above.
            if (
                broker is None or not broker.dpo_email
                or req.broker_id in disabled_alias_ids
            ):
                continue

            events = events_by_request.get(req.id, [])
            event_types = [e.event_type for e in events]

            if "follow_up_sent" not in event_types:
                # Send follow-up using broker's language
                try:
                    rendered = renderer.render_localized(
                        "follow_up",
                        broker.language,
                        profile=profile,
                        reference_id=req.id[:8].upper(),
                        broker_name=broker.name,
                        original_date=(
                            req.sent_at.strftime("%Y-%m-%d") if req.sent_at else "unknown"
                        ),
                    )
                    # A thread aliased at blast time must be chased through
                    # the same alias. Reuse-only: no row means the original
                    # went from the real mailbox — never mint mid-thread.
                    # Reuse is a DB lookup, so no API key is needed (or
                    # wanted: chases must work even after the key is removed).
                    smtp_to, alias_email = await resolve_recipient(
                        session, None, req.broker_id,
                        broker.dpo_email, mint=False,
                    )
                    send_result = await sender.send(
                        to_email=smtp_to, rendered_text=rendered,
                        request_id=req.id,
                    )

                    if send_result.status.value == "success":
                        outbound = EmailMessage(
                            request_id=req.id,
                            message_id=f"<{uuid.uuid4()}@incognito.local>",
                            direction=EmailDirection.OUTBOUND,
                            from_address=alias_email or smtp.username,
                            to_address=broker.dpo_email,
                            subject=f"Follow-Up [REF-{req.id[:8].upper()}]",
                            body_text=rendered,
                        )
                        session.add(outbound)
                        event = RequestEvent(
                            request_id=req.id,
                            event_type="follow_up_sent",
                            details=f"Follow-up sent to {broker.dpo_email}",
                        )
                        session.add(event)
                        session.commit()
                        result.follow_ups_sent += 1
                    else:
                        result.errors.append(
                            f"Failed to send follow-up to {broker.name}: {send_result.message}"
                        )
                except Exception as e:
                    session.rollback()
                    result.errors.append(
                        f"Error sending follow-up to {broker.name}: {e}"
                    )

            if "follow_up_sent" in event_types and "escalation_sent" not in event_types:
                # Check if enough time has passed since the follow-up for escalation
                follow_up_event = next(
                    (e for e in events if e.event_type == "follow_up_sent"), None,
                )
                if not follow_up_event:
                    continue
                aware_ts = _ensure_aware(follow_up_event.created_at)
                if (now - aware_ts).total_seconds() >= escalation_days * 86400:
                    try:
                        rendered = renderer.render_localized(
                            "escalation_warning",
                            broker.language,
                            profile=profile,
                            reference_id=req.id[:8].upper(),
                            broker_name=broker.name,
                            original_date=(
                                req.sent_at.strftime("%Y-%m-%d") if req.sent_at else "unknown"
                            ),
                        )
                        smtp_to, alias_email = await resolve_recipient(
                            session, None, req.broker_id,
                            broker.dpo_email, mint=False,
                        )
                        send_result = await sender.send(
                            to_email=smtp_to, rendered_text=rendered,
                            request_id=req.id,
                        )

                        if send_result.status.value == "success":
                            outbound = EmailMessage(
                                request_id=req.id,
                                message_id=f"<{uuid.uuid4()}@incognito.local>",
                                direction=EmailDirection.OUTBOUND,
                                from_address=alias_email or smtp.username,
                                to_address=broker.dpo_email,
                                subject=f"Escalation Warning [REF-{req.id[:8].upper()}]",
                                body_text=rendered,
                            )
                            session.add(outbound)
                            mgr.mark_escalated(req.id)
                            event = RequestEvent(
                                request_id=req.id,
                                event_type="escalation_sent",
                                details=f"Escalation warning sent to {broker.dpo_email}",
                            )
                            session.add(event)
                            session.commit()
                            result.escalations_sent += 1
                        else:
                            result.errors.append(
                                f"Failed to send escalation to {broker.name}: "
                                f"{send_result.message}"
                            )
                    except Exception as e:
                        session.rollback()
                        result.errors.append(
                            f"Error sending escalation to {broker.name}: {e}"
                        )

    # Step 3: Overdue entries with no email channel (form-only controllers)
    # cannot be chased by mail — after the escalation window, move them to
    # ESCALATED so the DPA-complaint path opens instead of stalling OVERDUE.
    still_overdue = (
        session.query(Request)
        .filter(Request.status == RequestStatus.OVERDUE)
        .all()
    )
    for req in still_overdue:
        broker = broker_registry.get(req.broker_id)
        if broker is None:
            continue
        if broker.dpo_email and req.broker_id not in disabled_alias_ids:
            continue
        overdue_ev = (
            session.query(RequestEvent)
            .filter(
                RequestEvent.request_id == req.id,
                RequestEvent.event_type == "overdue",
            )
            .first()
        )
        if overdue_ev is None:
            continue
        overdue_at = _ensure_aware(overdue_ev.created_at)
        if (now - overdue_at).total_seconds() < escalation_days * 86400:
            continue
        reason = (
            f"Alias for {broker.name} is disabled — no direct contact"
            if req.broker_id in disabled_alias_ids
            else f"No email channel for {broker.name}"
        )
        try:
            mgr.mark_escalated(req.id)
            session.add(RequestEvent(
                request_id=req.id,
                event_type="escalation_due",
                details=f"{reason} — escalate via a DPA complaint",
            ))
            session.commit()
            result.escalated_no_email += 1

            from backend.core.notifier import EventType, notify
            notify(
                EventType.ESCALATION_SENT,
                f"{broker.name}: escalate via DPA complaint",
                f"Request {req.id[:8].upper()} is overdue. {reason} — "
                "generate the DPA complaint from the request page.",
            )
        except Exception as e:
            session.rollback()
            result.errors.append(f"Failed to escalate {req.broker_id}: {e}")

    return result
