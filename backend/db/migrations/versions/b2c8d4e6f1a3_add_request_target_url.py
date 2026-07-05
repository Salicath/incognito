"""add request target_url for delisting requests

Revision ID: b2c8d4e6f1a3
Revises: f3a1c9d27e64
Create Date: 2026-07-05 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c8d4e6f1a3'
down_revision: str | Sequence[str] | None = 'f3a1c9d27e64'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    columns = [c["name"] for c in inspector.get_columns("requests")]
    if "target_url" not in columns:
        op.add_column("requests", sa.Column("target_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("requests", "target_url")
