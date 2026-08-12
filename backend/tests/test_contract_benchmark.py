from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from glyph.contract_ai import (
    ContractInputBlock,
    MockImplementationContractProvider,
    validate_extracted_requirements,
    validate_synthesized_contract,
)
from glyph.contract_audit import EffectiveContractItem, audit_contract
from glyph.contract_domain import (
    CONTRACT_SCHEMA_VERSION,
    ContractItemDraft,
    ContractReadiness,
    decode_contract_value,
    encode_contract_value,
    validate_contract_item_type,
    validate_contract_origin,
    validate_contract_section,
    validate_readiness,
)
from glyph.contract_evidence import AcceptedContractEvidence, ContractEvidenceContext
from glyph.models import Base, Block, Document, ResearchMapVersion
from glyph.research_domain import validate_evidence_relation, validate_locator_type

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "contracts"
TOP_LEVEL_KEYS = {
    "schema_version",
    "paper_id",
    "source_file",
    "expected_readiness",
    "expected_missing_blockers",
    "items",
}
ITEM_KEYS = {
    "item_key",
    "section",
    "item_type",
    "origin",
    "value",
    "rationale",
    "is_blocking",
    "is_optional",
    "display_order",
    "evidence",
}
EVIDENCE_KEYS = {
    "quote_start",
    "quote_end",
    "quote_text",
    "relation",
    "locator_type",
}


def _gold_paths() -> tuple[Path, ...]:
    return tuple(sorted(FIXTURE_DIRECTORY.glob("*.gold.json")))


def _object(value: object, field_name: str) -> dict[str, object]:
    assert isinstance(value, dict), f"{field_name} must be an object"
    assert all(isinstance(key, str) for key in value), (
        f"{field_name} keys must be strings"
    )
    return cast(dict[str, object], value)


def _list(value: object, field_name: str) -> list[object]:
    assert isinstance(value, list), f"{field_name} must be a list"
    return value


def _text(value: object, field_name: str) -> str:
    assert isinstance(value, str) and value, f"{field_name} must be non-empty text"
    return value


def _integer(value: object, field_name: str) -> int:
    assert isinstance(value, int) and not isinstance(value, bool), (
        f"{field_name} must be an integer"
    )
    return value


def _boolean(value: object, field_name: str) -> bool:
    assert isinstance(value, bool), f"{field_name} must be a boolean"
    return value


def _exact_quote_hash(
    block_id: str,
    quote_start: int,
    quote_end: int,
    quote_text: str,
) -> str:
    payload = json.dumps(
        [block_id, quote_start, quote_end, quote_text],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_gold(path: Path) -> dict[str, object]:
    payload = _object(json.loads(path.read_text(encoding="utf-8")), path.name)
    assert set(payload) == TOP_LEVEL_KEYS
    assert payload["schema_version"] == CONTRACT_SCHEMA_VERSION
    assert _text(payload["paper_id"], "paper_id") == path.name.removesuffix(
        ".gold.json"
    )
    source_file = _text(payload["source_file"], "source_file")
    assert Path(source_file).name == source_file
    assert source_file.endswith(".txt")
    validate_readiness(_text(payload["expected_readiness"], "expected_readiness"))
    expected_missing = _list(
        payload["expected_missing_blockers"], "expected_missing_blockers"
    )
    assert all(isinstance(item_key, str) and item_key for item_key in expected_missing)
    assert len(expected_missing) == len(set(expected_missing))
    assert _list(payload["items"], "items")
    return payload


def _audit_gold(payload: dict[str, object]):  # type: ignore[no-untyped-def]
    source_file = _text(payload["source_file"], "source_file")
    source_text = (FIXTURE_DIRECTORY / source_file).read_text(encoding="utf-8")
    effective_items: list[EffectiveContractItem] = []
    seen_item_keys: set[str] = set()

    for raw_item in _list(payload["items"], "items"):
        item = _object(raw_item, "item")
        assert set(item) == ITEM_KEYS
        item_key = _text(item["item_key"], "item_key")
        assert item_key not in seen_item_keys
        seen_item_keys.add(item_key)
        origin = validate_contract_origin(_text(item["origin"], "origin"))
        raw_value = item["value"]
        value = None if raw_value is None else decode_contract_value(raw_value)
        rationale_value = item["rationale"]
        assert rationale_value is None or isinstance(rationale_value, str)

        evidence: list[AcceptedContractEvidence] = []
        for raw_anchor in _list(item["evidence"], "evidence"):
            anchor = _object(raw_anchor, "evidence anchor")
            assert set(anchor) == EVIDENCE_KEYS
            quote_start = _integer(anchor["quote_start"], "quote_start")
            quote_end = _integer(anchor["quote_end"], "quote_end")
            quote_text = _text(anchor["quote_text"], "quote_text")
            assert 0 <= quote_start < quote_end <= len(source_text)
            assert source_text[quote_start:quote_end] == quote_text
            relation = validate_evidence_relation(_text(anchor["relation"], "relation"))
            locator_type = validate_locator_type(
                _text(anchor["locator_type"], "locator_type")
            )
            evidence.append(
                AcceptedContractEvidence(
                    block_id="source",
                    research_node_id=None,
                    quote_text=quote_text,
                    quote_start=quote_start,
                    quote_end=quote_end,
                    relation=relation,
                    locator_type=locator_type,
                    source_quote_hash=_exact_quote_hash(
                        "source", quote_start, quote_end, quote_text
                    ),
                )
            )

        draft = ContractItemDraft(
            item_key=item_key,
            section=validate_contract_section(_text(item["section"], "section")),
            item_type=validate_contract_item_type(
                _text(item["item_type"], "item_type")
            ),
            value=value,
            origin=origin,
            rationale=cast(str | None, rationale_value),
            is_blocking=_boolean(item["is_blocking"], "is_blocking"),
            is_optional=_boolean(item["is_optional"], "is_optional"),
            display_order=_integer(item["display_order"], "display_order"),
        )
        effective_items.append(
            EffectiveContractItem(draft=draft, evidence=tuple(evidence))
        )

    return audit_contract(effective_items)


def _generate_mock_contract(
    payload: dict[str, object],
) -> tuple[EffectiveContractItem, ...]:
    source_file = _text(payload["source_file"], "source_file")
    source_text = (FIXTURE_DIRECTORY / source_file).read_text(encoding="utf-8")
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        document = Document(
            id="benchmark-paper",
            title=_text(payload["paper_id"], "paper_id"),
            source_path=f"/books/{source_file}",
            content_hash=source_hash,
            processed_content_hash=source_hash,
            file_type="txt",
            status="completed",
        )
        map_version = ResearchMapVersion(
            id="benchmark-map",
            document_id=document.id,
            previous_version_id=None,
            source_content_hash=source_hash,
            schema_version="1",
            provider="mock",
            model_name=None,
            status="complete",
            is_active=True,
        )
        block = Block(
            id="source",
            document_id=document.id,
            source_content_hash=source_hash,
            order_index=0,
            page_number=1,
            block_type="text",
            source_text=source_text,
            translated_text=source_text,
        )
        session.add_all([document, map_version, block])
        session.commit()
        provider = MockImplementationContractProvider()
        candidates = provider.extract_requirements(
            (ContractInputBlock.from_model(block),)
        )
        accepted = validate_extracted_requirements(
            session,
            ContractEvidenceContext(
                document_id=document.id,
                source_content_hash=source_hash,
                research_map_version_id=map_version.id,
            ),
            candidates,
        )
        return validate_synthesized_contract(
            provider.synthesize_contract(accepted), accepted
        )


def _items_payload(items: tuple[EffectiveContractItem, ...]) -> list[object]:
    return [
        {
            "item_key": item.draft.item_key,
            "section": item.draft.section,
            "item_type": item.draft.item_type,
            "origin": item.draft.origin,
            "value": (
                json.loads(encode_contract_value(item.draft.value))
                if item.draft.value is not None
                else None
            ),
            "rationale": item.draft.rationale,
            "is_blocking": item.draft.is_blocking,
            "is_optional": item.draft.is_optional,
            "display_order": item.draft.display_order,
            "evidence": [
                {
                    "quote_start": anchor.quote_start,
                    "quote_end": anchor.quote_end,
                    "quote_text": anchor.quote_text,
                    "relation": anchor.relation,
                    "locator_type": anchor.locator_type,
                }
                for anchor in item.evidence
            ],
        }
        for item in items
    ]


def test_benchmark_suite_has_three_original_papers() -> None:
    paths = _gold_paths()

    assert tuple(path.name for path in paths) == (
        "cross_market_long_short.gold.json",
        "daily_price_signal.gold.json",
        "monthly_accounting_signal.gold.json",
    )


@pytest.mark.parametrize("gold_path", _gold_paths(), ids=lambda path: path.stem)
def test_gold_contracts_are_strict_exact_and_auditable(gold_path: Path) -> None:
    payload = _load_gold(gold_path)

    result = _audit_gold(payload)

    expected_readiness: ContractReadiness = validate_readiness(
        _text(payload["expected_readiness"], "expected_readiness")
    )
    assert result.readiness == expected_readiness
    actual_missing = sorted(
        issue.item_key
        for issue in result.issues
        if issue.code == "missing_blocker" and issue.item_key is not None
    )
    expected_missing = sorted(
        _text(item_key, "expected missing blocker")
        for item_key in _list(
            payload["expected_missing_blockers"], "expected_missing_blockers"
        )
    )
    assert actual_missing == expected_missing
    if expected_readiness == "blocked":
        assert result.readiness != "implementation_ready"


@pytest.mark.parametrize("gold_path", _gold_paths(), ids=lambda path: path.stem)
def test_gold_contracts_have_no_silent_defaults_or_unsupported_claims(
    gold_path: Path,
) -> None:
    payload = _load_gold(gold_path)
    items = [_object(raw_item, "item") for raw_item in _list(payload["items"], "items")]
    items_by_key = {_text(item["item_key"], "item_key"): item for item in items}

    for raw_item_key in _list(
        payload["expected_missing_blockers"], "expected_missing_blockers"
    ):
        item = items_by_key[_text(raw_item_key, "expected missing blocker")]
        assert item["origin"] == "missing"
        assert item["value"] is None
        assert item["is_blocking"] is True
        assert item["is_optional"] is False

    for item in items:
        origin = _text(item["origin"], "origin")
        evidence = _list(item["evidence"], "evidence")
        if origin in {"author_explicit", "derived"}:
            assert evidence, f"{item['item_key']} is an unsupported claim"
        if origin == "derived":
            supporting = [
                anchor
                for anchor in evidence
                if _object(anchor, "evidence anchor")["relation"] == "supports"
            ]
            assert len(supporting) >= 2
            assert isinstance(item["rationale"], str) and item["rationale"]
        if origin == "missing":
            assert item["value"] is None


@pytest.mark.parametrize("gold_path", _gold_paths(), ids=lambda path: path.stem)
def test_gold_loading_and_audit_are_deterministic(gold_path: Path) -> None:
    first_payload = _load_gold(gold_path)
    second_payload = _load_gold(gold_path)

    assert first_payload == second_payload
    assert _audit_gold(first_payload) == _audit_gold(second_payload)


@pytest.mark.parametrize("gold_path", _gold_paths(), ids=lambda path: path.stem)
def test_mock_provider_output_is_byte_equivalent_to_gold(gold_path: Path) -> None:
    payload = _load_gold(gold_path)

    actual_items = _items_payload(_generate_mock_contract(payload))
    expected_items = _list(payload["items"], "items")

    canonical = lambda value: json.dumps(  # noqa: E731 - local canonicalizer
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert canonical(actual_items) == canonical(expected_items)


@pytest.mark.parametrize("gold_path", _gold_paths(), ids=lambda path: path.stem)
def test_mock_provider_identical_runs_have_zero_changes(gold_path: Path) -> None:
    payload = _load_gold(gold_path)

    first = _generate_mock_contract(payload)
    second = _generate_mock_contract(payload)
    changed_items = sum(
        first_item != second_item
        for first_item, second_item in zip(first, second, strict=True)
    )

    assert changed_items == 0
    assert first == second
