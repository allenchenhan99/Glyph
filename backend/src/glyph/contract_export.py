from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.orm import Session

from glyph.contract_audit import EffectiveContractItem, audit_contract
from glyph.contract_domain import (
    CONTRACT_SECTIONS,
    ContractItemDraft,
    ContractResolutionDraft,
    ContractValue,
    encode_contract_value,
    validate_contract_item_type,
    validate_contract_origin,
    validate_contract_section,
    validate_resolution_status,
)
from glyph.contract_evidence import AcceptedContractEvidence
from glyph.implementation_contracts import (
    ContractResolutionView,
    ImplementationContractView,
    load_implementation_contract,
)
from glyph.research_domain import validate_evidence_relation, validate_locator_type

ExportFormat = Literal["json", "markdown"]
ExportLanguage = Literal["en", "zh-TW", "bilingual"]

_SECTION_LABELS = {
    "thesis": ("Thesis", "論點"),
    "data_requirements": ("Data Requirements", "資料需求"),
    "universe_and_sample": ("Universe and Sample", "投資範圍與樣本"),
    "signal_and_timing": ("Signal and Timing", "訊號與時點"),
    "portfolio_construction": ("Portfolio Construction", "投資組合建構"),
    "evaluation": ("Evaluation", "評估"),
    "frictions_and_risks": ("Frictions and Risks", "摩擦與風險"),
    "open_decisions": ("Open Decisions", "待決事項"),
}
_MARKDOWN_ESCAPE = re.compile(r"([\\`*_{}\[\]()#+.!|>-])")


@dataclass(frozen=True)
class ContractExportArtifact:
    content: bytes
    media_type: str
    filename: str


def export_implementation_contract(
    session: Session,
    version_id: str,
    export_format: ExportFormat,
    language: ExportLanguage,
) -> ContractExportArtifact:
    if export_format not in {"json", "markdown"}:
        raise ValueError("Unknown Implementation Contract export format")
    if language not in {"en", "zh-TW", "bilingual"}:
        raise ValueError("Unknown Implementation Contract export language")
    payload = build_canonical_contract_export(session, version_id, language)
    if export_format == "json":
        content = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        media_type = "application/json"
        suffix = "json"
    else:
        content = _render_markdown(payload, language).encode("utf-8")
        media_type = "text/markdown"
        suffix = "md"
    return ContractExportArtifact(
        content=content,
        media_type=media_type,
        filename=f"implementation-contract-{version_id}.{suffix}",
    )


def build_canonical_contract_export(
    session: Session,
    version_id: str,
    language: ExportLanguage,
) -> dict[str, object]:
    view = load_implementation_contract(session, version_id)
    audit = _fresh_audit(view)
    audited_by_key = {item.draft.item_key: item for item in audit.items}
    ordered_items = sorted(
        view.items,
        key=lambda item: (
            CONTRACT_SECTIONS.index(validate_contract_section(item.section)),
            item.display_order,
            item.item_key,
        ),
    )
    items: list[dict[str, object]] = []
    for item in ordered_items:
        audited = audited_by_key[item.item_key]
        items.append(
            {
                "item_id": item.id,
                "item_key": item.item_key,
                "section": item.section,
                "item_type": item.item_type,
                "draft_value": _value_payload(item.draft_value),
                "effective_value": _value_payload(audited.effective_value),
                "origin": item.origin,
                "effective_origin": audited.effective_origin,
                "rationale": item.rationale,
                "is_blocking": item.is_blocking,
                "is_optional": item.is_optional,
                "item_signature": item.item_signature,
                "evidence": [
                    _evidence_payload(anchor, language)
                    for anchor in sorted(
                        item.evidence,
                        key=lambda value: (
                            value.page_number,
                            value.block_id,
                            value.quote_start,
                            value.quote_end,
                            value.id,
                        ),
                    )
                ],
                "decision": _decision_payload(item.resolution),
                "decision_history": [
                    _decision_payload(decision)
                    for decision in sorted(
                        item.resolution_history,
                        key=lambda value: (value.revision_number, value.id),
                    )
                ],
            }
        )
    readiness_marker = (
        "IMPLEMENTATION READY"
        if audit.readiness == "implementation_ready"
        else "NOT IMPLEMENTATION READY"
    )
    return {
        "export_schema_version": "1",
        "contract_schema_version": view.schema_version,
        "contract_version_id": view.id,
        "document_id": view.document_id,
        "research_map_version_id": view.research_map_version_id,
        "source_content_hash": view.source_content_hash,
        "research_map_signature": view.research_map_signature,
        "language": language,
        "generation_status": audit.generation_status,
        "readiness": audit.readiness,
        "readiness_marker": readiness_marker,
        "persisted_generation_status": view.status,
        "persisted_readiness": view.readiness,
        "is_current": view.is_current,
        "is_stale": view.is_stale,
        "items": items,
        "issues": [
            {
                "item_key": issue.item_key,
                "code": issue.code,
                "severity": issue.severity,
                "message": issue.message,
            }
            for issue in audit.issues
        ],
    }


def _fresh_audit(view: ImplementationContractView):
    effective_items: list[EffectiveContractItem] = []
    for item in view.items:
        draft = ContractItemDraft(
            item_key=item.item_key,
            section=validate_contract_section(item.section),
            item_type=validate_contract_item_type(item.item_type),
            value=item.draft_value,
            origin=validate_contract_origin(item.origin),
            rationale=item.rationale,
            is_blocking=item.is_blocking,
            is_optional=item.is_optional,
            display_order=item.display_order,
        )
        resolution = (
            ContractResolutionDraft(
                status=validate_resolution_status(item.resolution.status),
                value=item.resolution.resolved_value,
                reason=item.resolution.reason,
            )
            if item.resolution is not None
            else None
        )
        evidence = tuple(
            AcceptedContractEvidence(
                block_id=anchor.block_id,
                research_node_id=anchor.research_node_id,
                quote_text=anchor.quote_text,
                quote_start=anchor.quote_start,
                quote_end=anchor.quote_end,
                relation=validate_evidence_relation(anchor.relation),
                locator_type=validate_locator_type(anchor.locator_type),
                source_quote_hash=anchor.source_quote_hash,
                source_label=anchor.source_label,
            )
            for anchor in item.evidence
        )
        effective_items.append(
            EffectiveContractItem(
                draft=draft,
                evidence=evidence,
                resolution=resolution,
            )
        )
    return audit_contract(effective_items)


def _value_payload(value: ContractValue | None) -> object:
    return json.loads(encode_contract_value(value)) if value is not None else None


def _decision_payload(
    resolution: ContractResolutionView | None,
) -> dict[str, object] | None:
    if resolution is None:
        return None
    return {
        "id": resolution.id,
        "revision_number": resolution.revision_number,
        "supersedes_resolution_id": resolution.supersedes_resolution_id,
        "status": resolution.status,
        "resolved_value": _value_payload(resolution.resolved_value),
        "reason": resolution.reason,
        "based_on_contract_version_id": resolution.based_on_contract_version_id,
        "based_on_item_signature": resolution.based_on_item_signature,
        "request_id": resolution.request_id,
        "resolved_at": _iso_utc(resolution.resolved_at),
    }


def _evidence_payload(anchor, language: ExportLanguage) -> dict[str, object]:
    payload: dict[str, object] = {
        "block_id": anchor.block_id,
        "research_node_id": anchor.research_node_id,
        "page_number": anchor.page_number,
        "locator_type": anchor.locator_type,
        "quote_start": anchor.quote_start,
        "quote_end": anchor.quote_end,
        "source_quote_hash": anchor.source_quote_hash,
        "relation": anchor.relation,
        "source_label": anchor.source_label,
        "source_quote": anchor.quote_text,
    }
    if language in {"zh-TW", "bilingual"}:
        payload["translated_context"] = anchor.translated_text
    return payload


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _render_markdown(
    payload: dict[str, object],
    language: ExportLanguage,
) -> str:
    marker = str(payload["readiness_marker"])
    title = _label("Implementation Contract", "實作契約", language)
    lines = [
        f"# {marker}",
        "",
        f"# {title}",
        "",
        f"- {_label('Version', '版本', language)}: `{payload['contract_version_id']}`",
        f"- {_label('Readiness', '就緒狀態', language)}: `{payload['readiness']}`",
        f"- {_label('Generation status', '生成狀態', language)}: "
        f"`{payload['generation_status']}`",
        "",
    ]
    items = payload["items"]
    if not isinstance(items, list):
        raise ValueError("Canonical contract items must be a list")
    for section in CONTRACT_SECTIONS:
        section_items = [item for item in items if item.get("section") == section]
        if not section_items:
            continue
        english, chinese = _SECTION_LABELS[section]
        lines.extend([f"## {_label(english, chinese, language)}", ""])
        for item in section_items:
            lines.extend(_markdown_item(item, language))
    issues = payload["issues"]
    if not isinstance(issues, list):
        raise ValueError("Canonical contract issues must be a list")
    lines.extend([f"## {_label('Audit Issues', '稽核問題', language)}", ""])
    if not issues:
        lines.extend([f"- {_label('None', '無', language)}", ""])
    else:
        for issue in issues:
            lines.append(
                f"- `{issue['severity']}` `{issue['code']}` "
                f"{_escape_markdown(str(issue['message']))}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _markdown_item(item: dict[str, object], language: ExportLanguage) -> list[str]:
    lines = [
        f"### `{item['item_key']}` — `{item['item_type']}`",
        "",
        f"- {_label('Origin', '來源', language)}: `{item['origin']}`",
        f"- {_label('Effective origin', '有效來源', language)}: "
        f"`{item['effective_origin']}`",
        f"- {_label('Blocking', '阻擋項目', language)}: "
        f"`{str(item['is_blocking']).lower()}`",
        "",
        f"#### {_label('Draft Value', '草稿值', language)}",
        "",
        *_json_indented(item["draft_value"]),
        "",
        f"#### {_label('Effective Value', '有效值', language)}",
        "",
        *_json_indented(item["effective_value"]),
        "",
    ]
    rationale = item.get("rationale")
    if rationale is not None:
        lines.extend(
            [
                f"#### {_label('Rationale', '理由', language)}",
                "",
                _escape_markdown(str(rationale)),
                "",
            ]
        )
    lines.extend([f"#### {_label('Evidence', '證據', language)}", ""])
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        lines.extend([f"- {_label('None', '無', language)}", ""])
    else:
        for anchor in evidence:
            lines.append(
                f"- `{anchor['block_id']}:{anchor['quote_start']}-"
                f"{anchor['quote_end']}` (`{anchor['source_quote_hash']}`)"
            )
            lines.extend(_quoted_code(str(anchor["source_quote"])))
            translated = anchor.get("translated_context")
            if translated is not None:
                lines.append(f"> {_label('Translated context', '翻譯脈絡', language)}")
                lines.extend(_quoted_code(str(translated)))
            lines.append("")
    lines.extend([f"#### {_label('Decision History', '決策歷程', language)}", ""])
    history = item.get("decision_history")
    if not isinstance(history, list) or not history:
        lines.extend([f"- {_label('None', '無', language)}", ""])
    else:
        for decision in history:
            reason = decision.get("reason")
            reason_text = (
                f" — {_escape_markdown(str(reason))}" if reason is not None else ""
            )
            lines.append(
                f"- r{decision['revision_number']} `{decision['status']}`{reason_text}"
            )
        lines.append("")
    return lines


def _json_indented(value: object) -> list[str]:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    return [f"    {line}" for line in encoded.splitlines()]


def _quoted_code(value: str) -> list[str]:
    longest_run = max((len(run) for run in re.findall(r"`+", value)), default=0)
    fence = "`" * max(3, longest_run + 1)
    return [
        f"> {fence}text",
        *(f"> {line}" for line in value.splitlines()),
        f"> {fence}",
    ]


def _escape_markdown(value: str) -> str:
    return _MARKDOWN_ESCAPE.sub(r"\\\1", value.replace("\r", ""))


def _label(english: str, chinese: str, language: ExportLanguage) -> str:
    if language == "en":
        return english
    if language == "zh-TW":
        return chinese
    return f"{english} / {chinese}"
