from fastapi.testclient import TestClient
from sqlalchemy import select
from support import process_and_wait, wait_for_job

from glyph.ai import ParsedBlock
from glyph.main import create_app
from glyph.models import Block, Document, Page, ProcessingJob, Section, Summary
from glyph.pipeline import block_from_parsed


def test_formula_latex_is_preserved_when_building_persistent_block():
    section = Section(
        id="section-1",
        document_id="document-1",
        title="Returns",
        path="Returns",
        order_index=0,
        summary="報酬率摘要",
    )
    parsed = ParsedBlock(
        order_index=0,
        page_number=3,
        block_type="formula",
        source_text="E[R] = rf + beta * (rm - rf)",
        translated_text="預期報酬公式",
        formula_latex=r"\mathbb{E}[R] = r_f + \beta(r_m-r_f)",
        section_title="Returns",
    )

    block = block_from_parsed("document-1", parsed, {"Returns": section})

    assert block.formula_latex == r"\mathbb{E}[R] = r_f + \beta(r_m-r_f)"


def test_process_document_creates_blocks_translations_sections_and_summary(
    tmp_path, monkeypatch
):
    book = tmp_path / "book"
    book.mkdir()
    (book / "sample.pdf").write_text(
        "# Introduction\n\n"
        "This paper explains alpha and risk.\n\n"
        "1. What is the expected return?\n\n"
        "The expected return is uncertain.",
    )
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_OCR_MODE", "mock")
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    app = create_app()
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]

    process_response = client.post(f"/api/documents/{document_id}/process")

    assert process_response.status_code == 202
    job = wait_for_job(client, process_response.json()["id"])
    assert job["status"] == "completed"
    assert job["stage"] == "completed"
    assert job["progress"] == 100

    job_response = client.get(f"/api/jobs/{job['id']}")
    assert job_response.status_code == 200
    assert job_response.json()["status"] == "completed"

    with app.state.session_factory() as session:
        blocks = session.scalars(
            select(Block)
            .where(Block.document_id == document_id)
            .order_by(Block.order_index)
        ).all()
        sections = session.scalars(
            select(Section).where(Section.document_id == document_id)
        ).all()
        summaries = session.scalars(
            select(Summary).where(Summary.document_id == document_id)
        ).all()

    assert [block.block_type for block in blocks] == [
        "heading",
        "paragraph",
        "question",
        "paragraph",
    ]
    assert blocks[1].translated_text.startswith("繁中翻譯：")
    assert sections[0].title == "Introduction"
    assert "Introduction" in summaries[0].summary_text


def reader_snapshot(session, document_id):
    return {
        "blocks": session.scalars(
            select(Block)
            .where(Block.document_id == document_id)
            .order_by(Block.order_index)
        ).all(),
        "pages": session.scalars(
            select(Page)
            .where(Page.document_id == document_id)
            .order_by(Page.page_number)
        ).all(),
        "sections": session.scalars(
            select(Section)
            .where(Section.document_id == document_id)
            .order_by(Section.order_index)
        ).all(),
        "summaries": session.scalars(
            select(Summary)
            .where(Summary.document_id == document_id)
            .order_by(Summary.id)
        ).all(),
    }


def snapshot_values(snapshot):
    return {
        "blocks": [
            (item.id, item.source_text, item.translated_text)
            for item in snapshot["blocks"]
        ],
        "pages": [
            (item.id, item.page_number, item.raw_text) for item in snapshot["pages"]
        ],
        "sections": [
            (item.id, item.title, item.summary) for item in snapshot["sections"]
        ],
        "summaries": [
            (item.id, item.section_id, item.summary_text)
            for item in snapshot["summaries"]
        ],
    }


def test_persistence_failure_keeps_last_good_reader_snapshot(tmp_path, monkeypatch):
    book = tmp_path / "book"
    book.mkdir()
    (book / "sample.pdf").write_text("# Introduction\n\nExisting readable content.")
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_OCR_MODE", "mock")
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    app = create_app()
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    process_and_wait(client, document_id)
    with app.state.session_factory() as session:
        before = snapshot_values(reader_snapshot(session, document_id))
        document = session.get(Document, document_id)
        assert document is not None
        processed_hash = document.processed_content_hash

    def fail_after_new_page_is_flushed(session, document_id, parsed_sections):
        session.flush()
        raise RuntimeError("persistence unavailable")

    monkeypatch.setattr(
        "glyph.pipeline.persist_sections", fail_after_new_page_is_flushed
    )
    failed_job = process_and_wait(client, document_id)
    with app.state.session_factory() as session:
        after = snapshot_values(reader_snapshot(session, document_id))
        document = session.get(Document, document_id)
        assert document is not None

    assert failed_job["status"] == "failed"
    assert failed_job["error_message"] == (
        "Processing failed. Check the server logs for details."
    )
    assert after == before
    assert document.status == "completed"
    assert document.processed_content_hash == processed_hash


def test_initial_persistence_failure_leaves_no_reader_snapshot(tmp_path, monkeypatch):
    book = tmp_path / "book"
    book.mkdir()
    (book / "sample.pdf").write_text("# Introduction\n\nNew readable content.")
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_OCR_MODE", "mock")
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    app = create_app()
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]

    def fail_after_new_page_is_flushed(session, document_id, parsed_sections):
        session.flush()
        raise RuntimeError("persistence unavailable")

    monkeypatch.setattr(
        "glyph.pipeline.persist_sections", fail_after_new_page_is_flushed
    )

    failed_job = process_and_wait(client, document_id)

    with app.state.session_factory() as session:
        snapshot = snapshot_values(reader_snapshot(session, document_id))
        document = session.get(Document, document_id)
        assert document is not None
    assert failed_job["status"] == "failed"
    assert snapshot == {"blocks": [], "pages": [], "sections": [], "summaries": []}
    assert document.status == "failed"
    assert document.processed_content_hash is None


def test_overlapping_processing_of_same_document_returns_conflict(
    tmp_path, monkeypatch
):
    book = tmp_path / "book"
    book.mkdir()
    (book / "sample.pdf").write_text("# Introduction\n\nReadable content.")
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_OCR_MODE", "mock")
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    app = create_app()
    monkeypatch.setattr(
        app.state.processing_job_executor, "submit", lambda *args, **kwargs: None
    )
    first_client = TestClient(app)
    second_client = TestClient(app)
    document_id = first_client.get("/api/documents").json()[0]["id"]

    first_response = first_client.post(f"/api/documents/{document_id}/process")
    second_response = second_client.post(f"/api/documents/{document_id}/process")

    assert first_response.status_code == 202
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Document is already processing"
    with app.state.session_factory() as session:
        jobs = session.scalars(
            select(ProcessingJob).where(ProcessingJob.document_id == document_id)
        ).all()
    assert len(jobs) == 1
