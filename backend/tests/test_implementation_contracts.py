from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from glyph.contract_ai import (
    ContractInputBlock,
    MockImplementationContractProvider,
    SynthesizedContractItem,
    ValidatedContractEvidence,
)
from glyph.contract_domain import decode_contract_value, encode_contract_value
from glyph.implementation_contracts import (
    ImplementationContractConflictError,
    ImplementationContractNotFoundError,
    ImplementationContractService,
    load_implementation_contract,
)
from glyph.models import (
    Base,
    Block,
    Document,
    ImplementationContractEvidence,
    ImplementationContractIssue,
    ImplementationContractItem,
    ImplementationContractVersion,
    ResearchEvidence,
    ResearchMapVersion,
    ResearchNode,
    ResearchNodeReview,
)
from glyph.research_evidence import exact_quote_hash

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "contracts"


class RecordingProvider:
    provider_name = "recording_mock"
    model_name: str | None = None

    def __init__(self) -> None:
        self._delegate = MockImplementationContractProvider()
        self.extracted_blocks: tuple[ContractInputBlock, ...] = ()
        self.synthesized_evidence: tuple[ValidatedContractEvidence, ...] = ()

    def extract_requirements(self, blocks):  # type: ignore[no-untyped-def]
        self.extracted_blocks = tuple(blocks)
        return self._delegate.extract_requirements(blocks)

    def synthesize_contract(self, evidence):  # type: ignore[no-untyped-def]
        assert all(isinstance(item, ValidatedContractEvidence) for item in evidence)
        assert all(item.anchor.source_quote_hash for item in evidence)
        self.synthesized_evidence = tuple(evidence)
        return self._delegate.synthesize_contract(evidence)


class PartialProvider(MockImplementationContractProvider):
    provider_name = "partial_mock"

    def synthesize_contract(self, evidence):  # type: ignore[no-untyped-def]
        items = super().synthesize_contract(evidence)
        return (
            SynthesizedContractItem(items[0].draft, ()),
            *items[1:],
        )


@pytest.fixture
def contract_database_factory() -> Iterator[
    Callable[[str], tuple[Session, Document, ResearchMapVersion]]
]:
    resources: list[tuple[Session, Engine]] = []

    def create(
        source_file: str = "monthly_accounting_signal.txt",
    ) -> tuple[Session, Document, ResearchMapVersion]:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        session = Session(engine)
        resources.append((session, engine))
        source_text = (FIXTURE_DIRECTORY / source_file).read_text(encoding="utf-8")
        source_hash = hashlib.sha256(source_text.encode()).hexdigest()
        document = Document(
            id="paper-1",
            title=source_file.removesuffix(".txt"),
            source_path=f"/books/{source_file}",
            content_hash=source_hash,
            processed_content_hash=source_hash,
            file_type="txt",
            status="completed",
        )
        block = Block(
            id="source",
            document_id=document.id,
            source_content_hash=source_hash,
            order_index=0,
            page_number=1,
            block_type="text",
            source_text=source_text,
            translated_text=f"繁中：{source_text}",
        )
        map_version = ResearchMapVersion(
            id="map-active",
            document_id=document.id,
            previous_version_id=None,
            source_content_hash=source_hash,
            schema_version="1",
            provider="mock",
            model_name=None,
            status="complete",
            is_active=True,
        )
        node = ResearchNode(
            id="map-node",
            map_version_id=map_version.id,
            parent_node_id=None,
            node_key="author_claim.1",
            node_type="author_claim",
            title="Research claim",
            claim_text="The source states a reproducible signal.",
            explanation="",
            provenance="author_explicit",
            evidence_quality="direct",
            display_order=0,
            node_signature="c" * 64,
        )
        quote = source_text.splitlines()[1]
        quote_start = source_text.index(quote)
        session.add_all(
            [
                document,
                block,
                map_version,
                node,
                ResearchEvidence(
                    id="map-evidence",
                    node_id=node.id,
                    block_id=block.id,
                    locator_type="text_span",
                    quote_text=quote,
                    quote_start=quote_start,
                    quote_end=quote_start + len(quote),
                    source_quote_hash=exact_quote_hash(
                        block.id,
                        quote_start,
                        quote_start + len(quote),
                        quote,
                    ),
                    relation="supports",
                    source_label="Research claim",
                ),
            ]
        )
        session.commit()
        return session, document, map_version

    try:
        yield create
    finally:
        for session, engine in resources:
            session.close()
            engine.dispose()


def _counts(session: Session) -> dict[str, int]:
    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model))
        or 0
        for model in (
            ImplementationContractVersion,
            ImplementationContractItem,
            ImplementationContractEvidence,
            ImplementationContractIssue,
        )
    }


def _snapshot_contract(session: Session, version_id: str) -> tuple[object, ...]:
    version = session.get(ImplementationContractVersion, version_id)
    assert version is not None
    items = session.scalars(
        select(ImplementationContractItem)
        .where(ImplementationContractItem.contract_version_id == version_id)
        .order_by(ImplementationContractItem.item_key)
    ).all()
    item_ids = [item.id for item in items]
    evidence = session.scalars(
        select(ImplementationContractEvidence)
        .where(ImplementationContractEvidence.item_id.in_(item_ids))
        .order_by(
            ImplementationContractEvidence.item_id, ImplementationContractEvidence.id
        )
    ).all()
    issues = session.scalars(
        select(ImplementationContractIssue)
        .where(ImplementationContractIssue.contract_version_id == version_id)
        .order_by(ImplementationContractIssue.code, ImplementationContractIssue.id)
    ).all()
    return (
        (
            version.id,
            version.document_id,
            version.research_map_version_id,
            version.previous_version_id,
            version.source_content_hash,
            version.research_map_signature,
            version.schema_version,
            version.provider,
            version.model_name,
            version.status,
            version.readiness,
            version.is_active,
        ),
        tuple(
            (
                item.id,
                item.item_key,
                item.draft_value_json,
                item.origin,
                item.item_signature,
            )
            for item in items
        ),
        tuple(
            (
                anchor.id,
                anchor.item_id,
                anchor.block_id,
                anchor.quote_start,
                anchor.quote_end,
                anchor.source_quote_hash,
                anchor.relation,
            )
            for anchor in evidence
        ),
        tuple(
            (issue.id, issue.item_id, issue.code, issue.severity, issue.message)
            for issue in issues
        ),
    )


def test_generate_runs_the_exact_evidence_first_stage_order_and_persists_view(
    contract_database_factory,
) -> None:
    session, document, map_version = contract_database_factory()
    provider = RecordingProvider()
    stages: list[tuple[str, float]] = []
    service = ImplementationContractService(
        session,
        provider,
        lambda stage, progress: stages.append((stage, progress)),
    )

    contract = service.generate(document.id)
    session.commit()

    assert [stage for stage, _ in stages] == [
        "load_context",
        "extract_requirements",
        "validate_evidence",
        "synthesize_contract",
        "audit_readiness",
        "persist_and_activate",
    ]
    assert [progress for _, progress in stages] == sorted(
        progress for _, progress in stages
    )
    assert provider.extracted_blocks[0].source_text.startswith(
        "MONTHLY ACCOUNTING SIGNAL"
    )
    assert provider.synthesized_evidence
    assert contract.document_id == document.id
    assert contract.research_map_version_id == map_version.id
    assert contract.provider == "recording_mock"
    assert contract.status == "complete"
    assert contract.readiness == "review_needed"
    assert contract.is_active is True
    assert contract.is_current is True
    assert contract.is_stale is False
    assert len(contract.items) == 16
    assert contract.issues
    assert all(item.item_signature for item in contract.items)
    assert all(item.evidence for item in contract.items)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda document, _map, _session: setattr(document, "status", "stale"),
            "current completed Reader",
        ),
        (
            lambda document, _map, _session: setattr(
                document, "processed_content_hash", None
            ),
            "current completed Reader",
        ),
        (
            lambda _document, _map, session: session.query(Block).delete(),
            "Reader blocks",
        ),
        (
            lambda _document, map_version, _session: setattr(
                map_version, "status", "building"
            ),
            "complete or partial",
        ),
        (
            lambda _document, map_version, _session: setattr(
                map_version, "source_content_hash", "f" * 64
            ),
            "same current source",
        ),
    ],
)
def test_generation_requires_current_reader_and_eligible_map(
    contract_database_factory,
    mutation,
    message: str,
) -> None:
    session, document, map_version = contract_database_factory()
    mutation(document, map_version, session)
    session.commit()

    with pytest.raises(ImplementationContractConflictError, match=message):
        ImplementationContractService(
            session, MockImplementationContractProvider()
        ).generate(document.id)

    assert _counts(session)["implementation_contract_versions"] == 0


def test_generation_rejects_missing_document_map_and_cross_document_map(
    contract_database_factory,
) -> None:
    session, document, map_version = contract_database_factory()

    with pytest.raises(ImplementationContractNotFoundError, match="Document"):
        ImplementationContractService(
            session, MockImplementationContractProvider()
        ).generate("missing-paper")
    map_version.is_active = False
    session.commit()
    with pytest.raises(
        ImplementationContractConflictError, match="active Research Map"
    ):
        ImplementationContractService(
            session, MockImplementationContractProvider()
        ).generate(document.id)
    with pytest.raises(ImplementationContractNotFoundError, match="Research Map"):
        ImplementationContractService(
            session, MockImplementationContractProvider()
        ).generate(document.id, "missing-map")

    foreign_document = Document(
        id="paper-foreign",
        title="Foreign",
        source_path="/books/foreign.txt",
        content_hash="e" * 64,
        processed_content_hash="e" * 64,
        file_type="txt",
        status="completed",
    )
    foreign_map = ResearchMapVersion(
        id="map-foreign",
        document_id=foreign_document.id,
        previous_version_id=None,
        source_content_hash="e" * 64,
        schema_version="1",
        provider="mock",
        model_name=None,
        status="complete",
        is_active=True,
    )
    session.add_all([foreign_document, foreign_map])
    session.commit()

    with pytest.raises(ImplementationContractConflictError, match="same document"):
        ImplementationContractService(
            session, MockImplementationContractProvider()
        ).generate(document.id, foreign_map.id)


def test_explicit_inactive_immutable_map_is_supported(
    contract_database_factory,
) -> None:
    session, document, active_map = contract_database_factory()
    explicit_map = ResearchMapVersion(
        id="map-explicit",
        document_id=document.id,
        previous_version_id=active_map.id,
        source_content_hash=document.content_hash,
        schema_version="1",
        provider="mock",
        model_name=None,
        status="partial",
        is_active=False,
    )
    session.add(explicit_map)
    session.commit()

    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id, explicit_map.id)

    assert contract.research_map_version_id == explicit_map.id
    assert contract.is_current is True


def test_values_and_signatures_are_canonical_and_replacement_switches_active(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    service = ImplementationContractService(
        session, MockImplementationContractProvider()
    )
    first = service.generate(document.id)
    session.commit()
    first_signatures = {item.item_key: item.item_signature for item in first.items}

    second = service.generate(document.id)
    session.commit()
    session.expire_all()

    first_model = session.get(ImplementationContractVersion, first.id)
    second_model = session.get(ImplementationContractVersion, second.id)
    assert first_model is not None and first_model.is_active is False
    assert second_model is not None and second_model.is_active is True
    assert second.previous_version_id == first.id
    assert {item.item_key: item.item_signature for item in second.items} == (
        first_signatures
    )
    required_dataset = session.scalar(
        select(ImplementationContractItem).where(
            ImplementationContractItem.contract_version_id == second.id,
            ImplementationContractItem.item_key == "required_dataset.1",
        )
    )
    assert required_dataset is not None
    assert required_dataset.draft_value_json is not None
    decoded = decode_contract_value(json.loads(required_dataset.draft_value_json))
    assert required_dataset.draft_value_json == encode_contract_value(decoded)
    assert session.scalars(
        select(ImplementationContractVersion).where(
            ImplementationContractVersion.is_active.is_(True)
        )
    ).all() == [second_model]


def test_partial_blocked_contract_can_be_active_but_is_labelled_honestly(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory(
        "cross_market_long_short.txt"
    )

    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)

    assert contract.status == "complete"
    assert contract.readiness == "blocked"
    assert contract.is_active is True
    assert {issue.code for issue in contract.issues} >= {"missing_blocker"}
    assert {
        item.item_key
        for item in contract.items
        if item.origin == "missing" and item.is_blocking
    } == {"transaction_cost.1", "weighting_rule.1"}


def test_partial_generation_can_be_active_but_is_labelled_partial(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()

    contract = ImplementationContractService(session, PartialProvider()).generate(
        document.id
    )

    assert contract.status == "partial"
    assert contract.readiness == "blocked"
    assert contract.is_active is True
    assert "explicit_without_evidence" in {issue.code for issue in contract.issues}


def test_failed_replacement_rolls_back_partial_rows_and_preserves_active_contract(
    contract_database_factory,
    monkeypatch,
) -> None:
    session, document, _map_version = contract_database_factory()
    service = ImplementationContractService(
        session, MockImplementationContractProvider()
    )
    original = service.generate(document.id)
    session.commit()
    before_snapshot = _snapshot_contract(session, original.id)
    before_counts = _counts(session)
    from glyph import implementation_contracts as module

    original_persist_items = module.persist_items

    def fail_after_first_item(session_arg, version, items):  # type: ignore[no-untyped-def]
        original_persist_items(session_arg, version, items[:1])
        session_arg.flush()
        raise RuntimeError("injected persistence failure")

    monkeypatch.setattr(module, "persist_items", fail_after_first_item)

    with pytest.raises(RuntimeError, match="injected persistence failure"):
        service.generate(document.id)

    session.expire_all()
    assert _counts(session) == before_counts
    assert _snapshot_contract(session, original.id) == before_snapshot
    active_id = session.scalar(
        select(ImplementationContractVersion.id).where(
            ImplementationContractVersion.document_id == document.id,
            ImplementationContractVersion.is_active.is_(True),
        )
    )
    assert active_id == original.id


def test_stale_state_uses_both_reader_hash_and_research_map_signature(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    session.commit()

    assert load_implementation_contract(session, contract.id).is_current is True
    original_hash = document.content_hash
    document.content_hash = "f" * 64
    session.commit()
    source_stale = load_implementation_contract(session, contract.id)
    assert source_stale.is_current is False
    assert source_stale.is_stale is True

    document.content_hash = original_hash
    node = session.get(ResearchNode, "map-node")
    assert node is not None
    node.node_signature = "d" * 64
    session.commit()
    map_stale = load_implementation_contract(session, contract.id)
    assert map_stale.is_current is False
    assert map_stale.is_stale is True


def test_human_map_reviews_do_not_change_contract_signature_or_source_evidence(
    contract_database_factory,
) -> None:
    session, document, map_version = contract_database_factory()
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    session.commit()
    signature = contract.research_map_signature
    session.add(
        ResearchNodeReview(
            id="review-1",
            node_id="map-node",
            revision_number=1,
            supersedes_review_id=None,
            status="corrected",
            corrected_claim_text="A human correction that is not source truth.",
            review_note="Context only.",
            based_on_map_version_id=map_version.id,
            based_on_node_signature="c" * 64,
        )
    )
    session.commit()

    loaded = load_implementation_contract(session, contract.id)

    assert loaded.research_map_signature == signature
    assert loaded.is_current is True
    assert all(
        anchor.research_node_id is None
        for item in loaded.items
        for anchor in item.evidence
    )


def test_loader_batches_items_evidence_and_issues_without_n_plus_one(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    session.commit()
    session.expire_all()
    statements: list[str] = []

    def record_selects(_connection, _cursor, statement, _parameters, _context, _many):  # type: ignore[no-untyped-def]
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(session.get_bind(), "before_cursor_execute", record_selects)
    try:
        loaded = load_implementation_contract(session, contract.id)
    finally:
        event.remove(session.get_bind(), "before_cursor_execute", record_selects)

    contract_evidence_selects = [
        statement
        for statement in statements
        if "implementation_contract_evidence" in statement
    ]
    assert len(loaded.items) == 16
    assert sum(len(item.evidence) for item in loaded.items) == 17
    assert len(statements) <= 9
    assert len(contract_evidence_selects) == 1
