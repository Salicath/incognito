from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from backend.core.broker import BrokerRegistry
from backend.core.profile import Profile, SmtpConfig
from backend.core.request import RequestManager
from backend.core.template import TemplateRenderer
from backend.db.models import Request, RequestEvent, RequestStatus, RequestType
from backend.senders.email import EmailSender


@dataclass
class FollowUpResult:
    newly_overdue: int = 0
    follow_ups_sent: int = 0
    escalations_sent: int = 0
    errors: list[str] = field(default_factory=list)


async def run_follow_ups(
    session: Session,
    profile: Profile,
    smtp: SmtpConfig | None,
    broker_registry: BrokerRegistry,
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
    now = datetime.now(timezone.utc)

    # Step 1: Find and mark overdue requests
    overdue_requests = mgr.find_overdue()
    for req in overdue_requests:
        try:
            mgr.mark_overdue(req.id)
            result.newly_overdue += 1
        except Exception as e:
            result.errors.append(f"Failed to mark {req.broker_id} as overdue: {e}")

    # Step 2: Send follow-ups for OVERDUE requests that haven't had a follow-up yet
    if smtp is not None:
        sender = EmailSender(smtp)

        all_overdue = (
            session.query(Request)
            .filter(Request.status == RequestStatus.OVERDUE)
            .all()
        )

        for req in all_overdue:
            broker = broker_registry.get(req.broker_id)
            if broker is None:
                continue

            # Check if we already sent a follow-up for this request
            events = (
                session.query(RequestEvent)
                .filter_by(request_id=req.id)
                .all()
            )
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
                        original_date=req.sent_at.strftime("%Y-%m-%d") if req.sent_at else "unknown",
                    )
                    send_result = await sender.send(to_email=broker.dpo_email, rendered_text=rendered)

                    if send_result.status.value == "success":
                        event = RequestEvent(
                            request_id=req.id,
                            event_type="follow_up_sent",
                            details=f"Follow-up sent to {broker.dpo_email}",
                        )
                        session.add(event)
                        session.commit()
                        result.follow_ups_sent += 1
                    else:
                        result.errors.append(f"Failed to send follow-up to {broker.name}: {send_result.message}")
                except Exception as e:
                    result.errors.append(f"Error sending follow-up to {broker.name}: {e}")

            elif "escalation_sent" not in event_types:
                # Check if enough time has passed since the follow-up for escalation
                follow_up_event = next((e for e in events if e.event_type == "follow_up_sent"), None)
                if follow_up_event and (now - follow_up_event.created_at).days >= escalation_days:
                    try:
                        rendered = renderer.render_localized(
                            "escalation_warning",
                            broker.language,
                            profile=profile,
                            reference_id=req.id[:8].upper(),
                            broker_name=broker.name,
                            original_date=req.sent_at.strftime("%Y-%m-%d") if req.sent_at else "unknown",
                        )
                        send_result = await sender.send(to_email=broker.dpo_email, rendered_text=rendered)

                        if send_result.status.value == "success":
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
                            result.errors.append(f"Failed to send escalation to {broker.name}: {send_result.message}")
                    except Exception as e:
                        result.errors.append(f"Error sending escalation to {broker.name}: {e}")

    return result
