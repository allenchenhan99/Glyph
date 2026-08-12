import json
import shutil
import subprocess
import threading

import pytest

from glyph.cli_ai import (
    CliAiAdapter,
    CliAiError,
    build_cli_command,
    run_cli,
    run_codex,
)


def test_claude_cli_adapter_translates_every_block_and_returns_formula_latex():
    calls = []

    def runner(command, prompt, timeout_seconds):
        calls.append((command, json.loads(prompt), timeout_seconds))
        return {
            "items": [
                {
                    "id": "0",
                    "translated_text": "第一章 投資報酬",
                    "formula_latex": None,
                },
                {
                    "id": "1",
                    "translated_text": "預期報酬具有不確定性。",
                    "formula_latex": None,
                },
                {
                    "id": "2",
                    "translated_text": "預期報酬等於無風險利率加上貝塔乘以市場風險溢酬。",
                    "formula_latex": r"\[\mathbb{E}[R] = r_f + \beta(r_m-r_f)\]",
                },
            ]
        }

    adapter = CliAiAdapter(
        provider="claude",
        model=None,
        batch_size=10,
        timeout_seconds=90,
        concurrency=1,
        runner=runner,
    )

    parsed = adapter.parse_translate_and_summarize(
        [
            (
                1,
                "# Chapter 1 Investment Returns\n\n"
                "Expected return is uncertain.\n\n"
                "E[R] = rf + beta * (rm - rf)",
            )
        ]
    )

    assert [block.translated_text for block in parsed.blocks] == [
        "第一章 投資報酬",
        "預期報酬具有不確定性。",
        "預期報酬等於無風險利率加上貝塔乘以市場風險溢酬。",
    ]
    assert parsed.blocks[2].formula_latex == r"\mathbb{E}[R] = r_f + \beta(r_m-r_f)"
    assert calls[0][1]["blocks"][2]["source_text"] == "E[R] = rf + beta * (rm - rf)"
    assert calls[0][2] == 90


def test_cli_adapter_rejects_partial_results_instead_of_faking_translation():
    def runner(command, prompt, timeout_seconds):
        return {
            "items": [
                {"id": "0", "translated_text": "第一章", "formula_latex": None},
            ]
        }

    adapter = CliAiAdapter(
        provider="claude",
        model=None,
        batch_size=10,
        timeout_seconds=90,
        concurrency=1,
        runner=runner,
    )

    with pytest.raises(CliAiError, match="coverage mismatch"):
        adapter.parse_translate_and_summarize(
            [(1, "# Chapter 1\n\nExpected return is uncertain.")]
        )


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("claude", ["claude", "-p", "--tools", ""]),
        ("codex", ["codex", "exec", "--ephemeral", "--sandbox", "read-only"]),
    ],
)
def test_cli_commands_are_noninteractive_and_tool_restricted(provider, expected):
    command = build_cli_command(provider, '{"type":"object"}', model=None)

    assert command[: len(expected)] == expected


def test_cli_adapter_runs_bounded_batches_concurrently_and_preserves_order():
    barrier = threading.Barrier(2)

    def runner(command, prompt, timeout_seconds):
        block = json.loads(prompt)["blocks"][0]
        barrier.wait(timeout=2)
        return {
            "items": [
                {
                    "id": block["id"],
                    "translated_text": f"譯文 {block['id']}",
                    "formula_latex": None,
                }
            ]
        }

    adapter = CliAiAdapter(
        provider="claude",
        model=None,
        batch_size=1,
        timeout_seconds=90,
        concurrency=2,
        runner=runner,
    )

    parsed = adapter.parse_translate_and_summarize(
        [(1, "First paragraph.\n\nSecond paragraph.")]
    )

    assert [block.translated_text for block in parsed.blocks] == ["譯文 0", "譯文 1"]


def test_cli_adapter_reuses_completed_batch_cache(tmp_path):
    calls = 0

    def runner(command, prompt, timeout_seconds):
        nonlocal calls
        calls += 1
        block = json.loads(prompt)["blocks"][0]
        return {
            "items": [
                {
                    "id": block["id"],
                    "translated_text": "已快取的譯文",
                    "formula_latex": None,
                }
            ]
        }

    adapter = CliAiAdapter(
        provider="claude",
        model=None,
        batch_size=1,
        timeout_seconds=90,
        concurrency=1,
        cache_dir=tmp_path,
        runner=runner,
    )

    first = adapter.parse_translate_and_summarize(
        [(1, "Expected return is uncertain.")]
    )
    second = adapter.parse_translate_and_summarize(
        [(1, "Expected return is uncertain.")]
    )

    assert calls == 1
    assert (
        first.blocks[0].translated_text
        == second.blocks[0].translated_text
        == "已快取的譯文"
    )


def test_cli_adapter_retries_invalid_batch_before_caching(tmp_path):
    calls = 0
    prompts = []

    def runner(command, prompt, timeout_seconds):
        nonlocal calls
        calls += 1
        payload = json.loads(prompt)
        prompts.append(payload)
        block_id = payload["blocks"][0]["id"]
        return {
            "items": [
                {
                    "id": block_id,
                    "translated_text": "" if calls == 1 else "有效譯文",
                    "formula_latex": None,
                }
            ]
        }

    adapter = CliAiAdapter(
        provider="claude",
        model=None,
        batch_size=1,
        timeout_seconds=90,
        concurrency=1,
        cache_dir=tmp_path,
        runner=runner,
    )

    first = adapter.parse_translate_and_summarize(
        [(1, "Expected return is uncertain.")]
    )
    second = adapter.parse_translate_and_summarize(
        [(1, "Expected return is uncertain.")]
    )

    assert calls == 2
    assert "previous response was rejected" in prompts[1]["correction"]
    assert (
        first.blocks[0].translated_text
        == second.blocks[0].translated_text
        == "有效譯文"
    )


def test_cli_adapter_retries_transient_cli_failure():
    calls = 0

    def runner(command, prompt, timeout_seconds):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise CliAiError("claude CLI timed out")
        block_id = json.loads(prompt)["blocks"][0]["id"]
        return {
            "items": [
                {"id": block_id, "translated_text": "重試成功", "formula_latex": None}
            ]
        }

    adapter = CliAiAdapter("claude", None, 1, 90, concurrency=1, runner=runner)

    parsed = adapter.parse_translate_and_summarize(
        [(1, "Expected return is uncertain.")]
    )

    assert calls == 2
    assert parsed.blocks[0].translated_text == "重試成功"


def test_claude_cli_failure_uses_resolved_executable_without_exposing_stderr(
    monkeypatch,
):
    observed = {}
    monkeypatch.setattr(shutil, "which", lambda executable: f"/opt/bin/{executable}")

    def fail(command, **kwargs):
        observed["command"] = command
        return subprocess.CompletedProcess(
            command, 2, "", "/private/paper.pdf contains sensitive source text"
        )

    monkeypatch.setattr("glyph.cli_ai.subprocess.run", fail)

    with pytest.raises(CliAiError) as error:
        run_cli(["claude", "-p"], "private prompt", 9)

    assert str(error.value) == "claude CLI failed with exit code 2"
    assert observed["command"][0] == "/opt/bin/claude"
    assert "private" not in str(error.value)


def test_codex_cli_failure_uses_resolved_executable_without_exposing_stderr(
    monkeypatch,
):
    observed = {}
    monkeypatch.setattr(shutil, "which", lambda executable: f"/opt/bin/{executable}")

    def fail(command, **kwargs):
        observed["command"] = command
        return subprocess.CompletedProcess(
            command, 3, "", "/private/paper.pdf contains sensitive source text"
        )

    monkeypatch.setattr("glyph.cli_ai.subprocess.run", fail)
    command = ["codex", "exec", "--output-schema", '{"type":"object"}', "-"]

    with pytest.raises(CliAiError) as error:
        run_codex(command, "private prompt", 9)

    assert str(error.value) == "codex CLI failed with exit code 3"
    assert observed["command"][0] == "/opt/bin/codex"
    assert "private" not in str(error.value)
