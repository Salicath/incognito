from typer.testing import CliRunner

from cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "incognito" in result.output.lower() or "Incognito" in result.output


def test_serve_help():
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "host" in result.output.lower() or "port" in result.output.lower()


def test_status_without_init(tmp_path, monkeypatch):
    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0 or "not initialized" in result.output.lower()


def test_brokers_list(tmp_path, monkeypatch):
    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["brokers", "list"])
    assert result.exit_code == 0
    assert "Broker Registry" in result.output


def test_brokers_list_filter_country(tmp_path, monkeypatch):
    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["brokers", "list", "--country", "DE"])
    assert result.exit_code == 0


def test_brokers_stats(tmp_path, monkeypatch):
    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["brokers", "stats"])
    assert result.exit_code == 0
    assert "Total brokers" in result.output
    assert "By Country" in result.output


def test_send_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["send"])
    # Not initialized — should exit gracefully
    assert "not initialized" in result.output.lower() or result.exit_code == 0
