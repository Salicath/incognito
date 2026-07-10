"""rewrite alias_leak exposure keys from mailto:<full-sender> to mailto:<domain>

The leak-exposure dedup identity is (source, broker_id, url). The url moved
from the full sender address to just its domain (VERP campaigns vary the local
part per message). Without rewriting existing rows, the first post-upgrade poll
computes the new domain key, finds no match, and re-mints a fresh needs_triage
exposure — resurrecting dismissed leaks and re-notifying. Rewrite in place so
the key (and any disposition) is preserved.

Revision ID: b3c5e7f9a012
Revises: a91b3e5c7d20
Create Date: 2026-07-10 18:30:00.000000

"""
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b3c5e7f9a012'
down_revision: str | Sequence[str] | None = 'a91b3e5c7d20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "scan_results" not in inspector.get_table_names():
        return

    rows = conn.execute(
        sa.text(
            "SELECT id, found_data FROM scan_results WHERE source = 'alias_leak'"
        )
    ).fetchall()
    for row_id, found_data in rows:
        try:
            data = json.loads(found_data) if found_data else {}
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        url = data.get("url", "")
        if not url.startswith("mailto:"):
            continue
        full = url[len("mailto:"):]
        if "@" not in full:
            continue  # already a bare domain
        domain = full.rsplit("@", 1)[-1].strip().lower()
        data.setdefault("sender", full)
        data["url"] = f"mailto:{domain}"
        title = data.get("title", "")
        if "leaked or sold" in title:
            data["title"] = (
                f"Unexpected sender on the alias for {data.get('broker_domain', '')}"
            ).strip()
        conn.execute(
            sa.text("UPDATE scan_results SET found_data = :d WHERE id = :i"),
            {"d": json.dumps(data), "i": row_id},
        )


def downgrade() -> None:
    # One-way data normalization; the domain key is a strict improvement.
    pass
