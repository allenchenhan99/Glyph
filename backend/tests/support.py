"""Shared helpers for API tests that drive background document processing."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from glyph.main import create_app

TERMINAL_STATUSES = {"completed", "failed", "cancelled", "interrupted"}


def make_book_app(tmp_path, monkeypatch, text: str = "# Title\n\nSome prose.", **env):
    book = tmp_path / "book"
    book.mkdir(parents=True, exist_ok=True)
    (book / "sample.pdf").write_text(text)
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_OCR_MODE", "mock")
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    monkeypatch.delenv("GLYPH_TRANSLATION_PROVIDER", raising=False)
    monkeypatch.delenv("ORCAROUTER_API_KEY", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return create_app()


def wait_for_job(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in TERMINAL_STATUSES:
            return job
        if time.monotonic() > deadline:
            raise AssertionError(f"job did not finish in time: {job}")
        time.sleep(0.02)


def process_and_wait(client: TestClient, document_id: str) -> dict:
    response = client.post(f"/api/documents/{document_id}/process")
    assert response.status_code == 202, response.text
    return wait_for_job(client, response.json()["id"])
