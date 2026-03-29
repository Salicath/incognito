import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.db.models import Base

log = logging.getLogger("incognito.db")


def get_engine(db_path: Path):
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, echo=False)

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_db(db_path: Path) -> sessionmaker:
    is_new = not db_path.exists()
    engine = get_engine(db_path)

    if is_new:
        # Fresh install: create all tables and stamp as current migration
        Base.metadata.create_all(engine)
        try:
            from alembic import command
            from alembic.config import Config
            alembic_cfg = Config(str(Path(__file__).parent.parent.parent / "alembic.ini"))
            command.stamp(alembic_cfg, "head")
            log.info("New database created and stamped at current migration")
        except Exception:
            log.debug("Alembic stamp skipped (alembic.ini not found)")
    else:
        # Existing install: run pending migrations
        try:
            from alembic import command
            from alembic.config import Config
            alembic_cfg = Config(str(Path(__file__).parent.parent.parent / "alembic.ini"))
            command.upgrade(alembic_cfg, "head")
            log.info("Database migrations applied")
        except Exception:
            # Fallback: ensure tables exist (e.g. in tests without alembic.ini)
            Base.metadata.create_all(engine)

    # Restrict database file permissions (owner-only read/write)
    if db_path.exists():
        os.chmod(db_path, 0o600)

    return sessionmaker(bind=engine)
