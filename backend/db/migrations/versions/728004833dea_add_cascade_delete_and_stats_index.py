"""add cascade delete and stats index

Revision ID: 728004833dea
Revises: ad5d9eafabea
Create Date: 2026-03-29 17:03:06.639718

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '728004833dea'
down_revision: str | Sequence[str] | None = 'ad5d9eafabea'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("requests")}
    if "ix_requests_status_reply_read_at" not in existing_indexes:
        op.create_index(
            "ix_requests_status_reply_read_at",
            "requests",
            ["status", "reply_read_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_requests_status_reply_read_at", table_name="requests")
