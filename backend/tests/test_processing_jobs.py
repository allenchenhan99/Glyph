from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from support import make_book_app, process_and_wait, wait_for_job

from glyph.ai import MockAiAdapter
from glyph.models import Block, Document, ProcessingJob
from glyph.orcarouter import TransportResponse

TEXT = "# Introduction\n\nOne.\n\nTwo.\n\nThree.\n\nFour.\n\nFive.\n\nSix."


def document_id_of(client: TestClient) -> str:
    return client.get("/api/documents").json()[0]["id"]


def reader_texts(client: TestClient, document_id: str) -> list[str]:
    reader = client.get(f"/api/documents/{document_id}/reader").json()
    return [block["translated_text"] for block in reader["blocks"]]


class GatedAdapter(MockAiAdapter):
    """Mock translation that pauses between batches so tests can observe progress."""

    def __init__(
        self, gate: threading.Event, started: threading.Event, batch_size: int = 2
    ):
        self.gate = gate
        self.started = started
        self.batch_size = batch_size
        self.batches_started = 0

    def parse_translate_and_summarize(
        self, page_text, *, progress=None, should_cancel=None
    ):
        document = self.prepare_document(page_text)
        total = len(document.blocks)
        if progress is not None:
            progress(0, total)
        translated = []
        for start in range(0, total, self.batch_size):
            if should_cancel is not None and should_cancel():
                from glyph.cli_ai import TranslationCancelledError

                raise TranslationCancelledError("cancelled")
            self.batches_started += 1
            self.started.set()
            assert self.gate.wait(timeout=10)
            self.gate.clear()
            batch = document.blocks[start : start + self.batch_size]
            translated.extend(batch)
            if progress is not None:
                progress(len(translated), total)
        return document.__class__(
            blocks=translated, sections=document.sections, summary=document.summary
        )


def test_process_returns_202_promptly_and_job_completes_in_background(
    tmp_path, monkeypatch
):
    app = make_book_app(tmp_path, monkeypatch, TEXT)
    gate, started = threading.Event(), threading.Event()
    adapter = GatedAdapter(gate, started, batch_size=3)
    monkeypatch.setattr(
        "glyph.processing_jobs.create_ai_adapter", lambda *a, **k: adapter
    )
    client = TestClient(app)
    document_id = document_id_of(client)

    response = client.post(f"/api/documents/{document_id}/process")
    assert response.status_code == 202
    job = response.json()
    assert job["status"] in {"queued", "running"}
    assert job["provider"] == "mock"
    assert job["model"] == ""
    assert job["cancel_requested"] is False
    assert job["completed_blocks"] is None
    assert set(job) >= {
        "id",
        "document_id",
        "status",
        "stage",
        "progress",
        "error_message",
    }
    assert client.get("/api/documents").json()[0]["status"] == "processing"

    assert started.wait(timeout=10)
    started.clear()
    running = client.get(f"/api/jobs/{job['id']}").json()
    assert running["status"] == "running"
    assert running["stage"] == "translate"
    assert (running["completed_blocks"], running["total_blocks"]) == (0, 7)
    gate.set()  # batch 1 completes; batch 2 signals once its progress is recorded
    assert started.wait(timeout=10)
    started.clear()
    midway = client.get(f"/api/jobs/{job['id']}").json()
    assert midway["completed_blocks"] == 3
    assert 0 < midway["progress"] < 100
    gate.set()
    assert started.wait(timeout=10)
    started.clear()
    gate.set()

    finished = wait_for_job(client, job["id"])
    assert finished["status"] == "completed"
    assert finished["stage"] == "completed"
    assert finished["progress"] == 100
    assert (finished["completed_blocks"], finished["total_blocks"]) == (7, 7)
    assert client.get("/api/documents").json()[0]["status"] == "completed"
    assert len(reader_texts(client, document_id)) == 7

    latest = client.get("/api/jobs").json()
    assert [item["id"] for item in latest] == [job["id"]]


def test_jobs_endpoint_lists_latest_job_per_document_including_terminal(
    tmp_path, monkeypatch
):
    app = make_book_app(tmp_path, monkeypatch, TEXT)
    (tmp_path / "book" / "second.pdf").write_text("# Second\n\nText.")
    client = TestClient(app)
    ids = [d["id"] for d in client.get("/api/documents").json()]
    first_old = process_and_wait(client, ids[0])
    first_new = process_and_wait(client, ids[0])
    second = process_and_wait(client, ids[1])
    listed = client.get("/api/jobs").json()
    assert {item["id"] for item in listed} == {first_new["id"], second["id"]}
    assert first_old["id"] not in {item["id"] for item in listed}
    assert all(item["status"] == "completed" for item in listed)


def test_only_one_active_job_per_document_is_allowed(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch, TEXT)
    monkeypatch.setattr(
        app.state.processing_job_executor, "submit", lambda *a, **k: None
    )
    client = TestClient(app)
    document_id = document_id_of(client)
    first = client.post(f"/api/documents/{document_id}/process")
    assert first.status_code == 202
    second = client.post(f"/api/documents/{document_id}/process")
    assert second.status_code == 409
    assert "already" in second.json()["detail"]
    with app.state.session_factory() as session:
        session.add(
            ProcessingJob(
                id="duplicate",
                document_id=document_id,
                status="running",
                stage="ocr",
                progress=0,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_cancel_running_job_is_cooperative_and_preserves_reader(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch, TEXT)
    client = TestClient(app)
    document_id = document_id_of(client)
    assert process_and_wait(client, document_id)["status"] == "completed"
    before = reader_texts(client, document_id)

    gate, started = threading.Event(), threading.Event()
    adapter = GatedAdapter(gate, started, batch_size=2)
    monkeypatch.setattr(
        "glyph.processing_jobs.create_ai_adapter", lambda *a, **k: adapter
    )
    job = client.post(f"/api/documents/{document_id}/process").json()
    assert started.wait(timeout=10)
    cancel = client.post(f"/api/jobs/{job['id']}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "running"
    assert cancel.json()["cancel_requested"] is True
    gate.set()  # the in-flight batch finishes first

    finished = wait_for_job(client, job["id"])
    assert finished["status"] == "cancelled"
    assert finished["stage"] == "cancelled"
    assert finished["cancel_requested"] is True
    assert adapter.batches_started == 1
    assert reader_texts(client, document_id) == before
    assert client.get("/api/documents").json()[0]["status"] == "completed"
    assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 409
    assert client.post("/api/jobs/unknown/cancel").status_code == 404


def test_cancel_queued_job_is_immediate(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch, TEXT)
    monkeypatch.setattr(
        app.state.processing_job_executor, "submit", lambda *a, **k: None
    )
    client = TestClient(app)
    document_id = document_id_of(client)
    job = client.post(f"/api/documents/{document_id}/process").json()
    assert job["status"] == "queued"
    cancelled = client.post(f"/api/jobs/{job['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert client.get("/api/documents").json()[0]["status"] == "discovered"
    assert client.post(f"/api/documents/{document_id}/process").status_code == 202


def test_source_change_during_processing_does_not_publish_wrong_reader(
    tmp_path, monkeypatch
):
    app = make_book_app(tmp_path, monkeypatch, TEXT)
    client = TestClient(app)
    document_id = document_id_of(client)
    assert process_and_wait(client, document_id)["status"] == "completed"
    before = reader_texts(client, document_id)
    source = tmp_path / "book" / "sample.pdf"

    class MutatingOcr:
        def extract_pages(self, path):
            from glyph.ocr import OcrPage

            source.write_text("# Replaced\n\nDifferent content.")
            return [OcrPage(page_number=1, text=TEXT)]

    monkeypatch.setattr(
        "glyph.processing_jobs.create_ocr_adapter", lambda *a, **k: MutatingOcr()
    )
    job = process_and_wait(client, document_id)
    assert job["status"] == "failed"
    assert "changed" in job["error_message"].lower()
    assert reader_texts(client, document_id) == before
    documents = client.get("/api/documents").json()
    assert documents[0]["status"] == "stale"


def test_restart_marks_unfinished_jobs_interrupted_without_replaying(
    tmp_path, monkeypatch
):
    app = make_book_app(tmp_path, monkeypatch, TEXT)
    monkeypatch.setattr(
        app.state.processing_job_executor, "submit", lambda *a, **k: None
    )
    client = TestClient(app)
    document_id = document_id_of(client)
    queued = client.post(f"/api/documents/{document_id}/process").json()
    with app.state.session_factory.begin() as session:
        job = session.get(ProcessingJob, queued["id"])
        job.status = "running"
        job.stage = "translate"

    submitted: list[str] = []
    import glyph.processing_jobs as module

    monkeypatch.setattr(
        module.ProcessingJobExecutor,
        "submit",
        lambda self, job_id, *a, **k: submitted.append(job_id),
    )
    restarted = make_book_app(tmp_path, monkeypatch, TEXT)
    client2 = TestClient(restarted)
    listed = client2.get("/api/jobs").json()
    assert [item["status"] for item in listed] == ["interrupted"]
    assert "retry" in listed[0]["error_message"].lower()
    assert submitted == []
    assert client2.get("/api/documents").json()[0]["status"] == "discovered"
    assert client2.get(f"/api/jobs/{queued['id']}").json()["stage"] == "interrupted"


def test_retry_after_interruption_reuses_cache_and_never_persists_keys(
    tmp_path, monkeypatch
):
    import glyph.orcarouter as orca

    calls: list[bytes] = []

    def transport(
        body: bytes, headers: dict[str, str], timeout: float
    ) -> TransportResponse:
        calls.append(body)
        blocks = json.loads(json.loads(body)["messages"][-1]["content"])["blocks"]
        items = [
            {"id": b["id"], "translated_text": "譯", "formula_latex": None}
            for b in blocks
        ]
        content = json.dumps({"items": items})
        return TransportResponse(
            200,
            {},
            json.dumps(
                {
                    "choices": [
                        {"message": {"content": content}, "finish_reason": "stop"}
                    ]
                }
            ).encode(),
        )

    monkeypatch.setattr(orca, "https_transport", transport)
    app = make_book_app(tmp_path, monkeypatch, "# Title\n\nOne.\n\nTwo.")
    client = TestClient(app)
    document_id = document_id_of(client)
    settings = {
        "provider": "orcarouter",
        "model": "test/model",
        "api_key": "very-secret-key",
    }
    assert client.post("/api/settings/ai", json=settings).status_code == 200
    first = process_and_wait(client, document_id)
    assert first["status"] == "completed"
    assert first["provider"] == "orcarouter"
    assert first["model"] == "test/model"
    assert len(calls) == 1
    database = (tmp_path / "data" / "glyph.sqlite3").read_bytes()
    assert b"very-secret-key" not in database
    assert b"very-secret-key" not in b"".join(
        p.read_bytes() for p in (tmp_path / "data").rglob("*.json")
    )

    # Simulate a restart with the job still running: it must not be replayed.
    with app.state.session_factory.begin() as session:
        job = session.get(ProcessingJob, first["id"])
        job.status = "running"
    restarted = make_book_app(
        tmp_path,
        monkeypatch,
        "# Title\n\nOne.\n\nTwo.",
        GLYPH_TRANSLATION_PROVIDER="orcarouter",
    )
    client2 = TestClient(restarted)
    assert client2.get(f"/api/jobs/{first['id']}").json()["status"] == "interrupted"
    assert len(calls) == 1
    # No key survived the restart, so the retry is blocked until it is re-entered.
    assert client2.post(f"/api/documents/{document_id}/process").status_code == 422

    # Retry with re-entered session settings reuses the validated cache.
    assert client2.post("/api/settings/ai", json=settings).status_code == 200
    retried = process_and_wait(client2, document_id)
    assert retried["status"] == "completed"
    assert retried["id"] != first["id"]
    assert len(calls) == 1


def test_failed_run_preserves_snapshot_and_reports_public_error(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch, TEXT)
    client = TestClient(app)
    document_id = document_id_of(client)
    assert process_and_wait(client, document_id)["status"] == "completed"
    before = reader_texts(client, document_id)

    def fail_after_flush(session, document_id, parsed_sections):
        session.flush()
        raise RuntimeError("persistence unavailable")

    monkeypatch.setattr("glyph.pipeline.persist_sections", fail_after_flush)
    failed = process_and_wait(client, document_id)
    assert failed["status"] == "failed"
    assert (
        failed["error_message"]
        == "Processing failed. Check the server logs for details."
    )
    assert reader_texts(client, document_id) == before
    with app.state.session_factory() as session:
        document = session.get(Document, document_id)
        assert document.status == "completed"
        blocks = session.scalars(
            select(Block).where(Block.document_id == document_id)
        ).all()
        assert len(blocks) == len(before)


def test_shutdown_marks_running_job_interrupted(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch, TEXT)
    gate, started = threading.Event(), threading.Event()
    adapter = GatedAdapter(gate, started, batch_size=2)
    monkeypatch.setattr(
        "glyph.processing_jobs.create_ai_adapter", lambda *a, **k: adapter
    )
    client = TestClient(app)
    document_id = document_id_of(client)
    job = client.post(f"/api/documents/{document_id}/process").json()
    assert started.wait(timeout=10)
    app.state.processing_job_executor.shutdown(timeout_seconds=0.2)
    gate.set()
    finished = wait_for_job(client, job["id"])
    assert finished["status"] == "interrupted"
    assert adapter.batches_started == 1
    assert client.get("/api/documents").json()[0]["status"] == "discovered"


def test_stale_worker_cannot_publish_over_an_interrupted_job(tmp_path, monkeypatch):
    from glyph.processing_jobs import mark_interrupted_jobs

    app = make_book_app(tmp_path, monkeypatch, TEXT)
    gate, started = threading.Event(), threading.Event()
    adapter = GatedAdapter(gate, started, batch_size=7)
    monkeypatch.setattr(
        "glyph.processing_jobs.create_ai_adapter", lambda *a, **k: adapter
    )
    client = TestClient(app)
    document_id = document_id_of(client)
    old = client.post(f"/api/documents/{document_id}/process").json()
    assert started.wait(timeout=10)

    # "Restart": the running job is marked interrupted while its provider call is
    # still in flight, and the user enqueues a retry that stays queued.
    with app.state.session_factory.begin() as session:
        assert mark_interrupted_jobs(session, app.state.settings) == (old["id"],)
    monkeypatch.setattr(
        app.state.processing_job_executor, "submit", lambda *a, **k: None
    )
    retry = client.post(f"/api/documents/{document_id}/process").json()
    assert retry["status"] == "queued"

    gate.set()
    assert app.state.processing_job_executor.wait_for_idle(timeout_seconds=10)
    assert client.get(f"/api/jobs/{old['id']}").json()["status"] == "interrupted"
    assert client.get(f"/api/jobs/{retry['id']}").json()["status"] == "queued"
    assert client.get(f"/api/documents/{document_id}/reader").json()["blocks"] == []
    with app.state.session_factory() as session:
        document = session.get(Document, document_id)
        assert document.processed_content_hash is None


def test_executor_rejection_does_not_leave_an_orphan_queued_job(tmp_path, monkeypatch):
    from glyph.processing_jobs import ProcessingExecutorClosedError

    app = make_book_app(tmp_path, monkeypatch, TEXT)

    def rejecting_submit(*args, **kwargs):
        raise ProcessingExecutorClosedError("closed")

    monkeypatch.setattr(app.state.processing_job_executor, "submit", rejecting_submit)
    client = TestClient(app)
    document_id = document_id_of(client)
    response = client.post(f"/api/documents/{document_id}/process")
    assert response.status_code == 503
    assert "retry" in response.json()["detail"].lower()
    jobs = client.get("/api/jobs").json()
    assert [job["status"] for job in jobs] == ["interrupted"]
    assert client.get("/api/documents").json()[0]["status"] == "discovered"
    with app.state.session_factory() as session:
        active = session.scalars(
            select(ProcessingJob).where(ProcessingJob.status.in_(("queued", "running")))
        ).all()
        assert active == []


def test_latest_jobs_always_include_active_work_beyond_the_history_bound(
    tmp_path, monkeypatch
):
    from glyph.processing_jobs import list_latest_jobs

    app = make_book_app(tmp_path, monkeypatch, TEXT)
    with app.state.session_factory.begin() as session:
        for index in range(3):
            session.add(
                Document(
                    id=f"doc-{index}",
                    title=f"doc-{index}.pdf",
                    source_path=str(tmp_path / f"doc-{index}.pdf"),
                    content_hash="a" * 64,
                    file_type="pdf",
                    status="discovered",
                )
            )
        session.flush()
        # Oldest document has queued work; newer ones only have finished history.
        session.add(
            ProcessingJob(
                id="old-queued",
                document_id="doc-0",
                status="queued",
                stage="queued",
                progress=0,
            )
        )
        session.flush()
        for index in (1, 2):
            session.add(
                ProcessingJob(
                    id=f"done-{index}",
                    document_id=f"doc-{index}",
                    status="completed",
                    stage="completed",
                    progress=100,
                )
            )
            session.flush()
    with app.state.session_factory() as session:
        listed = list_latest_jobs(session, limit=1)
    assert {job.id for job in listed} >= {"old-queued"}
    assert all(job.status != "completed" or job.id == "done-2" for job in listed)
