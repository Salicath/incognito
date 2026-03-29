import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker

from backend.db.models import Base

log = logging.getLogger("incognito.db")

ALEMBIC_INI = Path(__file__).parent.parent.parent / "alembic.ini"


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


def _schema_matches_models(engine) -> bool:
    """Check if the DB schema already has all tables and columns from models."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            return False
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        model_cols = {c.name for c in table.columns}
        if not model_cols.issubset(existing_cols):
            return False
    return True


def _get_alembic_cfg(db_path: Path):
    """Get Alembic config pointing at the given DB, or None if alembic.ini doesn't exist."""
    if not ALEMBIC_INI.exists():
        return None
    from alembic.config import Config
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def init_db(db_path: Path) -> sessionmaker:
    is_new = not db_path.exists()
    engine = get_engine(db_path)

    if is_new:
        # Fresh install: create all tables and stamp as current migration
        Base.metadata.create_all(engine)
        alembic_cfg = _get_alembic_cfg(db_path)
        if alembic_cfg:
            from alembic import command
            command.stamp(alembic_cfg, "head")
            log.info("New database created and stamped at current migration")
        else:
            log.debug("Alembic stamp skipped (alembic.ini not found)")
    else:
        # Existing install: run pending migrations
        alembic_cfg = _get_alembic_cfg(db_path)
        if alembic_cfg:
            from alembic import command
            try:
                command.upgrade(alembic_cfg, "head")
                log.info("Database migrations applied")
            except Exception:
                # Schema may already match models (e.g. created with create_all()
                # but stamped at an older migration). Re-stamp instead of failing.
                if _schema_matches_models(engine):
                    command.stamp(alembic_cfg, "head")
                    log.info("Schema already up to date, re-stamped migration head")
                else:
                    raise
        else:
            # No alembic.ini (e.g. tests): ensure tables exist
            Base.metadata.create_all(engine)

    # Restrict database file permissions (owner-only read/write)
    if db_path.exists():
        os.chmod(db_path, 0o600)

    return sessionmaker(bind=engine)
