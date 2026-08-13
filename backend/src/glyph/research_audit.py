from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from glyph.research_ai import (
    CORE_NODE_GROUPS,
    NodeDraft,
    ValidatedEvidence,
)

MapStatus = Literal["complete", "partial"]


@dataclass(frozen=True)
class MapAuditIssue:
    code: str
    severity: str
    message: str
    node_key: str | None = None
    details: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class MapAuditResult:
    status: MapStatus
    issues: tuple[MapAuditIssue, ...]


def audit_research_map(
    nodes: tuple[NodeDraft, ...],
    evidence: tuple[ValidatedEvidence, ...],
) -> MapAuditResult:
    accepted_by_id = {item.evidence_id: item for item in evidence}
    issues: list[MapAuditIssue] = []

    for node in nodes:
        cited = [
            accepted_by_id[evidence_id]
            for evidence_id in node.evidence_ids
            if evidence_id in accepted_by_id
        ]
        has_unknown_reference = len(cited) != len(set(node.evidence_ids))
        supporting = [item for item in cited if item.anchor.relation == "supports"]
        if has_unknown_reference or not _claim_has_required_support(node, supporting):
            issues.append(
                MapAuditIssue(
                    code="unsupported_claim",
                    severity="error",
                    message="The claim lacks the required validated supporting evidence.",
                    node_key=node.node_key,
                )
            )
        if node.evidence_quality == "not_reported":
            issues.append(
                MapAuditIssue(
                    code="not_reported",
                    severity="warning",
                    message="The paper explicitly does not report this quantity.",
                    node_key=node.node_key,
                )
            )
        if node.evidence_quality == "conflicted":
            issues.append(
                MapAuditIssue(
                    code="conflicting_evidence",
                    severity="warning",
                    message="Accepted evidence for this claim is in conflict.",
                    node_key=node.node_key,
                )
            )

    represented_types = {node.node_type for node in nodes}
    for category, allowed_types in CORE_NODE_GROUPS.items():
        if not represented_types.intersection(allowed_types):
            issues.append(
                MapAuditIssue(
                    code="missing_core_node",
                    severity="error",
                    message=f"The Research Map is missing its {category} category.",
                    details=MappingProxyType({"category": category}),
                )
            )

    has_statistical_evidence = any(
        node.node_type == "statistical_evidence"
        and any(item in accepted_by_id for item in node.evidence_ids)
        for node in nodes
    )
    if not has_statistical_evidence:
        for primary_result in (
            node for node in nodes if node.node_type == "primary_result"
        ):
            issues.append(
                MapAuditIssue(
                    code="missing_statistical_evidence",
                    severity="error",
                    message="The primary result lacks statistical evidence.",
                    node_key=primary_result.node_key,
                )
            )

    ordered_issues = tuple(
        sorted(
            issues,
            key=lambda issue: (
                issue.node_key or "",
                issue.code,
                issue.message,
            ),
        )
    )
    status: MapStatus = "partial" if ordered_issues else "complete"
    return MapAuditResult(status=status, issues=ordered_issues)


def _claim_has_required_support(
    node: NodeDraft,
    supporting: list[ValidatedEvidence],
) -> bool:
    if node.provenance == "ai_synthesis":
        if node.evidence_quality in {"insufficient", "not_reported"}:
            return True
        return len({item.evidence_id for item in supporting}) >= 2
    if node.provenance == "author_explicit":
        return bool(supporting) and node.evidence_quality != "synthesized"
    if node.evidence_quality in {"insufficient", "not_reported"}:
        return True
    return bool(supporting)
