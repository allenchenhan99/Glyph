"""Durable document-processing jobs with one local worker.

A job row is committed before the request returns. Credentials for the run are
captured in memory when the job is enqueued and travel with the worker task only;
the database stores provider and model names, never keys. Each stage commits in
its own short transaction, and the Reader snapshot is replaced atomically only
after the source identity and cancellation state are re-checked.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path
from threading import Event, Lock
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from glyph.ai import ParsedDocument, create_ai_adapter
from glyph.cli_ai import CliAiError, TranslationCancelledError
from glyph.config import Settings, TranslationSettings, resolve_translation_settings
from glyph.models import Document, ProcessingJob
from glyph.ocr import OcrPage, OcrUnavailableError, create_ocr_adapter
from glyph.orcarouter import OrcaRouterError
from glyph.pipeline import replace_reader_snapshot

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("queued", "running")
TERMINAL_STATUSES = ("completed", "failed", "cancelled", "interrupted")
INTERRUPTED_MESSAGE = (
    "Processing was interrupted by a restart. Retry to continue; validated "
    "translation batches are reused from the local cache."
)
SOURCE_CHANGED_MESSAGE = (
    "The source file changed or disappeared while processing; the Reader was "
    "not replaced. Process the document again to translate the current file."
)
GENERIC_FAILURE_MESSAGE = "Processing failed. Check the server logs for details."
STAGE_PROGRESS = {"queued": 0.0, "ocr": 10.0, "translate": 25.0, "persist": 90.0}
TRANSLATE_SPAN = STAGE_PROGRESS["persist"] - STAGE_PROGRESS["translate"]


class ProcessingConflictError(RuntimeError):
    """Raised when the same document already has queued or running work."""


class ProcessingJobNotFoundError(LookupError):
    """Raised when a job or its document is unavailable."""


class ProcessingJobStateError(RuntimeError):
    """Raised when a transition is not valid for the job's current status."""


class ProcessingExecutorClosedError(RuntimeError):
    """Raised when work is submitted during application shutdown."""


class SourceChangedError(RuntimeError):
    """The file no longer matches the content hash captured at enqueue time."""


def compute_source_hash(source_path: Path) -> str:
    from glyph.documents import compute_hash

    return compute_hash(source_path)


def enqueue_processing_job(
    session: Session, settings: Settings, document: Document
) -> tuple[ProcessingJob, TranslationSettings]:
    """Persist a queued job and return the in-memory translation settings for it."""
    translation = resolve_translation_settings(settings)
    active = session.scalar(
        select(ProcessingJob.id).where(
            ProcessingJob.document_id == document.id,
            ProcessingJob.status.in_(ACTIVE_STATUSES),
        )
    )
    if active is not None:
        raise ProcessingConflictError("Document is already processing")
    job = ProcessingJob(
        id=str(uuid4()),
        document_id=document.id,
        status="queued",
        stage="queued",
        progress=STAGE_PROGRESS["queued"],
        error_message=None,
        completed_blocks=None,
        total_blocks=None,
        cancel_requested=False,
        provider=translation.provider,
        model=translation.model,
        source_content_hash=document.content_hash,
    )
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError as exc:
        raise ProcessingConflictError("Document is already processing") from exc
    document.status = "processing"
    session.flush()
    return job, translation


def request_cancel(session: Session, job_id: str, settings: Settings) -> ProcessingJob:
    job = session.get(ProcessingJob, job_id)
    if job is None:
        raise ProcessingJobNotFoundError("Job not found")
    if job.status == "queued":
        job.cancel_requested = True
        _finish(job, "cancelled", None)
        document = session.get(Document, job.document_id)
        if document is not None:
            restore_document_status(document, settings)
        return job
    if job.status == "running":
        job.cancel_requested = True
        return job
    raise ProcessingJobStateError(f"Job is already {job.status}")


def mark_interrupted_jobs(session: Session, settings: Settings) -> tuple[str, ...]:
    """Called at startup: unfinished work cannot resume without its credentials."""
    jobs = session.scalars(
        select(ProcessingJob)
        .where(ProcessingJob.status.in_(ACTIVE_STATUSES))
        .order_by(ProcessingJob.created_at, ProcessingJob.id)
    ).all()
    for job in jobs:
        _finish(job, "interrupted", INTERRUPTED_MESSAGE)
        document = session.get(Document, job.document_id)
        if document is not None:
            restore_document_status(document, settings)
    session.flush()
    return tuple(job.id for job in jobs)


def list_latest_jobs(session: Session, limit: int = 200) -> list[ProcessingJob]:
    """Latest job per document: every active job, plus bounded terminal history."""
    latest_by_document: dict[str, ProcessingJob] = {}
    active = session.scalars(
        select(ProcessingJob)
        .where(ProcessingJob.status.in_(ACTIVE_STATUSES))
        .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
    )
    for job in active:
        latest_by_document.setdefault(job.document_id, job)
    history = session.scalars(
        select(ProcessingJob)
        .where(ProcessingJob.status.not_in(ACTIVE_STATUSES))
        .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
    )
    terminal_documents = 0
    for job in history:
        if terminal_documents >= limit:
            break
        if job.document_id not in latest_by_document:
            latest_by_document[job.document_id] = job
            terminal_documents += 1
    return list(latest_by_document.values())


def abandon_unsubmitted_job(session: Session, job_id: str, settings: Settings) -> None:
    """The row was committed but no worker will run it: make that visible."""
    job = session.get(ProcessingJob, job_id)
    if job is None or job.status != "queued":
        return
    _finish(
        job,
        "interrupted",
        "The server is shutting down and could not start this job. Retry once "
        "Glyph is running again.",
    )
    document = session.get(Document, job.document_id)
    if document is not None:
        restore_document_status(document, settings)


def restore_document_status(document: Document, settings: Settings) -> None:
    """Leave 'processing' without losing the last readable snapshot state."""
    from glyph.documents import refresh_document_state, unprocessed_status_for_path

    source_path = Path(document.source_path)
    document.status = "discovered"
    refresh_document_state(
        document, source_path, unprocessed_status_for_path(settings, source_path)
    )


def execute_processing_job(
    session_factory: sessionmaker[Session],
    settings: Settings,
    job_id: str,
    translation: TranslationSettings,
    stop_event: Event | None = None,
) -> None:
    context = _claim(session_factory, job_id, settings)
    if context is None:
        return
    document_id, source_path, expected_hash = context

    def should_stop() -> bool:
        if stop_event is not None and stop_event.is_set():
            return True
        with session_factory() as session:
            job = session.get(ProcessingJob, job_id)
            # A job moved out of "running" by a restart or cancel no longer owns
            # the document; the stale worker must stop without publishing.
            return job is None or job.status != "running" or job.cancel_requested

    def record_progress(completed_blocks: int, total_blocks: int) -> None:
        with session_factory.begin() as session:
            job = session.get(ProcessingJob, job_id)
            if job is None or job.status != "running":
                return
            job.completed_blocks = completed_blocks
            job.total_blocks = total_blocks
            if total_blocks:
                job.progress = round(
                    STAGE_PROGRESS["translate"]
                    + TRANSLATE_SPAN * completed_blocks / total_blocks,
                    2,
                )

    try:
        _verify_source(source_path, expected_hash)
        ai_adapter = create_ai_adapter(settings, translation)
        ocr_pages = create_ocr_adapter(settings).extract_pages(source_path)
        if should_stop():
            raise TranslationCancelledError("cancelled after OCR")
        _record_stage(session_factory, job_id, "translate")
        parsed = ai_adapter.parse_translate_and_summarize(
            [(page.page_number, page.text) for page in ocr_pages],
            progress=record_progress,
            should_cancel=should_stop,
        )
        if should_stop():
            raise TranslationCancelledError("cancelled after translation")
        _record_stage(session_factory, job_id, "persist")
        _publish(session_factory, job_id, document_id, expected_hash, ocr_pages, parsed)
    except TranslationCancelledError:
        outcome = (
            "interrupted"
            if stop_event is not None and stop_event.is_set()
            else "cancelled"
        )
        message = INTERRUPTED_MESSAGE if outcome == "interrupted" else None
        _fail(session_factory, settings, job_id, outcome, message)
    except Exception as exc:  # noqa: BLE001 - adapters are an external boundary
        logger.exception(
            "Document processing failed",
            extra={"job_id": job_id, "document_id": document_id},
        )
        _fail(session_factory, settings, job_id, "failed", public_processing_error(exc))


def public_processing_error(exc: Exception) -> str:
    if isinstance(exc, SourceChangedError):
        return SOURCE_CHANGED_MESSAGE
    if isinstance(exc, (CliAiError, OcrUnavailableError, OrcaRouterError)):
        return str(exc)
    return GENERIC_FAILURE_MESSAGE


def _claim(
    session_factory: sessionmaker[Session], job_id: str, settings: Settings
) -> tuple[str, Path, str | None] | None:
    with session_factory.begin() as session:
        job = session.get(ProcessingJob, job_id)
        if job is None or job.status != "queued":
            return None
        document = session.get(Document, job.document_id)
        if document is None:
            _finish(job, "failed", "Document not found")
            return None
        if job.cancel_requested:
            _finish(job, "cancelled", None)
            restore_document_status(document, settings)
            return None
        job.status = "running"
        job.stage = "ocr"
        job.progress = STAGE_PROGRESS["ocr"]
        return document.id, Path(document.source_path), job.source_content_hash


def _verify_source(source_path: Path, expected_hash: str | None) -> None:
    if not source_path.is_file():
        raise SourceChangedError("missing")
    if expected_hash is not None and compute_source_hash(source_path) != expected_hash:
        raise SourceChangedError("changed")


def _record_stage(
    session_factory: sessionmaker[Session], job_id: str, stage: str
) -> None:
    with session_factory.begin() as session:
        job = session.get(ProcessingJob, job_id)
        if job is not None and job.status == "running":
            job.stage = stage
            job.progress = max(job.progress, STAGE_PROGRESS[stage])


def _publish(
    session_factory: sessionmaker[Session],
    job_id: str,
    document_id: str,
    expected_hash: str | None,
    ocr_pages: list[OcrPage],
    parsed: ParsedDocument,
) -> None:
    """Replace the Reader in one transaction, guarded by source identity."""
    source_path: Path | None = None
    with session_factory() as session:
        document = session.get(Document, document_id)
        if document is not None:
            source_path = Path(document.source_path)
    if source_path is not None:
        _verify_source(source_path, expected_hash)
    with session_factory.begin() as session:
        job = session.get(ProcessingJob, job_id)
        document = session.get(Document, document_id)
        if job is None or document is None:
            raise ProcessingJobNotFoundError("Job or document disappeared")
        if job.status != "running" or job.cancel_requested:
            raise TranslationCancelledError("job no longer running before publish")
        if expected_hash is not None and document.content_hash != expected_hash:
            raise SourceChangedError("catalog hash moved")
        replace_reader_snapshot(session, document, ocr_pages, parsed)
        job.completed_blocks = len(parsed.blocks)
        job.total_blocks = len(parsed.blocks)
        _finish(job, "completed", None)


def _fail(
    session_factory: sessionmaker[Session],
    settings: Settings,
    job_id: str,
    outcome: str,
    message: str | None,
) -> None:
    with session_factory.begin() as session:
        job = session.get(ProcessingJob, job_id)
        if job is None or job.status in TERMINAL_STATUSES:
            return
        _finish(job, outcome, message)
        document = session.get(Document, job.document_id)
        if document is not None:
            restore_document_status(document, settings)
            if outcome == "failed" and document.processed_content_hash is None:
                document.status = "failed"


def _finish(job: ProcessingJob, status: str, message: str | None) -> None:
    job.status = status
    job.stage = status
    job.progress = 100
    job.error_message = message


class ProcessingJobExecutor:
    """One worker thread; credentials live only in the submitted task."""

    def __init__(self, session_factory: sessionmaker[Session], settings: Settings):
        self._session_factory = session_factory
        self._settings = settings
        self._pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="glyph-processing"
        )
        self._guard = Lock()
        self._accepting = True
        self._stop_event = Event()
        self._futures: set[Future[None]] = set()

    def submit(self, job_id: str, translation: TranslationSettings) -> Future[None]:
        with self._guard:
            if not self._accepting:
                raise ProcessingExecutorClosedError(
                    "Processing executor is not accepting new work"
                )
            future = self._pool.submit(
                execute_processing_job,
                self._session_factory,
                self._settings,
                job_id,
                translation,
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
                "Processing executor shutdown timed out",
                extra={"pending_jobs": len(pending)},
            )

    def _discard_future(self, future: Future[None]) -> None:
        with self._guard:
            self._futures.discard(future)


ExecutorFactory = Callable[[sessionmaker[Session], Settings], ProcessingJobExecutor]
