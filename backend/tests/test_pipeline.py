from fastapi.testclient import TestClient
from sqlalchemy import select

from glyph.ai import ParsedBlock
from glyph.main import create_app
from glyph.models import Block, Section, Summary
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

    assert process_response.status_code == 200
    job = process_response.json()
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


def test_failed_reprocessing_keeps_previous_reader_content(tmp_path, monkeypatch):
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
    client.post(f"/api/documents/{document_id}/process")

    class FailingAdapter:
        def parse_translate_and_summarize(self, page_text):
            raise RuntimeError("CLI unavailable")

    monkeypatch.setattr(
        "glyph.pipeline.create_ai_adapter", lambda settings: FailingAdapter()
    )
    failed_job = client.post(f"/api/documents/{document_id}/process").json()
    reader = client.get(f"/api/documents/{document_id}/reader").json()

    assert failed_job["status"] == "failed"
    assert [block["source_text"] for block in reader["blocks"]] == [
        "Introduction",
        "Existing readable content.",
    ]
