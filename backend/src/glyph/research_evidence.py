from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from glyph.models import Block, Document
from glyph.research_domain import (
    EvidenceRelation,
    InvalidDomainValueError,
    LocatorType,
    validate_evidence_relation,
    validate_locator_type,
)

MAX_EVIDENCE_QUOTE_LENGTH = 8_000

_URL_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_HTML_PATTERN = re.compile(r"<\s*/?\s*[a-z][^>]*>", re.IGNORECASE)
_WINDOWS_ABSOLUTE_PATH_PATTERN = re.compile(r"^[a-z]:[\\/]", re.IGNORECASE)


class InvalidEvidenceError(ValueError):
    """Raised when an evidence anchor cannot be proven against Reader text."""


@dataclass(frozen=True)
class EvidenceCandidate:
    block_id: str
    quote_text: str
    relation: str
    locator_type: str
    quote_start: int | None = None
    quote_end: int | None = None
    source_label: str | None = None

    def __post_init__(self) -> None:
        _validate_structured_text("block_id", self.block_id)
        if self.source_label is not None:
            _validate_structured_text("source_label", self.source_label)
        if not self.quote_text.strip():
            raise InvalidEvidenceError("quote_text must be non-empty")
        if len(self.quote_text) > MAX_EVIDENCE_QUOTE_LENGTH:
            raise InvalidEvidenceError("quote_text exceeds the evidence length limit")
        if (self.quote_start is None) != (self.quote_end is None):
            raise InvalidEvidenceError(
                "quote_start and quote_end must both be provided or both be omitted"
            )
        try:
            validate_evidence_relation(self.relation)
            validate_locator_type(self.locator_type)
        except InvalidDomainValueError as exc:
            raise InvalidEvidenceError(str(exc)) from exc


@dataclass(frozen=True)
class AcceptedEvidence:
    block_id: str
    quote_text: str
    quote_start: int
    quote_end: int
    relation: EvidenceRelation
    locator_type: LocatorType
    source_quote_hash: str
    source_label: str | None = None


def validate_candidate(
    session: Session,
    document: Document,
    candidate: EvidenceCandidate,
) -> AcceptedEvidence:
    block = session.get(Block, candidate.block_id)
    if block is None:
        raise InvalidEvidenceError(
            f"Evidence block {candidate.block_id} does not exist"
        )
    if block.document_id != document.id:
        raise InvalidEvidenceError("Evidence block belongs to another document")

    quote_start, quote_end = _resolve_offsets(block.source_text, candidate)
    actual_quote = block.source_text[quote_start:quote_end]
    if actual_quote != candidate.quote_text:
        raise InvalidEvidenceError(
            "Evidence quote does not match the target Reader block offsets"
        )

    relation = validate_evidence_relation(candidate.relation)
    locator_type = validate_locator_type(candidate.locator_type)
    return AcceptedEvidence(
        block_id=block.id,
        quote_text=candidate.quote_text,
        quote_start=quote_start,
        quote_end=quote_end,
        relation=relation,
        locator_type=locator_type,
        source_quote_hash=_quote_hash(
            block.id, quote_start, quote_end, candidate.quote_text
        ),
        source_label=candidate.source_label,
    )


def validate_candidates(
    session: Session,
    document: Document,
    candidates: Iterable[EvidenceCandidate],
) -> tuple[AcceptedEvidence, ...]:
    accepted: list[AcceptedEvidence] = []
    seen: set[tuple[str, int, int, EvidenceRelation, LocatorType]] = set()
    for candidate in candidates:
        anchor = validate_candidate(session, document, candidate)
        identity = (
            anchor.block_id,
            anchor.quote_start,
            anchor.quote_end,
            anchor.relation,
            anchor.locator_type,
        )
        if identity not in seen:
            seen.add(identity)
            accepted.append(anchor)
    return tuple(accepted)


def _resolve_offsets(
    source_text: str,
    candidate: EvidenceCandidate,
) -> tuple[int, int]:
    if candidate.quote_start is None:
        first_match = source_text.find(candidate.quote_text)
        if first_match == -1:
            raise InvalidEvidenceError(
                "Evidence quote does not occur in the target block"
            )
        if source_text.find(candidate.quote_text, first_match + 1) != -1:
            raise InvalidEvidenceError(
                "Evidence quote occurs more than once; explicit offsets are required"
            )
        return first_match, first_match + len(candidate.quote_text)

    quote_start = candidate.quote_start
    quote_end = candidate.quote_end
    if quote_end is None:
        raise InvalidEvidenceError(
            "quote_start and quote_end must both be provided or both be omitted"
        )
    if quote_start < 0 or quote_end > len(source_text):
        raise InvalidEvidenceError("Evidence offsets are outside the target block")
    if quote_end <= quote_start:
        raise InvalidEvidenceError("Evidence offsets must select non-empty text")
    return quote_start, quote_end


def _quote_hash(block_id: str, quote_start: int, quote_end: int, quote: str) -> str:
    canonical = json.dumps(
        [block_id, quote_start, quote_end, quote],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_structured_text(field_name: str, value: str) -> None:
    if not value.strip():
        raise InvalidEvidenceError(f"{field_name} must be non-empty")
    is_absolute_path = (
        value.startswith(("/", "~/"))
        or _WINDOWS_ABSOLUTE_PATH_PATTERN.search(value) is not None
    )
    if (
        is_absolute_path
        or _URL_PATTERN.search(value) is not None
        or _HTML_PATTERN.search(value) is not None
    ):
        raise InvalidEvidenceError(
            f"{field_name} cannot contain a URL, absolute path, or HTML"
        )
