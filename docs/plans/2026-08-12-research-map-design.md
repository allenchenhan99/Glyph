# Glyph Research Map Design

## Status

Approved for implementation on 2026-08-12. This design follows the reliability baseline merged in PR #1 and defines Glyph's first differentiated product milestone.

## Product thesis

Glyph is a verifiable bilingual research environment for Chinese-speaking quantitative finance, econometrics, and statistics researchers. The first benchmark is empirical asset-pricing and quantitative-strategy papers.

The first product promise is measurable:

> Within ten minutes of uploading an English quantitative paper, a reader can correctly identify its research question, data, signal, method, main result, and limitations, and open the original evidence for every conclusion immediately.

Research Map is the default document view. The aligned bilingual Reader remains the evidence-reading surface. A formula and derivation workspace follows this milestone; cross-paper research graphs follow only after single-paper extraction is trustworthy.

## Product boundaries

### In scope

- Evidence-first research maps for empirical asset-pricing and quantitative-strategy papers.
- Six core guided-review categories: research question, data/sample, signal definition, empirical method, primary result, and limitations.
- A controlled quantitative-finance ontology for detailed nodes.
- Exact evidence anchors into persisted Reader blocks.
- Explicit author statement, AI synthesis, and human-created provenance.
- Human confirmation, questioning, and correction without overwriting the AI draft.
- Immutable map versions, active-version selection, source staleness, and exact review carry-forward.
- A ten-minute guided review, structured map, evidence inspector, and Reader deep link.
- Local CLI providers and a deterministic mock provider behind provider-neutral interfaces.
- Persistent generation jobs with progress and restart recovery for the supported single-process local deployment.

### Out of scope

- Generic document chat.
- Formula derivation and symbolic dependency analysis.
- Cross-paper search, comparison, or knowledge graphs.
- Collaborative editing, sharing, accounts, or cloud sync.
- Investment recommendations or automated strategy generation.
- Claims that Glyph independently proves a paper true or false.
- Full mobile editing.
- Building Glyph Cloud in this milestone.

## Experience design

### Library

Each document row adds map availability, generation stage, verification progress, and evidence-gap count. `Open Research Map` is primary and `Open Full Reader` remains secondary. The library does not expose a chat prompt.

### Workspace

The desktop workspace has three coordinated regions:

1. A left map outline with ontology categories and verification progress.
2. A central guided review or structured node list.
3. A right Evidence Inspector with verbatim English, aligned Traditional Chinese, source locator, provenance, and review actions.

Map and Reader share the selected block. Opening evidence in Reader must focus the corresponding persisted block, and returning to Map restores the selected research node.

### Guided review

`Start 10-minute review` walks through five stages:

1. Research question.
2. Data and sample.
3. Signal and portfolio construction.
4. Method and main result.
5. Limitations and missing implementation evidence.

Every stage shows one concise conclusion and its strongest evidence. A paper may have multiple detailed nodes, but the guided path remains intentionally bounded.

### Visual language

Glyph uses an understated research-workbench aesthetic: warm paper surfaces, charcoal text, deep-blue evidence links, amber for unreviewed or insufficient evidence, ink green for human confirmation, and dark red only for conflicts, stale evidence, or errors. Serif typography is reserved for source reading; sans-serif is used for controls and structured fields. Motion is limited to expansion, evidence focus, and state transitions. All actions are keyboard reachable and have visible focus.

## Controlled ontology

The map supports these node types in schema version 1:

- `research_question`
- `author_claim`
- `economic_mechanism`
- `hypothesis`
- `data_and_sample`
- `data_source`
- `sample_filter`
- `signal_definition`
- `variable_definition`
- `portfolio_construction`
- `rebalancing_rule`
- `empirical_method`
- `benchmark_model`
- `identification_strategy`
- `primary_result`
- `statistical_evidence`
- `economic_magnitude`
- `turnover`
- `transaction_cost`
- `robustness_test`
- `subsample_result`
- `alternative_explanation`
- `implementation_constraint`
- `limitations`
- `unanswered_question`

Providers cannot invent types. Unknown values fail schema validation. Multiple nodes of one type are allowed and receive deterministic per-version keys such as `robustness_test.1`.

## Persistent model

### `research_map_versions`

- `id`
- `document_id`
- `previous_version_id`
- `source_content_hash`
- `schema_version`
- `provider`
- `model_name`
- `status`: `building`, `complete`, `partial`, or `failed`
- `is_active`
- `created_at`, `completed_at`

Map versions are immutable after completion except for the active flag. A newly generated map cannot replace the active version until persistence and audits finish.

### `research_nodes`

- `id`, `map_version_id`, optional `parent_node_id`
- `node_key`, `node_type`, `title`
- `claim_text`, `explanation`
- `provenance`: `author_explicit`, `ai_synthesis`, or `human_created`
- `evidence_quality`: `direct`, `synthesized`, `insufficient`, `conflicted`, or `not_reported`
- `display_order`
- `node_signature`

`node_signature` hashes the normalized claim, ontology type, and sorted evidence hashes. It is the only basis for automatically carrying a human review to another version.

### `research_evidence`

- `id`, `node_id`, `block_id`
- `locator_type`: `text_span`, `equation`, `table`, `figure`, or `caption`
- `quote_text`, `quote_start`, `quote_end`, `source_quote_hash`
- `relation`: `supports`, `qualifies`, `contradicts`, or `context`
- optional `source_label`

Page and document identity are derived from the block. Provider-supplied page numbers are never trusted.

### `research_node_reviews`

- `id`, `node_id`, `revision_number`, optional `supersedes_review_id`
- `status`: `confirmed`, `questioned`, or `corrected`
- optional `corrected_claim_text`, `review_note`
- `based_on_map_version_id`, `based_on_node_signature`
- `reviewed_at`

The AI draft is immutable and reviews are append-only. The effective UI value is the draft plus the latest review revision. Corrected content is required only for `corrected`; it is forbidden for `confirmed`. Earlier confirmations, questions, and corrections remain available as review history.

### `research_map_issues`

- `id`, `map_version_id`, optional `node_id`
- `code`, `severity`, `message`

Issues represent missing core categories, unsupported claims, conflicting evidence, or missing quantitative details. They make partial completion explainable.

### `research_map_jobs`

- `id`, `document_id`, optional `map_version_id`
- `status`: `queued`, `running`, `completed`, or `failed`
- `stage`, `progress`, `error_message`
- `attempt_count`, `lease_token`
- `created_at`, `updated_at`

Only one active map job per document is allowed in the local process. Startup returns interrupted `running` jobs to `queued`, with a bounded attempt count.

## Evidence contract

An AI claim cannot be a normal supported node without validated evidence. For every candidate anchor, the backend verifies:

1. The block exists and belongs to the target document and current processed source hash.
2. `quote_start` and `quote_end` select `quote_text` exactly.
3. If offsets are omitted, the quote occurs exactly once and the backend derives them.
4. The quote is non-empty and within configured length bounds.
5. Duplicate anchors are removed by block, span, relation, and locator type.
6. HTML, absolute paths, URLs, unknown ontology values, and unknown relations are rejected.

`author_explicit` requires at least one supporting direct anchor. `ai_synthesis` requires at least two accepted anchors unless the node is explicitly `insufficient` or `not_reported`. `not_reported` is semantically different from zero or not applicable.

## Generation pipeline

1. **Precondition:** a current completed Reader snapshot must exist. A stale source must be reprocessed before generating a current map.
2. **Metadata extraction:** identify bibliographic metadata only when supported by document blocks.
3. **Candidate extraction:** provider returns node type, block ID, exact quote, optional offset, locator, and relation. It cannot write final conclusions yet.
4. **Deterministic validation:** the backend validates and canonicalizes every anchor.
5. **Node synthesis:** the provider receives only accepted evidence IDs and quotes and produces claims, explanations, provenance, and referenced evidence IDs.
6. **Deterministic audit:** enforce ontology, evidence, core-category, quantitative-detail, and completeness rules.
7. **Atomic persistence:** store the immutable version, nodes, anchors, and issues in one savepoint.
8. **Activation:** mark the finished version active while deactivating the previous one in the same transaction.
9. **Human review:** reviews are persisted separately and never sent back as if they were author text.

The mock provider deterministically recognizes fixture headings and quantitative fields. CLI providers use strict JSON schemas, bounded batch sizes, existing timeout rules, no network/tool access supplied by Glyph, and document-content delimiters that explicitly treat the paper as untrusted data.

## Versioning and review carry-forward

Generating a new map never mutates an old version. Diffs use `node_key`, node signatures, and evidence hashes to classify nodes as `unchanged`, `claim_changed`, `evidence_changed`, `added`, or `removed`.

A review can be carried forward only when the node signature is byte-for-byte identical. Otherwise the previous review stays visible in history and the new node becomes unreviewed. Source changes immediately make the active map stale because its `source_content_hash` differs from the document's current `content_hash`.

## Execution and recovery

The HTTP route creates a persistent queued job and returns `202`. A provider-neutral `ResearchMapService` performs the pipeline. A local single-worker executor runs jobs outside the request, records stage progress, and uses a process-local per-document coordinator plus database state. On startup, interrupted jobs are requeued once; repeated interruption becomes a safe failed job. A failure never changes the previous active map.

This is deliberately not a distributed queue. The service and storage contracts permit a future Glyph Cloud worker to replace the local executor without changing domain rules or frontend payloads.

## Local-first and future cloud boundary

The open-source core owns ontology, evidence validation, map/version/review semantics, migrations, APIs, mock provider, CLI provider, and local executor. It never depends on an account or hosted service.

A future optional Glyph Cloud may supply authentication, object storage, managed OCR/models, durable distributed queues, sync, and collaboration. It must consume the same canonical Research Map API and may not weaken evidence invariants. Local users can remain fully local, and export formats must not depend on the cloud.

## API

- `POST /api/documents/{document_id}/research-map` → `202 ResearchMapJobOut`
- `GET /api/research-map-jobs/{job_id}`
- `GET /api/documents/{document_id}/research-map` → active effective map
- `GET /api/documents/{document_id}/research-map/versions`
- `GET /api/research-maps/{version_id}`
- `GET /api/research-maps/{version_id}/diff?against={other_version_id}`
- `PATCH /api/research-nodes/{node_id}/review`
- `POST /api/research-maps/{version_id}/activate`

The Reader API remains compatible. All request and response bodies use explicit Pydantic and TypeScript discriminated unions rather than free-form dictionaries.

## Error handling

- `404`: document, map, node, block, or job does not exist.
- `409`: source missing/stale, Reader unavailable, duplicate active job, invalid activation, or review based on an obsolete signature.
- `422`: invalid ontology, review transition, anchor, or payload.
- Map-provider and internal persistence errors are recorded as safe failed jobs; server logs retain tracebacks.
- Partial maps expose structured issues and never appear complete.
- Previous active maps and reviews remain readable after every generation failure.

## Testing and quality

TDD is required. Backend tests cover migrations, anchor validation, provider contracts, atomic generation, background job recovery, completeness audits, version diff, review overlays, stale behavior, and API errors. Frontend tests cover Library map state, guided review, inspector evidence, provenance, review actions, partial/stale warnings, Map/Reader navigation, keyboard access, and failed jobs.

All existing backend and frontend gates remain mandatory. Final acceptance adds a browser smoke test with a synthetic empirical-finance paper: generate a map, inspect evidence, confirm and correct nodes, restart, mutate the source, regenerate, observe the diff, and prove the correction was not silently overwritten.

## Product measurement

The local product records no telemetry by default. The benchmark harness measures generation time, six-category coverage, valid-anchor rate, claim correction rate, evidence-open actions, and answers to a fixed comprehension rubric. Any future opt-in product analytics must be separate from document contents and disabled by default in the open-source build.

## Rollout sequence

1. Domain schema and migrations.
2. Evidence validation and deterministic mock map.
3. Persistent jobs, atomic generation, and API resources.
4. Review overlays, versions, diffs, and freshness.
5. CLI evidence extraction and synthesis.
6. Research Map workspace and guided review.
7. Reader linking, accessibility, documentation, benchmark, and smoke validation.
