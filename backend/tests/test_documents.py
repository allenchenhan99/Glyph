import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from glyph.main import create_app
from glyph.models import Block, Document


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
    assert all(item["implementation_contract"] is None for item in response.json())


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
    original_without_page_links = [
        {**block, "page_image_url": None} for block in original_reader["blocks"]
    ]
    assert stale_reader["blocks"] == original_without_page_links
    with client.app.state.session_factory() as session:
        document = session.get(Document, document_id)
        assert document is not None
        assert document.content_hash != document.processed_content_hash


def test_reader_can_load_an_exact_retained_source_snapshot(tmp_path, monkeypatch):
    book = tmp_path / "book"
    book.mkdir()
    source = book / "sample.pdf"
    source.write_text("# Current\n\nCurrent replacement content.")
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_OCR_MODE", "mock")
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    client = TestClient(create_app())
    document_id = client.get("/api/documents").json()[0]["id"]
    client.post(f"/api/documents/{document_id}/process")
    historical_hash = "b" * 64
    with client.app.state.session_factory.begin() as session:
        session.add(
            Block(
                id="retained-historical-block",
                document_id=document_id,
                source_content_hash=historical_hash,
                order_index=0,
                page_number=1,
                block_type="paragraph",
                source_text="Existing historical content.",
                translated_text="既有歷史內容。",
            )
        )
    response = client.get(
        f"/api/documents/{document_id}/reader",
        params={"source_content_hash": historical_hash},
    )

    assert response.status_code == 200
    assert any(
        "Existing historical content" in block["source_text"]
        for block in response.json()["blocks"]
    )
    assert all(
        "Current replacement content" not in block["source_text"]
        for block in response.json()["blocks"]
    )
    assert all(block["page_image_url"] is None for block in response.json()["blocks"])


def test_page_image_rejects_an_obsolete_source_snapshot_hash(tmp_path, monkeypatch):
    book = tmp_path / "book"
    book.mkdir()
    source = book / "sample.pdf"
    source.write_text("# Current\n\nCurrent content.")
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_OCR_MODE", "mock")
    client = TestClient(create_app())
    document_id = client.get("/api/documents").json()[0]["id"]

    response = client.get(
        f"/api/documents/{document_id}/pages/1/image",
        params={"source_content_hash": "b" * 64},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Original page snapshot is unavailable"


def test_page_image_url_becomes_invalid_when_source_changes(tmp_path, monkeypatch):
    book = tmp_path / "book"
    book.mkdir()
    source = book / "sample.pdf"
    source.write_text("# Original\n\nOriginal source page.")
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_OCR_MODE", "mock")
    client = TestClient(create_app())
    document_id = client.get("/api/documents").json()[0]["id"]
    client.post(f"/api/documents/{document_id}/process")
    old_page_url = client.get(f"/api/documents/{document_id}/reader").json()["blocks"][
        0
    ]["page_image_url"]
    assert old_page_url is not None and "source_content_hash=" in old_page_url

    source.write_text("# Revised\n\nA different current source page.")
    response = client.get(old_page_url)

    assert response.status_code == 409
    assert response.json()["detail"] == "Original page snapshot is unavailable"


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


def test_page_render_timeout_returns_safe_gateway_timeout(tmp_path, monkeypatch):
    book = tmp_path / "book"
    book.mkdir()
    source = book / "sample.pdf"
    source.write_bytes(b"%PDF-1.4")
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_PAGE_RENDER_TIMEOUT_SECONDS", "13")
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    document_id = client.get("/api/documents").json()[0]["id"]
    observed = {}

    monkeypatch.setattr("glyph.documents.shutil.which", lambda _: "/opt/bin/pdftoppm")

    def timeout_when_bounded(command, **kwargs):
        observed["command"] = command
        observed["timeout"] = kwargs.get("timeout")
        if kwargs.get("timeout") is None:
            return subprocess.CompletedProcess(command, 1, "", "missing timeout")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("glyph.documents.subprocess.run", timeout_when_bounded)

    response = client.get(f"/api/documents/{document_id}/pages/1/image")

    assert response.status_code == 504
    assert response.json()["detail"] == "Page rendering timed out after 13 seconds"
    assert observed["command"][0] == "/opt/bin/pdftoppm"
    assert observed["timeout"] == 13
    assert str(source) not in response.json()["detail"]


def test_page_image_cache_is_invalidated_when_source_changes(tmp_path, monkeypatch):
    book = tmp_path / "book"
    book.mkdir()
    source = book / "sample.pdf"
    source.write_bytes(b"%PDF-1.4 original")
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    app = create_app()
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    render_count = 0

    monkeypatch.setattr("glyph.documents.shutil.which", lambda _: "/opt/bin/pdftoppm")

    def render_page(command, **kwargs):
        nonlocal render_count
        render_count += 1
        output_path = Path(command[-1]).with_suffix(".png")
        output_path.write_bytes(f"render-{render_count}".encode())
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("glyph.documents.subprocess.run", render_page)

    first_image = client.get(f"/api/documents/{document_id}/pages/1/image")
    source.write_bytes(b"%PDF-1.4 changed")
    client.get("/api/documents")
    second_image = client.get(f"/api/documents/{document_id}/pages/1/image")

    assert first_image.content == b"render-1"
    assert second_image.content == b"render-2"
    assert render_count == 2
