"""Summary providers: a labeled development mock and the CLI provider factory."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Protocol

from glyph.config import Settings
from glyph.summaries import SummaryInputs
from glyph.summary_domain import ClaimDraft, QuoteDraft

MOCK_LABEL = "[Development mock output] "
_SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s+")

CancelCheck = Callable[[], bool]


class SummaryProvider(Protocol):
    name: str
    model_name: str | None

    def generate(
        self, inputs: SummaryInputs, *, should_cancel: CancelCheck
    ) -> tuple[ClaimDraft, ...]: ...


def first_sentence(text: str) -> str:
    return _SENTENCE_END.split(text.strip(), maxsplit=1)[0].strip()


class MockSummaryProvider:
    """Deterministic fixture output: verbatim excerpts, explicitly labeled."""

    name = "mock"
    model_name: str | None = None

    def generate(
        self, inputs: SummaryInputs, *, should_cancel: CancelCheck
    ) -> tuple[ClaimDraft, ...]:
        drafts: list[ClaimDraft] = []
        by_path: dict[str, list] = {}
        for block in inputs.blocks:
            path = inputs.section_path_of(block)
            if path is not None:
                by_path.setdefault(path, []).append(block)
        lead = inputs.blocks[0]
        excerpt = first_sentence(lead.source_text)
        drafts.append(
            ClaimDraft(
                None,
                f"{MOCK_LABEL}The document opens with: {excerpt}",
                (QuoteDraft(lead.id, excerpt, None, None),),
            )
        )
        for path in inputs.section_paths:
            if should_cancel():
                from glyph.cli_ai import TranslationCancelledError

                raise TranslationCancelledError("Summary generation was cancelled.")
            block = by_path[path][-1]
            excerpt = first_sentence(block.source_text)
            drafts.append(
                ClaimDraft(
                    path,
                    f"{MOCK_LABEL}{path} ends with: {excerpt}",
                    (QuoteDraft(block.id, excerpt, None, None),),
                )
            )
        return tuple(drafts)


def create_summary_provider(settings: Settings) -> SummaryProvider:
    """Follows GLYPH_AI_MODE; translation overrides never select the provider."""
    if settings.ai_mode == "mock":
        return MockSummaryProvider()
    if settings.ai_mode in {"claude_cli", "codex_cli"}:
        from glyph.summary_cli_ai import CliSummaryProvider

        return CliSummaryProvider(
            provider=settings.ai_mode.removesuffix("_cli"),
            model=settings.cli_model,
            timeout_seconds=settings.cli_timeout_seconds,
            block_batch_size=settings.research_cli_block_batch_size,
            cache_dir=settings.data_dir / "summary-ai-cache",
        )
    raise RuntimeError(f"Unknown summary AI mode: {settings.ai_mode}")
