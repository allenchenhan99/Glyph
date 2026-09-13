from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# GLYPH_AI_MODE drives Research Maps, Implementation Contracts and the translation
# default. Translation alone may be redirected to OrcaRouter, by environment or by a
# session-only override entered in the UI.
AI_MODES = frozenset({"claude_cli", "codex_cli", "mock"})
TRANSLATION_PROVIDERS = AI_MODES | {"orcarouter"}


@dataclass(frozen=True)
class TranslationSettings:
    """Provider selection for document translation; never persisted."""

    provider: str
    model: str
    api_key: str = field(default="", repr=False)


@dataclass
class TranslationSession:
    # Replace the whole snapshot in one assignment so readers never see a partial state.
    override: TranslationSettings | None = field(default=None, repr=False)


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
    max_upload_bytes: int = 50 * 1024 * 1024
    ocr_timeout_seconds: int = 300
    page_render_timeout_seconds: int = 30
    research_job_max_attempts: int = 2
    research_cli_block_batch_size: int = 12
    contract_cli_block_batch_size: int = 8
    translation_provider: str | None = None  # None: follow ai_mode
    orcarouter_model: str = ""
    orcarouter_api_key: str = field(default="", repr=False)
    translation_session: TranslationSession = field(
        default_factory=TranslationSession, repr=False, compare=False
    )


def positive_int_from_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def choice_from_env(name: str, default: str, allowed: frozenset[str]) -> str:
    value = os.environ.get(name, default)
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(sorted(allowed))}")
    return value


def resolve_translation_settings(settings: Settings) -> TranslationSettings:
    override = settings.translation_session.override
    if override is not None:
        return override
    provider = settings.translation_provider or settings.ai_mode
    model = (
        settings.orcarouter_model
        if provider == "orcarouter"
        else settings.cli_model or ""
    )
    return TranslationSettings(
        provider=provider,
        model=model,
        api_key=settings.orcarouter_api_key,
    )


def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[3]
    data_dir = Path(os.environ.get("GLYPH_DATA_DIR", project_root / "data"))
    book_dir = Path(os.environ.get("GLYPH_BOOK_DIR", project_root / "book"))
    database_url = os.environ.get(
        "GLYPH_DATABASE_URL",
        f"sqlite:///{data_dir / 'glyph.sqlite3'}",
    )
    ai_mode = choice_from_env("GLYPH_AI_MODE", "claude_cli", AI_MODES)
    return Settings(
        book_dir=book_dir,
        data_dir=data_dir,
        database_url=database_url,
        ocr_mode=os.environ.get("GLYPH_OCR_MODE", "mock"),
        ai_mode=ai_mode,
        unlimited_ocr_repo=Path(repo)
        if (repo := os.environ.get("GLYPH_UNLIMITED_OCR_REPO"))
        else None,
        unlimited_ocr_command=os.environ.get("GLYPH_UNLIMITED_OCR_COMMAND"),
        cli_model=os.environ.get("GLYPH_CLI_MODEL"),
        cli_batch_size=positive_int_from_env("GLYPH_CLI_BATCH_SIZE", 24),
        cli_timeout_seconds=positive_int_from_env("GLYPH_CLI_TIMEOUT_SECONDS", 300),
        cli_concurrency=positive_int_from_env("GLYPH_CLI_CONCURRENCY", 3),
        max_upload_bytes=positive_int_from_env(
            "GLYPH_MAX_UPLOAD_BYTES", 50 * 1024 * 1024
        ),
        ocr_timeout_seconds=positive_int_from_env("GLYPH_OCR_TIMEOUT_SECONDS", 300),
        page_render_timeout_seconds=positive_int_from_env(
            "GLYPH_PAGE_RENDER_TIMEOUT_SECONDS", 30
        ),
        research_job_max_attempts=positive_int_from_env(
            "GLYPH_RESEARCH_JOB_MAX_ATTEMPTS", 2
        ),
        research_cli_block_batch_size=positive_int_from_env(
            "GLYPH_RESEARCH_CLI_BLOCK_BATCH_SIZE", 12
        ),
        contract_cli_block_batch_size=positive_int_from_env(
            "GLYPH_CONTRACT_CLI_BLOCK_BATCH_SIZE", 8
        ),
        translation_provider=choice_from_env(
            "GLYPH_TRANSLATION_PROVIDER", ai_mode, TRANSLATION_PROVIDERS
        )
        if "GLYPH_TRANSLATION_PROVIDER" in os.environ
        else None,
        orcarouter_model=os.environ.get("GLYPH_ORCAROUTER_MODEL", ""),
        orcarouter_api_key=os.environ.get("ORCAROUTER_API_KEY", ""),
    )
