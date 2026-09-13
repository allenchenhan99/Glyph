"""Evidence-linked summary inputs, validation, publication and state views.

Inputs are the attached Reader blocks (``section_id IS NOT NULL``) of the
current completed snapshot. Their fingerprint, not the source hash alone,
identifies the exact Reader that a version summarizes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from glyph.config import Settings
from glyph.models import (
    Block,
    Document,
    Section,
    SummaryClaim,
    SummaryEvidence,
    SummaryJob,
    SummaryVersion,
)
from glyph.research_evidence import (
    ExactQuoteError,
    exact_quote_hash,
    resolve_exact_quote,
)
from glyph.summary_domain import (
    MAX_CLAIM_TEXT_CHARS,
    MAX_CLAIMS_PER_VERSION,
    MAX_QUOTES_PER_CLAIM,
    AcceptedClaim,
    AcceptedQuote,
    ClaimDraft,
    SummaryStatus,
    SummaryValidationError,
    compute_reader_fingerprint,
)

ACTIVE_JOB_STATUSES = ("queued", "running")


class SummaryConflictError(RuntimeError):
    """The Reader is not in a state that allows generation or publication."""


class SummaryNotFoundError(LookupError):
    """The document does not exist."""


@dataclass(frozen=True)
class SummaryInputs:
    document_id: str
    source_content_hash: str
    reader_fingerprint: str
    blocks: tuple[Block, ...]
    section_paths: tuple[str, ...]
    section_path_by_block_id: dict[str, str | None]

    def section_path_of(self, block: Block) -> str | None:
        return self.section_path_by_block_id.get(block.id)


@dataclass(frozen=True)
class EvidenceView:
    block_id: str
    quote_text: str
    quote_start: int
    quote_end: int
    page_number: int


@dataclass(frozen=True)
class ClaimView:
    id: str
    section_path: str | None
    text: str
    evidence: tuple[EvidenceView, ...]


@dataclass(frozen=True)
class SummaryVersionView:
    id: str
    source_content_hash: str
    reader_fingerprint: str
    provider: str
    model: str | None
    created_at: datetime
    claims: tuple[ClaimView, ...]


SummaryJobStatus = Literal["queued", "running", "completed", "failed", "interrupted"]


@dataclass(frozen=True)
class SummaryJobView:
    id: str
    status: SummaryJobStatus
    error_message: str | None


@dataclass(frozen=True)
class SummaryStateView:
    status: SummaryStatus
    provider: str
    model: str | None
    version: SummaryVersionView | None
    job: SummaryJobView | None


def current_reader_blocks(session: Session, document: Document) -> list[Block]:
    """Attached blocks of the current snapshot; retained citations are excluded."""
    return list(
        session.scalars(
            select(Block)
            .where(
                Block.document_id == document.id,
                Block.source_content_hash == document.processed_content_hash,
                Block.section_id.is_not(None),
            )
            .order_by(Block.order_index, Block.id)
        ).all()
    )


def capture_summary_inputs(session: Session, document_id: str) -> SummaryInputs:
    document = session.get(Document, document_id)
    if document is None:
        raise SummaryNotFoundError("Document not found")
    if (
        document.status != "completed"
        or document.processed_content_hash is None
        or document.processed_content_hash != document.content_hash
    ):
        raise SummaryConflictError(
            "Summaries require a current completed Reader snapshot"
        )
    blocks = current_reader_blocks(session, document)
    if not blocks:
        raise SummaryConflictError("Document has no current Reader blocks")
    sections = session.scalars(
        select(Section)
        .where(Section.document_id == document.id)
        .order_by(Section.order_index, Section.id)
    ).all()
    path_by_section_id = {section.id: section.path for section in sections}
    section_path_by_block_id = {
        block.id: path_by_section_id.get(block.section_id or "") for block in blocks
    }
    covered = {section_path_by_block_id[block.id] for block in blocks}
    section_paths = tuple(
        section.path for section in sections if section.path in covered
    )
    return SummaryInputs(
        document_id=document.id,
        source_content_hash=document.processed_content_hash,
        reader_fingerprint=compute_reader_fingerprint(blocks),
        blocks=tuple(blocks),
        section_paths=section_paths,
        section_path_by_block_id=section_path_by_block_id,
    )


def validate_claims(
    inputs: SummaryInputs, drafts: tuple[ClaimDraft, ...]
) -> tuple[AcceptedClaim, ...]:
    if not drafts:
        raise SummaryValidationError("Provider returned no claims")
    if len(drafts) > MAX_CLAIMS_PER_VERSION:
        raise SummaryValidationError(
            f"Provider returned more than {MAX_CLAIMS_PER_VERSION} claims"
        )
    block_by_id = {block.id: block for block in inputs.blocks}
    accepted: list[AcceptedClaim] = []
    for draft in drafts:
        text = draft.text.strip()
        if not text or len(text) > MAX_CLAIM_TEXT_CHARS:
            raise SummaryValidationError(
                "Claim text must be non-empty and within the length limit"
            )
        if (
            draft.section_path is not None
            and draft.section_path not in inputs.section_paths
        ):
            raise SummaryValidationError(
                f"Claim names an unknown section path: {draft.section_path!r}"
            )
        if not draft.evidence:
            raise SummaryValidationError(
                "Every claim needs at least one exact quote from the Reader"
            )
        if len(draft.evidence) > MAX_QUOTES_PER_CLAIM:
            raise SummaryValidationError("Claim cites too many quotes")
        quotes: list[AcceptedQuote] = []
        seen: set[tuple[str, int, int]] = set()
        for quote in draft.evidence:
            block = block_by_id.get(quote.block_id)
            if block is None:
                raise SummaryValidationError(
                    f"Evidence block {quote.block_id!r} is not in the permitted "
                    "Reader block set (it does not exist or is not current)"
                )
            if not quote.quote_text.strip():
                raise SummaryValidationError("quote_text must be non-empty")
            if (
                draft.section_path is not None
                and inputs.section_path_of(block) != draft.section_path
            ):
                raise SummaryValidationError(
                    "Section claims must cite blocks from their own section"
                )
            try:
                start, end = resolve_exact_quote(
                    block.source_text,
                    quote.quote_text,
                    quote.quote_start,
                    quote.quote_end,
                )
            except ExactQuoteError as exc:
                raise SummaryValidationError(str(exc)) from exc
            identity = (block.id, start, end)
            if identity in seen:
                continue
            seen.add(identity)
            quotes.append(
                AcceptedQuote(
                    block_id=block.id,
                    quote_text=quote.quote_text,
                    quote_start=start,
                    quote_end=end,
                    source_quote_hash=exact_quote_hash(
                        block.id, start, end, quote.quote_text
                    ),
                    page_number=block.page_number,
                )
            )
        accepted.append(AcceptedClaim(draft.section_path, text, tuple(quotes)))
    if not any(claim.section_path is None for claim in accepted):
        raise SummaryValidationError("Missing the document overview claim")
    covered = {claim.section_path for claim in accepted}
    missing = [path for path in inputs.section_paths if path not in covered]
    if missing:
        raise SummaryValidationError(
            "Missing section coverage for: " + ", ".join(missing)
        )
    return tuple(accepted)


def persist_summary_version(
    session: Session,
    inputs: SummaryInputs,
    accepted: tuple[AcceptedClaim, ...],
    *,
    provider: str,
    model: str | None,
) -> SummaryVersion:
    """Publish atomically after re-checking that the Reader is unchanged."""
    document = session.get(Document, inputs.document_id)
    if document is None:
        raise SummaryNotFoundError("Document not found")
    current = current_reader_blocks(session, document)
    if (
        document.processed_content_hash != inputs.source_content_hash
        or document.content_hash != inputs.source_content_hash
        or compute_reader_fingerprint(current) != inputs.reader_fingerprint
        or current_source_hash(document) != inputs.source_content_hash
    ):
        raise SummaryConflictError(
            "The Reader or its source file changed while the summary was being "
            "generated"
        )
    previous = session.scalar(
        select(SummaryVersion).where(
            SummaryVersion.document_id == document.id,
            SummaryVersion.is_active.is_(True),
        )
    )
    with session.begin_nested():
        version = SummaryVersion(
            id=str(uuid4()),
            document_id=document.id,
            previous_version_id=previous.id if previous is not None else None,
            source_content_hash=inputs.source_content_hash,
            reader_fingerprint=inputs.reader_fingerprint,
            provider=provider,
            model_name=model,
            is_active=False,
        )
        session.add(version)
        for order, claim in enumerate(accepted):
            row = SummaryClaim(
                id=str(uuid4()),
                version_id=version.id,
                section_path=claim.section_path,
                display_order=order,
                text=claim.text,
            )
            session.add(row)
            for quote in claim.evidence:
                session.add(
                    SummaryEvidence(
                        id=str(uuid4()),
                        claim_id=row.id,
                        block_id=quote.block_id,
                        quote_text=quote.quote_text,
                        quote_start=quote.quote_start,
                        quote_end=quote.quote_end,
                        source_quote_hash=quote.source_quote_hash,
                    )
                )
        session.flush()
        if previous is not None:
            previous.is_active = False
            session.flush()
        version.is_active = True
        session.flush()
    return version


def current_source_hash(document: Document) -> str | None:
    """Hash the file on disk; the catalog may not have been refreshed yet."""
    from glyph.documents import compute_hash

    source_path = Path(document.source_path)
    if not source_path.is_file():
        return None
    return compute_hash(source_path)


def load_summary_state(
    session: Session, document_id: str, settings: Settings
) -> SummaryStateView:
    document = session.get(Document, document_id)
    if document is None:
        raise SummaryNotFoundError("Document not found")
    provider = settings.ai_mode
    model = settings.cli_model if provider != "mock" else None
    active = session.scalar(
        select(SummaryVersion).where(
            SummaryVersion.document_id == document.id,
            SummaryVersion.is_active.is_(True),
        )
    )
    latest_job = session.scalar(
        select(SummaryJob)
        .where(SummaryJob.document_id == document.id)
        .order_by(SummaryJob.created_at.desc(), SummaryJob.id.desc())
    )
    version = _version_view(session, active) if active is not None else None
    job = (
        SummaryJobView(
            latest_job.id,
            cast(SummaryJobStatus, latest_job.status),
            latest_job.error_message,
        )
        if latest_job is not None
        else None
    )
    status: SummaryStatus
    if latest_job is not None and latest_job.status in ACTIVE_JOB_STATUSES:
        status = "generating"
    elif latest_job is not None and latest_job.status in {"failed", "interrupted"}:
        status = "failed"
    elif active is None:
        status = "not_generated"
    elif _is_current(session, document, active):
        status = "available"
    else:
        status = "stale"
    return SummaryStateView(status, provider, model, version, job)


def _is_current(session: Session, document: Document, version: SummaryVersion) -> bool:
    if version.source_content_hash != document.processed_content_hash:
        return False
    if document.processed_content_hash != document.content_hash:
        return False
    current = current_reader_blocks(session, document)
    return compute_reader_fingerprint(current) == version.reader_fingerprint


def _version_view(session: Session, version: SummaryVersion) -> SummaryVersionView:
    claims: list[ClaimView] = []
    for claim in version.claims:
        evidence = []
        for item in claim.evidence:
            block = session.get(Block, item.block_id)
            evidence.append(
                EvidenceView(
                    block_id=item.block_id,
                    quote_text=item.quote_text,
                    quote_start=item.quote_start,
                    quote_end=item.quote_end,
                    page_number=block.page_number if block is not None else 1,
                )
            )
        claims.append(
            ClaimView(claim.id, claim.section_path, claim.text, tuple(evidence))
        )
    return SummaryVersionView(
        id=version.id,
        source_content_hash=version.source_content_hash,
        reader_fingerprint=version.reader_fingerprint,
        provider=version.provider,
        model=version.model_name,
        created_at=version.created_at,
        claims=tuple(claims),
    )
