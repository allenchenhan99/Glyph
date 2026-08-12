# Glyph Implementation Contract Design

## Status

Approved for planning on 2026-08-12. This design is a stacked milestone on top of the Research Map work in PR #7. It defines Glyph's next differentiated product capability; implementation starts only after the detailed plan is separately approved.

## Product strategy

Glyph serves Chinese-speaking quantitative-finance self-learners and job seekers first. Academic researchers and institutional quant teams remain credible later segments, but they do not control this milestone's product decisions.

The market already has strong products for grounded document questions and summaries, literature search and extraction, curated strategy discovery, and backtest infrastructure. The open product gap is the transition between understanding a paper and implementing it faithfully:

> Turn one quantitative paper into an auditable implementation contract without silently inventing missing assumptions.

Implementation Contract follows Research Map in the product sequence:

1. Research Map: understand and verify what the paper says.
2. Implementation Contract: specify exactly what must be implemented and expose what the paper does not say.
3. Interview Defense: practice defending the research and implementation choices.
4. Reproduction Lab: execute and compare an implementation with the reported result.

Two alternatives were considered for this milestone. Interview Defense offers faster engagement but depends on a reliable structured interpretation. Reproduction Lab offers the strongest eventual proof but prematurely expands Glyph into data acquisition and execution infrastructure. Implementation Contract is the smallest step that compounds the evidence system already built while producing a differentiated, exportable artifact.

## Product promise

Within fifteen minutes after a Research Map is available, a user can produce a contract that a human or coding agent can implement without guessing which values came from the paper, which were derived, which were chosen by the user, and which remain missing.

Every contract item has exactly one origin:

- `author_explicit`: stated by the paper and backed by direct evidence.
- `derived`: inferred from multiple paper passages with a visible rationale.
- `human_decision`: supplied or changed by the user with a required reason.
- `missing`: unresolved and never replaced by an invisible default.

The critical promise is stronger than generic paper summarization: Glyph never silently fills an implementation gap.

## Product boundaries

### In scope

- Generate a contract from an immutable Research Map version and its Reader source snapshot.
- Cover the thesis, required data, sample and universe, signal and temporal rules, portfolio construction, evaluation, frictions, biases, risks, and open decisions.
- Inspect exact source evidence and derivation chains for every non-human value.
- Let a human confirm, correct, decide, question, or explicitly mark a field not applicable without mutating the AI draft.
- Maintain immutable versions, freshness, deterministic diffs, and exact-signature-only carry-forward.
- Export typed JSON and readable Markdown, including unresolved blockers and implementation instructions.
- Provide an implementation checklist for humans and coding agents.
- Support the deterministic mock provider and existing local CLI provider boundary.

### Out of scope

- Downloading or licensing financial datasets.
- Generating a complete backtest implementation.
- Executing backtests or comparing reproduced returns.
- Investment advice, portfolio recommendations, or a claim that a strategy is profitable.
- Cross-paper synthesis or comparison.
- Interview Defense and Reproduction Lab experiences.
- General symbolic derivation of every formula.
- Collaboration, accounts, hosted sync, or a required Glyph Cloud service.

## Contract schema

A contract contains eight fixed sections:

1. `thesis`
2. `data_requirements`
3. `universe_and_sample`
4. `signal_and_timing`
5. `portfolio_construction`
6. `evaluation`
7. `frictions_and_risks`
8. `open_decisions`

Sections contain repeatable, controlled item types rather than arbitrary keys. Schema version 1 includes at least:

- `required_dataset`
- `required_field`
- `data_frequency`
- `availability_lag`
- `sample_period`
- `universe_filter`
- `sample_filter`
- `signal_formula`
- `signal_direction`
- `formation_date`
- `lookback_window`
- `weighting_rule`
- `rebalance_frequency`
- `holding_period`
- `long_short_definition`
- `benchmark_model`
- `evaluation_metric`
- `statistical_test`
- `transaction_cost`
- `turnover_assumption`
- `survivorship_risk`
- `lookahead_risk`
- `implementation_constraint`

Unknown sections, item types, origin values, and readiness values fail validation. Providers cannot extend the contract with unreviewed vocabulary.

Each item stores a stable key, controlled type and section, structured draft value, origin, rationale, blocking status, optionality, and deterministic item signature. The effective value is the immutable draft plus the latest append-only human resolution.

## Persistent model

### `implementation_contract_versions`

- `id`, `document_id`, `research_map_version_id`, `previous_version_id`
- `source_content_hash`, `research_map_signature`
- `schema_version`, `provider`, `model_name`
- generation `status`: `building`, `complete`, `partial`, or `failed`
- readiness `readiness`: `blocked`, `review_needed`, or `implementation_ready`
- `is_active`, `created_at`, `completed_at`

Generation status and readiness are deliberately independent. A successfully generated contract may remain blocked. A provider cannot set readiness.

### `implementation_contract_items`

- `id`, `contract_version_id`
- `item_key`, `section`, `item_type`
- typed `draft_value`
- `origin`, `rationale`
- `is_blocking`, `is_optional`, `display_order`
- `item_signature`

`item_signature` hashes the normalized type, draft value, origin, rationale, and sorted evidence hashes. It is the only basis for automatic resolution carry-forward.

### `implementation_contract_evidence`

- `id`, `item_id`, `block_id`
- optional `research_node_id`
- `locator_type`, `quote_text`, `quote_start`, `quote_end`
- `source_quote_hash`, `relation`, optional `source_label`

Evidence anchors obey the same exact Reader-block validation contract as Research Map. A contract may add implementation-specific evidence, but doing so never changes the underlying Research Map.

### `implementation_contract_resolutions`

- `id`, `item_id`, `revision_number`, optional `supersedes_resolution_id`
- `status`: `confirmed`, `corrected`, `decided`, `questioned`, or `not_applicable`
- optional typed `resolved_value`
- required `reason` for corrected, decided, and not-applicable outcomes
- `based_on_contract_version_id`, `based_on_item_signature`
- `request_id`, `resolved_at`

Resolutions are append-only. The AI draft remains immutable and earlier user decisions remain auditable.

### `implementation_contract_issues`

Issues make a partial generation or blocked readiness explainable with stable code, severity, message, optional item link, and deterministic ordering.

### `implementation_contract_jobs`

Jobs persist their document, optional version, lifecycle status, stage, progress, safe error, attempt count, lease token, and timestamps. Only one active contract-generation job per document is accepted by the supported local process.

## Generation pipeline

1. **Load context:** require a current completed Reader snapshot and an eligible immutable Research Map version for the same document and source hash.
2. **Extract requirements:** ask the provider for typed candidates and exact evidence references.
3. **Validate evidence:** prove Reader-block ownership, exact spans, evidence relations, and source freshness.
4. **Synthesize contract:** create typed items only from accepted evidence, while representing unresolved fields as `missing`.
5. **Audit readiness:** apply deterministic invariants, temporal-consistency checks, and blocker rules outside the provider.
6. **Persist and activate:** store the immutable version, items, evidence, and issues atomically; activate only after the audit completes.
7. **Resolve and export:** apply append-only human overlays and re-run readiness before every export.

A failure at any generation stage preserves the previous active contract. A partial contract is persistable and inspectable, but cannot disguise unresolved blockers.

## Deterministic readiness contract

`implementation_ready` is allowed only when all of the following hold:

- Every blocking item has a valid effective value or an explicit, valid not-applicable resolution.
- Every effective value is backed by accepted source evidence or an auditable human resolution.
- Every `author_explicit` item has at least one direct supporting anchor.
- Every `derived` item has at least two supporting anchors and a non-empty rationale.
- Every `human_decision` has a typed value and reason.
- Every `missing` item remains visibly unresolved; no fallback is inserted by a provider, service, UI, or exporter.
- Formation, availability lag, rebalance, and holding-period fields are temporally consistent and do not use future-unavailable information.
- Missing transaction costs remain a blocker unless the user explicitly chooses a gross replication or supplies a cost model with a reason.
- Evaluation metrics, statistical tests, and benchmark models match the result the contract claims to reproduce.
- All signatures and source hashes can reconstruct the audit decision.

The audit emits stable issue codes. `blocked` means one or more implementation blockers remain. `review_needed` means the contract is structurally sufficient but still requires explicit user review. `implementation_ready` means the deterministic rules pass; it does not mean the strategy is correct or profitable.

## Versioning, freshness, and carry-forward

Generating a new contract never mutates an old one. A contract is stale when the document source hash or selected Research Map signature no longer matches its inputs.

Version diffs classify items as `unchanged`, `value_changed`, `origin_changed`, `evidence_changed`, `added`, or `removed`. Human resolutions carry forward only when the item signature is byte-for-byte identical. Otherwise the previous decision remains in history and the new item requires review.

Activating a historical version is allowed only when it belongs to the document and remains internally valid. Activation does not make a stale contract current.

## Workbench experience

### Entry points

The Research Map adds `Build Implementation Contract`. The Library displays contract generation state, readiness, blocker count, and staleness. A user can resume an existing review or build a new version from the selected Research Map.

### Three-column workspace

1. The left column shows the fixed contract outline, completion state, and blocker count by section.
2. The center column runs a bounded fifteen-minute guided review and also exposes a structured item list.
3. The right Evidence & Decision Inspector shows verbatim evidence, translated Reader context, origin, derivation rationale, effective value, history, and resolution controls.

Selection is shared among Contract, Research Map, and Reader. Evidence deep links focus the exact persisted block; returning restores the selected contract item.

### Guided review

The review contains six steps:

1. Data availability.
2. Universe and sample.
3. Signal and timing.
4. Portfolio construction.
5. Evaluation and frictions.
6. Resolve blockers and export.

Every item visibly separates AI draft from effective value and labels its origin, blocker state, evidence, and derivation chain. A missing blocker offers only explicit actions: leave blocked, make a human decision with a reason, mark not applicable with a reason, or return to the Reader. There is no accept-default action.

The primary UI language is Traditional Chinese, schema keys and technical terms remain in English, and verbatim English evidence is preserved. Exports may be bilingual or English according to an explicit option.

### Export behavior

Exports are deterministic Markdown and typed JSON. If blockers remain, the first line of Markdown and the top-level JSON readiness state say `NOT IMPLEMENTATION READY`. Export does not imply approval.

Coding-agent instructions require the consumer to:

- never guess a missing value;
- stop or request input when a blocker remains;
- preserve temporal availability and avoid look-ahead;
- implement validation and tests before strategy logic;
- record any choice not present in the source as a new human decision.

## API contract

- `POST /api/documents/{document_id}/implementation-contract` creates a persistent job and returns `202`.
- `GET /api/implementation-contract-jobs/{job_id}` returns lifecycle state and stage.
- `GET /api/documents/{document_id}/implementation-contract` returns the active effective contract.
- `GET /api/documents/{document_id}/implementation-contract/versions` lists immutable versions.
- `GET /api/implementation-contracts/{version_id}` returns one effective version.
- `GET /api/implementation-contracts/{version_id}/diff?against={other_version_id}` returns a deterministic diff.
- `PATCH /api/implementation-contract-items/{item_id}/resolution` appends a resolution with optimistic `request_id` handling.
- `POST /api/implementation-contracts/{version_id}/activate` activates an eligible version.
- `GET /api/implementation-contracts/{version_id}/export?format=json|markdown&language=en|zh-TW|bilingual` returns a freshly audited export.

All payloads use explicit Pydantic schemas and TypeScript runtime guards. Free-form dictionaries are confined to versioned typed-value schemas; unknown keys are rejected.

## Jobs, recovery, and errors

Generation stages are `load_context`, `extract_requirements`, `validate_evidence`, `synthesize_contract`, `audit_readiness`, and `persist_and_activate`. Startup requeues interrupted jobs once, then safely fails repeated interruptions. Job progress is monotonic and terminal jobs never resume.

- `404`: document, map, contract, item, block, or job does not exist.
- `409`: stale or missing input, duplicate active job, invalid activation, obsolete signature, or resolution request conflict.
- `422`: invalid vocabulary, typed value, evidence, transition, reason, or export option.

Errors returned to clients contain safe messages. Provider output and persistence tracebacks remain in local logs. A partial result is never reported as a failed transport request, and a failed generation never replaces the previous active version.

## Security and provider boundary

Paper content is untrusted data. CLI providers receive delimited content, strict JSON schemas, bounded batches, existing timeouts, and no Glyph-provided network or tool access. Document and version identity are always derived by the backend, never accepted from provider output.

The backend rejects absolute paths, URLs, HTML, unknown vocabulary, malformed typed values, cross-document IDs, and evidence spans that are not exact. Generated formulas and code-like strings are stored and exported as data; Glyph never executes them in this milestone.

## Testing and benchmark

TDD is mandatory. Backend coverage includes migrations, controlled vocabulary, typed values, exact evidence, derived and missing invariants, temporal and look-ahead rules, blockers and readiness, atomic activation, preservation of old versions, stale behavior, diff and exact carry-forward, job recovery, deterministic exports, conflicts, and bounded provider queries.

Frontend coverage includes the six-step review, all four origin states, absence of auto-defaults, reason-required decisions, pending-resolution locking and late-response isolation, evidence deep links, blocker/readiness state, stale versions, diffs, export warnings, keyboard access, screen-reader semantics, and responsive layout.

The benchmark corpus contains at least three original synthetic papers with gold contracts:

1. A monthly accounting signal with an explicit reporting lag.
2. A daily price signal with rebalance and turnover rules.
3. A cross-market long-short strategy that intentionally omits transaction costs and weighting.

Non-negotiable benchmark gates are:

- Unsupported silent defaults: `0%`.
- Missing blocking-field detection: `100%`.
- False `implementation_ready`: `0`.
- Evidence coverage for every non-human effective value: `100%`.
- Exported JSON schema validity: `100%`.
- Deterministic mock diff across identical runs: `0` changes.
- A failed generation always preserves the prior active contract.

No user-document telemetry is enabled by default.

## Rollout sequence

1. Schema, migration, controlled vocabulary, and typed values.
2. Exact evidence validation, temporal checks, and deterministic readiness audit.
3. Mock and CLI provider contracts, service orchestration, and atomic persistence.
4. Persistent jobs, APIs, version diff, resolution overlays, and deterministic export.
5. Local CLI commands.
6. Library entry points and three-column contract workspace.
7. Guided review, inspector, and Contract–Map–Reader deep links.
8. Gold benchmarks, documentation, security review, and browser acceptance.

The milestone is complete only when all existing backend and frontend gates remain green, all three gold benchmarks pass, the full browser scenario succeeds, migration and recovery guidance is documented, and an independent code review finds no unresolved critical or important issues. Only then is the branch pushed and a pull request prepared for review.
