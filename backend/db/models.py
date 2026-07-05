import enum
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RequestStatus(enum.StrEnum):
    CREATED = "created"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"
    REFUSED = "refused"
    OVERDUE = "overdue"
    ESCALATED = "escalated"
    MANUAL_ACTION_NEEDED = "manual_action_needed"


class RequestType(enum.StrEnum):
    ACCESS = "access"
    ERASURE = "erasure"
    FOLLOW_UP = "follow_up"
    ESCALATION_WARNING = "escalation_warning"
    DPA_COMPLAINT = "dpa_complaint"


class EmailDirection(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CprLeverStatus(enum.StrEnum):
    NEW = "new"
    USER_NOTIFIED = "user_notified"
    ACTIVE = "active"
    RENEWAL_DUE = "renewal_due"
    EXPIRED = "expired"
    USER_DEFERRED = "user_deferred"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    broker_id: Mapped[str] = mapped_column(String, nullable=False)
    request_type: Mapped[RequestType] = mapped_column(Enum(RequestType), nullable=False)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus), nullable=False, default=RequestStatus.CREATED
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Delisting requests target one URL per engine; NULL for broker/controller requests
    target_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    events: Mapped[list["RequestEvent"]] = relationship(back_populates="request")


class RequestEvent(Base):
    __tablename__ = "request_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        String, ForeignKey("requests.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    request: Mapped["Request"] = relationship(back_populates="events")


class EmailMessage(Base):
    __tablename__ = "email_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        String, ForeignKey("requests.id"), nullable=False, index=True
    )
    message_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    in_reply_to: Mapped[str | None] = mapped_column(String, nullable=True)
    direction: Mapped[EmailDirection] = mapped_column(Enum(EmailDirection), nullable=False)
    from_address: Mapped[str] = mapped_column(String, nullable=False)
    to_address: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class CprLeverState(Base):
    __tablename__ = "cpr_lever_state"

    lever_id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[CprLeverStatus] = mapped_column(
        Enum(CprLeverStatus), nullable=False, default=CprLeverStatus.NEW
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Renewal notification ladder: 0=none, 1=T-30 sent, 2=T-7 sent, 3=expiry sent
    reminder_stage: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class ScanResult(Base):
    __tablename__ = "scan_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    broker_id: Mapped[str | None] = mapped_column(String, nullable=True)
    found_data: Mapped[str] = mapped_column(Text, nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    actioned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Triage disposition: None = needs triage; else "actioned" | "dismissed" | "legally_impossible"
    disposition: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
