from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from glyph.models import (
    Base,
    Block,
    Document,
    ResearchEvidence,
    ResearchMapIssue,
    ResearchMapVersion,
    ResearchNode,
    ResearchNodeReview,
)
from glyph.pipeline import clear_document_outputs
from glyph.research_ai import MockResearchMapProvider
from glyph.research_maps import (
    ResearchMapConflictError,
    ResearchMapService,
    activate_research_map,
    append_node_review,
    load_research_map,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "empirical_asset_pricing.txt"
SOURCE_HASH = "a" * 64


@pytest.fixture
def map_database() -> Iterator[tuple[Session, Document]]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    document = Document(
        id="paper-1",
        title="Signal Persistence and Expected Returns",
        source_path="/books/synthetic-paper.txt",
        content_hash=SOURCE_HASH,
        processed_content_hash=SOURCE_HASH,
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
            source_content_hash=SOURCE_HASH,
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
    try:
        yield session, document
    finally:
        session.close()
        engine.dispose()


def counts(session: Session) -> dict[str, int]:
    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model))
        or 0
        for model in (
            ResearchMapVersion,
            ResearchNode,
            ResearchEvidence,
            ResearchMapIssue,
            ResearchNodeReview,
        )
    }


def test_generate_persists_an_active_audited_version(map_database):
    session, document = map_database
    service = ResearchMapService(session, MockResearchMapProvider())

    version = service.generate(document.id)
    session.commit()

    assert version.document_id == document.id
    assert version.previous_version_id is None
    assert version.source_content_hash == SOURCE_HASH
    assert version.schema_version == "1"
    assert version.provider == "mock"
    assert version.model_name is None
    assert version.status == "partial"
    assert version.is_active is True
    assert version.completed_at is not None
    assert len(version.nodes) == 13
    assert any(issue.code == "not_reported" for issue in version.issues)
    assert all(node.node_signature for node in version.nodes)
    assert counts(session) == {
        "research_map_versions": 1,
        "research_nodes": 13,
        "research_evidence": 13,
        "research_map_issues": 1,
        "research_node_reviews": 0,
    }


def test_replacement_is_deterministic_and_switches_active_version(map_database):
    session, document = map_database
    service = ResearchMapService(session, MockResearchMapProvider())
    first = service.generate(document.id)
    session.commit()
    first_signatures = {node.node_key: node.node_signature for node in first.nodes}

    second = service.generate(document.id)
    session.commit()
    session.refresh(first)

    assert first.is_active is False
    assert second.is_active is True
    assert second.previous_version_id == first.id
    assert {node.node_key: node.node_signature for node in second.nodes} == (
        first_signatures
    )
    assert session.scalars(
        select(ResearchMapVersion).where(ResearchMapVersion.is_active.is_(True))
    ).all() == [second]


@pytest.mark.parametrize(
    ("status", "content_hash", "processed_hash", "remove_blocks", "message"),
    [
        ("stale", "b" * 64, SOURCE_HASH, False, "current completed Reader"),
        ("missing", SOURCE_HASH, SOURCE_HASH, False, "current completed Reader"),
        ("discovered", SOURCE_HASH, None, False, "current completed Reader"),
        ("completed", SOURCE_HASH, SOURCE_HASH, True, "Reader blocks"),
    ],
)
def test_generation_requires_a_current_completed_reader(
    map_database,
    status,
    content_hash,
    processed_hash,
    remove_blocks,
    message,
):
    session, document = map_database
    document.status = status
    document.content_hash = content_hash
    document.processed_content_hash = processed_hash
    if remove_blocks:
        session.query(Block).delete()
    session.commit()

    with pytest.raises(ResearchMapConflictError, match=message):
        ResearchMapService(session, MockResearchMapProvider()).generate(document.id)

    assert counts(session)["research_map_versions"] == 0


def test_persistence_failure_preserves_active_map_and_reviews(
    map_database, monkeypatch
):
    session, document = map_database
    service = ResearchMapService(session, MockResearchMapProvider())
    active = service.generate(document.id)
    session.commit()
    reviewed_node = active.nodes[0]
    review = ResearchNodeReview(
        id="review-1",
        node_id=reviewed_node.id,
        revision_number=1,
        status="confirmed",
        based_on_map_version_id=active.id,
        based_on_node_signature=reviewed_node.node_signature,
    )
    session.add(review)
    session.commit()
    before = counts(session)

    def fail_after_nodes_and_evidence(*args, **kwargs):
        raise RuntimeError("injected persistence failure")

    monkeypatch.setattr(
        "glyph.research_maps.persist_map_issues",
        fail_after_nodes_and_evidence,
    )

    with pytest.raises(RuntimeError, match="injected persistence failure"):
        service.generate(document.id)

    session.expire_all()
    assert counts(session) == before
    assert session.get(ResearchMapVersion, active.id).is_active is True
    assert session.get(ResearchNodeReview, review.id).status == "confirmed"


def test_review_revision_race_returns_a_reload_conflict(map_database, monkeypatch):
    session, document = map_database
    version = ResearchMapService(session, MockResearchMapProvider()).generate(
        document.id
    )
    session.commit()
    node = version.nodes[0]

    original_flush = session.flush

    def fail_with_revision_race(*args, **kwargs):
        if any(isinstance(value, ResearchNodeReview) for value in session.new):
            raise IntegrityError("INSERT review", {}, Exception("duplicate revision"))
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(session, "flush", fail_with_revision_race)

    with pytest.raises(ResearchMapConflictError, match="Review changed concurrently"):
        append_node_review(
            session,
            node.id,
            status="confirmed",
            based_on_node_signature=node.node_signature,
            corrected_claim_text=None,
            review_note=None,
        )


def test_loader_batches_exact_evidence_and_effective_review(map_database):
    session, document = map_database
    version = ResearchMapService(session, MockResearchMapProvider()).generate(
        document.id
    )
    session.commit()
    reviewed_node = version.nodes[0]
    session.add(
        ResearchNodeReview(
            id="review-1",
            node_id=reviewed_node.id,
            revision_number=1,
            status="corrected",
            corrected_claim_text="人工校正後的研究問題",
            review_note="原文問題描述較精確。",
            based_on_map_version_id=version.id,
            based_on_node_signature=reviewed_node.node_signature,
        )
    )
    session.commit()

    loaded = load_research_map(session, version.id)

    first_node = loaded.nodes[0]
    assert loaded.is_current is True
    assert loaded.is_stale is False
    assert loaded.reviewed_core_nodes == 1
    assert loaded.reviewable_core_nodes > loaded.reviewed_core_nodes
    assert first_node.review is not None
    assert first_node.review.status == "corrected"
    assert first_node.effective_claim_text == "人工校正後的研究問題"
    assert first_node.evidence[0].quote_text.startswith("Research Question:")
    assert first_node.evidence[0].translated_text.startswith("繁中：")
    assert first_node.evidence[0].page_number == 1


def test_failed_or_stale_version_cannot_be_activated(map_database):
    session, document = map_database
    failed = ResearchMapVersion(
        id="failed-map",
        document_id=document.id,
        source_content_hash=SOURCE_HASH,
        schema_version="1",
        provider="mock",
        status="failed",
        is_active=False,
    )
    session.add(failed)
    session.commit()

    with pytest.raises(ResearchMapConflictError, match="complete or partial"):
        activate_research_map(session, failed.id)

    failed.status = "partial"
    document.content_hash = "b" * 64
    session.commit()
    with pytest.raises(ResearchMapConflictError, match="stale"):
        activate_research_map(session, failed.id)


def test_reprocessing_preserves_blocks_cited_by_immutable_versions(map_database):
    session, document = map_database
    version = ResearchMapService(session, MockResearchMapProvider()).generate(
        document.id
    )
    session.commit()
    cited_block_ids = set(session.scalars(select(ResearchEvidence.block_id)).all())

    clear_document_outputs(session, document.id)
    document.content_hash = "b" * 64
    document.processed_content_hash = "b" * 64
    session.add(
        Block(
            id="replacement-block",
            document_id=document.id,
            source_content_hash=document.processed_content_hash,
            order_index=0,
            page_number=1,
            block_type="paragraph",
            source_text="A newly processed source snapshot.",
            translated_text="重新處理後的來源。",
        )
    )
    session.commit()

    assert (
        set(
            session.scalars(select(Block.id).where(Block.id.in_(cited_block_ids))).all()
        )
        == cited_block_ids
    )
    assert session.scalars(
        select(Block.id).where(
            Block.document_id == document.id,
            Block.source_content_hash == document.processed_content_hash,
        )
    ).all() == ["replacement-block"]
    loaded = load_research_map(session, version.id)
    assert loaded.is_stale is True
    assert loaded.nodes[0].evidence[0].quote_text.startswith("Research Question:")
