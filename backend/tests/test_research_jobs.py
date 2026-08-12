from collections.abc import Iterator
from concurrent.futures import Future
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from glyph.main import create_app
from glyph.models import Base, Block, Document, ResearchMapJob, ResearchMapVersion
from glyph.research_ai import MockResearchMapProvider
from glyph.research_jobs import (
    ResearchJobConflictError,
    ResearchJobExecutorClosedError,
    ResearchMapJobExecutor,
    enqueue_research_map_job,
    execute_research_map_job,
    recover_interrupted_jobs,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "empirical_asset_pricing.txt"
SOURCE_HASH = "a" * 64


@pytest.fixture
def job_database(tmp_path) -> Iterator[tuple[sessionmaker[Session], str]]:
    database_path = tmp_path / "research-jobs.sqlite3"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    document = Document(
        id="paper-1",
        title="Signal Persistence and Expected Returns",
        source_path="/books/synthetic-paper.txt",
        content_hash=SOURCE_HASH,
        processed_content_hash=SOURCE_HASH,
        file_type="txt",
        status="completed",
    )
    second_document = Document(
        id="paper-2",
        title="Second paper",
        source_path="/books/second-paper.txt",
        content_hash="b" * 64,
        processed_content_hash="b" * 64,
        file_type="txt",
        status="completed",
    )
    paragraphs = [
        line.strip()
        for line in FIXTURE_PATH.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    with factory.begin() as session:
        session.add_all([document, second_document])
        session.add_all(
            Block(
                id=f"block-{index}",
                document_id=document.id,
                source_content_hash=SOURCE_HASH,
                order_index=index,
                page_number=1 + index // 4,
                block_type="paragraph",
                source_text=paragraph,
                translated_text=f"繁中：{paragraph}",
            )
            for index, paragraph in enumerate(paragraphs)
        )
    try:
        yield factory, document.id
    finally:
        engine.dispose()


def test_enqueue_returns_persistent_queued_job_and_rejects_duplicate(job_database):
    factory, document_id = job_database
    with factory.begin() as session:
        job = enqueue_research_map_job(session, document_id)

    assert job.status == "queued"
    assert job.stage == "queued"
    assert job.progress == 0
    assert job.attempt_count == 0
    assert job.lease_token is None

    with (
        factory.begin() as session,
        pytest.raises(ResearchJobConflictError, match="already queued or running"),
    ):
        enqueue_research_map_job(session, document_id)


def test_job_runner_commits_each_stage_and_completes_with_map(job_database):
    factory, document_id = job_database
    with factory.begin() as session:
        queued = enqueue_research_map_job(session, document_id)
    observed_stages: list[tuple[str, float]] = []

    execute_research_map_job(
        factory,
        queued.id,
        MockResearchMapProvider,
        stage_observer=lambda stage, progress: observed_stages.append(
            (stage, progress)
        ),
    )

    assert [stage for stage, _ in observed_stages] == [
        "evidence",
        "validation",
        "synthesis",
        "audit",
        "persistence",
    ]
    with factory() as session:
        completed = session.get(ResearchMapJob, queued.id)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.stage == "completed"
        assert completed.progress == 100
        assert completed.attempt_count == 1
        assert completed.lease_token is None
        assert completed.map_version_id is not None
        version = session.get(ResearchMapVersion, completed.map_version_id)
        assert version is not None
        assert version.is_active is True


def test_provider_failure_is_sanitized_and_keeps_previous_active_map(job_database):
    factory, document_id = job_database
    with factory.begin() as session:
        first_job = enqueue_research_map_job(session, document_id)
    execute_research_map_job(factory, first_job.id, MockResearchMapProvider)
    with factory() as session:
        active_before = session.scalar(
            select(ResearchMapVersion).where(ResearchMapVersion.is_active.is_(True))
        )
        assert active_before is not None
        active_before_id = active_before.id

    class FailingProvider(MockResearchMapProvider):
        def extract_candidates(self, blocks):
            raise RuntimeError("secret provider traceback /Users/private/key")

    with factory.begin() as session:
        failed_job = enqueue_research_map_job(session, document_id)
    execute_research_map_job(factory, failed_job.id, FailingProvider)

    with factory() as session:
        failed = session.get(ResearchMapJob, failed_job.id)
        active_after = session.scalar(
            select(ResearchMapVersion).where(ResearchMapVersion.is_active.is_(True))
        )
        assert failed is not None
        assert failed.status == "failed"
        assert failed.stage == "failed"
        assert failed.progress == 100
        assert failed.lease_token is None
        assert failed.error_message == (
            "Research Map generation failed. Check the server logs for details."
        )
        assert active_after is not None
        assert active_after.id == active_before_id


def test_restart_requeues_once_then_fails_at_attempt_limit(job_database):
    factory, document_id = job_database
    with factory.begin() as session:
        session.add_all(
            [
                ResearchMapJob(
                    id="interrupted-once",
                    document_id=document_id,
                    status="running",
                    stage="synthesis",
                    progress=55,
                    attempt_count=1,
                    lease_token="old-lease",
                ),
                ResearchMapJob(
                    id="interrupted-twice",
                    document_id="paper-2",
                    status="running",
                    stage="audit",
                    progress=70,
                    attempt_count=2,
                    lease_token="old-lease-2",
                ),
            ]
        )

    with factory.begin() as session:
        queued_ids = recover_interrupted_jobs(session, max_attempts=2)

    assert queued_ids == ("interrupted-once",)
    with factory() as session:
        requeued = session.get(ResearchMapJob, "interrupted-once")
        failed = session.get(ResearchMapJob, "interrupted-twice")
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
            "Research Map generation was interrupted too many times."
        )


def test_single_worker_executor_uses_events_and_rejects_after_shutdown(job_database):
    factory, document_id = job_database
    provider_started = Event()
    release_provider = Event()

    class BlockingProvider(MockResearchMapProvider):
        def extract_candidates(self, blocks):
            provider_started.set()
            assert release_provider.wait(timeout=5)
            return super().extract_candidates(blocks)

    with factory.begin() as session:
        queued = enqueue_research_map_job(session, document_id)
    executor = ResearchMapJobExecutor(factory, BlockingProvider)
    future: Future[None] = executor.submit(queued.id)
    assert provider_started.wait(timeout=5)
    try:
        with factory() as session:
            running = session.get(ResearchMapJob, queued.id)
            assert running is not None
            assert running.status == "running"
            assert running.attempt_count == 1
            assert running.lease_token is not None
    finally:
        release_provider.set()
    future.result(timeout=5)
    executor.shutdown()

    with pytest.raises(ResearchJobExecutorClosedError, match="not accepting"):
        executor.submit(queued.id)


def test_app_startup_recovers_and_submits_interrupted_jobs(tmp_path, monkeypatch):
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book_dir))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    provider_started = Event()
    release_provider = Event()

    class BlockingProvider(MockResearchMapProvider):
        def extract_candidates(self, blocks):
            provider_started.set()
            assert release_provider.wait(timeout=5)
            return super().extract_candidates(blocks)

    monkeypatch.setattr(
        "glyph.main.create_research_map_provider",
        lambda settings: BlockingProvider(),
    )
    app = create_app()
    with app.state.session_factory.begin() as session:
        document = Document(
            id="recover-paper",
            title="Recover paper",
            source_path="/books/recover-paper.txt",
            content_hash=SOURCE_HASH,
            processed_content_hash=SOURCE_HASH,
            file_type="txt",
            status="completed",
        )
        session.add_all(
            [
                document,
                Block(
                    id="recover-block",
                    document_id=document.id,
                    source_content_hash=SOURCE_HASH,
                    order_index=0,
                    page_number=1,
                    block_type="paragraph",
                    source_text="Research Question: Can startup recovery finish?",
                    translated_text="研究問題：啟動復原能否完成？",
                ),
                ResearchMapJob(
                    id="recover-job",
                    document_id=document.id,
                    status="running",
                    stage="validation",
                    progress=35,
                    attempt_count=1,
                    lease_token="interrupted-lease",
                ),
            ]
        )

    try:
        with TestClient(app):
            assert provider_started.wait(timeout=5)
            with app.state.session_factory() as session:
                recovered = session.get(ResearchMapJob, "recover-job")
                assert recovered is not None
                assert recovered.status == "running"
                assert recovered.attempt_count == 2
                assert recovered.lease_token != "interrupted-lease"
            release_provider.set()
    finally:
        release_provider.set()

    with app.state.session_factory() as session:
        completed = session.get(ResearchMapJob, "recover-job")
        assert completed is not None
        assert completed.status == "completed"
        assert completed.map_version_id is not None
