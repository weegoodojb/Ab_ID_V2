from fastapi.testclient import TestClient

from app.main import app


def test_home_page_loads_with_empty_local_database(monkeypatch, tmp_path):
    monkeypatch.setenv("ABID_SQLITE_PATH", str(tmp_path / "ab-id.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Ab ID" in response.text