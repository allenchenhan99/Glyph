import pytest

from glyph.config import get_settings


def test_upload_limit_defaults_to_fifty_mebibytes(monkeypatch):
    monkeypatch.delenv("GLYPH_MAX_UPLOAD_BYTES", raising=False)

    settings = get_settings()

    assert getattr(settings, "max_upload_bytes", None) == 50 * 1024 * 1024


def test_upload_limit_must_be_positive(monkeypatch):
    monkeypatch.setenv("GLYPH_MAX_UPLOAD_BYTES", "0")

    with pytest.raises(ValueError, match="GLYPH_MAX_UPLOAD_BYTES must be positive"):
        get_settings()


def test_external_process_timeouts_have_conservative_defaults(monkeypatch):
    monkeypatch.delenv("GLYPH_OCR_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("GLYPH_PAGE_RENDER_TIMEOUT_SECONDS", raising=False)

    settings = get_settings()

    assert getattr(settings, "ocr_timeout_seconds", None) == 300
    assert getattr(settings, "page_render_timeout_seconds", None) == 30
    assert getattr(settings, "research_job_max_attempts", None) == 2
    assert getattr(settings, "research_cli_block_batch_size", None) == 12


@pytest.mark.parametrize(
    "name",
    ["GLYPH_OCR_TIMEOUT_SECONDS", "GLYPH_PAGE_RENDER_TIMEOUT_SECONDS"],
)
def test_external_process_timeouts_must_be_positive(monkeypatch, name):
    monkeypatch.setenv(name, "0")

    with pytest.raises(ValueError, match=f"{name} must be positive"):
        get_settings()


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_research_job_max_attempts_must_be_positive(monkeypatch, value):
    monkeypatch.setenv("GLYPH_RESEARCH_JOB_MAX_ATTEMPTS", value)

    with pytest.raises(ValueError, match="GLYPH_RESEARCH_JOB_MAX_ATTEMPTS"):
        get_settings()


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_research_cli_block_batch_size_must_be_positive(monkeypatch, value):
    monkeypatch.setenv("GLYPH_RESEARCH_CLI_BLOCK_BATCH_SIZE", value)

    with pytest.raises(ValueError, match="GLYPH_RESEARCH_CLI_BLOCK_BATCH_SIZE"):
        get_settings()
