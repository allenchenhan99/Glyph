from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from glyph.main import create_app

WORKSPACE_KEYS = {
    "status",
    "development_features",
    "translation",
    "research",
    "ocr",
    "recovery",
}
RESEARCH_FEATURES = ["summaries", "research_maps", "implementation_contracts"]


def workspace_app(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(tmp_path / "book"))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_OCR_MODE", "mock")
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    for name in (
        "GLYPH_TRANSLATION_PROVIDER",
        "ORCAROUTER_API_KEY",
        "GLYPH_ORCAROUTER_MODEL",
        "GLYPH_CLI_MODEL",
        "GLYPH_UNLIMITED_OCR_COMMAND",
        "GLYPH_UNLIMITED_OCR_REPO",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return create_app()


def which_only(*names: str):
    return lambda name: f"/usr/bin/{name}" if name in names else None


def get_workspace(client: TestClient) -> dict:
    response = client.get("/api/workspace")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == WORKSPACE_KEYS
    for capability in ("translation", "research", "ocr"):
        assert set(body[capability]) == {"provider", "configured", "message"}
        assert body[capability]["message"]
    return body


def test_all_mock_workspace_labels_every_deterministic_feature(tmp_path, monkeypatch):
    monkeypatch.setattr("glyph.workspace.shutil.which", which_only("pdftotext"))
    client = TestClient(workspace_app(tmp_path, monkeypatch))
    body = get_workspace(client)
    assert body["status"] == "ready"
    assert body["recovery"] is None
    assert body["development_features"] == ["translation", *RESEARCH_FEATURES]
    assert body["translation"] == {
        "provider": "mock",
        "configured": True,
        "message": body["translation"]["message"],
    }
    assert "deterministic" in body["translation"]["message"].lower()
    assert body["research"]["provider"] == "mock"
    assert body["research"]["configured"] is True
    assert body["ocr"]["provider"] == "mock"
    assert body["ocr"]["configured"] is True
    assert "text" in body["ocr"]["message"].lower()
    assert "scanned" in body["ocr"]["message"].lower()
    assert "deterministic" not in body["ocr"]["message"].lower()


def test_mock_ocr_with_real_research_cli_is_not_labeled_development(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "glyph.workspace.shutil.which", which_only("pdftotext", "claude")
    )
    client = TestClient(
        workspace_app(tmp_path, monkeypatch, GLYPH_AI_MODE="claude_cli")
    )
    body = get_workspace(client)
    assert body["development_features"] == []
    assert body["research"]["provider"] == "claude_cli"
    assert body["research"]["configured"] is True
    assert (
        "not verified" in body["research"]["message"].lower()
        or "cannot verify" in body["research"]["message"].lower()
    )
    assert body["translation"]["provider"] == "claude_cli"
    assert body["translation"]["configured"] is True


def test_missing_research_cli_is_reported_without_blocking_the_workspace(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("glyph.workspace.shutil.which", which_only("pdftotext"))
    client = TestClient(workspace_app(tmp_path, monkeypatch, GLYPH_AI_MODE="codex_cli"))
    body = get_workspace(client)
    assert body["status"] == "ready"
    assert body["research"]["configured"] is False
    assert "codex" in body["research"]["message"]
    assert "PATH" in body["research"]["message"]
    assert body["translation"]["configured"] is False


def test_translation_and_research_providers_are_independent(tmp_path, monkeypatch):
    monkeypatch.setattr("glyph.workspace.shutil.which", which_only("pdftotext"))
    app = workspace_app(tmp_path, monkeypatch, GLYPH_TRANSLATION_PROVIDER="orcarouter")
    client = TestClient(app)
    body = get_workspace(client)
    assert body["development_features"] == RESEARCH_FEATURES
    assert body["translation"]["provider"] == "orcarouter"
    assert body["translation"]["configured"] is False
    assert "model" in body["translation"]["message"].lower()
    assert body["research"]["provider"] == "mock"

    applied = client.post(
        "/api/settings/ai",
        json={
            "provider": "orcarouter",
            "model": "vendor/model",
            "api_key": "private-session-key",
        },
    )
    assert applied.status_code == 200
    response = client.get("/api/workspace")
    body = response.json()
    assert body["translation"]["configured"] is True
    assert (
        "not verified" in body["translation"]["message"].lower()
        or "no request" in body["translation"]["message"].lower()
    )
    assert "private-session-key" not in response.text
    assert "vendor/model" not in response.text


def test_environment_secrets_never_appear_in_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("glyph.workspace.shutil.which", which_only("pdftotext"))
    client = TestClient(
        workspace_app(
            tmp_path,
            monkeypatch,
            GLYPH_TRANSLATION_PROVIDER="orcarouter",
            ORCAROUTER_API_KEY="env-secret-key\nInjected",
            GLYPH_ORCAROUTER_MODEL="m",
        )
    )
    response = client.get("/api/workspace")
    assert response.status_code == 200
    assert "env-secret-key" not in response.text
    assert response.json()["translation"]["configured"] is False


@pytest.mark.parametrize(
    ("env", "configured", "fragment"),
    [
        ({}, False, "GLYPH_UNLIMITED_OCR_COMMAND"),
        (
            {
                "GLYPH_UNLIMITED_OCR_COMMAND": "missing-tool --input {input} --output_dir {output_dir}"
            },
            False,
            "not installed",
        ),
        ({"GLYPH_UNLIMITED_OCR_REPO": "{tmp}/repo"}, True, "scanned"),
    ],
)
def test_ocr_capability_explains_configured_adapter(
    tmp_path, monkeypatch, env, configured, fragment
):
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / "infer.py").write_text("")
    monkeypatch.setattr("glyph.workspace.shutil.which", which_only("pdftotext"))
    client = TestClient(
        workspace_app(
            tmp_path,
            monkeypatch,
            GLYPH_OCR_MODE="unlimited_ocr",
            **{k: v.replace("{tmp}", str(tmp_path)) for k, v in env.items()},
        )
    )
    body = get_workspace(client)
    assert body["ocr"]["provider"] == "unlimited_ocr"
    assert body["ocr"]["configured"] is configured
    assert fragment in body["ocr"]["message"]
    assert "development_features" in body and "ocr" not in body["development_features"]


def test_missing_poppler_is_reported_for_mock_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr("glyph.workspace.shutil.which", which_only())
    body = get_workspace(TestClient(workspace_app(tmp_path, monkeypatch)))
    assert body["ocr"]["configured"] is False
    assert "pdftotext" in body["ocr"]["message"]


def legacy_desktop_database(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        for table in (
            "blocks",
            "documents",
            "pages",
            "processing_jobs",
            "sections",
            "summaries",
            "document_revisions",
        ):
            connection.execute(
                f"CREATE TABLE {table} (id TEXT PRIMARY KEY, payload TEXT)"
            )
        connection.execute(
            "INSERT INTO documents VALUES ('doc-1', 'private desktop row')"
        )
        connection.commit()
    finally:
        connection.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_unsupported_database_starts_diagnostic_app_without_touching_it(
    tmp_path, monkeypatch
):
    database = tmp_path / "data" / "glyph.sqlite3"
    before = legacy_desktop_database(database)
    app = workspace_app(tmp_path, monkeypatch)
    client = TestClient(app)

    body = get_workspace(client)
    assert body["status"] == "blocked"
    assert body["development_features"] == []
    assert body["recovery"]
    assert "GLYPH_DATA_DIR" in body["recovery"]
    assert "GLYPH_DATABASE_URL" in body["recovery"]
    assert "unchanged" in body["recovery"].lower()
    for capability in ("translation", "research", "ocr"):
        assert body[capability]["configured"] is False
    assert "private desktop row" not in client.get("/api/workspace").text

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "blocked"
    assert "recovery" in health.json()

    for method, path in (
        ("GET", "/api/documents"),
        ("POST", "/api/documents/upload"),
        ("POST", "/api/documents/doc-1/process"),
        ("GET", "/api/jobs"),
        ("POST", "/api/settings/ai"),
        ("GET", "/api/documents/doc-1/summaries"),
        ("POST", "/api/documents/doc-1/research-map"),
        ("PATCH", "/api/anything"),
    ):
        response = client.request(method, path)
        assert response.status_code == 503, (method, path, response.text)
        assert (
            "recovery" in response.json()["detail"].lower()
            or "GLYPH_DATA_DIR" in response.json()["detail"]
        )

    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert not list((tmp_path / "data").glob("*.sqlite3-journal"))

    # Recovery: a new empty GLYPH_DATA_DIR starts a ready workspace; old file untouched.
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "fresh"))
    monkeypatch.setattr("glyph.workspace.shutil.which", which_only("pdftotext"))
    recovered = TestClient(create_app())
    assert recovered.get("/api/workspace").json()["status"] == "ready"
    assert recovered.get("/api/documents").status_code == 200
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("GLYPH_AI_MODE", "secret-looking-value"),
        ("GLYPH_MAX_UPLOAD_BYTES", "0"),
        ("GLYPH_TRANSLATION_PROVIDER", "another-secret"),
    ],
)
def test_invalid_configuration_starts_diagnostic_app_without_echoing_values(
    tmp_path, monkeypatch, name, value
):
    app = workspace_app(tmp_path, monkeypatch, **{name: value})
    client = TestClient(app)
    response = client.get("/api/workspace")
    body = response.json()
    assert body["status"] == "blocked"
    assert name in body["recovery"]
    assert value not in response.text
    assert client.get("/api/health").json()["status"] == "blocked"
    assert client.get("/api/documents").status_code == 503


@pytest.mark.parametrize(
    "name",
    ["GLYPH_CLI_BATCH_SIZE", "GLYPH_CLI_TIMEOUT_SECONDS", "GLYPH_CLI_CONCURRENCY"],
)
@pytest.mark.parametrize("value", ["sk-fake-secret-value", "0", "-3"])
def test_cli_integer_settings_diagnose_without_echoing_values(
    tmp_path, monkeypatch, name, value
):
    client = TestClient(workspace_app(tmp_path, monkeypatch, **{name: value}))
    response = client.get("/api/workspace")
    body = response.json()
    assert body["status"] == "blocked"
    assert name in body["recovery"]
    assert value not in response.text
    assert value not in client.get("/api/health").text
    assert value not in client.get("/api/documents").text
