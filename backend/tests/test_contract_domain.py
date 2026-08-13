import json
import math

import pytest


def domain():
    from glyph import contract_domain

    return contract_domain


def test_schema_v1_vocabulary_is_closed_and_complete():
    contract_domain = domain()

    assert contract_domain.CONTRACT_SCHEMA_VERSION == "1"
    assert contract_domain.CONTRACT_SECTIONS == (
        "thesis",
        "data_requirements",
        "universe_and_sample",
        "signal_and_timing",
        "portfolio_construction",
        "evaluation",
        "frictions_and_risks",
        "open_decisions",
    )
    assert contract_domain.CONTRACT_ITEM_TYPES == (
        "required_dataset",
        "required_field",
        "data_frequency",
        "availability_lag",
        "sample_period",
        "universe_filter",
        "sample_filter",
        "signal_formula",
        "signal_direction",
        "formation_date",
        "lookback_window",
        "weighting_rule",
        "rebalance_frequency",
        "holding_period",
        "long_short_definition",
        "benchmark_model",
        "evaluation_metric",
        "statistical_test",
        "transaction_cost",
        "turnover_assumption",
        "survivorship_risk",
        "lookahead_risk",
        "implementation_constraint",
    )
    assert contract_domain.CONTRACT_ORIGINS == (
        "author_explicit",
        "derived",
        "human_decision",
        "missing",
    )
    assert contract_domain.GENERATION_STATUSES == (
        "building",
        "complete",
        "partial",
        "failed",
    )
    assert contract_domain.READINESS_STATES == (
        "blocked",
        "review_needed",
        "implementation_ready",
    )
    assert contract_domain.RESOLUTION_STATUSES == (
        "confirmed",
        "corrected",
        "decided",
        "questioned",
        "not_applicable",
    )
    assert contract_domain.ISSUE_SEVERITIES == ("info", "warning", "error")
    assert contract_domain.DIFF_CLASSIFICATIONS == (
        "unchanged",
        "type_changed",
        "value_changed",
        "origin_changed",
        "evidence_changed",
        "added",
        "removed",
    )


@pytest.mark.parametrize(
    ("validator_name", "value"),
    [
        ("validate_contract_section", "chat"),
        ("validate_contract_item_type", "magic_default"),
        ("validate_contract_origin", "ai_guess"),
        ("validate_generation_status", "ready"),
        ("validate_readiness", "profitable"),
        ("validate_resolution_status", "accepted"),
        ("validate_issue_severity", "critical"),
        ("validate_diff_classification", "changed"),
    ],
)
def test_unknown_controlled_values_are_rejected(validator_name, value):
    contract_domain = domain()

    with pytest.raises(contract_domain.InvalidContractValueError, match="Unknown"):
        getattr(contract_domain, validator_name)(value)


def test_scalar_value_has_canonical_json_and_round_trips():
    contract_domain = domain()
    payload = {"unit": "percent", "value": 1.25, "kind": "scalar"}

    value = contract_domain.decode_contract_value(payload)

    assert value == contract_domain.ScalarValue(
        kind="scalar", value=1.25, unit="percent"
    )
    assert contract_domain.encode_contract_value(value) == (
        '{"kind":"scalar","unit":"percent","value":1.25}'
    )
    assert (
        contract_domain.decode_contract_value(
            json.loads(contract_domain.encode_contract_value(value))
        )
        == value
    )


def test_all_typed_values_round_trip_without_shape_loss():
    contract_domain = domain()
    payloads = (
        {"kind": "scalar", "value": True, "unit": None},
        {
            "kind": "formula",
            "expression": "book_equity / market_equity",
            "variables": ["book_equity", "market_equity"],
        },
        {
            "kind": "rule",
            "operator": "threshold",
            "field": "price",
            "value": {"kind": "scalar", "value": 5, "unit": "USD"},
        },
        {
            "kind": "list",
            "values": [
                {"kind": "scalar", "value": "NYSE", "unit": None},
                {"kind": "scalar", "value": "NASDAQ", "unit": None},
            ],
        },
        {
            "kind": "range",
            "minimum": {"kind": "scalar", "value": 0, "unit": "percentile"},
            "maximum": {"kind": "scalar", "value": 10, "unit": "percentile"},
            "include_minimum": True,
            "include_maximum": False,
        },
        {
            "kind": "period",
            "amount": 6,
            "unit": "month",
            "anchor": "formation_date",
        },
    )

    for payload in payloads:
        decoded = contract_domain.decode_contract_value(payload)
        encoded = contract_domain.encode_contract_value(decoded)
        assert contract_domain.decode_contract_value(json.loads(encoded)) == decoded


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "kind"),
        ({"kind": "scalar", "value": 1, "surprise": True}, "Unknown keys"),
        ({"kind": "scalar", "value": math.nan, "unit": None}, "finite"),
        ({"kind": "scalar", "value": math.inf, "unit": None}, "finite"),
        ({"kind": "scalar", "value": {"nested": "object"}}, "scalar"),
        ({"kind": "scalar", "value": "https://example.com"}, "URL"),
        ({"kind": "scalar", "value": "/Users/research/data.csv"}, "absolute path"),
        ({"kind": "scalar", "value": "<script>alert(1)</script>"}, "HTML"),
        (
            {"kind": "formula", "expression": "x", "variables": ["x"] * 65},
            "at most 64",
        ),
        (
            {
                "kind": "list",
                "values": [
                    {"kind": "scalar", "value": index, "unit": None}
                    for index in range(101)
                ],
            },
            "at most 100",
        ),
    ],
)
def test_malformed_or_unsafe_typed_values_are_rejected(payload, message):
    contract_domain = domain()

    with pytest.raises(contract_domain.InvalidContractValueError, match=message):
        contract_domain.decode_contract_value(payload)


def test_oversized_typed_value_is_rejected_before_parsing():
    contract_domain = domain()

    with pytest.raises(contract_domain.InvalidContractValueError, match="too large"):
        contract_domain.decode_contract_value(
            {"kind": "scalar", "value": "x" * 20_000, "unit": None}
        )


def test_boolean_scalar_is_not_reencoded_as_integer():
    contract_domain = domain()
    value = contract_domain.decode_contract_value(
        {"kind": "scalar", "value": True, "unit": None}
    )

    assert isinstance(value.value, bool)
    assert contract_domain.encode_contract_value(value) == (
        '{"kind":"scalar","unit":null,"value":true}'
    )


def test_directly_constructed_values_cannot_bypass_canonical_validation():
    contract_domain = domain()

    with pytest.raises(contract_domain.InvalidContractValueError, match="URL"):
        contract_domain.encode_contract_value(
            contract_domain.ScalarValue("scalar", "https://example.com", None)
        )
    with pytest.raises(
        contract_domain.InvalidContractValueError, match="positive integer"
    ):
        contract_domain.encode_contract_value(
            contract_domain.PeriodValue("period", 0, "month", None)
        )


def test_missing_item_has_no_value_and_nonmissing_item_requires_one():
    contract_domain = domain()

    missing = contract_domain.ContractItemDraft(
        item_key="transaction_cost.1",
        section="frictions_and_risks",
        item_type="transaction_cost",
        value=None,
        origin="missing",
        rationale="The paper does not report transaction costs.",
        is_blocking=True,
        is_optional=False,
        display_order=0,
    )
    assert missing.value is None

    with pytest.raises(
        contract_domain.InvalidContractValueError, match="must not have"
    ):
        contract_domain.ContractItemDraft(
            item_key="transaction_cost.1",
            section="frictions_and_risks",
            item_type="transaction_cost",
            value=contract_domain.ScalarValue("scalar", 0, "bps"),
            origin="missing",
            rationale=None,
            is_blocking=True,
            is_optional=False,
            display_order=0,
        )
    with pytest.raises(
        contract_domain.InvalidContractValueError, match="requires a value"
    ):
        contract_domain.ContractItemDraft(
            item_key="holding_period.1",
            section="portfolio_construction",
            item_type="holding_period",
            value=None,
            origin="author_explicit",
            rationale=None,
            is_blocking=True,
            is_optional=False,
            display_order=0,
        )


def test_provider_draft_cannot_claim_a_human_decision():
    contract_domain = domain()

    with pytest.raises(
        contract_domain.InvalidContractValueError, match="provider draft"
    ):
        contract_domain.ContractItemDraft(
            item_key="weighting_rule.1",
            section="portfolio_construction",
            item_type="weighting_rule",
            value=contract_domain.ScalarValue("scalar", "equal_weight", None),
            origin="human_decision",
            rationale="Chosen by a model.",
            is_blocking=True,
            is_optional=False,
            display_order=0,
        )


@pytest.mark.parametrize("status", ["corrected", "decided"])
def test_corrected_and_decided_resolutions_require_value_and_reason(status):
    contract_domain = domain()

    with pytest.raises(
        contract_domain.InvalidContractValueError, match="value and reason"
    ):
        contract_domain.ContractResolutionDraft(
            status=status,
            value=None,
            reason=None,
        )


def test_not_applicable_resolution_requires_reason_and_forbids_value():
    contract_domain = domain()

    with pytest.raises(contract_domain.InvalidContractValueError, match="reason"):
        contract_domain.ContractResolutionDraft(
            status="not_applicable", value=None, reason=None
        )
    with pytest.raises(
        contract_domain.InvalidContractValueError, match="must not have"
    ):
        contract_domain.ContractResolutionDraft(
            status="not_applicable",
            value=contract_domain.ScalarValue("scalar", 0, None),
            reason="Not used in a gross replication.",
        )


def test_item_signature_is_order_independent_for_evidence_and_change_sensitive():
    contract_domain = domain()
    draft = contract_domain.ContractItemDraft(
        item_key="holding_period.1",
        section="portfolio_construction",
        item_type="holding_period",
        value=contract_domain.PeriodValue("period", 1, "month", "formation_date"),
        origin="author_explicit",
        rationale=None,
        is_blocking=True,
        is_optional=False,
        display_order=0,
    )
    hash_a = "a" * 64
    hash_b = "b" * 64

    signature = contract_domain.item_signature(draft, (hash_b, hash_a))

    assert signature == contract_domain.item_signature(draft, (hash_a, hash_b))
    assert len(signature) == 64
    changed = contract_domain.ContractItemDraft(
        item_key=draft.item_key,
        section=draft.section,
        item_type=draft.item_type,
        value=contract_domain.PeriodValue("period", 2, "month", "formation_date"),
        origin=draft.origin,
        rationale=draft.rationale,
        is_blocking=draft.is_blocking,
        is_optional=draft.is_optional,
        display_order=draft.display_order,
    )
    assert contract_domain.item_signature(changed, (hash_a, hash_b)) != signature
    renamed = contract_domain.ContractItemDraft(
        item_key="holding_period.secondary",
        section=draft.section,
        item_type=draft.item_type,
        value=draft.value,
        origin=draft.origin,
        rationale=draft.rationale,
        is_blocking=draft.is_blocking,
        is_optional=draft.is_optional,
        display_order=draft.display_order,
    )
    assert contract_domain.item_signature(renamed, (hash_a, hash_b)) != signature
