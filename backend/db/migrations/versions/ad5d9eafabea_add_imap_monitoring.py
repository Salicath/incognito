"""add imap monitoring

Revision ID: ad5d9eafabea
Revises: 38b3086318eb
Create Date: 2026-03-29 16:34:23.797355

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad5d9eafabea'
down_revision: Union[str, Sequence[str], None] = '38b3086318eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("message_id", sa.String(), nullable=True))
    op.add_column("requests", sa.Column("reply_read_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "email_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("in_reply_to", sa.String(), nullable=True),
        sa.Column(
            "direction",
            sa.Enum("inbound", "outbound", name="emaildirection"),
            nullable=False,
        ),
        sa.Column("from_address", sa.String(), nullable=False),
        sa.Column("to_address", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_messages_request_id", "email_messages", ["request_id"])
    op.create_index("ix_email_messages_message_id", "email_messages", ["message_id"])


def downgrade() -> None:
    op.drop_table("email_messages")
    op.drop_column("requests", "reply_read_at")
    op.drop_column("requests", "message_id")
