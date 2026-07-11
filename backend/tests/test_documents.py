from fastapi.testclient import TestClient

from glyph.main import create_app


def test_documents_endpoint_discovers_supported_book_files(tmp_path, monkeypatch):
    book = tmp_path / "book"
    book.mkdir()
    (book / "sample.pdf").write_bytes(b"%PDF-1.4")
    (book / "page.png").write_bytes(b"fake")
    (book / "notes.txt").write_text("ignore")
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")

    response = TestClient(create_app()).get("/api/documents")

    assert response.status_code == 200
    names = [item["title"] for item in response.json()]
    assert names == ["page.png", "sample.pdf"]
    assert all(item["status"] == "discovered" for item in response.json())


def test_documents_endpoint_does_not_downgrade_processed_status(tmp_path, monkeypatch):
    book = tmp_path / "book"
    book.mkdir()
    (book / "sample.pdf").write_text("# Title\n\nBody text.")
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    client = TestClient(create_app())
    document_id = client.get("/api/documents").json()[0]["id"]
    client.post(f"/api/documents/{document_id}/process")

    response = client.get("/api/documents")

    assert response.status_code == 200
    assert response.json()[0]["status"] == "completed"
