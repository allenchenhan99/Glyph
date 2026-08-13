from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from glyph.contract_ai import (
    ContractInputBlock,
    ImplementationContractProvider,
    validate_extracted_requirements,
    validate_synthesized_contract,
)
from glyph.contract_audit import (
    ContractAuditResult,
    EffectiveContractItem,
    audit_contract,
)
from glyph.contract_domain import (
    CONTRACT_SCHEMA_VERSION,
    CONTRACT_SECTIONS,
    ContractItemDraft,
    ContractResolutionDraft,
    ContractValue,
    decode_contract_value,
    encode_contract_value,
    item_signature,
    validate_contract_item_type,
    validate_contract_origin,
    validate_contract_section,
    validate_diff_classification,
    validate_resolution_status,
)
from glyph.contract_evidence import AcceptedContractEvidence, ContractEvidenceContext
from glyph.models import (
    Block,
    Document,
    ImplementationContractEvidence,
    ImplementationContractIssue,
    ImplementationContractItem,
    ImplementationContractResolution,
    ImplementationContractVersion,
    ResearchEvidence,
    ResearchMapVersion,
    ResearchNode,
)
from glyph.research_domain import validate_evidence_relation, validate_locator_type

StageCallback = Callable[[str, float], None]
_SECTION_ORDER = {section: index for index, section in enumerate(CONTRACT_SECTIONS)}


class ImplementationContractConflictError(RuntimeError):
    """Raised when current persisted state cannot support a contract operation."""


class ImplementationContractNotFoundError(LookupError):
    """Raised when a requested contract input or version does not exist."""


@dataclass(frozen=True)
class ContractEvidenceView:
    id: str
    block_id: str
    research_node_id: str | None
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
class ContractIssueView:
    id: str
    item_id: str | None
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class ContractResolutionView:
    id: str
    item_id: str
    revision_number: int
    supersedes_resolution_id: str | None
    status: str
    resolved_value: ContractValue | None
    reason: str | None
    based_on_contract_version_id: str
    based_on_item_signature: str
    request_id: str
    resolved_at: datetime


@dataclass(frozen=True)
class ContractItemView:
    id: str
    item_key: str
    section: str
    item_type: str
    draft_value: ContractValue | None
    effective_value: ContractValue | None
    origin: str
    effective_origin: str
    rationale: str | None
    is_blocking: bool
    is_optional: bool
    display_order: int
    item_signature: str
    evidence: tuple[ContractEvidenceView, ...]
    issues: tuple[ContractIssueView, ...]
    resolution: ContractResolutionView | None
    resolution_history: tuple[ContractResolutionView, ...]


@dataclass(frozen=True)
class ImplementationContractView:
    id: str
    document_id: str
    research_map_version_id: str
    previous_version_id: str | None
    source_content_hash: str
    research_map_signature: str
    schema_version: str
    provider: str
    model_name: str | None
    status: str
    readiness: str
    is_active: bool
    is_current: bool
    is_stale: bool
    created_at: datetime
    completed_at: datetime | None
    items: tuple[ContractItemView, ...]
    issues: tuple[ContractIssueView, ...]


@dataclass(frozen=True)
class ImplementationContractVersionSummaryView:
    id: str
    document_id: str
    research_map_version_id: str
    previous_version_id: str | None
    source_content_hash: str
    research_map_signature: str
    schema_version: str
    provider: str
    model_name: str | None
    status: str
    readiness: str
    is_active: bool
    is_current: bool
    is_stale: bool
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True)
class ImplementationContractLibrarySummaryView:
    version_id: str
    generation_status: str
    readiness: str
    is_current: bool
    is_stale: bool
    blocker_count: int
    reviewed_count: int
    total_reviewable_count: int


@dataclass(frozen=True)
class ContractItemDiffView:
    item_key: str
    classification: str
    version_item_id: str | None
    against_item_id: str | None
    section_order: int
    display_order: int


@dataclass(frozen=True)
class ImplementationContractDiffView:
    version_id: str
    against_version_id: str
    items: tuple[ContractItemDiffView, ...]


@dataclass(frozen=True)
class _GenerationContext:
    document: Document
    research_map: ResearchMapVersion
    blocks: tuple[Block, ...]
    research_map_signature: str


class ImplementationContractService:
    def __init__(
        self,
        session: Session,
        provider: ImplementationContractProvider,
        stage_callback: StageCallback | None = None,
    ) -> None:
        self._session = session
        self._provider = provider
        self._stage_callback = stage_callback or (lambda _stage, _progress: None)

    def generate(
        self,
        document_id: str,
        research_map_version_id: str | None = None,
    ) -> ImplementationContractView:
        self._stage_callback("load_context", 5)
        context = _load_generation_context(
            self._session, document_id, research_map_version_id
        )
        self._stage_callback("extract_requirements", 20)
        candidates = self._provider.extract_requirements(
            tuple(ContractInputBlock.from_model(block) for block in context.blocks)
        )
        self._stage_callback("validate_evidence", 40)
        accepted = validate_extracted_requirements(
            self._session,
            ContractEvidenceContext(
                document_id=context.document.id,
                source_content_hash=context.document.content_hash,
                research_map_version_id=context.research_map.id,
            ),
            candidates,
        )
        self._stage_callback("synthesize_contract", 60)
        synthesized = self._provider.synthesize_contract(accepted)
        effective = validate_synthesized_contract(synthesized, accepted)
        self._stage_callback("audit_readiness", 75)
        audit = audit_contract(effective)
        self._stage_callback("persist_and_activate", 90)
        version_id = _persist_and_activate(
            self._session,
            context,
            effective,
            audit,
            self._provider,
        )
        return load_implementation_contract(self._session, version_id)


def _load_generation_context(
    session: Session,
    document_id: str,
    research_map_version_id: str | None,
) -> _GenerationContext:
    document = session.get(Document, document_id)
    if document is None:
        raise ImplementationContractNotFoundError("Document not found")
    if (
        document.status != "completed"
        or document.processed_content_hash is None
        or document.processed_content_hash != document.content_hash
    ):
        raise ImplementationContractConflictError(
            "Implementation Contract requires a current completed Reader snapshot"
        )
    blocks = tuple(
        session.scalars(
            select(Block)
            .where(
                Block.document_id == document.id,
                Block.source_content_hash == document.processed_content_hash,
            )
            .order_by(Block.order_index, Block.id)
        ).all()
    )
    if not blocks:
        raise ImplementationContractConflictError(
            "Document has no current Reader blocks"
        )

    if research_map_version_id is None:
        research_map = session.scalar(
            select(ResearchMapVersion).where(
                ResearchMapVersion.document_id == document.id,
                ResearchMapVersion.is_active.is_(True),
            )
        )
        if research_map is None:
            raise ImplementationContractConflictError(
                "Document has no active Research Map"
            )
    else:
        research_map = session.get(ResearchMapVersion, research_map_version_id)
        if research_map is None:
            raise ImplementationContractNotFoundError("Research Map not found")
    if research_map.document_id != document.id:
        raise ImplementationContractConflictError(
            "Research Map must belong to the same document"
        )
    if research_map.source_content_hash != document.content_hash:
        raise ImplementationContractConflictError(
            "Research Map must use the same current source"
        )
    if research_map.status not in {"complete", "partial"}:
        raise ImplementationContractConflictError(
            "Research Map must be complete or partial"
        )
    return _GenerationContext(
        document=document,
        research_map=research_map,
        blocks=blocks,
        research_map_signature=_research_map_signature(session, research_map),
    )


def _research_map_signature(
    session: Session,
    map_version: ResearchMapVersion,
) -> str:
    nodes = session.scalars(
        select(ResearchNode)
        .where(ResearchNode.map_version_id == map_version.id)
        .order_by(ResearchNode.node_key, ResearchNode.id)
    ).all()
    evidence_hashes = session.scalars(
        select(ResearchEvidence.source_quote_hash)
        .join(ResearchNode, ResearchEvidence.node_id == ResearchNode.id)
        .where(ResearchNode.map_version_id == map_version.id)
        .order_by(ResearchEvidence.source_quote_hash, ResearchEvidence.id)
    ).all()
    payload = {
        "map_version_id": map_version.id,
        "schema_version": map_version.schema_version,
        "source_content_hash": map_version.source_content_hash,
        "nodes": [[node.id, node.node_key, node.node_signature] for node in nodes],
        "evidence_hashes": list(evidence_hashes),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _persist_and_activate(
    session: Session,
    context: _GenerationContext,
    items: tuple[EffectiveContractItem, ...],
    audit: ContractAuditResult,
    provider: ImplementationContractProvider,
) -> str:
    previous = session.scalar(
        select(ImplementationContractVersion).where(
            ImplementationContractVersion.document_id == context.document.id,
            ImplementationContractVersion.is_active.is_(True),
        )
    )
    with session.begin_nested():
        version = ImplementationContractVersion(
            id=str(uuid4()),
            document_id=context.document.id,
            research_map_version_id=context.research_map.id,
            previous_version_id=previous.id if previous is not None else None,
            source_content_hash=context.document.content_hash,
            research_map_signature=context.research_map_signature,
            schema_version=CONTRACT_SCHEMA_VERSION,
            provider=provider.provider_name,
            model_name=provider.model_name,
            status="building",
            readiness="blocked",
            is_active=False,
        )
        session.add(version)
        item_by_key = persist_items(session, version, items)
        persist_issues(session, version, audit, item_by_key)
        session.flush()
        _refresh_contract_audit(session, version)
        version.completed_at = datetime.now(UTC)
        if previous is not None:
            previous.is_active = False
            session.flush()
        version.is_active = True
        session.flush()
    return version.id


def persist_items(
    session: Session,
    version: ImplementationContractVersion,
    items: Sequence[EffectiveContractItem],
) -> dict[str, ImplementationContractItem]:
    item_by_key: dict[str, ImplementationContractItem] = {}
    for item in items:
        draft = item.draft
        model = ImplementationContractItem(
            id=str(uuid4()),
            contract_version_id=version.id,
            item_key=draft.item_key,
            section=draft.section,
            item_type=draft.item_type,
            draft_value_json=(
                encode_contract_value(draft.value) if draft.value is not None else None
            ),
            origin=draft.origin,
            rationale=draft.rationale,
            is_blocking=draft.is_blocking,
            is_optional=draft.is_optional,
            display_order=draft.display_order,
            item_signature=item_signature(
                draft,
                tuple(anchor.source_quote_hash for anchor in item.evidence),
            ),
        )
        session.add(model)
        item_by_key[draft.item_key] = model
        for anchor in item.evidence:
            session.add(
                ImplementationContractEvidence(
                    id=str(uuid4()),
                    item_id=model.id,
                    block_id=anchor.block_id,
                    research_node_id=anchor.research_node_id,
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
    return item_by_key


def persist_issues(
    session: Session,
    version: ImplementationContractVersion,
    audit: ContractAuditResult,
    item_by_key: dict[str, ImplementationContractItem],
) -> None:
    for issue in audit.issues:
        item = item_by_key.get(issue.item_key) if issue.item_key is not None else None
        session.add(
            ImplementationContractIssue(
                id=str(uuid4()),
                contract_version_id=version.id,
                item_id=item.id if item is not None else None,
                code=issue.code,
                severity=issue.severity,
                message=issue.message,
            )
        )


def append_contract_resolution(
    session: Session,
    item_id: str,
    *,
    status: str,
    based_on_item_signature: str,
    value: ContractValue | None,
    reason: str | None,
    request_id: str,
) -> ContractResolutionView:
    item = session.get(ImplementationContractItem, item_id)
    if item is None:
        raise ImplementationContractNotFoundError(
            "Implementation Contract item not found"
        )
    version = session.get(ImplementationContractVersion, item.contract_version_id)
    if version is None:
        raise ImplementationContractNotFoundError("Implementation Contract not found")
    if item.item_signature != based_on_item_signature:
        raise ImplementationContractConflictError(
            "Resolution is based on an obsolete item signature"
        )
    if not request_id or len(request_id) > 128:
        raise ValueError("request_id must contain between 1 and 128 characters")
    normalized_reason = reason.strip() if reason and reason.strip() else None
    resolution_draft = ContractResolutionDraft(
        status=validate_resolution_status(status),
        value=value,
        reason=normalized_reason,
    )
    if resolution_draft.status == "not_applicable" and not item.is_optional:
        raise ImplementationContractConflictError(
            "This mandatory contract item cannot be marked not applicable"
        )
    desired_value_json = (
        encode_contract_value(resolution_draft.value)
        if resolution_draft.value is not None
        else None
    )
    existing = session.scalar(
        select(ImplementationContractResolution).where(
            ImplementationContractResolution.item_id == item.id,
            ImplementationContractResolution.request_id == request_id,
        )
    )
    if existing is not None:
        if _resolution_payload(existing) != (
            resolution_draft.status,
            desired_value_json,
            resolution_draft.reason,
            based_on_item_signature,
        ):
            raise ImplementationContractConflictError(
                "Resolution request ID was already used with a different payload"
            )
        return _resolution_view(existing)

    lineage_resolutions = _load_resolution_models(
        session,
        _lineage_version_ids(session, version),
        (item,),
    )
    latest = (
        max(
            (resolution for resolution, _item_key in lineage_resolutions),
            key=lambda resolution: (
                resolution.resolved_at,
                resolution.revision_number,
                resolution.id,
            ),
        )
        if lineage_resolutions
        else None
    )
    latest_revision = max(
        (resolution.revision_number for resolution, _item_key in lineage_resolutions),
        default=0,
    )
    resolution = ImplementationContractResolution(
        id=str(uuid4()),
        item_id=item.id,
        revision_number=latest_revision + 1,
        supersedes_resolution_id=latest.id if latest is not None else None,
        status=resolution_draft.status,
        resolved_value_json=desired_value_json,
        reason=resolution_draft.reason,
        based_on_contract_version_id=version.id,
        based_on_item_signature=item.item_signature,
        request_id=request_id,
    )
    try:
        with session.begin_nested():
            session.add(resolution)
            session.flush()
            _refresh_affected_contract_audits(
                session, version, item.item_key, item.item_signature
            )
    except IntegrityError as exc:
        raced = session.scalar(
            select(ImplementationContractResolution).where(
                ImplementationContractResolution.item_id == item.id,
                ImplementationContractResolution.request_id == request_id,
            )
        )
        if raced is not None and _resolution_payload(raced) == (
            resolution_draft.status,
            desired_value_json,
            resolution_draft.reason,
            based_on_item_signature,
        ):
            return _resolution_view(raced)
        raise ImplementationContractConflictError(
            "Resolution changed concurrently; reload and try again"
        ) from exc
    return _resolution_view(resolution)


def _resolution_payload(
    resolution: ImplementationContractResolution,
) -> tuple[str, str | None, str | None, str]:
    return (
        resolution.status,
        resolution.resolved_value_json,
        resolution.reason,
        resolution.based_on_item_signature,
    )


def _refresh_contract_audit(
    session: Session,
    version: ImplementationContractVersion,
) -> None:
    items = list(
        session.scalars(
            select(ImplementationContractItem).where(
                ImplementationContractItem.contract_version_id == version.id
            )
        ).all()
    )
    item_ids = [item.id for item in items]
    evidence_models = (
        session.scalars(
            select(ImplementationContractEvidence)
            .where(ImplementationContractEvidence.item_id.in_(item_ids))
            .order_by(
                ImplementationContractEvidence.item_id,
                ImplementationContractEvidence.quote_start,
                ImplementationContractEvidence.id,
            )
        ).all()
        if item_ids
        else ()
    )
    evidence_by_item: defaultdict[str, list[AcceptedContractEvidence]] = defaultdict(
        list
    )
    for anchor in evidence_models:
        evidence_by_item[anchor.item_id].append(
            AcceptedContractEvidence(
                block_id=anchor.block_id,
                research_node_id=anchor.research_node_id,
                quote_text=anchor.quote_text,
                quote_start=anchor.quote_start,
                quote_end=anchor.quote_end,
                relation=validate_evidence_relation(anchor.relation),
                locator_type=validate_locator_type(anchor.locator_type),
                source_quote_hash=anchor.source_quote_hash,
                source_label=anchor.source_label,
            )
        )
    resolution_rows = _load_resolution_models(
        session,
        _lineage_version_ids(session, version),
        items,
    )
    effective_by_identity = {
        (item_key, resolution.based_on_item_signature): resolution
        for resolution, item_key in resolution_rows
    }
    effective_items: list[EffectiveContractItem] = []
    for item in items:
        value = (
            decode_contract_value(json.loads(item.draft_value_json))
            if item.draft_value_json is not None
            else None
        )
        draft = ContractItemDraft(
            item_key=item.item_key,
            section=validate_contract_section(item.section),
            item_type=validate_contract_item_type(item.item_type),
            value=value,
            origin=validate_contract_origin(item.origin),
            rationale=item.rationale,
            is_blocking=item.is_blocking,
            is_optional=item.is_optional,
            display_order=item.display_order,
        )
        resolution_model = effective_by_identity.get(
            (item.item_key, item.item_signature)
        )
        resolution = (
            ContractResolutionDraft(
                status=validate_resolution_status(resolution_model.status),
                value=(
                    decode_contract_value(
                        json.loads(resolution_model.resolved_value_json)
                    )
                    if resolution_model.resolved_value_json is not None
                    else None
                ),
                reason=resolution_model.reason,
            )
            if resolution_model is not None
            else None
        )
        effective_items.append(
            EffectiveContractItem(
                draft=draft,
                evidence=tuple(evidence_by_item[item.id]),
                resolution=resolution,
            )
        )
    audit = audit_contract(effective_items)
    session.execute(
        delete(ImplementationContractIssue).where(
            ImplementationContractIssue.contract_version_id == version.id
        )
    )
    persist_issues(session, version, audit, {item.item_key: item for item in items})
    version.status = audit.generation_status
    version.readiness = audit.readiness
    session.flush()


def _refresh_affected_contract_audits(
    session: Session,
    source_version: ImplementationContractVersion,
    item_key: str,
    item_signature_value: str,
) -> None:
    candidates = (
        session.scalars(
            select(ImplementationContractVersion)
            .join(
                ImplementationContractItem,
                ImplementationContractItem.contract_version_id
                == ImplementationContractVersion.id,
            )
            .where(
                ImplementationContractVersion.document_id == source_version.document_id,
                ImplementationContractItem.item_key == item_key,
                ImplementationContractItem.item_signature == item_signature_value,
            )
        )
        .unique()
        .all()
    )
    for candidate in candidates:
        if source_version.id in _lineage_version_ids(session, candidate):
            _refresh_contract_audit(session, candidate)


def load_implementation_contract(
    session: Session,
    version_id: str,
) -> ImplementationContractView:
    version = session.get(ImplementationContractVersion, version_id)
    if version is None:
        raise ImplementationContractNotFoundError("Implementation Contract not found")
    document = session.get(Document, version.document_id)
    if document is None:
        raise ImplementationContractNotFoundError("Document not found")
    map_version = session.get(ResearchMapVersion, version.research_map_version_id)
    if map_version is None:
        raise ImplementationContractNotFoundError("Research Map not found")

    item_models = list(
        session.scalars(
            select(ImplementationContractItem).where(
                ImplementationContractItem.contract_version_id == version.id
            )
        ).all()
    )
    item_models.sort(
        key=lambda item: (
            _SECTION_ORDER.get(validate_contract_section(item.section), 999),
            item.display_order,
            item.item_key,
        )
    )
    item_ids = [item.id for item in item_models]
    evidence_by_item: defaultdict[str, list[ContractEvidenceView]] = defaultdict(list)
    if item_ids:
        rows = session.execute(
            select(ImplementationContractEvidence, Block)
            .join(Block, ImplementationContractEvidence.block_id == Block.id)
            .where(ImplementationContractEvidence.item_id.in_(item_ids))
            .order_by(
                ImplementationContractEvidence.item_id,
                ImplementationContractEvidence.quote_start,
                ImplementationContractEvidence.quote_end,
                ImplementationContractEvidence.id,
            )
        ).all()
        for anchor, block in rows:
            evidence_by_item[anchor.item_id].append(
                ContractEvidenceView(
                    id=anchor.id,
                    block_id=anchor.block_id,
                    research_node_id=anchor.research_node_id,
                    locator_type=anchor.locator_type,
                    quote_text=anchor.quote_text,
                    quote_start=anchor.quote_start,
                    quote_end=anchor.quote_end,
                    source_quote_hash=anchor.source_quote_hash,
                    relation=anchor.relation,
                    source_label=anchor.source_label,
                    page_number=block.page_number,
                    block_type=block.block_type,
                    translated_text=block.translated_text,
                )
            )
    issue_models = session.scalars(
        select(ImplementationContractIssue)
        .where(ImplementationContractIssue.contract_version_id == version.id)
        .order_by(
            ImplementationContractIssue.severity,
            ImplementationContractIssue.code,
            ImplementationContractIssue.id,
        )
    ).all()
    issue_views = tuple(
        ContractIssueView(
            id=issue.id,
            item_id=issue.item_id,
            code=issue.code,
            severity=issue.severity,
            message=issue.message,
        )
        for issue in issue_models
    )
    issues_by_item: defaultdict[str, list[ContractIssueView]] = defaultdict(list)
    for issue in issue_views:
        if issue.item_id is not None:
            issues_by_item[issue.item_id].append(issue)

    resolution_rows = _load_resolution_models(
        session,
        _lineage_version_ids(session, version),
        item_models,
    )
    history_by_identity: defaultdict[tuple[str, str], list[ContractResolutionView]] = (
        defaultdict(list)
    )
    effective_by_identity: dict[tuple[str, str], ContractResolutionView] = {}
    for resolution_model, item_key in resolution_rows:
        resolution = _resolution_view(resolution_model)
        identity = (item_key, resolution.based_on_item_signature)
        history_by_identity[identity].append(resolution)
        effective_by_identity[identity] = resolution

    item_views = tuple(
        _item_view(
            item,
            tuple(evidence_by_item[item.id]),
            tuple(issues_by_item[item.id]),
            effective_by_identity.get((item.item_key, item.item_signature)),
            tuple(history_by_identity[(item.item_key, item.item_signature)]),
        )
        for item in item_models
    )
    reader_is_current = (
        document.status == "completed"
        and document.processed_content_hash == document.content_hash
        and version.source_content_hash == document.content_hash
    )
    map_is_current = (
        map_version.document_id == document.id
        and map_version.source_content_hash == document.content_hash
        and version.research_map_signature
        == _research_map_signature(session, map_version)
    )
    is_current = reader_is_current and map_is_current
    return ImplementationContractView(
        id=version.id,
        document_id=version.document_id,
        research_map_version_id=version.research_map_version_id,
        previous_version_id=version.previous_version_id,
        source_content_hash=version.source_content_hash,
        research_map_signature=version.research_map_signature,
        schema_version=version.schema_version,
        provider=version.provider,
        model_name=version.model_name,
        status=version.status,
        readiness=version.readiness,
        is_active=version.is_active,
        is_current=is_current,
        is_stale=not is_current,
        created_at=version.created_at,
        completed_at=version.completed_at,
        items=item_views,
        issues=issue_views,
    )


def list_implementation_contract_versions(
    session: Session,
    document_id: str,
    *,
    limit: int = 50,
) -> tuple[ImplementationContractVersionSummaryView, ...]:
    if not 1 <= limit <= 100:
        raise ValueError("Contract history limit must be between 1 and 100")
    document = session.get(Document, document_id)
    if document is None:
        raise ImplementationContractNotFoundError("Document not found")
    versions = session.scalars(
        select(ImplementationContractVersion)
        .where(ImplementationContractVersion.document_id == document_id)
        .order_by(
            ImplementationContractVersion.created_at.desc(),
            ImplementationContractVersion.id.desc(),
        )
        .limit(limit)
    ).all()
    map_ids = tuple({version.research_map_version_id for version in versions})
    maps_by_id = {
        map_version.id: map_version
        for map_version in session.scalars(
            select(ResearchMapVersion).where(ResearchMapVersion.id.in_(map_ids))
        ).all()
    }
    map_signatures = _research_map_signatures(session, map_ids, maps_by_id)
    summaries: list[ImplementationContractVersionSummaryView] = []
    for version in versions:
        map_version = maps_by_id.get(version.research_map_version_id)
        is_current = (
            document.status == "completed"
            and document.processed_content_hash == document.content_hash
            and version.source_content_hash == document.content_hash
            and map_version is not None
            and map_version.document_id == document.id
            and map_version.source_content_hash == document.content_hash
            and version.research_map_signature == map_signatures[map_version.id]
        )
        summaries.append(
            ImplementationContractVersionSummaryView(
                id=version.id,
                document_id=version.document_id,
                research_map_version_id=version.research_map_version_id,
                previous_version_id=version.previous_version_id,
                source_content_hash=version.source_content_hash,
                research_map_signature=version.research_map_signature,
                schema_version=version.schema_version,
                provider=version.provider,
                model_name=version.model_name,
                status=version.status,
                readiness=version.readiness,
                is_active=version.is_active,
                is_current=is_current,
                is_stale=not is_current,
                created_at=version.created_at,
                completed_at=version.completed_at,
            )
        )
    return tuple(summaries)


def load_implementation_contract_library_summaries(
    session: Session,
    documents: Sequence[Document],
) -> dict[str, ImplementationContractLibrarySummaryView]:
    """Load compact active-contract state with a fixed number of queries."""
    if not documents:
        return {}
    documents_by_id = {document.id: document for document in documents}
    version_rows = session.execute(
        select(ImplementationContractVersion, ResearchMapVersion)
        .join(
            ResearchMapVersion,
            ImplementationContractVersion.research_map_version_id
            == ResearchMapVersion.id,
        )
        .where(
            ImplementationContractVersion.document_id.in_(documents_by_id),
            ImplementationContractVersion.is_active.is_(True),
        )
    ).all()
    if not version_rows:
        return {}

    versions = [version for version, _map_version in version_rows]
    maps_by_id = {map_version.id: map_version for _version, map_version in version_rows}
    version_ids = [version.id for version in versions]
    map_ids = list(maps_by_id)
    items = session.scalars(
        select(ImplementationContractItem).where(
            ImplementationContractItem.contract_version_id.in_(version_ids)
        )
    ).all()
    items_by_version: defaultdict[str, list[ImplementationContractItem]] = defaultdict(
        list
    )
    signatures: set[str] = set()
    for item in items:
        items_by_version[item.contract_version_id].append(item)
        signatures.add(item.item_signature)

    blocker_counts = {
        version_id: count
        for version_id, count in session.execute(
            select(
                ImplementationContractIssue.contract_version_id,
                func.count(ImplementationContractIssue.id),
            )
            .where(
                ImplementationContractIssue.contract_version_id.in_(version_ids),
                ImplementationContractIssue.severity == "error",
            )
            .group_by(ImplementationContractIssue.contract_version_id)
        ).all()
    }
    reviewed_signatures_by_document: defaultdict[str, set[str]] = defaultdict(set)
    if signatures:
        resolution_rows = session.execute(
            select(
                ImplementationContractVersion.document_id,
                ImplementationContractResolution.based_on_item_signature,
            )
            .join(
                ImplementationContractVersion,
                ImplementationContractResolution.based_on_contract_version_id
                == ImplementationContractVersion.id,
            )
            .where(
                ImplementationContractVersion.document_id.in_(documents_by_id),
                ImplementationContractResolution.based_on_item_signature.in_(
                    signatures
                ),
            )
            .distinct()
        ).all()
        for document_id, signature in resolution_rows:
            reviewed_signatures_by_document[document_id].add(signature)

    map_signatures = _research_map_signatures(session, map_ids, maps_by_id)
    summaries: dict[str, ImplementationContractLibrarySummaryView] = {}
    for version in versions:
        document = documents_by_id[version.document_id]
        map_version = maps_by_id[version.research_map_version_id]
        version_items = items_by_version[version.id]
        reviewed_signatures = reviewed_signatures_by_document[document.id]
        is_current = (
            document.status == "completed"
            and document.processed_content_hash == document.content_hash
            and version.source_content_hash == document.content_hash
            and map_version.document_id == document.id
            and map_version.source_content_hash == document.content_hash
            and version.research_map_signature == map_signatures[map_version.id]
        )
        summaries[document.id] = ImplementationContractLibrarySummaryView(
            version_id=version.id,
            generation_status=version.status,
            readiness=version.readiness,
            is_current=is_current,
            is_stale=not is_current,
            blocker_count=blocker_counts.get(version.id, 0),
            reviewed_count=sum(
                item.item_signature in reviewed_signatures for item in version_items
            ),
            total_reviewable_count=len(version_items),
        )
    return summaries


def _research_map_signatures(
    session: Session,
    map_ids: Sequence[str],
    maps_by_id: dict[str, ResearchMapVersion],
) -> dict[str, str]:
    nodes = session.scalars(
        select(ResearchNode)
        .where(ResearchNode.map_version_id.in_(map_ids))
        .order_by(ResearchNode.node_key, ResearchNode.id)
    ).all()
    nodes_by_map: defaultdict[str, list[ResearchNode]] = defaultdict(list)
    for node in nodes:
        nodes_by_map[node.map_version_id].append(node)
    evidence_by_map: defaultdict[str, list[str]] = defaultdict(list)
    for map_id, source_quote_hash in session.execute(
        select(ResearchNode.map_version_id, ResearchEvidence.source_quote_hash)
        .join(ResearchEvidence, ResearchEvidence.node_id == ResearchNode.id)
        .where(ResearchNode.map_version_id.in_(map_ids))
        .order_by(
            ResearchNode.map_version_id,
            ResearchEvidence.source_quote_hash,
            ResearchEvidence.id,
        )
    ).all():
        evidence_by_map[map_id].append(source_quote_hash)
    signatures: dict[str, str] = {}
    for map_id in map_ids:
        map_version = maps_by_id[map_id]
        payload = {
            "map_version_id": map_version.id,
            "schema_version": map_version.schema_version,
            "source_content_hash": map_version.source_content_hash,
            "nodes": [
                [node.id, node.node_key, node.node_signature]
                for node in nodes_by_map[map_id]
            ],
            "evidence_hashes": evidence_by_map[map_id],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        signatures[map_id] = hashlib.sha256(encoded.encode()).hexdigest()
    return signatures


def activate_implementation_contract(
    session: Session,
    version_id: str,
) -> ImplementationContractView:
    target = session.get(ImplementationContractVersion, version_id)
    if target is None:
        raise ImplementationContractNotFoundError("Implementation Contract not found")
    if target.status not in {"complete", "partial"} or target.completed_at is None:
        raise ImplementationContractConflictError(
            "Only complete or partial Implementation Contracts can be activated"
        )
    with session.begin_nested():
        current_versions = session.scalars(
            select(ImplementationContractVersion).where(
                ImplementationContractVersion.document_id == target.document_id,
                ImplementationContractVersion.is_active.is_(True),
                ImplementationContractVersion.id != target.id,
            )
        ).all()
        for version in current_versions:
            version.is_active = False
        session.flush()
        target.is_active = True
        session.flush()
    return load_implementation_contract(session, target.id)


def diff_implementation_contracts(
    session: Session,
    version_id: str,
    against_version_id: str,
) -> ImplementationContractDiffView:
    version = session.get(ImplementationContractVersion, version_id)
    against = session.get(ImplementationContractVersion, against_version_id)
    if version is None or against is None:
        raise ImplementationContractNotFoundError("Implementation Contract not found")
    if version.document_id != against.document_id:
        raise ImplementationContractConflictError(
            "Implementation Contract versions must belong to the same document"
        )
    all_items = session.scalars(
        select(ImplementationContractItem).where(
            ImplementationContractItem.contract_version_id.in_((version.id, against.id))
        )
    ).all()
    items_by_version: defaultdict[str, dict[str, ImplementationContractItem]] = (
        defaultdict(dict)
    )
    for item in all_items:
        items_by_version[item.contract_version_id][item.item_key] = item
    item_ids = [item.id for item in all_items]
    evidence_hashes_by_item: defaultdict[str, list[str]] = defaultdict(list)
    if item_ids:
        for item_id, source_quote_hash in session.execute(
            select(
                ImplementationContractEvidence.item_id,
                ImplementationContractEvidence.source_quote_hash,
            )
            .where(ImplementationContractEvidence.item_id.in_(item_ids))
            .order_by(
                ImplementationContractEvidence.item_id,
                ImplementationContractEvidence.source_quote_hash,
            )
        ).all():
            evidence_hashes_by_item[item_id].append(source_quote_hash)
    differences: list[ContractItemDiffView] = []
    for item_key in set(items_by_version[version.id]) | set(
        items_by_version[against.id]
    ):
        current = items_by_version[version.id].get(item_key)
        previous = items_by_version[against.id].get(item_key)
        classification = _diff_classification(
            current,
            previous,
            evidence_hashes_by_item,
        )
        representative = current or previous
        if representative is None:
            raise ImplementationContractConflictError(
                "Implementation Contract diff contains no comparable item"
            )
        differences.append(
            ContractItemDiffView(
                item_key=item_key,
                classification=classification,
                version_item_id=current.id if current is not None else None,
                against_item_id=previous.id if previous is not None else None,
                section_order=_SECTION_ORDER[
                    validate_contract_section(representative.section)
                ],
                display_order=representative.display_order,
            )
        )
    differences.sort(
        key=lambda item: (item.section_order, item.display_order, item.item_key)
    )
    return ImplementationContractDiffView(
        version_id=version.id,
        against_version_id=against.id,
        items=tuple(differences),
    )


def _diff_classification(
    current: ImplementationContractItem | None,
    previous: ImplementationContractItem | None,
    evidence_hashes_by_item: dict[str, list[str]],
) -> str:
    if previous is None:
        return validate_diff_classification("added")
    if current is None:
        return validate_diff_classification("removed")
    if current.item_type != previous.item_type:
        return validate_diff_classification("type_changed")
    if current.draft_value_json != previous.draft_value_json:
        return validate_diff_classification("value_changed")
    if current.origin != previous.origin:
        return validate_diff_classification("origin_changed")
    if (
        evidence_hashes_by_item[current.id] != evidence_hashes_by_item[previous.id]
        or current.rationale != previous.rationale
    ):
        return validate_diff_classification("evidence_changed")
    return validate_diff_classification("unchanged")


def _item_view(
    item: ImplementationContractItem,
    evidence: tuple[ContractEvidenceView, ...],
    issues: tuple[ContractIssueView, ...],
    resolution: ContractResolutionView | None,
    resolution_history: tuple[ContractResolutionView, ...],
) -> ContractItemView:
    section = validate_contract_section(item.section)
    item_type = validate_contract_item_type(item.item_type)
    origin = validate_contract_origin(item.origin)
    value = (
        decode_contract_value(json.loads(item.draft_value_json))
        if item.draft_value_json is not None
        else None
    )
    draft = ContractItemDraft(
        item_key=item.item_key,
        section=section,
        item_type=item_type,
        value=value,
        origin=origin,
        rationale=item.rationale,
        is_blocking=item.is_blocking,
        is_optional=item.is_optional,
        display_order=item.display_order,
    )
    resolution_draft = (
        ContractResolutionDraft(
            status=validate_resolution_status(resolution.status),
            value=resolution.resolved_value,
            reason=resolution.reason,
        )
        if resolution is not None
        else None
    )
    effective = audit_contract(
        (
            EffectiveContractItem(
                draft=draft,
                evidence=(),
                resolution=resolution_draft,
            ),
        )
    ).items[0]
    return ContractItemView(
        id=item.id,
        item_key=item.item_key,
        section=section,
        item_type=item_type,
        draft_value=value,
        effective_value=effective.effective_value,
        origin=origin,
        effective_origin=effective.effective_origin,
        rationale=item.rationale,
        is_blocking=item.is_blocking,
        is_optional=item.is_optional,
        display_order=item.display_order,
        item_signature=item.item_signature,
        evidence=evidence,
        issues=issues,
        resolution=resolution,
        resolution_history=resolution_history,
    )


def _load_resolution_models(
    session: Session,
    lineage_version_ids: set[str],
    items: Sequence[ImplementationContractItem],
) -> Sequence[tuple[ImplementationContractResolution, str]]:
    if not items:
        return ()
    item_ids = [item.id for item in items]
    item_identities = {(item.item_key, item.item_signature) for item in items}
    rows = session.execute(
        select(ImplementationContractResolution, ImplementationContractItem.item_key)
        .join(
            ImplementationContractItem,
            ImplementationContractResolution.item_id == ImplementationContractItem.id,
        )
        .join(
            ImplementationContractVersion,
            ImplementationContractItem.contract_version_id
            == ImplementationContractVersion.id,
        )
        .where(
            ImplementationContractResolution.based_on_contract_version_id.in_(
                lineage_version_ids
            ),
            (
                ImplementationContractResolution.item_id.in_(item_ids)
                | tuple_(
                    ImplementationContractItem.item_key,
                    ImplementationContractResolution.based_on_item_signature,
                ).in_(item_identities)
            ),
        )
        .order_by(
            ImplementationContractResolution.resolved_at,
            ImplementationContractResolution.revision_number,
            ImplementationContractResolution.id,
        )
    ).all()
    return tuple((resolution, item_key) for resolution, item_key in rows)


def _lineage_version_ids(
    session: Session,
    version: ImplementationContractVersion,
) -> set[str]:
    rows = session.execute(
        select(
            ImplementationContractVersion.id,
            ImplementationContractVersion.previous_version_id,
        ).where(ImplementationContractVersion.document_id == version.document_id)
    ).all()
    previous_by_id = {version_id: previous_id for version_id, previous_id in rows}
    lineage: set[str] = set()
    current_id: str | None = version.id
    while current_id is not None:
        if current_id in lineage:
            raise ImplementationContractConflictError(
                "Implementation Contract version lineage contains a cycle"
            )
        lineage.add(current_id)
        current_id = previous_by_id.get(current_id)
    return lineage


def _resolution_view(
    resolution: ImplementationContractResolution,
) -> ContractResolutionView:
    value = (
        decode_contract_value(json.loads(resolution.resolved_value_json))
        if resolution.resolved_value_json is not None
        else None
    )
    draft = ContractResolutionDraft(
        status=validate_resolution_status(resolution.status),
        value=value,
        reason=resolution.reason,
    )
    return ContractResolutionView(
        id=resolution.id,
        item_id=resolution.item_id,
        revision_number=resolution.revision_number,
        supersedes_resolution_id=resolution.supersedes_resolution_id,
        status=draft.status,
        resolved_value=draft.value,
        reason=draft.reason,
        based_on_contract_version_id=resolution.based_on_contract_version_id,
        based_on_item_signature=resolution.based_on_item_signature,
        request_id=resolution.request_id,
        resolved_at=_as_utc(resolution.resolved_at),
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
