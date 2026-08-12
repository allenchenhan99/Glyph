from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, TypeVar

CONTRACT_SCHEMA_VERSION = "1"
MAX_VALUE_BYTES = 16_384
MAX_TEXT_LENGTH = 4_000
MAX_VARIABLES = 64
MAX_LIST_VALUES = 100

ContractSection = Literal[
    "thesis",
    "data_requirements",
    "universe_and_sample",
    "signal_and_timing",
    "portfolio_construction",
    "evaluation",
    "frictions_and_risks",
    "open_decisions",
]
ContractItemType = Literal[
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
]
ContractOrigin = Literal["author_explicit", "derived", "human_decision", "missing"]
ContractGenerationStatus = Literal["building", "complete", "partial", "failed"]
ContractReadiness = Literal["blocked", "review_needed", "implementation_ready"]
ResolutionStatus = Literal[
    "confirmed", "corrected", "decided", "questioned", "not_applicable"
]
IssueSeverity = Literal["info", "warning", "error"]
DiffClassification = Literal[
    "unchanged",
    "value_changed",
    "origin_changed",
    "evidence_changed",
    "added",
    "removed",
]
RuleOperator = Literal["include", "exclude", "rank", "threshold"]
PeriodUnit = Literal["business_day", "day", "week", "month", "quarter", "year"]

CONTRACT_SECTIONS: tuple[ContractSection, ...] = (
    "thesis",
    "data_requirements",
    "universe_and_sample",
    "signal_and_timing",
    "portfolio_construction",
    "evaluation",
    "frictions_and_risks",
    "open_decisions",
)
CONTRACT_ITEM_TYPES: tuple[ContractItemType, ...] = (
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
CONTRACT_ORIGINS: tuple[ContractOrigin, ...] = (
    "author_explicit",
    "derived",
    "human_decision",
    "missing",
)
GENERATION_STATUSES: tuple[ContractGenerationStatus, ...] = (
    "building",
    "complete",
    "partial",
    "failed",
)
READINESS_STATES: tuple[ContractReadiness, ...] = (
    "blocked",
    "review_needed",
    "implementation_ready",
)
RESOLUTION_STATUSES: tuple[ResolutionStatus, ...] = (
    "confirmed",
    "corrected",
    "decided",
    "questioned",
    "not_applicable",
)
ISSUE_SEVERITIES: tuple[IssueSeverity, ...] = ("info", "warning", "error")
DIFF_CLASSIFICATIONS: tuple[DiffClassification, ...] = (
    "unchanged",
    "value_changed",
    "origin_changed",
    "evidence_changed",
    "added",
    "removed",
)
RULE_OPERATORS: tuple[RuleOperator, ...] = (
    "include",
    "exclude",
    "rank",
    "threshold",
)
PERIOD_UNITS: tuple[PeriodUnit, ...] = (
    "business_day",
    "day",
    "week",
    "month",
    "quarter",
    "year",
)

_HTML_PATTERN = re.compile(r"</?[A-Za-z][^>]*>")
_URL_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:/|[A-Za-z]:[\\/])")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class InvalidContractValueError(ValueError):
    """Raised when contract data escapes the versioned typed schema."""


ControlledValue = TypeVar(
    "ControlledValue",
    ContractSection,
    ContractItemType,
    ContractOrigin,
    ContractGenerationStatus,
    ContractReadiness,
    ResolutionStatus,
    IssueSeverity,
    DiffClassification,
    RuleOperator,
    PeriodUnit,
)


def _validate_controlled_value(
    field_name: str,
    value: str,
    allowed: tuple[ControlledValue, ...],
) -> ControlledValue:
    if value not in allowed:
        raise InvalidContractValueError(f"Unknown {field_name}: {value}")
    return value


def validate_contract_section(value: str) -> ContractSection:
    return _validate_controlled_value("contract section", value, CONTRACT_SECTIONS)


def validate_contract_item_type(value: str) -> ContractItemType:
    return _validate_controlled_value("contract item type", value, CONTRACT_ITEM_TYPES)


def validate_contract_origin(value: str) -> ContractOrigin:
    return _validate_controlled_value("contract origin", value, CONTRACT_ORIGINS)


def validate_generation_status(value: str) -> ContractGenerationStatus:
    return _validate_controlled_value("generation status", value, GENERATION_STATUSES)


def validate_readiness(value: str) -> ContractReadiness:
    return _validate_controlled_value("readiness", value, READINESS_STATES)


def validate_resolution_status(value: str) -> ResolutionStatus:
    return _validate_controlled_value("resolution status", value, RESOLUTION_STATUSES)


def validate_issue_severity(value: str) -> IssueSeverity:
    return _validate_controlled_value("issue severity", value, ISSUE_SEVERITIES)


def validate_diff_classification(value: str) -> DiffClassification:
    return _validate_controlled_value(
        "diff classification", value, DIFF_CLASSIFICATIONS
    )


@dataclass(frozen=True)
class ScalarValue:
    kind: Literal["scalar"]
    value: str | int | float | bool
    unit: str | None = None


@dataclass(frozen=True)
class FormulaValue:
    kind: Literal["formula"]
    expression: str
    variables: tuple[str, ...]


@dataclass(frozen=True)
class RuleValue:
    kind: Literal["rule"]
    operator: RuleOperator
    field: str
    value: ScalarValue


@dataclass(frozen=True)
class ListValue:
    kind: Literal["list"]
    values: tuple[ScalarValue, ...]


@dataclass(frozen=True)
class RangeValue:
    kind: Literal["range"]
    minimum: ScalarValue
    maximum: ScalarValue
    include_minimum: bool
    include_maximum: bool


@dataclass(frozen=True)
class PeriodValue:
    kind: Literal["period"]
    amount: int
    unit: PeriodUnit
    anchor: str | None = None


ContractValue: TypeAlias = (
    ScalarValue | FormulaValue | RuleValue | ListValue | RangeValue | PeriodValue
)
_CONTRACT_VALUE_TYPES = (
    ScalarValue,
    FormulaValue,
    RuleValue,
    ListValue,
    RangeValue,
    PeriodValue,
)


@dataclass(frozen=True)
class ContractItemDraft:
    item_key: str
    section: ContractSection
    item_type: ContractItemType
    value: ContractValue | None
    origin: ContractOrigin
    rationale: str | None
    is_blocking: bool
    is_optional: bool
    display_order: int

    def __post_init__(self) -> None:
        _validate_safe_text("item key", self.item_key, max_length=128)
        validate_contract_section(self.section)
        validate_contract_item_type(self.item_type)
        validate_contract_origin(self.origin)
        if self.value is not None and not isinstance(self.value, _CONTRACT_VALUE_TYPES):
            raise InvalidContractValueError("Item value is not a ContractValue")
        if self.value is not None:
            encode_contract_value(self.value)
        if self.origin == "missing" and self.value is not None:
            raise InvalidContractValueError("A missing item must not have a value")
        if self.origin != "missing" and self.value is None:
            raise InvalidContractValueError(f"A {self.origin} item requires a value")
        if self.origin == "human_decision":
            raise InvalidContractValueError(
                "A provider draft cannot claim a human_decision origin"
            )
        if self.rationale is not None:
            _validate_safe_text("rationale", self.rationale)
        if self.display_order < 0:
            raise InvalidContractValueError("display_order cannot be negative")


@dataclass(frozen=True)
class ContractResolutionDraft:
    status: ResolutionStatus
    value: ContractValue | None
    reason: str | None

    def __post_init__(self) -> None:
        validate_resolution_status(self.status)
        if self.value is not None and not isinstance(self.value, _CONTRACT_VALUE_TYPES):
            raise InvalidContractValueError("Resolution value is not a ContractValue")
        normalized_reason = self.reason.strip() if self.reason else None
        if normalized_reason is not None:
            _validate_safe_text("resolution reason", normalized_reason)
        if self.status in ("corrected", "decided") and (
            self.value is None or normalized_reason is None
        ):
            raise InvalidContractValueError(
                f"A {self.status} resolution requires a value and reason"
            )
        if self.status == "not_applicable":
            if normalized_reason is None:
                raise InvalidContractValueError(
                    "A not_applicable resolution requires a reason"
                )
            if self.value is not None:
                raise InvalidContractValueError(
                    "A not_applicable resolution must not have a value"
                )
        if self.status in ("confirmed", "questioned") and self.value is not None:
            raise InvalidContractValueError(
                f"A {self.status} resolution must not have a replacement value"
            )


@dataclass(frozen=True)
class ContractIssueDraft:
    code: str
    severity: IssueSeverity
    message: str
    item_key: str | None = None

    def __post_init__(self) -> None:
        _validate_safe_text("issue code", self.code, max_length=64)
        validate_issue_severity(self.severity)
        _validate_safe_text("issue message", self.message)
        if self.item_key is not None:
            _validate_safe_text("issue item key", self.item_key, max_length=128)


def decode_contract_value(payload: object) -> ContractValue:
    _validate_payload_size(payload)
    if not isinstance(payload, Mapping):
        raise InvalidContractValueError("Contract value must be an object")
    kind = payload.get("kind")
    if not isinstance(kind, str):
        raise InvalidContractValueError("Contract value requires a string kind")
    if kind == "scalar":
        return _decode_scalar(payload)
    if kind == "formula":
        return _decode_formula(payload)
    if kind == "rule":
        return _decode_rule(payload)
    if kind == "list":
        return _decode_list(payload)
    if kind == "range":
        return _decode_range(payload)
    if kind == "period":
        return _decode_period(payload)
    raise InvalidContractValueError(f"Unknown contract value kind: {kind}")


def encode_contract_value(value: ContractValue) -> str:
    if not isinstance(value, _CONTRACT_VALUE_TYPES):
        raise InvalidContractValueError("Value is not a ContractValue")
    payload = _value_payload(value)
    decode_contract_value(payload)
    return _canonical_json(payload)


def item_signature(
    draft: ContractItemDraft,
    evidence_hashes: Sequence[str],
) -> str:
    hashes = sorted(evidence_hashes)
    if any(_HASH_PATTERN.fullmatch(value) is None for value in hashes):
        raise InvalidContractValueError("Evidence hashes must be lowercase SHA-256")
    payload = {
        "item_type": draft.item_type,
        "value": (
            json.loads(encode_contract_value(draft.value))
            if draft.value is not None
            else None
        ),
        "origin": draft.origin,
        "rationale": draft.rationale,
        "evidence_hashes": hashes,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _decode_scalar(payload: Mapping[object, object]) -> ScalarValue:
    _require_keys(payload, required={"kind", "value"}, optional={"unit"})
    raw_value = payload["value"]
    if isinstance(raw_value, bool):
        value: str | int | float | bool = raw_value
    elif isinstance(raw_value, int):
        value = raw_value
    elif isinstance(raw_value, float):
        if not math.isfinite(raw_value):
            raise InvalidContractValueError("Scalar numbers must be finite")
        value = raw_value
    elif isinstance(raw_value, str):
        _validate_safe_text("scalar value", raw_value)
        value = raw_value
    else:
        raise InvalidContractValueError("Scalar value must be a scalar primitive")
    unit = _optional_text(payload.get("unit"), "scalar unit", max_length=64)
    return ScalarValue(kind="scalar", value=value, unit=unit)


def _decode_formula(payload: Mapping[object, object]) -> FormulaValue:
    _require_keys(payload, required={"kind", "expression", "variables"})
    expression = _required_text(payload["expression"], "formula expression")
    raw_variables = payload["variables"]
    if not isinstance(raw_variables, list):
        raise InvalidContractValueError("Formula variables must be a list")
    if len(raw_variables) > MAX_VARIABLES:
        raise InvalidContractValueError("Formula variables allow at most 64 values")
    variables = tuple(
        _required_text(value, "formula variable", max_length=128)
        for value in raw_variables
    )
    return FormulaValue(kind="formula", expression=expression, variables=variables)


def _decode_rule(payload: Mapping[object, object]) -> RuleValue:
    _require_keys(payload, required={"kind", "operator", "field", "value"})
    operator_raw = _required_text(payload["operator"], "rule operator", max_length=32)
    operator = _validate_controlled_value("rule operator", operator_raw, RULE_OPERATORS)
    field = _required_text(payload["field"], "rule field", max_length=128)
    value = decode_contract_value(payload["value"])
    if not isinstance(value, ScalarValue):
        raise InvalidContractValueError("Rule value must be scalar")
    return RuleValue(kind="rule", operator=operator, field=field, value=value)


def _decode_list(payload: Mapping[object, object]) -> ListValue:
    _require_keys(payload, required={"kind", "values"})
    raw_values = payload["values"]
    if not isinstance(raw_values, list):
        raise InvalidContractValueError("List values must be a list")
    if not raw_values:
        raise InvalidContractValueError("List values cannot be empty")
    if len(raw_values) > MAX_LIST_VALUES:
        raise InvalidContractValueError("List values allow at most 100 entries")
    values: list[ScalarValue] = []
    for raw_value in raw_values:
        value = decode_contract_value(raw_value)
        if not isinstance(value, ScalarValue):
            raise InvalidContractValueError("List entries must be scalar")
        values.append(value)
    return ListValue(kind="list", values=tuple(values))


def _decode_range(payload: Mapping[object, object]) -> RangeValue:
    _require_keys(
        payload,
        required={
            "kind",
            "minimum",
            "maximum",
            "include_minimum",
            "include_maximum",
        },
    )
    minimum = decode_contract_value(payload["minimum"])
    maximum = decode_contract_value(payload["maximum"])
    if not isinstance(minimum, ScalarValue) or not isinstance(maximum, ScalarValue):
        raise InvalidContractValueError("Range bounds must be scalar")
    include_minimum = payload["include_minimum"]
    include_maximum = payload["include_maximum"]
    if not isinstance(include_minimum, bool) or not isinstance(include_maximum, bool):
        raise InvalidContractValueError("Range inclusion flags must be boolean")
    return RangeValue(
        kind="range",
        minimum=minimum,
        maximum=maximum,
        include_minimum=include_minimum,
        include_maximum=include_maximum,
    )


def _decode_period(payload: Mapping[object, object]) -> PeriodValue:
    _require_keys(
        payload,
        required={"kind", "amount", "unit"},
        optional={"anchor"},
    )
    amount = payload["amount"]
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise InvalidContractValueError("Period amount must be a positive integer")
    unit_raw = _required_text(payload["unit"], "period unit", max_length=32)
    unit = _validate_controlled_value("period unit", unit_raw, PERIOD_UNITS)
    anchor = _optional_text(payload.get("anchor"), "period anchor", max_length=128)
    return PeriodValue(kind="period", amount=amount, unit=unit, anchor=anchor)


def _value_payload(value: ContractValue) -> dict[str, object]:
    if isinstance(value, ScalarValue):
        return {"kind": value.kind, "value": value.value, "unit": value.unit}
    if isinstance(value, FormulaValue):
        return {
            "kind": value.kind,
            "expression": value.expression,
            "variables": list(value.variables),
        }
    if isinstance(value, RuleValue):
        return {
            "kind": value.kind,
            "operator": value.operator,
            "field": value.field,
            "value": _value_payload(value.value),
        }
    if isinstance(value, ListValue):
        return {
            "kind": value.kind,
            "values": [_value_payload(item) for item in value.values],
        }
    if isinstance(value, RangeValue):
        return {
            "kind": value.kind,
            "minimum": _value_payload(value.minimum),
            "maximum": _value_payload(value.maximum),
            "include_minimum": value.include_minimum,
            "include_maximum": value.include_maximum,
        }
    return {
        "kind": value.kind,
        "amount": value.amount,
        "unit": value.unit,
        "anchor": value.anchor,
    }


def _validate_payload_size(payload: object) -> None:
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise InvalidContractValueError(
            "Contract value is not JSON serializable"
        ) from exc
    if len(encoded.encode("utf-8")) > MAX_VALUE_BYTES:
        raise InvalidContractValueError("Contract value is too large")


def _require_keys(
    payload: Mapping[object, object],
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    if any(not isinstance(key, str) for key in payload):
        raise InvalidContractValueError("Contract value keys must be strings")
    actual = set(payload)
    missing = required - actual
    if missing:
        raise InvalidContractValueError(
            f"Missing keys: {', '.join(sorted(str(key) for key in missing))}"
        )
    unknown = actual - required - (optional or set())
    if unknown:
        raise InvalidContractValueError(
            f"Unknown keys: {', '.join(sorted(str(key) for key in unknown))}"
        )


def _required_text(
    value: object, field_name: str, *, max_length: int = MAX_TEXT_LENGTH
) -> str:
    if not isinstance(value, str):
        raise InvalidContractValueError(f"{field_name} must be text")
    _validate_safe_text(field_name, value, max_length=max_length)
    return value


def _optional_text(
    value: object,
    field_name: str,
    *,
    max_length: int = MAX_TEXT_LENGTH,
) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name, max_length=max_length)


def _validate_safe_text(
    field_name: str,
    value: str,
    *,
    max_length: int = MAX_TEXT_LENGTH,
) -> None:
    if not value.strip():
        raise InvalidContractValueError(f"{field_name} cannot be empty")
    if len(value) > max_length:
        raise InvalidContractValueError(
            f"{field_name} exceeds the {max_length}-character limit"
        )
    if _URL_PATTERN.search(value):
        raise InvalidContractValueError(f"{field_name} cannot contain a URL")
    if _ABSOLUTE_PATH_PATTERN.search(value):
        raise InvalidContractValueError(f"{field_name} cannot contain an absolute path")
    if _HTML_PATTERN.search(value):
        raise InvalidContractValueError(f"{field_name} cannot contain HTML")


def _canonical_json(payload: object) -> str:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise InvalidContractValueError("Contract value is not canonical JSON") from exc
