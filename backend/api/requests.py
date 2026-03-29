from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import SessionStore
from backend.core.request import InvalidTransitionError, RequestManager
from backend.db.models import (
    EmailMessage,
    Request,
    RequestEvent,
    RequestStatus,
    RequestType,
    ScanResult,
)


def create_requests_router(
    db_session_factory, session_store: SessionStore, gdpr_deadline_days: int,
    broker_registry=None,
) -> APIRouter:
    r = APIRouter(prefix="/api/requests", tags=["requests"])

    class CreateRequest(BaseModel):
        broker_id: str
        request_type: RequestType

    class TransitionRequest(BaseModel):
        action: str
        details: str | None = None

    def _get_db() -> Session:
        return db_session_factory()

    @r.get("/stats")
    def stats(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = _get_db()
        try:
            all_requests = db.query(Request).all()
            counts = {}
            for status in RequestStatus:
                counts[status.value] = sum(1 for req in all_requests if req.status == status)
            counts["total"] = len(all_requests)
            counts["broker_count"] = len(broker_registry.brokers) if broker_registry else 0
            counts["unread_replies"] = (
                db.query(Request)
                .filter(
                    Request.status == RequestStatus.ACKNOWLEDGED,
                    Request.response_at.isnot(None),
                    Request.reply_read_at.is_(None),
                )
                .count()
            )
            # Scan exposure stats
            exposures_found = db.query(ScanResult).count()
            exposures_actioned = (
                db.query(ScanResult).filter(ScanResult.actioned.is_(True)).count()
            )
            counts["exposures_found"] = exposures_found
            counts["exposures_actioned"] = exposures_actioned
            return counts
        finally:
            db.close()

    @r.get("")
    def list_requests(
        status: str | None = None,
        session: str | None = Cookie(default=None),
    ):
        session_store.validate(session)
        db = _get_db()
        try:
            query = db.query(Request)
            if status:
                query = query.filter(Request.status == status)
            requests = query.order_by(Request.created_at.desc()).all()
            results = []
            for req in requests:
                item = {
                    "id": req.id,
                    "broker_id": req.broker_id,
                    "request_type": req.request_type.value,
                    "status": req.status.value,
                    "sent_at": req.sent_at.isoformat() if req.sent_at else None,
                    "deadline_at": req.deadline_at.isoformat() if req.deadline_at else None,
                    "created_at": req.created_at.isoformat() if req.created_at else None,
                }
                if broker_registry:
                    broker = broker_registry.get(req.broker_id)
                    if broker:
                        item["broker_name"] = broker.name
                results.append(item)
            return results
        finally:
            db.close()

    @r.post("")
    def create_request(body: CreateRequest, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = _get_db()
        try:
            mgr = RequestManager(db, gdpr_deadline_days)
            req = mgr.create(body.broker_id, body.request_type)
            return {
                "id": req.id,
                "broker_id": req.broker_id,
                "request_type": req.request_type.value,
                "status": req.status.value,
            }
        finally:
            db.close()

    @r.get("/{request_id}")
    def get_request(request_id: str, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = _get_db()
        try:
            req = db.get(Request, request_id)
            if req is None:
                raise HTTPException(status_code=404, detail="Request not found")
            result = {
                "id": req.id,
                "broker_id": req.broker_id,
                "request_type": req.request_type.value,
                "status": req.status.value,
                "sent_at": req.sent_at.isoformat() if req.sent_at else None,
                "deadline_at": req.deadline_at.isoformat() if req.deadline_at else None,
                "response_at": req.response_at.isoformat() if req.response_at else None,
                "response_body": req.response_body,
                "created_at": req.created_at.isoformat() if req.created_at else None,
                "updated_at": req.updated_at.isoformat() if req.updated_at else None,
            }
            if broker_registry:
                broker = broker_registry.get(req.broker_id)
                if broker:
                    result["broker"] = {
                        "name": broker.name,
                        "domain": broker.domain,
                        "dpo_email": broker.dpo_email,
                        "removal_method": broker.removal_method.value,
                        "country": broker.country,
                        "language": broker.language,
                    }

            emails = (
                db.query(EmailMessage)
                .filter_by(request_id=request_id)
                .order_by(EmailMessage.received_at)
                .all()
            )
            result["email_messages"] = [
                {
                    "id": e.id,
                    "direction": e.direction.value,
                    "from_address": e.from_address,
                    "to_address": e.to_address,
                    "subject": e.subject,
                    "body_text": e.body_text,
                    "received_at": e.received_at.isoformat() if e.received_at else None,
                }
                for e in emails
            ]

            # Mark replies as read
            if emails and req.reply_read_at is None:
                has_inbound = any(e.direction.value == "inbound" for e in emails)
                if has_inbound:
                    req.reply_read_at = datetime.now(UTC)
                    db.commit()

            return result
        finally:
            db.close()

    @r.get("/{request_id}/events")
    def get_events(request_id: str, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = _get_db()
        try:
            events = (
                db.query(RequestEvent)
                .filter_by(request_id=request_id)
                .order_by(RequestEvent.id)
                .all()
            )
            return [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "details": e.details,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ]
        finally:
            db.close()

    @r.post("/{request_id}/transition")
    def transition(
        request_id: str, body: TransitionRequest, session: str | None = Cookie(default=None)
    ):
        session_store.validate(session)
        db = _get_db()
        try:
            mgr = RequestManager(db, gdpr_deadline_days)
            action_map = {
                "mark_sent": mgr.mark_sent,
                "mark_acknowledged": lambda rid: mgr.mark_acknowledged(rid, body.details or ""),
                "mark_completed": mgr.mark_completed,
                "mark_refused": lambda rid: mgr.mark_refused(rid, body.details or ""),
                "mark_overdue": mgr.mark_overdue,
                "mark_escalated": mgr.mark_escalated,
                "mark_manual_action_needed": lambda rid: mgr.mark_manual_action_needed(
                    rid, body.details or ""
                ),
            }
            fn = action_map.get(body.action)
            if fn is None:
                raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")
            try:
                req = fn(request_id)
            except InvalidTransitionError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            return {"id": req.id, "status": req.status.value}
        finally:
            db.close()

    @r.get("/export/audit-trail")
    def export_audit_trail(
        output_format: str = "json",
        session: str | None = Cookie(default=None),
    ):
        """Export the complete GDPR audit trail for all requests."""
        session_store.validate(session)
        db = _get_db()
        try:
            all_requests = (
                db.query(Request).order_by(Request.created_at).all()
            )
            events = db.query(RequestEvent).order_by(RequestEvent.id).all()
            emails = db.query(EmailMessage).order_by(EmailMessage.received_at).all()

            events_by_req = {}
            for e in events:
                events_by_req.setdefault(e.request_id, []).append({
                    "event_type": e.event_type,
                    "details": e.details,
                    "timestamp": (
                        e.created_at.isoformat() if e.created_at else None
                    ),
                })

            emails_by_req = {}
            for e in emails:
                emails_by_req.setdefault(e.request_id, []).append({
                    "direction": e.direction.value,
                    "from": e.from_address,
                    "to": e.to_address,
                    "subject": e.subject,
                    "date": (
                        e.received_at.isoformat() if e.received_at else None
                    ),
                })

            trail = []
            for req in all_requests:
                broker_name = req.broker_id
                if broker_registry:
                    b = broker_registry.get(req.broker_id)
                    if b:
                        broker_name = b.name

                entry = {
                    "request_id": req.id,
                    "broker_id": req.broker_id,
                    "broker_name": broker_name,
                    "request_type": req.request_type.value,
                    "status": req.status.value,
                    "created_at": (
                        req.created_at.isoformat() if req.created_at else None
                    ),
                    "sent_at": (
                        req.sent_at.isoformat() if req.sent_at else None
                    ),
                    "deadline_at": (
                        req.deadline_at.isoformat() if req.deadline_at else None
                    ),
                    "response_at": (
                        req.response_at.isoformat() if req.response_at else None
                    ),
                    "events": events_by_req.get(req.id, []),
                    "emails": emails_by_req.get(req.id, []),
                }
                trail.append(entry)

            if output_format == "csv":
                import csv
                import io

                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow([
                    "request_id", "broker_name", "type", "status",
                    "created", "sent", "deadline", "response",
                    "events_count", "emails_count",
                ])
                for entry in trail:
                    writer.writerow([
                        entry["request_id"],
                        entry["broker_name"],
                        entry["request_type"],
                        entry["status"],
                        entry["created_at"],
                        entry["sent_at"],
                        entry["deadline_at"],
                        entry["response_at"],
                        len(entry["events"]),
                        len(entry["emails"]),
                    ])
                from fastapi.responses import Response as RawResponse
                return RawResponse(
                    content=output.getvalue(),
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": (
                            "attachment; filename=incognito-audit-trail.csv"
                        ),
                    },
                )

            return {
                "generated_at": datetime.now(UTC).isoformat(),
                "total_requests": len(trail),
                "trail": trail,
            }
        finally:
            db.close()

    @r.get("/report/exposure")
    def exposure_report(session: str | None = Cookie(default=None)):
        """Generate an exposure report with privacy score and per-broker status."""
        session_store.validate(session)
        db = _get_db()
        try:
            all_requests = db.query(Request).all()
            scan_results = db.query(ScanResult).all()

            # Group requests by broker, keep the most advanced status
            broker_status: dict[str, dict] = {}
            status_rank = {
                RequestStatus.COMPLETED: 6,
                RequestStatus.ACKNOWLEDGED: 5,
                RequestStatus.ESCALATED: 4,
                RequestStatus.OVERDUE: 3,
                RequestStatus.SENT: 2,
                RequestStatus.CREATED: 1,
                RequestStatus.REFUSED: 0,
                RequestStatus.MANUAL_ACTION_NEEDED: 0,
            }
            for req in all_requests:
                existing = broker_status.get(req.broker_id)
                rank = status_rank.get(req.status, 0)
                if existing is None or rank > existing["_rank"]:
                    broker_name = req.broker_id
                    if broker_registry:
                        b = broker_registry.get(req.broker_id)
                        if b:
                            broker_name = b.name
                    broker_status[req.broker_id] = {
                        "_rank": rank,
                        "broker_id": req.broker_id,
                        "broker_name": broker_name,
                        "status": req.status.value,
                        "sent_at": (
                            req.sent_at.isoformat() if req.sent_at else None
                        ),
                        "response_at": (
                            req.response_at.isoformat() if req.response_at else None
                        ),
                    }

            # Calculate score
            total_brokers = len(broker_status)
            completed = sum(
                1 for b in broker_status.values()
                if b["status"] == RequestStatus.COMPLETED.value
            )
            acknowledged = sum(
                1 for b in broker_status.values()
                if b["status"] == RequestStatus.ACKNOWLEDGED.value
            )
            sent = sum(
                1 for b in broker_status.values()
                if b["status"] in (
                    RequestStatus.SENT.value,
                    RequestStatus.OVERDUE.value,
                    RequestStatus.ESCALATED.value,
                )
            )
            in_progress = acknowledged + sent

            # Score: 100 = all completed, 0 = nothing done
            if total_brokers > 0:
                score = round(
                    (completed * 100 + in_progress * 40) / total_brokers
                )
                score = min(score, 100)
            else:
                score = 0

            # Grade
            if score >= 90:
                grade = "A"
            elif score >= 70:
                grade = "B"
            elif score >= 50:
                grade = "C"
            elif score >= 30:
                grade = "D"
            else:
                grade = "F"

            # Exposure sources from scans
            exposures = []
            for sr in scan_results:
                exposures.append({
                    "source": sr.source,
                    "broker_id": sr.broker_id,
                    "scanned_at": (
                        sr.scanned_at.isoformat() if sr.scanned_at else None
                    ),
                    "actioned": sr.actioned,
                })

            # Clean up internal rank field
            brokers_list = []
            for b in broker_status.values():
                entry = {k: v for k, v in b.items() if k != "_rank"}
                brokers_list.append(entry)

            return {
                "generated_at": datetime.now(UTC).isoformat(),
                "score": score,
                "grade": grade,
                "summary": {
                    "total_brokers_contacted": total_brokers,
                    "completed": completed,
                    "in_progress": in_progress,
                    "exposures_found": len(scan_results),
                },
                "brokers": sorted(
                    brokers_list, key=lambda x: x["broker_name"],
                ),
                "exposures": exposures[:50],
            }
        finally:
            db.close()

    return r
