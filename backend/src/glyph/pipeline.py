from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from glyph.ai import ParsedBlock
from glyph.models import (
    Block,
    Document,
    ImplementationContractEvidence,
    Page,
    ProcessingJob,
    ResearchEvidence,
    Section,
    Summary,
)

logger = logging.getLogger(__name__)


def replace_reader_snapshot(session: Session, document: Document, ocr_pages, parsed):
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
        session.add(
            block_from_parsed(
                document.id,
                parsed_block,
                section_by_title,
                source_content_hash=document.content_hash,
            )
        )
    session.add(
        Summary(
            id=str(uuid4()),
            document_id=document.id,
            section_id=None,
            summary_text=parsed.summary,
        )
    )
    document.status = "completed"
    document.processed_content_hash = document.content_hash
    session.flush()


def clear_document_outputs(session: Session, document_id: str) -> None:
    research_cited_block_ids = (
        select(ResearchEvidence.block_id)
        .join(Block, ResearchEvidence.block_id == Block.id)
        .where(Block.document_id == document_id)
    )
    contract_cited_block_ids = (
        select(ImplementationContractEvidence.block_id)
        .join(Block, ImplementationContractEvidence.block_id == Block.id)
        .where(Block.document_id == document_id)
    )
    cited_block_ids = research_cited_block_ids.union(contract_cited_block_ids)
    session.execute(
        update(Block)
        .where(Block.document_id == document_id, Block.id.in_(cited_block_ids))
        .values(section_id=None)
    )
    session.execute(
        delete(Block).where(
            Block.document_id == document_id,
            Block.id.not_in(cited_block_ids),
        )
    )
    for model in (Summary, Page, Section):
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
    source_content_hash: str | None = None,
) -> Block:
    section = section_by_title.get(parsed_block.section_title) or next(
        iter(section_by_title.values())
    )
    return Block(
        id=str(uuid4()),
        document_id=document_id,
        source_content_hash=source_content_hash,
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
