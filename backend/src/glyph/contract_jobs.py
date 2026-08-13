from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from threading import Lock
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from glyph.contract_ai import ImplementationContractProvider
from glyph.implementation_contracts import (
    ImplementationContractService,
    contract_mutation_coordinator,
)
from glyph.models import Block, Document, ImplementationContractJob, ResearchMapVersion

logger = logging.getLogger(__name__)

ContractProviderFactory = Callable[[], ImplementationContractProvider]
StageObserver = Callable[[str, float], None]

_STAGES = (
    "load_context",
    "extract_requirements",
    "validate_evidence",
    "synthesize_contract",
    "audit_readiness",
    "persist_and_activate",
)
_STAGE_INDEX = {stage: index for index, stage in enumerate(_STAGES)}


class ContractJobConflictError(RuntimeError):
    """Raised when current state cannot accept or run a contract job."""


class ContractJobNotFoundError(LookupError):
    """Raised when a contract job or one of its requested inputs is missing."""


class ContractJobExecutorClosedError(RuntimeError):
    """Raised when work is submitted during application shutdown."""


def enqueue_implementation_contract_job(
    session: Session,
    document_id: str,
    research_map_version_id: str | None = None,
) -> ImplementationContractJob:
    requested_map_id = _resolve_requested_map_id(
        session, document_id, research_map_version_id
    )
    active = session.scalar(
        select(ImplementationContractJob.id).where(
            ImplementationContractJob.document_id == document_id,
            ImplementationContractJob.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        raise ContractJobConflictError(
            "An Implementation Contract job is already queued or running"
        )
    job = ImplementationContractJob(
        id=str(uuid4()),
        document_id=document_id,
        requested_research_map_version_id=requested_map_id,
        contract_version_id=None,
        status="queued",
        stage="queued",
        progress=0,
        error_message=None,
        attempt_count=0,
        lease_token=None,
    )
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError as exc:
        raise ContractJobConflictError(
            "An Implementation Contract job is already queued or running"
        ) from exc
    return job


def execute_implementation_contract_job(
    session_factory: sessionmaker[Session],
    job_id: str,
    provider_factory: ContractProviderFactory,
    stage_observer: StageObserver | None = None,
) -> None:
    session = session_factory()
    try:
        job = _claim_job(session, job_id)

        def record_stage(stage: str, progress: float) -> None:
            _record_stage(session, job, stage, progress)
            if stage_observer is not None:
                stage_observer(stage, progress)

        with contract_mutation_coordinator.acquire(job.document_id):
            try:
                version = ImplementationContractService(
                    session,
                    provider_factory(),
                    stage_callback=record_stage,
                ).generate(
                    job.document_id,
                    job.requested_research_map_version_id,
                )
                job.contract_version_id = version.id
                job.status = "completed"
                job.stage = "completed"
                job.progress = 100
                job.error_message = None
                job.lease_token = None
                session.commit()
            except Exception:  # noqa: BLE001 - providers are an external boundary
                document_id = job.document_id
                session.rollback()
                logger.exception(
                    "Implementation Contract job failed",
                    extra={"job_id": job_id, "document_id": document_id},
                )
                failed = session.get(ImplementationContractJob, job_id)
                if failed is not None:
                    failed.status = "failed"
                    failed.stage = "failed"
                    failed.progress = 100
                    failed.error_message = (
                        "Implementation Contract generation failed. "
                        "Check the server logs for details."
                    )
                    failed.lease_token = None
                    session.commit()
    finally:
        session.close()


def recover_interrupted_contract_jobs(
    session: Session,
    max_attempts: int,
) -> tuple[str, ...]:
    running = session.scalars(
        select(ImplementationContractJob)
        .where(ImplementationContractJob.status == "running")
        .order_by(
            ImplementationContractJob.created_at,
            ImplementationContractJob.id,
        )
    ).all()
    queued_ids: list[str] = []
    for job in running:
        job.lease_token = None
        if job.attempt_count >= max_attempts:
            job.status = "failed"
            job.stage = "failed"
            job.progress = 100
            job.error_message = (
                "Implementation Contract generation was interrupted too many times."
            )
        else:
            job.status = "queued"
            job.stage = "queued"
            job.progress = 0
            job.error_message = None
            queued_ids.append(job.id)
    session.flush()
    return tuple(queued_ids)


def list_queued_contract_job_ids(session: Session) -> tuple[str, ...]:
    return tuple(
        session.scalars(
            select(ImplementationContractJob.id)
            .where(ImplementationContractJob.status == "queued")
            .order_by(
                ImplementationContractJob.created_at,
                ImplementationContractJob.id,
            )
        ).all()
    )


class ImplementationContractJobExecutor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        provider_factory: ContractProviderFactory,
    ) -> None:
        self._session_factory = session_factory
        self._provider_factory = provider_factory
        self._pool = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="glyph-implementation-contract",
        )
        self._guard = Lock()
        self._accepting = True
        self._futures: set[Future[None]] = set()

    def submit(self, job_id: str) -> Future[None]:
        with self._guard:
            if not self._accepting:
                raise ContractJobExecutorClosedError(
                    "Implementation Contract executor is not accepting new work"
                )
            future = self._pool.submit(
                execute_implementation_contract_job,
                self._session_factory,
                job_id,
                self._provider_factory,
            )
            self._futures.add(future)
        future.add_done_callback(self._discard_future)
        return future

    def shutdown(self, timeout_seconds: float = 10) -> None:
        with self._guard:
            self._accepting = False
            futures = tuple(self._futures)
        _, pending = wait(futures, timeout=timeout_seconds)
        self._pool.shutdown(wait=not pending, cancel_futures=True)
        if pending:
            logger.warning(
                "Implementation Contract executor shutdown timed out",
                extra={"pending_jobs": len(pending)},
            )

    def _discard_future(self, future: Future[None]) -> None:
        with self._guard:
            self._futures.discard(future)


def _resolve_requested_map_id(
    session: Session,
    document_id: str,
    research_map_version_id: str | None,
) -> str:
    document = session.get(Document, document_id)
    if document is None:
        raise ContractJobNotFoundError("Document not found")
    if (
        document.status != "completed"
        or document.processed_content_hash is None
        or document.processed_content_hash != document.content_hash
    ):
        raise ContractJobConflictError(
            "Implementation Contract requires a current completed Reader snapshot"
        )
    has_current_block = session.scalar(
        select(Block.id).where(
            Block.document_id == document_id,
            Block.source_content_hash == document.processed_content_hash,
        )
    )
    if has_current_block is None:
        raise ContractJobConflictError("Document has no current Reader blocks")

    if research_map_version_id is None:
        research_map = session.scalar(
            select(ResearchMapVersion).where(
                ResearchMapVersion.document_id == document_id,
                ResearchMapVersion.is_active.is_(True),
            )
        )
        if research_map is None:
            raise ContractJobConflictError("Document has no active Research Map")
    else:
        research_map = session.get(ResearchMapVersion, research_map_version_id)
        if research_map is None:
            raise ContractJobNotFoundError("Research Map not found")
    if research_map.document_id != document_id:
        raise ContractJobConflictError("Research Map must belong to the same document")
    if research_map.source_content_hash != document.content_hash:
        raise ContractJobConflictError("Research Map must use the same current source")
    if research_map.status not in {"complete", "partial"}:
        raise ContractJobConflictError("Research Map must be complete or partial")
    return research_map.id


def _claim_job(session: Session, job_id: str) -> ImplementationContractJob:
    job = session.get(ImplementationContractJob, job_id)
    if job is None:
        raise ContractJobNotFoundError("Implementation Contract job not found")
    if job.status != "queued":
        raise ContractJobConflictError("Implementation Contract job is not queued")
    job.status = "running"
    job.stage = "load_context"
    job.progress = 1
    job.attempt_count += 1
    job.lease_token = uuid4().hex
    session.commit()
    return job


def _record_stage(
    session: Session,
    job: ImplementationContractJob,
    stage: str,
    progress: float,
) -> None:
    if stage not in _STAGE_INDEX:
        raise RuntimeError(f"Unknown Implementation Contract stage: {stage}")
    current_index = _STAGE_INDEX.get(job.stage, -1)
    next_index = _STAGE_INDEX[stage]
    if next_index < current_index or next_index > current_index + 1:
        raise RuntimeError("Implementation Contract stages must be monotonic")
    if progress < job.progress or progress > 100:
        raise RuntimeError("Implementation Contract progress must be monotonic")
    job.stage = stage
    job.progress = progress
    session.commit()
