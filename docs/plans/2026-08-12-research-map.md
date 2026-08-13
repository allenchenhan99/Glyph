# Glyph Research Map Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an evidence-first bilingual Research Map that lets a quantitative-finance reader understand and verify a paper's question, data, signal, method, result, and limitations within ten minutes.

**Architecture:** Add immutable map versions, exact block-backed evidence anchors, separate human review overlays, persistent generation jobs, and provider-neutral extraction/synthesis services to the existing FastAPI/SQLite backend. Add a typed React research workspace with guided review and Evidence Inspector while retaining the current Reader as the deep-reading surface. Keep execution local and single-worker for now, but isolate the service and executor so a future cloud queue can reuse the same domain contracts.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, Alembic, SQLite, Pydantic, pytest, React 19, TypeScript, Vite, Vitest, Testing Library, KaTeX.

---

### Task 1: Add the Research Map schema without risking existing data

**Files:**
- Create: `backend/migrations/versions/0003_research_maps.py`
- Modify: `backend/src/glyph/models.py`
- Modify: `backend/tests/test_database.py`

**Step 1: Write failing migration tests**

Add tests that upgrade both an empty database and a legacy database through revision `0003_research_maps`. Assert the six new tables exist, the previous document and Reader data remain byte-for-byte intact, foreign keys target the correct tables, and no map rows are invented for existing documents.

```python
def test_research_map_migration_preserves_existing_reader(tmp_path):
    database_url = create_legacy_database_with_reader(tmp_path)
    upgrade_database(settings_for(database_url))
    assert reader_values(database_url) == EXPECTED_LEGACY_READER
    assert table_names(database_url) >= {
        "research_map_versions",
        "research_nodes",
        "research_evidence",
        "research_node_reviews",
        "research_map_issues",
        "research_map_jobs",
    }
```

**Step 2: Run the focused test to verify RED**

Run: `.venv/bin/pytest backend/tests/test_database.py -q`

Expected: FAIL because revision `0003_research_maps` and the new tables do not exist.

**Step 3: Add SQLAlchemy models and relationships**

Add typed models for `ResearchMapVersion`, `ResearchNode`, `ResearchEvidence`, `ResearchNodeReview`, `ResearchMapIssue`, and `ResearchMapJob`. Add unique constraints for `(map_version_id, node_key)`, `(node_id, block_id, quote_start, quote_end, relation)`, and `(node_id, revision_number)`. Reviews are append-only revisions linked with `supersedes_review_id`, so corrections retain full history. Add indexes for document/version/job lookups. Keep status values as validated domain strings rather than database-specific enum types so SQLite migrations remain portable.

**Step 4: Add Alembic revision 0003**

Create every table explicitly, in dependency order. `downgrade()` drops only Research Map tables and never touches Reader tables. Use nullable `previous_version_id`, `parent_node_id`, and `map_version_id` job links. Store timestamps consistently with existing models.

**Step 5: Verify migration and regression tests**

Run:

```bash
.venv/bin/pytest backend/tests/test_database.py -q
.venv/bin/pytest -q
```

Expected: migration tests and all existing tests pass.

**Step 6: Commit**

```bash
git add backend/migrations/versions/0003_research_maps.py backend/src/glyph/models.py backend/tests/test_database.py
git commit -m "feat: add research map schema"
```

### Task 2: Define the controlled ontology and exact evidence validator

**Files:**
- Create: `backend/src/glyph/research_domain.py`
- Create: `backend/src/glyph/research_evidence.py`
- Create: `backend/tests/test_research_evidence.py`

**Step 1: Write failing ontology and evidence tests**

Cover:

- every approved schema-v1 node type;
- rejection of unknown node types, relations, provenance, and locator types;
- exact quote/offset validation;
- unique quote location when offsets are omitted;
- rejection when a quote occurs more than once without an offset;
- rejection when a block belongs to another document;
- deterministic quote hashes and duplicate removal;
- no absolute path, HTML, or URL in structured fields.

```python
def test_anchor_must_quote_the_target_block_exactly(session, completed_document):
    candidate = EvidenceCandidate(
        block_id=completed_document.blocks[0].id,
        quote_text="text that is not present",
        quote_start=0,
        quote_end=24,
        relation="supports",
        locator_type="text_span",
    )
    with pytest.raises(InvalidEvidenceError, match="does not match"):
        validate_candidate(session, completed_document, candidate)
```

**Step 2: Run tests to verify RED**

Run: `.venv/bin/pytest backend/tests/test_research_evidence.py -q`

Expected: collection fails because the domain and validator modules do not exist.

**Step 3: Implement literal unions and immutable dataclasses**

Define `NodeType`, `Provenance`, `EvidenceQuality`, `EvidenceRelation`, `LocatorType`, `ReviewStatus`, and schema version constants. Use frozen dataclasses for provider candidates and accepted anchors. Centralize allowed values; do not duplicate string lists in routes or providers.

**Step 4: Implement deterministic anchor validation**

Load the target block from the session, prove document ownership, canonicalize or derive offsets, perform exact slicing, enforce bounds, hash `block_id + span + quote`, and return an accepted anchor. Never trust provider page numbers.

**Step 5: Run focused and static checks**

```bash
.venv/bin/pytest backend/tests/test_research_evidence.py -q
.venv/bin/ruff check backend/src/glyph/research_domain.py backend/src/glyph/research_evidence.py backend/tests/test_research_evidence.py
.venv/bin/mypy backend/src/glyph
```

Expected: all pass.

**Step 6: Commit**

```bash
git add backend/src/glyph/research_domain.py backend/src/glyph/research_evidence.py backend/tests/test_research_evidence.py
git commit -m "feat: validate research evidence anchors"
```

### Task 3: Build an evidence-first mock provider and completeness audit

**Files:**
- Create: `backend/src/glyph/research_ai.py`
- Create: `backend/src/glyph/research_audit.py`
- Create: `backend/tests/fixtures/empirical_asset_pricing.txt`
- Create: `backend/tests/test_research_ai.py`
- Create: `backend/tests/test_research_audit.py`

**Step 1: Add a synthetic empirical-finance fixture**

Write an original, compact paper-like fixture with explicit sections for research question, CRSP sample dates, signal construction, monthly rebalancing, Fama-French benchmark regression, long-short return and t-statistic, transaction costs not reported, robustness, and limitations. Avoid third-party paper text.

**Step 2: Write failing provider-contract tests**

Require two explicit phases:

```python
candidates = provider.extract_candidates(blocks)
accepted = validate_candidates(session, document, candidates)
draft = provider.synthesize_nodes(accepted)
```

Assert synthesis receives no unvalidated block collection, all referenced evidence IDs exist, node keys are deterministic, and the six core categories are represented or produce structured missing issues.

**Step 3: Write failing audit tests**

Cover `author_explicit` direct-evidence requirements, two-anchor synthesis, `not_reported` semantics, unsupported normal claims, missing core categories, primary results without statistical/economic evidence, and `partial` versus `complete` map status.

**Step 4: Implement provider protocols and deterministic mock**

Define a `ResearchMapProvider` protocol with `extract_candidates()` and `synthesize_nodes()`. Implement `MockResearchMapProvider` with deterministic heading and field recognition for fixtures and local development. It must generate `not_reported` for absent transaction costs rather than inventing a value.

**Step 5: Implement deterministic audit**

Return `MapAuditResult(status, issues)` without mutating persistence models. Use stable issue codes such as `missing_core_node`, `unsupported_claim`, `missing_statistical_evidence`, and `conflicting_evidence`.

**Step 6: Verify focused tests**

```bash
.venv/bin/pytest backend/tests/test_research_ai.py backend/tests/test_research_audit.py -q
.venv/bin/ruff check backend/src backend/tests
.venv/bin/mypy backend/src/glyph
```

Expected: all pass.

**Step 7: Commit**

```bash
git add backend/src/glyph/research_ai.py backend/src/glyph/research_audit.py backend/tests
git commit -m "feat: generate audited research map drafts"
```

### Task 4: Persist map versions atomically and preserve the active map on failure

**Files:**
- Create: `backend/src/glyph/research_maps.py`
- Create: `backend/tests/test_research_maps.py`
- Modify: `backend/src/glyph/pipeline.py`
- Modify: `backend/src/glyph/documents.py`
- Modify: `backend/src/glyph/models.py`
- Modify: `backend/migrations/versions/0003_research_maps.py`

**Step 1: Write atomic-generation tests**

Test a successful version, then inject a failure after node deletion/insertion begins for a replacement version. Assert the old active map, nodes, evidence, issues, and reviews remain unchanged and the failed draft is not active.

Also test:

- a map requires a current completed Reader snapshot;
- stale/missing/unprocessed sources return domain conflicts;
- only one map version is active per document;
- source hash and provider metadata are stored;
- node signatures are deterministic;
- a `partial` map can be active but visibly remains partial;
- an explicitly failed version cannot activate.
- reprocessing retains cited historical blocks while the Reader selects only its
  current source-hash snapshot.

**Step 2: Verify RED**

Run: `.venv/bin/pytest backend/tests/test_research_maps.py -q`

Expected: FAIL because the service does not exist.

**Step 3: Implement `ResearchMapService`**

Separate pure generation from persistence. Validate all anchors and audit the draft before beginning the savepoint. Inside one nested transaction, create the immutable version, nodes, evidence, and issues; flush; deactivate the previous active version; activate the new version. Store safe public errors while logging internal tracebacks.

**Step 4: Add output-loading functions**

Load active or explicit versions with nodes ordered deterministically, evidence grouped by node, issues, effective review overlays, current/stale status, and verification counts. Avoid N+1 queries with explicit batched selects.

**Step 5: Verify tests and coverage**

```bash
.venv/bin/pytest backend/tests/test_research_maps.py backend/tests/test_pipeline.py -q
.venv/bin/pytest --cov=glyph --cov-report=term-missing --cov-fail-under=85
```

Expected: all pass and coverage remains above 85%.

**Step 6: Commit**

```bash
git add backend/src/glyph/research_maps.py backend/src/glyph/pipeline.py backend/tests/test_research_maps.py
git commit -m "feat: persist research maps atomically"
```

### Task 5: Add persistent background jobs with restart recovery

**Files:**
- Create: `backend/src/glyph/research_jobs.py`
- Create: `backend/tests/test_research_jobs.py`
- Modify: `backend/src/glyph/main.py`
- Modify: `backend/src/glyph/config.py`
- Modify: `.env.example`

**Step 1: Write failing job lifecycle tests**

Prove:

- enqueue returns immediately with a queued job;
- one document cannot have two queued/running jobs;
- stages progress through evidence, validation, synthesis, audit, and persistence;
- a provider failure creates a safe failed job and keeps the active map;
- startup requeues an interrupted running job once;
- repeated interruption beyond the attempt limit fails safely;
- executor shutdown does not leave new work accepting silently.

Use events, not sleeps, for concurrency tests.

**Step 2: Verify RED**

Run: `.venv/bin/pytest backend/tests/test_research_jobs.py -q`

Expected: FAIL because no job executor exists.

**Step 3: Implement repository and process-local coordinator**

Create, claim, progress, complete, and fail jobs through small functions. Claim with a lease token and flush before execution. Reuse the process-local per-document coordination pattern while keeping map and Reader job namespaces separate.

**Step 4: Implement a single-worker local executor**

Use a bounded `ThreadPoolExecutor(max_workers=1)` owned by app lifespan. Submit queued jobs outside request handling. On startup, recover interrupted jobs and submit queued work. On shutdown, stop accepting and wait for the active task within a bounded timeout.

Add `GLYPH_RESEARCH_JOB_MAX_ATTEMPTS` defaulting to 2. Reject non-positive values.

**Step 5: Verify recovery and regression tests**

```bash
.venv/bin/pytest backend/tests/test_research_jobs.py backend/tests/test_config.py -q
.venv/bin/pytest -q
```

Expected: all pass without timing flakes.

**Step 6: Commit**

```bash
git add .env.example backend/src/glyph/config.py backend/src/glyph/main.py backend/src/glyph/research_jobs.py backend/tests
git commit -m "feat: run persistent research map jobs"
```

### Task 6: Expose typed Research Map, job, review, version, and diff APIs

**Files:**
- Create: `backend/src/glyph/research_routes.py`
- Create: `backend/src/glyph/research_schemas.py`
- Create: `backend/tests/test_research_api.py`
- Modify: `backend/src/glyph/main.py`

**Step 1: Write failing API integration tests**

Cover every route from the design, status codes, response shapes, active/current/stale flags, partial issues, verification progress, exact evidence locators, review validation, activation constraints, and version diffs.

```python
response = client.post(f"/api/documents/{document_id}/research-map")
assert response.status_code == 202
job = response.json()
assert job["stage"] == "queued"
```

Test 404, 409, and 422 boundaries separately. Confirm API payloads never contain local paths, raw provider prompts, lease tokens, or internal tracebacks.

**Step 2: Run tests to verify RED**

Run: `.venv/bin/pytest backend/tests/test_research_api.py -q`

Expected: all new routes return 404.

**Step 3: Implement discriminated Pydantic schemas**

Use literal status/provenance/quality unions. Create dedicated evidence, node, review, issue, map summary, map detail, job, version, and diff schemas. Do not expose ORM objects directly.

**Step 4: Implement routes and review overlay rules**

`PATCH review` accepts a node signature precondition. Return 409 when a client edits an obsolete node. Require corrected text for `corrected`; clear it for other states. `activate` accepts only complete/partial non-stale versions for the same current source.

**Step 5: Implement deterministic version diff**

Compare same-document versions. Match node keys first, then classify exact signatures as unchanged, claim hash changes, evidence hash changes, additions, and removals. Do not add semantic embedding infrastructure in v1.

**Step 6: Verify API and security checks**

```bash
.venv/bin/pytest backend/tests/test_research_api.py -q
.venv/bin/ruff check backend/src backend/tests
.venv/bin/ruff format --check backend/src backend/tests
.venv/bin/mypy backend/src/glyph
.venv/bin/bandit -q -r backend/src/glyph
```

Expected: all pass.

**Step 7: Commit**

```bash
git add backend/src/glyph/main.py backend/src/glyph/research_routes.py backend/src/glyph/research_schemas.py backend/tests/test_research_api.py
git commit -m "feat: expose research map APIs"
```

### Task 7: Add strict CLI evidence extraction and synthesis providers

**Files:**
- Create: `backend/src/glyph/research_cli_ai.py`
- Create: `backend/tests/test_research_cli_ai.py`
- Modify: `backend/src/glyph/research_ai.py`
- Modify: `backend/src/glyph/config.py`
- Modify: `.env.example`

**Step 1: Write failing contract and security tests**

Mock CLI runners and test:

- extraction and synthesis use separate prompts and JSON schemas;
- document text is delimited and labeled untrusted data;
- only block IDs and bounded text are sent;
- provider cannot return unknown node types or evidence IDs;
- prompt injection inside the paper does not alter the requested schema;
- retries correct invalid JSON, missing coverage, duplicate IDs, and unknown evidence references;
- timeouts, missing executables, nonzero exits, and malformed output produce sanitized domain errors;
- cache keys include provider, model, schema version, stage, and source hash.

**Step 2: Verify RED**

Run: `.venv/bin/pytest backend/tests/test_research_cli_ai.py -q`

Expected: FAIL because the CLI provider does not exist.

**Step 3: Implement extraction schema and prompt**

Reuse resolved executable, argv-only, timeout, concurrency, retry, and cache utilities from `cli_ai.py` where behavior is identical. Extract shared process helpers instead of copying subprocess code. The extraction result cannot contain final claim text.

**Step 4: Implement synthesis schema and prompt**

Pass only accepted evidence with opaque IDs. Validate that every cited evidence ID exists and that author-explicit versus AI-synthesis requirements can pass the deterministic audit.

**Step 5: Wire provider selection and settings**

Use existing `GLYPH_AI_MODE`, model, timeout, and cache location. Add only settings that are genuinely Research Map-specific, such as bounded block batch size; document defaults.

**Step 6: Run provider, existing CLI, and security tests**

```bash
.venv/bin/pytest backend/tests/test_research_cli_ai.py backend/tests/test_cli_ai.py -q
.venv/bin/ruff check backend/src backend/tests
.venv/bin/mypy backend/src/glyph
.venv/bin/bandit -q -r backend/src/glyph
```

Expected: all pass with no new subprocess findings.

**Step 7: Commit**

```bash
git add .env.example backend/src/glyph/research_ai.py backend/src/glyph/research_cli_ai.py backend/src/glyph/config.py backend/tests/test_research_cli_ai.py
git commit -m "feat: extract research maps with cli providers"
```

### Task 8: Add typed frontend API contracts and workspace state

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/api.test.ts`
- Create: `frontend/src/researchMapState.ts`
- Create: `frontend/src/researchMapState.test.ts`

**Step 1: Write failing response-validation tests**

Test valid map/job/review/version/diff payloads and rejection of unknown provenance, qualities, node types, review statuses, malformed evidence, missing issues, and obsolete shapes. Keep runtime guards at the HTTP boundary.

**Step 2: Write failing state reducer tests**

Model loading, enqueue/poll, selected node, guided-review step, inspector open/close, optimistic review, review conflict rollback, Map/Reader mode, partial/stale warnings, and failed jobs as explicit reducer events. Avoid scattered component booleans.

**Step 3: Verify RED**

Run: `npm --prefix frontend test -- --run src/api.test.ts src/researchMapState.test.ts`

Expected: FAIL because types, guards, and reducer do not exist.

**Step 4: Implement discriminated TypeScript types and guards**

Mirror backend literal unions. Add `enqueueResearchMap`, `getResearchMapJob`, `getActiveResearchMap`, `getResearchMapVersion`, `listResearchMapVersions`, `getResearchMapDiff`, `reviewResearchNode`, and `activateResearchMap`.

**Step 5: Implement reducer and polling helper**

Polling uses condition-based intervals with cancellation on unmount/document change. It stops on completed/failed and refreshes map/library state exactly once. Do not put fetch calls inside the reducer.

**Step 6: Verify frontend unit tests and build**

```bash
npm --prefix frontend test -- --run src/api.test.ts src/researchMapState.test.ts
npm --prefix frontend run build
```

Expected: all pass.

**Step 7: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts frontend/src/api.test.ts frontend/src/researchMapState.ts frontend/src/researchMapState.test.ts
git commit -m "feat: add research map frontend contracts"
```

### Task 9: Build the Research Map workspace and ten-minute guided review

**Files:**
- Create: `frontend/src/ResearchMap.tsx`
- Create: `frontend/src/ResearchMap.test.tsx`
- Create: `frontend/src/EvidenceInspector.tsx`
- Create: `frontend/src/EvidenceInspector.test.tsx`
- Create: `frontend/src/GuidedReview.tsx`
- Create: `frontend/src/GuidedReview.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/styles.css`

**Step 1: Write failing component tests**

Require:

- Map is the default open action when available;
- generate CTA and privacy notice when absent;
- visible partial and stale states;
- six ontology categories and deterministic ordering;
- provenance and evidence-quality labels;
- guided review's five bounded steps and strongest evidence;
- inspector verbatim English, Traditional Chinese block translation, page/locator, relations, and open-in-Reader action;
- `Confirm`, `Question`, and `Correct` with required correction text;
- review conflict restores server state and announces an actionable alert;
- no generic chat input.

**Step 2: Verify RED**

Run:

```bash
npm --prefix frontend test -- --run src/ResearchMap.test.tsx src/EvidenceInspector.test.tsx src/GuidedReview.test.tsx src/App.test.tsx
```

Expected: FAIL because the workspace components do not exist.

**Step 3: Implement semantic workspace structure**

Use `nav` for ontology, `main`/region for review content, and a labeled complementary inspector. Render buttons with names that include the target node. Preserve selected node and mode in reducer state.

**Step 4: Implement guided review selection**

Choose the first supported node in each core stage. If a category is missing, render the matching structured issue rather than skipping silently. Completion counts human-reviewed core nodes, not mere clicks.

**Step 5: Implement review actions**

Use node signatures as optimistic concurrency preconditions. Announce success/error through accessible live regions. Never replace the displayed AI draft; show corrected effective text and retain a collapsible original draft.

**Step 6: Apply quiet research-workbench styling**

Create token variables for paper, ink, evidence blue, review green, warning amber, and conflict red. Keep a stable three-region desktop layout, two-region tablet fallback, and single-column readable narrow layout. Avoid gratuitous gradients, glass effects, and dashboard cards.

**Step 7: Verify tests, coverage, and build**

```bash
npm --prefix frontend run test:coverage
npm --prefix frontend run build
```

Expected: all tests pass and configured coverage thresholds remain satisfied.

**Step 8: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/ResearchMap.tsx frontend/src/ResearchMap.test.tsx frontend/src/EvidenceInspector.tsx frontend/src/EvidenceInspector.test.tsx frontend/src/GuidedReview.tsx frontend/src/GuidedReview.test.tsx frontend/src/styles.css
git commit -m "feat: add verifiable research map workspace"
```

### Task 10: Link Map evidence to Reader blocks and expose Library progress

**Files:**
- Modify: `frontend/src/Reader.tsx`
- Modify: `frontend/src/Reader.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/types.ts`
- Modify: `backend/src/glyph/research_schemas.py`
- Modify: `backend/tests/test_research_api.py`

**Step 1: Write failing integration-oriented component tests**

Prove:

- `View in Reader` selects and focuses `reader-row-{block_id}`;
- returning to Map restores the research node and inspector;
- the focused Reader row identifies which map nodes cite it;
- Library rows show `verified / reviewable core nodes`, partial issue count, and current/stale status;
- unprocessed documents still offer Full Reader behavior unchanged.

**Step 2: Verify RED**

Run: `npm --prefix frontend test -- --run src/App.test.tsx src/Reader.test.tsx`

Expected: new linking/progress expectations fail.

**Step 3: Add stable Reader block anchors**

Use the existing block ID DOM identifiers and focus after mode transition. Add an accessible temporary focus highlight and `aria-current` semantics. Do not scroll by coordinates.

**Step 4: Add compact map summaries to Library data flow**

Return map summary information from a batched endpoint or extend document listing with an explicitly nested optional summary. Avoid one request per document. Preserve compatibility for clients that ignore the field.

**Step 5: Verify backend/frontend focused tests**

```bash
.venv/bin/pytest backend/tests/test_research_api.py backend/tests/test_documents.py -q
npm --prefix frontend test -- --run src/App.test.tsx src/Reader.test.tsx
```

Expected: all pass.

**Step 6: Commit**

```bash
git add backend/src/glyph/research_schemas.py backend/tests frontend/src
git commit -m "feat: connect research maps to source reading"
```

### Task 11: Verify accessibility, resilience, benchmark behavior, and documentation

**Files:**
- Create: `backend/tests/test_research_benchmark.py`
- Create: `docs/research-map.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `CONTRIBUTING.md`
- Modify: `SECURITY.md`
- Modify: `.github/workflows/ci.yml` if commands change
- Modify if needed: `docs/plans/2026-08-12-research-map-design.md`

**Step 1: Add deterministic benchmark acceptance test**

Process the synthetic empirical-finance fixture with mock OCR/AI. Assert the six core categories, exact anchors, expected not-reported transaction-cost issue, primary result statistical evidence, deterministic output across two runs, and bounded generation time without using a flaky absolute wall-clock assertion in CI.

**Step 2: Run the benchmark to verify any missing contract**

Run: `.venv/bin/pytest backend/tests/test_research_benchmark.py -q`

Expected: PASS only when the whole backend pipeline is integrated.

**Step 3: Perform an accessibility pass**

Use semantic tests plus browser inspection to verify keyboard traversal, visible focus, headings/regions, live error announcements, contrast, inspector focus management, and 1280px/768px/narrow layouts. Fix issues with focused regression tests first.

**Step 4: Document operation and trust boundaries**

Explain generation stages, local provider data flow, evidence guarantees and limitations, human review semantics, source staleness, job recovery, environment variables, backup/migration guidance, and that Glyph does not independently validate scientific truth.

**Step 5: Run every quality gate from a clean dependency install**

```bash
.venv/bin/ruff check backend/src backend/tests
.venv/bin/ruff format --check backend/src backend/tests
.venv/bin/mypy backend/src/glyph
.venv/bin/pytest --cov=glyph --cov-report=term-missing --cov-fail-under=85
.venv/bin/bandit -q -r backend/src/glyph
.venv/bin/pip-audit
cd frontend
npm ci
npm audit --audit-level=high
npm run test:coverage
npm run build
```

Expected: every command exits zero.

**Step 6: Run the full browser smoke test**

With isolated mock data:

1. Upload the synthetic paper and process the Reader.
2. Enqueue a map and observe real stage progress without request blocking.
3. Complete the guided review, open exact evidence, confirm one node, question one, and correct one.
4. Restart services and prove the map and reviews persist.
5. Change source bytes, observe stale state, reprocess and regenerate.
6. Inspect the version diff and prove the correction was preserved or explicitly marked for review, never silently overwritten.
7. Inject provider/persistence failure and prove the previous active map remains usable.
8. Confirm no browser console errors and no runtime artifacts are tracked.

**Step 7: Write a completion audit**

Create `docs/plans/2026-08-12-research-map-audit.md` mapping every invariant and acceptance criterion to a test, API response, migration result, or browser observation.

**Step 8: Commit**

```bash
git add README.md CHANGELOG.md CONTRIBUTING.md SECURITY.md .github docs backend/tests/test_research_benchmark.py
git commit -m "docs: complete research map milestone"
```

### Task 12: Final repository and integration audit

**Files:**
- Modify only if verification uncovers a defect.

**Step 1: Re-run the complete suites**

Run the exact backend and frontend gate sets from Task 11 again after the documentation commit.

**Step 2: Inspect migration head and upgrade paths**

Run fresh, legacy, and reliability-baseline databases through Alembic head. Confirm map tables are added and all pre-existing rows survive.

**Step 3: Inspect repository hygiene**

```bash
git diff --check
git status --short
git log --oneline --decorate main..HEAD
git ls-files | rg '^(data/|book/(?!\.gitkeep$))' -P
```

Expected: clean worktree, reviewable commits, and no tracked runtime data.

**Step 4: Review goal scope**

Confirm Formula Workspace, cross-paper graph, cloud sync, accounts, collaboration, and investment advice did not enter the implementation. Record them only as later milestones.

**Step 5: Use the finishing-a-development-branch skill**

Present merge, PR, keep, and discard options only after every check passes.
