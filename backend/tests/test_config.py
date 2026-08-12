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
