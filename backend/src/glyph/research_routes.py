from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from glyph.documents import get_session
from glyph.models import ResearchMapJob
from glyph.research_jobs import (
    ResearchJobConflictError,
    ResearchJobNotFoundError,
    enqueue_research_map_job,
)
from glyph.research_maps import (
    ResearchMapConflictError,
    ResearchMapNotFoundError,
    activate_research_map,
    append_node_review,
    diff_research_maps,
    list_research_map_versions,
    load_active_research_map,
    load_research_map,
    require_current_reader,
)
from glyph.research_schemas import (
    ResearchMapDiffOut,
    ResearchMapJobOut,
    ResearchMapOut,
    ResearchMapVersionOut,
    ResearchNodeReviewRecordOut,
    ResearchNodeReviewRequest,
)

router = APIRouter(prefix="/api", tags=["research-map"])


@router.post(
    "/documents/{document_id}/research-map",
    response_model=ResearchMapJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_research_map(
    document_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> ResearchMapJobOut:
    try:
        require_current_reader(session, document_id)
        job = enqueue_research_map_job(session, document_id)
        session.commit()
    except (ResearchMapNotFoundError, ResearchJobNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ResearchMapConflictError, ResearchJobConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    payload = ResearchMapJobOut.model_validate(job)
    request.app.state.research_job_executor.submit(job.id)
    return payload


@router.get(
    "/research-map-jobs/{job_id}",
    response_model=ResearchMapJobOut,
)
def get_research_map_job(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ResearchMapJobOut:
    job = session.get(ResearchMapJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research Map job not found")
    return ResearchMapJobOut.model_validate(job)


@router.get(
    "/documents/{document_id}/research-map",
    response_model=ResearchMapOut,
)
def get_active_research_map(
    document_id: str,
    session: Annotated[Session, Depends(get_session)],
):
    try:
        return load_active_research_map(session, document_id)
    except ResearchMapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/documents/{document_id}/research-map/versions",
    response_model=tuple[ResearchMapVersionOut, ...],
)
def get_research_map_versions(
    document_id: str,
    session: Annotated[Session, Depends(get_session)],
):
    try:
        return list_research_map_versions(session, document_id)
    except ResearchMapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/research-maps/{version_id}", response_model=ResearchMapOut)
def get_research_map_version(
    version_id: str,
    session: Annotated[Session, Depends(get_session)],
):
    try:
        return load_research_map(session, version_id)
    except ResearchMapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/research-maps/{version_id}/diff",
    response_model=ResearchMapDiffOut,
)
def get_research_map_diff(
    version_id: str,
    against: Annotated[str, Query(min_length=1)],
    session: Annotated[Session, Depends(get_session)],
):
    try:
        return diff_research_maps(session, version_id, against)
    except ResearchMapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResearchMapConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch(
    "/research-nodes/{node_id}/review",
    response_model=ResearchNodeReviewRecordOut,
)
def review_research_node(
    node_id: str,
    payload: ResearchNodeReviewRequest,
    session: Annotated[Session, Depends(get_session)],
):
    try:
        return append_node_review(
            session,
            node_id,
            status=payload.status,
            based_on_node_signature=payload.based_on_node_signature,
            corrected_claim_text=payload.corrected_claim_text,
            review_note=payload.review_note,
        )
    except ResearchMapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResearchMapConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/research-maps/{version_id}/activate",
    response_model=ResearchMapOut,
)
def activate_research_map_version(
    version_id: str,
    session: Annotated[Session, Depends(get_session)],
):
    try:
        activate_research_map(session, version_id)
        return load_research_map(session, version_id)
    except ResearchMapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResearchMapConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
