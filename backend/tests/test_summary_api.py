from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient
from sqlalchemy import select
from support import make_book_app, process_and_wait

from glyph.models import SummaryJob, SummaryVersion
from glyph.summary_ai import MockSummaryProvider

TEXT = (
    "# Introduction\n\nAlpha decays quickly after publication.\n\n"
    "Returns concentrate in small stocks.\n\n"
    "# Data\n\nThe sample covers 1990 to 2020.\n\nCRSP monthly returns are used."
)


def ready_app(tmp_path, monkeypatch, text=TEXT, **env):
    app = make_book_app(tmp_path, monkeypatch, text, **env)
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    assert process_and_wait(client, document_id)["status"] == "completed"
    return app, client, document_id


def wait_for_summary(
    client: TestClient, document_id: str, timeout: float = 10.0
) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        state = client.get(f"/api/documents/{document_id}/summaries").json()
        if state["status"] != "generating":
            return state
        assert time.monotonic() < deadline, state
        time.sleep(0.02)


class GatedProvider(MockSummaryProvider):
    def __init__(self, gate: threading.Event, started: threading.Event):
        self.gate, self.started = gate, started

    def generate(self, inputs, *, should_cancel):
        self.started.set()
        assert self.gate.wait(timeout=10)
        return super().generate(inputs, should_cancel=should_cancel)


class FailingProvider(MockSummaryProvider):
    def generate(self, inputs, *, should_cancel):
        raise RuntimeError("provider exploded with secret details")


def test_not_generated_state_reports_provider_without_placeholders(
    tmp_path, monkeypatch
):
    app, client, document_id = ready_app(tmp_path, monkeypatch)
    state = client.get(f"/api/documents/{document_id}/summaries").json()
    assert state == {
        "status": "not_generated",
        "provider": "mock",
        "model": None,
        "version": None,
        "job": None,
    }
    assert client.get("/api/documents/unknown/summaries").status_code == 404


def test_generate_returns_202_quickly_then_available_with_exact_evidence(
    tmp_path, monkeypatch
):
    app, client, document_id = ready_app(tmp_path, monkeypatch)
    gate, started = threading.Event(), threading.Event()
    monkeypatch.setattr(
        "glyph.summary_jobs.create_summary_provider",
        lambda settings: GatedProvider(gate, started),
    )
    response = client.post(f"/api/documents/{document_id}/summaries")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "generating"
    assert body["job"]["status"] in {"queued", "running"}
    assert body["version"] is None
    assert started.wait(timeout=10)
    assert (
        client.get(f"/api/documents/{document_id}/summaries").json()["status"]
        == "generating"
    )
    assert client.post(f"/api/documents/{document_id}/summaries").status_code == 409
    gate.set()
    state = wait_for_summary(client, document_id)
    assert state["status"] == "available"
    assert state["job"]["status"] == "completed"
    assert state["job"]["error_message"] is None
    version = state["version"]
    assert set(version) == {
        "id",
        "source_content_hash",
        "reader_fingerprint",
        "provider",
        "model",
        "created_at",
        "claims",
    }
    assert version["provider"] == "mock"
    reader = client.get(f"/api/documents/{document_id}/reader").json()
    block_text = {
        block["id"]: (block["source_text"], block["page_number"])
        for block in reader["blocks"]
    }
    overview = [c for c in version["claims"] if c["section_path"] is None]
    assert overview and all(
        set(c) == {"id", "section_path", "text", "evidence"} for c in version["claims"]
    )
    for claim in version["claims"]:
        assert claim["evidence"]
        for item in claim["evidence"]:
            text, page = block_text[item["block_id"]]
            assert text[item["quote_start"] : item["quote_end"]] == item["quote_text"]
            assert item["page_number"] == page
    assert {c["section_path"] for c in version["claims"] if c["section_path"]} == {
        s["path"] for s in reader["sections"]
    }


def test_generation_requires_a_current_reader(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch, TEXT)
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    assert client.post(f"/api/documents/{document_id}/summaries").status_code == 409
    assert client.post("/api/documents/unknown/summaries").status_code == 404
    assert process_and_wait(client, document_id)["status"] == "completed"
    (tmp_path / "book" / "sample.pdf").write_text(TEXT + "\n\nChanged on disk.")
    response = client.post(f"/api/documents/{document_id}/summaries")
    assert response.status_code == 409
    assert (
        "stale" in response.json()["detail"].lower()
        or "current" in response.json()["detail"].lower()
    )
    assert client.get("/api/documents").json()[0]["status"] == "stale"


def test_failure_keeps_prior_version_and_reports_safe_error(tmp_path, monkeypatch):
    app, client, document_id = ready_app(tmp_path, monkeypatch)
    assert client.post(f"/api/documents/{document_id}/summaries").status_code == 202
    first = wait_for_summary(client, document_id)
    assert first["status"] == "available"
    monkeypatch.setattr(
        "glyph.summary_jobs.create_summary_provider", lambda settings: FailingProvider()
    )
    assert client.post(f"/api/documents/{document_id}/summaries").status_code == 202
    failed = wait_for_summary(client, document_id)
    assert failed["status"] == "failed"
    assert failed["job"]["status"] == "failed"
    assert "secret" not in failed["job"]["error_message"]
    assert failed["version"]["id"] == first["version"]["id"]
    with app.state.session_factory() as session:
        versions = session.scalars(select(SummaryVersion)).all()
        assert [v.is_active for v in versions] == [True]


def test_reprocessing_marks_summary_stale_but_keeps_quotes(tmp_path, monkeypatch):
    app, client, document_id = ready_app(tmp_path, monkeypatch)
    assert client.post(f"/api/documents/{document_id}/summaries").status_code == 202
    available = wait_for_summary(client, document_id)
    (tmp_path / "book" / "sample.pdf").write_text(
        TEXT + "\n\n# More\n\nExtra paragraph."
    )
    client.get("/api/documents")
    assert process_and_wait(client, document_id)["status"] == "completed"
    stale = wait_for_summary(client, document_id)
    assert stale["status"] == "stale"
    assert stale["version"]["id"] == available["version"]["id"]
    assert stale["version"]["claims"][0]["evidence"][0]["quote_text"]
    assert client.post(f"/api/documents/{document_id}/summaries").status_code == 202
    assert wait_for_summary(client, document_id)["status"] == "available"


def test_restart_marks_unfinished_job_interrupted_without_replay(tmp_path, monkeypatch):
    app, client, document_id = ready_app(tmp_path, monkeypatch)
    monkeypatch.setattr(app.state.summary_job_executor, "submit", lambda *a, **k: None)
    assert client.post(f"/api/documents/{document_id}/summaries").status_code == 202
    generated: list[str] = []
    monkeypatch.setattr(
        "glyph.summary_jobs.create_summary_provider",
        lambda settings: generated.append("called"),
    )
    restarted = make_book_app(tmp_path, monkeypatch, TEXT)
    state = TestClient(restarted).get(f"/api/documents/{document_id}/summaries").json()
    assert state["status"] == "failed"
    assert state["job"]["status"] == "interrupted"
    assert "retry" in state["job"]["error_message"].lower()
    assert generated == []
    assert restarted.state.summary_job_executor.wait_for_idle(timeout_seconds=2)


def test_stale_worker_cannot_publish_over_an_interrupted_job(tmp_path, monkeypatch):
    from glyph.summary_jobs import mark_interrupted_summary_jobs

    app, client, document_id = ready_app(tmp_path, monkeypatch)
    gate, started = threading.Event(), threading.Event()
    monkeypatch.setattr(
        "glyph.summary_jobs.create_summary_provider",
        lambda settings: GatedProvider(gate, started),
    )
    old = client.post(f"/api/documents/{document_id}/summaries").json()["job"]["id"]
    assert started.wait(timeout=10)
    with app.state.session_factory.begin() as session:
        assert mark_interrupted_summary_jobs(session) == (old,)
    gate.set()
    assert app.state.summary_job_executor.wait_for_idle(timeout_seconds=10)
    with app.state.session_factory() as session:
        assert session.get(SummaryJob, old).status == "interrupted"
        assert session.scalars(select(SummaryVersion)).all() == []
    assert (
        client.get(f"/api/documents/{document_id}/summaries").json()["version"] is None
    )


def test_executor_rejection_leaves_no_orphan_queued_job(tmp_path, monkeypatch):
    from glyph.summary_jobs import SummaryExecutorClosedError

    app, client, document_id = ready_app(tmp_path, monkeypatch)

    def rejecting(*args, **kwargs):
        raise SummaryExecutorClosedError("closed")

    monkeypatch.setattr(app.state.summary_job_executor, "submit", rejecting)
    response = client.post(f"/api/documents/{document_id}/summaries")
    assert response.status_code == 503
    state = client.get(f"/api/documents/{document_id}/summaries").json()
    assert state["job"]["status"] == "interrupted"
    assert client.post(f"/api/documents/{document_id}/summaries").status_code == 503
    with app.state.session_factory() as session:
        assert (
            session.scalars(
                select(SummaryJob).where(SummaryJob.status.in_(("queued", "running")))
            ).all()
            == []
        )


def test_source_change_during_generation_is_rejected_at_publication(
    tmp_path, monkeypatch
):
    app, client, document_id = ready_app(tmp_path, monkeypatch)
    gate, started = threading.Event(), threading.Event()
    monkeypatch.setattr(
        "glyph.summary_jobs.create_summary_provider",
        lambda settings: GatedProvider(gate, started),
    )
    assert client.post(f"/api/documents/{document_id}/summaries").status_code == 202
    assert started.wait(timeout=10)
    (tmp_path / "book" / "sample.pdf").write_text(TEXT + "\n\nMutated mid-run.")
    gate.set()
    state = wait_for_summary(client, document_id)
    assert state["status"] == "failed"
    assert "changed" in state["job"]["error_message"].lower()
    assert state["version"] is None
