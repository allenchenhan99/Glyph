from __future__ import annotations

from fastapi.testclient import TestClient
from support import make_book_app, process_and_wait

from glyph.config import get_settings
from glyph.summaries import capture_summary_inputs, validate_claims
from glyph.summary_ai import (
    MOCK_LABEL,
    MockSummaryProvider,
    SummaryProvider,
    create_summary_provider,
)

TEXT = (
    "# Introduction\n\nAlpha decays quickly after publication.\n\n"
    "Returns concentrate in small stocks.\n\n"
    "# Data\n\nThe sample covers 1990 to 2020.\n\nCRSP monthly returns are used."
)


def test_mock_provider_returns_labeled_source_derived_claims(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch, TEXT)
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    assert process_and_wait(client, document_id)["status"] == "completed"
    with app.state.session_factory() as session:
        inputs = capture_summary_inputs(session, document_id)
        provider = MockSummaryProvider()
        drafts = provider.generate(inputs, should_cancel=lambda: False)
        accepted = validate_claims(inputs, drafts)
    assert provider.name == "mock"
    assert provider.model_name is None
    assert all(claim.text.startswith(MOCK_LABEL) for claim in accepted)
    assert accepted[0].section_path is None
    assert {claim.section_path for claim in accepted[1:]} == set(inputs.section_paths)
    for claim in accepted:
        for quote in claim.evidence:
            block = next(b for b in inputs.blocks if b.id == quote.block_id)
            assert (
                block.source_text[quote.quote_start : quote.quote_end]
                == quote.quote_text
            )
            assert quote.quote_text in claim.text


def test_provider_factory_follows_ai_mode_not_translation_settings(monkeypatch):
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    monkeypatch.setenv("GLYPH_TRANSLATION_PROVIDER", "orcarouter")
    monkeypatch.setenv("ORCAROUTER_API_KEY", "k")
    monkeypatch.setenv("GLYPH_ORCAROUTER_MODEL", "m")
    provider: SummaryProvider = create_summary_provider(get_settings())
    assert isinstance(provider, MockSummaryProvider)
    monkeypatch.setenv("GLYPH_AI_MODE", "codex_cli")
    monkeypatch.setenv("GLYPH_CLI_MODEL", "gpt-x")
    provider = create_summary_provider(get_settings())
    assert (provider.name, provider.model_name) == ("codex_cli", "gpt-x")
