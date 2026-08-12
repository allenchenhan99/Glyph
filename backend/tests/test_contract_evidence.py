from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from glyph.models import Base, Block, Document, ResearchMapVersion, ResearchNode
from glyph.research_evidence import EvidenceCandidate, validate_candidate


def evidence_module():
    from glyph import contract_evidence

    return contract_evidence


@pytest.fixture
def contract_evidence_database() -> Iterator[tuple[Session, object]]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    first_document = Document(
        id="document-1",
        title="Asset pricing paper",
        source_path="/books/asset-pricing.pdf",
        content_hash="a" * 64,
        processed_content_hash="a" * 64,
        file_type="pdf",
        status="completed",
    )
    second_document = Document(
        id="document-2",
        title="Another paper",
        source_path="/books/another.pdf",
        content_hash="b" * 64,
        processed_content_hash="b" * 64,
        file_type="pdf",
        status="completed",
    )
    first_map = ResearchMapVersion(
        id="map-1",
        document_id=first_document.id,
        previous_version_id=None,
        source_content_hash="a" * 64,
        schema_version="1",
        provider="mock",
        model_name=None,
        status="complete",
        is_active=True,
    )
    other_map = ResearchMapVersion(
        id="map-other",
        document_id=first_document.id,
        previous_version_id="map-1",
        source_content_hash="a" * 64,
        schema_version="1",
        provider="mock",
        model_name=None,
        status="complete",
        is_active=False,
    )
    foreign_map = ResearchMapVersion(
        id="map-foreign",
        document_id=second_document.id,
        previous_version_id=None,
        source_content_hash="b" * 64,
        schema_version="1",
        provider="mock",
        model_name=None,
        status="complete",
        is_active=True,
    )
    session.add_all(
        [
            first_document,
            second_document,
            first_map,
            other_map,
            foreign_map,
            Block(
                id="block-1",
                document_id=first_document.id,
                source_content_hash="a" * 64,
                order_index=0,
                page_number=3,
                block_type="paragraph",
                source_text=(
                    "The long-short portfolio earns 0.8% per month with a "
                    "t-statistic of 3.1."
                ),
                translated_text="多空投資組合每月報酬為 0.8%，t 統計量為 3.1。",
            ),
            Block(
                id="block-repeated",
                document_id=first_document.id,
                source_content_hash="a" * 64,
                order_index=1,
                page_number=4,
                block_type="paragraph",
                source_text="Risk matters. Risk is priced. Risk matters.",
                translated_text="風險很重要。",
            ),
            Block(
                id="block-foreign",
                document_id=second_document.id,
                source_content_hash="b" * 64,
                order_index=0,
                page_number=1,
                block_type="paragraph",
                source_text="Foreign evidence belongs to another paper.",
                translated_text="另一篇論文的證據。",
            ),
            ResearchNode(
                id="node-1",
                map_version_id=first_map.id,
                parent_node_id=None,
                node_key="primary_result.1",
                node_type="primary_result",
                title="Primary result",
                claim_text="The portfolio earns 0.8% per month.",
                explanation="Reported result.",
                provenance="author_explicit",
                evidence_quality="direct",
                display_order=0,
                node_signature="c" * 64,
            ),
            ResearchNode(
                id="node-other-map",
                map_version_id=other_map.id,
                parent_node_id=None,
                node_key="primary_result.1",
                node_type="primary_result",
                title="Other map result",
                claim_text="A changed result.",
                explanation="Other version.",
                provenance="author_explicit",
                evidence_quality="direct",
                display_order=0,
                node_signature="d" * 64,
            ),
            ResearchNode(
                id="node-foreign",
                map_version_id=foreign_map.id,
                parent_node_id=None,
                node_key="primary_result.1",
                node_type="primary_result",
                title="Foreign result",
                claim_text="Another paper's result.",
                explanation="Foreign version.",
                provenance="author_explicit",
                evidence_quality="direct",
                display_order=0,
                node_signature="e" * 64,
            ),
        ]
    )
    session.commit()
    module = evidence_module()
    context = module.ContractEvidenceContext(
        document_id=first_document.id,
        source_content_hash="a" * 64,
        research_map_version_id=first_map.id,
    )
    try:
        yield session, context
    finally:
        session.close()
        engine.dispose()


def candidate(**overrides):
    module = evidence_module()
    values = {
        "block_id": "block-1",
        "research_node_id": "node-1",
        "quote_text": "0.8% per month",
        "quote_start": 31,
        "quote_end": 45,
        "relation": "supports",
        "locator_type": "text_span",
        "source_label": "Main result",
    }
    values.update(overrides)
    return module.ContractEvidenceCandidate(**values)


def test_contract_anchor_accepts_exact_current_reader_evidence(
    contract_evidence_database,
):
    session, context = contract_evidence_database
    module = evidence_module()

    accepted = module.validate_contract_candidate(session, context, candidate())

    assert accepted.block_id == "block-1"
    assert accepted.research_node_id == "node-1"
    assert accepted.quote_text == "0.8% per month"
    assert (accepted.quote_start, accepted.quote_end) == (31, 45)
    assert accepted.relation == "supports"
    assert accepted.locator_type == "text_span"
    assert len(accepted.source_quote_hash) == 64


def test_contract_and_research_map_use_the_same_exact_quote_hash(
    contract_evidence_database,
):
    session, context = contract_evidence_database
    module = evidence_module()
    document = session.get(Document, context.document_id)
    assert document is not None

    contract_anchor = module.validate_contract_candidate(session, context, candidate())
    research_anchor = validate_candidate(
        session,
        document,
        EvidenceCandidate(
            block_id="block-1",
            quote_text="0.8% per month",
            quote_start=31,
            quote_end=45,
            relation="supports",
            locator_type="text_span",
            source_label="Main result",
        ),
    )

    assert contract_anchor.source_quote_hash == research_anchor.source_quote_hash


def test_contract_anchor_derives_offsets_only_for_a_unique_quote(
    contract_evidence_database,
):
    session, context = contract_evidence_database
    module = evidence_module()

    accepted = module.validate_contract_candidate(
        session,
        context,
        candidate(quote_start=None, quote_end=None),
    )
    assert (accepted.quote_start, accepted.quote_end) == (31, 45)

    with pytest.raises(module.InvalidContractEvidenceError, match="more than once"):
        module.validate_contract_candidate(
            session,
            context,
            candidate(
                block_id="block-repeated",
                research_node_id=None,
                quote_text="Risk matters.",
                quote_start=None,
                quote_end=None,
            ),
        )


def test_contract_anchor_rejects_wrong_offsets(contract_evidence_database):
    session, context = contract_evidence_database
    module = evidence_module()

    with pytest.raises(module.InvalidContractEvidenceError, match="does not match"):
        module.validate_contract_candidate(
            session,
            context,
            candidate(quote_text="different quote", quote_start=0, quote_end=15),
        )


def test_contract_anchor_cannot_cross_document_boundaries(
    contract_evidence_database,
):
    session, context = contract_evidence_database
    module = evidence_module()

    with pytest.raises(module.InvalidContractEvidenceError, match="another document"):
        module.validate_contract_candidate(
            session,
            context,
            candidate(
                block_id="block-foreign",
                research_node_id=None,
                quote_text="Foreign evidence",
                quote_start=0,
                quote_end=16,
            ),
        )


@pytest.mark.parametrize("node_id", ["node-other-map", "node-foreign"])
def test_contract_anchor_cannot_link_a_node_from_another_map(
    contract_evidence_database,
    node_id,
):
    session, context = contract_evidence_database
    module = evidence_module()

    with pytest.raises(module.InvalidContractEvidenceError, match="same Research Map"):
        module.validate_contract_candidate(
            session,
            context,
            candidate(research_node_id=node_id),
        )


def test_contract_anchor_requires_current_source_hash(contract_evidence_database):
    session, context = contract_evidence_database
    module = evidence_module()
    document = session.get(Document, context.document_id)
    assert document is not None
    document.content_hash = "f" * 64
    session.commit()

    with pytest.raises(module.InvalidContractEvidenceError, match="current Reader"):
        module.validate_contract_candidate(session, context, candidate())


def test_contract_anchor_requires_context_map_to_match_document_and_source(
    contract_evidence_database,
):
    session, context = contract_evidence_database
    module = evidence_module()
    wrong_context = module.ContractEvidenceContext(
        document_id=context.document_id,
        source_content_hash=context.source_content_hash,
        research_map_version_id="map-foreign",
    )

    with pytest.raises(module.InvalidContractEvidenceError, match="document and source"):
        module.validate_contract_candidate(session, wrong_context, candidate())


def test_duplicate_contract_anchors_are_removed_by_persistence_identity(
    contract_evidence_database,
):
    session, context = contract_evidence_database
    module = evidence_module()

    accepted = module.validate_contract_candidates(
        session,
        context,
        (
            candidate(),
            candidate(locator_type="table"),
            candidate(relation="qualifies"),
        ),
    )

    assert len(accepted) == 2
    assert [(item.relation, item.locator_type) for item in accepted] == [
        ("supports", "text_span"),
        ("qualifies", "text_span"),
    ]


@pytest.mark.parametrize(
    "source_label",
    [
        "https://example.com/result",
        "/Users/researcher/private/paper.pdf",
        r"C:\private\paper.pdf",
        "<script>alert('x')</script>",
    ],
)
def test_contract_structured_fields_reject_urls_paths_and_html(source_label):
    module = evidence_module()

    with pytest.raises(module.InvalidContractEvidenceError, match="source_label"):
        candidate(source_label=source_label)


@pytest.mark.parametrize(
    ("field", "value"),
    [("relation", "mentions"), ("locator_type", "web_page")],
)
def test_contract_anchor_rejects_unknown_controlled_evidence_values(field, value):
    module = evidence_module()

    with pytest.raises(module.InvalidContractEvidenceError, match="Unknown"):
        candidate(**{field: value})
