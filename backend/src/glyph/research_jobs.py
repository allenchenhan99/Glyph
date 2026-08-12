from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from threading import Lock
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from glyph.models import Document, ResearchMapJob
from glyph.research_ai import ResearchMapProvider
from glyph.research_maps import ResearchMapService

logger = logging.getLogger(__name__)

ProviderFactory = Callable[[], ResearchMapProvider]
StageObserver = Callable[[str, float], None]


class ResearchJobConflictError(RuntimeError):
    """Raised when a document already has queued or running map work."""


class ResearchJobNotFoundError(LookupError):
    """Raised when a job or its document is unavailable."""


class ResearchJobExecutorClosedError(RuntimeError):
    """Raised when work is submitted during application shutdown."""


def enqueue_research_map_job(
    session: Session,
    document_id: str,
) -> ResearchMapJob:
    if session.get(Document, document_id) is None:
        raise ResearchJobNotFoundError("Document not found")
    active = session.scalar(
        select(ResearchMapJob.id).where(
            ResearchMapJob.document_id == document_id,
            ResearchMapJob.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        raise ResearchJobConflictError(
            "A Research Map job is already queued or running"
        )
    job = ResearchMapJob(
        id=str(uuid4()),
        document_id=document_id,
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
        raise ResearchJobConflictError(
            "A Research Map job is already queued or running"
        ) from exc
    return job


def execute_research_map_job(
    session_factory: sessionmaker[Session],
    job_id: str,
    provider_factory: ProviderFactory,
    stage_observer: StageObserver | None = None,
) -> None:
    session = session_factory()
    try:
        job = _claim_job(session, job_id)

        def record_stage(stage: str, progress: float) -> None:
            _record_stage(session, job, stage, progress)
            if stage_observer is not None:
                stage_observer(stage, progress)

        try:
            version = ResearchMapService(
                session,
                provider_factory(),
                stage_callback=record_stage,
            ).generate(job.document_id)
            job.map_version_id = version.id
            job.status = "completed"
            job.stage = "completed"
            job.progress = 100
            job.error_message = None
            job.lease_token = None
            session.commit()
        except Exception:  # noqa: BLE001 - providers are an external boundary
            session.rollback()
            logger.exception(
                "Research Map job failed",
                extra={"job_id": job_id, "document_id": job.document_id},
            )
            failed = session.get(ResearchMapJob, job_id)
            if failed is not None:
                failed.status = "failed"
                failed.stage = "failed"
                failed.progress = 100
                failed.error_message = (
                    "Research Map generation failed. Check the server logs for details."
                )
                failed.lease_token = None
                session.commit()
    finally:
        session.close()


def recover_interrupted_jobs(
    session: Session,
    max_attempts: int,
) -> tuple[str, ...]:
    running = session.scalars(
        select(ResearchMapJob)
        .where(ResearchMapJob.status == "running")
        .order_by(ResearchMapJob.created_at, ResearchMapJob.id)
    ).all()
    queued_ids: list[str] = []
    for job in running:
        job.lease_token = None
        if job.attempt_count >= max_attempts:
            job.status = "failed"
            job.stage = "failed"
            job.progress = 100
            job.error_message = (
                "Research Map generation was interrupted too many times."
            )
        else:
            job.status = "queued"
            job.stage = "queued"
            job.progress = 0
            job.error_message = None
            queued_ids.append(job.id)
    session.flush()
    return tuple(queued_ids)


def list_queued_job_ids(session: Session) -> tuple[str, ...]:
    return tuple(
        session.scalars(
            select(ResearchMapJob.id)
            .where(ResearchMapJob.status == "queued")
            .order_by(ResearchMapJob.created_at, ResearchMapJob.id)
        ).all()
    )


class ResearchMapJobExecutor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        provider_factory: ProviderFactory,
    ) -> None:
        self._session_factory = session_factory
        self._provider_factory = provider_factory
        self._pool = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="glyph-research-map",
        )
        self._guard = Lock()
        self._accepting = True
        self._futures: set[Future[None]] = set()

    def submit(self, job_id: str) -> Future[None]:
        with self._guard:
            if not self._accepting:
                raise ResearchJobExecutorClosedError(
                    "Research Map executor is not accepting new work"
                )
            future = self._pool.submit(
                execute_research_map_job,
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
                "Research Map executor shutdown timed out",
                extra={"pending_jobs": len(pending)},
            )

    def _discard_future(self, future: Future[None]) -> None:
        with self._guard:
            self._futures.discard(future)


def _claim_job(session: Session, job_id: str) -> ResearchMapJob:
    job = session.get(ResearchMapJob, job_id)
    if job is None:
        raise ResearchJobNotFoundError("Research Map job not found")
    if job.status != "queued":
        raise ResearchJobConflictError("Research Map job is not queued")
    job.status = "running"
    job.stage = "evidence"
    job.progress = 5
    job.attempt_count += 1
    job.lease_token = uuid4().hex
    session.commit()
    return job


def _record_stage(
    session: Session,
    job: ResearchMapJob,
    stage: str,
    progress: float,
) -> None:
    job.stage = stage
    job.progress = progress
    session.commit()
