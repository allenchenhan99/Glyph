# Glyph Implementation Contract Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an evidence-backed Implementation Contract that turns one Research Map into a typed, auditable specification for a human or coding agent without silently inventing missing assumptions.

**Architecture:** Add immutable contract versions, typed items, exact Reader evidence, append-only human resolutions, deterministic readiness auditing, and persistent generation jobs beside the existing Research Map subsystem. Keep AI providers limited to extraction and synthesis; backend rules alone decide readiness. Add a separate React contract state machine and three-column workbench, then coordinate Contract, Research Map, and Reader navigation in `App.tsx`.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, Alembic, SQLite, Pydantic, pytest, React 19, TypeScript, Vite, Vitest, Testing Library, CLI JSON providers.

---

## Preconditions and implementation rules

- Work only in the dedicated `feat/implementation-contract` worktree.
- This is a stacked branch based on `feat/research-map`; PR #7 must merge before this PR is retargeted to `main`.
- Before Task 1, run the current backend and frontend gates and record the baseline. A failure already present on the branch must be diagnosed before feature work.
- Use @superpowers:test-driven-development for every behavior change, @coding-principles and @karpathy-guidelines during implementation, @superpowers:systematic-debugging for unexpected failures, and @superpowers:verification-before-completion before any completion claim.
- Do not add data download, code generation, backtest execution, authentication, telemetry, collaboration, or a distributed queue.
- Do not let provider output, UI code, or export code set `implementation_ready`; every surface consumes one deterministic backend audit result.
- Each task ends in a focused commit after its focused tests and existing nearby tests pass.

### One-time worktree setup

Run from the worktree root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e './backend[dev]'
cd frontend && npm ci
```

Expected: the isolated Python environment and locked frontend dependencies install successfully. Do not copy `node_modules`, caches, databases, or user documents from another worktree.

### Baseline command

Run:

```bash
cd backend && ../.venv/bin/ruff check src tests && ../.venv/bin/mypy src/glyph && ../.venv/bin/pytest -q
cd ../frontend && npm test -- --run && npm run build
```

Expected: all checks pass before Task 1. Save counts in the final audit rather than changing product code.

### Task 1: Add the contract schema without risking Reader or Research Map data

**Files:**
- Create: `backend/migrations/versions/0004_implementation_contracts.py`
- Modify: `backend/src/glyph/models.py`
- Modify: `backend/tests/test_database.py`

**Step 1: Write the failing forward-migration test**

Create a revision-`0003_research_maps` database containing one document, Reader blocks, an active Research Map, nodes, evidence, and a review. Upgrade to head and assert every original row remains unchanged and these tables exist:

```python
CONTRACT_TABLES = {
    "implementation_contract_versions",
    "implementation_contract_items",
    "implementation_contract_evidence",
    "implementation_contract_resolutions",
    "implementation_contract_issues",
    "implementation_contract_jobs",
}

def test_contract_migration_preserves_reader_and_research_map(tmp_path):
    database_url, before = create_revision_0003_database(tmp_path)
    upgrade_database(settings_for(database_url))
    assert snapshot_existing_product_rows(database_url) == before
    assert CONTRACT_TABLES <= table_names(database_url)
    assert contract_row_count(database_url) == 0
```

Also assert foreign keys, unique constraints, partial unique indexes for one active contract and one queued/running job per document, and a clean empty-database upgrade.

**Step 2: Run the migration test to verify RED**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_database.py -q
```

Expected: FAIL because revision `0004_implementation_contracts` and its tables do not exist.

**Step 3: Add the six SQLAlchemy models**

Add `ImplementationContractVersion`, `ImplementationContractItem`, `ImplementationContractEvidence`, `ImplementationContractResolution`, `ImplementationContractIssue`, and `ImplementationContractJob`. Add relationships from `Document`, `ResearchMapVersion`, `ResearchNode`, and `Block` without changing existing cascade behavior.

Store typed item values as canonical JSON text in `draft_value_json` and `resolved_value_json`; parse them only through domain codecs. Required constraints include:

```python
UniqueConstraint("contract_version_id", "item_key")
UniqueConstraint("item_id", "revision_number")
UniqueConstraint("item_id", "request_id")
UniqueConstraint("item_id", "block_id", "quote_start", "quote_end", "relation")
```

Add SQLite partial unique indexes for `is_active = 1` and job status in `('queued', 'running')`. Use string columns for controlled values so migrations remain portable.

**Step 4: Add Alembic revision `0004`**

Create tables in dependency order, indexes explicitly, and a downgrade that removes only the six contract tables. Do not backfill contracts for old maps. Do not rewrite any Reader or Research Map column.

**Step 5: Run focused and full database tests**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_database.py -q
../.venv/bin/pytest tests/test_research_maps.py tests/test_reader_payload.py -q
```

Expected: all pass; existing Reader and Research Map behavior is unchanged.

**Step 6: Commit**

```bash
git add backend/migrations/versions/0004_implementation_contracts.py backend/src/glyph/models.py backend/tests/test_database.py
git commit -m "feat: add implementation contract schema"
```

### Task 2: Define controlled vocabulary and canonical typed values

**Files:**
- Create: `backend/src/glyph/contract_domain.py`
- Create: `backend/tests/test_contract_domain.py`

**Step 1: Write failing vocabulary and codec tests**

Cover all eight sections, schema-v1 item types, four origins, five resolution statuses, generation states, readiness states, issue severities, and diff classifications. Reject unknown values, non-finite numbers, empty objects, unknown keys, HTML, URLs, absolute paths, and payloads over configured depth/size limits.

Use a closed discriminated union rather than `dict[str, Any]`:

```python
@dataclass(frozen=True)
class ScalarValue:
    kind: Literal["scalar"]
    value: str | int | float | bool
    unit: str | None = None

@dataclass(frozen=True)
class FormulaValue:
    kind: Literal["formula"]
    expression: str
    variables: tuple[str, ...]

@dataclass(frozen=True)
class RuleValue:
    kind: Literal["rule"]
    operator: Literal["include", "exclude", "rank", "threshold"]
    field: str
    value: ScalarValue
```

Also define bounded `ListValue`, `RangeValue`, and `PeriodValue`. Tests must prove `encode_contract_value(decode_contract_value(payload))` is canonical and stable.

**Step 2: Verify RED**

Run: `cd backend && ../.venv/bin/pytest tests/test_contract_domain.py -q`

Expected: collection FAIL because `glyph.contract_domain` does not exist.

**Step 3: Implement immutable domain types and codecs**

Centralize:

- `CONTRACT_SCHEMA_VERSION = "1"`;
- `ContractSection`, `ContractItemType`, `ContractOrigin`;
- `ContractGenerationStatus`, `ContractReadiness`, `ResolutionStatus`;
- `ContractValue` discriminated union;
- frozen `ContractItemDraft`, `ContractResolutionDraft`, and `ContractIssueDraft`;
- canonical JSON encoding with sorted keys and compact separators;
- deterministic `item_signature()` over type, value, origin, rationale, and sorted evidence hashes.

Reject a `missing` origin with a draft value and reject every non-missing origin without one. `human_decision` is accepted only when constructing an effective overlay, never from provider draft output.

**Step 4: Run focused checks**

```bash
cd backend
../.venv/bin/pytest tests/test_contract_domain.py -q
../.venv/bin/ruff check src/glyph/contract_domain.py tests/test_contract_domain.py
../.venv/bin/mypy src/glyph/contract_domain.py
```

Expected: all pass.

**Step 5: Commit**

```bash
git add backend/src/glyph/contract_domain.py backend/tests/test_contract_domain.py
git commit -m "feat: define typed contract domain"
```

### Task 3: Reuse exact Reader evidence without weakening Research Map guarantees

**Files:**
- Create: `backend/src/glyph/contract_evidence.py`
- Create: `backend/tests/test_contract_evidence.py`
- Modify: `backend/src/glyph/research_evidence.py`

**Step 1: Write failing contract-evidence tests**

Test:

- current document/source ownership;
- exact offsets and unique quote derivation;
- optional Research Map node belongs to the chosen map and document;
- cross-document block or node rejection;
- duplicate removal;
- direct/supporting relation semantics;
- deterministic evidence hashes;
- safe rejection of paths, URLs, and HTML in labels.

```python
def test_contract_anchor_cannot_link_a_node_from_another_map(session, context):
    candidate = contract_anchor(
        block_id=context.block.id,
        research_node_id=context.other_document_node.id,
        quote_text=context.quote,
    )
    with pytest.raises(InvalidContractEvidenceError, match="same Research Map"):
        validate_contract_candidate(session, context.inputs, candidate)
```

**Step 2: Verify RED**

Run: `cd backend && ../.venv/bin/pytest tests/test_contract_evidence.py -q`

Expected: FAIL because the validator does not exist.

**Step 3: Extract only the generic exact-span primitive**

Move the existing literal quote/offset validation from `research_evidence.py` into a private reusable function or expose a narrowly typed helper. Do not change Research Map results or accepted/rejected inputs. Run existing evidence tests immediately after the refactor.

**Step 4: Implement the contract validator**

Accept a `ContractEvidenceCandidate` plus an immutable input context containing document ID, source hash, and map version ID. Derive page/document data from persistence. Return `AcceptedContractEvidence`; never trust provider-supplied identity, page number, URL, or path.

**Step 5: Run focused regression checks**

```bash
cd backend
../.venv/bin/pytest tests/test_research_evidence.py tests/test_contract_evidence.py -q
../.venv/bin/ruff check src/glyph/research_evidence.py src/glyph/contract_evidence.py tests/test_contract_evidence.py
../.venv/bin/mypy src/glyph
```

Expected: all pass and Research Map exact-anchor behavior is unchanged.

**Step 6: Commit**

```bash
git add backend/src/glyph/research_evidence.py backend/src/glyph/contract_evidence.py backend/tests/test_contract_evidence.py
git commit -m "feat: validate contract evidence anchors"
```

### Task 4: Build deterministic readiness and temporal audits first

**Files:**
- Create: `backend/src/glyph/contract_audit.py`
- Create: `backend/tests/test_contract_audit.py`

**Step 1: Write the failing readiness matrix**

Use table-driven tests for each invariant:

```python
@pytest.mark.parametrize(
    ("items", "expected_readiness", "issue_code"),
    [
        ((missing_blocker("weighting_rule"),), "blocked", "missing_blocker"),
        ((derived_with_one_anchor("signal_formula"),), "blocked", "derived_evidence_shortfall"),
        ((explicit_without_anchor("holding_period"),), "blocked", "explicit_without_evidence"),
        ((valid_but_unconfirmed_contract(),), "review_needed", "review_required"),
        ((fully_reviewed_contract(),), "implementation_ready", None),
    ],
)
def test_readiness_is_deterministic(items, expected_readiness, issue_code):
    audit = audit_contract(items)
    assert audit.readiness == expected_readiness
    assert issue_code is None or issue_code in {issue.code for issue in audit.issues}
```

Add separate tests for:

- accounting availability lag after formation date;
- look-ahead from end-of-period data used before publication;
- holding period and rebalance inconsistency;
- daily/monthly frequency mismatch;
- missing transaction costs;
- explicit gross-replication human decision;
- benchmark/metric mismatch;
- questioned items;
- optional missing items;
- evidence coverage for every non-human value;
- audit stability under input ordering.

**Step 2: Verify RED**

Run: `cd backend && ../.venv/bin/pytest tests/test_contract_audit.py -q`

Expected: FAIL because `audit_contract` does not exist.

**Step 3: Implement pure audit rules**

Create `ContractAuditResult(generation_status, readiness, issues)` and pure checks. Sort issues by `(severity, code, item_key)` and never inspect provider name. Audit effective values, but preserve draft origin and resolution provenance. A human decision resolves missing information only when it includes a typed value and non-empty reason.

Temporal checks operate on explicit `PeriodValue`/`ScalarValue` fields; do not parse natural-language prose. When fields cannot be compared structurally, emit `temporal_review_required` rather than guessing.

**Step 4: Run focused checks**

```bash
cd backend
../.venv/bin/pytest tests/test_contract_audit.py -q
../.venv/bin/ruff check src/glyph/contract_audit.py tests/test_contract_audit.py
../.venv/bin/mypy src/glyph/contract_audit.py
```

Expected: all readiness cases pass with no provider-dependent result.

**Step 5: Commit**

```bash
git add backend/src/glyph/contract_audit.py backend/tests/test_contract_audit.py
git commit -m "feat: audit contract readiness deterministically"
```

### Task 5: Establish three gold contracts before implementing providers

**Files:**
- Create: `backend/tests/fixtures/contracts/monthly_accounting_signal.txt`
- Create: `backend/tests/fixtures/contracts/daily_price_signal.txt`
- Create: `backend/tests/fixtures/contracts/cross_market_long_short.txt`
- Create: `backend/tests/fixtures/contracts/monthly_accounting_signal.gold.json`
- Create: `backend/tests/fixtures/contracts/daily_price_signal.gold.json`
- Create: `backend/tests/fixtures/contracts/cross_market_long_short.gold.json`
- Create: `backend/tests/test_contract_benchmark.py`

**Step 1: Write original synthetic papers**

Each paper must be original and compact enough for deterministic test runs. Include exact phrases for data, timing, signal, construction, evaluation, and risks. The third paper must intentionally omit transaction costs and weighting.

**Step 2: Encode versioned gold contracts**

Every gold file validates against the Task 2 codec and includes exact quote spans. The expected readiness is:

- monthly accounting: `review_needed` before confirmations;
- daily price: `review_needed` before confirmations;
- cross-market: `blocked` with at least `transaction_cost` and `weighting_rule` blockers.

**Step 3: Write a failing benchmark harness**

Assert schema validity, exact evidence, unsupported default rate `0%`, blocker recall `100%`, false-ready count `0`, non-human evidence coverage `100%`, and identical-run diff count `0`.

**Step 4: Verify RED for provider-dependent assertions**

Run: `cd backend && ../.venv/bin/pytest tests/test_contract_benchmark.py -q`

Expected: fixture/schema tests pass, provider generation tests FAIL because no mock contract provider exists.

**Step 5: Commit the benchmark contract**

```bash
git add backend/tests/fixtures/contracts backend/tests/test_contract_benchmark.py
git commit -m "test: define implementation contract benchmarks"
```

This intentional RED commit locks product acceptance before provider implementation.

### Task 6: Implement the evidence-first provider protocol and deterministic mock

**Files:**
- Create: `backend/src/glyph/contract_ai.py`
- Create: `backend/tests/test_contract_ai.py`
- Modify: `backend/tests/test_contract_benchmark.py`

**Step 1: Write provider-boundary tests**

Require two explicit phases:

```python
candidates = provider.extract_requirements(contract_input_blocks)
accepted = validate_contract_candidates(session, inputs, candidates)
draft = provider.synthesize_contract(accepted)
audit = audit_contract(to_effective_items(draft, accepted, ()))
```

Prove synthesis receives accepted evidence only, no session or unrestricted block collection. Reject referenced evidence IDs that were not accepted, duplicate item keys, unknown types, and `human_decision` output from a provider.

**Step 2: Verify RED**

Run: `cd backend && ../.venv/bin/pytest tests/test_contract_ai.py -q`

Expected: FAIL because the provider protocol does not exist.

**Step 3: Implement protocol and mock provider**

Define `ImplementationContractProvider` with `provider_name`, `model_name`, `extract_requirements()`, and `synthesize_contract()`. The deterministic mock recognizes only the synthetic fixture grammar and emits `missing` items for absent values. It must never invent common defaults such as equal weighting, next-day execution, zero costs, winsorization, delisting treatment, or a benchmark model.

**Step 4: Make the benchmark GREEN**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_contract_ai.py tests/test_contract_benchmark.py -q
```

Expected: all three gold contracts pass every non-negotiable metric.

**Step 5: Commit**

```bash
git add backend/src/glyph/contract_ai.py backend/tests/test_contract_ai.py backend/tests/test_contract_benchmark.py
git commit -m "feat: generate deterministic contract drafts"
```

### Task 7: Add the safe local CLI provider

**Files:**
- Create: `backend/src/glyph/contract_cli_ai.py`
- Create: `backend/tests/test_contract_cli_ai.py`
- Modify: `backend/src/glyph/config.py`
- Modify: `.env.example`

**Step 1: Write failing CLI contract tests**

Reuse the subprocess runner and cache safety patterns in `research_cli_ai.py`. Cover strict JSON, prompt delimiters, bounded batch size, timeout, non-zero exit, malformed JSON, unknown keys, URLs/paths/HTML, duplicate IDs, cross-batch evidence references, cache corruption, and public error redaction.

Also assert the prompt says the document is untrusted data and instructs the model to emit `missing`, never a default, when the paper is silent.

**Step 2: Verify RED**

Run: `cd backend && ../.venv/bin/pytest tests/test_contract_cli_ai.py -q`

Expected: FAIL because `CliImplementationContractProvider` does not exist.

**Step 3: Add bounded settings**

Add `contract_cli_block_batch_size` and use the existing positive-integer parser. Reuse `cli_model`, `cli_timeout_seconds`, and the configured executable mode. Add only the new environment variable to `.env.example`.

**Step 4: Implement strict extraction and synthesis adapters**

Use the existing safe CLI execution layer; do not use `shell=True`, expose tools, or grant network access. Parse with explicit Pydantic models configured with `extra="forbid"`, convert to frozen domain drafts, then run the same validator and audit as the mock provider.

**Step 5: Verify security and provider tests**

```bash
cd backend
../.venv/bin/pytest tests/test_contract_cli_ai.py tests/test_research_cli_ai.py tests/test_config.py -q
../.venv/bin/bandit -q -r src/glyph
```

Expected: all pass; existing Research Map CLI behavior remains intact.

**Step 6: Commit**

```bash
git add .env.example backend/src/glyph/config.py backend/src/glyph/contract_cli_ai.py backend/tests/test_contract_cli_ai.py backend/tests/test_config.py
git commit -m "feat: add safe contract cli provider"
```

### Task 8: Persist and activate contract versions atomically

**Files:**
- Create: `backend/src/glyph/implementation_contracts.py`
- Create: `backend/tests/test_implementation_contracts.py`

**Step 1: Write failing service tests**

Cover:

- document, Reader, and Research Map preconditions;
- selected map belongs to the document and source hash;
- current active map is the default input, explicit immutable map is supported;
- pipeline stage order;
- exact evidence before synthesis;
- canonical persistence of values;
- deterministic signatures;
- successful active-version swap;
- partial/blocked contracts can be active but are labelled honestly;
- injected persistence failure preserves the previous active contract byte-for-byte;
- failed generation does not persist partial items or deactivate the old version;
- stale calculation from both source hash and map signature;
- bounded eager loading with no N+1 item/evidence queries.

```python
def test_failed_replacement_preserves_active_contract(session, ready_context, monkeypatch):
    original = generate_contract(session, ready_context)
    before = snapshot_contract(session, original.id)
    monkeypatch.setattr("glyph.implementation_contracts.persist_items", raise_after_first_item)
    with pytest.raises(RuntimeError):
        generate_contract(session, ready_context)
    assert snapshot_contract(session, original.id) == before
    assert active_contract_id(session, ready_context.document.id) == original.id
```

**Step 2: Verify RED**

Run: `cd backend && ../.venv/bin/pytest tests/test_implementation_contracts.py -q`

Expected: FAIL because `ImplementationContractService` does not exist.

**Step 3: Implement input loading and stage orchestration**

Define immutable view types and `ImplementationContractService.generate(document_id, research_map_version_id=None)`. Stage callback values are exactly `load_context`, `extract_requirements`, `validate_evidence`, `synthesize_contract`, `audit_readiness`, and `persist_and_activate` with monotonic progress.

Compute `research_map_signature` from map version identity, node signatures, and evidence hashes. Do not use mutable human Map reviews as author evidence; a corrected Map claim may be context for the user, not source truth.

**Step 4: Implement savepoint persistence and loading**

Persist version, items, anchors, and issues in one nested transaction. Set completed status/readiness from the deterministic audit, then deactivate the previous version and activate the new version in the same savepoint. Return complete effective views with latest resolutions and derived `is_current`/`is_stale`.

**Step 5: Run focused tests**

```bash
cd backend
../.venv/bin/pytest tests/test_implementation_contracts.py tests/test_research_maps.py -q
../.venv/bin/ruff check src/glyph/implementation_contracts.py tests/test_implementation_contracts.py
../.venv/bin/mypy src/glyph
```

Expected: all pass.

**Step 6: Commit**

```bash
git add backend/src/glyph/implementation_contracts.py backend/tests/test_implementation_contracts.py
git commit -m "feat: persist implementation contracts atomically"
```

### Task 9: Add append-only decisions, exact carry-forward, versions, and diffs

**Files:**
- Modify: `backend/src/glyph/implementation_contracts.py`
- Modify: `backend/tests/test_implementation_contracts.py`

**Step 1: Write failing resolution tests**

Test every transition and invariant:

- `confirmed` keeps the draft value;
- `corrected` and `decided` require typed values and reasons;
- `not_applicable` requires a reason and is forbidden for mandatory semantic fields where audit rules disallow it;
- `questioned` makes readiness blocked/review-needed as appropriate;
- obsolete item signature returns conflict;
- duplicate `request_id` returns the original saved resolution without a duplicate row;
- a different payload reusing a request ID returns conflict;
- revision numbers and supersedes links are monotonic;
- concurrent attempts cannot create duplicate revisions;
- audit/readiness refreshes after every resolution.

**Step 2: Write failing version/diff tests**

Classify `unchanged`, `value_changed`, `origin_changed`, `evidence_changed`, `added`, and `removed`. Carry a resolution only when the full item signature matches byte-for-byte. Never carry a decision to changed evidence or value.

**Step 3: Verify RED**

Run: `cd backend && ../.venv/bin/pytest tests/test_implementation_contracts.py -q`

Expected: new resolution and diff tests FAIL.

**Step 4: Implement append and idempotency logic**

Lock at the transaction boundary available to SQLite, re-read the latest revision, validate `based_on_item_signature`, and catch unique-constraint races. Re-audit the effective contract and update only the version readiness field; immutable AI draft fields never change.

**Step 5: Implement list, activate, diff, and carry-forward**

Historical activation must check document ownership and finished status. Stale historical versions remain marked stale. Diff ordering follows section order, display order, then item key.

**Step 6: Run focused tests**

Run: `cd backend && ../.venv/bin/pytest tests/test_implementation_contracts.py -q`

Expected: all pass, including conflict and idempotency cases.

**Step 7: Commit**

```bash
git add backend/src/glyph/implementation_contracts.py backend/tests/test_implementation_contracts.py
git commit -m "feat: resolve and version implementation contracts"
```

### Task 10: Add persistent jobs and restart recovery

**Files:**
- Create: `backend/src/glyph/contract_jobs.py`
- Create: `backend/tests/test_contract_jobs.py`
- Modify: `backend/src/glyph/main.py`

**Step 1: Write failing lifecycle tests**

Mirror but do not couple to `research_jobs.py`. Test enqueue, one active job per document, claim, monotonic stages, success link to version, safe failure message, executor shutdown, one restart requeue, repeated-interruption failure, queued-job startup submission, and concurrent unique-index enforcement.

**Step 2: Verify RED**

Run: `cd backend && ../.venv/bin/pytest tests/test_contract_jobs.py -q`

Expected: FAIL because contract jobs do not exist.

**Step 3: Implement job functions and single-worker executor**

Use `ImplementationContractJobExecutor`, its own one-worker pool, and the same bounded shutdown policy. Catch provider/persistence failures at the external boundary, log tracebacks locally, and expose only `Implementation Contract generation failed. Check the server logs for details.`

**Step 4: Wire lifespan recovery**

Create both Research Map and Contract executors in `main.py`, recover and submit both queues at startup, and shut both down in `finally`. Keep executor state names distinct: `research_job_executor` and `contract_job_executor`.

**Step 5: Run lifecycle regressions**

```bash
cd backend
../.venv/bin/pytest tests/test_contract_jobs.py tests/test_research_jobs.py tests/test_health.py -q
```

Expected: both job systems pass independently.

**Step 6: Commit**

```bash
git add backend/src/glyph/contract_jobs.py backend/src/glyph/main.py backend/tests/test_contract_jobs.py
git commit -m "feat: run persistent contract jobs"
```

### Task 11: Expose strict APIs and Library summaries

**Files:**
- Create: `backend/src/glyph/contract_schemas.py`
- Create: `backend/src/glyph/contract_routes.py`
- Create: `backend/tests/test_contract_api.py`
- Modify: `backend/src/glyph/main.py`
- Modify: `backend/src/glyph/schemas.py`
- Modify: `backend/src/glyph/documents.py`
- Modify: `backend/tests/test_documents.py`
- Modify: `backend/pyproject.toml`

**Step 1: Write failing schema and route tests**

Cover all designed endpoints and exact `404`, `409`, `422`, and `202` behavior. Pydantic request models use `extra="forbid"`, strict discriminated values, bounded text, hash patterns, and cross-field validators.

Resolution request shape:

```python
class ContractResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    status: ResolutionStatus
    based_on_item_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolved_value: ContractValueIn | None = None
    reason: str | None = Field(default=None, max_length=4000)
```

Also prove no route returns raw ORM JSON and malformed/unknown typed-value keys are rejected.

**Step 2: Verify RED**

Run: `cd backend && ../.venv/bin/pytest tests/test_contract_api.py -q`

Expected: FAIL because routes and schemas do not exist.

**Step 3: Implement Pydantic views and routes**

Add:

- `POST /api/documents/{document_id}/implementation-contract`
- `GET /api/implementation-contract-jobs/{job_id}`
- `GET /api/documents/{document_id}/implementation-contract`
- `GET /api/documents/{document_id}/implementation-contract/versions`
- `GET /api/implementation-contracts/{version_id}`
- `GET /api/implementation-contracts/{version_id}/diff?against=...`
- `PATCH /api/implementation-contract-items/{item_id}/resolution`
- `POST /api/implementation-contracts/{version_id}/activate`

The enqueue body optionally accepts `research_map_version_id`; the backend verifies ownership and freshness.

**Step 4: Add bounded Library summaries**

Extend `DocumentOut` with optional `implementation_contract` containing version ID, generation status, readiness, current/stale flags, blocker count, reviewed count, and total reviewable count. Load all summaries for a document list with bounded aggregate queries, never one query per document.

**Step 5: Register the router and lint exception narrowly**

Include the contract router in `main.py`. If FastAPI dependency defaults trigger Ruff B008, add only `src/glyph/contract_routes.py` to the existing per-file ignore.

**Step 6: Run API and catalog regressions**

```bash
cd backend
../.venv/bin/pytest tests/test_contract_api.py tests/test_documents.py tests/test_research_api.py -q
../.venv/bin/ruff check src tests
../.venv/bin/mypy src/glyph
```

Expected: all pass and old JSON remains backward compatible through optional fields.

**Step 7: Commit**

```bash
git add backend/src/glyph/contract_schemas.py backend/src/glyph/contract_routes.py backend/src/glyph/main.py backend/src/glyph/schemas.py backend/src/glyph/documents.py backend/tests/test_contract_api.py backend/tests/test_documents.py backend/pyproject.toml
git commit -m "feat: expose implementation contract api"
```

### Task 12: Build deterministic JSON/Markdown exports and local CLI commands

**Files:**
- Create: `backend/src/glyph/contract_export.py`
- Create: `backend/src/glyph/contract_cli.py`
- Create: `backend/tests/test_contract_export.py`
- Create: `backend/tests/test_contract_cli.py`
- Modify: `backend/src/glyph/contract_routes.py`
- Modify: `backend/src/glyph/contract_schemas.py`
- Modify: `backend/tests/test_contract_api.py`
- Modify: `backend/pyproject.toml`

**Step 1: Write failing exporter tests**

Assert byte-identical output for repeated runs, stable section/item ordering, valid JSON schema, escaped Markdown, bilingual/English options, source anchors without local paths, effective/draft value separation, decision history, and a top-level `NOT IMPLEMENTATION READY` marker when blockers remain.

Before serialization, mutate persistence into an invalid state and prove export re-audits and refuses a false-ready label.

**Step 2: Write failing CLI tests**

Add `glyph-contract list`, `show DOCUMENT_ID`, `generate DOCUMENT_ID [--map-version ID]`, and `export VERSION_ID --format json|markdown --language en|zh-TW|bilingual --output PATH`. Tests call `main(argv, settings)` directly, capture stdout/stderr, and use a temporary explicit output path. No command executes generated code.

**Step 3: Verify RED**

Run:

```bash
cd backend
../.venv/bin/pytest tests/test_contract_export.py tests/test_contract_cli.py -q
```

Expected: FAIL because exporter and CLI are absent.

**Step 4: Implement one canonical export model**

Build a pure canonical payload from the freshly audited effective view. Both HTTP and CLI serializers consume it. JSON uses UTF-8, sorted keys, and fixed separators; Markdown uses fixed headings and preserves verbatim evidence as quoted data.

**Step 5: Add export route and script entry point**

Add `GET /api/implementation-contracts/{version_id}/export` with strict format/language query enums and correct `Content-Type`/`Content-Disposition`. Add:

```toml
[project.scripts]
glyph-contract = "glyph.contract_cli:entrypoint"
```

The CLI uses the same settings, migrations, service, audit, and export functions as HTTP; it does not make an HTTP call to localhost.

**Step 6: Run export, CLI, and API checks**

```bash
cd backend
../.venv/bin/pytest tests/test_contract_export.py tests/test_contract_cli.py tests/test_contract_api.py -q
../.venv/bin/ruff check src tests
../.venv/bin/mypy src/glyph
```

Expected: all pass and repeated mock exports are byte-identical.

**Step 7: Commit**

```bash
git add backend/src/glyph/contract_export.py backend/src/glyph/contract_cli.py backend/src/glyph/contract_routes.py backend/src/glyph/contract_schemas.py backend/tests/test_contract_export.py backend/tests/test_contract_cli.py backend/tests/test_contract_api.py backend/pyproject.toml
git commit -m "feat: export implementation contracts"
```

### Task 13: Add frontend types, runtime guards, API functions, and state machine

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/api.test.ts`
- Create: `frontend/src/implementationContractState.ts`
- Create: `frontend/src/implementationContractState.test.ts`
- Create: `frontend/src/implementationContractTestData.ts`

**Step 1: Write failing runtime-guard tests**

Test valid payloads and reject unknown section/type/origin/readiness/status values, malformed typed values, unknown keys, invalid hashes, invalid dates, non-finite numbers, and structurally incomplete evidence/resolution/diff/job/export metadata.

**Step 2: Write failing state-machine tests**

Cover idle/loading/absent/ready/error, job polling, selected item, six guided steps, inspector open/close, stale/blocker warnings, optimistic resolution, reason-required lockout, success, conflict rollback, request-ID isolation, and ignoring a late response from an obsolete request or document.

```ts
it('ignores a late resolution from the previous item', () => {
  const pending = reduceReady({ type: 'resolutionOptimistic', requestId: 'r1', itemId: 'old', resolution })
  const switched = reducer(pending, { type: 'selectItem', itemId: 'new' })
  expect(reducer(switched, { type: 'resolutionSaved', requestId: 'r0', resolution })).toEqual(switched)
})
```

**Step 3: Verify RED**

Run:

```bash
cd frontend
npm test -- --run src/api.test.ts src/implementationContractState.test.ts
```

Expected: FAIL because types, guards, and reducer do not exist.

**Step 4: Implement discriminated types and runtime guards**

Use exact TypeScript unions matching Pydantic. Keep validator arrays central and reject unknown typed-value keys by comparing allowed key sets. Add API functions for enqueue/job/active/version/list/diff/resolve/activate/export.

**Step 5: Implement the independent reducer and poller**

Do not add contract decision state to `researchMapState.ts`. The contract reducer owns selection, guided step `0..5`, pending resolution, notice, current contract, job, and the surface to return to after Reader evidence navigation.

**Step 6: Run focused tests and build**

```bash
cd frontend
npm test -- --run src/api.test.ts src/implementationContractState.test.ts
npm run build
```

Expected: all pass with no unsafe casts at API call sites.

**Step 7: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts frontend/src/api.test.ts frontend/src/implementationContractState.ts frontend/src/implementationContractState.test.ts frontend/src/implementationContractTestData.ts
git commit -m "feat: model implementation contract state"
```

### Task 14: Add Library and Research Map entry points with job flow

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/ResearchMap.tsx`
- Modify: `frontend/src/ResearchMap.test.tsx`
- Modify: `frontend/src/researchMapState.ts`
- Modify: `frontend/src/researchMapState.test.ts`

**Step 1: Write failing Library tests**

Assert each row renders contract readiness, blockers, stale/current state, and a `Resume Contract` action only when appropriate. For a current Research Map with no contract, the primary action remains opening Research Map; contract creation is available from the map workspace.

**Step 2: Write failing Map action tests**

Render `Build Implementation Contract` only when a completed/partial Map version is eligible. Clicking it passes the explicit active Map version ID to the handler. A stale map disables creation and explains that the source/Map must be refreshed.

**Step 3: Write failing App job-flow tests**

Test enqueue, polling progress, completion load, safe failure, duplicate-job `409`, abort on document switch/unmount, and refresh of Library summary after completion.

**Step 4: Verify RED**

Run:

```bash
cd frontend
npm test -- --run src/App.test.tsx src/ResearchMap.test.tsx src/researchMapState.test.ts
```

Expected: new entry-point and job-flow assertions FAIL.

**Step 5: Implement top-level surface coordination**

Extend only the top-level workspace mode to `map | contract | reader`; keep Map and Contract reducers independent. `App.tsx` owns which reducer receives a Reader-return event. Opening contract evidence records `contract` as the return surface; opening Map evidence records `map`.

**Step 6: Run focused tests**

Run the command from Step 4.

Expected: all pass and existing Map/Reader navigation remains green.

**Step 7: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/ResearchMap.tsx frontend/src/ResearchMap.test.tsx frontend/src/researchMapState.ts frontend/src/researchMapState.test.ts
git commit -m "feat: open contracts from research maps"
```

### Task 15: Build the three-column Contract workbench and six-step review

**Files:**
- Create: `frontend/src/ImplementationContract.tsx`
- Create: `frontend/src/ImplementationContract.test.tsx`
- Create: `frontend/src/ContractGuidedReview.tsx`
- Create: `frontend/src/ContractGuidedReview.test.tsx`
- Create: `frontend/src/ContractInspector.tsx`
- Create: `frontend/src/ContractInspector.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Step 1: Write failing outline/workbench tests**

Assert eight fixed sections, item counts, blocker badges, selected state, origin labels, draft/effective value separation, readiness banner, partial/stale alerts, keyboard-reachable controls, visible focus, and inspector collapse behavior.

**Step 2: Write failing guided-review tests**

Assert exactly six steps in Traditional Chinese:

1. 資料可得性
2. 樣本與投資範圍
3. 訊號與時間規則
4. 投資組合建構
5. 評估與交易摩擦
6. 解決阻擋項目並匯出

Next/previous boundaries are deterministic. Each step shows only its mapped sections and strongest blocker/evidence summary.

**Step 3: Write failing inspector tests**

For `author_explicit`, show direct anchors. For `derived`, show at least two anchors and rationale. For `human_decision`, show reason and history. For `missing`, offer only: remain blocked, decide with reason, not applicable with reason, and open Reader. Prove there is no default/auto-fill button.

Test form validation, pending lock, server conflict, accessible error association, and exact `onOpenReader(blockId)` calls.

**Step 4: Verify RED**

Run:

```bash
cd frontend
npm test -- --run src/ImplementationContract.test.tsx src/ContractGuidedReview.test.tsx src/ContractInspector.test.tsx
```

Expected: FAIL because components do not exist.

**Step 5: Implement semantic components**

Use native buttons, headings, nav, progress, fieldsets, labels, and `aria-live`/`role=alert` where state changes. Keep source evidence verbatim English with aligned Traditional Chinese context. Use existing paper/charcoal/deep-blue/amber/green/red visual tokens; add CSS variables only where a semantic contract state is missing.

**Step 6: Implement responsive behavior**

Desktop uses three columns. Medium screens collapse the inspector to a controlled drawer. Small screens use one ordered column with outline, review, then inspector; no horizontal dependency and no hidden blocker state.

**Step 7: Run focused tests and build**

```bash
cd frontend
npm test -- --run src/ImplementationContract.test.tsx src/ContractGuidedReview.test.tsx src/ContractInspector.test.tsx src/App.test.tsx
npm run build
```

Expected: all pass.

**Step 8: Commit**

```bash
git add frontend/src/ImplementationContract.tsx frontend/src/ImplementationContract.test.tsx frontend/src/ContractGuidedReview.tsx frontend/src/ContractGuidedReview.test.tsx frontend/src/ContractInspector.tsx frontend/src/ContractInspector.test.tsx frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat: add contract review workbench"
```

### Task 16: Add versions, diffs, export warnings, and Contract–Map–Reader deep links

**Files:**
- Create: `frontend/src/ContractVersions.tsx`
- Create: `frontend/src/ContractVersions.test.tsx`
- Create: `frontend/src/ContractExport.tsx`
- Create: `frontend/src/ContractExport.test.tsx`
- Modify: `frontend/src/ImplementationContract.tsx`
- Modify: `frontend/src/ImplementationContract.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/Reader.tsx`
- Modify: `frontend/src/Reader.test.tsx`
- Modify: `frontend/src/styles.css`

**Step 1: Write failing history/diff tests**

Assert current/stale/active labels, deterministic diff groups, changed evidence/value/origin distinctions, activation confirmation, `409` handling, and no UI claim that activating stale history makes it current.

**Step 2: Write failing export tests**

Assert format/language selection, explicit `NOT IMPLEMENTATION READY` warning, blocker count, download filename, API error recovery, and no optimistic ready label. Ready exports still state that Glyph does not validate profitability.

**Step 3: Write failing navigation tests**

Test Contract → exact Reader block → return to same Contract item; Contract → linked Research Map node → return to same item; Map → Contract → Reader; document switching clears all selections. Reader citing context must label whether citations came from Contract or Map.

**Step 4: Verify RED**

Run:

```bash
cd frontend
npm test -- --run src/ContractVersions.test.tsx src/ContractExport.test.tsx src/ImplementationContract.test.tsx src/App.test.tsx src/Reader.test.tsx
```

Expected: new version/export/deep-link assertions FAIL.

**Step 5: Implement the surfaces and return stack**

Store stable IDs, not component instances, in navigation state. On return, reselect only if the contract/map still contains the ID; otherwise select the first valid item and announce the change. Use backend-provided diffs and readiness, never recompute them in React.

**Step 6: Run focused and full frontend tests**

```bash
cd frontend
npm test -- --run
npm run build
```

Expected: all tests and TypeScript build pass.

**Step 7: Commit**

```bash
git add frontend/src/ContractVersions.tsx frontend/src/ContractVersions.test.tsx frontend/src/ContractExport.tsx frontend/src/ContractExport.test.tsx frontend/src/ImplementationContract.tsx frontend/src/ImplementationContract.test.tsx frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/Reader.tsx frontend/src/Reader.test.tsx frontend/src/styles.css
git commit -m "feat: complete contract navigation and export ui"
```

### Task 17: Document trust boundaries, recovery, and architecture decision

**Files:**
- Create: `docs/implementation-contract.md`
- Create: `docs/adr/ADR-0002-auditable-implementation-contract.md`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `SECURITY.md`
- Modify: `CHANGELOG.md`

**Step 1: Write the user and operator guide**

Document:

- the four origins and three readiness states;
- why missing is not zero/not-applicable;
- the six-step workflow;
- JSON/Markdown export fields;
- CLI and HTTP examples;
- local provider configuration;
- stale/version/carry-forward semantics;
- migration `0004`, backup, forward upgrade, recovery after job interruption, and preservation of the prior active contract;
- limitations: no execution, no investment advice, no proof of profitability.

**Step 2: Record the ADR**

ADR-0002 must state the decision that provider output cannot set readiness and that human resolutions are append-only overlays. Include alternatives (free-form AI spec, auto-default templates, direct code generation), rejected reasons, consequences, and the boundary for future Reproduction Lab.

**Step 3: Update contribution and security guidance**

Require tests for new vocabulary/readiness rules and gold fixture changes. Explain untrusted document prompts, exact-anchor validation, no code execution, no provider-supplied identity, local logs, and safe export handling.

**Step 4: Verify all commands and links**

Run:

```bash
rg -n "implementation-contract|glyph-contract|0004_implementation_contracts" README.md CONTRIBUTING.md SECURITY.md CHANGELOG.md docs
git diff --check
```

Expected: all named routes/commands match code and no whitespace errors exist.

**Step 5: Commit**

```bash
git add README.md CONTRIBUTING.md SECURITY.md CHANGELOG.md docs/implementation-contract.md docs/adr/ADR-0002-auditable-implementation-contract.md
git commit -m "docs: explain implementation contract guarantees"
```

### Task 18: Run full acceptance, browser QA, security checks, and independent review

**Files:**
- Create: `docs/plans/2026-08-12-implementation-contract-audit.md`
- Modify only if a discovered defect requires a tested fix: relevant source and test files

**Step 1: Run all backend gates**

```bash
cd backend
../.venv/bin/ruff check src tests
../.venv/bin/mypy src/glyph
../.venv/bin/pytest --cov=glyph --cov-report=term-missing --cov-fail-under=85
../.venv/bin/bandit -q -r src/glyph
../.venv/bin/pip-audit --skip-editable
```

Expected: zero failures, typing errors, lint errors, Bandit findings, or known dependency vulnerabilities; coverage at least 85%.

**Step 2: Run all frontend gates**

```bash
cd frontend
npm test -- --run
npm run build
npm audit --audit-level=high
```

Expected: zero test/build failures and zero high/critical dependency findings.

**Step 3: Run benchmark acceptance explicitly**

```bash
cd backend
../.venv/bin/pytest tests/test_contract_benchmark.py -q
```

Expected:

- unsupported silent defaults `0%`;
- missing blocker detection `100%`;
- false-ready count `0`;
- evidence coverage `100%`;
- JSON validity `100%`;
- identical mock run diff `0`;
- failed generation preserves previous active version.

**Step 4: Run a real browser acceptance scenario**

Start backend/frontend in mock mode with isolated temporary data. In a browser:

1. Upload/process the monthly fixture and generate its Research Map.
2. Build a Contract and observe all six generation stages.
3. Complete the six-step review, inspect exact English/Chinese evidence, and open/return from Reader.
4. Make one reasoned human decision and confirm readiness changes only after audit.
5. Export valid JSON and Markdown.
6. Load the intentionally incomplete cross-market fixture and prove missing costs/weighting cannot become ready or silently default.
7. Restart both services and prove jobs/versions/resolutions persist.
8. Change/reprocess the source, regenerate Map and Contract, inspect diff, and prove changed signatures do not inherit the old resolution.
9. Inject a provider failure and prove the old active contract remains readable.
10. Check keyboard-only flow, focus visibility, semantic alerts, and narrow viewport layout.

Capture observations in the audit document; do not commit generated user data or screenshots containing local paths.

**Step 5: Request independent code review**

Use @superpowers:requesting-code-review. The reviewer must check product invariants, schema/migration safety, readiness authority, temporal correctness, concurrency/idempotency, provider security, query bounds, frontend late-response isolation, accessibility, and scope creep. Fix every Critical or Important issue with a failing regression test first, then repeat Steps 1–4.

**Step 6: Write the completion audit**

Record commit/branch, exact command results and counts, benchmark metrics, browser scenarios, migration backup/recovery confirmation, security results, known limitations, and independent-review disposition. Do not claim completion if any required gate or Critical/Important review issue remains.

**Step 7: Verify branch scope**

```bash
git status --short
git diff --check feat/research-map...HEAD
git log --oneline --decorate feat/research-map..HEAD
git diff --stat feat/research-map...HEAD
```

Expected: clean worktree; only Implementation Contract design, plan, implementation, tests, docs, and audit changes.

**Step 8: Commit the audit**

```bash
git add docs/plans/2026-08-12-implementation-contract-audit.md
git commit -m "docs: audit implementation contract milestone"
```

Do not push, open, or merge a pull request unless the user explicitly authorizes that external action after reviewing the completed audit.

## Completion definition

This plan is complete only when:

- all 18 tasks are implemented in order with TDD evidence;
- existing Research Map and Reader tests remain green;
- migration `0004` preserves all existing data and invents no contract rows;
- the provider cannot output a human decision or readiness state;
- the deterministic audit is the sole readiness authority for persistence, API, UI, CLI, and export;
- all three gold benchmarks meet every non-negotiable metric;
- the full browser scenario and responsive/a11y checks pass;
- operator and security documentation matches the shipped behavior;
- independent review has no unresolved Critical or Important issues;
- the worktree is clean and the final audit is committed.
