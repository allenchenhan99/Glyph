"""Deterministic quality-acceptance runner for a small public corpus.

Scope is extraction only: Poppler text extraction and Glyph's deterministic
block splitting. Nothing here calls a model, reads application settings, opens
the database, or evaluates translation or summary semantics. Every report
entry says so explicitly (``scope`` and ``semantics: null``); scanned pages are
rendered only to prove that OCR would be required, never to fabricate text.

Run: ``python -m glyph.quality --manifest PATH --corpus-dir DIR --output PATH``.
Downloads happen only with ``--download``, over HTTPS, bounded, hash-gated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil

# All subprocesses use resolved executables, fixed argv, no shell and timeouts.
import subprocess  # nosec B404
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from glyph.ai import MockAiAdapter, ParsedBlock
from glyph.ocr import (
    OCR_REQUIRED_MESSAGE,
    MockOcrAdapter,
    OcrPage,
    OcrUnavailableError,
    extract_text_backed_pdf_pages,
)

SCHEMA_VERSION = 1
SCOPE = "deterministic/extraction_only"
CASE_KINDS = ("text", "scan")
EXTRACTION_TIMEOUT_SECONDS = 120
RENDER_TIMEOUT_SECONDS = 60
PROBE_TIMEOUT_SECONDS = 30
DOWNLOAD_TIMEOUT_SECONDS = 60
DOWNLOAD_MAX_BYTES = 10 * 1024 * 1024
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}\.pdf$")


class QualityManifestError(ValueError):
    """The manifest is malformed or names unsafe inputs."""


class QualityCorpusError(RuntimeError):
    """A corpus file is missing, corrupted, or could not be fetched safely."""


@dataclass(frozen=True)
class Source:
    id: str
    filename: str
    url: str
    sha256: str
    pages: int
    title: str
    license_url: str
    rights_note: str


@dataclass(frozen=True)
class Case:
    id: str
    source_id: str
    page: int
    kind: str
    anchors: tuple[str, ...]
    ordered_passages: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Manifest:
    sources: tuple[Source, ...]
    cases: tuple[Case, ...]


# --- manifest ------------------------------------------------------------------


def load_manifest(path: Path) -> Manifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QualityManifestError(f"Cannot read manifest: {exc}") from None
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise QualityManifestError("Manifest schema_version must be 1")
    sources = tuple(_parse_source(item) for item in _list(payload, "sources"))
    if len({source.id for source in sources}) != len(sources):
        raise QualityManifestError("Manifest source ids must be unique")
    pages_by_source = {source.id: source.pages for source in sources}
    cases = tuple(
        _parse_case(item, pages_by_source) for item in _list(payload, "cases")
    )
    if len({case.id for case in cases}) != len(cases):
        raise QualityManifestError("Manifest case ids must be unique")
    return Manifest(sources=sources, cases=cases)


def _list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise QualityManifestError(f"Manifest {key} must be a list")
    return value


def _text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str):
        raise QualityManifestError(f"Manifest field {key!r} must be a string")
    return value


def _string_list(item: dict[str, Any], key: str) -> list[str]:
    value = item.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise QualityManifestError(f"Manifest case {key} must be a list of strings")
    return value


def _parse_source(item: Any) -> Source:
    if not isinstance(item, dict):
        raise QualityManifestError("Manifest source must be an object")
    filename = _text(item, "filename")
    if not SAFE_FILENAME.fullmatch(filename) or ".." in filename:
        raise QualityManifestError(
            f"Manifest source filename {filename!r} must be a plain .pdf name"
        )
    url = _text(item, "url")
    if not url.startswith("https://"):
        raise QualityManifestError("Manifest source url must use https")
    sha256 = _text(item, "sha256").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise QualityManifestError("Manifest source sha256 must be 64 hex characters")
    pages = item.get("pages")
    if not isinstance(pages, int) or isinstance(pages, bool) or pages < 1:
        raise QualityManifestError("Manifest source pages must be a positive integer")
    return Source(
        id=_text(item, "id"),
        filename=filename,
        url=url,
        sha256=sha256,
        pages=pages,
        title=_text(item, "title"),
        license_url=_text(item, "license_url"),
        rights_note=_text(item, "rights_note"),
    )


def _parse_case(item: Any, pages_by_source: dict[str, int]) -> Case:
    if not isinstance(item, dict):
        raise QualityManifestError("Manifest case must be an object")
    source_id = _text(item, "source_id")
    if source_id not in pages_by_source:
        raise QualityManifestError(
            f"Manifest case references unknown source {source_id!r}"
        )
    kind = _text(item, "kind")
    if kind not in CASE_KINDS:
        raise QualityManifestError(f"Manifest case kind must be one of {CASE_KINDS}")
    page = item.get("page")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise QualityManifestError("Manifest case page must be a positive integer")
    if page > pages_by_source[source_id]:
        raise QualityManifestError(
            f"Manifest case page {page} exceeds the {pages_by_source[source_id]} "
            f"pages declared for source {source_id!r}"
        )
    anchors = _string_list(item, "anchors")
    passages = _string_list(item, "ordered_passages")
    rows = item.get("rows", [])
    if not isinstance(rows, list) or not all(
        isinstance(row, list) and row and all(isinstance(cell, str) for cell in row)
        for row in rows
    ):
        raise QualityManifestError(
            "Manifest rows must be a list of non-empty string lists"
        )
    return Case(
        id=_text(item, "id"),
        source_id=source_id,
        page=page,
        kind=kind,
        anchors=tuple(anchors),
        ordered_passages=tuple(passages),
        rows=tuple(tuple(row) for row in rows),
    )


# --- corpus --------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_source(corpus_dir: Path, source: Source, *, download: bool) -> Path:
    path = corpus_dir / source.filename
    if not path.is_file():
        if not download:
            raise QualityCorpusError(
                f"Corpus file for {source.id!r} is missing at {path}; "
                "pass --download to fetch it over HTTPS."
            )
        download_source(corpus_dir, source)
    actual = sha256_of(path)
    if actual != source.sha256:
        raise QualityCorpusError(
            f"Corpus file for {source.id!r} has sha256 {actual}, expected "
            f"{source.sha256}; refusing to evaluate an unverified file."
        )
    return path


def download_source(corpus_dir: Path, source: Source) -> Path:
    executable = shutil.which("curl")
    if executable is None:
        raise QualityCorpusError("curl is required for --download")
    corpus_dir.mkdir(parents=True, exist_ok=True)
    final_path = corpus_dir / source.filename
    partial = corpus_dir / f"{source.filename}.part"
    partial.unlink(missing_ok=True)
    command = [
        executable,
        "--proto",
        "=https",
        "--tlsv1.2",
        "--fail",
        "--silent",
        "--show-error",
        "--max-time",
        str(DOWNLOAD_TIMEOUT_SECONDS),
        "--max-filesize",
        str(DOWNLOAD_MAX_BYTES),
        source.url,
        "--output",
        str(partial),
    ]
    try:
        completed = subprocess.run(  # nosec B603
            command,
            capture_output=True,
            check=False,
            timeout=DOWNLOAD_TIMEOUT_SECONDS + 15,
        )
    except subprocess.TimeoutExpired:
        partial.unlink(missing_ok=True)
        raise QualityCorpusError(f"Download of {source.id!r} timed out") from None
    if completed.returncode != 0 or not partial.is_file():
        partial.unlink(missing_ok=True)
        raise QualityCorpusError(
            f"Download of {source.id!r} failed (curl exit code {completed.returncode})"
        )
    actual = sha256_of(partial)
    if actual != source.sha256:
        partial.unlink(missing_ok=True)
        raise QualityCorpusError(
            f"Downloaded file for {source.id!r} has sha256 {actual}, expected "
            f"{source.sha256}; it was discarded."
        )
    partial.replace(final_path)
    return final_path


# --- tool probes ---------------------------------------------------------------


def _probe(command: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(  # nosec B603
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def pdfinfo_page_count(path: Path) -> int | None:
    """Page count reported by Poppler, or None when unavailable or unreadable."""
    executable = shutil.which("pdfinfo")
    if executable is None:
        return None
    completed = _probe([executable, str(path)])
    if completed is None or completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        label, _, value = line.partition(":")
        if label.strip() == "Pages":
            try:
                return int(value.strip())
            except ValueError:
                return None
    return None


def tool_versions() -> dict[str, str | None]:
    """First line of ``<tool> -v`` for reproducibility; never the full banner."""
    versions: dict[str, str | None] = {}
    for name in ("pdftotext", "pdfinfo"):
        executable = shutil.which(name)
        completed = _probe([executable, "-v"]) if executable else None
        if completed is None:
            versions[name] = None
            continue
        banner = (completed.stderr or completed.stdout).strip().splitlines()
        versions[name] = banner[0][:200] if banner else None
    return versions


# --- evaluation ----------------------------------------------------------------


def normalize_ws(text: str) -> str:
    return " ".join(text.split())


def evaluate_source(
    source: Source, path: Path
) -> tuple[dict[str, Any], list[OcrPage], list[ParsedBlock]]:
    pages = extract_text_backed_pdf_pages(path, EXTRACTION_TIMEOUT_SECONDS)
    document = MockAiAdapter().prepare_document(
        [(page.page_number, page.text) for page in pages]
    )
    numbers = [page.page_number for page in pages]
    identity_ok = len(set(numbers)) == len(numbers) and all(
        1 <= number <= source.pages for number in numbers
    )
    extracted_pages = set(numbers)
    block_identity_ok = all(
        block.page_number in extracted_pages for block in document.blocks
    )
    info_pages = pdfinfo_page_count(path)
    entry = {
        "id": source.id,
        "filename": source.filename,
        "sha256": source.sha256,
        "title": source.title,
        "license_url": source.license_url,
        "rights_note": source.rights_note,
        "expected_pages": source.pages,
        "text_pages": len(pages),
        "pdfinfo_pages": info_pages,
        "pdfinfo_pages_match_manifest": info_pages == source.pages,
        "page_identity_ok": identity_ok,
        "block_page_identity_ok": block_identity_ok,
        "block_count": len(document.blocks),
        "section_count": len(document.sections),
        "block_types": dict(Counter(block.block_type for block in document.blocks)),
        "scope": SCOPE,
        "semantics": None,
    }
    return entry, pages, list(document.blocks)


def evaluate_text_case(
    case: Case, pages: Sequence[OcrPage], blocks: Sequence[ParsedBlock]
) -> dict[str, Any]:
    page_text = next((page.text for page in pages if page.page_number == case.page), "")
    normalized = normalize_ws(page_text)
    missed = [
        anchor for anchor in case.anchors if normalize_ws(anchor) not in normalized
    ]
    positions: list[int] = []
    failed_passages: list[str] = []
    for passage in case.ordered_passages:
        index = normalized.find(normalize_ws(passage))
        if index == -1:
            failed_passages.append(passage)
        else:
            positions.append(index)
    in_order = positions == sorted(positions)
    page_lines = [line.split() for line in page_text.splitlines()]
    block_lines = [
        line.split()
        for block in blocks
        if block.page_number == case.page
        for line in block.source_text.splitlines()
    ]
    matched_rows = [row for row in case.rows if list(row) in page_lines]
    failed_rows = [list(row) for row in case.rows if list(row) not in page_lines]
    intact = [row for row in case.rows if list(row) in block_lines]
    failed_block_rows = [list(row) for row in case.rows if list(row) not in block_lines]
    # A missing page always fails; rows must also survive block splitting intact.
    all_passed = (
        bool(page_text)
        and not missed
        and not failed_passages
        and in_order
        and not failed_rows
        and not failed_block_rows
    )
    return {
        "id": case.id,
        "source_id": case.source_id,
        "page": case.page,
        "kind": "text",
        "scope": SCOPE,
        "semantics": None,
        "page_text_present": bool(page_text),
        "anchors": {
            "total": len(case.anchors),
            "hit": len(case.anchors) - len(missed),
            "missed": missed,
        },
        "ordered_passages": {
            "total": len(case.ordered_passages),
            "contiguous": len(case.ordered_passages) - len(failed_passages),
            "in_order": in_order,
            "failed": failed_passages,
        },
        "rows": {
            "total": len(case.rows),
            "matched": len(matched_rows),
            "failed": failed_rows,
            # Rows must survive Glyph's block splitting as one line; paragraph
            # blocks join lines, so this is where tables currently fail.
            "intact": len(intact),
            "failed_block_rows": failed_block_rows,
            "intact_in_blocks_ratio": (
                (len(intact) / len(case.rows)) if case.rows else None
            ),
        },
        "status": "all_checks_passed" if all_passed else "content_checks_failed",
    }


def evaluate_scan_case(case: Case, pdf_path: Path) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": case.id,
        "source_id": case.source_id,
        "page": case.page,
        "kind": "scan",
        "scope": SCOPE,
        "semantics": None,
        "ocr_quality": "not_evaluated",
    }
    executable = shutil.which("pdftoppm")
    if executable is None:
        entry["status"] = "render_unavailable"
        return entry
    with tempfile.TemporaryDirectory(prefix="glyph-quality-") as directory:
        prefix = Path(directory) / f"page-{case.page}"
        command = [
            executable,
            "-f",
            str(case.page),
            "-l",
            str(case.page),
            "-singlefile",
            "-r",
            "100",
            "-png",
            str(pdf_path),
            str(prefix),
        ]
        try:
            completed = subprocess.run(  # nosec B603
                command,
                capture_output=True,
                check=False,
                timeout=RENDER_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            entry["status"] = "render_timeout"
            return entry
        image = prefix.with_suffix(".png")
        if completed.returncode != 0 or not image.is_file():
            entry["status"] = "render_failed"
            return entry
        try:
            MockOcrAdapter().extract_pages(image)
        except OcrUnavailableError as exc:
            # Only the explicit "OCR required" refusal is the expected outcome;
            # any other adapter error is reported without its message.
            entry["status"] = (
                "blocked_no_ocr" if str(exc) == OCR_REQUIRED_MESSAGE else "ocr_error"
            )
        else:
            # The development adapter must never produce text for an image.
            entry["status"] = "unexpected_extraction"
    return entry


def run_quality(
    manifest_path: Path,
    corpus_dir: Path,
    output_path: Path,
    *,
    download: bool = False,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    # Verify every source before evaluating anything: a corrupted file must
    # never be extracted.
    paths = {
        source.id: ensure_source(corpus_dir, source, download=download)
        for source in manifest.sources
    }
    sources: list[dict[str, Any]] = []
    extracted: dict[str, tuple[list[OcrPage], list[ParsedBlock]]] = {}
    for source in manifest.sources:
        entry, pages, blocks = evaluate_source(source, paths[source.id])
        sources.append(entry)
        extracted[source.id] = (pages, blocks)
    cases: list[dict[str, Any]] = []
    for case in manifest.cases:
        if case.kind == "scan":
            cases.append(evaluate_scan_case(case, paths[case.source_id]))
        else:
            pages, blocks = extracted[case.source_id]
            cases.append(evaluate_text_case(case, pages, blocks))
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": SCOPE,
        "semantics": None,
        "note": (
            "Deterministic extraction checks only. Translation, summary, formula "
            "reconstruction and OCR quality are not evaluated by this run."
        ),
        "tools": tool_versions(),
        "sources": sources,
        "cases": cases,
        "summary": {
            "sources_total": len(sources),
            "cases_total": len(cases),
            "cases_all_checks_passed": sum(
                1 for case in cases if case["status"] == "all_checks_passed"
            ),
            "cases_blocked_no_ocr": sum(
                1 for case in cases if case["status"] == "blocked_no_ocr"
            ),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--corpus-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_quality(
            args.manifest, args.corpus_dir, args.output, download=args.download
        )
    except (QualityManifestError, QualityCorpusError) as exc:
        print(f"quality: {exc}", file=sys.stderr)
        return 2
    summary = report["summary"]
    print(
        f"quality: {summary['cases_total']} cases, "
        f"{summary['cases_all_checks_passed']} passed all structural checks, "
        f"{summary['cases_blocked_no_ocr']} blocked without OCR "
        f"(scope {SCOPE}; semantics not evaluated) -> {args.output}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
