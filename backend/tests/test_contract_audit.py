from collections.abc import Iterable

import pytest

from glyph.contract_domain import (
    ContractItemDraft,
    ContractResolutionDraft,
    PeriodValue,
    ScalarValue,
)
from glyph.contract_evidence import AcceptedContractEvidence


def audit_module():
    from glyph import contract_audit

    return contract_audit


def evidence(seed: str = "a", *, relation: str = "supports"):
    return AcceptedContractEvidence(
        block_id=f"block-{seed}",
        research_node_id=None,
        quote_text=f"Supported statement {seed}",
        quote_start=0,
        quote_end=21,
        relation=relation,
        locator_type="text_span",
        source_quote_hash=seed * 64,
        source_label=None,
    )


def item(
    item_type: str,
    *,
    value=None,
    origin: str = "author_explicit",
    anchors: Iterable[AcceptedContractEvidence] = (),
    resolution: ContractResolutionDraft | None = None,
    rationale: str | None = None,
    blocking: bool = True,
    optional: bool = False,
    order: int = 0,
):
    module = audit_module()
    sections = {
        "required_dataset": "data_requirements",
        "required_field": "data_requirements",
        "data_frequency": "data_requirements",
        "availability_lag": "signal_and_timing",
        "formation_date": "signal_and_timing",
        "signal_formula": "signal_and_timing",
        "rebalance_frequency": "portfolio_construction",
        "holding_period": "portfolio_construction",
        "weighting_rule": "portfolio_construction",
        "benchmark_model": "evaluation",
        "evaluation_metric": "evaluation",
        "transaction_cost": "frictions_and_risks",
    }
    draft = ContractItemDraft(
        item_key=f"{item_type}.1",
        section=sections[item_type],
        item_type=item_type,
        value=value,
        origin=origin,
        rationale=rationale,
        is_blocking=blocking,
        is_optional=optional,
        display_order=order,
    )
    return module.EffectiveContractItem(
        draft=draft,
        evidence=tuple(anchors),
        resolution=resolution,
    )


def explicit_item(
    item_type: str = "holding_period",
    *,
    resolution: ContractResolutionDraft | None = None,
    blocking: bool = True,
):
    return item(
        item_type,
        value=PeriodValue("period", 1, "month", "formation_date"),
        anchors=(evidence(),),
        resolution=resolution,
        blocking=blocking,
    )


def confirmed():
    return ContractResolutionDraft(status="confirmed", value=None, reason=None)


@pytest.mark.parametrize(
    ("items", "expected_status", "expected_readiness", "issue_code"),
    [
        (
            lambda: (
                item(
                    "weighting_rule",
                    value=None,
                    origin="missing",
                    rationale="The paper does not state a weighting rule.",
                ),
            ),
            "complete",
            "blocked",
            "missing_blocker",
        ),
        (
            lambda: (
                item(
                    "signal_formula",
                    value=ScalarValue("scalar", "book_to_market", None),
                    origin="derived",
                    anchors=(evidence(),),
                    rationale="The formula follows the variable definitions.",
                ),
            ),
            "partial",
            "blocked",
            "derived_evidence_shortfall",
        ),
        (
            lambda: (
                item(
                    "holding_period",
                    value=PeriodValue("period", 1, "month", "formation_date"),
                    origin="author_explicit",
                ),
            ),
            "partial",
            "blocked",
            "explicit_without_evidence",
        ),
        (
            lambda: (explicit_item(),),
            "complete",
            "review_needed",
            "review_required",
        ),
        (
            lambda: (explicit_item(resolution=confirmed()),),
            "complete",
            "implementation_ready",
            None,
        ),
    ],
)
def test_readiness_matrix(
    items,
    expected_status,
    expected_readiness,
    issue_code,
):
    module = audit_module()

    audit = module.audit_contract(items())

    assert audit.generation_status == expected_status
    assert audit.readiness == expected_readiness
    codes = {issue.code for issue in audit.issues}
    assert issue_code is None or issue_code in codes


def test_derived_item_requires_two_supporting_anchors_and_rationale():
    module = audit_module()
    derived = item(
        "signal_formula",
        value=ScalarValue("scalar", "book_to_market", None),
        origin="derived",
        anchors=(evidence("a"), evidence("b", relation="qualifies")),
        rationale=None,
    )

    audit = module.audit_contract((derived,))

    assert audit.readiness == "blocked"
    assert {issue.code for issue in audit.issues} >= {
        "derived_evidence_shortfall",
        "derived_without_rationale",
    }


def test_accounting_data_available_after_formation_is_lookahead():
    module = audit_module()
    formation = item(
        "formation_date",
        value=PeriodValue("period", 4, "month", "fiscal_period_end"),
        anchors=(evidence("a"),),
        resolution=confirmed(),
    )
    availability = item(
        "availability_lag",
        value=PeriodValue("period", 6, "month", "fiscal_period_end"),
        anchors=(evidence("b"),),
        resolution=confirmed(),
    )

    audit = module.audit_contract((formation, availability))

    assert audit.readiness == "blocked"
    assert "lookahead_risk_detected" in {issue.code for issue in audit.issues}


def test_matching_accounting_lag_does_not_create_lookahead_issue():
    module = audit_module()
    items = (
        item(
            "formation_date",
            value=PeriodValue("period", 6, "month", "fiscal_period_end"),
            anchors=(evidence("a"),),
            resolution=confirmed(),
        ),
        item(
            "availability_lag",
            value=PeriodValue("period", 6, "month", "fiscal_period_end"),
            anchors=(evidence("b"),),
            resolution=confirmed(),
        ),
    )

    audit = module.audit_contract(items)

    assert "lookahead_risk_detected" not in {issue.code for issue in audit.issues}
    assert audit.readiness == "implementation_ready"


def test_incomparable_temporal_fields_require_review_instead_of_guessing():
    module = audit_module()
    items = (
        item(
            "formation_date",
            value=PeriodValue("period", 20, "business_day", "fiscal_period_end"),
            anchors=(evidence("a"),),
            resolution=confirmed(),
        ),
        item(
            "availability_lag",
            value=PeriodValue("period", 1, "month", "fiscal_period_end"),
            anchors=(evidence("b"),),
            resolution=confirmed(),
        ),
    )

    audit = module.audit_contract(items)

    assert audit.readiness == "review_needed"
    assert "temporal_review_required" in {issue.code for issue in audit.issues}


def test_holding_period_shorter_than_rebalance_frequency_creates_gap():
    module = audit_module()
    items = (
        item(
            "holding_period",
            value=PeriodValue("period", 1, "month", "formation_date"),
            anchors=(evidence("a"),),
            resolution=confirmed(),
        ),
        item(
            "rebalance_frequency",
            value=PeriodValue("period", 3, "month", "formation_date"),
            anchors=(evidence("b"),),
            resolution=confirmed(),
        ),
    )

    audit = module.audit_contract(items)

    assert audit.readiness == "blocked"
    assert "holding_rebalance_gap" in {issue.code for issue in audit.issues}


@pytest.mark.parametrize(
    ("data_frequency", "rebalance", "expect_mismatch"),
    [
        ("monthly", PeriodValue("period", 1, "day", "formation_date"), True),
        ("daily", PeriodValue("period", 1, "month", "formation_date"), False),
    ],
)
def test_data_frequency_must_support_rebalance_frequency(
    data_frequency,
    rebalance,
    expect_mismatch,
):
    module = audit_module()
    items = (
        item(
            "data_frequency",
            value=ScalarValue("scalar", data_frequency, None),
            anchors=(evidence("a"),),
            resolution=confirmed(),
        ),
        item(
            "rebalance_frequency",
            value=rebalance,
            anchors=(evidence("b"),),
            resolution=confirmed(),
        ),
    )

    codes = {issue.code for issue in module.audit_contract(items).issues}

    assert ("data_rebalance_frequency_mismatch" in codes) is expect_mismatch


def test_missing_transaction_cost_is_blocking_until_gross_replication_decision():
    module = audit_module()
    missing_cost = item(
        "transaction_cost",
        value=None,
        origin="missing",
        rationale="The paper does not report costs.",
    )
    gross_replication = item(
        "transaction_cost",
        value=None,
        origin="missing",
        rationale="The paper does not report costs.",
        resolution=ContractResolutionDraft(
            status="not_applicable",
            value=None,
            reason="Reproduce gross returns without a cost adjustment.",
        ),
    )

    blocked = module.audit_contract((missing_cost,))
    resolved = module.audit_contract((gross_replication,))

    assert blocked.readiness == "blocked"
    assert resolved.readiness == "implementation_ready"
    assert "missing_blocker" not in {issue.code for issue in resolved.issues}


@pytest.mark.parametrize(
    ("metric", "with_benchmark", "issue_code"),
    [
        ("factor_alpha", False, "benchmark_required"),
        ("raw_return", True, "benchmark_metric_mismatch"),
        ("factor_alpha", True, None),
    ],
)
def test_benchmark_must_match_the_evaluation_metric(
    metric,
    with_benchmark,
    issue_code,
):
    module = audit_module()
    items = [
        item(
            "evaluation_metric",
            value=ScalarValue("scalar", metric, None),
            anchors=(evidence("a"),),
            resolution=confirmed(),
        )
    ]
    if with_benchmark:
        items.append(
            item(
                "benchmark_model",
                value=ScalarValue("scalar", "fama_french_3_factor", None),
                anchors=(evidence("b"),),
                resolution=confirmed(),
                order=1,
            )
        )

    audit = module.audit_contract(items)
    codes = {issue.code for issue in audit.issues}

    assert (issue_code in codes) if issue_code else audit.readiness == "implementation_ready"


def test_questioned_blocking_item_cannot_be_ready():
    module = audit_module()
    questioned = explicit_item(
        resolution=ContractResolutionDraft(
            status="questioned",
            value=None,
            reason="The timing statement may refer to the robustness sample.",
        )
    )

    audit = module.audit_contract((questioned,))

    assert audit.readiness == "blocked"
    assert "blocking_item_questioned" in {issue.code for issue in audit.issues}


def test_optional_missing_item_does_not_block_a_reviewed_contract():
    module = audit_module()
    optional_cost = item(
        "transaction_cost",
        value=None,
        origin="missing",
        rationale="Optional sensitivity analysis is not reported.",
        blocking=False,
        optional=True,
    )

    audit = module.audit_contract(
        (explicit_item(resolution=confirmed()), optional_cost)
    )

    assert audit.readiness == "implementation_ready"
    assert "missing_blocker" not in {issue.code for issue in audit.issues}


def test_human_decision_requires_a_typed_value_and_reason():
    module = audit_module()
    decided = item(
        "weighting_rule",
        value=None,
        origin="missing",
        rationale="The paper omits portfolio weights.",
        resolution=ContractResolutionDraft(
            status="decided",
            value=ScalarValue("scalar", "equal_weight", None),
            reason="Use equal weights for the first reproduction attempt.",
        ),
    )

    audit = module.audit_contract((decided,))

    assert audit.readiness == "implementation_ready"
    assert audit.items[0].effective_origin == "human_decision"
    assert audit.items[0].effective_value == ScalarValue(
        "scalar", "equal_weight", None
    )


def test_audit_output_is_stable_under_input_ordering():
    module = audit_module()
    missing_cost = item(
        "transaction_cost",
        value=None,
        origin="missing",
        rationale="Costs are absent.",
        order=2,
    )
    unsupported = item(
        "holding_period",
        value=PeriodValue("period", 1, "month", "formation_date"),
        anchors=(),
        order=1,
    )

    forward = module.audit_contract((missing_cost, unsupported))
    reverse = module.audit_contract((unsupported, missing_cost))

    assert forward == reverse
    assert [(issue.severity, issue.code, issue.item_key) for issue in forward.issues] == sorted(
        (issue.severity, issue.code, issue.item_key) for issue in forward.issues
    )
