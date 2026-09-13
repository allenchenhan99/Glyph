"""Read-only workspace capabilities for first-use guidance.

Every check is local: executables on PATH, environment configuration and
session settings. Nothing here contacts a provider, and the response never
carries keys, credential values, document paths or document text. ``configured``
means locally configured, never authenticated or funded.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import APIRouter, Request

from glyph.config import Settings, resolve_translation_settings
from glyph.orcarouter import is_valid_api_key
from glyph.processing_preflight import unlimited_ocr_problem

RESEARCH_FEATURES = ("summaries", "research_maps", "implementation_contracts")
BLOCKED_MESSAGE = "Unavailable until the workspace is recovered."

router = APIRouter(prefix="/api", tags=["workspace"])


@dataclass(frozen=True)
class CapabilityView:
    provider: str
    configured: bool
    message: str


@dataclass(frozen=True)
class WorkspaceView:
    status: Literal["ready", "blocked"]
    development_features: tuple[str, ...]
    translation: CapabilityView
    research: CapabilityView
    ocr: CapabilityView
    recovery: str | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "development_features": list(self.development_features),
            "translation": vars(self.translation),
            "research": vars(self.research),
            "ocr": vars(self.ocr),
            "recovery": self.recovery,
        }


def describe_workspace(settings: Settings) -> WorkspaceView:
    translation = translation_capability(settings)
    research = research_capability(settings)
    features: list[str] = []
    if translation.provider == "mock":
        features.append("translation")
    if research.provider == "mock":
        features.extend(RESEARCH_FEATURES)
    return WorkspaceView(
        status="ready",
        development_features=tuple(features),
        translation=translation,
        research=research,
        ocr=ocr_capability(settings),
        recovery=None,
    )


def blocked_workspace(recovery: str) -> WorkspaceView:
    unknown = CapabilityView("unknown", False, BLOCKED_MESSAGE)
    return WorkspaceView(
        status="blocked",
        development_features=(),
        translation=unknown,
        research=unknown,
        ocr=unknown,
        recovery=recovery,
    )


def translation_capability(settings: Settings) -> CapabilityView:
    translation = resolve_translation_settings(settings)
    provider = translation.provider
    if provider == "mock":
        return CapabilityView(
            provider,
            True,
            "Deterministic development translation: fixed placeholder text, not "
            "a language model.",
        )
    if provider in {"claude_cli", "codex_cli"}:
        return cli_capability(provider, "translation")
    if not translation.model or not translation.api_key:
        return CapabilityView(
            provider,
            False,
            "OrcaRouter needs a model ID and your API key. Enter both in "
            "Translation settings or in the environment.",
        )
    if not is_valid_api_key(translation.api_key):
        return CapabilityView(
            provider,
            False,
            "The OrcaRouter API key has an unsupported format. Re-enter the key.",
        )
    return CapabilityView(
        provider,
        True,
        "OrcaRouter is configured with a model and key. They are not verified "
        "before a run and no request is made now; usage is billed to your account.",
    )


def research_capability(settings: Settings) -> CapabilityView:
    if settings.ai_mode == "mock":
        return CapabilityView(
            "mock",
            True,
            "Deterministic fixture output for summaries, Research Maps and "
            "Implementation Contracts; not a language model.",
        )
    return cli_capability(settings.ai_mode, "research")


def cli_capability(provider: str, purpose: str) -> CapabilityView:
    executable = provider.removesuffix("_cli")
    if shutil.which(executable) is None:
        return CapabilityView(
            provider,
            False,
            f"The {executable} CLI is not on PATH, so {purpose} cannot run. "
            "Install and authenticate it, then restart Glyph.",
        )
    return CapabilityView(
        provider,
        True,
        f"The {executable} CLI is installed. Its authentication is not verified "
        "here; a run reports the CLI error if it is not signed in.",
    )


def ocr_capability(settings: Settings) -> CapabilityView:
    poppler = shutil.which("pdftotext") is not None
    if settings.ocr_mode == "mock":
        if not poppler:
            return CapabilityView(
                "mock",
                False,
                "Poppler (pdftotext) is not installed, so text cannot be extracted "
                "from PDFs. Install Poppler; scanned PDFs and images additionally "
                "need a configured OCR adapter.",
            )
        return CapabilityView(
            "mock",
            True,
            "Text-layer PDFs are extracted locally with Poppler (pdftotext). "
            "Scanned PDFs and images need a configured OCR adapter "
            "(GLYPH_OCR_MODE=unlimited_ocr); the mock does not read images.",
        )
    if settings.ocr_mode == "unlimited_ocr":
        problem = unlimited_ocr_problem(settings)
        if problem is not None:
            return CapabilityView("unlimited_ocr", False, problem)
        poppler_note = (
            "" if poppler else " Poppler (pdftotext) is missing for text-layer PDFs."
        )
        return CapabilityView(
            "unlimited_ocr",
            True,
            "Unlimited-OCR is configured for scanned PDFs and images; text-layer "
            "PDFs are still extracted with Poppler." + poppler_note,
        )
    return CapabilityView(
        settings.ocr_mode,
        False,
        f"Unknown GLYPH_OCR_MODE '{settings.ocr_mode}'. Use mock or unlimited_ocr.",
    )


@router.get("/workspace")
def get_workspace(request: Request) -> dict[str, Any]:
    view: WorkspaceView = request.app.state.workspace_view()
    return view.to_payload()
