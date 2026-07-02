"""add lever reminder stage

Revision ID: e8f21a7c4d55
Revises: c41f7a2d9b10
Create Date: 2026-07-02 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e8f21a7c4d55'
down_revision: str | Sequence[str] | None = 'c41f7a2d9b10'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    columns = [c["name"] for c in inspector.get_columns("cpr_lever_state")]
    if "reminder_stage" not in columns:
        op.add_column(
            "cpr_lever_state",
            sa.Column("reminder_stage", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    op.drop_column("cpr_lever_state", "reminder_stage")
