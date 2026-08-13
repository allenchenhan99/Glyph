import hashlib

from fastapi.testclient import TestClient

from glyph.main import create_app


def test_reader_payload_returns_aligned_blocks_sections_and_summary(
    tmp_path, monkeypatch
):
    book = tmp_path / "book"
    book.mkdir()
    (book / "reader.pdf").write_text(
        "# Chapter One\n\n"
        "A clean paragraph for translation.\n\n"
        "2. Why does alignment matter?",
    )
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    client = TestClient(create_app())
    document_id = client.get("/api/documents").json()[0]["id"]
    client.post(f"/api/documents/{document_id}/process")

    reader_response = client.get(f"/api/documents/{document_id}/reader")
    sections_response = client.get(f"/api/documents/{document_id}/sections")
    summary_response = client.get(f"/api/documents/{document_id}/summary")

    assert reader_response.status_code == 200
    reader = reader_response.json()
    assert reader["document"]["id"] == document_id
    assert reader["summary"].startswith("Chapter One")
    assert reader["blocks"][0]["source_text"] == "Chapter One"
    assert reader["blocks"][0]["translated_text"] == "標題：Chapter One"
    assert reader["blocks"][0]["formula_latex"] is None
    assert reader["blocks"][0]["section_path"] == "Chapter One"
    assert reader["blocks"][0]["page_image_url"] == (
        f"/api/documents/{document_id}/pages/1/image"
        f"?source_content_hash={hashlib.sha256((book / 'reader.pdf').read_bytes()).hexdigest()}"
    )
    assert reader["blocks"][0]["page_number"] == 1
    assert reader["blocks"][0]["block_type"] == "heading"
    assert sections_response.json()[0]["title"] == "Chapter One"
    assert summary_response.json()["summary"] == reader["summary"]
