"""add cpr lever state

Revision ID: c41f7a2d9b10
Revises: 728004833dea
Create Date: 2026-07-01 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c41f7a2d9b10'
down_revision: str | Sequence[str] | None = '728004833dea'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "cpr_lever_state" not in inspector.get_table_names():
        op.create_table(
            "cpr_lever_state",
            sa.Column("lever_id", sa.String(), nullable=False),
            sa.Column(
                "status",
                sa.Enum(
                    "NEW", "USER_NOTIFIED", "ACTIVE", "RENEWAL_DUE",
                    "EXPIRED", "USER_DEFERRED",
                    name="cprleverstatus",
                ),
                nullable=False,
            ),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("user_note", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("lever_id"),
        )


def downgrade() -> None:
    op.drop_table("cpr_lever_state")
