"""Value objects and limits for evidence-linked summaries.

Every published claim is an AI draft whose quotes are proven to be exact
spans of the current Reader; quotation integrity is not semantic entailment.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from glyph.models import Block

SUMMARY_SCHEMA_VERSION = "summary.v1"
SummaryStatus = Literal["not_generated", "generating", "available", "stale", "failed"]
SUMMARY_JOB_STATUSES = ("queued", "running", "completed", "failed", "interrupted")
MAX_CLAIM_TEXT_CHARS = 2_000
MAX_CLAIMS_PER_VERSION = 400
MAX_QUOTES_PER_CLAIM = 12


class SummaryValidationError(ValueError):
    """Provider output that cannot be published as evidence-linked claims."""


@dataclass(frozen=True)
class QuoteDraft:
    block_id: str
    quote_text: str
    quote_start: int | None = None
    quote_end: int | None = None


@dataclass(frozen=True)
class ClaimDraft:
    section_path: str | None
    text: str
    evidence: tuple[QuoteDraft, ...]


@dataclass(frozen=True)
class AcceptedQuote:
    block_id: str
    quote_text: str
    quote_start: int
    quote_end: int
    source_quote_hash: str
    page_number: int


@dataclass(frozen=True)
class AcceptedClaim:
    section_path: str | None
    text: str
    evidence: tuple[AcceptedQuote, ...]


def compute_reader_fingerprint(blocks: Iterable[Block]) -> str:
    """Identity of the exact attached block set: ids, order and text."""
    canonical = json.dumps(
        [[block.id, block.order_index, block.source_text] for block in blocks],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
