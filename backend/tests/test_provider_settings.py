from __future__ import annotations

import json

from fastapi.testclient import TestClient

from glyph.ai import MockAiAdapter, create_ai_adapter
from glyph.config import get_settings, resolve_translation_settings
from glyph.contract_ai import (
    MockImplementationContractProvider,
    create_implementation_contract_provider,
)
from glyph.main import create_app
from glyph.orcarouter import OrcaRouterAdapter, TransportResponse
from glyph.research_ai import MockResearchMapProvider, create_research_map_provider


def make_app(tmp_path, monkeypatch):
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(tmp_path / "book"))
    monkeypatch.setenv("GLYPH_OCR_MODE", "mock")
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    monkeypatch.delenv("ORCAROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GLYPH_TRANSLATION_PROVIDER", raising=False)
    return create_app()


def test_session_settings_redact_key_and_reset_per_process(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)
    client = TestClient(app)
    assert client.get("/api/settings/ai").json() == {
        "provider": "mock",
        "model": "",
        "has_api_key": False,
        "ocr_mode": "mock",
    }
    payload = {
        "provider": "orcarouter",
        "model": "test/model",
        "api_key": "private-key",
    }
    response = client.post("/api/settings/ai", json=payload)
    assert response.status_code == 200
    assert response.json() == {
        "provider": "orcarouter",
        "model": "test/model",
        "has_api_key": True,
        "ocr_mode": "mock",
    }
    assert "private-key" not in response.text
    assert "private-key" not in client.get("/api/settings/ai").text
    assert "private-key" not in repr(app.state.settings)
    resolved = resolve_translation_settings(app.state.settings)
    assert (resolved.provider, resolved.model) == ("orcarouter", "test/model")
    assert "private-key" not in repr(resolved)
    assert "private-key" not in client.get("/api/health").text

    # Model changes keep the stored key when the field is left blank.
    response = client.post(
        "/api/settings/ai", json={"provider": "orcarouter", "model": "test/other"}
    )
    assert response.json()["has_api_key"] is True
    assert resolve_translation_settings(app.state.settings).api_key == "private-key"

    # A fresh process starts from environment configuration again.
    fresh = TestClient(make_app(tmp_path, monkeypatch)).get("/api/settings/ai").json()
    assert fresh == {
        "provider": "mock",
        "model": "",
        "has_api_key": False,
        "ocr_mode": "mock",
    }


def test_translation_override_does_not_change_map_and_contract_providers(
    tmp_path, monkeypatch
):
    app = make_app(tmp_path, monkeypatch)
    client = TestClient(app)
    client.post(
        "/api/settings/ai",
        json={"provider": "orcarouter", "model": "test/model", "api_key": "k"},
    )
    settings = app.state.settings
    assert settings.ai_mode == "mock"
    assert isinstance(create_research_map_provider(settings), MockResearchMapProvider)
    assert isinstance(
        create_implementation_contract_provider(settings),
        MockImplementationContractProvider,
    )
    assert isinstance(create_ai_adapter(settings), OrcaRouterAdapter)
    assert client.get("/api/health").json()["ai_mode"] == "mock"
    assert client.get("/api/health").json()["translation_provider"] == "orcarouter"

    client.post("/api/settings/ai", json={"provider": "mock", "model": ""})
    assert isinstance(create_ai_adapter(settings), MockAiAdapter)


def test_environment_can_select_orcarouter_for_translation_only(tmp_path, monkeypatch):
    monkeypatch.setenv("GLYPH_TRANSLATION_PROVIDER", "orcarouter")
    monkeypatch.setenv("ORCAROUTER_API_KEY", "env-key")
    monkeypatch.setenv("GLYPH_ORCAROUTER_MODEL", "env/model")
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    settings = get_settings()
    assert settings.ai_mode == "mock"
    assert "env-key" not in repr(settings)
    resolved = resolve_translation_settings(settings)
    assert (resolved.provider, resolved.model, resolved.api_key) == (
        "orcarouter",
        "env/model",
        "env-key",
    )
    assert isinstance(create_ai_adapter(settings), OrcaRouterAdapter)
    assert isinstance(create_research_map_provider(settings), MockResearchMapProvider)


def test_settings_validation_and_local_origin_guards(tmp_path, monkeypatch):
    client = TestClient(make_app(tmp_path, monkeypatch))
    payload = {"provider": "orcarouter", "model": "test/model"}
    assert client.post("/api/settings/ai", json=payload).status_code == 400
    assert (
        client.post("/api/settings/ai", json={**payload, "api_key": ""}).status_code
        == 400
    )
    assert (
        client.post("/api/settings/ai", json={**payload, "api_key": "a b"}).status_code
        == 400
    )
    assert (
        client.post("/api/settings/ai", json={**payload, "api_key": ["k"]}).status_code
        == 400
    )
    assert (
        client.post(
            "/api/settings/ai", json={"provider": "other", "model": ""}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/settings/ai", json={"provider": "mock", "extra": "x"}
        ).status_code
        == 400
    )
    assert client.post("/api/settings/ai", json=[1]).status_code == 400
    assert (
        client.post(
            "/api/settings/ai",
            content=b"{",
            headers={"Content-Type": "application/json"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/settings/ai",
            content=b"provider=mock",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).status_code
        == 415
    )
    good = {**payload, "api_key": "k"}
    assert (
        client.post(
            "/api/settings/ai", json=good, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/settings/ai", json=good, headers={"Origin": "http://127.0.0.1:5173"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/settings/ai", json=good, headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/settings/ai", json={"provider": "claude_cli", "model": "opus"}
        ).status_code
        == 200
    )
    assert client.get("/api/settings/ai").json()["model"] == "opus"


def test_document_processing_uses_session_orcarouter_settings(tmp_path, monkeypatch):
    import glyph.orcarouter as module

    bodies: list[bytes] = []

    def fake_transport(
        body: bytes, headers: dict[str, str], timeout: float
    ) -> TransportResponse:
        bodies.append(body)
        assert headers["Authorization"] == "Bearer session-key"
        blocks = json.loads(json.loads(body)["messages"][-1]["content"])["blocks"]
        items = [
            {"id": b["id"], "translated_text": "會話翻譯", "formula_latex": None}
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

    monkeypatch.setattr(module, "https_transport", fake_transport)
    app = make_app(tmp_path, monkeypatch)
    (tmp_path / "book").mkdir(parents=True, exist_ok=True)
    (tmp_path / "book" / "sample.pdf").write_text("# Title\n\nSome prose.")
    client = TestClient(app)
    assert (
        client.post(
            "/api/settings/ai",
            json={
                "provider": "orcarouter",
                "model": "test/model",
                "api_key": "session-key",
            },
        ).status_code
        == 200
    )
    document_id = client.get("/api/documents").json()[0]["id"]
    job = client.post(f"/api/documents/{document_id}/process").json()
    assert job["status"] == "completed", job
    reader = client.get(f"/api/documents/{document_id}/reader").json()
    assert any(block["translated_text"] == "會話翻譯" for block in reader["blocks"])
    assert bodies


def test_run_keeps_settings_captured_before_ocr(tmp_path, monkeypatch):
    import glyph.orcarouter as module
    import glyph.pipeline as pipeline
    from glyph.ocr import OcrPage

    calls: list[bytes] = []

    def fake_transport(
        body: bytes, headers: dict[str, str], timeout: float
    ) -> TransportResponse:
        calls.append(body)
        assert headers["Authorization"] == "Bearer first-key"
        blocks = json.loads(json.loads(body)["messages"][-1]["content"])["blocks"]
        items = [
            {"id": b["id"], "translated_text": "首次設定", "formula_latex": None}
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

    monkeypatch.setattr(module, "https_transport", fake_transport)
    app = make_app(tmp_path, monkeypatch)
    (tmp_path / "book").mkdir(parents=True, exist_ok=True)
    (tmp_path / "book" / "sample.pdf").write_text("# Title\n\nSome prose.")
    client = TestClient(app)

    class SlowOcr:
        def extract_pages(self, source_path):
            # A user changes Settings while OCR is still running.
            client.post("/api/settings/ai", json={"provider": "mock", "model": ""})
            return [
                OcrPage(page_number=1, text="# Title\n\nSome prose.", image_path=None)
            ]

    monkeypatch.setattr(pipeline, "create_ocr_adapter", lambda settings: SlowOcr())
    assert (
        client.post(
            "/api/settings/ai",
            json={
                "provider": "orcarouter",
                "model": "test/model",
                "api_key": "first-key",
            },
        ).status_code
        == 200
    )
    document_id = client.get("/api/documents").json()[0]["id"]
    job = client.post(f"/api/documents/{document_id}/process").json()
    assert job["status"] == "completed", job
    assert len(calls) == 1
    reader = client.get(f"/api/documents/{document_id}/reader").json()
    assert any(block["translated_text"] == "首次設定" for block in reader["blocks"])
    assert client.get("/api/settings/ai").json()["provider"] == "mock"


def test_missing_session_key_fails_job_with_public_message(tmp_path, monkeypatch):
    make_app(tmp_path, monkeypatch)  # base environment without any key
    monkeypatch.setenv("GLYPH_TRANSLATION_PROVIDER", "orcarouter")
    monkeypatch.delenv("GLYPH_ORCAROUTER_MODEL", raising=False)
    app = create_app()
    (tmp_path / "book").mkdir(parents=True, exist_ok=True)
    (tmp_path / "book" / "sample.pdf").write_text("# Title\n\nSome prose.")
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    job = client.post(f"/api/documents/{document_id}/process").json()
    assert job["status"] == "failed"
    assert "Settings" in job["error_message"]
