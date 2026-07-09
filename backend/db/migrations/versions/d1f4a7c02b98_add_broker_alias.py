"""add broker_alias table (per-recipient SimpleLogin aliases)

Revision ID: d1f4a7c02b98
Revises: c9e5f2a7b4d1
Create Date: 2026-07-09 20:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1f4a7c02b98'
down_revision: str | Sequence[str] | None = 'c9e5f2a7b4d1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "broker_alias" not in inspector.get_table_names():
        op.create_table(
            "broker_alias",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("broker_id", sa.String(), nullable=False, unique=True),
            sa.Column("alias_id", sa.Integer(), nullable=False),
            sa.Column("alias_email", sa.String(), nullable=False),
            sa.Column("reverse_alias_address", sa.String(), nullable=False),
            sa.Column("contact_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_broker_alias_alias_email", "broker_alias", ["alias_email"])


def downgrade() -> None:
    op.drop_index("ix_broker_alias_alias_email", table_name="broker_alias")
    op.drop_table("broker_alias")
