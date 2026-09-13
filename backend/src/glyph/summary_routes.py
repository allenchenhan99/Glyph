from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from glyph.config import Settings
from glyph.documents import (
    get_session,
    get_settings,
    refresh_document_state,
    unprocessed_status_for_path,
)
from glyph.models import Document
from glyph.summaries import (
    SummaryConflictError,
    SummaryNotFoundError,
    SummaryStateView,
    load_summary_state,
)
from glyph.summary_jobs import (
    SummaryExecutorClosedError,
    SummaryJobConflictError,
    abandon_unsubmitted_summary_job,
    enqueue_summary_job,
)
from glyph.summary_schemas import (
    SummaryClaimOut,
    SummaryEvidenceOut,
    SummaryJobOut,
    SummaryStateOut,
    SummaryVersionOut,
)

router = APIRouter(prefix="/api", tags=["summaries"])


def refresh_source_state(
    session: Session, settings: Settings, document_id: str
) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    source_path = Path(document.source_path)
    refresh_document_state(
        document, source_path, unprocessed_status_for_path(settings, source_path)
    )
    session.flush()
    return document


def state_to_out(state: SummaryStateView) -> SummaryStateOut:
    version = state.version
    return SummaryStateOut(
        status=state.status,
        provider=state.provider,
        model=state.model,
        version=SummaryVersionOut(
            id=version.id,
            source_content_hash=version.source_content_hash,
            reader_fingerprint=version.reader_fingerprint,
            provider=version.provider,
            model=version.model,
            created_at=version.created_at,
            claims=[
                SummaryClaimOut(
                    id=claim.id,
                    section_path=claim.section_path,
                    text=claim.text,
                    evidence=[
                        SummaryEvidenceOut(
                            block_id=item.block_id,
                            quote_text=item.quote_text,
                            quote_start=item.quote_start,
                            quote_end=item.quote_end,
                            page_number=item.page_number,
                        )
                        for item in claim.evidence
                    ],
                )
                for claim in version.claims
            ],
        )
        if version is not None
        else None,
        job=SummaryJobOut(
            id=state.job.id,
            status=state.job.status,
            error_message=state.job.error_message,
        )
        if state.job is not None
        else None,
    )


@router.get("/documents/{document_id}/summaries", response_model=SummaryStateOut)
def get_summaries(
    document_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
) -> SummaryStateOut:
    refresh_source_state(session, settings, document_id)
    return state_to_out(load_summary_state(session, document_id, settings))


@router.post(
    "/documents/{document_id}/summaries",
    response_model=SummaryStateOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_summaries(
    document_id: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
) -> SummaryStateOut:
    refresh_source_state(session, settings, document_id)
    try:
        job = enqueue_summary_job(session, document_id)
        session.commit()
    except SummaryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (SummaryConflictError, SummaryJobConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        request.app.state.summary_job_executor.submit(job.id)
    except SummaryExecutorClosedError as exc:
        abandon_unsubmitted_summary_job(session, job.id)
        session.commit()
        raise HTTPException(
            status_code=503,
            detail="Glyph is shutting down and cannot start summary generation. "
            "Retry after it restarts.",
        ) from exc
    return state_to_out(load_summary_state(session, document_id, settings))
