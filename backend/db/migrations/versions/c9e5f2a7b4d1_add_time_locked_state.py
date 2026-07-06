"""add time_locked_state table

Revision ID: c9e5f2a7b4d1
Revises: b2c8d4e6f1a3
Create Date: 2026-07-05 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9e5f2a7b4d1'
down_revision: str | Sequence[str] | None = 'b2c8d4e6f1a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "time_locked_state" not in inspector.get_table_names():
        op.create_table(
            "time_locked_state",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("entry_id", sa.String(), nullable=False),
            sa.Column("institution", sa.String(), nullable=False, server_default=""),
            sa.Column("trigger_date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("fires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "conservative", sa.Boolean(), nullable=False, server_default="0"
            ),
            sa.Column("status", sa.Enum("ARMED", "FIRED", "DISMISSED",
                                        name="timelockedstatus"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("time_locked_state")
