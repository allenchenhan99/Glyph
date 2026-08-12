from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from glyph.models import Base, Block, Document
from glyph.research_domain import (
    EVIDENCE_QUALITIES,
    EVIDENCE_RELATIONS,
    LOCATOR_TYPES,
    NODE_TYPES,
    PROVENANCES,
    REVIEW_STATUSES,
    InvalidDomainValueError,
    validate_evidence_quality,
    validate_evidence_relation,
    validate_locator_type,
    validate_node_type,
    validate_provenance,
    validate_review_status,
)
from glyph.research_evidence import (
    EvidenceCandidate,
    InvalidEvidenceError,
    validate_candidate,
    validate_candidates,
)

EXPECTED_NODE_TYPES = {
    "author_claim",
    "economic_mechanism",
    "hypothesis",
    "data_and_sample",
    "data_source",
    "sample_filter",
    "signal_definition",
    "variable_definition",
    "portfolio_construction",
    "rebalancing_rule",
    "empirical_method",
    "benchmark_model",
    "identification_strategy",
    "primary_result",
    "statistical_evidence",
    "economic_magnitude",
    "turnover",
    "transaction_cost",
    "robustness_test",
    "subsample_result",
    "alternative_explanation",
    "implementation_constraint",
    "limitations",
    "unanswered_question",
}


@pytest.fixture
def evidence_database() -> Iterator[tuple[Session, Document, Document]]:
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
    session.add_all(
        [
            first_document,
            second_document,
            Block(
                id="block-1",
                document_id=first_document.id,
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
                order_index=1,
                page_number=4,
                block_type="paragraph",
                source_text="Risk matters. Risk is priced. Risk matters.",
                translated_text="風險很重要。",
            ),
            Block(
                id="block-foreign",
                document_id=second_document.id,
                order_index=0,
                page_number=1,
                block_type="paragraph",
                source_text="Foreign evidence belongs to another paper.",
                translated_text="另一篇論文的證據。",
            ),
        ]
    )
    session.commit()
    try:
        yield session, first_document, second_document
    finally:
        session.close()
        engine.dispose()


def candidate(**overrides) -> EvidenceCandidate:
    values = {
        "block_id": "block-1",
        "quote_text": "0.8% per month",
        "quote_start": 31,
        "quote_end": 45,
        "relation": "supports",
        "locator_type": "text_span",
        "source_label": "Main result",
    }
    values.update(overrides)
    return EvidenceCandidate(**values)


def test_schema_v1_has_only_the_approved_controlled_values():
    assert set(NODE_TYPES) == EXPECTED_NODE_TYPES
    assert set(PROVENANCES) == {"author_explicit", "ai_synthesis", "human_created"}
    assert set(EVIDENCE_QUALITIES) == {
        "direct",
        "synthesized",
        "insufficient",
        "conflicted",
        "not_reported",
    }
    assert set(EVIDENCE_RELATIONS) == {
        "supports",
        "qualifies",
        "contradicts",
        "context",
    }
    assert set(LOCATOR_TYPES) == {
        "text_span",
        "equation",
        "table",
        "figure",
        "caption",
    }
    assert set(REVIEW_STATUSES) == {"confirmed", "questioned", "corrected"}


@pytest.mark.parametrize(
    ("validator", "unknown"),
    [
        (validate_node_type, "chat_answer"),
        (validate_provenance, "model_guess"),
        (validate_evidence_quality, "probably_true"),
        (validate_evidence_relation, "mentions"),
        (validate_locator_type, "web_page"),
        (validate_review_status, "approved_by_ai"),
    ],
)
def test_unknown_controlled_values_are_rejected(validator, unknown):
    with pytest.raises(InvalidDomainValueError, match=unknown):
        validator(unknown)


def test_anchor_must_quote_the_target_block_exactly(evidence_database):
    session, document, _ = evidence_database

    with pytest.raises(InvalidEvidenceError, match="does not match"):
        validate_candidate(
            session,
            document,
            candidate(quote_text="a different text", quote_start=0, quote_end=16),
        )


def test_anchor_accepts_exact_offsets_and_builds_a_stable_hash(evidence_database):
    session, document, _ = evidence_database

    first = validate_candidate(session, document, candidate())
    second = validate_candidate(session, document, candidate())

    assert first.quote_text == "0.8% per month"
    assert (first.quote_start, first.quote_end) == (31, 45)
    assert first.source_quote_hash == second.source_quote_hash
    assert len(first.source_quote_hash) == 64


def test_unique_quote_offsets_are_derived_when_omitted(evidence_database):
    session, document, _ = evidence_database

    accepted = validate_candidate(
        session,
        document,
        candidate(quote_start=None, quote_end=None),
    )

    assert (accepted.quote_start, accepted.quote_end) == (31, 45)


def test_repeated_quote_requires_explicit_offsets(evidence_database):
    session, document, _ = evidence_database

    with pytest.raises(InvalidEvidenceError, match="more than once"):
        validate_candidate(
            session,
            document,
            candidate(
                block_id="block-repeated",
                quote_text="Risk matters.",
                quote_start=None,
                quote_end=None,
            ),
        )


def test_anchor_cannot_cross_document_boundaries(evidence_database):
    session, document, _ = evidence_database

    with pytest.raises(InvalidEvidenceError, match="another document"):
        validate_candidate(
            session,
            document,
            candidate(
                block_id="block-foreign",
                quote_text="Foreign evidence",
                quote_start=0,
                quote_end=16,
            ),
        )


def test_missing_block_is_rejected(evidence_database):
    session, document, _ = evidence_database

    with pytest.raises(InvalidEvidenceError, match="does not exist"):
        validate_candidate(
            session,
            document,
            candidate(block_id="missing-block"),
        )


@pytest.mark.parametrize(
    ("quote_start", "quote_end", "message"),
    [
        (-1, 3, "outside"),
        (10, 10, "non-empty"),
        (10, 500, "outside"),
        (None, 20, "both be provided"),
    ],
)
def test_invalid_offset_pairs_are_rejected(
    evidence_database, quote_start, quote_end, message
):
    session, document, _ = evidence_database

    with pytest.raises(InvalidEvidenceError, match=message):
        validate_candidate(
            session,
            document,
            candidate(quote_start=quote_start, quote_end=quote_end),
        )


def test_duplicate_anchors_are_removed_deterministically(evidence_database):
    session, document, _ = evidence_database

    accepted = validate_candidates(
        session,
        document,
        [candidate(), candidate(), candidate(relation="qualifies")],
    )

    assert len(accepted) == 2
    assert [anchor.relation for anchor in accepted] == ["supports", "qualifies"]


@pytest.mark.parametrize(
    "source_label",
    [
        "https://example.com/result",
        "www.example.com/result",
        "/Users/researcher/private/paper.pdf",
        r"C:\\private\\paper.pdf",
        "<script>alert('x')</script>",
    ],
)
def test_structured_evidence_fields_reject_urls_paths_and_html(source_label):
    with pytest.raises(InvalidEvidenceError, match="source_label"):
        candidate(source_label=source_label)


def test_verbatim_quotes_are_not_sanitized(evidence_database):
    session, document, _ = evidence_database
    block = session.get(Block, "block-1")
    assert block is not None
    block.source_text = "Data are available at https://example.edu/dataset."
    session.commit()

    accepted = validate_candidate(
        session,
        document,
        candidate(
            quote_text="https://example.edu/dataset",
            quote_start=22,
            quote_end=49,
            source_label=None,
        ),
    )

    assert accepted.quote_text == "https://example.edu/dataset"
