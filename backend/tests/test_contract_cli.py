from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from glyph.config import Settings
from glyph.contract_cli import main
from glyph.database import create_session_factory
from glyph.models import Block, Document, ResearchMapVersion

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "contracts" / "monthly_accounting_signal.txt"
)


@pytest.fixture
def cli_settings(tmp_path: Path) -> tuple[Settings, str, str]:
    settings = Settings(
        book_dir=tmp_path / "book",
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{tmp_path / 'data' / 'glyph.sqlite3'}",
        ocr_mode="mock",
        ai_mode="mock",
        unlimited_ocr_repo=None,
        unlimited_ocr_command=None,
    )
    source_text = FIXTURE_PATH.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source_text.encode()).hexdigest()
    factory = create_session_factory(settings)
    with factory.begin() as session:
        session.add_all(
            [
                Document(
                    id="cli-paper",
                    title="CLI paper",
                    source_path=str(tmp_path / "private" / "cli-paper.txt"),
                    content_hash=source_hash,
                    processed_content_hash=source_hash,
                    file_type="txt",
                    status="completed",
                ),
                Block(
                    id="cli-source",
                    document_id="cli-paper",
                    source_content_hash=source_hash,
                    order_index=0,
                    page_number=1,
                    block_type="text",
                    source_text=source_text,
                    translated_text=f"繁中：{source_text}",
                ),
                ResearchMapVersion(
                    id="cli-map",
                    document_id="cli-paper",
                    source_content_hash=source_hash,
                    schema_version="1",
                    provider="mock",
                    status="complete",
                    is_active=True,
                ),
            ]
        )
    return settings, "cli-paper", "cli-map"


def test_cli_generate_list_show_and_export_share_local_services(
    cli_settings, tmp_path, capsys
):
    settings, document_id, map_id = cli_settings

    assert (
        main(
            ["generate", document_id, "--map-version", map_id],
            settings,
        )
        == 0
    )
    generated = json.loads(capsys.readouterr().out)
    version_id = generated["contract_version_id"]
    assert generated["document_id"] == document_id
    assert generated["research_map_version_id"] == map_id

    assert main(["list"], settings) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed == [
        {
            "document_id": document_id,
            "readiness": generated["readiness"],
            "status": generated["status"],
            "version_id": version_id,
        }
    ]

    assert main(["show", document_id], settings) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["id"] == version_id
    assert shown["items"]
    assert "draft_value_json" not in json.dumps(shown)

    output = tmp_path / "exports" / "contract.md"
    assert (
        main(
            [
                "export",
                version_id,
                "--format",
                "markdown",
                "--language",
                "bilingual",
                "--output",
                str(output),
            ],
            settings,
        )
        == 0
    )
    exported = json.loads(capsys.readouterr().out)
    assert exported == {"output": str(output), "version_id": version_id}
    assert output.read_text(encoding="utf-8").startswith("# NOT IMPLEMENTATION READY\n")
    assert "Implementation Contract / 實作契約" in output.read_text(encoding="utf-8")


def test_cli_reports_safe_missing_contract_and_rejects_invalid_choices(
    cli_settings, tmp_path, capsys
):
    settings, _document_id, _map_id = cli_settings

    assert main(["show", "missing"], settings) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip().endswith("Active Implementation Contract not found")
    assert "private" not in captured.err.lower()

    with pytest.raises(SystemExit) as invalid:
        main(
            [
                "export",
                "missing",
                "--format",
                "python",
                "--language",
                "en",
                "--output",
                str(tmp_path / "out.txt"),
            ],
            settings,
        )
    assert invalid.value.code == 2


def test_cli_export_never_executes_formula_text(cli_settings, tmp_path, capsys):
    settings, document_id, map_id = cli_settings
    assert main(["generate", document_id, "--map-version", map_id], settings) == 0
    version_id = json.loads(capsys.readouterr().out)["contract_version_id"]
    sentinel = tmp_path / "must-not-exist"
    output = tmp_path / "contract.json"

    assert (
        main(
            [
                "export",
                version_id,
                "--format",
                "json",
                "--language",
                "en",
                "--output",
                str(output),
            ],
            settings,
        )
        == 0
    )

    assert output.is_file()
    assert not sentinel.exists()
    assert json.loads(output.read_bytes())["contract_version_id"] == version_id
