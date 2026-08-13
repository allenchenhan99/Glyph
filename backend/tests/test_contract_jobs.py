from __future__ import annotations

import hashlib
from collections.abc import Iterator
from concurrent.futures import Future
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from glyph.contract_ai import MockImplementationContractProvider
from glyph.contract_jobs import (
    ContractJobConflictError,
    ContractJobExecutorClosedError,
    ImplementationContractJobExecutor,
    enqueue_implementation_contract_job,
    execute_implementation_contract_job,
    recover_interrupted_contract_jobs,
)
from glyph.main import create_app
from glyph.models import (
    Base,
    Block,
    Document,
    ImplementationContractJob,
    ImplementationContractVersion,
    ResearchEvidence,
    ResearchMapVersion,
    ResearchNode,
)
from glyph.research_evidence import exact_quote_hash

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "contracts" / "monthly_accounting_signal.txt"
)


def _add_contract_inputs(
    session: Session,
    *,
    document_id: str,
    map_id: str,
    source_path: str,
) -> tuple[Document, ResearchMapVersion]:
    source_text = FIXTURE_PATH.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source_text.encode()).hexdigest()
    document = Document(
        id=document_id,
        title="Monthly accounting signal",
        source_path=source_path,
        content_hash=source_hash,
        processed_content_hash=source_hash,
        file_type="txt",
        status="completed",
    )
    block = Block(
        id=f"block-{document_id}",
        document_id=document_id,
        source_content_hash=source_hash,
        order_index=0,
        page_number=1,
        block_type="text",
        source_text=source_text,
        translated_text=f"繁中：{source_text}",
    )
    map_version = ResearchMapVersion(
        id=map_id,
        document_id=document_id,
        source_content_hash=source_hash,
        schema_version="1",
        provider="mock",
        model_name=None,
        status="complete",
        is_active=True,
    )
    node = ResearchNode(
        id=f"node-{document_id}",
        map_version_id=map_id,
        node_key="author_claim.1",
        node_type="author_claim",
        title="Research claim",
        claim_text="The source states a reproducible signal.",
        explanation="",
        provenance="author_explicit",
        evidence_quality="direct",
        display_order=0,
        node_signature="c" * 64,
    )
    quote = source_text.splitlines()[1]
    quote_start = source_text.index(quote)
    evidence = ResearchEvidence(
        id=f"evidence-{document_id}",
        node_id=node.id,
        block_id=block.id,
        locator_type="text_span",
        quote_text=quote,
        quote_start=quote_start,
        quote_end=quote_start + len(quote),
        source_quote_hash=exact_quote_hash(
            block.id,
            quote_start,
            quote_start + len(quote),
            quote,
        ),
        relation="supports",
        source_label="Research claim",
    )
    session.add_all([document, block, map_version, node, evidence])
    return document, map_version


@pytest.fixture
def job_database(
    tmp_path: Path,
) -> Iterator[tuple[sessionmaker[Session], str, str]]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'contract-jobs.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory.begin() as session:
        document, map_version = _add_contract_inputs(
            session,
            document_id="paper-1",
            map_id="map-1",
            source_path="/books/paper-1.txt",
        )
        session.add(
            Document(
                id="paper-2",
                title="Second paper",
                source_path="/books/paper-2.txt",
                content_hash="b" * 64,
                processed_content_hash="b" * 64,
                file_type="txt",
                status="completed",
            )
        )
    try:
        yield factory, document.id, map_version.id
    finally:
        engine.dispose()


def test_enqueue_persists_selected_map_and_rejects_active_duplicate(job_database):
    factory, document_id, map_id = job_database
    with factory.begin() as session:
        job = enqueue_implementation_contract_job(session, document_id, map_id)

    assert job.status == "queued"
    assert job.stage == "queued"
    assert job.progress == 0
    assert job.attempt_count == 0
    assert job.lease_token is None
    assert job.requested_research_map_version_id == map_id

    with factory() as session:
        persisted = session.get(ImplementationContractJob, job.id)
        assert persisted is not None
        assert persisted.requested_research_map_version_id == map_id

    with (
        factory.begin() as session,
        pytest.raises(ContractJobConflictError, match="already queued or running"),
    ):
        enqueue_implementation_contract_job(session, document_id, map_id)


def test_database_unique_index_closes_concurrent_enqueue_race(job_database):
    factory, document_id, map_id = job_database
    with factory.begin() as session:
        enqueue_implementation_contract_job(session, document_id, map_id)

    with factory.begin() as session:
        session.add(
            ImplementationContractJob(
                id="racing-job",
                document_id=document_id,
                requested_research_map_version_id=map_id,
                status="queued",
                stage="queued",
                progress=0,
                attempt_count=0,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_runner_commits_monotonic_stages_and_links_completed_version(job_database):
    factory, document_id, map_id = job_database
    with factory.begin() as session:
        queued = enqueue_implementation_contract_job(session, document_id, map_id)
    observed: list[tuple[str, float]] = []

    def observe(stage: str, progress: float) -> None:
        with factory() as session:
            persisted = session.get(ImplementationContractJob, queued.id)
            assert persisted is not None
            assert (persisted.stage, persisted.progress) == (stage, progress)
        observed.append((stage, progress))

    execute_implementation_contract_job(
        factory,
        queued.id,
        MockImplementationContractProvider,
        stage_observer=observe,
    )

    assert [stage for stage, _ in observed] == [
        "load_context",
        "extract_requirements",
        "validate_evidence",
        "synthesize_contract",
        "audit_readiness",
        "persist_and_activate",
    ]
    assert [progress for _, progress in observed] == sorted(
        progress for _, progress in observed
    )
    with factory() as session:
        completed = session.get(ImplementationContractJob, queued.id)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.stage == "completed"
        assert completed.progress == 100
        assert completed.attempt_count == 1
        assert completed.lease_token is None
        assert completed.contract_version_id is not None
        version = session.get(
            ImplementationContractVersion, completed.contract_version_id
        )
        assert version is not None
        assert version.is_active is True
        assert version.research_map_version_id == map_id


def test_provider_failure_is_sanitized_and_keeps_previous_active_contract(
    job_database,
):
    factory, document_id, map_id = job_database
    with factory.begin() as session:
        first = enqueue_implementation_contract_job(session, document_id, map_id)
    execute_implementation_contract_job(
        factory, first.id, MockImplementationContractProvider
    )
    with factory() as session:
        active_before = session.scalar(
            select(ImplementationContractVersion).where(
                ImplementationContractVersion.is_active.is_(True)
            )
        )
        assert active_before is not None
        active_before_id = active_before.id

    class FailingProvider(MockImplementationContractProvider):
        def extract_requirements(self, blocks):  # type: ignore[no-untyped-def]
            raise RuntimeError("secret provider traceback /Users/private/key")

    with factory.begin() as session:
        failed_job = enqueue_implementation_contract_job(session, document_id, map_id)
    execute_implementation_contract_job(factory, failed_job.id, FailingProvider)

    with factory() as session:
        failed = session.get(ImplementationContractJob, failed_job.id)
        active_after = session.scalar(
            select(ImplementationContractVersion).where(
                ImplementationContractVersion.is_active.is_(True)
            )
        )
        assert failed is not None
        assert failed.status == "failed"
        assert failed.stage == "failed"
        assert failed.progress == 100
        assert failed.lease_token is None
        assert failed.error_message == (
            "Implementation Contract generation failed. "
            "Check the server logs for details."
        )
        assert active_after is not None
        assert active_after.id == active_before_id


def test_restart_requeues_once_then_fails_at_attempt_limit(job_database):
    factory, document_id, map_id = job_database
    with factory.begin() as session:
        session.add_all(
            [
                ImplementationContractJob(
                    id="interrupted-once",
                    document_id=document_id,
                    requested_research_map_version_id=map_id,
                    status="running",
                    stage="synthesize_contract",
                    progress=60,
                    attempt_count=1,
                    lease_token="old-lease",
                ),
                ImplementationContractJob(
                    id="interrupted-twice",
                    document_id="paper-2",
                    status="running",
                    stage="audit_readiness",
                    progress=75,
                    attempt_count=2,
                    lease_token="old-lease-2",
                ),
            ]
        )

    with factory.begin() as session:
        queued_ids = recover_interrupted_contract_jobs(session, max_attempts=2)

    assert queued_ids == ("interrupted-once",)
    with factory() as session:
        requeued = session.get(ImplementationContractJob, "interrupted-once")
        failed = session.get(ImplementationContractJob, "interrupted-twice")
        assert requeued is not None
        assert requeued.status == "queued"
        assert requeued.stage == "queued"
        assert requeued.progress == 0
        assert requeued.lease_token is None
        assert failed is not None
        assert failed.status == "failed"
        assert failed.stage == "failed"
        assert failed.progress == 100
        assert failed.lease_token is None
        assert failed.error_message == (
            "Implementation Contract generation was interrupted too many times."
        )


def test_single_worker_executor_uses_events_and_rejects_after_shutdown(job_database):
    factory, document_id, map_id = job_database
    provider_started = Event()
    release_provider = Event()

    class BlockingProvider(MockImplementationContractProvider):
        def extract_requirements(self, blocks):  # type: ignore[no-untyped-def]
            provider_started.set()
            assert release_provider.wait(timeout=5)
            return super().extract_requirements(blocks)

    with factory.begin() as session:
        queued = enqueue_implementation_contract_job(session, document_id, map_id)
    executor = ImplementationContractJobExecutor(factory, BlockingProvider)
    future: Future[None] = executor.submit(queued.id)
    assert provider_started.wait(timeout=5)
    try:
        with factory() as session:
            running = session.get(ImplementationContractJob, queued.id)
            assert running is not None
            assert running.status == "running"
            assert running.attempt_count == 1
            assert running.lease_token is not None
    finally:
        release_provider.set()
    future.result(timeout=5)
    executor.shutdown()

    with pytest.raises(ContractJobExecutorClosedError, match="not accepting"):
        executor.submit(queued.id)


def test_app_startup_recovers_and_submits_contract_jobs(tmp_path, monkeypatch):
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book_dir))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    provider_started = Event()
    release_provider = Event()

    class BlockingProvider(MockImplementationContractProvider):
        def extract_requirements(self, blocks):  # type: ignore[no-untyped-def]
            provider_started.set()
            assert release_provider.wait(timeout=5)
            return super().extract_requirements(blocks)

    monkeypatch.setattr(
        "glyph.main.create_implementation_contract_provider",
        lambda settings: BlockingProvider(),
    )
    app = create_app()
    with app.state.session_factory.begin() as session:
        document, map_version = _add_contract_inputs(
            session,
            document_id="recover-paper",
            map_id="recover-map",
            source_path="/books/recover-paper.txt",
        )
        session.add(
            ImplementationContractJob(
                id="recover-contract-job",
                document_id=document.id,
                requested_research_map_version_id=map_version.id,
                status="running",
                stage="validate_evidence",
                progress=40,
                attempt_count=1,
                lease_token="interrupted-lease",
            )
        )

    try:
        with TestClient(app):
            assert app.state.contract_job_executor is not (
                app.state.research_job_executor
            )
            assert provider_started.wait(timeout=5)
            with app.state.session_factory() as session:
                recovered = session.get(
                    ImplementationContractJob, "recover-contract-job"
                )
                assert recovered is not None
                assert recovered.status == "running"
                assert recovered.attempt_count == 2
                assert recovered.lease_token != "interrupted-lease"
            release_provider.set()
    finally:
        release_provider.set()

    with app.state.session_factory() as session:
        completed = session.get(ImplementationContractJob, "recover-contract-job")
        assert completed is not None
        assert completed.status == "completed"
        assert completed.contract_version_id is not None
