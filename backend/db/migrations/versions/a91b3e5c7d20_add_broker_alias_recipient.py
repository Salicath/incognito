"""add broker_alias.recipient (the contact address behind the reverse-alias)

Revision ID: a91b3e5c7d20
Revises: d1f4a7c02b98
Create Date: 2026-07-10 17:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a91b3e5c7d20'
down_revision: str | Sequence[str] | None = 'd1f4a7c02b98'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "broker_alias" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("broker_alias")}
        if "recipient" not in cols:
            op.add_column(
                "broker_alias", sa.Column("recipient", sa.String(), nullable=True)
            )


def downgrade() -> None:
    op.drop_column("broker_alias", "recipient")
