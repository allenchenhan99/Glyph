from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from glyph.config import Settings
from glyph.models import Base, Block, Document
from glyph.research_ai import (
    CORE_NODE_GROUPS,
    ExtractedEvidenceCandidate,
    MockResearchMapProvider,
    NodeDraft,
    ResearchBlock,
    create_research_map_provider,
    validate_extracted_candidates,
)
from glyph.research_domain import InvalidDomainValueError

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "empirical_asset_pricing.txt"


def build_fixture_session() -> tuple[Session, Document, list[Block]]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    document = Document(
        id="paper-1",
        title="Signal Persistence and Expected Returns",
        source_path="/books/synthetic-paper.txt",
        content_hash="a" * 64,
        processed_content_hash="a" * 64,
        file_type="txt",
        status="completed",
    )
    paragraphs = [
        line.strip()
        for line in FIXTURE_PATH.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    blocks = [
        Block(
            id=f"block-{index}",
            document_id=document.id,
            source_content_hash=document.processed_content_hash,
            order_index=index,
            page_number=1 + index // 4,
            block_type="paragraph",
            source_text=paragraph,
            translated_text=f"繁中：{paragraph}",
        )
        for index, paragraph in enumerate(paragraphs)
    ]
    session.add_all([document, *blocks])
    session.commit()
    persisted_blocks = session.scalars(select(Block).order_by(Block.order_index)).all()
    return session, document, list(persisted_blocks)


def test_mock_provider_uses_separate_evidence_first_phases():
    session, document, blocks = build_fixture_session()
    provider = MockResearchMapProvider()
    try:
        research_blocks = tuple(ResearchBlock.from_model(block) for block in blocks)
        candidates = provider.extract_candidates(research_blocks)
        accepted = validate_extracted_candidates(session, document, candidates)
        draft = provider.synthesize_nodes(accepted)
    finally:
        session.close()

    accepted_ids = {item.evidence_id for item in accepted}
    assert candidates
    assert all(item.anchor.quote_text for item in candidates)
    assert all(item.anchor.source_quote_hash for item in accepted)
    assert all(set(node.evidence_ids) <= accepted_ids for node in draft)
    assert all(node.node_key for node in draft)


def test_mock_provider_is_deterministic_and_covers_the_core_research_map():
    session, document, blocks = build_fixture_session()
    provider = MockResearchMapProvider()
    research_blocks = tuple(ResearchBlock.from_model(block) for block in blocks)
    try:
        first_candidates = provider.extract_candidates(research_blocks)
        first_accepted = validate_extracted_candidates(
            session, document, first_candidates
        )
        first_draft = provider.synthesize_nodes(first_accepted)
        second_draft = provider.synthesize_nodes(
            validate_extracted_candidates(
                session,
                document,
                provider.extract_candidates(research_blocks),
            )
        )
    finally:
        session.close()

    represented_types = {node.node_type for node in first_draft}
    assert first_draft == second_draft
    assert all(
        represented_types.intersection(allowed_types)
        for allowed_types in CORE_NODE_GROUPS.values()
    )
    assert [node.node_key for node in first_draft] == [
        "author_claim.1",
        "data_source.1",
        "data_and_sample.1",
        "signal_definition.1",
        "portfolio_construction.1",
        "rebalancing_rule.1",
        "empirical_method.1",
        "benchmark_model.1",
        "primary_result.1",
        "statistical_evidence.1",
        "robustness_test.1",
        "transaction_cost.1",
        "limitations.1",
    ]


def test_mock_provider_marks_unreported_costs_instead_of_inventing_a_value():
    session, document, blocks = build_fixture_session()
    provider = MockResearchMapProvider()
    try:
        accepted = validate_extracted_candidates(
            session,
            document,
            provider.extract_candidates(
                tuple(ResearchBlock.from_model(block) for block in blocks)
            ),
        )
        cost_node = next(
            node
            for node in provider.synthesize_nodes(accepted)
            if node.node_type == "transaction_cost"
        )
    finally:
        session.close()

    assert cost_node.evidence_quality == "not_reported"
    assert "does not report" in cost_node.claim_text
    assert "0" not in cost_node.claim_text


def test_synthesis_rejects_unvalidated_reader_blocks():
    provider = MockResearchMapProvider()

    with pytest.raises(TypeError, match="validated evidence"):
        provider.synthesize_nodes(
            (ResearchBlock("block-1", "paragraph", "Unvalidated paper text"),)
        )


def test_provider_candidates_reject_unknown_ontology_types():
    with pytest.raises(InvalidDomainValueError, match="chat_summary"):
        ExtractedEvidenceCandidate(
            evidence_id="evidence-1",
            node_type="chat_summary",
            block_id="block-1",
            quote_text="A source quote",
            quote_start=0,
            quote_end=14,
            relation="supports",
            locator_type="text_span",
        )


def test_node_drafts_reject_unknown_provenance_and_evidence_references_are_tuples():
    with pytest.raises(InvalidDomainValueError, match="model_guess"):
        NodeDraft(
            node_key="author_claim.1",
            node_type="author_claim",
            title="Research question",
            claim_text="A claim",
            explanation="",
            provenance="model_guess",
            evidence_quality="direct",
            evidence_ids=("evidence-1",),
            display_order=0,
        )


@pytest.mark.parametrize(
    ("ai_mode", "expected_name"),
    [
        ("mock", "mock"),
        ("claude_cli", "claude_cli"),
        ("codex_cli", "codex_cli"),
    ],
)
def test_research_map_provider_selection(ai_mode, expected_name, tmp_path):
    settings = Settings(
        book_dir=tmp_path / "book",
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{tmp_path / 'glyph.sqlite3'}",
        ocr_mode="mock",
        ai_mode=ai_mode,
        unlimited_ocr_repo=None,
        unlimited_ocr_command=None,
    )

    provider = create_research_map_provider(settings)

    assert provider.name == expected_name


def test_unknown_research_map_provider_mode_fails_fast(tmp_path):
    settings = Settings(
        book_dir=tmp_path / "book",
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{tmp_path / 'glyph.sqlite3'}",
        ocr_mode="mock",
        ai_mode="remote_magic",
        unlimited_ocr_repo=None,
        unlimited_ocr_command=None,
    )

    with pytest.raises(RuntimeError, match="Unknown Research Map AI mode"):
        create_research_map_provider(settings)
