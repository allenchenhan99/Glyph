from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from glyph.models import Block, Document, ResearchMapVersion, ResearchNode
from glyph.research_domain import (
    EvidenceRelation,
    InvalidDomainValueError,
    LocatorType,
    validate_evidence_relation,
    validate_locator_type,
)
from glyph.research_evidence import (
    MAX_EVIDENCE_QUOTE_LENGTH,
    ExactQuoteError,
    exact_quote_hash,
    resolve_exact_quote,
)

_URL_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_HTML_PATTERN = re.compile(r"<\s*/?\s*[a-z][^>]*>", re.IGNORECASE)
_WINDOWS_ABSOLUTE_PATH_PATTERN = re.compile(r"^[a-z]:[\\/]", re.IGNORECASE)
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class InvalidContractEvidenceError(ValueError):
    """Raised when a contract anchor cannot be proven against its inputs."""


@dataclass(frozen=True)
class ContractEvidenceContext:
    document_id: str
    source_content_hash: str
    research_map_version_id: str

    def __post_init__(self) -> None:
        _validate_structured_text("document_id", self.document_id)
        _validate_structured_text(
            "research_map_version_id", self.research_map_version_id
        )
        if _HASH_PATTERN.fullmatch(self.source_content_hash) is None:
            raise InvalidContractEvidenceError(
                "source_content_hash must be a lowercase SHA-256 hash"
            )


@dataclass(frozen=True)
class ContractEvidenceCandidate:
    block_id: str
    quote_text: str
    relation: str
    locator_type: str
    research_node_id: str | None = None
    quote_start: int | None = None
    quote_end: int | None = None
    source_label: str | None = None

    def __post_init__(self) -> None:
        _validate_structured_text("block_id", self.block_id)
        if self.research_node_id is not None:
            _validate_structured_text("research_node_id", self.research_node_id)
        if self.source_label is not None:
            _validate_structured_text("source_label", self.source_label)
        if not self.quote_text.strip():
            raise InvalidContractEvidenceError("quote_text must be non-empty")
        if len(self.quote_text) > MAX_EVIDENCE_QUOTE_LENGTH:
            raise InvalidContractEvidenceError(
                "quote_text exceeds the evidence length limit"
            )
        if (self.quote_start is None) != (self.quote_end is None):
            raise InvalidContractEvidenceError(
                "quote_start and quote_end must both be provided or both be omitted"
            )
        try:
            validate_evidence_relation(self.relation)
            validate_locator_type(self.locator_type)
        except InvalidDomainValueError as exc:
            raise InvalidContractEvidenceError(str(exc)) from exc


@dataclass(frozen=True)
class AcceptedContractEvidence:
    block_id: str
    research_node_id: str | None
    quote_text: str
    quote_start: int
    quote_end: int
    relation: EvidenceRelation
    locator_type: LocatorType
    source_quote_hash: str
    source_label: str | None = None


def validate_contract_candidate(
    session: Session,
    context: ContractEvidenceContext,
    candidate: ContractEvidenceCandidate,
) -> AcceptedContractEvidence:
    document = session.get(Document, context.document_id)
    if document is None:
        raise InvalidContractEvidenceError("Contract document does not exist")
    map_version = session.get(ResearchMapVersion, context.research_map_version_id)
    if map_version is None:
        raise InvalidContractEvidenceError("Contract Research Map does not exist")
    if (
        map_version.document_id != context.document_id
        or map_version.source_content_hash != context.source_content_hash
    ):
        raise InvalidContractEvidenceError(
            "Contract Research Map must match the context document and source"
        )
    if (
        document.content_hash != context.source_content_hash
        or document.processed_content_hash != context.source_content_hash
    ):
        raise InvalidContractEvidenceError(
            "Contract evidence requires the current Reader source"
        )

    block = session.get(Block, candidate.block_id)
    if block is None:
        raise InvalidContractEvidenceError(
            f"Evidence block {candidate.block_id} does not exist"
        )
    if block.document_id != context.document_id:
        raise InvalidContractEvidenceError("Evidence block belongs to another document")
    if block.source_content_hash != context.source_content_hash:
        raise InvalidContractEvidenceError(
            "Evidence block does not belong to the current Reader source"
        )

    if candidate.research_node_id is not None:
        node = session.get(ResearchNode, candidate.research_node_id)
        if node is None:
            raise InvalidContractEvidenceError("Linked Research Map node does not exist")
        if node.map_version_id != context.research_map_version_id:
            raise InvalidContractEvidenceError(
                "Linked node must belong to the same Research Map"
            )

    try:
        quote_start, quote_end = resolve_exact_quote(
            block.source_text,
            candidate.quote_text,
            candidate.quote_start,
            candidate.quote_end,
        )
    except ExactQuoteError as exc:
        raise InvalidContractEvidenceError(str(exc)) from exc

    relation = validate_evidence_relation(candidate.relation)
    locator_type = validate_locator_type(candidate.locator_type)
    return AcceptedContractEvidence(
        block_id=block.id,
        research_node_id=candidate.research_node_id,
        quote_text=candidate.quote_text,
        quote_start=quote_start,
        quote_end=quote_end,
        relation=relation,
        locator_type=locator_type,
        source_quote_hash=exact_quote_hash(
            block.id,
            quote_start,
            quote_end,
            candidate.quote_text,
        ),
        source_label=candidate.source_label,
    )


def validate_contract_candidates(
    session: Session,
    context: ContractEvidenceContext,
    candidates: Iterable[ContractEvidenceCandidate],
) -> tuple[AcceptedContractEvidence, ...]:
    accepted: list[AcceptedContractEvidence] = []
    seen: set[tuple[str, int, int, EvidenceRelation]] = set()
    for candidate in candidates:
        anchor = validate_contract_candidate(session, context, candidate)
        identity = (
            anchor.block_id,
            anchor.quote_start,
            anchor.quote_end,
            anchor.relation,
        )
        if identity not in seen:
            seen.add(identity)
            accepted.append(anchor)
    return tuple(accepted)


def _validate_structured_text(field_name: str, value: str) -> None:
    if not value.strip():
        raise InvalidContractEvidenceError(f"{field_name} must be non-empty")
    is_absolute_path = (
        value.startswith(("/", "~/"))
        or _WINDOWS_ABSOLUTE_PATH_PATTERN.search(value) is not None
    )
    if (
        is_absolute_path
        or _URL_PATTERN.search(value) is not None
        or _HTML_PATTERN.search(value) is not None
    ):
        raise InvalidContractEvidenceError(
            f"{field_name} cannot contain a URL, absolute path, or HTML"
        )
