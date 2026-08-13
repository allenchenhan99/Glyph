from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from glyph.models import (
    Block,
    Document,
    ResearchEvidence,
    ResearchMapIssue,
    ResearchMapVersion,
    ResearchNode,
    ResearchNodeReview,
)
from glyph.research_ai import (
    CORE_NODE_GROUPS,
    NodeDraft,
    ResearchBlock,
    ResearchMapProvider,
    ValidatedEvidence,
    validate_extracted_candidates,
)
from glyph.research_audit import MapAuditIssue, MapAuditResult, audit_research_map
from glyph.research_domain import RESEARCH_MAP_SCHEMA_VERSION

StageCallback = Callable[[str, float], None]


class ResearchMapConflictError(RuntimeError):
    """Raised when current document state cannot support a map operation."""


class ResearchMapNotFoundError(LookupError):
    """Raised when a requested document or Research Map does not exist."""


@dataclass(frozen=True)
class ReviewView:
    id: str
    status: str
    corrected_claim_text: str | None
    review_note: str | None
    revision_number: int
    supersedes_review_id: str | None
    reviewed_at: datetime


@dataclass(frozen=True)
class EvidenceView:
    id: str
    block_id: str
    locator_type: str
    quote_text: str
    quote_start: int
    quote_end: int
    source_quote_hash: str
    relation: str
    source_label: str | None
    page_number: int
    block_type: str
    translated_text: str


@dataclass(frozen=True)
class IssueView:
    id: str
    node_id: str | None
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class NodeView:
    id: str
    parent_node_id: str | None
    node_key: str
    node_type: str
    title: str
    claim_text: str
    effective_claim_text: str
    explanation: str
    provenance: str
    evidence_quality: str
    display_order: int
    node_signature: str
    evidence: tuple[EvidenceView, ...]
    issues: tuple[IssueView, ...]
    review: ReviewView | None


@dataclass(frozen=True)
class ResearchMapView:
    id: str
    document_id: str
    previous_version_id: str | None
    source_content_hash: str
    schema_version: str
    provider: str
    model_name: str | None
    status: str
    is_active: bool
    is_current: bool
    is_stale: bool
    created_at: datetime
    completed_at: datetime | None
    reviewed_core_nodes: int
    reviewable_core_nodes: int
    nodes: tuple[NodeView, ...]
    issues: tuple[IssueView, ...]


@dataclass(frozen=True)
class ResearchMapVersionSummaryView:
    id: str
    document_id: str
    previous_version_id: str | None
    source_content_hash: str
    schema_version: str
    provider: str
    model_name: str | None
    status: str
    is_active: bool
    is_current: bool
    is_stale: bool
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True)
class ResearchMapLibrarySummaryView:
    version_id: str
    status: str
    is_current: bool
    is_stale: bool
    reviewed_core_nodes: int
    reviewable_core_nodes: int
    issue_count: int


@dataclass(frozen=True)
class ReviewRecordView:
    id: str
    node_id: str
    status: str
    corrected_claim_text: str | None
    review_note: str | None
    based_on_map_version_id: str
    based_on_node_signature: str
    revision_number: int
    supersedes_review_id: str | None
    reviewed_at: datetime


@dataclass(frozen=True)
class NodeDiffView:
    node_key: str
    classification: str
    version_node_id: str | None
    against_node_id: str | None


@dataclass(frozen=True)
class ResearchMapDiffView:
    version_id: str
    against_version_id: str
    nodes: tuple[NodeDiffView, ...]


class ResearchMapService:
    def __init__(
        self,
        session: Session,
        provider: ResearchMapProvider,
        stage_callback: StageCallback | None = None,
    ) -> None:
        self._session = session
        self._provider = provider
        self._stage_callback = stage_callback or (lambda _stage, _progress: None)

    def generate(self, document_id: str) -> ResearchMapVersion:
        document = self._require_current_reader(document_id)
        blocks = self._current_blocks(document)
        if not blocks:
            raise ResearchMapConflictError("Document has no current Reader blocks")

        self._stage_callback("evidence", 15)
        candidates = self._provider.extract_candidates(
            tuple(ResearchBlock.from_model(block) for block in blocks)
        )
        self._stage_callback("validation", 35)
        accepted = validate_extracted_candidates(self._session, document, candidates)
        self._stage_callback("synthesis", 55)
        draft = self._provider.synthesize_nodes(accepted)
        self._stage_callback("audit", 70)
        audit = audit_research_map(draft, accepted)
        self._stage_callback("persistence", 85)
        return self._persist(document, draft, accepted, audit)

    def _require_current_reader(self, document_id: str) -> Document:
        return require_current_reader(self._session, document_id)

    def _current_blocks(self, document: Document) -> Sequence[Block]:
        return self._session.scalars(
            select(Block)
            .where(
                Block.document_id == document.id,
                Block.source_content_hash == document.processed_content_hash,
            )
            .order_by(Block.order_index, Block.id)
        ).all()

    def _persist(
        self,
        document: Document,
        draft: tuple[NodeDraft, ...],
        accepted: tuple[ValidatedEvidence, ...],
        audit: MapAuditResult,
    ) -> ResearchMapVersion:
        previous = self._session.scalar(
            select(ResearchMapVersion).where(
                ResearchMapVersion.document_id == document.id,
                ResearchMapVersion.is_active.is_(True),
            )
        )
        with self._session.begin_nested():
            version = ResearchMapVersion(
                id=str(uuid4()),
                document_id=document.id,
                previous_version_id=previous.id if previous is not None else None,
                source_content_hash=document.processed_content_hash,
                schema_version=RESEARCH_MAP_SCHEMA_VERSION,
                provider=self._provider.name,
                model_name=self._provider.model_name,
                status="building",
                is_active=False,
            )
            self._session.add(version)
            node_by_key = persist_map_nodes(self._session, version, draft, accepted)
            persist_map_issues(self._session, version, audit.issues, node_by_key)
            self._session.flush()

            version.status = audit.status
            version.completed_at = _utc_now()
            if previous is not None:
                previous.is_active = False
                self._session.flush()
            version.is_active = True
            self._session.flush()
        return version


def persist_map_nodes(
    session: Session,
    version: ResearchMapVersion,
    drafts: tuple[NodeDraft, ...],
    accepted: tuple[ValidatedEvidence, ...],
) -> dict[str, ResearchNode]:
    accepted_by_id = {item.evidence_id: item for item in accepted}
    node_by_key: dict[str, ResearchNode] = {}
    for draft in drafts:
        cited = tuple(
            accepted_by_id[evidence_id]
            for evidence_id in draft.evidence_ids
            if evidence_id in accepted_by_id
        )
        node = ResearchNode(
            id=str(uuid4()),
            map_version_id=version.id,
            node_key=draft.node_key,
            node_type=draft.node_type,
            title=draft.title,
            claim_text=draft.claim_text,
            explanation=draft.explanation,
            provenance=draft.provenance,
            evidence_quality=draft.evidence_quality,
            display_order=draft.display_order,
            node_signature=node_signature(draft, cited),
        )
        session.add(node)
        node_by_key[draft.node_key] = node
        for item in cited:
            anchor = item.anchor
            session.add(
                ResearchEvidence(
                    id=str(uuid4()),
                    node_id=node.id,
                    block_id=anchor.block_id,
                    locator_type=anchor.locator_type,
                    quote_text=anchor.quote_text,
                    quote_start=anchor.quote_start,
                    quote_end=anchor.quote_end,
                    source_quote_hash=anchor.source_quote_hash,
                    relation=anchor.relation,
                    source_label=anchor.source_label,
                )
            )
    session.flush()
    for draft in drafts:
        if draft.parent_node_key is not None:
            node_by_key[draft.node_key].parent_node_id = node_by_key[
                draft.parent_node_key
            ].id
    session.flush()
    return node_by_key


def persist_map_issues(
    session: Session,
    version: ResearchMapVersion,
    issues: tuple[MapAuditIssue, ...],
    node_by_key: dict[str, ResearchNode],
) -> None:
    for issue in issues:
        node = node_by_key.get(issue.node_key) if issue.node_key else None
        session.add(
            ResearchMapIssue(
                id=str(uuid4()),
                map_version_id=version.id,
                node_id=node.id if node is not None else None,
                code=issue.code,
                severity=issue.severity,
                message=issue.message,
            )
        )


def node_signature(
    node: NodeDraft,
    evidence: Sequence[ValidatedEvidence],
) -> str:
    normalized_claim = " ".join(node.claim_text.split()).casefold()
    payload = json.dumps(
        [
            node.node_type,
            normalized_claim,
            sorted(item.anchor.source_quote_hash for item in evidence),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def load_research_map(session: Session, version_id: str) -> ResearchMapView:
    version = session.get(ResearchMapVersion, version_id)
    if version is None:
        raise ResearchMapNotFoundError("Research Map not found")
    document = session.get(Document, version.document_id)
    if document is None:
        raise ResearchMapNotFoundError("Document not found")

    nodes = session.scalars(
        select(ResearchNode)
        .where(ResearchNode.map_version_id == version.id)
        .order_by(ResearchNode.display_order, ResearchNode.node_key)
    ).all()
    node_ids = [node.id for node in nodes]
    evidence_by_node = _load_evidence(session, node_ids)
    issue_models = session.scalars(
        select(ResearchMapIssue)
        .where(ResearchMapIssue.map_version_id == version.id)
        .order_by(ResearchMapIssue.code, ResearchMapIssue.id)
    ).all()
    issue_views = tuple(_issue_view(issue) for issue in issue_models)
    issues_by_node: defaultdict[str, list[IssueView]] = defaultdict(list)
    for issue in issue_views:
        if issue.node_id is not None:
            issues_by_node[issue.node_id].append(issue)
    reviews_by_signature = _load_effective_reviews(
        session,
        document.id,
        {node.node_signature for node in nodes},
    )
    core_types = frozenset().union(*CORE_NODE_GROUPS.values())
    node_views = tuple(
        _node_view(
            node,
            tuple(evidence_by_node[node.id]),
            tuple(issues_by_node[node.id]),
            reviews_by_signature.get(node.node_signature),
        )
        for node in nodes
    )
    reviewable = [node for node in node_views if node.node_type in core_types]
    is_current = (
        document.status == "completed"
        and document.processed_content_hash == document.content_hash
        and version.source_content_hash == document.content_hash
    )
    return ResearchMapView(
        id=version.id,
        document_id=version.document_id,
        previous_version_id=version.previous_version_id,
        source_content_hash=version.source_content_hash,
        schema_version=version.schema_version,
        provider=version.provider,
        model_name=version.model_name,
        status=version.status,
        is_active=version.is_active,
        is_current=is_current,
        is_stale=not is_current,
        created_at=version.created_at,
        completed_at=version.completed_at,
        reviewed_core_nodes=sum(node.review is not None for node in reviewable),
        reviewable_core_nodes=len(reviewable),
        nodes=node_views,
        issues=issue_views,
    )


def load_active_research_map(session: Session, document_id: str) -> ResearchMapView:
    version_id = session.scalar(
        select(ResearchMapVersion.id).where(
            ResearchMapVersion.document_id == document_id,
            ResearchMapVersion.is_active.is_(True),
        )
    )
    if version_id is None:
        raise ResearchMapNotFoundError("Active Research Map not found")
    return load_research_map(session, version_id)


def load_research_map_library_summaries(
    session: Session,
    documents: Sequence[Document],
) -> dict[str, ResearchMapLibrarySummaryView]:
    """Load compact active-map state in a bounded number of batched queries."""
    if not documents:
        return {}
    documents_by_id = {document.id: document for document in documents}
    versions = session.scalars(
        select(ResearchMapVersion).where(
            ResearchMapVersion.document_id.in_(documents_by_id),
            ResearchMapVersion.is_active.is_(True),
        )
    ).all()
    if not versions:
        return {}

    version_ids = [version.id for version in versions]
    nodes = session.scalars(
        select(ResearchNode).where(ResearchNode.map_version_id.in_(version_ids))
    ).all()
    issue_counts: dict[str, int] = {
        version_id: count
        for version_id, count in session.execute(
            select(ResearchMapIssue.map_version_id, func.count(ResearchMapIssue.id))
            .where(ResearchMapIssue.map_version_id.in_(version_ids))
            .group_by(ResearchMapIssue.map_version_id)
        ).all()
    }

    core_types = frozenset().union(*CORE_NODE_GROUPS.values())
    nodes_by_version: defaultdict[str, list[ResearchNode]] = defaultdict(list)
    all_signatures: set[str] = set()
    for node in nodes:
        nodes_by_version[node.map_version_id].append(node)
        all_signatures.add(node.node_signature)

    reviewed_signatures_by_document: defaultdict[str, set[str]] = defaultdict(set)
    if all_signatures:
        reviewed_rows = session.execute(
            select(
                ResearchMapVersion.document_id,
                ResearchNodeReview.based_on_node_signature,
            )
            .join(ResearchNode, ResearchNodeReview.node_id == ResearchNode.id)
            .join(
                ResearchMapVersion,
                ResearchNode.map_version_id == ResearchMapVersion.id,
            )
            .where(
                ResearchMapVersion.document_id.in_(documents_by_id),
                ResearchNodeReview.based_on_node_signature.in_(all_signatures),
            )
            .distinct()
        ).all()
        for document_id, signature in reviewed_rows:
            reviewed_signatures_by_document[document_id].add(signature)

    summaries: dict[str, ResearchMapLibrarySummaryView] = {}
    for version in versions:
        document = documents_by_id[version.document_id]
        core_nodes = [
            node
            for node in nodes_by_version[version.id]
            if node.node_type in core_types
        ]
        reviewed_signatures = reviewed_signatures_by_document[document.id]
        is_current = (
            document.status == "completed"
            and document.processed_content_hash == document.content_hash
            and version.source_content_hash == document.content_hash
        )
        summaries[document.id] = ResearchMapLibrarySummaryView(
            version_id=version.id,
            status=version.status,
            is_current=is_current,
            is_stale=not is_current,
            reviewed_core_nodes=sum(
                node.node_signature in reviewed_signatures for node in core_nodes
            ),
            reviewable_core_nodes=len(core_nodes),
            issue_count=issue_counts.get(version.id, 0),
        )
    return summaries


def require_current_reader(session: Session, document_id: str) -> Document:
    document = session.get(Document, document_id)
    if document is None:
        raise ResearchMapNotFoundError("Document not found")
    if (
        document.status != "completed"
        or document.processed_content_hash is None
        or document.processed_content_hash != document.content_hash
    ):
        raise ResearchMapConflictError(
            "Research Map requires a current completed Reader snapshot"
        )
    has_current_blocks = session.scalar(
        select(Block.id).where(
            Block.document_id == document.id,
            Block.source_content_hash == document.processed_content_hash,
        )
    )
    if has_current_blocks is None:
        raise ResearchMapConflictError("Document has no current Reader blocks")
    return document


def list_research_map_versions(
    session: Session,
    document_id: str,
) -> tuple[ResearchMapVersionSummaryView, ...]:
    document = session.get(Document, document_id)
    if document is None:
        raise ResearchMapNotFoundError("Document not found")
    versions = session.scalars(
        select(ResearchMapVersion)
        .where(ResearchMapVersion.document_id == document_id)
        .order_by(
            ResearchMapVersion.created_at.desc(),
            ResearchMapVersion.id.desc(),
        )
    ).all()
    document_is_current = (
        document.status == "completed"
        and document.processed_content_hash == document.content_hash
    )
    return tuple(
        ResearchMapVersionSummaryView(
            id=version.id,
            document_id=version.document_id,
            previous_version_id=version.previous_version_id,
            source_content_hash=version.source_content_hash,
            schema_version=version.schema_version,
            provider=version.provider,
            model_name=version.model_name,
            status=version.status,
            is_active=version.is_active,
            is_current=(
                document_is_current
                and version.source_content_hash == document.content_hash
            ),
            is_stale=(
                not document_is_current
                or version.source_content_hash != document.content_hash
            ),
            created_at=version.created_at,
            completed_at=version.completed_at,
        )
        for version in versions
    )


def append_node_review(
    session: Session,
    node_id: str,
    *,
    status: str,
    based_on_node_signature: str,
    corrected_claim_text: str | None,
    review_note: str | None,
) -> ReviewRecordView:
    node = session.get(ResearchNode, node_id)
    if node is None:
        raise ResearchMapNotFoundError("Research node not found")
    if node.node_signature != based_on_node_signature:
        raise ResearchMapConflictError(
            "Review is based on an obsolete Research Map node signature"
        )
    if status == "corrected" and not (
        corrected_claim_text and corrected_claim_text.strip()
    ):
        raise ValueError("corrected_claim_text is required for corrected reviews")
    corrected_value = (
        corrected_claim_text.strip()
        if status == "corrected" and corrected_claim_text is not None
        else None
    )
    version = session.get(ResearchMapVersion, node.map_version_id)
    if version is None:
        raise ResearchMapNotFoundError("Research Map not found")
    latest_effective = session.scalar(
        select(ResearchNodeReview)
        .join(ResearchNode, ResearchNodeReview.node_id == ResearchNode.id)
        .join(
            ResearchMapVersion,
            ResearchNode.map_version_id == ResearchMapVersion.id,
        )
        .where(
            ResearchMapVersion.document_id == version.document_id,
            ResearchNodeReview.based_on_node_signature == node.node_signature,
        )
        .order_by(
            ResearchNodeReview.reviewed_at.desc(),
            ResearchNodeReview.revision_number.desc(),
            ResearchNodeReview.id.desc(),
        )
    )
    latest_revision = session.scalar(
        select(func.max(ResearchNodeReview.revision_number)).where(
            ResearchNodeReview.node_id == node.id
        )
    )
    review = ResearchNodeReview(
        id=str(uuid4()),
        node_id=node.id,
        revision_number=(latest_revision or 0) + 1,
        supersedes_review_id=(
            latest_effective.id if latest_effective is not None else None
        ),
        status=status,
        corrected_claim_text=corrected_value,
        review_note=review_note.strip()
        if review_note and review_note.strip()
        else None,
        based_on_map_version_id=node.map_version_id,
        based_on_node_signature=node.node_signature,
    )
    try:
        with session.begin_nested():
            session.add(review)
            session.flush()
    except IntegrityError as exc:
        raise ResearchMapConflictError(
            "Review changed concurrently; reload the Research Map and review it again"
        ) from exc
    return _review_record_view(review)


def diff_research_maps(
    session: Session,
    version_id: str,
    against_version_id: str,
) -> ResearchMapDiffView:
    version = session.get(ResearchMapVersion, version_id)
    against = session.get(ResearchMapVersion, against_version_id)
    if version is None or against is None:
        raise ResearchMapNotFoundError("Research Map not found")
    if version.document_id != against.document_id:
        raise ResearchMapConflictError(
            "Research Map versions must belong to the same document"
        )
    version_nodes = _nodes_by_key(session, version.id)
    against_nodes = _nodes_by_key(session, against.id)
    version_evidence = _evidence_hashes_by_node(session, version_nodes.values())
    against_evidence = _evidence_hashes_by_node(session, against_nodes.values())
    diffs: list[NodeDiffView] = []
    for node_key in sorted(set(version_nodes) | set(against_nodes)):
        current = version_nodes.get(node_key)
        previous = against_nodes.get(node_key)
        if current is None:
            classification = "removed"
        elif previous is None:
            classification = "added"
        elif current.node_signature == previous.node_signature:
            classification = "unchanged"
        elif _normalized_claim(current.claim_text) != _normalized_claim(
            previous.claim_text
        ):
            classification = "claim_changed"
        elif version_evidence[current.id] != against_evidence[previous.id]:
            classification = "evidence_changed"
        else:
            classification = "claim_changed"
        diffs.append(
            NodeDiffView(
                node_key=node_key,
                classification=classification,
                version_node_id=current.id if current is not None else None,
                against_node_id=previous.id if previous is not None else None,
            )
        )
    return ResearchMapDiffView(
        version_id=version.id,
        against_version_id=against.id,
        nodes=tuple(diffs),
    )


def activate_research_map(session: Session, version_id: str) -> ResearchMapVersion:
    version = session.get(ResearchMapVersion, version_id)
    if version is None:
        raise ResearchMapNotFoundError("Research Map not found")
    document = session.get(Document, version.document_id)
    if document is None:
        raise ResearchMapNotFoundError("Document not found")
    if version.status not in {"complete", "partial"}:
        raise ResearchMapConflictError(
            "Only a complete or partial Research Map can be activated"
        )
    if (
        document.status != "completed"
        or document.processed_content_hash != document.content_hash
        or version.source_content_hash != document.content_hash
    ):
        raise ResearchMapConflictError("A stale Research Map cannot be activated")
    with session.begin_nested():
        current = session.scalar(
            select(ResearchMapVersion).where(
                ResearchMapVersion.document_id == document.id,
                ResearchMapVersion.is_active.is_(True),
            )
        )
        if current is not None and current.id != version.id:
            current.is_active = False
            session.flush()
        version.is_active = True
        session.flush()
    return version


def _load_evidence(
    session: Session,
    node_ids: list[str],
) -> defaultdict[str, list[EvidenceView]]:
    by_node: defaultdict[str, list[EvidenceView]] = defaultdict(list)
    if not node_ids:
        return by_node
    rows = session.execute(
        select(ResearchEvidence, Block)
        .join(Block, ResearchEvidence.block_id == Block.id)
        .where(ResearchEvidence.node_id.in_(node_ids))
        .order_by(
            ResearchEvidence.node_id,
            Block.page_number,
            ResearchEvidence.quote_start,
            ResearchEvidence.id,
        )
    ).all()
    for evidence, block in rows:
        by_node[evidence.node_id].append(
            EvidenceView(
                id=evidence.id,
                block_id=evidence.block_id,
                locator_type=evidence.locator_type,
                quote_text=evidence.quote_text,
                quote_start=evidence.quote_start,
                quote_end=evidence.quote_end,
                source_quote_hash=evidence.source_quote_hash,
                relation=evidence.relation,
                source_label=evidence.source_label,
                page_number=block.page_number,
                block_type=block.block_type,
                translated_text=block.translated_text,
            )
        )
    return by_node


def _load_effective_reviews(
    session: Session,
    document_id: str,
    signatures: set[str],
) -> dict[str, ResearchNodeReview]:
    if not signatures:
        return {}
    reviews = session.scalars(
        select(ResearchNodeReview)
        .join(ResearchNode, ResearchNodeReview.node_id == ResearchNode.id)
        .join(
            ResearchMapVersion,
            ResearchNode.map_version_id == ResearchMapVersion.id,
        )
        .where(
            ResearchMapVersion.document_id == document_id,
            ResearchNodeReview.based_on_node_signature.in_(signatures),
        )
        .order_by(
            ResearchNodeReview.reviewed_at,
            ResearchNodeReview.revision_number,
            ResearchNodeReview.id,
        )
    ).all()
    return {review.based_on_node_signature: review for review in reviews}


def _node_view(
    node: ResearchNode,
    evidence: tuple[EvidenceView, ...],
    issues: tuple[IssueView, ...],
    review: ResearchNodeReview | None,
) -> NodeView:
    review_view = (
        ReviewView(
            id=review.id,
            status=review.status,
            corrected_claim_text=review.corrected_claim_text,
            review_note=review.review_note,
            revision_number=review.revision_number,
            supersedes_review_id=review.supersedes_review_id,
            reviewed_at=review.reviewed_at,
        )
        if review is not None
        else None
    )
    effective_claim = (
        review.corrected_claim_text
        if review is not None
        and review.status == "corrected"
        and review.corrected_claim_text is not None
        else node.claim_text
    )
    return NodeView(
        id=node.id,
        parent_node_id=node.parent_node_id,
        node_key=node.node_key,
        node_type=node.node_type,
        title=node.title,
        claim_text=node.claim_text,
        effective_claim_text=effective_claim,
        explanation=node.explanation,
        provenance=node.provenance,
        evidence_quality=node.evidence_quality,
        display_order=node.display_order,
        node_signature=node.node_signature,
        evidence=evidence,
        issues=issues,
        review=review_view,
    )


def _issue_view(issue: ResearchMapIssue) -> IssueView:
    return IssueView(
        id=issue.id,
        node_id=issue.node_id,
        code=issue.code,
        severity=issue.severity,
        message=issue.message,
    )


def _review_record_view(review: ResearchNodeReview) -> ReviewRecordView:
    return ReviewRecordView(
        id=review.id,
        node_id=review.node_id,
        status=review.status,
        corrected_claim_text=review.corrected_claim_text,
        review_note=review.review_note,
        based_on_map_version_id=review.based_on_map_version_id,
        based_on_node_signature=review.based_on_node_signature,
        revision_number=review.revision_number,
        supersedes_review_id=review.supersedes_review_id,
        reviewed_at=review.reviewed_at,
    )


def _nodes_by_key(
    session: Session,
    version_id: str,
) -> dict[str, ResearchNode]:
    return {
        node.node_key: node
        for node in session.scalars(
            select(ResearchNode).where(ResearchNode.map_version_id == version_id)
        ).all()
    }


def _evidence_hashes_by_node(
    session: Session,
    nodes: Iterable[ResearchNode],
) -> defaultdict[str, tuple[str, ...]]:
    node_ids = [node.id for node in nodes]
    hashes: defaultdict[str, list[str]] = defaultdict(list)
    if node_ids:
        rows = session.execute(
            select(
                ResearchEvidence.node_id,
                ResearchEvidence.source_quote_hash,
            )
            .where(ResearchEvidence.node_id.in_(node_ids))
            .order_by(
                ResearchEvidence.node_id,
                ResearchEvidence.source_quote_hash,
            )
        ).all()
        for node_id, source_quote_hash in rows:
            hashes[node_id].append(source_quote_hash)
    return defaultdict(
        tuple,
        {node_id: tuple(values) for node_id, values in hashes.items()},
    )


def _normalized_claim(claim: str) -> str:
    return " ".join(claim.split()).casefold()


def _utc_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
