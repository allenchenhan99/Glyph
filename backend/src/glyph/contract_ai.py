from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from glyph.config import Settings
from glyph.contract_audit import EffectiveContractItem
from glyph.contract_domain import (
    ContractItemDraft,
    ContractItemType,
    ContractOrigin,
    ContractSection,
    ContractValue,
    FormulaValue,
    ListValue,
    PeriodUnit,
    PeriodValue,
    ScalarValue,
    validate_contract_item_type,
)
from glyph.contract_evidence import (
    AcceptedContractEvidence,
    ContractEvidenceCandidate,
    ContractEvidenceContext,
    validate_contract_candidate,
)
from glyph.models import Block


@dataclass(frozen=True)
class ContractInputBlock:
    id: str
    block_type: str
    source_text: str
    source_content_hash: str | None = None

    @classmethod
    def from_model(cls, block: Block) -> ContractInputBlock:
        return cls(
            id=block.id,
            block_type=block.block_type,
            source_text=block.source_text,
            source_content_hash=block.source_content_hash,
        )


@dataclass(frozen=True)
class ExtractedRequirementCandidate:
    evidence_id: str
    item_types: tuple[str, ...]
    block_id: str
    quote_text: str
    relation: str
    locator_type: str
    research_node_id: str | None = None
    quote_start: int | None = None
    quote_end: int | None = None
    source_label: str | None = None

    def __post_init__(self) -> None:
        if not self.evidence_id or any(
            marker in self.evidence_id.lower()
            for marker in ("/", "\\", "http:", "https:", "<", ">")
        ):
            raise ValueError("evidence_id must be an opaque identifier")
        if not self.item_types:
            raise ValueError("A requirement candidate must identify an item type")
        for item_type in self.item_types:
            validate_contract_item_type(item_type)
        _ = self.anchor

    @property
    def anchor(self) -> ContractEvidenceCandidate:
        return ContractEvidenceCandidate(
            block_id=self.block_id,
            research_node_id=self.research_node_id,
            quote_text=self.quote_text,
            quote_start=self.quote_start,
            quote_end=self.quote_end,
            relation=self.relation,
            locator_type=self.locator_type,
            source_label=self.source_label,
        )


@dataclass(frozen=True)
class ValidatedContractEvidence:
    evidence_id: str
    item_types: tuple[ContractItemType, ...]
    anchor: AcceptedContractEvidence


@dataclass(frozen=True)
class SynthesizedContractItem:
    draft: ContractItemDraft
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_ids, tuple):
            raise TypeError("evidence_ids must be an immutable tuple")


class ImplementationContractProvider(Protocol):
    provider_name: str
    model_name: str | None

    def extract_requirements(
        self, blocks: Sequence[ContractInputBlock]
    ) -> tuple[ExtractedRequirementCandidate, ...]: ...

    def synthesize_contract(
        self, evidence: Sequence[ValidatedContractEvidence]
    ) -> tuple[SynthesizedContractItem, ...]: ...


_PREFIX_ITEM_TYPES: dict[str, tuple[ContractItemType, ...]] = {
    "Thesis:": ("signal_direction",),
    "Data:": ("required_dataset", "data_frequency"),
    "Fields:": ("required_field",),
    "Availability:": ("availability_lag",),
    "Formation:": ("formation_date",),
    "Universe:": ("universe_filter",),
    "Signal:": ("signal_formula", "signal_direction"),
    "Direction:": ("signal_direction",),
    "Portfolio:": ("weighting_rule", "rebalance_frequency", "holding_period"),
    "Weighting:": ("weighting_rule",),
    "Evaluation:": ("benchmark_model", "evaluation_metric", "statistical_test"),
    "Friction:": ("transaction_cost", "turnover_assumption"),
    "Risk:": ("survivorship_risk", "lookahead_risk", "implementation_constraint"),
}


@dataclass(frozen=True)
class _ItemRule:
    item_key: str
    section: ContractSection
    item_type: ContractItemType
    value: ContractValue | None
    evidence_prefixes: tuple[str, ...]
    display_order: int
    origin: ContractOrigin = "author_explicit"
    rationale: str | None = None
    is_blocking: bool = True
    is_optional: bool = False


def _scalar(value: str | int, unit: str | None = None) -> ScalarValue:
    return ScalarValue(kind="scalar", value=value, unit=unit)


def _list(*values: str) -> ListValue:
    return ListValue(
        kind="list",
        values=tuple(_scalar(value) for value in values),
    )


def _formula(expression: str, *variables: str) -> FormulaValue:
    return FormulaValue(kind="formula", expression=expression, variables=variables)


def _period(amount: int, unit: PeriodUnit, anchor: str) -> PeriodValue:
    return PeriodValue(kind="period", amount=amount, unit=unit, anchor=anchor)


_MONTHLY_RULES: tuple[_ItemRule, ...] = (
    _ItemRule(
        "required_dataset.1",
        "data_requirements",
        "required_dataset",
        _list("Compustat", "CRSP"),
        ("Data:",),
        0,
    ),
    _ItemRule(
        "required_field.1",
        "data_requirements",
        "required_field",
        _list(
            "book_equity",
            "market_equity",
            "monthly_return",
            "exchange_code",
            "share_code",
            "market_capitalization",
        ),
        ("Fields:",),
        1,
    ),
    _ItemRule(
        "data_frequency.1",
        "data_requirements",
        "data_frequency",
        _scalar("monthly"),
        ("Data:",),
        2,
    ),
    _ItemRule(
        "availability_lag.1",
        "signal_and_timing",
        "availability_lag",
        _period(6, "month", "fiscal_period_end"),
        ("Availability:",),
        0,
    ),
    _ItemRule(
        "universe_filter.1",
        "universe_and_sample",
        "universe_filter",
        _scalar("NYSE_AMEX_NASDAQ_common_positive_book_equity_price_above_5"),
        ("Universe:",),
        0,
    ),
    _ItemRule(
        "signal_formula.1",
        "signal_and_timing",
        "signal_formula",
        _formula("book_equity / market_equity", "book_equity", "market_equity"),
        ("Signal:",),
        1,
    ),
    _ItemRule(
        "signal_direction.1",
        "signal_and_timing",
        "signal_direction",
        _scalar("high_signal_long_low_signal_short"),
        ("Thesis:", "Signal:"),
        2,
        origin="derived",
        rationale="The thesis and signal definition jointly establish the portfolio direction.",
    ),
    _ItemRule(
        "formation_date.1",
        "signal_and_timing",
        "formation_date",
        _period(6, "month", "fiscal_period_end"),
        ("Formation:",),
        3,
    ),
    _ItemRule(
        "weighting_rule.1",
        "portfolio_construction",
        "weighting_rule",
        _scalar("value_weight"),
        ("Portfolio:",),
        0,
    ),
    _ItemRule(
        "rebalance_frequency.1",
        "portfolio_construction",
        "rebalance_frequency",
        _period(1, "month", "formation_date"),
        ("Portfolio:",),
        1,
    ),
    _ItemRule(
        "holding_period.1",
        "portfolio_construction",
        "holding_period",
        _period(1, "month", "formation_date"),
        ("Portfolio:",),
        2,
    ),
    _ItemRule(
        "benchmark_model.1",
        "evaluation",
        "benchmark_model",
        _scalar("fama_french_3_factor"),
        ("Evaluation:",),
        0,
    ),
    _ItemRule(
        "evaluation_metric.1",
        "evaluation",
        "evaluation_metric",
        _scalar("factor_alpha"),
        ("Evaluation:",),
        1,
    ),
    _ItemRule(
        "statistical_test.1",
        "evaluation",
        "statistical_test",
        _scalar("newey_west_t_statistic"),
        ("Evaluation:",),
        2,
    ),
    _ItemRule(
        "transaction_cost.1",
        "frictions_and_risks",
        "transaction_cost",
        _scalar(20, "basis_points_per_one_way_trade"),
        ("Friction:",),
        0,
    ),
    _ItemRule(
        "survivorship_risk.1",
        "frictions_and_risks",
        "survivorship_risk",
        _scalar("include_delistings_forbid_survivorship_histories"),
        ("Risk:",),
        1,
    ),
)

_DAILY_RULES: tuple[_ItemRule, ...] = (
    _ItemRule(
        "required_dataset.1",
        "data_requirements",
        "required_dataset",
        _list("split_adjusted_daily_close", "daily_total_return"),
        ("Data:",),
        0,
    ),
    _ItemRule(
        "required_field.1",
        "data_requirements",
        "required_field",
        _list(
            "adjusted_close",
            "total_return",
            "trading_date",
            "share_code",
            "median_dollar_volume_20d",
        ),
        ("Fields:",),
        1,
    ),
    _ItemRule(
        "data_frequency.1",
        "data_requirements",
        "data_frequency",
        _scalar("daily"),
        ("Data:",),
        2,
    ),
    _ItemRule(
        "availability_lag.1",
        "signal_and_timing",
        "availability_lag",
        _period(1, "business_day", "session_close"),
        ("Availability:",),
        0,
    ),
    _ItemRule(
        "universe_filter.1",
        "universe_and_sample",
        "universe_filter",
        _scalar("US_common_stocks_median_dollar_volume_20d_above_10m"),
        ("Universe:",),
        0,
    ),
    _ItemRule(
        "signal_formula.1",
        "signal_and_timing",
        "signal_formula",
        _formula("product(1 + daily_return[1:20]) - 1", "daily_return"),
        ("Signal:",),
        1,
    ),
    _ItemRule(
        "signal_direction.1",
        "signal_and_timing",
        "signal_direction",
        _scalar("high_signal_long_low_signal_short"),
        ("Direction:",),
        2,
    ),
    _ItemRule(
        "formation_date.1",
        "signal_and_timing",
        "formation_date",
        _period(1, "business_day", "session_close"),
        ("Formation:",),
        3,
    ),
    _ItemRule(
        "weighting_rule.1",
        "portfolio_construction",
        "weighting_rule",
        _scalar("equal_weight"),
        ("Portfolio:",),
        0,
    ),
    _ItemRule(
        "rebalance_frequency.1",
        "portfolio_construction",
        "rebalance_frequency",
        _period(5, "business_day", "formation_date"),
        ("Portfolio:",),
        1,
    ),
    _ItemRule(
        "holding_period.1",
        "portfolio_construction",
        "holding_period",
        _period(5, "business_day", "formation_date"),
        ("Portfolio:",),
        2,
    ),
    _ItemRule(
        "evaluation_metric.1",
        "evaluation",
        "evaluation_metric",
        _scalar("raw_return"),
        ("Evaluation:",),
        0,
    ),
    _ItemRule(
        "statistical_test.1",
        "evaluation",
        "statistical_test",
        _scalar("heteroskedasticity_consistent_t_statistic"),
        ("Evaluation:",),
        1,
    ),
    _ItemRule(
        "transaction_cost.1",
        "frictions_and_risks",
        "transaction_cost",
        _scalar(10, "basis_points_per_entry_and_exit"),
        ("Friction:",),
        0,
    ),
    _ItemRule(
        "turnover_assumption.1",
        "frictions_and_risks",
        "turnover_assumption",
        _scalar("measure_on_each_rebalance_date"),
        ("Friction:",),
        1,
        is_blocking=False,
    ),
    _ItemRule(
        "implementation_constraint.1",
        "frictions_and_risks",
        "implementation_constraint",
        _scalar("split_adjust_prices_and_returns_before_signal"),
        ("Risk:",),
        2,
    ),
)

_CROSS_MARKET_RULES: tuple[_ItemRule, ...] = (
    _ItemRule(
        "required_dataset.1",
        "data_requirements",
        "required_dataset",
        _list("US_daily_prices_and_returns", "Japan_daily_prices_and_returns"),
        ("Data:",),
        0,
    ),
    _ItemRule(
        "required_field.1",
        "data_requirements",
        "required_field",
        _list(
            "adjusted_close",
            "total_return",
            "market_identifier",
            "local_trading_date",
            "security_type",
        ),
        ("Fields:",),
        1,
    ),
    _ItemRule(
        "data_frequency.1",
        "data_requirements",
        "data_frequency",
        _scalar("daily"),
        ("Data:",),
        2,
    ),
    _ItemRule(
        "availability_lag.1",
        "signal_and_timing",
        "availability_lag",
        _period(1, "business_day", "aligned_market_close"),
        ("Availability:",),
        0,
    ),
    _ItemRule(
        "universe_filter.1",
        "universe_and_sample",
        "universe_filter",
        _scalar("local_common_stocks_with_120_valid_returns"),
        ("Universe:",),
        0,
    ),
    _ItemRule(
        "signal_formula.1",
        "signal_and_timing",
        "signal_formula",
        _formula(
            "cumulative_return_60_business_days_excluding_latest_5",
            "daily_total_return",
        ),
        ("Signal:",),
        1,
    ),
    _ItemRule(
        "signal_direction.1",
        "signal_and_timing",
        "signal_direction",
        _scalar("top_quintile_long_bottom_quintile_short_by_market"),
        ("Direction:",),
        2,
    ),
    _ItemRule(
        "formation_date.1",
        "signal_and_timing",
        "formation_date",
        _period(1, "business_day", "aligned_market_close"),
        ("Formation:",),
        3,
    ),
    _ItemRule(
        "weighting_rule.1",
        "portfolio_construction",
        "weighting_rule",
        None,
        ("Weighting:",),
        0,
        origin="missing",
        rationale="The paper explicitly leaves within-quintile weighting unspecified.",
    ),
    _ItemRule(
        "rebalance_frequency.1",
        "portfolio_construction",
        "rebalance_frequency",
        _period(1, "month", "formation_date"),
        ("Portfolio:",),
        1,
    ),
    _ItemRule(
        "holding_period.1",
        "portfolio_construction",
        "holding_period",
        _period(1, "month", "formation_date"),
        ("Portfolio:",),
        2,
    ),
    _ItemRule(
        "evaluation_metric.1",
        "evaluation",
        "evaluation_metric",
        _scalar("raw_return"),
        ("Evaluation:",),
        0,
    ),
    _ItemRule(
        "statistical_test.1",
        "evaluation",
        "statistical_test",
        _scalar("block_bootstrap_confidence_interval"),
        ("Evaluation:",),
        1,
    ),
    _ItemRule(
        "transaction_cost.1",
        "frictions_and_risks",
        "transaction_cost",
        None,
        ("Friction:",),
        0,
        origin="missing",
        rationale="The paper explicitly does not report transaction costs or market impact.",
    ),
    _ItemRule(
        "lookahead_risk.1",
        "frictions_and_risks",
        "lookahead_risk",
        _scalar("never_fill_local_holidays_with_future_prices"),
        ("Risk:",),
        1,
    ),
)


class MockImplementationContractProvider:
    provider_name = "mock"
    model_name: str | None = None

    def extract_requirements(
        self, blocks: Sequence[ContractInputBlock]
    ) -> tuple[ExtractedRequirementCandidate, ...]:
        candidates: list[ExtractedRequirementCandidate] = []
        for block in blocks:
            offset = 0
            for raw_line in block.source_text.splitlines(keepends=True):
                quote_text = raw_line.rstrip("\r\n")
                quote_start = offset
                quote_end = quote_start + len(quote_text)
                offset += len(raw_line)
                item_types = next(
                    (
                        types
                        for prefix, types in _PREFIX_ITEM_TYPES.items()
                        if quote_text.startswith(prefix)
                    ),
                    None,
                )
                if item_types is None:
                    continue
                relation = (
                    "context"
                    if "does not specify" in quote_text or "not reported" in quote_text
                    else "supports"
                )
                candidates.append(
                    ExtractedRequirementCandidate(
                        evidence_id=_evidence_id(
                            block.id, quote_start, quote_end, quote_text
                        ),
                        item_types=item_types,
                        block_id=block.id,
                        quote_text=quote_text,
                        quote_start=quote_start,
                        quote_end=quote_end,
                        relation=relation,
                        locator_type="text_span",
                        source_label=quote_text.partition(":")[0],
                    )
                )
        return tuple(candidates)

    def synthesize_contract(
        self, evidence: Sequence[ValidatedContractEvidence]
    ) -> tuple[SynthesizedContractItem, ...]:
        if not all(isinstance(item, ValidatedContractEvidence) for item in evidence):
            raise TypeError("synthesize_contract requires validated contract evidence")
        evidence_by_prefix = {
            prefix: item
            for item in evidence
            for prefix in _PREFIX_ITEM_TYPES
            if item.anchor.quote_text.startswith(prefix)
        }
        rules = _rules_for_evidence(evidence)
        synthesized: list[SynthesizedContractItem] = []
        for rule in rules:
            if not all(
                prefix in evidence_by_prefix for prefix in rule.evidence_prefixes
            ):
                continue
            referenced = tuple(
                evidence_by_prefix[prefix].evidence_id
                for prefix in rule.evidence_prefixes
            )
            synthesized.append(
                SynthesizedContractItem(
                    draft=ContractItemDraft(
                        item_key=rule.item_key,
                        section=rule.section,
                        item_type=rule.item_type,
                        value=rule.value,
                        origin=rule.origin,
                        rationale=rule.rationale,
                        is_blocking=rule.is_blocking,
                        is_optional=rule.is_optional,
                        display_order=rule.display_order,
                    ),
                    evidence_ids=referenced,
                )
            )
        return tuple(synthesized)


def create_implementation_contract_provider(
    settings: Settings,
) -> ImplementationContractProvider:
    if settings.ai_mode == "mock":
        return MockImplementationContractProvider()
    if settings.ai_mode in {"claude_cli", "codex_cli"}:
        from glyph.contract_cli_ai import CliImplementationContractProvider

        return CliImplementationContractProvider(
            provider=settings.ai_mode.removesuffix("_cli"),
            model=settings.cli_model,
            timeout_seconds=settings.cli_timeout_seconds,
            block_batch_size=settings.contract_cli_block_batch_size,
            concurrency=settings.cli_concurrency,
            cache_dir=settings.data_dir / "implementation-contract-ai-cache",
        )
    raise RuntimeError(f"Unknown Implementation Contract AI mode: {settings.ai_mode}")


def validate_extracted_requirements(
    session: Session,
    context: ContractEvidenceContext,
    candidates: Sequence[ExtractedRequirementCandidate],
) -> tuple[ValidatedContractEvidence, ...]:
    accepted: list[ValidatedContractEvidence] = []
    evidence_ids: set[str] = set()
    for candidate in candidates:
        if candidate.evidence_id in evidence_ids:
            raise ValueError(f"Duplicate evidence ID: {candidate.evidence_id}")
        evidence_ids.add(candidate.evidence_id)
        accepted.append(
            ValidatedContractEvidence(
                evidence_id=candidate.evidence_id,
                item_types=tuple(
                    validate_contract_item_type(item_type)
                    for item_type in candidate.item_types
                ),
                anchor=validate_contract_candidate(session, context, candidate.anchor),
            )
        )
    return tuple(accepted)


def validate_synthesized_contract(
    items: Sequence[SynthesizedContractItem],
    evidence: Sequence[ValidatedContractEvidence],
) -> tuple[EffectiveContractItem, ...]:
    accepted_by_id = {item.evidence_id: item for item in evidence}
    if len(accepted_by_id) != len(evidence):
        raise ValueError("Validated contract evidence IDs must be unique")
    seen_item_keys: set[str] = set()
    effective: list[EffectiveContractItem] = []
    for item in items:
        if not isinstance(item, SynthesizedContractItem):
            raise TypeError("Contract output must contain synthesized contract items")
        item_key = item.draft.item_key
        if item_key in seen_item_keys:
            raise ValueError(f"Duplicate contract item key: {item_key}")
        seen_item_keys.add(item_key)
        unknown_ids = set(item.evidence_ids) - accepted_by_id.keys()
        if unknown_ids:
            raise ValueError(f"Unaccepted evidence ID: {min(unknown_ids)}")
        for evidence_id in item.evidence_ids:
            if item.draft.item_type not in accepted_by_id[evidence_id].item_types:
                raise ValueError(
                    f"Evidence ID {evidence_id} was not extracted for "
                    f"{item.draft.item_type}"
                )
        effective.append(
            EffectiveContractItem(
                draft=item.draft,
                evidence=tuple(
                    accepted_by_id[evidence_id].anchor
                    for evidence_id in item.evidence_ids
                ),
            )
        )
    return tuple(effective)


def _rules_for_evidence(
    evidence: Sequence[ValidatedContractEvidence],
) -> tuple[_ItemRule, ...]:
    text = "\n".join(item.anchor.quote_text for item in evidence)
    if "Compustat annual book equity" in text:
        return _MONTHLY_RULES
    if "liquid US common stocks" in text:
        return _DAILY_RULES
    if "US and Japanese common stocks" in text:
        return _CROSS_MARKET_RULES
    return ()


def _evidence_id(
    block_id: str,
    quote_start: int,
    quote_end: int,
    quote_text: str,
) -> str:
    digest = hashlib.sha256(
        f"{block_id}\0{quote_start}\0{quote_end}\0{quote_text}".encode()
    ).hexdigest()[:20]
    return f"contract-evidence-{digest}"
