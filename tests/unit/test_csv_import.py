"""Tests for CSV import endpoint."""


def test_import_csv_basic(authenticated_client):
    csv_data = "broker,status,date\nAcxiom,completed,2026-03-01\n"
    resp = authenticated_client.post(
        "/api/settings/import-csv", json={"csv": csv_data},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 1
    assert data["skipped"] == 0


def test_import_csv_unknown_broker(authenticated_client):
    csv_data = "broker,status,date\nNonexistent Corp,completed,2026-03-01\n"
    resp = authenticated_client.post(
        "/api/settings/import-csv", json={"csv": csv_data},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 0
    assert data["skipped"] == 1
    assert any("not found" in e.lower() for e in data["errors"])


def test_import_csv_empty(authenticated_client):
    resp = authenticated_client.post(
        "/api/settings/import-csv", json={"csv": ""},
    )
    assert resp.status_code == 400


def test_import_csv_duplicate_skipped(authenticated_client):
    """Importing the same broker twice should skip the second."""
    csv_data = "broker,status,date\nSpokeo,completed,2026-03-01\n"

    resp1 = authenticated_client.post(
        "/api/settings/import-csv", json={"csv": csv_data},
    )
    assert resp1.json()["imported"] == 1

    resp2 = authenticated_client.post(
        "/api/settings/import-csv", json={"csv": csv_data},
    )
    assert resp2.json()["imported"] == 0
    assert resp2.json()["skipped"] == 1


def test_import_csv_requires_auth(config, seeded_vault):
    from fastapi.testclient import TestClient

    from backend.main import create_app

    app = create_app(config)
    client = TestClient(app)
    resp = client.post("/api/settings/import-csv", json={"csv": "broker,status\n"})
    assert resp.status_code == 401
