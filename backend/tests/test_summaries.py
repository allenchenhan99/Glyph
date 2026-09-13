from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from support import make_book_app, process_and_wait

from glyph.models import Block, Document, SummaryEvidence, SummaryVersion
from glyph.summaries import (
    SummaryConflictError,
    SummaryValidationError,
    capture_summary_inputs,
    current_reader_blocks,
    load_summary_state,
    persist_summary_version,
    validate_claims,
)
from glyph.summary_domain import ClaimDraft, QuoteDraft, compute_reader_fingerprint

TEXT = (
    "# Introduction\n\nAlpha decays quickly after publication.\n\n"
    "Returns concentrate in small stocks.\n\n"
    "# Data\n\nThe sample covers 1990 to 2020.\n\nCRSP monthly returns are used."
)


def prepared_document(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch, TEXT)
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    assert process_and_wait(client, document_id)["status"] == "completed"
    return app, client, document_id


def quote(block: Block, text: str | None = None) -> QuoteDraft:
    body = text or block.source_text
    start = block.source_text.index(body)
    return QuoteDraft(block.id, body, start, start + len(body))


def valid_drafts(inputs) -> tuple[ClaimDraft, ...]:
    by_path: dict[str | None, list[Block]] = {}
    for block in inputs.blocks:
        by_path.setdefault(inputs.section_path_of(block), []).append(block)
    drafts = [ClaimDraft(None, "Overview claim.", (quote(inputs.blocks[0]),))]
    for path, blocks in by_path.items():
        if path is not None:
            drafts.append(ClaimDraft(path, f"Claim for {path}.", (quote(blocks[-1]),)))
    return tuple(drafts)


def test_fingerprint_covers_ids_order_and_text_of_attached_blocks_only(
    tmp_path, monkeypatch
):
    app, client, document_id = prepared_document(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        document = session.get(Document, document_id)
        blocks = current_reader_blocks(session, document)
        assert all(block.section_id is not None for block in blocks)
        baseline = compute_reader_fingerprint(blocks)
        assert compute_reader_fingerprint(list(reversed(blocks))) != baseline
        changed = [*blocks]
        changed[0] = Block(
            id=blocks[0].id,
            document_id=document_id,
            source_content_hash=blocks[0].source_content_hash,
            section_id=blocks[0].section_id,
            order_index=blocks[0].order_index,
            block_type="paragraph",
            source_text="edited",
        )
        assert compute_reader_fingerprint(changed) != baseline
        retained = Block(
            id="retained",
            document_id=document_id,
            source_content_hash=blocks[0].source_content_hash,
            section_id=None,
            order_index=99,
            block_type="paragraph",
            source_text="old",
        )
        session.add(retained)
        session.flush()
        assert [b.id for b in current_reader_blocks(session, document)] == [
            b.id for b in blocks
        ]
        inputs = capture_summary_inputs(session, document_id)
        assert inputs.reader_fingerprint == baseline
        assert inputs.source_content_hash == document.processed_content_hash


def test_inputs_require_a_current_completed_reader(tmp_path, monkeypatch):
    app = make_book_app(tmp_path, monkeypatch, TEXT)
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]
    with app.state.session_factory() as session:
        with pytest.raises(SummaryConflictError):
            capture_summary_inputs(session, document_id)
        with pytest.raises(LookupError):
            capture_summary_inputs(session, "missing")


def test_valid_claims_are_accepted_with_exact_offsets_and_section_paths(
    tmp_path, monkeypatch
):
    app, client, document_id = prepared_document(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        inputs = capture_summary_inputs(session, document_id)
        accepted = validate_claims(inputs, valid_drafts(inputs))
    assert accepted[0].section_path is None
    assert {claim.section_path for claim in accepted[1:]} == set(inputs.section_paths)
    evidence = accepted[0].evidence[0]
    assert evidence.block_id == inputs.blocks[0].id
    assert evidence.quote_text == inputs.blocks[0].source_text
    assert (evidence.quote_start, evidence.quote_end) == (
        0,
        len(inputs.blocks[0].source_text),
    )
    assert evidence.page_number == inputs.blocks[0].page_number
    assert evidence.source_quote_hash


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda i: QuoteDraft("not-a-block", "Alpha", 0, 5), "does not exist"),
        (
            lambda i: QuoteDraft(i.blocks[0].id, "never in text", 0, 12),
            "does not match",
        ),
        (
            lambda i: QuoteDraft(i.blocks[0].id, i.blocks[0].source_text, 1, 3),
            "does not match",
        ),
        (
            lambda i: QuoteDraft(i.blocks[0].id, i.blocks[0].source_text, 0, 10_000),
            "outside",
        ),
        (lambda i: QuoteDraft(i.blocks[0].id, "  ", None, None), "non-empty"),
        (lambda i: QuoteDraft(i.blocks[2].id, "s", None, None), "more than once"),
    ],
)
def test_invalid_evidence_is_rejected(tmp_path, monkeypatch, mutate, fragment):
    app, client, document_id = prepared_document(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        inputs = capture_summary_inputs(session, document_id)
        drafts = list(valid_drafts(inputs))
        drafts[0] = ClaimDraft(None, "Overview claim.", (mutate(inputs),))
        with pytest.raises(SummaryValidationError, match=fragment):
            validate_claims(inputs, tuple(drafts))


def test_foreign_and_retained_blocks_are_rejected(tmp_path, monkeypatch):
    app, client, document_id = prepared_document(tmp_path, monkeypatch)
    (tmp_path / "book" / "other.pdf").write_text("# Other\n\nForeign block text.")
    other_id = next(
        d["id"]
        for d in client.get("/api/documents").json()
        if d["title"] == "other.pdf"
    )
    assert process_and_wait(client, other_id)["status"] == "completed"
    with app.state.session_factory() as session:
        inputs = capture_summary_inputs(session, document_id)
        foreign = session.scalars(
            select(Block).where(Block.document_id == other_id)
        ).first()
        drafts = list(valid_drafts(inputs))
        drafts[0] = ClaimDraft(None, "Overview claim.", (quote(foreign),))
        with pytest.raises(SummaryValidationError, match="permitted"):
            validate_claims(inputs, tuple(drafts))
        retained = Block(
            id="retained",
            document_id=document_id,
            source_content_hash=inputs.source_content_hash,
            section_id=None,
            order_index=99,
            block_type="paragraph",
            source_text="Retained old text.",
        )
        session.add(retained)
        session.flush()
        drafts[0] = ClaimDraft(None, "Overview claim.", (quote(retained),))
        with pytest.raises(SummaryValidationError, match="permitted"):
            validate_claims(inputs, tuple(drafts))


@pytest.mark.parametrize(
    ("edit", "fragment"),
    [
        ("drop_overview", "overview"),
        ("drop_section", "coverage"),
        ("unknown_section", "section"),
        ("cross_section", "own section"),
        ("no_evidence", "at least one"),
        ("empty_text", "text"),
    ],
)
def test_claim_structure_rules(tmp_path, monkeypatch, edit, fragment):
    app, client, document_id = prepared_document(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        inputs = capture_summary_inputs(session, document_id)
        drafts = list(valid_drafts(inputs))
        section_claim = drafts[1]
        other_section_block = next(
            b
            for b in inputs.blocks
            if inputs.section_path_of(b) not in {None, section_claim.section_path}
        )
        if edit == "drop_overview":
            drafts = drafts[1:]
        elif edit == "drop_section":
            drafts = drafts[:-1]
        elif edit == "unknown_section":
            drafts[1] = ClaimDraft("Nope", section_claim.text, section_claim.evidence)
        elif edit == "cross_section":
            drafts[1] = ClaimDraft(
                section_claim.section_path,
                section_claim.text,
                (quote(other_section_block),),
            )
        elif edit == "no_evidence":
            drafts[1] = ClaimDraft(section_claim.section_path, section_claim.text, ())
        elif edit == "empty_text":
            drafts[1] = ClaimDraft(
                section_claim.section_path, "   ", section_claim.evidence
            )
        with pytest.raises(SummaryValidationError, match=fragment):
            validate_claims(inputs, tuple(drafts))


def test_persist_publishes_atomically_and_keeps_prior_version_on_failure(
    tmp_path, monkeypatch
):
    app, client, document_id = prepared_document(tmp_path, monkeypatch)
    with app.state.session_factory.begin() as session:
        inputs = capture_summary_inputs(session, document_id)
        first = persist_summary_version(
            session,
            inputs,
            validate_claims(inputs, valid_drafts(inputs)),
            provider="mock",
            model=None,
        )
        first_id = first.id
    with app.state.session_factory.begin() as session:
        inputs = capture_summary_inputs(session, document_id)
        second = persist_summary_version(
            session,
            inputs,
            validate_claims(inputs, valid_drafts(inputs)),
            provider="mock",
            model=None,
        )
        second_id = second.id
    with app.state.session_factory() as session:
        versions = session.scalars(
            select(SummaryVersion).where(SummaryVersion.document_id == document_id)
        ).all()
        assert {v.id: v.is_active for v in versions} == {
            first_id: False,
            second_id: True,
        }
        assert session.get(SummaryVersion, second_id).previous_version_id == first_id
        assert session.scalars(select(SummaryEvidence)).all()
        # Identity drift between input capture and publication is rejected.
        stale_inputs = capture_summary_inputs(session, document_id)
    object.__setattr__(stale_inputs, "reader_fingerprint", "0" * 64)
    with (
        app.state.session_factory.begin() as session,
        pytest.raises(SummaryConflictError, match="changed"),
    ):
        persist_summary_version(
            session,
            stale_inputs,
            validate_claims(
                capture_summary_inputs(session, document_id),
                valid_drafts(stale_inputs),
            ),
            provider="mock",
            model=None,
        )
    with app.state.session_factory() as session:
        assert session.get(SummaryVersion, second_id).is_active is True
        state = load_summary_state(session, document_id, app.state.settings)
    assert state.status == "available"
    assert state.version is not None and state.version.id == second_id
    assert state.version.claims[0].section_path is None
    assert state.version.claims[0].evidence[0].page_number >= 1


def test_same_file_reprocessing_keeps_citations_without_duplicate_reader_rows(
    tmp_path, monkeypatch
):
    app, client, document_id = prepared_document(tmp_path, monkeypatch)
    with app.state.session_factory.begin() as session:
        inputs = capture_summary_inputs(session, document_id)
        persist_summary_version(
            session,
            inputs,
            validate_claims(inputs, valid_drafts(inputs)),
            provider="mock",
            model=None,
        )
        cited_ids = {e.block_id for e in session.scalars(select(SummaryEvidence)).all()}
        source_hash = inputs.source_content_hash
        block_count = len(inputs.blocks)
    assert process_and_wait(client, document_id)["status"] == "completed"
    default_reader = client.get(f"/api/documents/{document_id}/reader").json()
    assert len(default_reader["blocks"]) == block_count
    assert len({b["id"] for b in default_reader["blocks"]}) == block_count
    assert cited_ids.isdisjoint({b["id"] for b in default_reader["blocks"]})
    historical = client.get(
        f"/api/documents/{document_id}/reader",
        params={"source_content_hash": source_hash},
    ).json()
    assert cited_ids <= {b["id"] for b in historical["blocks"]}
    assert len(historical["blocks"]) == block_count + len(cited_ids)
    with app.state.session_factory() as session:
        state = load_summary_state(session, document_id, app.state.settings)
    assert state.status == "stale"
    assert state.version is not None
    assert {e.block_id for c in state.version.claims for e in c.evidence} == cited_ids
    assert state.version.claims[0].evidence[0].quote_text


def test_reader_no_longer_exposes_placeholder_summaries(tmp_path, monkeypatch):
    app, client, document_id = prepared_document(tmp_path, monkeypatch)
    reader = client.get(f"/api/documents/{document_id}/reader").json()
    assert reader["summary"] == ""
    assert all(section["summary"] == "" for section in reader["sections"])
    assert client.get(f"/api/documents/{document_id}/summary").json() == {"summary": ""}


def test_source_mutation_without_catalog_refresh_blocks_publication(
    tmp_path, monkeypatch
):
    app, client, document_id = prepared_document(tmp_path, monkeypatch)
    with app.state.session_factory() as session:
        inputs = capture_summary_inputs(session, document_id)
        accepted = validate_claims(inputs, valid_drafts(inputs))
    (tmp_path / "book" / "sample.pdf").write_text(TEXT + "\n\nAppended after capture.")
    with (
        app.state.session_factory.begin() as session,
        pytest.raises(SummaryConflictError, match="changed"),
    ):
        persist_summary_version(session, inputs, accepted, provider="mock", model=None)
    with app.state.session_factory() as session:
        assert session.scalars(select(SummaryVersion)).all() == []


def test_retained_summary_citations_do_not_duplicate_research_map_inputs(
    tmp_path, monkeypatch
):
    from glyph.research_ai import MockResearchMapProvider
    from glyph.research_maps import ResearchMapService

    app, client, document_id = prepared_document(tmp_path, monkeypatch)
    with app.state.session_factory.begin() as session:
        inputs = capture_summary_inputs(session, document_id)
        persist_summary_version(
            session,
            inputs,
            validate_claims(inputs, valid_drafts(inputs)),
            provider="mock",
            model=None,
        )
        block_count = len(inputs.blocks)
    assert process_and_wait(client, document_id)["status"] == "completed"
    with app.state.session_factory() as session:
        document = session.get(Document, document_id)
        service = ResearchMapService(session, MockResearchMapProvider())
        map_inputs = service._current_blocks(document)
        assert len(map_inputs) == block_count
        assert len({b.source_text for b in map_inputs}) == len(
            {b.source_text for b in inputs.blocks}
        )
        assert all(b.section_id is not None for b in map_inputs)
