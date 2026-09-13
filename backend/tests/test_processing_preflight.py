from __future__ import annotations

import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient
from support import make_book_app, process_and_wait

from glyph.models import ProcessingJob

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def preflight(client: TestClient, document_id: str) -> dict:
    response = client.get(f"/api/documents/{document_id}/preflight")
    assert response.status_code == 200, response.text
    return response.json()


def codes(result: dict) -> set[str]:
    return {issue["code"] for issue in result["issues"]}


def errors(result: dict) -> set[str]:
    return {i["code"] for i in result["issues"] if i["severity"] == "error"}


def test_text_fixture_with_mock_provider_is_ready_with_warnings(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch)
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    result = preflight(client, document_id)
    assert result["ready"] is True
    assert result["source_type"] == "text"
    assert result["provider"] == "mock"
    assert result["page_count"] is None
    assert errors(result) == set()
    assert {"development_fixture", "mock_translation"} <= codes(result)
    assert all(
        i["severity"] in {"error", "warning"} and i["message"] for i in result["issues"]
    )


def test_image_without_ocr_is_blocked_and_process_returns_422(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch)
    (tmp_path / "book" / "scan.png").write_bytes(PNG)
    client = TestClient(app)
    document_id = next(
        d["id"] for d in client.get("/api/documents").json() if d["title"] == "scan.png"
    )
    result = preflight(client, document_id)
    assert result["ready"] is False
    assert result["source_type"] == "image"
    assert result["page_count"] == 1
    assert "ocr_required" in errors(result)
    response = client.post(f"/api/documents/{document_id}/process")
    assert response.status_code == 422
    assert "OCR" in response.json()["detail"]
    with app.state.session_factory() as session:
        assert session.query(ProcessingJob).count() == 0


def test_scanned_pdf_without_text_requires_ocr(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch)
    (tmp_path / "book" / "scan.pdf").write_bytes(b"%PDF-1.4\n\xff\xfe binary")
    monkeypatch.setattr("glyph.processing_preflight.pdf_page_count", lambda *a, **k: 7)
    monkeypatch.setattr(
        "glyph.processing_preflight.pdf_has_text", lambda *a, **k: False
    )
    client = TestClient(app)
    document_id = next(
        d["id"] for d in client.get("/api/documents").json() if d["title"] == "scan.pdf"
    )
    result = preflight(client, document_id)
    assert result["ready"] is False
    assert result["source_type"] == "pdf"
    assert result["page_count"] == 7
    assert "ocr_required" in errors(result)


def test_text_pdf_with_configured_ocr_is_ready_and_unverified(tmp_path, monkeypatch):
    app = make_book_app(
        tmp_path,
        monkeypatch,
        GLYPH_OCR_MODE="unlimited_ocr",
        GLYPH_UNLIMITED_OCR_COMMAND="ocr --input {input} --output_dir {output_dir}",
        GLYPH_AI_MODE="claude_cli",
    )
    (tmp_path / "book" / "paper.pdf").write_bytes(b"%PDF-1.4\n\xff\xfe binary")
    monkeypatch.setattr("glyph.processing_preflight.pdf_page_count", lambda *a, **k: 3)
    monkeypatch.setattr("glyph.processing_preflight.pdf_has_text", lambda *a, **k: True)
    monkeypatch.setattr(
        "glyph.processing_preflight.shutil.which",
        lambda name: (
            f"/usr/bin/{name}" if name in {"claude", "pdftotext", "ocr"} else None
        ),
    )
    client = TestClient(app)
    document_id = next(
        d["id"]
        for d in client.get("/api/documents").json()
        if d["title"] == "paper.pdf"
    )
    result = preflight(client, document_id)
    assert result["ready"] is True
    assert result["provider"] == "claude_cli"
    assert result["page_count"] == 3
    assert errors(result) == set()
    unverified = next(i for i in result["issues"] if i["code"] == "provider_unverified")
    assert (
        "not verified" in unverified["message"]
        or "cannot verify" in unverified["message"]
    )


def test_unlimited_ocr_without_configuration_is_blocked(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch, GLYPH_OCR_MODE="unlimited_ocr")
    (tmp_path / "book" / "scan.png").write_bytes(PNG)
    client = TestClient(app)
    document_id = next(
        d["id"] for d in client.get("/api/documents").json() if d["title"] == "scan.png"
    )
    assert "ocr_unconfigured" in errors(preflight(client, document_id))


def test_missing_cli_and_orcarouter_settings_are_blockers(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch, GLYPH_AI_MODE="codex_cli")
    monkeypatch.setattr("glyph.processing_preflight.shutil.which", lambda name: None)
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    result = preflight(client, document_id)
    assert "provider_cli_missing" in errors(result)
    assert "codex" in next(
        i["message"] for i in result["issues"] if i["code"] == "provider_cli_missing"
    )

    client.post(
        "/api/settings/ai",
        json={"provider": "orcarouter", "model": "m", "api_key": "k"},
    )
    result = preflight(client, document_id)
    assert result["provider"] == "orcarouter"
    assert errors(result) == set()
    assert "provider_unverified" in codes(result)

    app.state.settings.translation_session.override = None
    monkeypatch.setenv("GLYPH_TRANSLATION_PROVIDER", "orcarouter")
    app2 = make_book_app(tmp_path, monkeypatch, GLYPH_TRANSLATION_PROVIDER="orcarouter")
    client2 = TestClient(app2)
    document_id = client2.get("/api/documents").json()[0]["id"]
    result = preflight(client2, document_id)
    assert "orcarouter_unconfigured" in errors(result)
    response = client2.post(f"/api/documents/{document_id}/process")
    assert response.status_code == 422
    assert "OrcaRouter" in response.json()["detail"]


def test_missing_source_is_a_blocker(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch)
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    (tmp_path / "book" / "sample.pdf").unlink()
    result = preflight(client, document_id)
    assert result["ready"] is False
    assert "source_missing" in errors(result)
    assert client.get("/api/documents/unknown/preflight").status_code == 404


def test_pdf_checks_are_bounded_and_report_unreadable_pdfs(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch, GLYPH_PAGE_RENDER_TIMEOUT_SECONDS="7")
    (tmp_path / "book" / "broken.pdf").write_bytes(b"%PDF-1.4\n\xff\xfe binary")
    observed: list[tuple[list[str], float | None]] = []

    def fake_run(command, **kwargs):
        observed.append((list(command), kwargs.get("timeout")))
        if "pdfinfo" in command[0]:
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout") or 0)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="secret")

    monkeypatch.setattr("glyph.processing_preflight.subprocess.run", fake_run)
    monkeypatch.setattr("glyph.ocr.subprocess.run", fake_run)
    monkeypatch.setattr(
        "glyph.processing_preflight.shutil.which", lambda name: f"/usr/bin/{name}"
    )
    client = TestClient(app)
    document_id = next(
        d["id"]
        for d in client.get("/api/documents").json()
        if d["title"] == "broken.pdf"
    )
    result = preflight(client, document_id)
    assert result["ready"] is False
    assert result["page_count"] is None
    assert "pdf_unreadable" in errors(result)
    assert observed and all(timeout == 7 for _, timeout in observed)
    assert "secret" not in str(result)


def test_active_job_is_reported_and_blocks_a_second_run(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch)
    monkeypatch.setattr(
        app.state.processing_job_executor, "submit", lambda *a, **k: None
    )
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    assert client.post(f"/api/documents/{document_id}/process").status_code == 202
    result = preflight(client, document_id)
    assert result["ready"] is False
    assert "job_active" in errors(result)
    assert client.post(f"/api/documents/{document_id}/process").status_code == 409


def test_real_poppler_path_is_used_when_available(tmp_path, monkeypatch):
    if shutil.which("pdftotext") is None or shutil.which("pdfinfo") is None:
        pytest.skip("Poppler is not installed")
    app = make_book_app(tmp_path, monkeypatch)
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    assert process_and_wait(client, document_id)["status"] == "completed"


def test_text_pdf_still_validates_the_selected_ocr_adapter(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch, GLYPH_OCR_MODE="unlimited_ocr")
    (tmp_path / "book" / "paper.pdf").write_bytes(b"%PDF-1.4\n\xff\xfe binary")
    monkeypatch.setattr("glyph.processing_preflight.pdf_page_count", lambda *a, **k: 2)
    monkeypatch.setattr("glyph.processing_preflight.pdf_has_text", lambda *a, **k: True)
    monkeypatch.setattr(
        "glyph.processing_preflight.shutil.which", lambda name: f"/usr/bin/{name}"
    )
    client = TestClient(app)
    document_id = next(
        d["id"]
        for d in client.get("/api/documents").json()
        if d["title"] == "paper.pdf"
    )
    result = preflight(client, document_id)
    assert result["ready"] is False
    assert "ocr_unconfigured" in errors(result)


@pytest.mark.parametrize(
    ("env", "fragment"),
    [
        (
            {
                "GLYPH_UNLIMITED_OCR_COMMAND": "missing-ocr-tool --input {input} --output_dir {output_dir}"
            },
            "not installed",
        ),
        ({"GLYPH_UNLIMITED_OCR_REPO": "{tmp}/repo-without-infer"}, "infer.py"),
        ({"GLYPH_UNLIMITED_OCR_REPO": "{tmp}/does-not-exist"}, "directory"),
    ],
)
def test_unlimited_ocr_configuration_is_checked_locally_without_running(
    tmp_path, monkeypatch, env, fragment
):
    (tmp_path / "repo-without-infer").mkdir()
    app = make_book_app(
        tmp_path,
        monkeypatch,
        GLYPH_OCR_MODE="unlimited_ocr",
        **{key: value.replace("{tmp}", str(tmp_path)) for key, value in env.items()},
    )
    (tmp_path / "book" / "scan.png").write_bytes(PNG)
    ran: list[list[str]] = []
    monkeypatch.setattr(
        "glyph.ocr.subprocess.run", lambda command, **k: ran.append(command)
    )
    client = TestClient(app)
    document_id = next(
        d["id"] for d in client.get("/api/documents").json() if d["title"] == "scan.png"
    )
    result = preflight(client, document_id)
    assert "ocr_unconfigured" in errors(result)
    assert fragment in next(
        i["message"] for i in result["issues"] if i["code"] == "ocr_unconfigured"
    )
    assert ran == []


def test_unlimited_ocr_repo_with_infer_is_accepted(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "infer.py").write_text("print('never executed by preflight')")
    app = make_book_app(
        tmp_path,
        monkeypatch,
        GLYPH_OCR_MODE="unlimited_ocr",
        GLYPH_UNLIMITED_OCR_REPO=str(repo),
    )
    (tmp_path / "book" / "scan.png").write_bytes(PNG)
    client = TestClient(app)
    document_id = next(
        d["id"] for d in client.get("/api/documents").json() if d["title"] == "scan.png"
    )
    result = preflight(client, document_id)
    assert errors(result) - {"development_fixture"} == set()
    assert result["ready"] is True


def test_damaged_binary_file_is_never_ready(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch)
    (tmp_path / "book" / "damaged.pdf").write_bytes(b"\x00\x01\x02garbage\xff\xfe")
    client = TestClient(app)
    document_id = next(
        d["id"]
        for d in client.get("/api/documents").json()
        if d["title"] == "damaged.pdf"
    )
    result = preflight(client, document_id)
    assert result["ready"] is False
    assert "source_unreadable" in errors(result)
    assert client.post(f"/api/documents/{document_id}/process").status_code == 422


def test_text_fixture_requires_mock_ocr(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "infer.py").write_text("")
    app = make_book_app(
        tmp_path,
        monkeypatch,
        GLYPH_OCR_MODE="unlimited_ocr",
        GLYPH_UNLIMITED_OCR_REPO=str(repo),
    )
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    result = preflight(client, document_id)
    assert result["ready"] is False
    assert "development_fixture" in errors(result)


def test_malformed_environment_key_is_blocked_without_leaking(
    tmp_path, monkeypatch, caplog
):
    import glyph.orcarouter as orca

    calls: list[bytes] = []
    monkeypatch.setattr(
        orca, "https_transport", lambda body, headers, timeout: calls.append(body)
    )
    app = make_book_app(
        tmp_path,
        monkeypatch,
        GLYPH_TRANSLATION_PROVIDER="orcarouter",
        GLYPH_ORCAROUTER_MODEL="m",
        ORCAROUTER_API_KEY="secret-part\nInjected: header",
    )
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    result = preflight(client, document_id)
    assert result["ready"] is False
    assert "orcarouter_key_invalid" in errors(result)
    response = client.post(f"/api/documents/{document_id}/process")
    assert response.status_code == 422
    assert "secret-part" not in response.text
    assert "secret-part" not in str(result)
    assert "secret-part" not in caplog.text
    assert calls == []
