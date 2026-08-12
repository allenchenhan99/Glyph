from __future__ import annotations

import hashlib
import json
import shutil

# CLI adapters use resolved argv, no shell, and explicit timeouts.
import subprocess  # nosec B404
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from glyph.ai import MockAiAdapter, ParsedDocument

CliRunner = Callable[[list[str], str, int], dict]


class CliAiError(RuntimeError):
    pass


TRANSLATION_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "translated_text": {"type": "string", "minLength": 1},
                    "formula_latex": {"type": ["string", "null"]},
                },
                "required": ["id", "translated_text", "formula_latex"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


class CliAiAdapter:
    def __init__(
        self,
        provider: str,
        model: str | None,
        batch_size: int,
        timeout_seconds: int,
        concurrency: int = 1,
        cache_dir: Path | None = None,
        runner: CliRunner | None = None,
    ) -> None:
        if provider not in {"claude", "codex"}:
            raise ValueError(f"Unsupported CLI AI provider: {provider}")
        if batch_size < 1:
            raise ValueError("CLI batch size must be at least 1")
        if concurrency < 1:
            raise ValueError("CLI concurrency must be at least 1")
        self.provider = provider
        self.model = model
        self.batch_size = batch_size
        self.timeout_seconds = timeout_seconds
        self.concurrency = concurrency
        self.cache_dir = cache_dir
        self.runner = runner or run_cli

    def parse_translate_and_summarize(
        self, page_text: list[tuple[int, str]]
    ) -> ParsedDocument:
        source_document = MockAiAdapter().parse_translate_and_summarize(page_text)
        schema_json = json.dumps(TRANSLATION_SCHEMA, ensure_ascii=True)
        batches = [
            source_document.blocks[start : start + self.batch_size]
            for start in range(0, len(source_document.blocks), self.batch_size)
        ]

        def translate_batch(batch):
            prompt = build_translation_prompt(batch)
            command = build_cli_command(self.provider, schema_json, self.model)
            translated_by_id = self.load_or_run_batch(command, prompt, batch)
            translated_batch = []
            for block in batch:
                item = translated_by_id[str(block.order_index)]
                translated_batch.append(
                    replace(
                        block,
                        translated_text=item["translated_text"].strip(),
                        formula_latex=normalize_formula_latex(item["formula_latex"]),
                    )
                )
            return translated_batch

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            translated_batches = list(executor.map(translate_batch, batches))
        translated_blocks = [block for batch in translated_batches for block in batch]

        return replace(source_document, blocks=translated_blocks)

    def load_or_run_batch(
        self, command: list[str], prompt: str, batch
    ) -> dict[str, dict]:
        cache_path = None
        if self.cache_dir is not None:
            cache_path = self.batch_cache_path(prompt)
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(cached, dict):
                    return validate_batch_response(cached, batch)
            except (FileNotFoundError, json.JSONDecodeError, OSError, CliAiError):
                cache_path.unlink(missing_ok=True)

        last_error = None
        current_prompt = prompt
        for _attempt in range(2):
            try:
                response = self.runner(command, current_prompt, self.timeout_seconds)
            except CliAiError as exc:
                last_error = exc
                current_prompt = add_retry_instruction(prompt, str(exc))
                continue
            try:
                validated = validate_batch_response(response, batch)
            except CliAiError as exc:
                last_error = exc
                current_prompt = add_retry_instruction(prompt, str(exc))
                continue
            if cache_path is not None:
                self.store_batch_cache(cache_path, response)
            return validated
        raise last_error or CliAiError("CLI returned an invalid translation batch")

    def batch_cache_path(self, prompt: str) -> Path:
        if self.cache_dir is None:
            raise CliAiError("CLI cache directory is not configured")
        cache_key = hashlib.sha256(
            f"{self.provider}\0{self.model or ''}\0{prompt}".encode()
        ).hexdigest()
        return self.cache_dir / f"{cache_key}.json"

    def store_batch_cache(self, cache_path: Path, response: dict) -> None:
        if self.cache_dir is None:
            raise CliAiError("CLI cache directory is not configured")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = cache_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(response, ensure_ascii=False), encoding="utf-8"
        )
        temporary_path.replace(cache_path)


def build_translation_prompt(blocks) -> str:
    payload = {
        "instructions": (
            "Translate every block into natural Traditional Chinese (Taiwan usage). Preserve all meaning, "
            "numbers, citations, and terminology. Do not prefix translations with labels. For a formula "
            "block, translated_text should translate its surrounding explanation and formula_latex must "
            "contain valid display-mode KaTeX-compatible LaTeX for the mathematical expression. For every "
            "Do not wrap LaTeX in dollar signs or \\[...\\] delimiters. For every "
            "non-formula block, formula_latex must be null. Return exactly one item for every input id."
        ),
        "blocks": [
            {
                "id": str(block.order_index),
                "block_type": block.block_type,
                "source_text": block.source_text,
            }
            for block in blocks
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def build_cli_command(provider: str, schema: str, model: str | None) -> list[str]:
    if provider == "claude":
        command = [
            "claude",
            "-p",
            "--tools",
            "",
            "--no-session-persistence",
            "--output-format",
            "json",
            "--json-schema",
            schema,
        ]
    elif provider == "codex":
        command = [
            "codex",
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--output-schema",
            schema,
            "-",
        ]
    else:
        raise ValueError(f"Unsupported CLI AI provider: {provider}")
    if model:
        command[1:1] = ["--model", model] if provider == "claude" else []
        if provider == "codex":
            command[2:2] = ["--model", model]
    return command


def run_cli(command: list[str], prompt: str, timeout_seconds: int) -> dict:
    executable = Path(command[0]).name
    try:
        if executable == "codex":
            return run_codex(command, prompt, timeout_seconds)
        resolved_command = resolve_cli_command(command, executable)
        completed = subprocess.run(  # nosec B603
            resolved_command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CliAiError(f"{executable} CLI is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise CliAiError(
            f"{executable} CLI timed out after {timeout_seconds} seconds"
        ) from exc
    if completed.returncode != 0:
        raise CliAiError(
            f"{executable} CLI failed with exit code {completed.returncode}"
        )
    try:
        envelope = json.loads(completed.stdout)
        structured = envelope.get("structured_output")
        if structured is None and isinstance(envelope.get("result"), str):
            structured = json.loads(envelope["result"])
        if not isinstance(structured, dict):
            raise ValueError("structured_output is missing")
        return structured
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise CliAiError(
            f"{executable} CLI returned invalid structured output"
        ) from exc


def run_codex(command: list[str], prompt: str, timeout_seconds: int) -> dict:
    schema_index = command.index("--output-schema") + 1
    schema = command[schema_index]
    try:
        with tempfile.TemporaryDirectory(prefix="glyph-codex-") as directory:
            schema_path = Path(directory) / "schema.json"
            output_path = Path(directory) / "result.json"
            schema_path.write_text(schema, encoding="utf-8")
            actual_command = resolve_cli_command(command, "codex")
            actual_command[schema_index] = str(schema_path)
            actual_command[-1:-1] = ["--output-last-message", str(output_path)]
            completed = subprocess.run(  # nosec B603
                actual_command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                raise CliAiError(
                    f"codex CLI failed with exit code {completed.returncode}"
                )
            return json.loads(output_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CliAiError("codex CLI is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise CliAiError(
            f"codex CLI timed out after {timeout_seconds} seconds"
        ) from exc
    except (json.JSONDecodeError, OSError) as exc:
        raise CliAiError("codex CLI returned invalid structured output") from exc


def resolve_cli_command(command: list[str], executable_name: str) -> list[str]:
    executable = shutil.which(command[0])
    if executable is None:
        raise CliAiError(f"{executable_name} CLI is not installed")
    return [executable, *command[1:]]


def validate_batch_response(response: dict, blocks) -> dict[str, dict]:
    items = response.get("items")
    if not isinstance(items, list):
        raise CliAiError("CLI response does not contain an items array")
    expected_ids = {str(block.order_index) for block in blocks}
    actual_ids = [item.get("id") for item in items if isinstance(item, dict)]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
        raise CliAiError("CLI translation coverage mismatch")

    by_id = {item["id"]: item for item in items}
    for block in blocks:
        item = by_id[str(block.order_index)]
        translated_text = item.get("translated_text")
        formula_latex = item.get("formula_latex")
        if not isinstance(translated_text, str) or not translated_text.strip():
            raise CliAiError(
                f"CLI returned an empty translation for block {block.order_index}"
            )
        if block.block_type == "formula" and (
            not isinstance(formula_latex, str) or not formula_latex.strip()
        ):
            raise CliAiError(
                f"CLI returned no LaTeX for formula block {block.order_index}"
            )
        if block.block_type != "formula" and formula_latex is not None:
            raise CliAiError(
                f"CLI returned LaTeX for non-formula block {block.order_index}"
            )
    return by_id


def normalize_formula_latex(value: str | None) -> str | None:
    if value is None:
        return None
    latex = value.strip()
    if (
        latex.startswith(r"\[")
        and latex.endswith(r"\]")
        or latex.startswith("$$")
        and latex.endswith("$$")
    ):
        latex = latex[2:-2].strip()
    return latex or None


def add_retry_instruction(prompt: str, error: str) -> str:
    payload = json.loads(prompt)
    payload["correction"] = (
        f"The previous response was rejected: {error}. Correct that exact problem. If OCR in a formula "
        "block is damaged or mixed with prose, reconstruct the recognizable mathematical expressions "
        "as faithful KaTeX-compatible LaTeX instead of returning null."
    )
    return json.dumps(payload, ensure_ascii=False)
