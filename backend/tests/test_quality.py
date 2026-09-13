from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from glyph import quality
from glyph.ocr import OcrPage
from glyph.quality import (
    QualityCorpusError,
    QualityManifestError,
    main,
    run_quality,
)

PAGE_ONE = (
    "Guidelines for Evaluating Uncertainty\n"
    "The four-step procedure for calculating kp is as follows.\n"
    "Obtain y and uc(y) as indicated in Appendix A.\n"
    "\n"
    "Degrees of    Fraction p in percent\n"
    "1 1.84 6.31 12.71\n"
    "2 1.32 2.92 4.30\n"
)
PAGE_TWO = (
    "Left column first sentence here.   Right column starts here.\n"
    "Left column second sentence.       Right column continues.\n"
)


def write_pdf_stub(path: Path, content: bytes = b"%PDF-1.4\n%stub\n") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def manifest(
    tmp_path: Path,
    *,
    sha256: str,
    filename: str = "paper.pdf",
    cases=None,
    url="https://example.org/paper.pdf",
) -> Path:
    payload = {
        "schema_version": 1,
        "sources": [
            {
                "id": "paper",
                "filename": filename,
                "url": url,
                "sha256": sha256,
                "pages": 2,
                "title": "Public paper",
                "license_url": "https://example.org/license",
                "rights_note": "public domain",
            }
        ],
        "cases": cases
        if cases is not None
        else [
            {
                "id": "p1-text",
                "source_id": "paper",
                "page": 1,
                "kind": "text",
                "anchors": [
                    "four-step   procedure",
                    "Fraction p in percent",
                    "not on this page",
                ],
                "ordered_passages": ["Obtain y and uc(y) as indicated in Appendix A."],
                "rows": [["1", "1.84", "6.31", "12.71"], ["2", "1.32", "2.92", "4.31"]],
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload))
    return path


def stub_tools(monkeypatch, pages: int | None = 2):
    monkeypatch.setattr(quality, "pdfinfo_page_count", lambda path: pages)
    monkeypatch.setattr(
        quality, "tool_versions", lambda: {"pdftotext": "stub", "pdfinfo": "stub"}
    )


def stub_extraction(monkeypatch, pages=None, calls=None):
    stub_tools(monkeypatch)

    def fake(path, timeout_seconds=300):
        if calls is not None:
            calls.append(path)
        return (
            pages if pages is not None else [OcrPage(1, PAGE_ONE), OcrPage(2, PAGE_TWO)]
        )

    monkeypatch.setattr(quality, "extract_text_backed_pdf_pages", fake)


def test_corrupted_hash_fails_before_any_extraction(tmp_path, monkeypatch):
    write_pdf_stub(tmp_path / "corpus" / "paper.pdf")
    calls: list[Path] = []
    stub_extraction(monkeypatch, calls=calls)
    path = manifest(tmp_path, sha256="0" * 64)
    with pytest.raises(QualityCorpusError, match="sha256"):
        run_quality(path, tmp_path / "corpus", tmp_path / "report.json")
    assert calls == []
    assert not (tmp_path / "report.json").exists()
    assert (
        main(
            [
                "--manifest",
                str(path),
                "--corpus-dir",
                str(tmp_path / "corpus"),
                "--output",
                str(tmp_path / "report.json"),
            ]
        )
        == 2
    )


def test_missing_source_is_an_error_not_a_skip(tmp_path, monkeypatch):
    stub_extraction(monkeypatch)
    path = manifest(tmp_path, sha256="a" * 64)
    with pytest.raises(QualityCorpusError, match="missing"):
        run_quality(path, tmp_path / "corpus", tmp_path / "report.json")


@pytest.mark.parametrize(
    "filename", ["../paper.pdf", "sub/paper.pdf", "/etc/paper.pdf", "paper.txt", ""]
)
def test_unsafe_or_non_pdf_filenames_are_rejected(tmp_path, monkeypatch, filename):
    stub_extraction(monkeypatch)
    path = manifest(tmp_path, sha256="a" * 64, filename=filename)
    with pytest.raises(QualityManifestError, match="filename"):
        run_quality(path, tmp_path / "corpus", tmp_path / "report.json")


@pytest.mark.parametrize(
    "bad",
    [
        {"schema_version": 2, "sources": [], "cases": []},
        {"sources": []},
        {
            "schema_version": 1,
            "sources": [],
            "cases": [{"id": "x", "source_id": "nope", "page": 1, "kind": "text"}],
        },
        {
            "schema_version": 1,
            "sources": [],
            "cases": [{"id": "x", "source_id": "p", "page": 1, "kind": "video"}],
        },
    ],
)
def test_manifest_schema_is_validated(tmp_path, bad):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(QualityManifestError):
        run_quality(path, tmp_path / "corpus", tmp_path / "report.json")


def test_download_is_explicit_https_bounded_and_hash_gated(tmp_path, monkeypatch):
    content = b"%PDF-1.4\n%downloaded\n"
    digest = hashlib.sha256(content).hexdigest()
    stub_extraction(monkeypatch)
    invocations: list[list[str]] = []

    def fake_curl(command, **kwargs):
        invocations.append(list(command))
        assert kwargs.get("timeout")
        Path(command[-1]).write_bytes(content)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(quality.subprocess, "run", fake_curl)
    path = manifest(tmp_path, sha256=digest)
    corpus = tmp_path / "corpus"

    # Without --download nothing is fetched.
    with pytest.raises(QualityCorpusError):
        run_quality(path, corpus, tmp_path / "report.json")
    assert invocations == []

    run_quality(path, corpus, tmp_path / "report.json", download=True)
    assert (corpus / "paper.pdf").read_bytes() == content
    command = invocations[0]
    assert command[0].endswith("curl")
    assert "--max-time" in command and command[command.index("--max-time") + 1] == "60"
    assert "--max-filesize" in command and command[
        command.index("--max-filesize") + 1
    ] == str(10 * 1024 * 1024)
    assert "--proto" in command and command[command.index("--proto") + 1] == "=https"
    assert "-L" not in command and "--location" not in command
    assert "https://example.org/paper.pdf" in command
    assert not list(corpus.glob("*.part"))


def test_download_with_wrong_hash_leaves_no_file(tmp_path, monkeypatch):
    stub_extraction(monkeypatch)

    def fake_curl(command, **kwargs):
        Path(command[-1]).write_bytes(b"%PDF-1.4\n%tampered\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(quality.subprocess, "run", fake_curl)
    path = manifest(tmp_path, sha256="b" * 64)
    corpus = tmp_path / "corpus"
    with pytest.raises(QualityCorpusError, match="sha256"):
        run_quality(path, corpus, tmp_path / "report.json", download=True)
    assert not (corpus / "paper.pdf").exists()
    assert not list(corpus.glob("*")) or not any(
        p.suffix == ".pdf" for p in corpus.iterdir()
    )


def test_download_rejects_non_https_urls_before_running_curl(tmp_path, monkeypatch):
    stub_extraction(monkeypatch)
    invocations: list[list[str]] = []
    monkeypatch.setattr(
        quality.subprocess,
        "run",
        lambda command, **kwargs: invocations.append(list(command)),
    )
    path = manifest(tmp_path, sha256="c" * 64, url="http://example.org/paper.pdf")
    with pytest.raises(QualityManifestError, match="https"):
        run_quality(path, tmp_path / "corpus", tmp_path / "report.json", download=True)
    assert invocations == []


def test_text_case_metrics_are_structural_and_honest(tmp_path, monkeypatch):
    digest = write_pdf_stub(tmp_path / "corpus" / "paper.pdf")
    stub_extraction(monkeypatch)
    path = manifest(tmp_path, sha256=digest)
    report_path = tmp_path / "report.json"
    assert (
        main(
            [
                "--manifest",
                str(path),
                "--corpus-dir",
                str(tmp_path / "corpus"),
                "--output",
                str(report_path),
            ]
        )
        == 0
    )
    report = json.loads(report_path.read_text())
    assert report["schema_version"] == 1
    assert report["scope"] == "deterministic/extraction_only"
    assert report["semantics"] is None
    source = report["sources"][0]
    assert source["id"] == "paper"
    assert source["expected_pages"] == 2
    assert source["text_pages"] == 2
    assert source["page_identity_ok"] is True
    assert source["block_count"] > 0
    assert source["section_count"] >= 1
    assert isinstance(source["block_types"], dict)
    assert "sha256" in source and source["sha256"] == digest

    case = report["cases"][0]
    assert case["scope"] == "deterministic/extraction_only"
    assert case["semantics"] is None
    assert case["kind"] == "text"
    assert case["anchors"] == {"total": 3, "hit": 2, "missed": ["not on this page"]}
    assert case["ordered_passages"] == {
        "total": 1,
        "contiguous": 1,
        "in_order": True,
        "failed": [],
    }
    assert case["rows"]["total"] == 2
    assert case["rows"]["matched"] == 1
    assert case["rows"]["failed"] == [["2", "1.32", "2.92", "4.31"]]
    assert 0.0 <= case["rows"]["intact_in_blocks_ratio"] <= 1.0
    assert case["status"] == "content_checks_failed"
    assert report["summary"]["cases_total"] == 1
    assert report["summary"]["cases_all_checks_passed"] == 0


def test_cross_column_sentence_and_near_miss_rows_fail(tmp_path, monkeypatch):
    digest = write_pdf_stub(tmp_path / "corpus" / "paper.pdf")
    stub_extraction(monkeypatch)
    cases = [
        {
            "id": "p2-columns",
            "source_id": "paper",
            "page": 2,
            "kind": "text",
            "anchors": ["Left column first sentence here."],
            "ordered_passages": [
                "Left column first sentence here. Left column second sentence.",
                "Right column starts here.",
            ],
            "rows": [],
        }
    ]
    path = manifest(tmp_path, sha256=digest, cases=cases)
    run_quality(path, tmp_path / "corpus", tmp_path / "report.json")
    case = json.loads((tmp_path / "report.json").read_text())["cases"][0]
    assert case["anchors"]["hit"] == 1
    assert case["ordered_passages"]["contiguous"] == 1
    assert case["ordered_passages"]["failed"] == [
        "Left column first sentence here. Left column second sentence."
    ]
    assert case["status"] == "content_checks_failed"


def test_rows_intact_in_blocks_reflects_parsed_block_line_preservation(
    tmp_path, monkeypatch
):
    digest = write_pdf_stub(tmp_path / "corpus" / "paper.pdf")
    formula_page = "x = 1\n1 1.84 6.31\n"
    stub_extraction(
        monkeypatch,
        pages=[OcrPage(1, formula_page), OcrPage(2, "Prose line one.\n1 1.84 6.31\n")],
    )
    cases = [
        {
            "id": "kept",
            "source_id": "paper",
            "page": 1,
            "kind": "text",
            "anchors": [],
            "ordered_passages": [],
            "rows": [["1", "1.84", "6.31"]],
        },
        {
            "id": "joined",
            "source_id": "paper",
            "page": 2,
            "kind": "text",
            "anchors": [],
            "ordered_passages": [],
            "rows": [["1", "1.84", "6.31"]],
        },
    ]
    path = manifest(tmp_path, sha256=digest, cases=cases)
    run_quality(path, tmp_path / "corpus", tmp_path / "report.json")
    report = json.loads((tmp_path / "report.json").read_text())
    kept, joined = report["cases"]
    assert kept["rows"]["matched"] == 1 and joined["rows"]["matched"] == 1
    assert kept["rows"]["intact_in_blocks_ratio"] == 1.0
    assert joined["rows"]["intact_in_blocks_ratio"] == 0.0
    assert kept["rows"]["intact"] == 1 and kept["rows"]["failed_block_rows"] == []
    assert joined["rows"]["intact"] == 0 and joined["rows"]["failed_block_rows"] == [
        ["1", "1.84", "6.31"]
    ]
    assert kept["status"] == "all_checks_passed"
    assert joined["status"] == "content_checks_failed"


def test_scan_case_renders_one_page_and_reports_ocr_required_without_fake_text(
    tmp_path, monkeypatch
):
    digest = write_pdf_stub(tmp_path / "corpus" / "paper.pdf")
    stub_extraction(monkeypatch)
    rendered: list[list[str]] = []

    def fake_pdftoppm(command, **kwargs):
        rendered.append(list(command))
        assert kwargs.get("timeout")
        Path(command[-1] + ".png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(quality.subprocess, "run", fake_pdftoppm)
    monkeypatch.setattr(quality.shutil, "which", lambda name: f"/usr/bin/{name}")
    cases = [
        {
            "id": "p2-scan",
            "source_id": "paper",
            "page": 2,
            "kind": "scan",
            "anchors": ["never used"],
            "ordered_passages": [],
            "rows": [],
        }
    ]
    path = manifest(tmp_path, sha256=digest, cases=cases)
    assert (
        main(
            [
                "--manifest",
                str(path),
                "--corpus-dir",
                str(tmp_path / "corpus"),
                "--output",
                str(tmp_path / "report.json"),
            ]
        )
        == 0
    )
    case = json.loads((tmp_path / "report.json").read_text())["cases"][0]
    assert case["kind"] == "scan"
    assert case["status"] == "blocked_no_ocr"
    assert case["ocr_quality"] == "not_evaluated"
    assert case["semantics"] is None
    assert "text" not in case
    command = rendered[0]
    assert command[1:5] == ["-f", "2", "-l", "2"]
    assert "-singlefile" in command and "-png" in command
    assert command[command.index("-r") + 1] == "100"
    assert not list(tmp_path.rglob("*.png"))


def test_scan_case_reports_unexpected_mock_text_as_not_a_pass(tmp_path, monkeypatch):
    digest = write_pdf_stub(tmp_path / "corpus" / "paper.pdf")
    stub_extraction(monkeypatch)

    def fake_pdftoppm(command, **kwargs):
        Path(command[-1] + ".png").write_text("plain text pretending to be an image")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(quality.subprocess, "run", fake_pdftoppm)
    monkeypatch.setattr(quality.shutil, "which", lambda name: f"/usr/bin/{name}")
    cases = [
        {
            "id": "p1-scan",
            "source_id": "paper",
            "page": 1,
            "kind": "scan",
            "anchors": [],
            "ordered_passages": [],
            "rows": [],
        }
    ]
    path = manifest(tmp_path, sha256=digest, cases=cases)
    run_quality(path, tmp_path / "corpus", tmp_path / "report.json")
    case = json.loads((tmp_path / "report.json").read_text())["cases"][0]
    assert case["status"] == "unexpected_extraction"
    assert case["ocr_quality"] == "not_evaluated"


def test_runner_never_imports_application_settings_or_database():
    source = Path(quality.__file__).read_text()
    for forbidden in (
        "glyph.main",
        "glyph.config",
        "glyph.database",
        "create_ai_adapter",
        "cli_ai",
    ):
        assert forbidden not in source


def test_missing_page_always_fails_even_without_checks(tmp_path, monkeypatch):
    digest = write_pdf_stub(tmp_path / "corpus" / "paper.pdf")
    stub_extraction(monkeypatch)
    cases = [
        {
            "id": "p2-empty",
            "source_id": "paper",
            "page": 2,
            "kind": "text",
            "anchors": [],
            "ordered_passages": [],
            "rows": [],
        }
    ]
    path = manifest(tmp_path, sha256=digest, cases=cases)
    stub_extraction(monkeypatch, pages=[OcrPage(1, PAGE_ONE)])
    run_quality(path, tmp_path / "corpus", tmp_path / "report.json")
    case = json.loads((tmp_path / "report.json").read_text())["cases"][0]
    assert case["page_text_present"] is False
    assert case["status"] == "content_checks_failed"


@pytest.mark.parametrize(
    "override",
    [
        {"anchors": None},
        {"anchors": "single string"},
        {"ordered_passages": "single string"},
        {"rows": "1 1.84"},
        {"rows": [["1"], "1 1.84"]},
        {"page": 3},
    ],
)
def test_case_fields_are_type_and_range_checked(tmp_path, monkeypatch, override):
    stub_extraction(monkeypatch)
    case = {
        "id": "p1",
        "source_id": "paper",
        "page": 1,
        "kind": "text",
        "anchors": [],
        "ordered_passages": [],
        "rows": [],
    }
    case.update(override)
    path = manifest(tmp_path, sha256="a" * 64, cases=[case])
    with pytest.raises(QualityManifestError):
        run_quality(path, tmp_path / "corpus", tmp_path / "report.json")


def test_case_ids_must_be_unique(tmp_path, monkeypatch):
    stub_extraction(monkeypatch)
    case = {
        "id": "dup",
        "source_id": "paper",
        "page": 1,
        "kind": "text",
        "anchors": [],
        "ordered_passages": [],
        "rows": [],
    }
    path = manifest(tmp_path, sha256="a" * 64, cases=[case, dict(case)])
    with pytest.raises(QualityManifestError, match="unique"):
        run_quality(path, tmp_path / "corpus", tmp_path / "report.json")


def test_scan_case_counts_only_the_ocr_required_error_as_blocked(tmp_path, monkeypatch):
    from glyph.ocr import OcrUnavailableError

    digest = write_pdf_stub(tmp_path / "corpus" / "paper.pdf")
    stub_extraction(monkeypatch)

    def fake_pdftoppm(command, **kwargs):
        Path(command[-1] + ".png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        return subprocess.CompletedProcess(command, 0)

    class OtherFailure:
        def extract_pages(self, path):
            raise OcrUnavailableError("Source file is missing.")

    monkeypatch.setattr(quality.subprocess, "run", fake_pdftoppm)
    monkeypatch.setattr(quality.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(quality, "MockOcrAdapter", OtherFailure)
    cases = [
        {
            "id": "p1-scan",
            "source_id": "paper",
            "page": 1,
            "kind": "scan",
            "anchors": [],
            "ordered_passages": [],
            "rows": [],
        }
    ]
    path = manifest(tmp_path, sha256=digest, cases=cases)
    run_quality(path, tmp_path / "corpus", tmp_path / "report.json")
    case = json.loads((tmp_path / "report.json").read_text())["cases"][0]
    assert case["status"] == "ocr_error"
    assert case["ocr_quality"] == "not_evaluated"
    assert "missing" not in json.dumps(case)


def test_source_entry_records_block_page_identity_pdfinfo_and_tool_versions(
    tmp_path, monkeypatch
):
    digest = write_pdf_stub(tmp_path / "corpus" / "paper.pdf")
    stub_extraction(monkeypatch)
    monkeypatch.setattr(quality, "pdfinfo_page_count", lambda path: 3)
    monkeypatch.setattr(
        quality,
        "tool_versions",
        lambda: {
            "pdftotext": "pdftotext version 24.0",
            "pdfinfo": "pdfinfo version 24.0",
        },
    )
    path = manifest(tmp_path, sha256=digest, cases=[])
    report = run_quality(path, tmp_path / "corpus", tmp_path / "report.json")
    source = report["sources"][0]
    assert source["block_page_identity_ok"] is True
    assert source["pdfinfo_pages"] == 3
    assert source["pdfinfo_pages_match_manifest"] is False
    assert report["tools"] == {
        "pdftotext": "pdftotext version 24.0",
        "pdfinfo": "pdfinfo version 24.0",
    }


def test_pdfinfo_probe_is_bounded_and_tolerates_failure(tmp_path, monkeypatch):
    observed: list[tuple[list[str], float | None]] = []

    def fake_run(command, **kwargs):
        observed.append((list(command), kwargs.get("timeout")))
        if command[0].endswith("pdfinfo") and "-v" not in command:
            return subprocess.CompletedProcess(
                command, 0, stdout="Title: x\nPages:          7\n", stderr=""
            )
        return subprocess.CompletedProcess(
            command, 0, stdout="", stderr="pdftotext version 24.0\nCopyright\n"
        )

    monkeypatch.setattr(quality.subprocess, "run", fake_run)
    monkeypatch.setattr(quality.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert quality.pdfinfo_page_count(tmp_path / "x.pdf") == 7
    assert quality.tool_versions()["pdftotext"] == "pdftotext version 24.0"
    assert all(timeout for _, timeout in observed)
    monkeypatch.setattr(
        quality.subprocess,
        "run",
        lambda command, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(command, 1)
        ),
    )
    assert quality.pdfinfo_page_count(tmp_path / "x.pdf") is None
    assert quality.tool_versions() == {"pdftotext": None, "pdfinfo": None}
