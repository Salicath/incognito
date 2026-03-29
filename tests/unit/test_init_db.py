"""Tests for init_db() migration handling."""
from sqlalchemy import create_engine, text

from backend.db.models import Base
from backend.db.session import _schema_matches_models, init_db


def test_init_db_fresh_install(tmp_path):
    """Fresh install creates DB and returns working sessionmaker."""
    db_path = tmp_path / "test.db"
    session_factory = init_db(db_path)
    assert db_path.exists()

    # Verify all tables exist
    with session_factory() as session:
        tables = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).scalars().all()
        assert "requests" in tables
        assert "request_events" in tables
        assert "email_messages" in tables
        assert "scan_results" in tables


def test_init_db_fresh_has_alembic_version(tmp_path):
    """Fresh install stamps alembic_version at head."""
    db_path = tmp_path / "test.db"
    session_factory = init_db(db_path)

    with session_factory() as session:
        tables = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).scalars().all()
        assert "alembic_version" in tables

        version = session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        assert version is not None


def test_init_db_existing_db_runs_migrations(tmp_path):
    """Existing DB with old schema gets migrated."""
    db_path = tmp_path / "test.db"

    # Simulate an old DB with only the initial schema (no IMAP columns)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE requests (
                id VARCHAR PRIMARY KEY,
                broker_id VARCHAR NOT NULL,
                request_type VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                sent_at DATETIME,
                deadline_at DATETIME,
                response_at DATETIME,
                response_body TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE request_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id VARCHAR NOT NULL REFERENCES requests(id),
                event_type VARCHAR NOT NULL,
                details TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE scan_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source VARCHAR NOT NULL,
                broker_id VARCHAR,
                found_data TEXT NOT NULL,
                scanned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actioned BOOLEAN NOT NULL DEFAULT 0
            )
        """))
        # Stamp at initial migration
        conn.execute(text(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        ))
        conn.execute(text(
            "INSERT INTO alembic_version VALUES ('38b3086318eb')"
        ))
        conn.commit()
    engine.dispose()

    # Now init_db should run the remaining migrations
    session_factory = init_db(db_path)

    with session_factory() as session:
        # Verify IMAP columns were added
        cols = session.execute(text("PRAGMA table_info(requests)")).fetchall()
        col_names = {c[1] for c in cols}
        assert "message_id" in col_names
        assert "reply_read_at" in col_names

        # Verify email_messages table was created
        tables = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).scalars().all()
        assert "email_messages" in tables


def test_init_db_schema_ahead_of_migrations(tmp_path):
    """DB created with create_all() but stamped at old migration gets re-stamped."""
    db_path = tmp_path / "test.db"

    # Create full schema with create_all() (as if installed from current models)
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    # But stamp at an old migration (simulating the bug)
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        ))
        conn.execute(text(
            "INSERT INTO alembic_version VALUES ('38b3086318eb')"
        ))
        conn.commit()
    engine.dispose()

    # init_db should detect schema is already current and re-stamp
    session_factory = init_db(db_path)

    with session_factory() as session:
        version = session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        # Should be at head now, not stuck at old revision
        assert version == "728004833dea"


def test_schema_matches_models_complete(tmp_path):
    """_schema_matches_models returns True when all tables/columns exist."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    assert _schema_matches_models(engine) is True


def test_schema_matches_models_missing_column(tmp_path):
    """_schema_matches_models returns False when columns are missing."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")

    # Create requests table without IMAP columns
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE requests (
                id VARCHAR PRIMARY KEY,
                broker_id VARCHAR NOT NULL,
                request_type VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE request_events (
                id INTEGER PRIMARY KEY, request_id VARCHAR, event_type VARCHAR,
                details TEXT, created_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE scan_results (
                id INTEGER PRIMARY KEY, source VARCHAR, broker_id VARCHAR,
                found_data TEXT, scanned_at DATETIME, actioned BOOLEAN
            )
        """))
        conn.commit()

    assert _schema_matches_models(engine) is False


def test_schema_matches_models_missing_table(tmp_path):
    """_schema_matches_models returns False when tables are missing."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE requests (id VARCHAR PRIMARY KEY)"))
        conn.commit()
    assert _schema_matches_models(engine) is False


def test_init_db_idempotent_migrations(tmp_path):
    """Running init_db twice on same DB doesn't fail."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    # Second call should be a no-op
    session_factory = init_db(db_path)
    assert session_factory is not None
