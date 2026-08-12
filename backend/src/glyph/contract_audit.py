from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from glyph.contract_domain import (
    CONTRACT_SECTIONS,
    ContractGenerationStatus,
    ContractIssueDraft,
    ContractItemDraft,
    ContractOrigin,
    ContractReadiness,
    ContractResolutionDraft,
    ContractValue,
    IssueSeverity,
    PeriodValue,
    ScalarValue,
)
from glyph.contract_evidence import AcceptedContractEvidence

_PARTIAL_ISSUE_CODES = {
    "derived_evidence_shortfall",
    "derived_without_rationale",
    "explicit_without_evidence",
}
_DATA_FREQUENCY_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 90,
    "annual": 365,
}


@dataclass(frozen=True)
class EffectiveContractItem:
    draft: ContractItemDraft
    evidence: tuple[AcceptedContractEvidence, ...]
    resolution: ContractResolutionDraft | None = None


@dataclass(frozen=True)
class AuditedContractItem:
    draft: ContractItemDraft
    evidence: tuple[AcceptedContractEvidence, ...]
    resolution: ContractResolutionDraft | None
    effective_value: ContractValue | None
    effective_origin: ContractOrigin
    is_applicable: bool


@dataclass(frozen=True)
class ContractAuditResult:
    generation_status: ContractGenerationStatus
    readiness: ContractReadiness
    items: tuple[AuditedContractItem, ...]
    issues: tuple[ContractIssueDraft, ...]


def audit_contract(items: Iterable[EffectiveContractItem]) -> ContractAuditResult:
    ordered = tuple(sorted(items, key=_item_sort_key))
    audited_items = tuple(_effective_item(item) for item in ordered)
    issues: list[ContractIssueDraft] = []

    for item in audited_items:
        _audit_evidence(item, issues)
        _audit_resolution(item, issues)
    _audit_formation_availability(audited_items, issues)
    _audit_holding_rebalance(audited_items, issues)
    _audit_data_rebalance(audited_items, issues)
    _audit_benchmark_metric(audited_items, issues)

    unique_issues = {
        (issue.severity, issue.code, issue.item_key, issue.message): issue
        for issue in issues
    }
    ordered_issues = tuple(
        sorted(
            unique_issues.values(),
            key=lambda issue: (
                issue.severity,
                issue.code,
                issue.item_key or "",
                issue.message,
            ),
        )
    )
    generation_status: ContractGenerationStatus = (
        "partial"
        if any(issue.code in _PARTIAL_ISSUE_CODES for issue in ordered_issues)
        else "complete"
    )
    if any(issue.severity == "error" for issue in ordered_issues):
        readiness: ContractReadiness = "blocked"
    elif ordered_issues:
        readiness = "review_needed"
    else:
        readiness = "implementation_ready"
    return ContractAuditResult(
        generation_status=generation_status,
        readiness=readiness,
        items=audited_items,
        issues=ordered_issues,
    )


def _effective_item(item: EffectiveContractItem) -> AuditedContractItem:
    resolution = item.resolution
    if resolution is None or resolution.status in ("confirmed", "questioned"):
        value = item.draft.value
        origin = item.draft.origin
        is_applicable = True
    elif resolution.status in ("corrected", "decided"):
        value = resolution.value
        origin = "human_decision"
        is_applicable = True
    else:
        value = None
        origin = "human_decision"
        is_applicable = False
    return AuditedContractItem(
        draft=item.draft,
        evidence=item.evidence,
        resolution=resolution,
        effective_value=value,
        effective_origin=origin,
        is_applicable=is_applicable,
    )


def _audit_evidence(
    item: AuditedContractItem,
    issues: list[ContractIssueDraft],
) -> None:
    supporting = tuple(
        anchor for anchor in item.evidence if anchor.relation == "supports"
    )
    if item.draft.origin == "author_explicit" and not supporting:
        _issue(
            issues,
            item,
            "explicit_without_evidence",
            "error",
            "An author_explicit item requires direct supporting evidence.",
        )
    if item.draft.origin == "derived":
        if len(supporting) < 2:
            _issue(
                issues,
                item,
                "derived_evidence_shortfall",
                "error",
                "A derived item requires at least two supporting anchors.",
            )
        if not (item.draft.rationale and item.draft.rationale.strip()):
            _issue(
                issues,
                item,
                "derived_without_rationale",
                "error",
                "A derived item requires an explicit rationale.",
            )


def _audit_resolution(
    item: AuditedContractItem,
    issues: list[ContractIssueDraft],
) -> None:
    resolution = item.resolution
    if item.draft.origin == "missing":
        resolved_by_decision = resolution is not None and resolution.status == "decided"
        gross_replication = (
            resolution is not None
            and resolution.status == "not_applicable"
            and item.draft.item_type == "transaction_cost"
        )
        if (
            not (resolved_by_decision or gross_replication)
            and item.draft.is_blocking
            and not item.draft.is_optional
        ):
            _issue(
                issues,
                item,
                "missing_blocker",
                "error",
                "A blocking implementation value remains missing.",
            )
        return

    if resolution is None:
        _issue(
            issues,
            item,
            "review_required",
            "info",
            "This supported item still requires explicit human review.",
        )
        return
    if resolution.status == "questioned":
        _issue(
            issues,
            item,
            "blocking_item_questioned",
            "error" if item.draft.is_blocking else "warning",
            "A questioned item cannot be treated as implementation-ready.",
        )
    if resolution.status == "not_applicable":
        _issue(
            issues,
            item,
            "unsupported_not_applicable",
            "error",
            "A reported implementation field cannot be discarded as not applicable.",
        )


def _audit_formation_availability(
    items: tuple[AuditedContractItem, ...],
    issues: list[ContractIssueDraft],
) -> None:
    formation = _first_applicable(items, "formation_date")
    availability = _first_applicable(items, "availability_lag")
    if formation is None or availability is None:
        return
    formation_value = formation.effective_value
    availability_value = availability.effective_value
    if not isinstance(formation_value, PeriodValue) or not isinstance(
        availability_value, PeriodValue
    ):
        _temporal_review(
            issues, formation, "Formation and availability must be periods."
        )
        return
    if formation_value.anchor != availability_value.anchor:
        _temporal_review(
            issues, formation, "Formation and availability anchors differ."
        )
        return
    comparison = _compare_periods(formation_value, availability_value)
    if comparison is None:
        _temporal_review(
            issues,
            formation,
            "Formation and availability periods are not exactly comparable.",
        )
    elif comparison < 0:
        _issue(
            issues,
            formation,
            "lookahead_risk_detected",
            "error",
            "The formation date precedes the stated data availability lag.",
        )


def _audit_holding_rebalance(
    items: tuple[AuditedContractItem, ...],
    issues: list[ContractIssueDraft],
) -> None:
    holding = _first_applicable(items, "holding_period")
    rebalance = _first_applicable(items, "rebalance_frequency")
    if holding is None or rebalance is None:
        return
    holding_value = holding.effective_value
    rebalance_value = rebalance.effective_value
    if not isinstance(holding_value, PeriodValue) or not isinstance(
        rebalance_value, PeriodValue
    ):
        _temporal_review(
            issues, holding, "Holding and rebalance values must be periods."
        )
        return
    comparison = _compare_periods(holding_value, rebalance_value)
    if comparison is None:
        _temporal_review(
            issues,
            holding,
            "Holding and rebalance periods are not exactly comparable.",
        )
    elif comparison < 0:
        _issue(
            issues,
            holding,
            "holding_rebalance_gap",
            "error",
            "The holding period ends before the next scheduled rebalance.",
        )


def _audit_data_rebalance(
    items: tuple[AuditedContractItem, ...],
    issues: list[ContractIssueDraft],
) -> None:
    data_frequency = _first_applicable(items, "data_frequency")
    rebalance = _first_applicable(items, "rebalance_frequency")
    if data_frequency is None or rebalance is None:
        return
    data_value = data_frequency.effective_value
    rebalance_value = rebalance.effective_value
    if not (
        isinstance(data_value, ScalarValue)
        and isinstance(data_value.value, str)
        and isinstance(rebalance_value, PeriodValue)
    ):
        _temporal_review(
            issues,
            data_frequency,
            "Data and rebalance frequencies are not structurally comparable.",
        )
        return
    data_days = _DATA_FREQUENCY_DAYS.get(data_value.value)
    rebalance_days = _approximate_period_days(rebalance_value)
    if data_days is None or rebalance_days is None:
        _temporal_review(
            issues,
            data_frequency,
            "Data and rebalance frequencies use unsupported units.",
        )
    elif data_days > rebalance_days:
        _issue(
            issues,
            data_frequency,
            "data_rebalance_frequency_mismatch",
            "error",
            "The portfolio rebalances faster than the source data updates.",
        )


def _audit_benchmark_metric(
    items: tuple[AuditedContractItem, ...],
    issues: list[ContractIssueDraft],
) -> None:
    metric = _first_applicable(items, "evaluation_metric")
    benchmark = _first_applicable(items, "benchmark_model")
    if metric is None:
        return
    metric_value = metric.effective_value
    if not isinstance(metric_value, ScalarValue) or not isinstance(
        metric_value.value, str
    ):
        return
    if metric_value.value == "factor_alpha" and benchmark is None:
        _issue(
            issues,
            metric,
            "benchmark_required",
            "error",
            "A factor-alpha metric requires a benchmark model.",
        )
    elif metric_value.value in ("raw_return", "sharpe_ratio") and benchmark is not None:
        _issue(
            issues,
            metric,
            "benchmark_metric_mismatch",
            "error",
            "The selected metric does not use the supplied factor benchmark.",
        )


def _compare_periods(left: PeriodValue, right: PeriodValue) -> int | None:
    left_value = _exact_period_value(left)
    right_value = _exact_period_value(right)
    if left_value is None or right_value is None or left_value[0] != right_value[0]:
        return None
    return (left_value[1] > right_value[1]) - (left_value[1] < right_value[1])


def _exact_period_value(period: PeriodValue) -> tuple[str, int] | None:
    if period.unit == "business_day":
        return "business_day", period.amount
    if period.unit == "day":
        return "day", period.amount
    if period.unit == "week":
        return "day", period.amount * 7
    if period.unit == "month":
        return "month", period.amount
    if period.unit == "quarter":
        return "month", period.amount * 3
    if period.unit == "year":
        return "month", period.amount * 12
    return None


def _approximate_period_days(period: PeriodValue) -> int | None:
    multipliers = {
        "business_day": 1,
        "day": 1,
        "week": 7,
        "month": 30,
        "quarter": 90,
        "year": 365,
    }
    multiplier = multipliers.get(period.unit)
    return None if multiplier is None else period.amount * multiplier


def _first_applicable(
    items: tuple[AuditedContractItem, ...],
    item_type: str,
) -> AuditedContractItem | None:
    return next(
        (
            item
            for item in items
            if item.draft.item_type == item_type
            and item.is_applicable
            and item.effective_value is not None
        ),
        None,
    )


def _temporal_review(
    issues: list[ContractIssueDraft],
    item: AuditedContractItem,
    message: str,
) -> None:
    _issue(issues, item, "temporal_review_required", "warning", message)


def _issue(
    issues: list[ContractIssueDraft],
    item: AuditedContractItem,
    code: str,
    severity: IssueSeverity,
    message: str,
) -> None:
    issues.append(
        ContractIssueDraft(
            code=code,
            severity=severity,
            message=message,
            item_key=item.draft.item_key,
        )
    )


def _item_sort_key(item: EffectiveContractItem) -> tuple[int, int, str]:
    return (
        CONTRACT_SECTIONS.index(item.draft.section),
        item.draft.display_order,
        item.draft.item_key,
    )
