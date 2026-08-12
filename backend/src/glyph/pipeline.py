from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from glyph.ai import ParsedBlock, create_ai_adapter
from glyph.config import Settings
from glyph.models import Block, Document, Page, ProcessingJob, Section, Summary
from glyph.ocr import create_ocr_adapter


def process_document(
    session: Session, settings: Settings, document: Document
) -> ProcessingJob:
    job = ProcessingJob(
        id=str(uuid4()),
        document_id=document.id,
        status="running",
        stage="ocr",
        progress=10,
        error_message=None,
    )
    session.add(job)
    document.status = "processing"
    session.flush()

    try:
        ocr_pages = create_ocr_adapter(settings).extract_pages(
            Path(document.source_path)
        )
        job.stage = "ai_parse"
        job.progress = 45
        parsed = create_ai_adapter(settings).parse_translate_and_summarize(
            [(page.page_number, page.text) for page in ocr_pages]
        )

        job.stage = "persist"
        job.progress = 75
        clear_document_outputs(session, document.id)
        for page in ocr_pages:
            session.add(
                Page(
                    id=str(uuid4()),
                    document_id=document.id,
                    page_number=page.page_number,
                    image_path=page.image_path,
                    raw_text=page.text,
                )
            )
        section_by_title = persist_sections(session, document.id, parsed.sections)
        for parsed_block in parsed.blocks:
            session.add(block_from_parsed(document.id, parsed_block, section_by_title))
        session.add(
            Summary(
                id=str(uuid4()),
                document_id=document.id,
                section_id=None,
                summary_text=parsed.summary,
            )
        )

        job.status = "completed"
        job.stage = "completed"
        job.progress = 100
        document.status = "completed"
    except Exception as exc:  # noqa: BLE001 - adapters may raise provider errors
        job.status = "failed"
        job.stage = "failed"
        job.progress = 100
        job.error_message = str(exc)
        document.status = "failed"
    session.flush()
    return job


def clear_document_outputs(session: Session, document_id: str) -> None:
    for model in (Block, Summary, Page, Section):
        session.execute(delete(model).where(model.document_id == document_id))


def persist_sections(
    session: Session, document_id: str, parsed_sections
) -> dict[str, Section]:
    section_by_title: dict[str, Section] = {}
    for parsed_section in parsed_sections:
        section = Section(
            id=str(uuid4()),
            document_id=document_id,
            title=parsed_section.title,
            path=parsed_section.path,
            order_index=parsed_section.order_index,
            parent_id=None,
            summary=parsed_section.summary,
        )
        session.add(section)
        section_by_title[section.title] = section
        session.add(
            Summary(
                id=str(uuid4()),
                document_id=document_id,
                section_id=section.id,
                summary_text=section.summary,
            )
        )
    session.flush()
    return section_by_title


def block_from_parsed(
    document_id: str,
    parsed_block: ParsedBlock,
    section_by_title: dict[str, Section],
) -> Block:
    section = section_by_title.get(parsed_block.section_title) or next(
        iter(section_by_title.values())
    )
    return Block(
        id=str(uuid4()),
        document_id=document_id,
        section_id=section.id,
        order_index=parsed_block.order_index,
        page_number=parsed_block.page_number,
        block_type=parsed_block.block_type,
        source_text=parsed_block.source_text,
        translated_text=parsed_block.translated_text,
        formula_latex=parsed_block.formula_latex,
        confidence=parsed_block.confidence,
    )


def get_job(session: Session, job_id: str) -> ProcessingJob | None:
    return session.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))
