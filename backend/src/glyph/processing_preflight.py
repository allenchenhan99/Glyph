"""Read-only readiness checks before a document is queued for processing.

Preflight inspects local configuration and the source file with bounded
subprocess calls. It never contacts a model provider and never claims that a
CLI or API key is authenticated; a run can still fail for account reasons.
"""

from __future__ import annotations

import shlex
import shutil

# pdfinfo runs with a resolved executable, fixed argv, no shell, and a timeout.
import subprocess  # nosec B404
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from glyph.config import Settings, resolve_translation_settings
from glyph.models import Document, ProcessingJob
from glyph.ocr import detect_source_kind, pdf_has_text
from glyph.orcarouter import INVALID_KEY_MESSAGE, is_valid_api_key

ACTIVE_JOB_STATUSES = ("queued", "running")


@dataclass(frozen=True)
class PreflightIssue:
    code: str
    severity: Literal["error", "warning"]
    message: str


@dataclass(frozen=True)
class PreflightResult:
    ready: bool
    source_type: str
    provider: str
    page_count: int | None
    issues: tuple[PreflightIssue, ...] = field(default_factory=tuple)

    @property
    def blockers(self) -> tuple[PreflightIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")


def run_preflight(
    session: Session, settings: Settings, document: Document
) -> PreflightResult:
    issues: list[PreflightIssue] = []
    source_path = Path(document.source_path)
    kind = detect_source_kind(source_path)
    page_count: int | None = None
    timeout = settings.page_render_timeout_seconds

    if kind == "missing":
        issues.append(
            PreflightIssue(
                "source_missing",
                "error",
                "The source file is missing. Restore it at its original path "
                "or upload the document again.",
            )
        )
    elif kind == "pdf":
        page_count, readable = inspect_pdf(source_path, timeout, issues)
        if readable:
            check_pdf_extraction(source_path, settings, timeout, issues)
    elif kind == "image":
        page_count = 1
        check_ocr_configuration(settings, issues, required=True)
    elif kind == "text":
        if settings.ocr_mode == "mock":
            issues.append(
                PreflightIssue(
                    "development_fixture",
                    "warning",
                    "This file is plain text, not a PDF or image. It is read as a "
                    "development fixture by the mock OCR mode.",
                )
            )
        else:
            issues.append(
                PreflightIssue(
                    "development_fixture",
                    "error",
                    "Plain-text fixtures are only supported with "
                    "GLYPH_OCR_MODE=mock; the selected OCR adapter cannot read them.",
                )
            )
    else:
        issues.append(
            PreflightIssue(
                "source_unreadable",
                "error",
                "The file is not a readable PDF, image or text document. It may "
                "be damaged; export it again and re-upload.",
            )
        )

    provider = check_translation_provider(settings, issues)
    check_active_job(session, document, issues)
    ready = not any(issue.severity == "error" for issue in issues)
    return PreflightResult(
        ready=ready,
        source_type=kind if kind != "missing" else document.file_type or "unknown",
        provider=provider,
        page_count=page_count,
        issues=tuple(issues),
    )


class PdfUnreadableError(RuntimeError):
    """pdfinfo could not read the file within the bounded timeout."""


def inspect_pdf(
    source_path: Path, timeout: int, issues: list[PreflightIssue]
) -> tuple[int | None, bool]:
    """Return (page_count, readable). Poppler is optional but bounded when used."""
    try:
        return pdf_page_count(source_path, timeout), True
    except PdfUnreadableError as exc:
        issues.append(PreflightIssue("pdf_unreadable", "error", str(exc)))
        return None, False


def pdf_page_count(source_path: Path, timeout: int) -> int | None:
    executable = shutil.which("pdfinfo")
    if executable is None:
        return None
    try:
        completed = subprocess.run(  # nosec B603
            [executable, str(source_path)],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise PdfUnreadableError(
            f"The PDF could not be inspected within {timeout} seconds. "
            "It may be damaged or unusually large."
        ) from exc
    if completed.returncode != 0:
        raise PdfUnreadableError(
            "The PDF could not be read. It may be damaged or password-protected; "
            "export an unlocked copy and try again."
        )
    for line in completed.stdout.splitlines():
        label, _, value = line.partition(":")
        if label.strip() == "Pages":
            try:
                return int(value.strip())
            except ValueError:
                return None
    return None


def check_pdf_extraction(
    source_path: Path,
    settings: Settings,
    timeout: int,
    issues: list[PreflightIssue],
) -> None:
    if shutil.which("pdftotext") is None:
        issues.append(
            PreflightIssue(
                "poppler_missing",
                "warning" if settings.ocr_mode != "mock" else "error",
                "Poppler (pdftotext) is not installed, so text cannot be extracted "
                "from PDFs. Install Poppler or configure OCR.",
            )
        )
        if settings.ocr_mode != "mock":
            check_ocr_configuration(settings, issues, required=True)
        return
    # The selected OCR adapter handles every PDF, so its configuration must be
    # valid even when a text layer exists; only the mock may skip OCR entirely.
    check_ocr_configuration(
        settings, issues, required=not pdf_has_text(source_path, timeout)
    )


def check_ocr_configuration(
    settings: Settings, issues: list[PreflightIssue], *, required: bool
) -> None:
    if settings.ocr_mode == "mock":
        if required:
            issues.append(
                PreflightIssue(
                    "ocr_required",
                    "error",
                    "This file needs OCR, and the development mock does not read "
                    "images or scanned pages. Set GLYPH_OCR_MODE=unlimited_ocr and "
                    "configure Unlimited-OCR before processing it.",
                )
            )
        return
    if settings.ocr_mode == "unlimited_ocr":
        problem = unlimited_ocr_problem(settings)
        if problem is not None:
            issues.append(PreflightIssue("ocr_unconfigured", "error", problem))
        return
    issues.append(
        PreflightIssue(
            "ocr_unconfigured",
            "error",
            f"Unknown GLYPH_OCR_MODE '{settings.ocr_mode}'. Use mock or unlimited_ocr.",
        )
    )


def unlimited_ocr_problem(settings: Settings) -> str | None:
    """Validate Unlimited-OCR configuration locally without running it."""
    repo = settings.unlimited_ocr_repo
    if repo is not None and not repo.is_dir():
        return (
            f"GLYPH_UNLIMITED_OCR_REPO does not point to a directory: {repo}. "
            "Check the path before processing scanned documents."
        )
    command = settings.unlimited_ocr_command
    if command:
        try:
            parts = shlex.split(command.format(input="input", output_dir="output"))
        except (ValueError, KeyError, IndexError):
            return "GLYPH_UNLIMITED_OCR_COMMAND could not be parsed as a command line."
        if not parts:
            return "GLYPH_UNLIMITED_OCR_COMMAND is empty."
        if shutil.which(parts[0]) is None:
            return (
                f"The Unlimited-OCR command '{parts[0]}' is not installed or "
                "executable. Install it or fix GLYPH_UNLIMITED_OCR_COMMAND."
            )
        return None
    if repo is None:
        return (
            "GLYPH_OCR_MODE=unlimited_ocr is selected but neither "
            "GLYPH_UNLIMITED_OCR_COMMAND nor GLYPH_UNLIMITED_OCR_REPO is set."
        )
    if not (repo / "infer.py").is_file():
        return (
            "Unlimited-OCR infer.py was not found in GLYPH_UNLIMITED_OCR_REPO. "
            "Clone the upstream repository there before processing."
        )
    return None


def check_translation_provider(settings: Settings, issues: list[PreflightIssue]) -> str:
    translation = resolve_translation_settings(settings)
    provider = translation.provider
    if provider == "mock":
        issues.append(
            PreflightIssue(
                "mock_translation",
                "warning",
                "Translation uses the deterministic development mock, not a real "
                "model. Choose a provider in Translation settings for real output.",
            )
        )
    elif provider in {"claude_cli", "codex_cli"}:
        executable = provider.removesuffix("_cli")
        if shutil.which(executable) is None:
            issues.append(
                PreflightIssue(
                    "provider_cli_missing",
                    "error",
                    f"The {executable} CLI is not on PATH. Install and authenticate "
                    "it, or choose another provider in Translation settings.",
                )
            )
        else:
            issues.append(
                PreflightIssue(
                    "provider_unverified",
                    "warning",
                    f"The {executable} CLI is installed, but Glyph cannot verify "
                    "that it is authenticated. A run fails with the CLI error if "
                    "it is not.",
                )
            )
    elif provider == "orcarouter":
        if not translation.api_key or not translation.model:
            issues.append(
                PreflightIssue(
                    "orcarouter_unconfigured",
                    "error",
                    "OrcaRouter needs a model ID and your API key. Enter both in "
                    "Translation settings or in the environment.",
                )
            )
        elif not is_valid_api_key(translation.api_key):
            issues.append(
                PreflightIssue("orcarouter_key_invalid", "error", INVALID_KEY_MESSAGE)
            )
        else:
            issues.append(
                PreflightIssue(
                    "provider_unverified",
                    "warning",
                    "The OrcaRouter key and model are not verified before the run; "
                    "no request is made by preflight. Usage is billed to your "
                    "account.",
                )
            )
    return provider


def check_active_job(
    session: Session, document: Document, issues: list[PreflightIssue]
) -> None:
    active = session.scalar(
        select(ProcessingJob.id).where(
            ProcessingJob.document_id == document.id,
            ProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
        )
    )
    if active is not None:
        issues.append(
            PreflightIssue(
                "job_active",
                "error",
                "This document is already queued or processing. Wait for that "
                "job to finish or cancel it first.",
            )
        )
