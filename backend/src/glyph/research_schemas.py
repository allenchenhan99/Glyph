from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from glyph.research_domain import (
    EvidenceQuality,
    EvidenceRelation,
    LocatorType,
    NodeType,
    Provenance,
    ReviewStatus,
)

MapStatus = Literal["building", "complete", "partial", "failed"]
JobStatus = Literal["queued", "running", "completed", "failed"]
IssueSeverity = Literal["info", "warning", "error"]
DiffClassification = Literal[
    "unchanged", "claim_changed", "evidence_changed", "added", "removed"
]


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


ApiDateTime = Annotated[datetime, BeforeValidator(ensure_utc)]


class AttributeModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ResearchMapJobOut(AttributeModel):
    id: str
    document_id: str
    map_version_id: str | None
    status: JobStatus
    stage: str
    progress: float
    error_message: str | None
    attempt_count: int
    created_at: ApiDateTime
    updated_at: ApiDateTime


class ResearchEvidenceOut(AttributeModel):
    id: str
    block_id: str
    locator_type: LocatorType
    quote_text: str
    quote_start: int
    quote_end: int
    source_quote_hash: str
    relation: EvidenceRelation
    source_label: str | None
    page_number: int
    block_type: str
    translated_text: str


class ResearchMapIssueOut(AttributeModel):
    id: str
    node_id: str | None
    code: str
    severity: IssueSeverity
    message: str


class ResearchNodeReviewOut(AttributeModel):
    id: str
    status: ReviewStatus
    corrected_claim_text: str | None
    review_note: str | None
    revision_number: int
    supersedes_review_id: str | None
    reviewed_at: ApiDateTime


class ResearchNodeOut(AttributeModel):
    id: str
    parent_node_id: str | None
    node_key: str
    node_type: NodeType
    title: str
    claim_text: str
    effective_claim_text: str
    explanation: str
    provenance: Provenance
    evidence_quality: EvidenceQuality
    display_order: int
    node_signature: str
    evidence: tuple[ResearchEvidenceOut, ...]
    issues: tuple[ResearchMapIssueOut, ...]
    review: ResearchNodeReviewOut | None


class ResearchMapOut(AttributeModel):
    id: str
    document_id: str
    previous_version_id: str | None
    source_content_hash: str
    schema_version: str
    provider: str
    model_name: str | None
    status: MapStatus
    is_active: bool
    is_current: bool
    is_stale: bool
    created_at: ApiDateTime
    completed_at: ApiDateTime | None
    reviewed_core_nodes: int
    reviewable_core_nodes: int
    nodes: tuple[ResearchNodeOut, ...]
    issues: tuple[ResearchMapIssueOut, ...]


class ResearchMapVersionOut(AttributeModel):
    id: str
    document_id: str
    previous_version_id: str | None
    source_content_hash: str
    schema_version: str
    provider: str
    model_name: str | None
    status: MapStatus
    is_active: bool
    is_current: bool
    is_stale: bool
    created_at: ApiDateTime
    completed_at: ApiDateTime | None


class ResearchNodeReviewRequest(BaseModel):
    status: ReviewStatus
    based_on_node_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    corrected_claim_text: str | None = None
    review_note: str | None = None

    @model_validator(mode="after")
    def corrected_review_requires_claim(self) -> Self:
        if self.status == "corrected" and not (
            self.corrected_claim_text and self.corrected_claim_text.strip()
        ):
            raise ValueError("corrected_claim_text is required for corrected reviews")
        return self


class ResearchNodeReviewRecordOut(ResearchNodeReviewOut):
    node_id: str
    based_on_map_version_id: str
    based_on_node_signature: str


class ResearchNodeDiffOut(AttributeModel):
    node_key: str
    classification: DiffClassification
    version_node_id: str | None
    against_node_id: str | None


class ResearchMapDiffOut(AttributeModel):
    version_id: str
    against_version_id: str
    nodes: tuple[ResearchNodeDiffOut, ...]
