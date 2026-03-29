import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.db.models import Base


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
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)

    # Restrict database file permissions (owner-only read/write)
    if db_path.exists():
        os.chmod(db_path, 0o600)

    return sessionmaker(bind=engine)
