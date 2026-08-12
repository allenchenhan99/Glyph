from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from glyph.config import Settings
from glyph.models import Block, Document
from glyph.research_domain import (
    EvidenceQuality,
    NodeType,
    Provenance,
    validate_evidence_quality,
    validate_node_type,
    validate_provenance,
)
from glyph.research_evidence import (
    AcceptedEvidence,
    EvidenceCandidate,
    validate_candidate,
)

CORE_NODE_GROUPS: dict[str, frozenset[NodeType]] = {
    "question": frozenset({"author_claim", "hypothesis"}),
    "data": frozenset({"data_and_sample", "data_source", "sample_filter"}),
    "signal": frozenset({"signal_definition", "variable_definition"}),
    "method": frozenset(
        {
            "portfolio_construction",
            "rebalancing_rule",
            "empirical_method",
            "benchmark_model",
            "identification_strategy",
        }
    ),
    "result": frozenset(
        {"primary_result", "statistical_evidence", "economic_magnitude"}
    ),
    "limitations": frozenset(
        {"limitations", "implementation_constraint", "alternative_explanation"}
    ),
}


@dataclass(frozen=True)
class ResearchBlock:
    id: str
    block_type: str
    source_text: str
    source_content_hash: str | None = None

    @classmethod
    def from_model(cls, block: Block) -> ResearchBlock:
        return cls(
            id=block.id,
            block_type=block.block_type,
            source_text=block.source_text,
            source_content_hash=block.source_content_hash,
        )


@dataclass(frozen=True)
class ExtractedEvidenceCandidate:
    evidence_id: str
    node_type: str
    block_id: str
    quote_text: str
    relation: str
    locator_type: str
    quote_start: int | None = None
    quote_end: int | None = None
    source_label: str | None = None
    evidence_quality: str = "direct"
    provenance: str = "author_explicit"

    def __post_init__(self) -> None:
        validate_node_type(self.node_type)
        validate_evidence_quality(self.evidence_quality)
        validate_provenance(self.provenance)
        if not self.evidence_id or any(
            marker in self.evidence_id.lower()
            for marker in ("/", "\\", "http:", "https:", "<", ">")
        ):
            raise ValueError("evidence_id must be an opaque identifier")
        _ = self.anchor

    @property
    def anchor(self) -> EvidenceCandidate:
        return EvidenceCandidate(
            block_id=self.block_id,
            quote_text=self.quote_text,
            quote_start=self.quote_start,
            quote_end=self.quote_end,
            relation=self.relation,
            locator_type=self.locator_type,
            source_label=self.source_label,
        )


@dataclass(frozen=True)
class ValidatedEvidence:
    evidence_id: str
    node_type: NodeType
    anchor: AcceptedEvidence
    evidence_quality: EvidenceQuality = "direct"
    provenance: Provenance = "author_explicit"


@dataclass(frozen=True)
class NodeDraft:
    node_key: str
    node_type: NodeType
    title: str
    claim_text: str
    explanation: str
    provenance: Provenance
    evidence_quality: EvidenceQuality
    evidence_ids: tuple[str, ...]
    display_order: int
    parent_node_key: str | None = None

    def __post_init__(self) -> None:
        validate_node_type(self.node_type)
        validate_provenance(self.provenance)
        validate_evidence_quality(self.evidence_quality)
        if not self.node_key or not self.title.strip() or not self.claim_text.strip():
            raise ValueError("Research Map node identity and claim fields are required")
        if not isinstance(self.evidence_ids, tuple):
            raise TypeError("evidence_ids must be an immutable tuple")


class ResearchMapProvider(Protocol):
    name: str
    model_name: str | None

    def extract_candidates(
        self, blocks: Sequence[ResearchBlock]
    ) -> tuple[ExtractedEvidenceCandidate, ...]: ...

    def synthesize_nodes(
        self, evidence: Sequence[ValidatedEvidence]
    ) -> tuple[NodeDraft, ...]: ...


@dataclass(frozen=True)
class _MockRule:
    prefix: str
    node_type: NodeType
    title: str
    evidence_quality: EvidenceQuality = "direct"


_MOCK_RULES: tuple[_MockRule, ...] = (
    _MockRule("Research Question:", "author_claim", "Research question"),
    _MockRule("Data Source:", "data_source", "Data source"),
    _MockRule("Sample:", "data_and_sample", "Data and sample"),
    _MockRule("Signal:", "signal_definition", "Signal definition"),
    _MockRule("Portfolio:", "portfolio_construction", "Portfolio construction"),
    _MockRule("Rebalancing:", "rebalancing_rule", "Rebalancing rule"),
    _MockRule("Method:", "empirical_method", "Empirical method"),
    _MockRule("Benchmark:", "benchmark_model", "Benchmark model"),
    _MockRule("Primary Result:", "primary_result", "Primary result"),
    _MockRule("Primary Result:", "statistical_evidence", "Statistical evidence"),
    _MockRule("Robustness:", "robustness_test", "Robustness"),
    _MockRule(
        "Transaction Costs:",
        "transaction_cost",
        "Transaction costs",
        "not_reported",
    ),
    _MockRule("Limitations:", "limitations", "Limitations"),
)
_TITLES_BY_NODE_TYPE = {rule.node_type: rule.title for rule in _MOCK_RULES}


class MockResearchMapProvider:
    name = "mock"
    model_name: str | None = None

    def extract_candidates(
        self, blocks: Sequence[ResearchBlock]
    ) -> tuple[ExtractedEvidenceCandidate, ...]:
        candidates: list[ExtractedEvidenceCandidate] = []
        for block in blocks:
            for rule in _MOCK_RULES:
                if block.source_text.startswith(rule.prefix):
                    candidates.append(
                        ExtractedEvidenceCandidate(
                            evidence_id=_evidence_id(rule.node_type, block),
                            node_type=rule.node_type,
                            block_id=block.id,
                            quote_text=block.source_text,
                            quote_start=0,
                            quote_end=len(block.source_text),
                            relation="supports",
                            locator_type="text_span",
                            source_label=rule.title,
                            evidence_quality=rule.evidence_quality,
                        )
                    )
        return tuple(candidates)

    def synthesize_nodes(
        self, evidence: Sequence[ValidatedEvidence]
    ) -> tuple[NodeDraft, ...]:
        if not all(isinstance(item, ValidatedEvidence) for item in evidence):
            raise TypeError("synthesize_nodes requires validated evidence")

        counts: defaultdict[NodeType, int] = defaultdict(int)
        nodes: list[NodeDraft] = []
        for display_order, item in enumerate(evidence):
            counts[item.node_type] += 1
            claim_text = _claim_from_quote(item.anchor.quote_text)
            nodes.append(
                NodeDraft(
                    node_key=f"{item.node_type}.{counts[item.node_type]}",
                    node_type=item.node_type,
                    title=_TITLES_BY_NODE_TYPE[item.node_type],
                    claim_text=claim_text,
                    explanation="",
                    provenance=item.provenance,
                    evidence_quality=item.evidence_quality,
                    evidence_ids=(item.evidence_id,),
                    display_order=display_order,
                )
            )
        return tuple(nodes)


def create_research_map_provider(settings: Settings) -> ResearchMapProvider:
    if settings.ai_mode == "mock":
        return MockResearchMapProvider()
    if settings.ai_mode in {"claude_cli", "codex_cli"}:
        from glyph.research_cli_ai import CliResearchMapProvider

        return CliResearchMapProvider(
            provider=settings.ai_mode.removesuffix("_cli"),
            model=settings.cli_model,
            timeout_seconds=settings.cli_timeout_seconds,
            block_batch_size=settings.research_cli_block_batch_size,
            concurrency=settings.cli_concurrency,
            cache_dir=settings.data_dir / "research-map-ai-cache",
        )
    raise RuntimeError(f"Unknown Research Map AI mode: {settings.ai_mode}")


def validate_extracted_candidates(
    session: Session,
    document: Document,
    candidates: Sequence[ExtractedEvidenceCandidate],
) -> tuple[ValidatedEvidence, ...]:
    accepted: list[ValidatedEvidence] = []
    evidence_ids: set[str] = set()
    for candidate in candidates:
        if candidate.evidence_id in evidence_ids:
            raise ValueError(f"Duplicate evidence ID: {candidate.evidence_id}")
        evidence_ids.add(candidate.evidence_id)
        accepted.append(
            ValidatedEvidence(
                evidence_id=candidate.evidence_id,
                node_type=validate_node_type(candidate.node_type),
                anchor=validate_candidate(session, document, candidate.anchor),
                evidence_quality=validate_evidence_quality(candidate.evidence_quality),
                provenance=validate_provenance(candidate.provenance),
            )
        )
    return tuple(accepted)


def _evidence_id(node_type: NodeType, block: ResearchBlock) -> str:
    digest = hashlib.sha256(
        f"{node_type}\0{block.id}\0{block.source_text}".encode()
    ).hexdigest()[:20]
    return f"evidence-{digest}"


def _claim_from_quote(quote: str) -> str:
    _, separator, claim = quote.partition(":")
    return claim.strip() if separator else quote.strip()
