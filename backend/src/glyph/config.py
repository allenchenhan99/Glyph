from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    book_dir: Path
    data_dir: Path
    database_url: str
    ocr_mode: str
    ai_mode: str
    unlimited_ocr_repo: Path | None
    unlimited_ocr_command: str | None
    cli_model: str | None = None
    cli_batch_size: int = 24
    cli_timeout_seconds: int = 300
    cli_concurrency: int = 3


def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[3]
    data_dir = Path(os.environ.get("GLYPH_DATA_DIR", project_root / "data"))
    book_dir = Path(os.environ.get("GLYPH_BOOK_DIR", project_root / "book"))
    database_url = os.environ.get(
        "GLYPH_DATABASE_URL",
        f"sqlite:///{data_dir / 'glyph.sqlite3'}",
    )
    return Settings(
        book_dir=book_dir,
        data_dir=data_dir,
        database_url=database_url,
        ocr_mode=os.environ.get("GLYPH_OCR_MODE", "mock"),
        ai_mode=os.environ.get("GLYPH_AI_MODE", "claude_cli"),
        unlimited_ocr_repo=Path(repo) if (repo := os.environ.get("GLYPH_UNLIMITED_OCR_REPO")) else None,
        unlimited_ocr_command=os.environ.get("GLYPH_UNLIMITED_OCR_COMMAND"),
        cli_model=os.environ.get("GLYPH_CLI_MODEL"),
        cli_batch_size=int(os.environ.get("GLYPH_CLI_BATCH_SIZE", "24")),
        cli_timeout_seconds=int(os.environ.get("GLYPH_CLI_TIMEOUT_SECONDS", "300")),
        cli_concurrency=int(os.environ.get("GLYPH_CLI_CONCURRENCY", "3")),
    )
