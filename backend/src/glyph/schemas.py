from __future__ import annotations

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    title: str
    source_path: str
    file_type: str
    status: str


class JobOut(BaseModel):
    id: str
    document_id: str
    status: str
    stage: str
    progress: float
    error_message: str | None = None


class BlockOut(BaseModel):
    id: str
    order_index: int
    page_number: int
    block_type: str
    source_text: str
    translated_text: str
    formula_latex: str | None = None
    page_image_url: str
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
