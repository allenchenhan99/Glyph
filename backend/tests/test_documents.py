from fastapi.testclient import TestClient

from glyph.main import create_app
from glyph.models import Document


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

    with client.app.state.session_factory() as session:
        document = session.get(Document, document_id)
        assert document is not None
        assert document.processed_content_hash == document.content_hash


def test_changed_source_is_marked_stale_without_deleting_reader_data(
    tmp_path, monkeypatch
):
    book = tmp_path / "book"
    book.mkdir()
    source = book / "sample.pdf"
    source.write_text("# Original\n\nExisting readable content.")
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_OCR_MODE", "mock")
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    client = TestClient(create_app())
    document_id = client.get("/api/documents").json()[0]["id"]
    client.post(f"/api/documents/{document_id}/process")
    original_reader = client.get(f"/api/documents/{document_id}/reader").json()

    source.write_text("# Revised\n\nNew source that has not been processed.")
    catalog_document = client.get("/api/documents").json()[0]
    stale_reader = client.get(f"/api/documents/{document_id}/reader").json()

    assert catalog_document["status"] == "stale"
    assert stale_reader["document"]["status"] == "stale"
    assert stale_reader["blocks"] == original_reader["blocks"]
    with client.app.state.session_factory() as session:
        document = session.get(Document, document_id)
        assert document is not None
        assert document.content_hash != document.processed_content_hash


def test_missing_source_is_retained_and_restored_using_hash_state(
    tmp_path, monkeypatch
):
    book = tmp_path / "book"
    book.mkdir()
    source = book / "sample.pdf"
    original_bytes = b"# Original\n\nExisting readable content."
    source.write_bytes(original_bytes)
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_OCR_MODE", "mock")
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    client = TestClient(create_app())
    document_id = client.get("/api/documents").json()[0]["id"]
    client.post(f"/api/documents/{document_id}/process")

    source.unlink()
    missing_document = client.get("/api/documents").json()[0]

    assert missing_document["id"] == document_id
    assert missing_document["status"] == "missing"
    assert client.get(f"/api/documents/{document_id}/reader").status_code == 200
    process_response = client.post(f"/api/documents/{document_id}/process")
    page_response = client.get(f"/api/documents/{document_id}/pages/1/image")
    assert process_response.status_code == 409
    assert process_response.json()["detail"] == "Source file is missing"
    assert page_response.status_code == 409
    assert page_response.json()["detail"] == "Source file is missing"

    source.write_bytes(original_bytes)
    restored_document = client.get("/api/documents").json()[0]
    assert restored_document["status"] == "completed"

    source.write_bytes(b"# Changed\n\nDifferent bytes.")
    changed_document = client.get("/api/documents").json()[0]
    assert changed_document["status"] == "stale"
