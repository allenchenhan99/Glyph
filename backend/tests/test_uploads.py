import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from glyph.main import create_app
from glyph.models import Document


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
    assert "source_path" not in payload
    stored_files = list((tmp_path / "data" / "uploads").glob("*.pdf"))
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == b"%PDF-1.4"


def test_uploaded_document_remains_in_catalog_after_refresh_and_restart(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(tmp_path / "book"))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    first_client = TestClient(create_app())
    uploaded = first_client.post(
        "/api/documents/upload",
        files={"file": ("uploaded.pdf", b"%PDF-1.4", "application/pdf")},
    ).json()

    first_catalog = first_client.get("/api/documents").json()
    second_catalog = TestClient(create_app()).get("/api/documents").json()

    assert uploaded["id"] in {item["id"] for item in first_catalog}
    assert uploaded["id"] in {item["id"] for item in second_catalog}


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


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("paper.pdf", b"%PDF-1.7\ncontent", "application/pdf"),
        ("figure.png", b"\x89PNG\r\n\x1a\ncontent", "image/png"),
        ("photo.jpg", b"\xff\xd8\xff\xe0content", "image/jpeg"),
    ],
)
def test_upload_accepts_supported_file_signatures(
    tmp_path, monkeypatch, filename, content, content_type
):
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(tmp_path / "book"))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())

    response = client.post(
        "/api/documents/upload",
        files={"file": (filename, content, content_type)},
    )

    assert response.status_code == 200
    assert response.json()["title"] == filename


def test_upload_rejects_signature_mismatch_and_removes_temporary_file(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(tmp_path / "book"))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())

    response = client.post(
        "/api/documents/upload",
        files={"file": ("disguised.pdf", b"plain text", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "File content does not match .pdf"
    assert list((tmp_path / "data" / "uploads").iterdir()) == []


def test_upload_rejects_oversized_payload_and_removes_temporary_file(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(tmp_path / "book"))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_MAX_UPLOAD_BYTES", "8")
    client = TestClient(create_app())

    response = client.post(
        "/api/documents/upload",
        files={"file": ("large.pdf", b"%PDF-1.7 too large", "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Upload exceeds the 8 byte limit"
    assert list((tmp_path / "data" / "uploads").iterdir()) == []


def test_same_name_uploads_use_distinct_storage_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(tmp_path / "book"))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    app = create_app()
    client = TestClient(app)

    first = client.post(
        "/api/documents/upload",
        files={"file": ("paper.pdf", b"%PDF-1.4 first", "application/pdf")},
    ).json()
    second = client.post(
        "/api/documents/upload",
        files={"file": ("paper.pdf", b"%PDF-1.4 second", "application/pdf")},
    ).json()

    with app.state.session_factory() as session:
        documents = session.scalars(
            select(Document).where(Document.title == "paper.pdf")
        ).all()
    assert first["id"] != second["id"]
    assert len(documents) == 2
    assert len({document.source_path for document in documents}) == 2
    assert len(list((tmp_path / "data" / "uploads").glob("*.pdf"))) == 2


def test_upload_sanitizes_path_like_filename(tmp_path, monkeypatch):
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(tmp_path / "book"))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())

    response = client.post(
        "/api/documents/upload",
        files={"file": ("../paper.pdf", b"%PDF-1.4", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "paper.pdf"
