"""initial schema

Revision ID: 38b3086318eb
Revises:
Create Date: 2026-03-29 12:42:42.432782

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "38b3086318eb"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial tables."""
    op.create_table(
        "requests",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("broker_id", sa.String(), nullable=False),
        sa.Column(
            "request_type",
            sa.Enum("access", "erasure", "follow_up", "escalation_warning", "dpa_complaint",
                    name="requesttype"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("created", "sent", "acknowledged", "completed", "refused", "overdue",
                    "escalated", "manual_action_needed", name="requeststatus"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "request_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "scan_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("broker_id", sa.String(), nullable=True),
        sa.Column("found_data", sa.Text(), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actioned", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("scan_results")
    op.drop_table("request_events")
    op.drop_table("requests")
