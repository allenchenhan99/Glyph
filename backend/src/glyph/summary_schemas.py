from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SummaryEvidenceOut(BaseModel):
    block_id: str
    quote_text: str
    quote_start: int
    quote_end: int
    page_number: int


class SummaryClaimOut(BaseModel):
    id: str
    section_path: str | None
    text: str
    evidence: list[SummaryEvidenceOut]


class SummaryVersionOut(BaseModel):
    id: str
    source_content_hash: str
    reader_fingerprint: str
    provider: str
    model: str | None
    created_at: datetime
    claims: list[SummaryClaimOut]


class SummaryJobOut(BaseModel):
    id: str
    status: Literal["queued", "running", "completed", "failed", "interrupted"]
    error_message: str | None


class SummaryStateOut(BaseModel):
    status: Literal["not_generated", "generating", "available", "stale", "failed"]
    provider: str
    model: str | None
    version: SummaryVersionOut | None
    job: SummaryJobOut | None
