from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from glyph.main import create_app
from glyph.models import Block, Document, ResearchMapJob, ResearchNodeReview
from glyph.research_ai import MockResearchMapProvider, NodeDraft
from glyph.research_maps import ResearchMapService

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "empirical_asset_pricing.txt"
SOURCE_HASH = "a" * 64


class CapturingExecutor:
    def __init__(self) -> None:
        self.job_ids: list[str] = []

    def submit(self, job_id: str) -> Future[None]:
        self.job_ids.append(job_id)
        future: Future[None] = Future()
        return future


@pytest.fixture
def research_api(tmp_path, monkeypatch):
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(tmp_path / "book"))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    app = create_app()
    executor = CapturingExecutor()
    app.state.research_job_executor = executor
    paragraphs = [
        line.strip()
        for line in FIXTURE_PATH.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    with app.state.session_factory.begin() as session:
        document = Document(
            id="paper-1",
            title="Signal Persistence and Expected Returns",
            source_path="/Users/private/book/synthetic-paper.txt",
            content_hash=SOURCE_HASH,
            processed_content_hash=SOURCE_HASH,
            file_type="txt",
            status="completed",
        )
        session.add(document)
        session.add_all(
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
        )
    return app, TestClient(app), executor, "paper-1"


def generate_map(app, document_id: str):
    with app.state.session_factory.begin() as session:
        version = ResearchMapService(session, MockResearchMapProvider()).generate(
            document_id
        )
        return version.id


def test_enqueue_and_job_routes_are_typed_and_do_not_leak_internal_fields(
    research_api,
):
    app, client, executor, document_id = research_api

    response = client.post(f"/api/documents/{document_id}/research-map")

    assert response.status_code == 202
    payload = response.json()
    assert payload == {
        "id": payload["id"],
        "document_id": document_id,
        "map_version_id": None,
        "status": "queued",
        "stage": "queued",
        "progress": 0.0,
        "error_message": None,
        "attempt_count": 0,
        "created_at": payload["created_at"],
        "updated_at": payload["updated_at"],
    }
    assert executor.job_ids == [payload["id"]]
    assert "lease" not in response.text.lower()
    assert "/Users/private" not in response.text

    job_response = client.get(f"/api/research-map-jobs/{payload['id']}")
    assert job_response.status_code == 200
    assert job_response.json() == payload

    with app.state.session_factory() as session:
        stored = session.get(ResearchMapJob, payload["id"])
        assert stored is not None
        assert stored.lease_token is None


def test_active_and_explicit_map_payloads_include_verifiable_bilingual_evidence(
    research_api,
):
    app, client, _, document_id = research_api
    version_id = generate_map(app, document_id)

    active_response = client.get(f"/api/documents/{document_id}/research-map")
    explicit_response = client.get(f"/api/research-maps/{version_id}")

    assert active_response.status_code == 200
    assert explicit_response.status_code == 200
    assert active_response.json() == explicit_response.json()
    payload = active_response.json()
    assert payload["id"] == version_id
    assert payload["status"] == "partial"
    assert payload["is_active"] is True
    assert payload["is_current"] is True
    assert payload["is_stale"] is False
    assert payload["reviewed_core_nodes"] == 0
    assert payload["reviewable_core_nodes"] > 0
    assert payload["issues"][0]["code"] == "not_reported"
    first_node = payload["nodes"][0]
    assert first_node["provenance"] == "author_explicit"
    assert first_node["evidence_quality"] == "direct"
    assert first_node["review"] is None
    evidence = first_node["evidence"][0]
    assert evidence["quote_text"].startswith("Research Question:")
    assert evidence["translated_text"].startswith("繁中：")
    assert evidence["locator_type"] == "text_span"
    assert evidence["relation"] == "supports"
    assert evidence["page_number"] == 1
    assert evidence["quote_start"] == 0
    assert evidence["quote_end"] == len(evidence["quote_text"])
    assert "/Users/private" not in active_response.text
    assert "lease_token" not in active_response.text


def test_version_list_is_ordered_and_exposes_compact_state(research_api):
    app, client, _, document_id = research_api
    first_id = generate_map(app, document_id)
    second_id = generate_map(app, document_id)

    response = client.get(f"/api/documents/{document_id}/research-map/versions")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [second_id, first_id]
    assert [item["is_active"] for item in payload] == [True, False]
    assert all(item["status"] == "partial" for item in payload)
    assert all(item["is_current"] is True for item in payload)


def test_document_list_batches_active_map_progress_without_n_plus_one(research_api):
    app, client, _, document_id = research_api
    source_dir = app.state.settings.data_dir / "summary-sources"
    source_dir.mkdir(parents=True)
    primary_source = source_dir / "paper-1.txt"
    primary_source.write_text("synthetic source")
    with app.state.session_factory.begin() as session:
        primary = session.get(Document, document_id)
        assert primary is not None
        primary.source_path = str(primary_source)
        for index in range(12):
            source = source_dir / f"paper-{index + 2}.txt"
            source.write_text(f"source {index}")
            session.add(
                Document(
                    id=f"paper-{index + 2}",
                    title=f"Paper {index + 2}",
                    source_path=str(source),
                    content_hash=f"{index + 1:x}".rjust(64, "0"),
                    processed_content_hash=None,
                    file_type="txt",
                    status="discovered",
                )
            )

    version_id = generate_map(app, document_id)
    active_map = client.get(f"/api/research-maps/{version_id}").json()
    first_node = active_map["nodes"][0]
    client.patch(
        f"/api/research-nodes/{first_node['id']}/review",
        json={
            "status": "confirmed",
            "based_on_node_signature": first_node["node_signature"],
        },
    )

    select_count = 0

    def count_selects(_connection, _cursor, statement, _parameters, _context, _many):
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    engine = app.state.session_factory.kw["bind"]
    event.listen(engine, "before_cursor_execute", count_selects)
    try:
        response = client.get("/api/documents")
    finally:
        event.remove(engine, "before_cursor_execute", count_selects)

    assert response.status_code == 200
    documents = {item["id"]: item for item in response.json()}
    summary = documents[document_id]["research_map"]
    assert summary == {
        "version_id": version_id,
        "status": "partial",
        "is_current": False,
        "is_stale": True,
        "reviewed_core_nodes": 1,
        "reviewable_core_nodes": active_map["reviewable_core_nodes"],
        "issue_count": len(active_map["issues"]),
    }
    assert documents["paper-2"]["research_map"] is None
    assert select_count <= 6


def test_review_routes_append_history_and_apply_effective_correction(research_api):
    app, client, _, document_id = research_api
    version_id = generate_map(app, document_id)
    map_payload = client.get(f"/api/research-maps/{version_id}").json()
    node = map_payload["nodes"][0]

    confirmed = client.patch(
        f"/api/research-nodes/{node['id']}/review",
        json={
            "status": "confirmed",
            "based_on_node_signature": node["node_signature"],
            "corrected_claim_text": "must be cleared",
            "review_note": "Checked against the paper.",
        },
    )
    corrected = client.patch(
        f"/api/research-nodes/{node['id']}/review",
        json={
            "status": "corrected",
            "based_on_node_signature": node["node_signature"],
            "corrected_claim_text": "人工校正後的研究問題",
            "review_note": "原文範圍更窄。",
        },
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["revision_number"] == 1
    assert confirmed.json()["corrected_claim_text"] is None
    assert corrected.status_code == 200
    assert corrected.json()["revision_number"] == 2
    assert corrected.json()["supersedes_review_id"] == confirmed.json()["id"]
    updated_node = client.get(f"/api/research-maps/{version_id}").json()["nodes"][0]
    assert updated_node["claim_text"] == node["claim_text"]
    assert updated_node["effective_claim_text"] == "人工校正後的研究問題"
    assert updated_node["review"]["status"] == "corrected"
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ResearchNodeReview)) == 2


def test_review_validation_and_optimistic_conflict_boundaries(research_api):
    app, client, _, document_id = research_api
    version_id = generate_map(app, document_id)
    node = client.get(f"/api/research-maps/{version_id}").json()["nodes"][0]

    missing_correction = client.patch(
        f"/api/research-nodes/{node['id']}/review",
        json={
            "status": "corrected",
            "based_on_node_signature": node["node_signature"],
        },
    )
    unknown_status = client.patch(
        f"/api/research-nodes/{node['id']}/review",
        json={
            "status": "approved_by_ai",
            "based_on_node_signature": node["node_signature"],
        },
    )
    obsolete = client.patch(
        f"/api/research-nodes/{node['id']}/review",
        json={
            "status": "questioned",
            "based_on_node_signature": "0" * 64,
        },
    )

    assert missing_correction.status_code == 422
    assert unknown_status.status_code == 422
    assert obsolete.status_code == 409
    assert "obsolete" in obsolete.json()["detail"].lower()


def test_activation_and_deterministic_diff_routes(research_api):
    app, client, _, document_id = research_api
    first_id = generate_map(app, document_id)
    with app.state.session_factory.begin() as session:
        question = session.get(Block, "block-0")
        assert question is not None
        question.source_text = (
            "Research Question: Does the revised signal predict returns?"
        )
    second_id = generate_map(app, document_id)

    diff_response = client.get(
        f"/api/research-maps/{second_id}/diff?against={first_id}"
    )
    activate_response = client.post(f"/api/research-maps/{first_id}/activate")

    assert diff_response.status_code == 200
    diff = diff_response.json()
    assert diff["version_id"] == second_id
    assert diff["against_version_id"] == first_id
    classifications = {
        item["node_key"]: item["classification"] for item in diff["nodes"]
    }
    assert classifications["author_claim.1"] == "claim_changed"
    assert classifications["data_source.1"] == "unchanged"
    assert activate_response.status_code == 200
    assert activate_response.json()["id"] == first_id
    assert activate_response.json()["is_active"] is True
    assert (
        client.get(f"/api/documents/{document_id}/research-map").json()["id"]
        == first_id
    )


def test_diff_classifies_evidence_changes_additions_and_removals(research_api):
    app, client, _, document_id = research_api
    first_id = generate_map(app, document_id)

    class StructurallyChangedProvider(MockResearchMapProvider):
        def synthesize_nodes(self, evidence):
            base_nodes = list(super().synthesize_nodes(evidence))
            sample_evidence_id = next(
                item.evidence_id
                for item in evidence
                if item.node_type == "data_and_sample"
            )
            changed_nodes = [
                replace(node, evidence_ids=(sample_evidence_id,))
                if node.node_type == "data_source"
                else node
                for node in base_nodes
                if node.node_type != "limitations"
            ]
            changed_nodes.append(
                NodeDraft(
                    node_key="unanswered_question.1",
                    node_type="unanswered_question",
                    title="Unanswered question",
                    claim_text="Can this signal survive live implementation?",
                    explanation="",
                    provenance="human_created",
                    evidence_quality="insufficient",
                    evidence_ids=(),
                    display_order=len(changed_nodes),
                )
            )
            return tuple(changed_nodes)

    with app.state.session_factory.begin() as session:
        second = ResearchMapService(session, StructurallyChangedProvider()).generate(
            document_id
        )
        second_id = second.id

    response = client.get(f"/api/research-maps/{second_id}/diff?against={first_id}")

    assert response.status_code == 200
    classifications = {
        item["node_key"]: item["classification"] for item in response.json()["nodes"]
    }
    assert classifications["data_source.1"] == "evidence_changed"
    assert classifications["limitations.1"] == "removed"
    assert classifications["unanswered_question.1"] == "added"


def test_http_404_409_and_stale_activation_boundaries(research_api):
    app, client, _, document_id = research_api
    version_id = generate_map(app, document_id)

    assert client.get("/api/research-map-jobs/missing").status_code == 404
    assert client.get("/api/research-maps/missing").status_code == 404
    assert client.get("/api/documents/missing/research-map").status_code == 404
    assert (
        client.patch(
            "/api/research-nodes/missing/review",
            json={"status": "confirmed", "based_on_node_signature": "0" * 64},
        ).status_code
        == 404
    )

    with app.state.session_factory.begin() as session:
        document = session.get(Document, document_id)
        assert document is not None
        document.status = "stale"
        document.content_hash = "b" * 64

    enqueue = client.post(f"/api/documents/{document_id}/research-map")
    activate = client.post(f"/api/research-maps/{version_id}/activate")
    stale_payload = client.get(f"/api/research-maps/{version_id}").json()
    assert enqueue.status_code == 409
    assert activate.status_code == 409
    assert stale_payload["is_current"] is False
    assert stale_payload["is_stale"] is True
