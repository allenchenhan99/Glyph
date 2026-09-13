from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from glyph.contract_schemas import ImplementationContractLibrarySummaryOut
from glyph.research_schemas import ResearchMapLibrarySummaryOut


class DocumentOut(BaseModel):
    id: str
    title: str
    file_type: str
    status: str
    research_map: ResearchMapLibrarySummaryOut | None = None
    implementation_contract: ImplementationContractLibrarySummaryOut | None = None


class JobOut(BaseModel):
    id: str
    document_id: str
    status: str
    stage: str
    progress: float
    error_message: str | None = None
    completed_blocks: int | None = None
    total_blocks: int | None = None
    cancel_requested: bool = False
    provider: str | None = None
    model: str | None = None


class PreflightIssueOut(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    message: str


class PreflightOut(BaseModel):
    ready: bool
    source_type: str
    provider: str
    page_count: int | None = None
    issues: list[PreflightIssueOut]


class BlockOut(BaseModel):
    id: str
    order_index: int
    page_number: int
    block_type: str
    source_text: str
    translated_text: str
    formula_latex: str | None = None
    page_image_url: str | None
    section_path: str | None = None
    confidence: float


class SectionOut(BaseModel):
    id: str
    title: str
    path: str
    order_index: int
    summary: str
    progress: float


class ReaderOut(BaseModel):
    document: DocumentOut
    blocks: list[BlockOut]
    sections: list[SectionOut]
    summary: str
