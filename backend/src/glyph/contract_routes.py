from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from glyph.contract_domain import decode_contract_value
from glyph.contract_jobs import (
    ContractJobConflictError,
    ContractJobNotFoundError,
    enqueue_implementation_contract_job,
)
from glyph.contract_schemas import (
    ContractEnqueueRequest,
    ContractJobOut,
    ContractResolutionOut,
    ContractResolutionRequest,
    ImplementationContractDiffOut,
    ImplementationContractOut,
    ImplementationContractVersionOut,
)
from glyph.documents import get_session
from glyph.implementation_contracts import (
    ImplementationContractConflictError,
    ImplementationContractNotFoundError,
    activate_implementation_contract,
    append_contract_resolution,
    diff_implementation_contracts,
    list_implementation_contract_versions,
    load_implementation_contract,
)
from glyph.models import ImplementationContractJob, ImplementationContractVersion

router = APIRouter(prefix="/api", tags=["implementation-contract"])


@router.post(
    "/documents/{document_id}/implementation-contract",
    response_model=ContractJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_contract(
    document_id: str,
    payload: ContractEnqueueRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> ContractJobOut:
    try:
        job = enqueue_implementation_contract_job(
            session,
            document_id,
            payload.research_map_version_id,
        )
        session.commit()
    except ContractJobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ContractJobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    response = ContractJobOut.model_validate(job)
    request.app.state.contract_job_executor.submit(job.id)
    return response


@router.get(
    "/implementation-contract-jobs/{job_id}",
    response_model=ContractJobOut,
)
def get_contract_job(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ContractJobOut:
    job = session.get(ImplementationContractJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=404, detail="Implementation Contract job not found"
        )
    return ContractJobOut.model_validate(job)


@router.get(
    "/documents/{document_id}/implementation-contract",
    response_model=ImplementationContractOut,
)
def get_active_contract(
    document_id: str,
    session: Annotated[Session, Depends(get_session)],
):
    version_id = session.scalar(
        select(ImplementationContractVersion.id).where(
            ImplementationContractVersion.document_id == document_id,
            ImplementationContractVersion.is_active.is_(True),
        )
    )
    if version_id is None:
        raise HTTPException(
            status_code=404, detail="Active Implementation Contract not found"
        )
    return load_implementation_contract(session, version_id)


@router.get(
    "/documents/{document_id}/implementation-contract/versions",
    response_model=tuple[ImplementationContractVersionOut, ...],
)
def get_contract_versions(
    document_id: str,
    session: Annotated[Session, Depends(get_session)],
):
    try:
        return list_implementation_contract_versions(session, document_id)
    except ImplementationContractNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/implementation-contracts/{version_id}",
    response_model=ImplementationContractOut,
)
def get_contract_version(
    version_id: str,
    session: Annotated[Session, Depends(get_session)],
):
    try:
        return load_implementation_contract(session, version_id)
    except ImplementationContractNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/implementation-contracts/{version_id}/diff",
    response_model=ImplementationContractDiffOut,
)
def get_contract_diff(
    version_id: str,
    against: Annotated[str, Query(min_length=1)],
    session: Annotated[Session, Depends(get_session)],
):
    try:
        return diff_implementation_contracts(session, version_id, against)
    except ImplementationContractNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ImplementationContractConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch(
    "/implementation-contract-items/{item_id}/resolution",
    response_model=ContractResolutionOut,
)
def resolve_contract_item(
    item_id: str,
    payload: ContractResolutionRequest,
    session: Annotated[Session, Depends(get_session)],
):
    try:
        value = (
            decode_contract_value(payload.resolved_value.model_dump(mode="json"))
            if payload.resolved_value is not None
            else None
        )
        return append_contract_resolution(
            session,
            item_id,
            status=payload.status,
            based_on_item_signature=payload.based_on_item_signature,
            value=value,
            reason=payload.reason,
            request_id=payload.request_id,
        )
    except ImplementationContractNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ImplementationContractConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/implementation-contracts/{version_id}/activate",
    response_model=ImplementationContractOut,
)
def activate_contract_version(
    version_id: str,
    session: Annotated[Session, Depends(get_session)],
):
    try:
        return activate_implementation_contract(session, version_id)
    except ImplementationContractNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ImplementationContractConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
