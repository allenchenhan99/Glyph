import os
import sys

from glyph.config import Settings
from glyph.ocr import MockOcrAdapter, UnlimitedOcrAdapter


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
        unlimited_ocr_command=f"{sys.executable} {script} --input {{input}} --output_dir {{output_dir}}",
    )

    pages = UnlimitedOcrAdapter(settings).extract_pages(source)

    assert pages[0].page_number == 1
    assert pages[0].text == "# Parsed\n\nUnlimited OCR output"
