from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
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
    ContractValue,
    decode_contract_value,
    encode_contract_value,
    item_signature,
    validate_contract_item_type,
    validate_contract_origin,
    validate_contract_section,
)
from glyph.contract_evidence import ContractEvidenceContext
from glyph.models import (
    Block,
    Document,
    ImplementationContractEvidence,
    ImplementationContractIssue,
    ImplementationContractItem,
    ImplementationContractVersion,
    ResearchEvidence,
    ResearchMapVersion,
    ResearchNode,
)

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
        version.status = audit.generation_status
        version.readiness = audit.readiness
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

    item_views = tuple(
        _item_view(
            item,
            tuple(evidence_by_item[item.id]),
            tuple(issues_by_item[item.id]),
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


def _item_view(
    item: ImplementationContractItem,
    evidence: tuple[ContractEvidenceView, ...],
    issues: tuple[ContractIssueView, ...],
) -> ContractItemView:
    section = validate_contract_section(item.section)
    item_type = validate_contract_item_type(item.item_type)
    origin = validate_contract_origin(item.origin)
    value = (
        decode_contract_value(json.loads(item.draft_value_json))
        if item.draft_value_json is not None
        else None
    )
    ContractItemDraft(
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
    return ContractItemView(
        id=item.id,
        item_key=item.item_key,
        section=section,
        item_type=item_type,
        draft_value=value,
        effective_value=value,
        origin=origin,
        effective_origin=origin,
        rationale=item.rationale,
        is_blocking=item.is_blocking,
        is_optional=item.is_optional,
        display_order=item.display_order,
        item_signature=item.item_signature,
        evidence=evidence,
        issues=issues,
    )
