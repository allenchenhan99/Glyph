from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from glyph.contract_domain import (
    ContractGenerationStatus,
    ContractItemType,
    ContractOrigin,
    ContractReadiness,
    ContractSection,
    DiffClassification,
    IssueSeverity,
    PeriodUnit,
    ResolutionStatus,
    RuleOperator,
)
from glyph.research_domain import EvidenceRelation, LocatorType

JobStatus = Literal["queued", "running", "completed", "failed"]
ContractExportFormat = Literal["json", "markdown"]
ContractExportLanguage = Literal["en", "zh-TW", "bilingual"]
BoundedText = Annotated[str, Field(max_length=4_000)]
BoundedName = Annotated[str, Field(min_length=1, max_length=128)]


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


ApiDateTime = Annotated[datetime, BeforeValidator(ensure_utc)]


class AttributeModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StrictInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)


class ContractEnqueueRequest(StrictInputModel):
    research_map_version_id: str | None = Field(
        default=None, min_length=1, max_length=36
    )


class ScalarValueIn(StrictInputModel):
    kind: Literal["scalar"]
    value: str | int | float | bool
    unit: str | None = Field(default=None, max_length=128)


class FormulaValueIn(StrictInputModel):
    kind: Literal["formula"]
    expression: BoundedText
    variables: list[BoundedName] | tuple[BoundedName, ...] = Field(max_length=64)


class RuleValueIn(StrictInputModel):
    kind: Literal["rule"]
    operator: RuleOperator
    field: BoundedName
    value: ScalarValueIn


class ListValueIn(StrictInputModel):
    kind: Literal["list"]
    values: list[ScalarValueIn] | tuple[ScalarValueIn, ...] = Field(max_length=100)


class RangeValueIn(StrictInputModel):
    kind: Literal["range"]
    minimum: ScalarValueIn
    maximum: ScalarValueIn
    include_minimum: bool
    include_maximum: bool


class PeriodValueIn(StrictInputModel):
    kind: Literal["period"]
    amount: int = Field(gt=0)
    unit: PeriodUnit
    anchor: str | None = Field(default=None, max_length=128)


ContractValueIn = Annotated[
    ScalarValueIn
    | FormulaValueIn
    | RuleValueIn
    | ListValueIn
    | RangeValueIn
    | PeriodValueIn,
    Field(discriminator="kind"),
]


class ContractResolutionRequest(StrictInputModel):
    request_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    status: ResolutionStatus
    based_on_item_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolved_value: ContractValueIn | None = None
    reason: str | None = Field(default=None, max_length=4_000)

    @model_validator(mode="after")
    def validate_resolution_shape(self) -> Self:
        has_reason = bool(self.reason and self.reason.strip())
        if self.status in {"corrected", "decided"} and (
            self.resolved_value is None or not has_reason
        ):
            raise ValueError(f"A {self.status} resolution requires a value and reason")
        if self.status == "not_applicable" and (
            self.resolved_value is not None or not has_reason
        ):
            raise ValueError(
                "A not_applicable resolution requires a reason and no value"
            )
        if self.status in {"confirmed", "questioned"} and (
            self.resolved_value is not None
        ):
            raise ValueError(
                f"A {self.status} resolution must not have a replacement value"
            )
        return self


class ContractJobOut(AttributeModel):
    id: str
    document_id: str
    requested_research_map_version_id: str | None
    contract_version_id: str | None
    status: JobStatus
    stage: str
    progress: float
    error_message: str | None
    attempt_count: int
    created_at: ApiDateTime
    updated_at: ApiDateTime


class ContractEvidenceOut(AttributeModel):
    id: str
    block_id: str
    research_node_id: str | None
    locator_type: LocatorType
    quote_text: str
    quote_start: int
    quote_end: int
    source_quote_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    relation: EvidenceRelation
    source_label: str | None
    page_number: int
    block_type: str
    translated_text: str


class ContractIssueOut(AttributeModel):
    id: str
    item_id: str | None
    code: str
    severity: IssueSeverity
    message: str


class ContractResolutionOut(AttributeModel):
    id: str
    item_id: str
    revision_number: int
    supersedes_resolution_id: str | None
    status: ResolutionStatus
    resolved_value: ContractValueIn | None
    reason: str | None
    based_on_contract_version_id: str
    based_on_item_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_id: str
    resolved_at: ApiDateTime


class ContractItemOut(AttributeModel):
    id: str
    item_key: str
    section: ContractSection
    item_type: ContractItemType
    draft_value: ContractValueIn | None
    effective_value: ContractValueIn | None
    origin: ContractOrigin
    effective_origin: ContractOrigin
    rationale: str | None
    is_blocking: bool
    is_optional: bool
    display_order: int
    item_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence: tuple[ContractEvidenceOut, ...]
    issues: tuple[ContractIssueOut, ...]
    resolution: ContractResolutionOut | None
    resolution_history: tuple[ContractResolutionOut, ...]


class ImplementationContractOut(AttributeModel):
    id: str
    document_id: str
    research_map_version_id: str
    previous_version_id: str | None
    source_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    research_map_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str
    provider: str
    model_name: str | None
    status: ContractGenerationStatus
    readiness: ContractReadiness
    is_active: bool
    is_current: bool
    is_stale: bool
    created_at: ApiDateTime
    completed_at: ApiDateTime | None
    items: tuple[ContractItemOut, ...]
    issues: tuple[ContractIssueOut, ...]


class ImplementationContractVersionOut(AttributeModel):
    id: str
    document_id: str
    research_map_version_id: str
    previous_version_id: str | None
    source_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    research_map_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str
    provider: str
    model_name: str | None
    status: ContractGenerationStatus
    readiness: ContractReadiness
    is_active: bool
    is_current: bool
    is_stale: bool
    created_at: ApiDateTime
    completed_at: ApiDateTime | None


class ContractItemDiffOut(AttributeModel):
    item_key: str
    classification: DiffClassification
    version_item_id: str | None
    against_item_id: str | None


class ImplementationContractDiffOut(AttributeModel):
    version_id: str
    against_version_id: str
    items: tuple[ContractItemDiffOut, ...]


class ImplementationContractLibrarySummaryOut(AttributeModel):
    version_id: str
    generation_status: ContractGenerationStatus
    readiness: ContractReadiness
    is_current: bool
    is_stale: bool
    blocker_count: int
    reviewed_count: int
    total_reviewable_count: int
