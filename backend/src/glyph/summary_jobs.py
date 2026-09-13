"""Durable summary generation with one local worker and short transactions.

Inputs are snapshotted before any external call; publication re-verifies the
Reader, the source file and the job's running ownership in one transaction.
Unfinished jobs found at startup become interrupted; nothing is replayed.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor, wait
from threading import Event, Lock
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from glyph.cli_ai import CliAiError, TranslationCancelledError
from glyph.config import Settings
from glyph.models import SummaryJob
from glyph.summaries import (
    SummaryConflictError,
    SummaryInputs,
    SummaryNotFoundError,
    capture_summary_inputs,
    persist_summary_version,
    validate_claims,
)
from glyph.summary_ai import create_summary_provider
from glyph.summary_domain import SummaryValidationError

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("queued", "running")
TERMINAL_STATUSES = ("completed", "failed", "interrupted")
INTERRUPTED_MESSAGE = (
    "Summary generation was interrupted by a restart. Retry to generate again; "
    "the previous summary version, if any, is unchanged."
)
GENERIC_FAILURE_MESSAGE = (
    "Summary generation failed. Check the server logs for details."
)


class SummaryJobConflictError(RuntimeError):
    """A summary job is already queued or running for the document."""


class SummaryExecutorClosedError(RuntimeError):
    """Raised when work is submitted during application shutdown."""


def enqueue_summary_job(session: Session, document_id: str) -> SummaryJob:
    """Validate the current Reader and commit a queued job row."""
    capture_summary_inputs(session, document_id)  # raises not-found / conflict
    active = session.scalar(
        select(SummaryJob.id).where(
            SummaryJob.document_id == document_id,
            SummaryJob.status.in_(ACTIVE_STATUSES),
        )
    )
    if active is not None:
        raise SummaryJobConflictError("A summary job is already queued or running")
    job = SummaryJob(
        id=str(uuid4()),
        document_id=document_id,
        status="queued",
        stage="queued",
        progress=0,
        error_message=None,
    )
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError as exc:
        raise SummaryJobConflictError(
            "A summary job is already queued or running"
        ) from exc
    return job


def abandon_unsubmitted_summary_job(session: Session, job_id: str) -> None:
    job = session.get(SummaryJob, job_id)
    if job is not None and job.status == "queued":
        _finish(
            job,
            "interrupted",
            "The server is shutting down and could not start summary generation. "
            "Retry once Glyph is running again.",
        )


def mark_interrupted_summary_jobs(session: Session) -> tuple[str, ...]:
    jobs = session.scalars(
        select(SummaryJob)
        .where(SummaryJob.status.in_(ACTIVE_STATUSES))
        .order_by(SummaryJob.created_at, SummaryJob.id)
    ).all()
    for job in jobs:
        _finish(job, "interrupted", INTERRUPTED_MESSAGE)
    session.flush()
    return tuple(job.id for job in jobs)


def execute_summary_job(
    session_factory: sessionmaker[Session],
    settings: Settings,
    job_id: str,
    stop_event: Event | None = None,
) -> None:
    with session_factory.begin() as session:
        job = session.get(SummaryJob, job_id)
        if job is None or job.status != "queued":
            return
        job.status = "running"
        job.stage = "inputs"
        job.progress = 5
        document_id = job.document_id
        try:
            inputs: SummaryInputs = capture_summary_inputs(session, document_id)
        except (SummaryConflictError, SummaryNotFoundError) as exc:
            _finish(job, "failed", str(exc))
            return

    def should_stop() -> bool:
        if stop_event is not None and stop_event.is_set():
            return True
        with session_factory() as session:
            job = session.get(SummaryJob, job_id)
            return job is None or job.status != "running"

    try:
        provider = create_summary_provider(settings)
        _record_stage(session_factory, job_id, "drafting", 20)
        drafts = provider.generate(inputs, should_cancel=should_stop)
        _record_stage(session_factory, job_id, "validating", 70)
        accepted = validate_claims(inputs, drafts)
        with session_factory.begin() as session:
            job = session.get(SummaryJob, job_id)
            # Same transaction: only the running owner may publish.
            if job is None or job.status != "running":
                raise TranslationCancelledError("job no longer running")
            version = persist_summary_version(
                session,
                inputs,
                accepted,
                provider=provider.name,
                model=provider.model_name,
            )
            job.version_id = version.id
            _finish(job, "completed", None)
    except TranslationCancelledError:
        outcome = (
            "interrupted"
            if stop_event is not None and stop_event.is_set()
            else "failed"
        )
        message = INTERRUPTED_MESSAGE if outcome == "interrupted" else None
        _fail(session_factory, job_id, outcome, message)
    except Exception as exc:  # noqa: BLE001 - providers are an external boundary
        logger.exception(
            "Summary generation failed",
            extra={"job_id": job_id, "document_id": document_id},
        )
        _fail(session_factory, job_id, "failed", public_summary_error(exc))


def public_summary_error(exc: Exception) -> str:
    if isinstance(exc, (CliAiError, SummaryValidationError, SummaryConflictError)):
        return str(exc)
    return GENERIC_FAILURE_MESSAGE


def _record_stage(
    session_factory: sessionmaker[Session], job_id: str, stage: str, progress: float
) -> None:
    with session_factory.begin() as session:
        job = session.get(SummaryJob, job_id)
        if job is not None and job.status == "running":
            job.stage = stage
            job.progress = progress


def _fail(
    session_factory: sessionmaker[Session],
    job_id: str,
    outcome: str,
    message: str | None,
) -> None:
    with session_factory.begin() as session:
        job = session.get(SummaryJob, job_id)
        if job is None or job.status in TERMINAL_STATUSES:
            return
        _finish(job, outcome, message)


def _finish(job: SummaryJob, status: str, message: str | None) -> None:
    job.status = status
    job.stage = status
    job.progress = 100
    job.error_message = message


class SummaryJobExecutor:
    def __init__(self, session_factory: sessionmaker[Session], settings: Settings):
        self._session_factory = session_factory
        self._settings = settings
        self._pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="glyph-summary"
        )
        self._guard = Lock()
        self._accepting = True
        self._stop_event = Event()
        self._futures: set[Future[None]] = set()

    def submit(self, job_id: str) -> Future[None]:
        with self._guard:
            if not self._accepting:
                raise SummaryExecutorClosedError(
                    "Summary executor is not accepting new work"
                )
            future = self._pool.submit(
                execute_summary_job,
                self._session_factory,
                self._settings,
                job_id,
                self._stop_event,
            )
            self._futures.add(future)
        future.add_done_callback(self._discard_future)
        return future

    def wait_for_idle(self, timeout_seconds: float = 30) -> bool:
        with self._guard:
            futures = tuple(self._futures)
        _, pending = wait(futures, timeout=timeout_seconds)
        return not pending

    def shutdown(self, timeout_seconds: float = 10) -> None:
        with self._guard:
            self._accepting = False
            futures = tuple(self._futures)
        self._stop_event.set()
        _, pending = wait(futures, timeout=timeout_seconds)
        self._pool.shutdown(wait=not pending, cancel_futures=True)
        if pending:
            logger.warning(
                "Summary executor shutdown timed out",
                extra={"pending_jobs": len(pending)},
            )

    def _discard_future(self, future: Future[None]) -> None:
        with self._guard:
            self._futures.discard(future)
