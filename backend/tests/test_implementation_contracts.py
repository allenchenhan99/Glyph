from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from glyph.contract_ai import (
    ContractInputBlock,
    MockImplementationContractProvider,
    SynthesizedContractItem,
    ValidatedContractEvidence,
)
from glyph.contract_domain import (
    ContractItemDraft,
    ListValue,
    ScalarValue,
    decode_contract_value,
    encode_contract_value,
)
from glyph.implementation_contracts import (
    ImplementationContractConflictError,
    ImplementationContractNotFoundError,
    ImplementationContractService,
    activate_implementation_contract,
    append_contract_resolution,
    diff_implementation_contracts,
    list_implementation_contract_versions,
    load_implementation_contract,
)
from glyph.models import (
    Base,
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
    ResearchNodeReview,
)
from glyph.pipeline import clear_document_outputs
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


class ChangedValueProvider(MockImplementationContractProvider):
    provider_name = "changed_value_mock"

    def synthesize_contract(self, evidence):  # type: ignore[no-untyped-def]
        items = list(super().synthesize_contract(evidence))
        first = items[0]
        changed_value = ListValue(
            kind="list",
            values=(
                ScalarValue(kind="scalar", value="Compustat"),
                ScalarValue(kind="scalar", value="CRSP"),
                ScalarValue(kind="scalar", value="IBES"),
            ),
        )
        items[0] = SynthesizedContractItem(
            replace(first.draft, value=changed_value), first.evidence_ids
        )
        return tuple(items)


class DiffClassificationProvider(MockImplementationContractProvider):
    provider_name = "diff_mock"

    def synthesize_contract(self, evidence):  # type: ignore[no-untyped-def]
        items = list(super().synthesize_contract(evidence))
        by_key = {item.draft.item_key: item for item in items}
        required_field = by_key["required_field.1"]
        by_key["required_field.1"] = SynthesizedContractItem(
            replace(
                required_field.draft,
                value=ListValue(
                    kind="list",
                    values=(ScalarValue(kind="scalar", value="revised_field"),),
                ),
            ),
            required_field.evidence_ids,
        )
        direction = by_key["signal_direction.1"]
        by_key["signal_direction.1"] = SynthesizedContractItem(
            replace(direction.draft, origin="author_explicit", rationale=None),
            direction.evidence_ids,
        )
        frequency = by_key["data_frequency.1"]
        by_key["data_frequency.1"] = SynthesizedContractItem(frequency.draft, ())
        statistical_test = by_key["statistical_test.1"]
        by_key["statistical_test.1"] = SynthesizedContractItem(
            replace(statistical_test.draft, item_type="evaluation_metric"),
            statistical_test.evidence_ids,
        )
        del by_key["availability_lag.1"]
        added = SynthesizedContractItem(
            ContractItemDraft(
                item_key="sample_filter.1",
                section="universe_and_sample",
                item_type="sample_filter",
                value=None,
                origin="missing",
                rationale="The paper does not state an additional sample filter.",
                is_blocking=False,
                is_optional=True,
                display_order=9,
            ),
            (),
        )
        return tuple(
            [
                by_key[item.draft.item_key]
                for item in items
                if item.draft.item_key in by_key
            ]
            + [added]
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


def _view_item(contract, item_key: str):  # type: ignore[no-untyped-def]
    return next(item for item in contract.items if item.item_key == item_key)


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


def test_reprocessing_preserves_blocks_cited_only_by_contract_evidence(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    source_text = "A Contract-only retained source anchor."
    contract_only_block = Block(
        id="contract-only-block",
        document_id=document.id,
        source_content_hash=document.content_hash,
        order_index=99,
        page_number=2,
        block_type="paragraph",
        source_text=source_text,
        translated_text=f"繁中：{source_text}",
    )
    session.add_all(
        [
            contract_only_block,
            ImplementationContractEvidence(
                id="contract-only-evidence",
                item_id=contract.items[0].id,
                block_id=contract_only_block.id,
                research_node_id=None,
                locator_type="text_span",
                quote_text=source_text,
                quote_start=0,
                quote_end=len(source_text),
                source_quote_hash=exact_quote_hash(
                    contract_only_block.id,
                    0,
                    len(source_text),
                    source_text,
                ),
                relation="supports",
                source_label="Contract-only anchor",
            ),
        ]
    )
    session.commit()
    contract_only_block_id = contract_only_block.id

    clear_document_outputs(session, document.id)
    session.commit()

    assert session.get(Block, contract_only_block_id) is not None
    assert (
        session.get(ImplementationContractEvidence, "contract-only-evidence")
        is not None
    )


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
    # Ten bounded queries include one whole-document lineage read; none scale
    # with the number of contract items or evidence anchors.
    assert len(statements) <= 10
    assert len(contract_evidence_selects) == 1


def test_confirmed_resolution_is_append_only_and_keeps_the_draft_value(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    item = _view_item(contract, "required_dataset.1")
    session.commit()

    resolution = append_contract_resolution(
        session,
        item.id,
        status="confirmed",
        based_on_item_signature=item.item_signature,
        value=None,
        reason=None,
        request_id="confirm-dataset",
    )
    session.commit()
    loaded_item = _view_item(
        load_implementation_contract(session, contract.id), item.item_key
    )

    assert resolution.revision_number == 1
    assert resolution.status == "confirmed"
    assert loaded_item.resolution == resolution
    assert loaded_item.effective_value == loaded_item.draft_value
    assert loaded_item.effective_origin == loaded_item.origin
    assert "review_required" not in {issue.code for issue in loaded_item.issues}
    model = session.get(ImplementationContractItem, item.id)
    assert model is not None
    assert model.draft_value_json == encode_contract_value(item.draft_value)
    assert model.origin == item.origin


@pytest.mark.parametrize("status", ["corrected", "decided"])
def test_corrected_and_decided_require_typed_values_and_reasons(
    contract_database_factory,
    status: str,
) -> None:
    source_file = (
        "cross_market_long_short.txt"
        if status == "decided"
        else "monthly_accounting_signal.txt"
    )
    session, document, _map_version = contract_database_factory(source_file)
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    item_key = "transaction_cost.1" if status == "decided" else "weighting_rule.1"
    item = _view_item(contract, item_key)
    replacement = ScalarValue(kind="scalar", value="explicit_human_choice")

    with pytest.raises(ValueError, match="value and reason"):
        append_contract_resolution(
            session,
            item.id,
            status=status,
            based_on_item_signature=item.item_signature,
            value=None,
            reason=None,
            request_id=f"invalid-{status}",
        )

    saved = append_contract_resolution(
        session,
        item.id,
        status=status,
        based_on_item_signature=item.item_signature,
        value=replacement,
        reason="A documented replication choice.",
        request_id=f"valid-{status}",
    )
    loaded_item = _view_item(
        load_implementation_contract(session, contract.id), item.item_key
    )

    assert saved.resolved_value == replacement
    assert loaded_item.effective_value == replacement
    assert loaded_item.effective_origin == "human_decision"


def test_not_applicable_is_limited_to_optional_items(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory(
        "cross_market_long_short.txt"
    )
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    weighting = _view_item(contract, "weighting_rule.1")
    cost = _view_item(contract, "transaction_cost.1")

    with pytest.raises(ImplementationContractConflictError, match="not applicable"):
        append_contract_resolution(
            session,
            weighting.id,
            status="not_applicable",
            based_on_item_signature=weighting.item_signature,
            value=None,
            reason="Attempt to skip a mandatory field.",
            request_id="skip-weighting",
        )
    with pytest.raises(ImplementationContractConflictError, match="not applicable"):
        append_contract_resolution(
            session,
            cost.id,
            status="not_applicable",
            based_on_item_signature=cost.item_signature,
            value=None,
            reason="Anything at all.",
            request_id="arbitrary-cost-skip",
        )


def test_questioned_resolution_refreshes_readiness_with_item_severity(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory(
        "daily_price_signal.txt"
    )
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    blocking = _view_item(contract, "weighting_rule.1")
    optional = _view_item(contract, "turnover_assumption.1")

    append_contract_resolution(
        session,
        optional.id,
        status="questioned",
        based_on_item_signature=optional.item_signature,
        value=None,
        reason="Turnover timing needs review.",
        request_id="question-turnover",
    )
    optional_loaded = _view_item(
        load_implementation_contract(session, contract.id), optional.item_key
    )
    assert (
        next(
            issue
            for issue in optional_loaded.issues
            if issue.code == "blocking_item_questioned"
        ).severity
        == "warning"
    )

    append_contract_resolution(
        session,
        blocking.id,
        status="questioned",
        based_on_item_signature=blocking.item_signature,
        value=None,
        reason="Weighting statement needs review.",
        request_id="question-weighting",
    )
    loaded = load_implementation_contract(session, contract.id)
    blocking_loaded = _view_item(loaded, blocking.item_key)
    assert loaded.readiness == "blocked"
    assert (
        next(
            issue
            for issue in blocking_loaded.issues
            if issue.code == "blocking_item_questioned"
        ).severity
        == "error"
    )


def test_resolution_rejects_obsolete_signatures_and_reused_request_payloads(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    item = _view_item(contract, "required_dataset.1")

    with pytest.raises(ImplementationContractConflictError, match="obsolete"):
        append_contract_resolution(
            session,
            item.id,
            status="confirmed",
            based_on_item_signature="0" * 64,
            value=None,
            reason=None,
            request_id="obsolete",
        )

    first = append_contract_resolution(
        session,
        item.id,
        status="confirmed",
        based_on_item_signature=item.item_signature,
        value=None,
        reason=None,
        request_id="idempotent-request",
    )
    repeated = append_contract_resolution(
        session,
        item.id,
        status="confirmed",
        based_on_item_signature=item.item_signature,
        value=None,
        reason=None,
        request_id="idempotent-request",
    )
    assert repeated == first
    assert (
        session.scalar(
            select(func.count()).select_from(ImplementationContractResolution)
        )
        == 1
    )

    with pytest.raises(ImplementationContractConflictError, match="request ID"):
        append_contract_resolution(
            session,
            item.id,
            status="questioned",
            based_on_item_signature=item.item_signature,
            value=None,
            reason="Different payload.",
            request_id="idempotent-request",
        )


def test_resolution_revisions_and_supersedes_links_are_monotonic(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    item = _view_item(contract, "required_dataset.1")

    first = append_contract_resolution(
        session,
        item.id,
        status="confirmed",
        based_on_item_signature=item.item_signature,
        value=None,
        reason=None,
        request_id="revision-1",
    )
    second = append_contract_resolution(
        session,
        item.id,
        status="questioned",
        based_on_item_signature=item.item_signature,
        value=None,
        reason="Reopened after data vendor review.",
        request_id="revision-2",
    )

    assert (first.revision_number, second.revision_number) == (1, 2)
    assert first.supersedes_resolution_id is None
    assert second.supersedes_resolution_id == first.id
    history = _view_item(
        load_implementation_contract(session, contract.id), item.item_key
    ).resolution_history
    assert [resolution.id for resolution in history] == [first.id, second.id]


def test_resolution_revision_race_returns_reload_conflict(
    contract_database_factory,
    monkeypatch,
) -> None:
    session, document, _map_version = contract_database_factory()
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    item = _view_item(contract, "required_dataset.1")
    original_flush = session.flush

    def fail_with_revision_race(*args, **kwargs):  # type: ignore[no-untyped-def]
        if any(
            isinstance(value, ImplementationContractResolution) for value in session.new
        ):
            raise IntegrityError(
                "INSERT resolution", {}, Exception("duplicate revision")
            )
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(session, "flush", fail_with_revision_race)

    with pytest.raises(
        ImplementationContractConflictError, match="changed concurrently"
    ):
        append_contract_resolution(
            session,
            item.id,
            status="confirmed",
            based_on_item_signature=item.item_signature,
            value=None,
            reason=None,
            request_id="concurrent-request",
        )


def test_resolution_and_readiness_refresh_are_one_atomic_savepoint(
    contract_database_factory,
    monkeypatch,
) -> None:
    session, document, _map_version = contract_database_factory()
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    item = _view_item(contract, "required_dataset.1")
    session.commit()

    def fail_refresh(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("injected audit refresh failure")

    monkeypatch.setattr(
        "glyph.implementation_contracts._refresh_affected_contract_audits",
        fail_refresh,
    )

    with pytest.raises(RuntimeError, match="injected audit refresh failure"):
        append_contract_resolution(
            session,
            item.id,
            status="confirmed",
            based_on_item_signature=item.item_signature,
            value=None,
            reason=None,
            request_id="atomic-resolution",
        )
    session.commit()

    assert (
        session.scalar(
            select(func.count()).select_from(ImplementationContractResolution)
        )
        == 0
    )
    loaded = load_implementation_contract(session, contract.id)
    assert loaded.readiness == "review_needed"
    assert _view_item(loaded, item.item_key).resolution is None


def test_readiness_and_issues_refresh_after_every_resolution(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)

    for index, item in enumerate(contract.items):
        append_contract_resolution(
            session,
            item.id,
            status="confirmed",
            based_on_item_signature=item.item_signature,
            value=None,
            reason=None,
            request_id=f"confirm-{index}",
        )
    ready = load_implementation_contract(session, contract.id)

    assert ready.readiness == "implementation_ready"
    assert ready.issues == ()
    model = session.get(ImplementationContractVersion, contract.id)
    assert model is not None and model.readiness == "implementation_ready"


def test_resolution_carries_only_to_an_identical_item_signature(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    first = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    first_item = _view_item(first, "required_dataset.1")
    resolution = append_contract_resolution(
        session,
        first_item.id,
        status="confirmed",
        based_on_item_signature=first_item.item_signature,
        value=None,
        reason=None,
        request_id="carry-exact",
    )
    session.commit()

    identical = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    identical_item = _view_item(identical, first_item.item_key)
    changed = ImplementationContractService(session, ChangedValueProvider()).generate(
        document.id
    )
    changed_item = _view_item(changed, first_item.item_key)

    assert identical_item.item_signature == first_item.item_signature
    assert identical_item.resolution is not None
    assert identical_item.resolution.id == resolution.id
    assert [item.id for item in identical_item.resolution_history] == [resolution.id]
    assert changed_item.item_signature != first_item.item_signature
    assert changed_item.resolution is None
    assert (
        session.scalar(
            select(func.count()).select_from(ImplementationContractResolution)
        )
        == 1
    )


def test_new_resolution_continues_carried_revision_and_supersession_chain(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    first = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    first_item = _view_item(first, "required_dataset.1")
    carried = append_contract_resolution(
        session,
        first_item.id,
        status="confirmed",
        based_on_item_signature=first_item.item_signature,
        value=None,
        reason=None,
        request_id="carry-revision-1",
    )
    session.commit()

    second = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    second_item = _view_item(second, first_item.item_key)
    revised = append_contract_resolution(
        session,
        second_item.id,
        status="questioned",
        based_on_item_signature=second_item.item_signature,
        value=None,
        reason="Reopened on the regenerated Contract.",
        request_id="carry-revision-2",
    )
    loaded = _view_item(
        load_implementation_contract(session, second.id), first_item.item_key
    )

    assert revised.revision_number == 2
    assert revised.supersedes_resolution_id == carried.id
    assert [value.id for value in loaded.resolution_history] == [carried.id, revised.id]
    assert loaded.resolution is not None and loaded.resolution.id == revised.id


def test_resolution_never_applies_to_a_different_item_with_same_signature(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory(
        "cross_market_long_short.txt"
    )
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    weighting = _view_item(contract, "weighting_rule.1")
    session.add(
        ImplementationContractItem(
            id="second-weighting-item",
            contract_version_id=contract.id,
            item_key="weighting_rule.2",
            section=weighting.section,
            item_type=weighting.item_type,
            draft_value_json=None,
            origin=weighting.origin,
            rationale=weighting.rationale,
            is_blocking=weighting.is_blocking,
            is_optional=weighting.is_optional,
            display_order=weighting.display_order + 1,
            item_signature=weighting.item_signature,
        )
    )
    session.commit()

    resolution = append_contract_resolution(
        session,
        weighting.id,
        status="decided",
        based_on_item_signature=weighting.item_signature,
        value=ScalarValue(kind="scalar", value="equal_weight"),
        reason="Desk decision for the first weighting rule only.",
        request_id="first-weighting-only",
    )
    loaded = load_implementation_contract(session, contract.id)

    first = _view_item(loaded, weighting.item_key)
    second = _view_item(loaded, "weighting_rule.2")
    assert first.resolution is not None and first.resolution.id == resolution.id
    assert second.resolution is None
    assert second.resolution_history == ()


def test_identical_regeneration_persists_readiness_from_carried_resolutions(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    first = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    for index, item in enumerate(first.items):
        append_contract_resolution(
            session,
            item.id,
            status="confirmed",
            based_on_item_signature=item.item_signature,
            value=None,
            reason=None,
            request_id=f"ready-{index}",
        )
    assert load_implementation_contract(session, first.id).readiness == (
        "implementation_ready"
    )
    session.commit()

    identical = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    model = session.get(ImplementationContractVersion, identical.id)

    assert identical.readiness == "implementation_ready"
    assert identical.issues == ()
    assert model is not None and model.readiness == "implementation_ready"
    assert session.scalar(
        select(func.count()).select_from(ImplementationContractResolution)
    ) == len(first.items)


def test_newer_resolution_never_applies_retroactively_to_ancestor(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    service = ImplementationContractService(
        session, MockImplementationContractProvider()
    )
    first = service.generate(document.id)
    session.commit()
    second = service.generate(document.id)
    second_item = _view_item(second, "required_dataset.1")

    saved = append_contract_resolution(
        session,
        second_item.id,
        status="confirmed",
        based_on_item_signature=second_item.item_signature,
        value=None,
        reason=None,
        request_id="newer-only",
    )

    assert (
        _view_item(
            load_implementation_contract(session, second.id), second_item.item_key
        ).resolution
        == saved
    )
    assert (
        _view_item(
            load_implementation_contract(session, first.id), second_item.item_key
        ).resolution
        is None
    )


def test_late_ancestor_resolutions_refresh_identical_descendant_readiness(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    service = ImplementationContractService(
        session, MockImplementationContractProvider()
    )
    first = service.generate(document.id)
    session.commit()
    second = service.generate(document.id)
    assert second.readiness == "review_needed"

    for index, item in enumerate(first.items):
        append_contract_resolution(
            session,
            item.id,
            status="confirmed",
            based_on_item_signature=item.item_signature,
            value=None,
            reason=None,
            request_id=f"late-ancestor-{index}",
        )

    descendant = load_implementation_contract(session, second.id)
    descendant_model = session.get(ImplementationContractVersion, second.id)
    assert descendant.readiness == "implementation_ready"
    assert descendant.issues == ()
    assert descendant_model is not None
    assert descendant_model.readiness == "implementation_ready"


def test_diff_classifies_all_change_types_in_stable_contract_order(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    baseline = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)
    session.commit()
    changed = ImplementationContractService(
        session, DiffClassificationProvider()
    ).generate(document.id)

    diff = diff_implementation_contracts(session, changed.id, baseline.id)
    classifications = {item.item_key: item.classification for item in diff.items}

    assert classifications["required_dataset.1"] == "unchanged"
    assert classifications["required_field.1"] == "value_changed"
    assert classifications["signal_direction.1"] == "origin_changed"
    assert classifications["data_frequency.1"] == "evidence_changed"
    assert classifications["statistical_test.1"] == "type_changed"
    assert classifications["sample_filter.1"] == "added"
    assert classifications["availability_lag.1"] == "removed"
    order = [
        (
            item.section_order,
            item.display_order,
            item.item_key,
        )
        for item in diff.items
    ]
    assert order == sorted(order)


def test_list_and_activate_historical_versions_preserve_stale_truth(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    service = ImplementationContractService(
        session, MockImplementationContractProvider()
    )
    first = service.generate(document.id)
    session.commit()
    second = service.generate(document.id)
    session.commit()

    versions = list_implementation_contract_versions(session, document.id)
    assert {version.id for version in versions} == {first.id, second.id}
    assert next(version for version in versions if version.id == second.id).is_active

    document.content_hash = "f" * 64
    document.status = "stale"
    session.commit()
    activated = activate_implementation_contract(session, first.id)

    assert activated.id == first.id
    assert activated.is_active is True
    assert activated.is_current is False
    assert activated.is_stale is True
    assert load_implementation_contract(session, second.id).is_active is False

    first_model = session.get(ImplementationContractVersion, first.id)
    assert first_model is not None
    first_model.status = "building"
    session.commit()
    with pytest.raises(
        ImplementationContractConflictError, match="complete or partial"
    ):
        activate_implementation_contract(session, first.id)


def test_version_history_is_bounded_and_uses_constant_query_count(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    service = ImplementationContractService(
        session, MockImplementationContractProvider()
    )
    for _ in range(4):
        service.generate(document.id)
        session.commit()
    query_count = 0

    def count_query(*_args):  # type: ignore[no-untyped-def]
        nonlocal query_count
        query_count += 1

    event.listen(session.bind, "before_cursor_execute", count_query)
    try:
        versions = list_implementation_contract_versions(session, document.id, limit=2)
    finally:
        event.remove(session.bind, "before_cursor_execute", count_query)

    assert len(versions) == 2
    assert query_count <= 5
    with pytest.raises(ValueError, match="between 1 and 100"):
        list_implementation_contract_versions(session, document.id, limit=101)


def test_version_listing_and_diff_validate_document_ownership_and_existence(
    contract_database_factory,
) -> None:
    session, document, _map_version = contract_database_factory()
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id)

    with pytest.raises(ImplementationContractNotFoundError, match="Document"):
        list_implementation_contract_versions(session, "missing-document")
    with pytest.raises(ImplementationContractNotFoundError, match="Contract"):
        diff_implementation_contracts(session, contract.id, "missing-contract")
