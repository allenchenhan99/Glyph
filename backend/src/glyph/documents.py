from __future__ import annotations

import hashlib
import shutil

# Page rendering uses a resolved executable, fixed argv, and no shell.
import subprocess  # nosec B404
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from glyph.config import Settings
from glyph.contract_schemas import ImplementationContractLibrarySummaryOut
from glyph.implementation_contracts import (
    ImplementationContractLibrarySummaryView,
    load_implementation_contract_library_summaries,
)
from glyph.models import Block, Document, Section, Summary
from glyph.pipeline import (
    ProcessingConflictError,
    document_process_coordinator,
    get_job,
    process_document,
)
from glyph.research_maps import (
    ResearchMapLibrarySummaryView,
    load_research_map_library_summaries,
)
from glyph.research_schemas import ResearchMapLibrarySummaryOut
from glyph.schemas import BlockOut, DocumentOut, JobOut, ReaderOut, SectionOut

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
UPLOAD_CHUNK_SIZE = 1024 * 1024
FILE_SIGNATURES = {
    ".pdf": b"%PDF-",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
}

router = APIRouter(prefix="/api", tags=["documents"])


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session_factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.session_factory


def get_session(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
):
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def compute_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register_document(
    session: Session,
    source_path: Path,
    status: str | None = None,
    title: str | None = None,
) -> Document:
    existing = session.scalar(
        select(Document).where(Document.source_path == str(source_path))
    )
    if existing is not None:
        refresh_document_state(existing, source_path, status or "discovered")
        existing.title = title or source_path.name
        return existing

    content_hash = compute_hash(source_path)
    document = Document(
        id=str(uuid4()),
        title=title or source_path.name,
        source_path=str(source_path),
        content_hash=content_hash,
        file_type=source_path.suffix.lower().lstrip("."),
        status=status or "discovered",
    )
    session.add(document)
    return document


def has_expected_signature(source_path: Path, suffix: str) -> bool:
    expected = FILE_SIGNATURES[suffix]
    with source_path.open("rb") as stored_file:
        return stored_file.read(len(expected)) == expected


async def store_upload(
    file: UploadFile,
    upload_dir: Path,
    suffix: str,
    max_upload_bytes: int,
) -> Path:
    storage_id = uuid4().hex
    temporary_path = upload_dir / f".{storage_id}.uploading"
    target_path = upload_dir / f"{storage_id}{suffix}"
    byte_count = 0
    try:
        with temporary_path.open("xb") as stored_file:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                byte_count += len(chunk)
                if byte_count > max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=(f"Upload exceeds the {max_upload_bytes} byte limit"),
                    )
                stored_file.write(chunk)
        if not has_expected_signature(temporary_path, suffix):
            raise HTTPException(
                status_code=400,
                detail=f"File content does not match {suffix}",
            )
        temporary_path.replace(target_path)
        return target_path
    finally:
        temporary_path.unlink(missing_ok=True)
        await file.close()


def refresh_document_state(
    document: Document, source_path: Path, unprocessed_status: str
) -> None:
    if not source_path.is_file():
        document.status = "missing"
        return

    previous_hash = document.content_hash
    document.content_hash = compute_hash(source_path)
    document.file_type = source_path.suffix.lower().lstrip(".")
    if document.status == "processing":
        return
    if document.processed_content_hash is not None:
        document.status = (
            "completed"
            if document.processed_content_hash == document.content_hash
            else "stale"
        )
    elif document.status == "missing" or previous_hash != document.content_hash:
        document.status = unprocessed_status


def unprocessed_status_for_path(settings: Settings, source_path: Path) -> str:
    try:
        source_path.resolve().relative_to((settings.data_dir / "uploads").resolve())
    except ValueError:
        return "discovered"
    return "uploaded"


def require_source_path(document: Document) -> Path:
    source_path = Path(document.source_path)
    if not source_path.is_file():
        document.status = "missing"
        raise HTTPException(status_code=409, detail="Source file is missing")
    return source_path


def discover_book_documents(settings: Settings, session: Session) -> list[Document]:
    settings.book_dir.mkdir(parents=True, exist_ok=True)
    documents: list[Document] = []
    for path in sorted(settings.book_dir.iterdir(), key=lambda item: item.name.lower()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            documents.append(register_document(session, path))
    session.flush()
    return documents


def document_to_out(
    document: Document,
    research_map: ResearchMapLibrarySummaryView | None = None,
    implementation_contract: ImplementationContractLibrarySummaryView | None = None,
) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        title=document.title,
        file_type=document.file_type,
        status=document.status,
        research_map=(
            ResearchMapLibrarySummaryOut.model_validate(research_map)
            if research_map is not None
            else None
        ),
        implementation_contract=(
            ImplementationContractLibrarySummaryOut.model_validate(
                implementation_contract
            )
            if implementation_contract is not None
            else None
        ),
    )


def job_to_out(job) -> JobOut:
    return JobOut(
        id=job.id,
        document_id=job.document_id,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        error_message=job.error_message,
    )


def section_to_out(
    section: Section, total_blocks: int, section_block_count: int
) -> SectionOut:
    progress = (
        0 if total_blocks == 0 else round((section_block_count / total_blocks) * 100, 2)
    )
    return SectionOut(
        id=section.id,
        title=section.title,
        path=section.path,
        order_index=section.order_index,
        summary=section.summary,
        progress=progress,
    )


def load_reader_parts(
    session: Session,
    document_id: str,
    source_content_hash: str | None = None,
):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    sections = session.scalars(
        select(Section)
        .where(Section.document_id == document_id)
        .order_by(Section.order_index)
    ).all()
    section_by_id = {section.id: section for section in sections}
    snapshot_hash = source_content_hash or document.processed_content_hash
    blocks = session.scalars(
        select(Block)
        .where(
            Block.document_id == document_id,
            Block.source_content_hash == snapshot_hash,
        )
        .order_by(Block.order_index)
    ).all()
    summary = session.scalar(
        select(Summary)
        .where(Summary.document_id == document_id, Summary.section_id.is_(None))
        .order_by(Summary.created_at.desc())
    )
    return document, sections, section_by_id, blocks, summary


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
) -> list[DocumentOut]:
    discover_book_documents(settings, session)
    documents = session.scalars(
        select(Document).order_by(Document.created_at, Document.title)
    ).all()
    for document in documents:
        source_path = Path(document.source_path)
        refresh_document_state(
            document,
            source_path,
            unprocessed_status_for_path(settings, source_path),
        )
    session.flush()
    summaries = load_research_map_library_summaries(session, documents)
    contract_summaries = load_implementation_contract_library_summaries(
        session, documents
    )
    return [
        document_to_out(
            document,
            summaries.get(document.id),
            contract_summaries.get(document.id),
        )
        for document in documents
    ]


@router.post("/documents/upload", response_model=DocumentOut)
async def upload_document(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    file: UploadFile = File(...),
) -> DocumentOut:
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix or 'missing extension'}",
        )

    upload_dir = settings.data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = await store_upload(file, upload_dir, suffix, settings.max_upload_bytes)
    document = register_document(session, target, status="uploaded", title=filename)
    session.flush()
    return document_to_out(document)


@router.post("/documents/{document_id}/process", response_model=JobOut)
def process_document_route(
    document_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
) -> JobOut:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    require_source_path(document)
    try:
        with document_process_coordinator.acquire(document_id):
            job = process_document(session, settings, document)
    except ProcessingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return job_to_out(job)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job_route(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> JobOut:
    job = get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_to_out(job)


@router.get("/documents/{document_id}/reader", response_model=ReaderOut)
def get_reader(
    document_id: str,
    session: Annotated[Session, Depends(get_session)],
    source_content_hash: Annotated[
        str | None,
        Query(pattern="^[0-9a-f]{64}$"),
    ] = None,
) -> ReaderOut:
    document, sections, section_by_id, blocks, summary = load_reader_parts(
        session, document_id, source_content_hash
    )
    section_block_counts = {
        section.id: sum(1 for block in blocks if block.section_id == section.id)
        for section in sections
    }
    return ReaderOut(
        document=document_to_out(document),
        blocks=[
            BlockOut(
                id=block.id,
                order_index=block.order_index,
                page_number=block.page_number,
                block_type=block.block_type,
                source_text=block.source_text,
                translated_text=block.translated_text,
                formula_latex=block.formula_latex,
                page_image_url=f"/api/documents/{document.id}/pages/{block.page_number}/image",
                section_path=section_by_id[block.section_id].path
                if block.section_id in section_by_id
                else None,
                confidence=block.confidence,
            )
            for block in blocks
        ],
        sections=[
            section_to_out(
                section, len(blocks), section_block_counts.get(section.id, 0)
            )
            for section in sections
        ],
        summary=summary.summary_text if summary is not None else "",
    )


@router.get("/documents/{document_id}/sections", response_model=list[SectionOut])
def get_sections(
    document_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> list[SectionOut]:
    _, sections, _, blocks, _ = load_reader_parts(session, document_id)
    section_block_counts = {
        section.id: sum(1 for block in blocks if block.section_id == section.id)
        for section in sections
    }
    return [
        section_to_out(section, len(blocks), section_block_counts.get(section.id, 0))
        for section in sections
    ]


@router.get("/documents/{document_id}/summary")
def get_summary(
    document_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    _, _, _, _, summary = load_reader_parts(session, document_id)
    return {"summary": summary.summary_text if summary is not None else ""}


@router.get("/documents/{document_id}/pages/{page_number}/image")
def get_page_image(
    document_id: str,
    page_number: int,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
) -> FileResponse:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    source_path = require_source_path(document)
    if document.file_type in {"png", "jpg", "jpeg"}:
        return FileResponse(source_path)
    if document.file_type != "pdf":
        raise HTTPException(status_code=404, detail="Page image unavailable")
    executable = shutil.which("pdftoppm")
    if executable is None:
        raise HTTPException(
            status_code=503, detail="pdftoppm is required for page images"
        )

    page_dir = settings.data_dir / "page-images" / document.id
    page_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = page_dir / (f"page-{page_number:04d}-{document.content_hash[:16]}")
    image_path = output_prefix.with_suffix(".png")
    if not image_path.exists():
        try:
            completed = subprocess.run(  # nosec B603
                [
                    executable,
                    "-f",
                    str(page_number),
                    "-l",
                    str(page_number),
                    "-singlefile",
                    "-png",
                    "-r",
                    "144",
                    str(source_path),
                    str(output_prefix),
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=settings.page_render_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            image_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=504,
                detail=(
                    "Page rendering timed out after "
                    f"{settings.page_render_timeout_seconds} seconds"
                ),
            ) from exc
        if completed.returncode != 0 or not image_path.exists():
            image_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=500,
                detail="Could not render page image",
            )
    return FileResponse(image_path, media_type="image/png")
