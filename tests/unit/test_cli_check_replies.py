"""Tests for the check-replies CLI command."""
from typer.testing import CliRunner

from cli import app

runner = CliRunner()


def test_check_replies_not_initialized(tmp_path, monkeypatch):
    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["check-replies"])
    assert result.exit_code == 0
    assert "Not initialized" in result.output


def test_check_replies_no_password(tmp_path, monkeypatch):
    """Without password env var and non-interactive, should fail."""
    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    # Create a fake vault so it looks initialized
    (tmp_path / "profile.enc").write_bytes(b"fake")
    monkeypatch.delenv("INCOGNITO_PASSWORD", raising=False)

    result = runner.invoke(app, ["check-replies"])
    # Should fail because we can't provide password in non-interactive mode
    # (typer runner is non-interactive, so getpass won't work)
    assert result.exit_code != 0 or "Error" in result.output or "password" in result.output.lower()


def test_check_replies_no_imap(tmp_path, monkeypatch, sample_profile, sample_smtp):
    """With valid vault but no IMAP config, should say not configured."""
    from backend.core.profile import ProfileVault

    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("INCOGNITO_PASSWORD", "test_password")

    vault = ProfileVault(tmp_path / "profile.enc")
    vault.save(sample_profile, sample_smtp, "test_password")

    result = runner.invoke(app, ["check-replies"])
    assert result.exit_code == 0
    assert "IMAP not configured" in result.output
