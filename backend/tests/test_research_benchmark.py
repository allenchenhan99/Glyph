from pathlib import Path

from fastapi.testclient import TestClient
from support import process_and_wait

from glyph.main import create_app
from glyph.models import Block
from glyph.research_ai import CORE_NODE_GROUPS, MockResearchMapProvider
from glyph.research_maps import ResearchMapService, load_research_map

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "empirical_asset_pricing.txt"


class CountingMockProvider(MockResearchMapProvider):
    def __init__(self) -> None:
        self.extraction_calls = 0
        self.synthesis_calls = 0

    def extract_candidates(self, blocks):
        self.extraction_calls += 1
        return super().extract_candidates(blocks)

    def synthesize_nodes(self, evidence):
        self.synthesis_calls += 1
        return super().synthesize_nodes(evidence)


def test_empirical_asset_pricing_benchmark_is_complete_verifiable_and_deterministic(
    tmp_path, monkeypatch
):
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    source = book_dir / "empirical-asset-pricing.pdf"
    source.write_text(FIXTURE_PATH.read_text())
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book_dir))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_OCR_MODE", "mock")
    monkeypatch.setenv("GLYPH_AI_MODE", "mock")
    app = create_app()
    client = TestClient(app)
    document_id = client.get("/api/documents").json()[0]["id"]

    processing = process_and_wait(client, document_id)

    assert processing["status"] == "completed"

    provider = CountingMockProvider()
    with app.state.session_factory.begin() as session:
        first_version = ResearchMapService(session, provider).generate(document_id)
        first = load_research_map(session, first_version.id)
    with app.state.session_factory.begin() as session:
        second_version = ResearchMapService(session, provider).generate(document_id)
        second = load_research_map(session, second_version.id)

    represented_types = {node.node_type for node in first.nodes}
    assert all(
        represented_types.intersection(allowed_types)
        for allowed_types in CORE_NODE_GROUPS.values()
    )
    assert {issue.code for issue in first.issues} == {"not_reported"}
    transaction_cost = next(
        node for node in first.nodes if node.node_type == "transaction_cost"
    )
    assert transaction_cost.evidence_quality == "not_reported"
    assert "does not report" in transaction_cost.claim_text

    primary_result = next(
        node for node in first.nodes if node.node_type == "primary_result"
    )
    statistical_evidence = next(
        node for node in first.nodes if node.node_type == "statistical_evidence"
    )
    assert primary_result.evidence
    assert statistical_evidence.evidence
    assert "t-statistic" in statistical_evidence.claim_text

    with app.state.session_factory() as session:
        for node in first.nodes:
            for evidence in node.evidence:
                block = session.get(Block, evidence.block_id)
                assert block is not None
                assert (
                    block.source_text[evidence.quote_start : evidence.quote_end]
                    == evidence.quote_text
                )

    assert normalized_map(first) == normalized_map(second)
    assert provider.extraction_calls == 2
    assert provider.synthesis_calls == 2
    assert (
        len(first.nodes)
        <= len(client.get(f"/api/documents/{document_id}/reader").json()["blocks"]) * 2
    )


def normalized_map(map_view):
    return [
        (
            node.node_key,
            node.node_type,
            node.claim_text,
            node.provenance,
            node.evidence_quality,
            node.node_signature,
            [
                (
                    evidence.block_id,
                    evidence.quote_start,
                    evidence.quote_end,
                    evidence.quote_text,
                    evidence.source_quote_hash,
                    evidence.relation,
                    evidence.locator_type,
                )
                for evidence in node.evidence
            ],
        )
        for node in map_view.nodes
    ]
