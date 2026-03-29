"""Tests for the CLI report command."""
import uuid
from datetime import UTC, datetime

from typer.testing import CliRunner

from backend.db.models import Base, Request, RequestStatus, RequestType

runner = CliRunner()


def test_report_no_data(tmp_path, monkeypatch):
    from cli import app

    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    # Create vault so it looks initialized
    vault_path = tmp_path / "profile.enc"
    vault_path.write_bytes(b"fake")

    result = runner.invoke(app, ["report"])
    assert result.exit_code == 0
    assert "No data yet" in result.output


def test_report_with_requests(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from cli import app

    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    vault_path = tmp_path / "profile.enc"
    vault_path.write_bytes(b"fake")

    # Create DB with some requests
    db_path = tmp_path / "incognito.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        for i, status in enumerate([
            RequestStatus.COMPLETED,
            RequestStatus.COMPLETED,
            RequestStatus.SENT,
        ]):
            req = Request(
                id=str(uuid.uuid4()),
                broker_id=f"broker-{i}",
                request_type=RequestType.ERASURE,
                status=status,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(req)
        session.commit()
    engine.dispose()

    result = runner.invoke(app, ["report"])
    assert result.exit_code == 0
    assert "Privacy Score" in result.output
    assert "Brokers contacted" in result.output
