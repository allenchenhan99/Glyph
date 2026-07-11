from fastapi.testclient import TestClient

from glyph.main import create_app


def test_upload_endpoint_registers_supported_document(tmp_path, monkeypatch):
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(tmp_path / "book"))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())

    response = client.post(
        "/api/documents/upload",
        files={"file": ("uploaded.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "uploaded.pdf"
    assert payload["file_type"] == "pdf"
    assert payload["status"] == "uploaded"
    assert (tmp_path / "data" / "uploads" / "uploaded.pdf").exists()


def test_upload_endpoint_rejects_unsupported_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(tmp_path / "book"))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())

    response = client.post(
        "/api/documents/upload",
        files={"file": ("notes.txt", b"not supported", "text/plain")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]
