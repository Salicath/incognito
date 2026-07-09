"""Tests for Prometheus metrics and proxy auth."""


def test_metrics_endpoint(config, seeded_vault):
    from fastapi.testclient import TestClient

    from backend.main import create_app

    client = TestClient(create_app(config))
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    text = resp.text
    assert "incognito_requests_total" in text
    assert "incognito_brokers_total" in text
    assert "incognito_scan_results_total" in text


def test_metrics_format(config, seeded_vault):
    """Metrics should be in Prometheus text format."""
    from fastapi.testclient import TestClient

    from backend.main import create_app

    client = TestClient(create_app(config))
    resp = client.get("/api/metrics")
    assert resp.headers["content-type"].startswith("text/plain")
    # Should contain TYPE and HELP lines
    assert "# TYPE" in resp.text
    assert "# HELP" in resp.text


def test_status_with_proxy_header(config, seeded_vault):
    """Status endpoint shows proxy_auth when header configured."""
    from fastapi.testclient import TestClient

    from backend.core.config import AppConfig
    from backend.main import create_app

    proxy_config = AppConfig(
        data_dir=config.data_dir,
        trusted_proxy_header="Remote-User",
    )
    client = TestClient(create_app(proxy_config))

    # Without header
    resp = client.get("/api/auth/status")
    assert resp.json()["proxy_auth"] is False

    # With header
    resp = client.get("/api/auth/status", headers={"Remote-User": "admin"})
    assert resp.json()["proxy_auth"] is True


def test_status_without_proxy_header(config, seeded_vault):
    """Status endpoint doesn't show proxy_auth when not configured."""
    from fastapi.testclient import TestClient

    from backend.main import create_app

    client = TestClient(create_app(config))
    resp = client.get("/api/auth/status")
    assert "proxy_auth" not in resp.json()


def test_metrics_token_required_when_set(tmp_path, sample_profile, sample_smtp):
    """With INCOGNITO_METRICS_TOKEN set, /api/metrics needs a bearer token."""
    from fastapi.testclient import TestClient

    from backend.core.config import AppConfig
    from backend.core.profile import ProfileVault
    from backend.main import create_app

    cfg = AppConfig(data_dir=tmp_path, metrics_token="s3cret")
    ProfileVault(cfg.vault_path).save(sample_profile, sample_smtp, "pw")
    client = TestClient(create_app(cfg))

    assert client.get("/api/metrics").status_code == 401
    assert client.get(
        "/api/metrics", headers={"Authorization": "Bearer wrong"}
    ).status_code == 401

    ok = client.get("/api/metrics", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
    assert "incognito_requests_total" in ok.text
