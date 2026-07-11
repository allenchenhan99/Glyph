from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from glyph.config import Settings


class OcrUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class OcrPage:
    page_number: int
    text: str
    image_path: str | None = None


class MockOcrAdapter:
    def extract_pages(self, source_path: Path) -> list[OcrPage]:
        if source_path.suffix.lower() == ".pdf":
            pdf_pages = extract_text_backed_pdf_pages(source_path)
            if pdf_pages:
                return pdf_pages

        try:
            text = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = ""
        text = text.replace("%PDF-1.4", "").strip()
        if not text:
            text = (
                "# Untitled\n\n"
                "OCR mock text extracted from an image-like source.\n\n"
                "1. Review this block."
            )
        return [OcrPage(page_number=1, text=text)]


class UnlimitedOcrAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def extract_pages(self, source_path: Path) -> list[OcrPage]:
        output_dir = self.settings.data_dir / "ocr" / f"{source_path.stem}-{uuid4().hex}"
        output_dir.mkdir(parents=True, exist_ok=True)
        if self.settings.unlimited_ocr_command:
            self._run_configured_command(source_path, output_dir)
        elif self.settings.unlimited_ocr_repo:
            self._run_repo_infer(source_path, output_dir)
        else:
            raise OcrUnavailableError(
                "Unlimited-OCR is selected but not configured. Set GLYPH_UNLIMITED_OCR_COMMAND "
                "or GLYPH_UNLIMITED_OCR_REPO before using GLYPH_OCR_MODE=unlimited_ocr."
            )
        return [OcrPage(page_number=1, text=read_markdown_output(output_dir))]

    def _run_configured_command(self, source_path: Path, output_dir: Path) -> None:
        assert self.settings.unlimited_ocr_command is not None
        command = self.settings.unlimited_ocr_command.format(
            input=shlex.quote(str(source_path)),
            output_dir=shlex.quote(str(output_dir)),
        )
        run_command(shlex.split(command), cwd=self.settings.unlimited_ocr_repo)

    def _run_repo_infer(self, source_path: Path, output_dir: Path) -> None:
        repo = self.settings.unlimited_ocr_repo
        if repo is None:
            raise OcrUnavailableError("GLYPH_UNLIMITED_OCR_REPO is not set.")
        infer_py = repo / "infer.py"
        if not infer_py.exists():
            raise OcrUnavailableError(f"Unlimited-OCR infer.py not found at {infer_py}")

        if source_path.suffix.lower() == ".pdf":
            run_command(
                [
                    sys.executable,
                    str(infer_py),
                    "--pdf",
                    str(source_path),
                    "--output_dir",
                    str(output_dir),
                    "--image_mode",
                    "base",
                ],
                cwd=repo,
            )
            return

        with tempfile.TemporaryDirectory(prefix="glyph_ocr_images_") as temp_dir:
            image_dir = Path(temp_dir)
            shutil.copy2(source_path, image_dir / source_path.name)
            run_command(
                [
                    sys.executable,
                    str(infer_py),
                    "--image_dir",
                    str(image_dir),
                    "--output_dir",
                    str(output_dir),
                    "--image_mode",
                    "gundam",
                ],
                cwd=repo,
            )


def create_ocr_adapter(settings: Settings) -> MockOcrAdapter | UnlimitedOcrAdapter:
    if settings.ocr_mode == "mock":
        return MockOcrAdapter()
    if settings.ocr_mode == "unlimited_ocr":
        return UnlimitedOcrAdapter(settings)
    raise OcrUnavailableError(f"Unknown OCR mode: {settings.ocr_mode}")


def extract_text_backed_pdf_pages(source_path: Path) -> list[OcrPage]:
    if shutil.which("pdftotext") is None:
        return []
    completed = subprocess.run(
        ["pdftotext", "-layout", str(source_path), "-"],
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        return []
    pages: list[OcrPage] = []
    for index, page_text in enumerate(completed.stdout.split("\f"), start=1):
        text = page_text.strip()
        if text:
            pages.append(OcrPage(page_number=index, text=text))
    return pages


def run_command(command: list[str], cwd: Path | None) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise OcrUnavailableError(
            "Unlimited-OCR command failed: "
            f"{completed.stderr.strip() or completed.stdout.strip() or completed.returncode}"
        )


def read_markdown_output(output_dir: Path) -> str:
    markdown_files = sorted(output_dir.rglob("*.md"), key=lambda path: path.stat().st_mtime)
    if not markdown_files:
        raise OcrUnavailableError(f"Unlimited-OCR produced no markdown output in {output_dir}")
    texts = [path.read_text(encoding="utf-8").strip() for path in markdown_files]
    text = "\n\n".join(part for part in texts if part)
    if not text:
        raise OcrUnavailableError("Unlimited-OCR produced empty markdown output.")
    return text
