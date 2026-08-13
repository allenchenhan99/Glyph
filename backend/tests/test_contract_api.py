from __future__ import annotations

import hashlib
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from glyph.contract_ai import MockImplementationContractProvider
from glyph.implementation_contracts import ImplementationContractService
from glyph.main import create_app
from glyph.models import (
    Block,
    Document,
    ResearchEvidence,
    ResearchMapVersion,
    ResearchNode,
)
from glyph.research_evidence import exact_quote_hash

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "contracts" / "monthly_accounting_signal.txt"
)


class CapturingExecutor:
    def __init__(self) -> None:
        self.job_ids: list[str] = []

    def submit(self, job_id: str) -> Future[None]:
        self.job_ids.append(job_id)
        return Future()


def _add_inputs(
    session: Session,
    *,
    document_id: str,
    map_id: str,
    source_path: Path,
) -> tuple[Document, ResearchMapVersion]:
    source_text = FIXTURE_PATH.read_text(encoding="utf-8")
    source_path.write_text(source_text, encoding="utf-8")
    source_hash = hashlib.sha256(source_text.encode()).hexdigest()
    document = Document(
        id=document_id,
        title=f"Contract paper {document_id}",
        source_path=str(source_path),
        content_hash=source_hash,
        processed_content_hash=source_hash,
        file_type="txt",
        status="completed",
    )
    block = Block(
        id=f"block-{document_id}",
        document_id=document_id,
        source_content_hash=source_hash,
        order_index=0,
        page_number=1,
        block_type="text",
        source_text=source_text,
        translated_text=f"繁中：{source_text}",
    )
    map_version = ResearchMapVersion(
        id=map_id,
        document_id=document_id,
        source_content_hash=source_hash,
        schema_version="1",
        provider="mock",
        model_name=None,
        status="complete",
        is_active=True,
    )
    node = ResearchNode(
        id=f"node-{document_id}",
        map_version_id=map_id,
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
                id=f"evidence-{document_id}",
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
    return document, map_version


@pytest.fixture
def contract_api(tmp_path, monkeypatch):
    book_dir = tmp_path / "book"
    source_dir = tmp_path / "sources"
    book_dir.mkdir()
    source_dir.mkdir()
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book_dir))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    app = create_app()
    executor = CapturingExecutor()
    app.state.contract_job_executor = executor
    with app.state.session_factory.begin() as session:
        document, map_version = _add_inputs(
            session,
            document_id="paper-1",
            map_id="map-1",
            source_path=source_dir / "paper-1.txt",
        )
        _add_inputs(
            session,
            document_id="paper-2",
            map_id="map-2",
            source_path=source_dir / "paper-2.txt",
        )
    return app, TestClient(app), executor, document.id, map_version.id, source_dir


def _generate_contract(app, document_id: str, map_id: str) -> str:
    with app.state.session_factory.begin() as session:
        contract = ImplementationContractService(
            session, MockImplementationContractProvider()
        ).generate(document_id, map_id)
        return contract.id


def test_enqueue_and_job_routes_are_strict_typed_and_safe(contract_api):
    _app, client, executor, document_id, map_id, _source_dir = contract_api

    response = client.post(
        f"/api/documents/{document_id}/implementation-contract",
        json={"research_map_version_id": map_id},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload == {
        "id": payload["id"],
        "document_id": document_id,
        "requested_research_map_version_id": map_id,
        "contract_version_id": None,
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

    job_response = client.get(f"/api/implementation-contract-jobs/{payload['id']}")
    assert job_response.status_code == 200
    assert job_response.json() == payload

    extra = client.post(
        f"/api/documents/{document_id}/implementation-contract",
        json={"research_map_version_id": map_id, "provider": "unsafe"},
    )
    assert extra.status_code == 422


def test_enqueue_maps_missing_stale_duplicate_and_wrong_owner_boundaries(contract_api):
    app, client, _executor, document_id, map_id, _source_dir = contract_api

    assert (
        client.post(
            "/api/documents/missing/implementation-contract", json={}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/documents/{document_id}/implementation-contract",
            json={"research_map_version_id": "missing-map"},
        ).status_code
        == 404
    )
    wrong_owner = client.post(
        f"/api/documents/{document_id}/implementation-contract",
        json={"research_map_version_id": "map-2"},
    )
    assert wrong_owner.status_code == 409

    accepted = client.post(
        f"/api/documents/{document_id}/implementation-contract",
        json={"research_map_version_id": map_id},
    )
    duplicate = client.post(
        f"/api/documents/{document_id}/implementation-contract", json={}
    )
    assert accepted.status_code == 202
    assert duplicate.status_code == 409

    with app.state.session_factory.begin() as session:
        document = session.get(Document, "paper-2")
        assert document is not None
        document.status = "stale"
        document.content_hash = "f" * 64
    stale = client.post("/api/documents/paper-2/implementation-contract", json={})
    assert stale.status_code == 409


def test_contract_read_routes_return_nested_typed_values_not_orm_json(contract_api):
    app, client, _executor, document_id, map_id, _source_dir = contract_api
    version_id = _generate_contract(app, document_id, map_id)

    active = client.get(f"/api/documents/{document_id}/implementation-contract")
    explicit = client.get(f"/api/implementation-contracts/{version_id}")
    versions = client.get(
        f"/api/documents/{document_id}/implementation-contract/versions"
    )

    assert active.status_code == 200
    assert explicit.status_code == 200
    assert active.json() == explicit.json()
    payload = active.json()
    assert payload["id"] == version_id
    assert payload["research_map_version_id"] == map_id
    assert payload["readiness"] == "review_needed"
    assert payload["is_active"] is True
    assert payload["is_current"] is True
    assert payload["is_stale"] is False
    assert payload["items"]
    assert payload["items"][0]["draft_value"]["kind"] in {
        "scalar",
        "formula",
        "rule",
        "list",
        "range",
        "period",
    }
    assert payload["items"][0]["evidence"][0]["translated_text"].startswith("繁中：")
    assert "draft_value_json" not in active.text
    assert "resolved_value_json" not in active.text
    assert "source_path" not in active.text
    assert versions.status_code == 200
    assert [item["id"] for item in versions.json()] == [version_id]
    assert "items" not in versions.text


def test_resolution_route_validates_discriminated_values_and_updates_contract(
    contract_api,
):
    app, client, _executor, document_id, map_id, _source_dir = contract_api
    version_id = _generate_contract(app, document_id, map_id)
    contract = client.get(f"/api/implementation-contracts/{version_id}").json()
    target_item = contract["items"][0]
    endpoint = f"/api/implementation-contract-items/{target_item['id']}/resolution"
    base = {
        "request_id": "decision-1",
        "status": "corrected",
        "based_on_item_signature": target_item["item_signature"],
        "resolved_value": {
            "kind": "scalar",
            "value": 0.0025,
            "unit": "fraction",
        },
        "reason": "Use a conservative round-trip cost assumption.",
    }

    success = client.patch(endpoint, json=base)

    assert success.status_code == 200
    resolution = success.json()
    assert resolution["status"] == "corrected"
    assert resolution["resolved_value"] == base["resolved_value"]
    assert resolution["revision_number"] == 1
    updated = client.get(f"/api/implementation-contracts/{version_id}").json()
    updated_item = next(
        item for item in updated["items"] if item["id"] == target_item["id"]
    )
    assert updated_item["effective_origin"] == "human_decision"
    assert updated_item["effective_value"] == base["resolved_value"]

    malformed_payloads = [
        {**base, "request_id": "decision-2", "unexpected": True},
        {
            **base,
            "request_id": "decision-3",
            "resolved_value": {**base["resolved_value"], "unknown": "field"},
        },
        {
            **base,
            "request_id": "decision-4",
            "resolved_value": {"kind": "mystery", "value": 1},
        },
        {**base, "request_id": "decision-5", "reason": None},
        {**base, "request_id": "contains spaces"},
        {**base, "request_id": "decision-6", "based_on_item_signature": "bad"},
    ]
    assert all(
        client.patch(endpoint, json=payload).status_code == 422
        for payload in malformed_payloads
    )

    obsolete = client.patch(
        endpoint,
        json={**base, "request_id": "decision-7", "based_on_item_signature": "0" * 64},
    )
    assert obsolete.status_code == 409
    assert "obsolete" in obsolete.json()["detail"].lower()


def test_diff_activation_and_error_boundaries(contract_api):
    app, client, _executor, document_id, map_id, _source_dir = contract_api
    first_id = _generate_contract(app, document_id, map_id)
    second_id = _generate_contract(app, document_id, map_id)

    diff = client.get(
        f"/api/implementation-contracts/{second_id}/diff?against={first_id}"
    )
    activate = client.post(f"/api/implementation-contracts/{first_id}/activate")

    assert diff.status_code == 200
    assert diff.json()["version_id"] == second_id
    assert diff.json()["against_version_id"] == first_id
    assert all(item["classification"] == "unchanged" for item in diff.json()["items"])
    assert activate.status_code == 200
    assert activate.json()["id"] == first_id
    assert activate.json()["is_active"] is True
    assert (
        client.get(f"/api/documents/{document_id}/implementation-contract").json()["id"]
        == first_id
    )

    assert client.get("/api/implementation-contract-jobs/missing").status_code == 404
    assert client.get("/api/implementation-contracts/missing").status_code == 404
    assert (
        client.get(
            "/api/documents/missing/implementation-contract/versions"
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/implementation-contracts/{second_id}/diff").status_code == 422
    )
    assert (
        client.patch(
            "/api/implementation-contract-items/missing/resolution",
            json={
                "request_id": "missing-item",
                "status": "confirmed",
                "based_on_item_signature": "0" * 64,
            },
        ).status_code
        == 404
    )


def test_concurrent_ancestor_and_descendant_decisions_cannot_fork_history(
    contract_api,
):
    app, client, _executor, document_id, map_id, _source_dir = contract_api
    first_id = _generate_contract(app, document_id, map_id)
    second_id = _generate_contract(app, document_id, map_id)
    first = client.get(f"/api/implementation-contracts/{first_id}").json()
    second = client.get(f"/api/implementation-contracts/{second_id}").json()
    first_item = first["items"][0]
    second_item = next(
        item for item in second["items"] if item["item_key"] == first_item["item_key"]
    )

    def decide(item: dict, request_id: str):
        with TestClient(app) as request_client:
            return request_client.patch(
                f"/api/implementation-contract-items/{item['id']}/resolution",
                json={
                    "request_id": request_id,
                    "status": "confirmed",
                    "based_on_item_signature": item["item_signature"],
                },
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        ancestor_future = executor.submit(decide, first_item, "ancestor-race")
        descendant_future = executor.submit(decide, second_item, "descendant-race")
        ancestor = ancestor_future.result(timeout=5)
        descendant = descendant_future.result(timeout=5)

    assert ancestor.status_code == 409
    assert "historical Contract item" in ancestor.json()["detail"]
    assert descendant.status_code == 200
    loaded = client.get(f"/api/implementation-contracts/{second_id}").json()
    loaded_item = next(
        item for item in loaded["items"] if item["item_key"] == first_item["item_key"]
    )
    assert [
        entry["revision_number"] for entry in loaded_item["resolution_history"]
    ] == [1]


def test_document_list_batches_contract_summary_without_n_plus_one(contract_api):
    app, client, _executor, document_id, map_id, source_dir = contract_api
    version_id = _generate_contract(app, document_id, map_id)
    explicit = client.get(f"/api/implementation-contracts/{version_id}").json()
    error_count = sum(issue["severity"] == "error" for issue in explicit["issues"])

    with app.state.session_factory.begin() as session:
        for index in range(12):
            source = source_dir / f"unprocessed-{index}.txt"
            source.write_text(f"source {index}", encoding="utf-8")
            session.add(
                Document(
                    id=f"unprocessed-{index}",
                    title=f"Unprocessed {index}",
                    source_path=str(source),
                    content_hash=f"{index + 1:x}".rjust(64, "0"),
                    processed_content_hash=None,
                    file_type="txt",
                    status="discovered",
                )
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
    assert documents[document_id]["implementation_contract"] == {
        "version_id": version_id,
        "generation_status": explicit["status"],
        "readiness": explicit["readiness"],
        "is_current": True,
        "is_stale": False,
        "blocker_count": error_count,
        "reviewed_count": 0,
        "total_reviewable_count": len(explicit["items"]),
    }
    assert documents["unprocessed-0"]["implementation_contract"] is None
    assert select_count <= 14

    first_item = explicit["items"][0]
    reviewed = client.patch(
        f"/api/implementation-contract-items/{first_item['id']}/resolution",
        json={
            "request_id": "library-review-1",
            "status": "confirmed",
            "based_on_item_signature": first_item["item_signature"],
        },
    )
    assert reviewed.status_code == 200
    refreshed = {item["id"]: item for item in client.get("/api/documents").json()}
    assert refreshed[document_id]["implementation_contract"]["reviewed_count"] == 1


def test_export_route_returns_fresh_typed_downloads_and_strict_options(contract_api):
    app, client, _executor, document_id, map_id, _source_dir = contract_api
    version_id = _generate_contract(app, document_id, map_id)

    json_response = client.get(
        f"/api/implementation-contracts/{version_id}/export",
        params={"format": "json", "language": "bilingual"},
    )
    markdown_response = client.get(
        f"/api/implementation-contracts/{version_id}/export",
        params={"format": "markdown", "language": "en"},
    )

    assert json_response.status_code == 200
    assert json_response.headers["content-type"] == "application/json"
    assert json_response.headers["content-disposition"].endswith(
        f'implementation-contract-{version_id}.json"'
    )
    assert json_response.json()["contract_version_id"] == version_id
    assert json_response.json()["readiness_marker"] == "NOT IMPLEMENTATION READY"
    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert markdown_response.text.startswith("# NOT IMPLEMENTATION READY\n")

    assert (
        client.get(
            f"/api/implementation-contracts/{version_id}/export",
            params={"format": "python", "language": "en"},
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/implementation-contracts/{version_id}/export",
            params={"format": "json", "language": "fr"},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/implementation-contracts/missing/export",
            params={"format": "json", "language": "en"},
        ).status_code
        == 404
    )
