"""Opt-in, single-page evaluation through Glyph's real translation/summary adapters.

Run from the repository root with the installed backend environment. Output
contains public source text and model translations; keep it outside git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil

# CLI names are allowlisted below; resolved argv and bounded calls, never a shell.
import subprocess  # nosec B404
import time
from dataclasses import asdict
from pathlib import Path

from glyph.ai import MockAiAdapter
from glyph.cli_ai import CliAiAdapter, run_cli
from glyph.models import Block
from glyph.ocr import extract_text_backed_pdf_pages
from glyph.summaries import SummaryInputs, validate_claims
from glyph.summary_cli_ai import CliSummaryProvider
from glyph.summary_domain import compute_reader_fingerprint


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--provider", choices=["claude", "codex"], required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument(
        "--task", choices=["translation", "summary"], default="translation"
    )
    args = parser.parse_args()
    if not args.run_live:
        parser.error("--run-live is required: this sends public text to your provider")
    manifest = json.loads(args.manifest.read_text())
    case = next(item for item in manifest["cases"] if item["id"] == args.case)
    if case["kind"] != "text":
        parser.error("Choose a text case; this evaluator does not perform scanned OCR")
    source = next(
        item for item in manifest["sources"] if item["id"] == case["source_id"]
    )
    filename = source["filename"]
    if Path(filename).name != filename:
        parser.error("Source filename must be a basename")
    path = args.corpus_dir / filename
    if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        parser.error("Source hash mismatch")
    page = next(
        page
        for page in extract_text_backed_pdf_pages(path)
        if page.page_number == case["page"]
    )
    if len(page.text) > 12000:
        parser.error("This bounded evaluation accepts at most 12000 source characters")
    calls = 0

    def runner(command: list[str], prompt: str, timeout: int) -> dict:
        nonlocal calls
        calls += 1
        if calls > 3:
            raise RuntimeError("Evaluation stopped after three provider attempts")
        return run_cli(command, prompt, timeout)

    executable = shutil.which(args.provider)
    if executable is None:
        parser.error("The selected provider CLI is not installed")
    cli_version = subprocess.run(  # nosec B603
        [executable, "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    ).stdout.strip()
    started = time.monotonic()
    page_input = [(page.page_number, page.text)]
    if args.task == "translation":
        adapter = CliAiAdapter(
            provider=args.provider,
            model=args.model,
            batch_size=24,
            timeout_seconds=120,
            concurrency=1,
            runner=runner,
        )
        parsed = adapter.parse_translate_and_summarize(page_input)
        outputs = {"blocks": [asdict(block) for block in parsed.blocks]}
    else:
        # Use the production source-block preparation without translating. The
        # summary provider receives only public source text, never mock output.
        prepared = MockAiAdapter().prepare_document(page_input)
        blocks = tuple(
            Block(
                id=f"quality-{block.order_index}",
                document_id=case["id"],
                order_index=block.order_index,
                page_number=block.page_number,
                block_type=block.block_type,
                source_text=block.source_text,
                translated_text="",
                source_content_hash=source["sha256"],
            )
            for block in prepared.blocks
        )
        inputs = SummaryInputs(
            case["id"],
            source["sha256"],
            compute_reader_fingerprint(blocks),
            blocks,
            tuple(section.path for section in prepared.sections),
            {
                block.id: prepared.blocks[index].section_title
                for index, block in enumerate(blocks)
            },
        )
        provider = CliSummaryProvider(
            provider=args.provider,
            model=args.model,
            timeout_seconds=120,
            block_batch_size=24,
            runner=runner,
        )
        claims = validate_claims(
            inputs, provider.generate(inputs, should_cancel=lambda: False)
        )
        outputs = {"claims": [asdict(claim) for claim in claims]}
    result = {
        "scope": f"live_{args.task}_single_public_page",
        "case": case["id"],
        "source_sha256": source["sha256"],
        "physical_pdf_page": case["page"],
        "provider": args.provider,
        "requested_model": args.model,
        "resolved_model": None,
        "model_note": "CLI aliases may resolve differently over time; adapter does not expose resolved model identity.",
        "cli_version": cli_version,
        "provider_calls": calls,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "source_text_sha256": hashlib.sha256(page.text.encode()).hexdigest(),
        **outputs,
        "semantic_quality": "Requires manual comparison; successful schema validation is not semantic approval.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "case": case["id"],
                "task": args.task,
                "provider_calls": calls,
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
