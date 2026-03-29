"""Tests for the brokers update CLI command."""
from unittest.mock import MagicMock, patch

import yaml
from typer.testing import CliRunner

from cli import app

runner = CliRunner()


def _mock_github_api(yaml_files: list[dict]):
    """Create mock responses for GitHub API calls."""
    listing = []
    file_responses = {}
    for f in yaml_files:
        name = f["name"]
        content = yaml.dump(f["data"])
        url = f"https://raw.githubusercontent.com/test/repo/main/brokers/{name}"
        listing.append({
            "name": name,
            "download_url": url,
        })
        file_responses[url] = content
    return listing, file_responses


@patch("httpx.get")
def test_brokers_update_adds_new(mock_get, tmp_path, monkeypatch):
    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    brokers_dir = tmp_path / "brokers"
    brokers_dir.mkdir()

    listing, file_responses = _mock_github_api([
        {
            "name": "new-broker.yaml",
            "data": {
                "name": "New Broker",
                "domain": "new-broker.com",
                "category": "data_broker",
                "dpo_email": "dpo@new-broker.com",
                "removal_method": "email",
                "country": "DE",
                "gdpr_applies": True,
                "verification_required": False,
                "last_verified": "2026-03-01",
            },
        }
    ])

    def side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        if "api.github.com" in url:
            resp.json.return_value = listing
        else:
            resp.text = file_responses.get(url, "")
        return resp

    mock_get.side_effect = side_effect

    result = runner.invoke(app, ["brokers", "update"])
    assert result.exit_code == 0
    assert "1 new" in result.output
    assert (brokers_dir / "new-broker.yaml").exists()


@patch("httpx.get")
def test_brokers_update_skips_invalid_yaml(mock_get, tmp_path, monkeypatch):
    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    brokers_dir = tmp_path / "brokers"
    brokers_dir.mkdir()

    def side_effect(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        if "api.github.com" in url:
            resp.json.return_value = [
                {"name": "bad.yaml", "download_url": "https://example.com/bad.yaml"},
            ]
        else:
            resp.text = "not: valid: broker: data"
        return resp

    mock_get.side_effect = side_effect

    result = runner.invoke(app, ["brokers", "update"])
    assert result.exit_code == 0
    assert "0 new" in result.output


@patch("httpx.get")
def test_brokers_update_network_error(mock_get, tmp_path, monkeypatch):
    import httpx
    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    (tmp_path / "brokers").mkdir()

    mock_get.side_effect = httpx.ConnectError("Connection refused")

    result = runner.invoke(app, ["brokers", "update"])
    assert result.exit_code == 1
    assert "Failed" in result.output
