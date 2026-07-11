from fastapi.testclient import TestClient

from glyph.main import create_app


def test_health_reports_ok_and_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(tmp_path / "book"))

    app = create_app()
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["book_dir"].endswith("book")
