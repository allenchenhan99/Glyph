from __future__ import annotations

from typing import Literal, TypeVar

RESEARCH_MAP_SCHEMA_VERSION = "1"

NodeType = Literal[
    "research_question",
    "author_claim",
    "economic_mechanism",
    "hypothesis",
    "data_and_sample",
    "data_source",
    "sample_filter",
    "signal_definition",
    "variable_definition",
    "portfolio_construction",
    "rebalancing_rule",
    "empirical_method",
    "benchmark_model",
    "identification_strategy",
    "primary_result",
    "statistical_evidence",
    "economic_magnitude",
    "turnover",
    "transaction_cost",
    "robustness_test",
    "subsample_result",
    "alternative_explanation",
    "implementation_constraint",
    "limitations",
    "unanswered_question",
]
Provenance = Literal["author_explicit", "ai_synthesis", "human_created"]
EvidenceQuality = Literal[
    "direct", "synthesized", "insufficient", "conflicted", "not_reported"
]
EvidenceRelation = Literal["supports", "qualifies", "contradicts", "context"]
LocatorType = Literal["text_span", "equation", "table", "figure", "caption"]
ReviewStatus = Literal["confirmed", "questioned", "corrected"]

NODE_TYPES: tuple[NodeType, ...] = (
    "research_question",
    "author_claim",
    "economic_mechanism",
    "hypothesis",
    "data_and_sample",
    "data_source",
    "sample_filter",
    "signal_definition",
    "variable_definition",
    "portfolio_construction",
    "rebalancing_rule",
    "empirical_method",
    "benchmark_model",
    "identification_strategy",
    "primary_result",
    "statistical_evidence",
    "economic_magnitude",
    "turnover",
    "transaction_cost",
    "robustness_test",
    "subsample_result",
    "alternative_explanation",
    "implementation_constraint",
    "limitations",
    "unanswered_question",
)
PROVENANCES: tuple[Provenance, ...] = (
    "author_explicit",
    "ai_synthesis",
    "human_created",
)
EVIDENCE_QUALITIES: tuple[EvidenceQuality, ...] = (
    "direct",
    "synthesized",
    "insufficient",
    "conflicted",
    "not_reported",
)
EVIDENCE_RELATIONS: tuple[EvidenceRelation, ...] = (
    "supports",
    "qualifies",
    "contradicts",
    "context",
)
LOCATOR_TYPES: tuple[LocatorType, ...] = (
    "text_span",
    "equation",
    "table",
    "figure",
    "caption",
)
REVIEW_STATUSES: tuple[ReviewStatus, ...] = (
    "confirmed",
    "questioned",
    "corrected",
)


class InvalidDomainValueError(ValueError):
    """Raised when provider output escapes the controlled Research Map schema."""


ControlledValue = TypeVar(
    "ControlledValue",
    NodeType,
    Provenance,
    EvidenceQuality,
    EvidenceRelation,
    LocatorType,
    ReviewStatus,
)


def _validate_controlled_value(
    field_name: str,
    value: str,
    allowed: tuple[ControlledValue, ...],
) -> ControlledValue:
    if value not in allowed:
        raise InvalidDomainValueError(f"Unknown {field_name}: {value}")
    return value


def validate_node_type(value: str) -> NodeType:
    return _validate_controlled_value("node type", value, NODE_TYPES)


def validate_provenance(value: str) -> Provenance:
    return _validate_controlled_value("provenance", value, PROVENANCES)


def validate_evidence_quality(value: str) -> EvidenceQuality:
    return _validate_controlled_value("evidence quality", value, EVIDENCE_QUALITIES)


def validate_evidence_relation(value: str) -> EvidenceRelation:
    return _validate_controlled_value("evidence relation", value, EVIDENCE_RELATIONS)


def validate_locator_type(value: str) -> LocatorType:
    return _validate_controlled_value("locator type", value, LOCATOR_TYPES)


def validate_review_status(value: str) -> ReviewStatus:
    return _validate_controlled_value("review status", value, REVIEW_STATUSES)
