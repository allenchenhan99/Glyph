import os
import shlex
import subprocess
import sys

import pytest

from glyph.config import Settings
from glyph.ocr import (
    MockOcrAdapter,
    OcrUnavailableError,
    UnlimitedOcrAdapter,
    create_ocr_adapter,
)


def test_mock_ocr_extracts_text_backed_pdf_with_pdftotext(tmp_path, monkeypatch):
    fake_pdftotext = tmp_path / "pdftotext"
    fake_pdftotext.write_text(
        "#!/usr/bin/env python3\n"
        "print('# Real PDF Title')\n"
        "print()\n"
        "print('This is embedded PDF text, not fallback text.')\n"
    )
    fake_pdftotext.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4\n\xff\xfe binary pdf")

    pages = MockOcrAdapter().extract_pages(source)

    assert (
        pages[0].text
        == "# Real PDF Title\n\nThis is embedded PDF text, not fallback text."
    )


def test_mock_ocr_splits_text_backed_pdf_by_form_feed_pages(tmp_path, monkeypatch):
    fake_pdftotext = tmp_path / "pdftotext"
    fake_pdftotext.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stdout.write('Page one text\\fPage two formula\\nE = mc^2\\f')\n"
    )
    fake_pdftotext.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4\n\xff\xfe binary pdf")

    pages = MockOcrAdapter().extract_pages(source)

    assert [(page.page_number, page.text) for page in pages] == [
        (1, "Page one text"),
        (2, "Page two formula\nE = mc^2"),
    ]


def test_unlimited_ocr_adapter_runs_configured_command_and_reads_markdown(tmp_path):
    script = tmp_path / "fake_unlimited_ocr.py"
    script.write_text(
        "import argparse\n"
        "from pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--input')\n"
        "parser.add_argument('--output_dir')\n"
        "args = parser.parse_args()\n"
        "Path(args.output_dir).mkdir(parents=True, exist_ok=True)\n"
        "Path(args.output_dir, 'result.md').write_text('# Parsed\\n\\nUnlimited OCR output')\n"
    )
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4")
    settings = Settings(
        book_dir=tmp_path / "book",
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{tmp_path / 'data' / 'glyph.sqlite3'}",
        ocr_mode="unlimited_ocr",
        ai_mode="mock",
        unlimited_ocr_repo=None,
        unlimited_ocr_command=(
            f"{shlex.quote(sys.executable)} {shlex.quote(str(script))} "
            "--input {input} --output_dir {output_dir}"
        ),
    )

    pages = UnlimitedOcrAdapter(settings).extract_pages(source)

    assert pages[0].page_number == 1
    assert pages[0].text == "# Parsed\n\nUnlimited OCR output"


def test_text_pdf_extraction_uses_resolved_executable_and_timeout(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4\n\xff\xfe binary pdf")
    observed = {}

    monkeypatch.setattr(
        "glyph.ocr.shutil.which", lambda executable: f"/opt/poppler/{executable}"
    )

    def timeout_when_bounded(command, **kwargs):
        observed["command"] = command
        observed["timeout"] = kwargs.get("timeout")
        if kwargs.get("timeout") is None:
            return subprocess.CompletedProcess(command, 1, "", "missing timeout")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("glyph.ocr.subprocess.run", timeout_when_bounded)
    settings = Settings(
        book_dir=tmp_path / "book",
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{tmp_path / 'data' / 'glyph.sqlite3'}",
        ocr_mode="mock",
        ai_mode="mock",
        unlimited_ocr_repo=None,
        unlimited_ocr_command=None,
        ocr_timeout_seconds=7,
    )

    with pytest.raises(
        OcrUnavailableError, match="PDF text extraction timed out after 7 seconds"
    ) as error:
        create_ocr_adapter(settings).extract_pages(source)

    assert observed == {
        "command": ["/opt/poppler/pdftotext", "-layout", str(source), "-"],
        "timeout": 7,
    }
    assert str(source) not in str(error.value)


def test_unlimited_ocr_uses_timeout_and_resolved_executable(tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4")
    observed = {}

    monkeypatch.setattr(
        "glyph.ocr.shutil.which", lambda executable: f"/opt/bin/{executable}"
    )

    def timeout_when_bounded(command, **kwargs):
        observed["command"] = command
        observed["timeout"] = kwargs.get("timeout")
        if kwargs.get("timeout") is None:
            return subprocess.CompletedProcess(command, 1, "", "missing timeout")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("glyph.ocr.subprocess.run", timeout_when_bounded)
    settings = Settings(
        book_dir=tmp_path / "book",
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{tmp_path / 'data' / 'glyph.sqlite3'}",
        ocr_mode="unlimited_ocr",
        ai_mode="mock",
        unlimited_ocr_repo=None,
        unlimited_ocr_command="fake-ocr --input {input} --output_dir {output_dir}",
        ocr_timeout_seconds=11,
    )

    with pytest.raises(
        OcrUnavailableError, match="Unlimited-OCR timed out after 11 seconds"
    ):
        UnlimitedOcrAdapter(settings).extract_pages(source)

    assert observed["command"][0] == "/opt/bin/fake-ocr"
    assert observed["timeout"] == 11


def test_unlimited_ocr_failure_does_not_expose_tool_output(tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr("glyph.ocr.shutil.which", lambda executable: executable)
    monkeypatch.setattr(
        "glyph.ocr.subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            2,
            "",
            f"private source: {source} " + "x" * 1000,
        ),
    )
    settings = Settings(
        book_dir=tmp_path / "book",
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{tmp_path / 'data' / 'glyph.sqlite3'}",
        ocr_mode="unlimited_ocr",
        ai_mode="mock",
        unlimited_ocr_repo=None,
        unlimited_ocr_command="fake-ocr --input {input} --output_dir {output_dir}",
    )

    with pytest.raises(OcrUnavailableError) as error:
        UnlimitedOcrAdapter(settings).extract_pages(source)

    assert str(error.value) == "Unlimited-OCR command failed with exit code 2"
    assert str(source) not in str(error.value)


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("scan.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16),
        ("photo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 16),
    ],
)
def test_mock_ocr_refuses_to_fabricate_text_for_real_images(tmp_path, name, content):
    source = tmp_path / name
    source.write_bytes(content)
    with pytest.raises(OcrUnavailableError, match="OCR"):
        MockOcrAdapter().extract_pages(source)


def test_mock_ocr_refuses_scanned_pdf_without_extractable_text(tmp_path, monkeypatch):
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF-1.4\n\xff\xfe binary pdf")
    monkeypatch.setattr("glyph.ocr.extract_text_backed_pdf_pages", lambda *a, **k: [])
    with pytest.raises(OcrUnavailableError, match="OCR"):
        MockOcrAdapter().extract_pages(source)


def test_mock_ocr_reads_development_text_fixtures_but_not_empty_files(tmp_path):
    fixture = tmp_path / "fixture.pdf"
    fixture.write_text("# Heading\n\nBody.")
    assert MockOcrAdapter().extract_pages(fixture)[0].text == "# Heading\n\nBody."
    empty = tmp_path / "empty.pdf"
    empty.write_text("")
    with pytest.raises(OcrUnavailableError):
        MockOcrAdapter().extract_pages(empty)


def test_mock_ocr_rejects_unrecognized_binary_content(tmp_path):
    damaged = tmp_path / "damaged.pdf"
    damaged.write_bytes(b"\x00\x01garbage\xff\xfe")
    with pytest.raises(OcrUnavailableError, match="not a readable"):
        MockOcrAdapter().extract_pages(damaged)
