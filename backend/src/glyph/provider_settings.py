"""Session-only translation provider settings.

Keys live in backend memory for the current process, are never written to the
database, cache or logs, and are never returned to the browser.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request

from glyph.config import (
    TRANSLATION_PROVIDERS,
    Settings,
    TranslationSettings,
    resolve_translation_settings,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
MAX_MODEL_LENGTH = 200
MAX_KEY_LENGTH = 4096


def public_settings(settings: Settings) -> dict[str, Any]:
    translation = resolve_translation_settings(settings)
    return {
        "provider": translation.provider,
        "model": translation.model,
        "has_api_key": bool(translation.api_key),
        "ocr_mode": settings.ocr_mode,
    }


@router.get("/ai")
def get_ai_settings(request: Request) -> dict[str, Any]:
    return public_settings(request.app.state.settings)


@router.post("/ai")
async def update_ai_settings(request: Request) -> dict[str, Any]:
    require_local_browser(request)
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        raise HTTPException(415, "Send JSON settings.")
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, "Invalid settings.") from None
    if not isinstance(payload, dict) or set(payload) - {"provider", "model", "api_key"}:
        raise HTTPException(400, "Invalid settings.")
    if any(not isinstance(value, str) for value in payload.values()):
        raise HTTPException(400, "Settings must be text values.")
    settings: Settings = request.app.state.settings
    current = resolve_translation_settings(settings)
    provider = payload.get("provider", "")
    model = payload.get("model", "").strip()
    key = payload.get("api_key", current.api_key).strip()
    if (
        provider not in TRANSLATION_PROVIDERS
        or len(model) > MAX_MODEL_LENGTH
        or len(key) > MAX_KEY_LENGTH
        or any(character.isspace() for character in key)
    ):
        raise HTTPException(400, "Invalid provider, model or API key.")
    if provider == "orcarouter" and (not key or not model):
        raise HTTPException(400, "Enter your OrcaRouter API key and model.")
    updated = TranslationSettings(provider=provider, model=model, api_key=key)
    settings.translation_session.override = updated
    return public_settings(settings)


def require_local_browser(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOCAL_HOSTS:
            raise HTTPException(
                403, "Provider settings can only be changed from the local app."
            )
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site settings changes are not allowed.")
