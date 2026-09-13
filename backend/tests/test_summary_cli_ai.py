from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from support import make_book_app, process_and_wait

from glyph.cli_ai import CliAiError, TranslationCancelledError
from glyph.summaries import capture_summary_inputs, validate_claims
from glyph.summary_cli_ai import (
    MAX_SUMMARY_BLOCK_CHARS,
    CliSummaryError,
    CliSummaryProvider,
)

TEXT = (
    "# Introduction\n\nAlpha decays quickly after publication.\n\n"
    "Returns concentrate in small stocks.\n\n"
    "# Data\n\nThe sample covers 1990 to 2020.\n\nCRSP monthly returns are used."
)


def inputs_for(tmp_path, monkeypatch, text=TEXT):
    app = make_book_app(tmp_path, monkeypatch, text)
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    assert process_and_wait(client, document_id)["status"] == "completed"
    with app.state.session_factory() as session:
        return capture_summary_inputs(session, document_id)


def structured_runner(record: list[dict]):
    """A CLI stand-in that answers each stage with schema-valid JSON."""

    def runner(command, prompt, timeout_seconds):
        payload = json.loads(prompt)
        record.append(payload)
        assert "--json-schema" in command or "--output-schema" in command
        if payload["stage"] == "section_claims":
            blocks = payload["untrusted_document"]["blocks"]
            return {
                "claims": [
                    {
                        "text": f"Claim about {block['id']}",
                        "evidence": [
                            {
                                "block_id": block["id"],
                                "quote_text": block["source_text"],
                                "quote_start": 0,
                                "quote_end": len(block["source_text"]),
                            }
                        ],
                    }
                    for block in blocks
                ]
            }
        return {
            "claims": [
                {
                    "text": "Overview drawn from accepted section quotes.",
                    "evidence": [
                        {
                            "block_id": quote["block_id"],
                            "quote_text": quote["quote_text"],
                            "quote_start": quote["quote_start"],
                            "quote_end": quote["quote_end"],
                        }
                        for quote in payload["accepted_quotes"][:3]
                    ],
                }
            ]
        }

    return runner


def provider_for(runner, tmp_path, batch_size=12, model=None):
    return CliSummaryProvider(
        provider="claude",
        model=model,
        timeout_seconds=30,
        block_batch_size=batch_size,
        cache_dir=tmp_path / "summary-cache",
        runner=runner,
    )


def test_real_structured_responses_become_validated_claims(tmp_path, monkeypatch):
    inputs = inputs_for(tmp_path, monkeypatch)
    record: list[dict] = []
    provider = provider_for(structured_runner(record), tmp_path)
    accepted = validate_claims(
        inputs, provider.generate(inputs, should_cancel=lambda: False)
    )
    assert (provider.name, provider.model_name) == ("claude_cli", None)
    assert accepted[0].section_path is None
    assert {c.section_path for c in accepted[1:]} == set(inputs.section_paths)
    stages = [payload["stage"] for payload in record]
    assert stages.count("section_claims") == len(inputs.section_paths)
    assert stages[-1] == "overview"
    assert all("security" in payload for payload in record)
    # Prompts wrap document text as untrusted data and carry the section path.
    section_payloads = [p for p in record if p["stage"] == "section_claims"]
    assert {p["section_path"] for p in section_payloads} == set(inputs.section_paths)


def test_batches_are_bounded_and_cached(tmp_path, monkeypatch):
    inputs = inputs_for(tmp_path, monkeypatch)
    record: list[dict] = []
    provider = provider_for(structured_runner(record), tmp_path, batch_size=1)
    provider.generate(inputs, should_cancel=lambda: False)
    section_batches = [p for p in record if p["stage"] == "section_claims"]
    assert len(section_batches) == len(inputs.blocks)
    assert all(len(p["untrusted_document"]["blocks"]) == 1 for p in section_batches)
    first_run = len(record)
    provider.generate(inputs, should_cancel=lambda: False)
    assert len(record) == first_run  # every stage came from the cache


def test_oversized_block_fails_explicitly_instead_of_truncating(tmp_path, monkeypatch):
    long_text = "# Big\n\n" + ("x" * (MAX_SUMMARY_BLOCK_CHARS + 1))
    inputs = inputs_for(tmp_path, monkeypatch, long_text)
    record: list[dict] = []
    provider = provider_for(structured_runner(record), tmp_path)
    with pytest.raises(CliSummaryError, match="exceeds"):
        provider.generate(inputs, should_cancel=lambda: False)
    assert record == []


@pytest.mark.parametrize(
    "response",
    [
        {"claims": "not a list"},
        {"claims": [{"text": "", "evidence": []}]},
        {"claims": [{"text": "x", "evidence": [{"block_id": 5}]}]},
        {"other": []},
    ],
)
def test_malformed_output_is_retried_once_then_fails_safely(
    tmp_path, monkeypatch, response
):
    inputs = inputs_for(tmp_path, monkeypatch)
    calls: list[str] = []

    def runner(command, prompt, timeout_seconds):
        calls.append(json.loads(prompt).get("correction", ""))
        return response

    provider = provider_for(runner, tmp_path)
    with pytest.raises(CliSummaryError) as error:
        provider.generate(inputs, should_cancel=lambda: False)
    assert len(calls) == 2
    assert calls[1]
    assert "Traceback" not in str(error.value)
    assert (
        not list((tmp_path / "summary-cache").glob("*.json"))
        if (tmp_path / "summary-cache").exists()
        else True
    )


def test_cli_failures_do_not_expose_tool_output(tmp_path, monkeypatch):
    inputs = inputs_for(tmp_path, monkeypatch)

    def runner(command, prompt, timeout_seconds):
        raise CliAiError("claude CLI failed with exit code 2")

    provider = provider_for(runner, tmp_path)
    with pytest.raises(CliSummaryError) as error:
        provider.generate(inputs, should_cancel=lambda: False)
    assert "secret" not in str(error.value)
    assert "summary" in str(error.value).lower()


def test_cancellation_stops_between_batches(tmp_path, monkeypatch):
    inputs = inputs_for(tmp_path, monkeypatch)
    record: list[dict] = []
    provider = provider_for(structured_runner(record), tmp_path, batch_size=1)
    with pytest.raises(TranslationCancelledError):
        provider.generate(inputs, should_cancel=lambda: len(record) >= 1)
    assert len(record) == 1


def test_fabricated_section_quote_never_reaches_cache_or_overview(
    tmp_path, monkeypatch
):
    inputs = inputs_for(tmp_path, monkeypatch)
    record: list[dict] = []

    def runner(command, prompt, timeout_seconds):
        payload = json.loads(prompt)
        record.append(payload)
        blocks = payload["untrusted_document"]["blocks"]
        return {
            "claims": [
                {
                    "text": "Fabricated",
                    "evidence": [
                        {
                            "block_id": blocks[0]["id"],
                            "quote_text": "text that is not in the block",
                            "quote_start": None,
                            "quote_end": None,
                        }
                    ],
                }
            ]
        }

    provider = provider_for(runner, tmp_path)
    with pytest.raises(CliSummaryError, match="section claims"):
        provider.generate(inputs, should_cancel=lambda: False)
    assert [p["stage"] for p in record] == ["section_claims", "section_claims"]
    assert "correction" in record[1]
    cache = tmp_path / "summary-cache"
    assert not cache.exists() or not list(cache.glob("*.json"))


def test_foreign_batch_block_ids_are_rejected_by_the_stage_validator(
    tmp_path, monkeypatch
):
    inputs = inputs_for(tmp_path, monkeypatch)
    other = inputs.blocks[-1]

    def runner(command, prompt, timeout_seconds):
        payload = json.loads(prompt)
        block = payload["untrusted_document"]["blocks"][0]
        target = other if other.id != block["id"] else inputs.blocks[0]
        return {
            "claims": [
                {
                    "text": "Cites a block outside this batch",
                    "evidence": [
                        {
                            "block_id": target.id,
                            "quote_text": target.source_text,
                            "quote_start": 0,
                            "quote_end": len(target.source_text),
                        }
                    ],
                }
            ]
        }

    provider = provider_for(runner, tmp_path, batch_size=1)
    with pytest.raises(CliSummaryError):
        provider.generate(inputs, should_cancel=lambda: False)


def test_corrupt_cached_quotes_are_evicted_and_regenerated(tmp_path, monkeypatch):
    inputs = inputs_for(tmp_path, monkeypatch)
    record: list[dict] = []
    provider = provider_for(structured_runner(record), tmp_path)
    provider.generate(inputs, should_cancel=lambda: False)
    first_run = len(record)
    cache_files = list((tmp_path / "summary-cache").glob("*.json"))
    assert cache_files
    for path in cache_files:
        path.write_text(path.read_text().replace("Alpha decays", "Alpha DECAYED"))
    accepted = validate_claims(
        inputs, provider.generate(inputs, should_cancel=lambda: False)
    )
    assert len(record) > first_run
    assert all(
        next(b for b in inputs.blocks if b.id == q.block_id).source_text[
            q.quote_start : q.quote_end
        ]
        == q.quote_text
        for c in accepted
        for q in c.evidence
    )


def test_overview_must_cite_accepted_quote_identities(tmp_path, monkeypatch):
    inputs = inputs_for(tmp_path, monkeypatch)
    record: list[dict] = []
    base = structured_runner(record)

    def runner(command, prompt, timeout_seconds):
        payload = json.loads(prompt)
        if payload["stage"] == "overview":
            block = inputs.blocks[1]
            return {
                "claims": [
                    {
                        "text": "Overview citing an unaccepted span",
                        "evidence": [
                            {
                                "block_id": block.id,
                                "quote_text": block.source_text[:5],
                                "quote_start": 0,
                                "quote_end": 5,
                            }
                        ],
                    }
                ]
            }
        return base(command, prompt, timeout_seconds)

    provider = provider_for(runner, tmp_path)
    with pytest.raises(CliSummaryError, match="overview"):
        provider.generate(inputs, should_cancel=lambda: False)


def test_cancellation_during_first_failing_call_prevents_the_retry(
    tmp_path, monkeypatch
):
    inputs = inputs_for(tmp_path, monkeypatch)
    calls = 0
    cancelled = False

    def runner(command, prompt, timeout_seconds):
        nonlocal calls, cancelled
        calls += 1
        cancelled = True
        return {"claims": "malformed"}

    provider = provider_for(runner, tmp_path)
    with pytest.raises(TranslationCancelledError):
        provider.generate(inputs, should_cancel=lambda: cancelled)
    assert calls == 1


def test_prompt_character_bounds_are_explicit(tmp_path, monkeypatch):
    import glyph.summary_cli_ai as module

    inputs = inputs_for(tmp_path, monkeypatch)
    record: list[dict] = []
    provider = provider_for(structured_runner(record), tmp_path, batch_size=50)
    monkeypatch.setattr(module, "MAX_PROMPT_CHARS", 400)
    with pytest.raises(CliSummaryError, match="exceeds"):
        provider.generate(inputs, should_cancel=lambda: False)
    assert record == []
    monkeypatch.setattr(module, "MAX_PROMPT_CHARS", 100_000)
    monkeypatch.setattr(module, "MAX_OVERVIEW_PROMPT_CHARS", 200)
    record.clear()
    with pytest.raises(CliSummaryError, match="overview"):
        provider.generate(inputs, should_cancel=lambda: False)
    assert all(p["stage"] == "section_claims" for p in record)
