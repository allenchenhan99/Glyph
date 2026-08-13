from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from glyph.config import Settings
from glyph.contract_ai import (
    ContractInputBlock,
    MockImplementationContractProvider,
    SynthesizedContractItem,
    create_implementation_contract_provider,
    validate_extracted_requirements,
    validate_synthesized_contract,
)
from glyph.contract_domain import (
    ContractItemDraft,
    InvalidContractValueError,
    ScalarValue,
)
from glyph.contract_evidence import ContractEvidenceContext
from glyph.models import Base, Block, Document, ResearchMapVersion

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "contracts"


@pytest.mark.parametrize(
    ("ai_mode", "expected_name"),
    [
        ("mock", "mock"),
        ("claude_cli", "claude_cli"),
        ("codex_cli", "codex_cli"),
    ],
)
def test_implementation_contract_provider_selection(ai_mode, expected_name, tmp_path):
    settings = Settings(
        book_dir=tmp_path / "book",
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{tmp_path / 'glyph.sqlite3'}",
        ocr_mode="mock",
        ai_mode=ai_mode,
        unlimited_ocr_repo=None,
        unlimited_ocr_command=None,
    )

    provider = create_implementation_contract_provider(settings)

    assert provider.provider_name == expected_name


def test_unknown_implementation_contract_provider_mode_fails_fast(tmp_path):
    settings = Settings(
        book_dir=tmp_path / "book",
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{tmp_path / 'glyph.sqlite3'}",
        ocr_mode="mock",
        ai_mode="remote_magic",
        unlimited_ocr_repo=None,
        unlimited_ocr_command=None,
    )

    with pytest.raises(RuntimeError, match="Unknown Implementation Contract AI mode"):
        create_implementation_contract_provider(settings)


@pytest.fixture
def contract_input_database() -> Iterator[tuple[Session, ContractEvidenceContext]]:
    source_text = (FIXTURE_DIRECTORY / "monthly_accounting_signal.txt").read_text()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    document = Document(
        id="paper",
        title="Monthly accounting signal",
        source_path="/books/monthly-accounting.txt",
        content_hash="a" * 64,
        processed_content_hash="a" * 64,
        file_type="txt",
        status="completed",
    )
    map_version = ResearchMapVersion(
        id="map",
        document_id=document.id,
        previous_version_id=None,
        source_content_hash="a" * 64,
        schema_version="1",
        provider="mock",
        model_name=None,
        status="complete",
        is_active=True,
    )
    block = Block(
        id="source",
        document_id=document.id,
        source_content_hash="a" * 64,
        order_index=0,
        page_number=1,
        block_type="text",
        source_text=source_text,
        translated_text=source_text,
    )
    session.add_all([document, map_version, block])
    session.commit()
    try:
        yield (
            session,
            ContractEvidenceContext(
                document_id=document.id,
                source_content_hash="a" * 64,
                research_map_version_id=map_version.id,
            ),
        )
    finally:
        session.close()


def test_mock_provider_uses_two_evidence_first_phases(contract_input_database) -> None:
    session, context = contract_input_database
    block = session.get(Block, "source")
    assert block is not None
    provider = MockImplementationContractProvider()
    inputs = (ContractInputBlock.from_model(block),)

    candidates = provider.extract_requirements(inputs)
    accepted = validate_extracted_requirements(session, context, candidates)
    synthesized = provider.synthesize_contract(accepted)
    effective = validate_synthesized_contract(synthesized, accepted)

    accepted_ids = {item.evidence_id for item in accepted}
    assert candidates
    assert all(candidate.anchor.quote_text for candidate in candidates)
    assert all(item.anchor.source_quote_hash for item in accepted)
    assert all(set(item.evidence_ids) <= accepted_ids for item in synthesized)
    assert all(item.evidence for item in effective)
    assert [item.draft.item_key for item in effective] == [
        "required_dataset.1",
        "required_field.1",
        "data_frequency.1",
        "availability_lag.1",
        "universe_filter.1",
        "signal_formula.1",
        "signal_direction.1",
        "formation_date.1",
        "weighting_rule.1",
        "rebalance_frequency.1",
        "holding_period.1",
        "benchmark_model.1",
        "evaluation_metric.1",
        "statistical_test.1",
        "transaction_cost.1",
        "survivorship_risk.1",
    ]


def test_synthesis_rejects_unvalidated_reader_blocks() -> None:
    provider = MockImplementationContractProvider()

    with pytest.raises(TypeError, match="validated contract evidence"):
        provider.synthesize_contract(
            (ContractInputBlock("source", "text", "Unvalidated paper text"),)
        )


def test_synthesis_cannot_create_claims_from_unrelated_accepted_evidence(
    contract_input_database,
) -> None:
    session, context = contract_input_database
    block = session.get(Block, "source")
    assert block is not None
    provider = MockImplementationContractProvider()
    accepted = validate_extracted_requirements(
        session,
        context,
        provider.extract_requirements((ContractInputBlock.from_model(block),)),
    )
    data_only = tuple(
        item for item in accepted if item.anchor.quote_text.startswith("Data:")
    )

    synthesized = provider.synthesize_contract(data_only)

    assert {item.draft.item_key for item in synthesized} == {
        "required_dataset.1",
        "data_frequency.1",
    }


def test_validation_rejects_unknown_evidence_references(
    contract_input_database,
) -> None:
    session, context = contract_input_database
    block = session.get(Block, "source")
    assert block is not None
    provider = MockImplementationContractProvider()
    accepted = validate_extracted_requirements(
        session,
        context,
        provider.extract_requirements((ContractInputBlock.from_model(block),)),
    )
    draft = ContractItemDraft(
        item_key="evaluation_metric.1",
        section="evaluation",
        item_type="evaluation_metric",
        value=ScalarValue(kind="scalar", value="raw_return"),
        origin="author_explicit",
        rationale=None,
        is_blocking=True,
        is_optional=False,
        display_order=0,
    )

    with pytest.raises(ValueError, match="Unaccepted evidence ID"):
        validate_synthesized_contract(
            (SynthesizedContractItem(draft, ("provider-invented-id",)),), accepted
        )


def test_validation_rejects_evidence_extracted_for_another_item_type(
    contract_input_database,
) -> None:
    session, context = contract_input_database
    block = session.get(Block, "source")
    assert block is not None
    provider = MockImplementationContractProvider()
    accepted = validate_extracted_requirements(
        session,
        context,
        provider.extract_requirements((ContractInputBlock.from_model(block),)),
    )
    data_evidence = next(
        item for item in accepted if item.anchor.quote_text.startswith("Data:")
    )
    draft = ContractItemDraft(
        item_key="evaluation_metric.1",
        section="evaluation",
        item_type="evaluation_metric",
        value=ScalarValue(kind="scalar", value="raw_return"),
        origin="author_explicit",
        rationale=None,
        is_blocking=True,
        is_optional=False,
        display_order=0,
    )

    with pytest.raises(ValueError, match="not extracted for evaluation_metric"):
        validate_synthesized_contract(
            (SynthesizedContractItem(draft, (data_evidence.evidence_id,)),),
            accepted,
        )


def test_validation_rejects_duplicate_item_keys(contract_input_database) -> None:
    session, context = contract_input_database
    block = session.get(Block, "source")
    assert block is not None
    provider = MockImplementationContractProvider()
    accepted = validate_extracted_requirements(
        session,
        context,
        provider.extract_requirements((ContractInputBlock.from_model(block),)),
    )
    first_item = provider.synthesize_contract(accepted)[0]

    with pytest.raises(ValueError, match="Duplicate contract item key"):
        validate_synthesized_contract((first_item, first_item), accepted)


@pytest.mark.parametrize(
    ("item_type", "origin", "message"),
    [
        ("chat_summary", "author_explicit", "contract item type"),
        ("evaluation_metric", "human_decision", "provider draft"),
    ],
)
def test_provider_drafts_reject_unknown_types_and_human_decisions(
    item_type: str,
    origin: str,
    message: str,
) -> None:
    with pytest.raises(InvalidContractValueError, match=message):
        ContractItemDraft(
            item_key="item.1",
            section="evaluation",
            item_type=item_type,  # type: ignore[arg-type]
            value=ScalarValue(kind="scalar", value="claim"),
            origin=origin,  # type: ignore[arg-type]
            rationale=None,
            is_blocking=True,
            is_optional=False,
            display_order=0,
        )


def test_mock_marks_absent_weighting_and_costs_without_inventing_defaults() -> None:
    source_text = (FIXTURE_DIRECTORY / "cross_market_long_short.txt").read_text()
    provider = MockImplementationContractProvider()
    candidates = provider.extract_requirements(
        (ContractInputBlock("source", "text", source_text),)
    )

    # The mock synthesis boundary deliberately requires platform-validated anchors.
    # Candidate values remain evidence only and cannot carry silent defaults.
    candidate_text = "\n".join(candidate.anchor.quote_text for candidate in candidates)
    assert "does not specify" in candidate_text
    assert "not reported" in candidate_text
    assert "equal_weight" not in candidate_text
    assert "zero_cost" not in candidate_text
