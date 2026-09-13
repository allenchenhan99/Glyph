from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from glyph.config import Settings, TranslationSettings


@dataclass(frozen=True)
class ParsedBlock:
    order_index: int
    page_number: int
    block_type: str
    source_text: str
    translated_text: str
    section_title: str
    formula_latex: str | None = None
    confidence: float = 1.0


@dataclass(frozen=True)
class ParsedSection:
    order_index: int
    title: str
    path: str
    summary: str


@dataclass(frozen=True)
class ParsedDocument:
    blocks: list[ParsedBlock]
    sections: list[ParsedSection]
    summary: str


class MockAiAdapter:
    def parse_translate_and_summarize(
        self,
        page_text: list[tuple[int, str]],
        *,
        progress: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> ParsedDocument:
        document = self.prepare_document(page_text)
        if progress is not None:
            progress(len(document.blocks), len(document.blocks))
        return document

    def prepare_document(self, page_text: list[tuple[int, str]]) -> ParsedDocument:
        blocks: list[ParsedBlock] = []
        sections: list[ParsedSection] = []
        current_section = "Document"

        for page_number, text in page_text:
            for part in [
                part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()
            ]:
                for unit in split_reading_units(part):
                    block_type = classify_block(unit)
                    source_text = normalize_source_text(unit, block_type)
                    if block_type == "heading":
                        current_section = source_text
                        if not any(
                            section.title == current_section for section in sections
                        ):
                            sections.append(
                                ParsedSection(
                                    order_index=len(sections),
                                    title=current_section,
                                    path=current_section,
                                    summary=f"{current_section} 的重點摘要。",
                                )
                            )
                    blocks.append(
                        ParsedBlock(
                            order_index=len(blocks),
                            page_number=page_number,
                            block_type=block_type,
                            source_text=source_text,
                            translated_text=translate_to_traditional_chinese(
                                source_text, block_type
                            ),
                            section_title=current_section,
                        )
                    )

        if not sections:
            sections.append(
                ParsedSection(
                    order_index=0,
                    title="Document",
                    path="Document",
                    summary="本文的主要內容摘要。",
                )
            )
        if not blocks:
            blocks.append(
                ParsedBlock(
                    order_index=0,
                    page_number=1,
                    block_type="paragraph",
                    source_text="No readable content was found.",
                    translated_text="繁中翻譯：未找到可讀內容。",
                    section_title=sections[0].title,
                    confidence=0.2,
                )
            )
        return ParsedDocument(
            blocks=blocks,
            sections=sections,
            summary=f"{sections[0].title}：共整理 {len(blocks)} 個閱讀區塊。",
        )


def split_reading_units(text: str) -> list[str]:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    while lines and re.fullmatch(r"\d+", lines[0].strip()):
        lines.pop(0)
    while lines and re.fullmatch(r"\d+", lines[-1].strip()):
        lines.pop()
    if not lines:
        return []

    first_line = lines[0].strip()
    if len(lines) > 1 and looks_like_heading(first_line):
        rest = "\n".join(line for line in lines[1:] if line.strip()).strip()
        return [first_line, rest] if rest else [first_line]
    return ["\n".join(lines).strip()]


def classify_block(text: str) -> str:
    stripped = text.strip()
    if looks_like_heading(stripped):
        return "heading"
    if re.match(r"^(fig\.?|figure)\s+\d", stripped, re.IGNORECASE):
        return "figure"
    if re.match(r"^table\s+\d", stripped, re.IGNORECASE):
        return "table"
    if looks_like_formula(stripped):
        return "formula"
    if re.match(r"^\d+[\.)]\s+", stripped):
        return "question"
    if stripped.startswith(("-", "*", "•")):
        return "list"
    return "paragraph"


def normalize_source_text(text: str, block_type: str) -> str:
    if block_type in {"formula", "table"}:
        return "\n".join(line.rstrip() for line in text.strip().splitlines())
    stripped = " ".join(line.strip() for line in text.strip().splitlines())
    if block_type == "heading":
        return stripped.lstrip("#").strip()
    return stripped


def translate_to_traditional_chinese(text: str, block_type: str) -> str:
    if block_type == "heading":
        return f"標題：{text}"
    if block_type == "formula":
        return f"公式：{text}"
    if block_type == "figure":
        return f"圖表：{text}"
    if block_type == "table":
        return f"表格：{text}"
    if block_type == "question":
        return f"繁中翻譯：{text}（問題）"
    return f"繁中翻譯：{text}"


def looks_like_formula(text: str) -> bool:
    if not text or len(text) > 600:
        return False
    formula_markers = (
        "=",
        "∑",
        "√",
        "≤",
        "≥",
        "≠",
        "σ",
        "μ",
        "^",
        "_",
        "\\frac",
        "\\sum",
    )
    if not any(marker in text for marker in formula_markers):
        return False
    words = re.findall(r"[A-Za-z]{3,}", text)
    operators = len(re.findall(r"[=+\-*/^]", text))
    return operators >= 1 and len(words) <= 16


def looks_like_heading(text: str) -> bool:
    if text.startswith("#"):
        return True
    if not re.match(r"^(chapter|section)\b", text, re.IGNORECASE):
        return False
    if len(text) > 160 or text.count("\n") > 1:
        return False
    return "....." not in text


def create_ai_adapter(
    settings: Settings, translation: TranslationSettings | None = None
):
    """Translation adapter; Research Maps and Contracts keep using ai_mode.

    Pass ``translation`` to build the adapter from settings captured earlier (for
    example at enqueue time) instead of the current session state.
    """
    from glyph.config import resolve_translation_settings

    if translation is None:
        translation = resolve_translation_settings(settings)
    if translation.provider == "orcarouter":
        from glyph.orcarouter import OrcaRouterAdapter

        return OrcaRouterAdapter(
            api_key=translation.api_key,
            model=translation.model,
            batch_size=min(settings.cli_batch_size, 8),
            timeout_seconds=settings.cli_timeout_seconds,
            concurrency=1,
            cache_dir=settings.data_dir / "ai-cache",
        )
    if translation.provider == "mock":
        return MockAiAdapter()
    if translation.provider in {"claude_cli", "codex_cli"}:
        from glyph.cli_ai import CliAiAdapter

        return CliAiAdapter(
            provider=translation.provider.removesuffix("_cli"),
            model=translation.model or None,
            batch_size=settings.cli_batch_size,
            timeout_seconds=settings.cli_timeout_seconds,
            concurrency=settings.cli_concurrency,
            cache_dir=settings.data_dir / "ai-cache",
        )
    raise RuntimeError(f"Unknown AI mode: {translation.provider}")
