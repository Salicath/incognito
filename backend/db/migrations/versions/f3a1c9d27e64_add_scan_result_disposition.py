"""add scan result disposition + note

Revision ID: f3a1c9d27e64
Revises: e8f21a7c4d55
Create Date: 2026-07-02 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3a1c9d27e64'
down_revision: str | Sequence[str] | None = 'e8f21a7c4d55'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    columns = [c["name"] for c in inspector.get_columns("scan_results")]
    if "disposition" not in columns:
        op.add_column("scan_results", sa.Column("disposition", sa.String(), nullable=True))
    if "note" not in columns:
        op.add_column(
            "scan_results",
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    op.drop_column("scan_results", "note")
    op.drop_column("scan_results", "disposition")
