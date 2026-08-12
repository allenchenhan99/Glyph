from glyph.research_ai import NodeDraft, ValidatedEvidence
from glyph.research_audit import audit_research_map
from glyph.research_evidence import AcceptedEvidence


def accepted(evidence_id: str, relation: str = "supports") -> ValidatedEvidence:
    return ValidatedEvidence(
        evidence_id=evidence_id,
        node_type="author_claim",
        anchor=AcceptedEvidence(
            block_id=f"block-{evidence_id}",
            quote_text=f"Source text for {evidence_id}",
            quote_start=0,
            quote_end=20 + len(evidence_id),
            relation=relation,
            locator_type="text_span",
            source_quote_hash=evidence_id.rjust(64, "0"),
        ),
    )


def node(
    node_key: str,
    node_type: str,
    evidence_ids: tuple[str, ...] = ("e1",),
    provenance: str = "author_explicit",
    evidence_quality: str = "direct",
) -> NodeDraft:
    return NodeDraft(
        node_key=node_key,
        node_type=node_type,
        title=node_type.replace("_", " ").title(),
        claim_text=f"Claim for {node_key}",
        explanation="",
        provenance=provenance,
        evidence_quality=evidence_quality,
        evidence_ids=evidence_ids,
        display_order=0,
    )


def issue_codes(result, node_key: str | None = None) -> set[str]:
    return {
        issue.code
        for issue in result.issues
        if node_key is None or issue.node_key == node_key
    }


def complete_nodes() -> tuple[NodeDraft, ...]:
    return (
        node("question.1", "author_claim"),
        node("data.1", "data_and_sample"),
        node("signal.1", "signal_definition"),
        node("method.1", "empirical_method"),
        node("result.1", "primary_result"),
        node("statistics.1", "statistical_evidence"),
        node("limitations.1", "limitations"),
    )


def test_author_explicit_claim_requires_direct_supporting_evidence():
    draft = node("question.1", "author_claim", evidence_ids=())

    result = audit_research_map((draft,), ())

    assert "unsupported_claim" in issue_codes(result, draft.node_key)
    assert result.status == "partial"


def test_author_explicit_claim_cannot_label_synthesized_evidence_as_direct():
    draft = node(
        "question.1",
        "author_claim",
        provenance="author_explicit",
        evidence_quality="synthesized",
    )

    result = audit_research_map((draft,), (accepted("e1"),))

    assert "unsupported_claim" in issue_codes(result, draft.node_key)


def test_ai_synthesis_requires_two_accepted_anchors():
    draft = node(
        "mechanism.1",
        "economic_mechanism",
        evidence_ids=("e1",),
        provenance="ai_synthesis",
        evidence_quality="synthesized",
    )

    one_anchor = audit_research_map((draft,), (accepted("e1"),))
    two_anchors = audit_research_map(
        (
            NodeDraft(
                **{
                    **draft.__dict__,
                    "evidence_ids": ("e1", "e2"),
                }
            ),
        ),
        (accepted("e1"), accepted("e2")),
    )

    assert "unsupported_claim" in issue_codes(one_anchor, draft.node_key)
    assert "unsupported_claim" not in issue_codes(two_anchors, draft.node_key)


def test_unknown_evidence_reference_is_a_structured_issue():
    draft = node("question.1", "author_claim", evidence_ids=("not-accepted",))

    result = audit_research_map((draft,), ())

    assert "unsupported_claim" in issue_codes(result, draft.node_key)


def test_not_reported_is_distinct_from_zero_and_keeps_map_partial():
    draft = node(
        "transaction_cost.1",
        "transaction_cost",
        evidence_ids=("e1",),
        evidence_quality="not_reported",
    )

    result = audit_research_map((draft,), (accepted("e1"),))

    assert "not_reported" in issue_codes(result, draft.node_key)
    assert result.status == "partial"


def test_missing_core_categories_are_named_individually():
    result = audit_research_map(
        (node("question.1", "author_claim"),),
        (accepted("e1"),),
    )

    missing = [issue for issue in result.issues if issue.code == "missing_core_node"]
    assert {issue.details["category"] for issue in missing} == {
        "data",
        "signal",
        "method",
        "result",
        "limitations",
    }


def test_primary_result_requires_statistical_evidence():
    nodes_without_statistics = tuple(
        item for item in complete_nodes() if item.node_type != "statistical_evidence"
    )

    result = audit_research_map(nodes_without_statistics, (accepted("e1"),))

    assert "missing_statistical_evidence" in issue_codes(result, "result.1")


def test_conflicted_evidence_is_explained_as_a_structured_issue():
    draft = node(
        "result.1",
        "primary_result",
        evidence_quality="conflicted",
    )

    result = audit_research_map((draft,), (accepted("e1"),))

    assert "conflicting_evidence" in issue_codes(result, draft.node_key)


def test_complete_and_partial_status_are_deterministic():
    nodes = complete_nodes()
    evidence = (accepted("e1"),)

    complete = audit_research_map(nodes, evidence)
    repeated = audit_research_map(nodes, evidence)
    partial = audit_research_map(nodes[:-1], evidence)

    assert complete.status == "complete"
    assert complete == repeated
    assert complete.issues == ()
    assert partial.status == "partial"
