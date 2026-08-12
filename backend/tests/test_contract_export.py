from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from glyph.contract_ai import MockImplementationContractProvider
from glyph.contract_export import export_implementation_contract
from glyph.implementation_contracts import (
    ImplementationContractService,
    append_contract_resolution,
    load_implementation_contract,
)
from glyph.models import (
    Base,
    Block,
    Document,
    ImplementationContractVersion,
    ResearchEvidence,
    ResearchMapVersion,
    ResearchNode,
)
from glyph.research_evidence import exact_quote_hash

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "contracts" / "monthly_accounting_signal.txt"
)


@pytest.fixture
def export_contract(tmp_path: Path) -> Iterator[tuple[Session, str, Path]]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    source_text = FIXTURE_PATH.read_text(encoding="utf-8").replace(
        "Data: We use Compustat annual book equity",
        "Data: We use Compustat annual book equity **untrusted-markdown**",
    )
    source_hash = hashlib.sha256(source_text.encode()).hexdigest()
    private_path = tmp_path / "private" / "paper.txt"
    document = Document(
        id="paper-export",
        title="Export paper",
        source_path=str(private_path),
        content_hash=source_hash,
        processed_content_hash=source_hash,
        file_type="txt",
        status="completed",
    )
    block = Block(
        id="export-source",
        document_id=document.id,
        source_content_hash=source_hash,
        order_index=0,
        page_number=1,
        block_type="text",
        source_text=source_text,
        translated_text=f"繁中翻譯：{source_text}",
    )
    map_version = ResearchMapVersion(
        id="map-export",
        document_id=document.id,
        source_content_hash=source_hash,
        schema_version="1",
        provider="mock",
        status="complete",
        is_active=True,
    )
    node = ResearchNode(
        id="node-export",
        map_version_id=map_version.id,
        node_key="author_claim.1",
        node_type="author_claim",
        title="Claim",
        claim_text="The source is reproducible.",
        explanation="",
        provenance="author_explicit",
        evidence_quality="direct",
        display_order=0,
        node_signature="c" * 64,
    )
    quote = source_text.splitlines()[1]
    start = source_text.index(quote)
    session.add_all(
        [
            document,
            block,
            map_version,
            node,
            ResearchEvidence(
                id="map-export-evidence",
                node_id=node.id,
                block_id=block.id,
                locator_type="text_span",
                quote_text=quote,
                quote_start=start,
                quote_end=start + len(quote),
                source_quote_hash=exact_quote_hash(
                    block.id, start, start + len(quote), quote
                ),
                relation="supports",
            ),
        ]
    )
    session.commit()
    contract = ImplementationContractService(
        session, MockImplementationContractProvider()
    ).generate(document.id, map_version.id)
    session.commit()
    try:
        yield session, contract.id, private_path
    finally:
        session.close()
        engine.dispose()


def test_json_export_is_byte_identical_canonical_and_path_safe(export_contract):
    session, version_id, private_path = export_contract

    first = export_implementation_contract(session, version_id, "json", "bilingual")
    second = export_implementation_contract(session, version_id, "json", "bilingual")

    assert first.content == second.content
    assert first.media_type == "application/json"
    assert first.filename.endswith(".json")
    payload = json.loads(first.content)
    assert payload["export_schema_version"] == "1"
    assert payload["contract_version_id"] == version_id
    assert payload["readiness_marker"] == "NOT IMPLEMENTATION READY"
    assert payload["readiness"] != "implementation_ready"
    assert [item["item_key"] for item in payload["items"]] == [
        item.item_key
        for item in load_implementation_contract(session, version_id).items
    ]
    assert payload["items"][0]["draft_value"] is not None
    assert "effective_value" in payload["items"][0]
    assert payload["items"][0]["evidence"][0]["block_id"] == "export-source"
    assert "translated_context" in payload["items"][0]["evidence"][0]
    assert str(private_path) not in first.content.decode()
    assert "source_path" not in first.content.decode()


def test_markdown_export_is_stable_quoted_and_language_aware(export_contract):
    session, version_id, _private_path = export_contract

    english = export_implementation_contract(session, version_id, "markdown", "en")
    chinese = export_implementation_contract(session, version_id, "markdown", "zh-TW")
    bilingual = export_implementation_contract(
        session, version_id, "markdown", "bilingual"
    )

    assert (
        english.content
        == export_implementation_contract(session, version_id, "markdown", "en").content
    )
    assert english.content.startswith(b"# NOT IMPLEMENTATION READY\n")
    assert b"Implementation Contract" in english.content
    assert "繁中翻譯" not in english.content.decode()
    assert "實作契約" in chinese.content.decode()
    assert "繁中翻譯" in chinese.content.decode()
    assert "Implementation Contract / 實作契約" in bilingual.content.decode()
    assert "> Data: We use Compustat annual book equity **untrusted-markdown**" in (
        bilingual.content.decode()
    )
    section_positions = [
        bilingual.content.decode().index(heading)
        for heading in (
            "## Data Requirements",
            "## Universe and Sample",
            "## Signal and Timing",
        )
    ]
    assert section_positions == sorted(section_positions)


def test_export_separates_decisions_and_preserves_append_only_history(
    export_contract,
):
    session, version_id, _private_path = export_contract
    contract = load_implementation_contract(session, version_id)
    item = contract.items[0]
    append_contract_resolution(
        session,
        item.id,
        status="confirmed",
        based_on_item_signature=item.item_signature,
        value=None,
        reason="Checked against the source.",
        request_id="export-review-1",
    )
    append_contract_resolution(
        session,
        item.id,
        status="questioned",
        based_on_item_signature=item.item_signature,
        value=None,
        reason="Needs a second reviewer.",
        request_id="export-review-2",
    )
    session.commit()

    payload = json.loads(
        export_implementation_contract(session, version_id, "json", "en").content
    )
    exported_item = next(
        value for value in payload["items"] if value["item_id"] == item.id
    )
    assert exported_item["draft_value"] == exported_item["effective_value"]
    assert [decision["status"] for decision in exported_item["decision_history"]] == [
        "confirmed",
        "questioned",
    ]
    assert exported_item["decision"]["status"] == "questioned"


def test_export_reaudits_and_refuses_persisted_false_ready_label(export_contract):
    session, version_id, _private_path = export_contract
    version = session.get(ImplementationContractVersion, version_id)
    assert version is not None
    version.readiness = "implementation_ready"
    version.status = "complete"
    session.commit()

    payload = json.loads(
        export_implementation_contract(session, version_id, "json", "en").content
    )
    markdown = export_implementation_contract(
        session, version_id, "markdown", "en"
    ).content.decode()

    assert payload["persisted_readiness"] == "implementation_ready"
    assert payload["readiness"] != "implementation_ready"
    assert payload["readiness_marker"] == "NOT IMPLEMENTATION READY"
    assert markdown.splitlines()[0] == "# NOT IMPLEMENTATION READY"
