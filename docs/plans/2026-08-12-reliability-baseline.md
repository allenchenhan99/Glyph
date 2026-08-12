# Glyph Reliability Baseline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Glyph preserve user data, correctly track document freshness, safely accept uploads and run external tools, and enforce the same quality gates locally and in CI.

**Architecture:** Keep the FastAPI/SQLite/React stack. Add an Alembic-backed compatible schema lifecycle, explicit document freshness hashes, bounded input/process boundaries, and savepoint-protected reader-output replacement. Preserve the synchronous API for now while isolating invariants that a later background worker can reuse.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, Alembic, SQLite, pytest, Ruff, mypy, Bandit, pip-audit, React 19, TypeScript, Vite, Vitest, GitHub Actions.

---

### Task 1: Establish deterministic backend quality tooling

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/glyph/ai.py`
- Modify: `backend/src/glyph/cli_ai.py`
- Modify: `backend/src/glyph/config.py`
- Modify: `backend/src/glyph/database.py`
- Modify: `backend/src/glyph/documents.py`
- Modify: `backend/src/glyph/models.py`
- Modify: `backend/src/glyph/ocr.py`
- Modify: `backend/src/glyph/pipeline.py`
- Modify: `backend/tests/*.py`

**Step 1: Add development dependencies and tool policy**

Add Alembic to runtime dependencies because application startup executes migrations. Add a `dev` optional dependency group containing Bandit, mypy, pip-audit, pytest-cov, and Ruff. Configure Python 3.11, an 88-character line length, project source paths, and only reviewed Bandit exclusions. Do not globally ignore subprocess findings before Task 6 has resolved them.

**Step 2: Install the development dependency group**

Run: `.venv/bin/python -m pip install -e 'backend[dev]'`

Expected: installation succeeds and `.venv/bin/ruff`, `.venv/bin/mypy`, and `.venv/bin/alembic` exist.

**Step 3: Verify the quality commands expose current failures**

Run:

```bash
.venv/bin/ruff check backend/src backend/tests
.venv/bin/ruff format --check backend/src backend/tests
.venv/bin/mypy backend/src/glyph
```

Expected: Ruff reports the known import/style issues and mypy reports nullable cache-path errors. These failures prove the new gates exercise the current code.

**Step 4: Apply mechanical formatting and minimal type fixes**

Run `.venv/bin/ruff check --fix backend/src backend/tests` and `.venv/bin/ruff format backend/src backend/tests`. Fix remaining findings manually without changing behavior. Narrow `cache_path` before path operations so mypy can prove it is not `None`.

**Step 5: Run the complete baseline after formatting**

Run:

```bash
.venv/bin/ruff check backend/src backend/tests
.venv/bin/ruff format --check backend/src backend/tests
.venv/bin/mypy backend/src/glyph
.venv/bin/pytest -q
```

Expected: all commands pass; pytest still reports 26 passing tests before later tasks add coverage.

**Step 6: Commit**

```bash
git add backend
git commit -m "chore: establish backend quality tooling"
```

### Task 2: Replace ad-hoc schema setup with compatible migrations

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/script.py.mako`
- Create: `backend/migrations/versions/0001_legacy_baseline.py`
- Create: `backend/migrations/versions/0002_reliability_fields.py`
- Modify: `backend/src/glyph/database.py`
- Modify: `backend/src/glyph/models.py`
- Modify: `backend/tests/test_database.py`

**Step 1: Write failing migration tests**

Add tests that:

```python
def test_empty_database_is_created_at_migration_head(tmp_path): ...

def test_legacy_database_is_stamped_and_preserves_document_data(tmp_path): ...

def test_completed_legacy_document_backfills_processed_hash(tmp_path): ...

def test_unrecognized_partial_schema_fails_without_dropping_tables(tmp_path): ...
```

The legacy fixture must create the public-release tables with SQL, insert a completed document and reader block, and omit `alembic_version`.

**Step 2: Run tests to verify RED**

Run: `.venv/bin/pytest backend/tests/test_database.py -q`

Expected: FAIL because migration-head creation and `processed_content_hash` do not exist.

**Step 3: Add migration revisions**

`0001_legacy_baseline` creates the public-release schema, including `formula_latex`. `0002_reliability_fields` adds nullable `documents.processed_content_hash` and backfills it from `content_hash` only for completed documents.

**Step 4: Add the compatibility bootstrap**

Implement `upgrade_database(settings)` so that it:

1. Runs Alembic to head for an empty database.
2. Detects the exact legacy table set when no version table exists.
3. Adds the historical `formula_latex` column if absent.
4. Stamps `0001_legacy_baseline` and upgrades to head.
5. Rejects unknown partial schemas with a descriptive exception.

Remove `Base.metadata.create_all()` and the one-off migration call from normal startup.

**Step 5: Run focused and complete tests**

Run:

```bash
.venv/bin/pytest backend/tests/test_database.py -q
.venv/bin/pytest -q
```

Expected: migration tests pass and existing API tests remain green.

**Step 6: Commit**

```bash
git add backend/alembic.ini backend/migrations backend/src/glyph/database.py backend/src/glyph/models.py backend/tests/test_database.py
git commit -m "feat: add compatible database migrations"
```

### Task 3: Unify the document catalog and freshness lifecycle

**Files:**
- Modify: `backend/src/glyph/documents.py`
- Modify: `backend/src/glyph/models.py`
- Modify: `backend/src/glyph/schemas.py`
- Modify: `backend/src/glyph/pipeline.py`
- Modify: `backend/tests/test_documents.py`
- Modify: `backend/tests/test_reader_payload.py`
- Modify: `backend/tests/test_uploads.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/Reader.test.tsx`

**Step 1: Write a failing uploaded-document listing test**

Extend `test_uploads.py`:

```python
def test_uploaded_document_remains_in_catalog_after_refresh_and_restart(...):
    uploaded = first_client.post(...).json()
    assert uploaded["id"] in {item["id"] for item in first_client.get("/api/documents").json()}
    second_client = TestClient(create_app())
    assert uploaded["id"] in {item["id"] for item in second_client.get("/api/documents").json()}
```

**Step 2: Verify RED**

Run: `.venv/bin/pytest backend/tests/test_uploads.py::test_uploaded_document_remains_in_catalog_after_refresh_and_restart -q`

Expected: FAIL because the list route only returns discovered `book/` files.

**Step 3: Implement the unified catalog query**

Synchronize `book/`, flush changes, then select all registered documents ordered by creation time and title. Remove `source_path` from `DocumentOut` so API responses do not expose absolute local paths.

**Step 4: Test source freshness and missing files**

Add failing tests proving:

- Completed unchanged files remain `completed`.
- Changing bytes changes `content_hash`, preserves reader rows, and marks the document `stale`.
- Removing a source marks the document `missing` without deleting database rows.
- Restoring a missing source re-evaluates it as `completed`, `stale`, or unprocessed based on hashes.

Run the focused tests and confirm each fails for the missing lifecycle behavior.

**Step 5: Implement lifecycle transitions**

Compare the old and new source hashes in registration. Store the successful hash after processing. Centralize stable-status calculation rather than scattering string assignments across routes.

**Step 6: Expose stale reader state safely**

Keep last-good blocks readable when present, but ensure the reader's document status is `stale`. A missing source may expose stored text but page rendering and processing must return a specific conflict/error response.

**Step 7: Run catalog and reader tests**

Run:

```bash
.venv/bin/pytest backend/tests/test_documents.py backend/tests/test_uploads.py backend/tests/test_reader_payload.py -q
.venv/bin/pytest -q
```

Expected: all tests pass.

**Step 8: Commit**

```bash
git add backend/src/glyph backend/tests
git commit -m "fix: preserve uploads and track document freshness"
```

### Task 4: Stream and validate uploads safely

**Files:**
- Modify: `.env.example`
- Modify: `backend/src/glyph/config.py`
- Modify: `backend/src/glyph/documents.py`
- Modify: `backend/tests/test_config.py`
- Modify: `backend/tests/test_uploads.py`

**Step 1: Write failing upload-boundary tests**

Add separate tests for:

- Valid PDF, PNG, and JPEG signatures.
- Extension/signature mismatch returning HTTP 400.
- Payload larger than `GLYPH_MAX_UPLOAD_BYTES` returning HTTP 413.
- Temporary-file cleanup after both rejection paths.
- Two uploads named `paper.pdf` receiving distinct IDs and storage paths while both retain the title `paper.pdf`.
- A path-like filename being reduced to its basename.

**Step 2: Verify RED**

Run: `.venv/bin/pytest backend/tests/test_uploads.py -q`

Expected: new signature, limit, cleanup, and duplicate tests fail.

**Step 3: Add validated settings**

Add `max_upload_bytes` with a 50 MiB default and reject non-positive environment values during settings creation. Document the environment variable in `.env.example`.

**Step 4: Implement bounded streaming**

Read `UploadFile` in 1 MiB chunks into a UUID-named temporary file under `data/uploads`. Stop immediately after the configured maximum, close and delete the temporary file, and raise HTTP 413.

Validate the leading bytes against the normalized extension. On success, atomically rename the temporary file to its UUID-based final name and register the original basename as `title`.

**Step 5: Run focused and full tests**

Run:

```bash
.venv/bin/pytest backend/tests/test_config.py backend/tests/test_uploads.py -q
.venv/bin/pytest -q
```

Expected: all pass and rejected uploads leave no files behind.

**Step 6: Commit**

```bash
git add .env.example backend/src/glyph/config.py backend/src/glyph/documents.py backend/tests
git commit -m "feat: enforce safe bounded uploads"
```

### Task 5: Make reader-output replacement atomic and conflict-safe

**Files:**
- Modify: `backend/src/glyph/pipeline.py`
- Modify: `backend/src/glyph/documents.py`
- Modify: `backend/tests/test_pipeline.py`
- Modify: `backend/tests/test_documents.py`

**Step 1: Strengthen the reprocessing regression test**

Change the failure injection so it raises after `clear_document_outputs()` and at least one new page insert, not during AI parsing. Assert the old blocks, pages, sections, summaries, status, and processed hash are unchanged.

**Step 2: Verify RED**

Run: `.venv/bin/pytest backend/tests/test_pipeline.py::test_persistence_failure_keeps_last_good_reader_snapshot -q`

Expected: FAIL because the caught exception lets the outer request commit deletion or partial replacement.

**Step 3: Implement savepoint-protected replacement**

Perform OCR and AI parsing first. Wrap deletion, all output inserts, `processed_content_hash`, and completed status in `session.begin_nested()`, then flush inside the savepoint. On failure, restore the pre-job stable status and record the failed job outside the savepoint.

**Step 4: Add first-attempt failure coverage**

Prove a persistence failure on a never-processed document creates no pages, blocks, sections, or summaries and marks only the job/document failure state.

**Step 5: Add same-document conflict coverage**

Use two test threads and a blocking fake adapter. While the first request holds the document processing lock, assert a second request returns HTTP 409 and creates no competing job.

**Step 6: Implement the process-local coordinator**

Add a small lock registry with non-blocking acquisition keyed by document ID. Always release in `finally`. Keep it independent of FastAPI so a later worker can replace it.

**Step 7: Run focused and full tests**

Run:

```bash
.venv/bin/pytest backend/tests/test_pipeline.py backend/tests/test_documents.py -q
.venv/bin/pytest -q
```

Expected: atomicity and conflict tests pass.

**Step 8: Commit**

```bash
git add backend/src/glyph/pipeline.py backend/src/glyph/documents.py backend/tests
git commit -m "fix: replace reader snapshots atomically"
```

### Task 6: Bound every external process

**Files:**
- Modify: `.env.example`
- Modify: `backend/src/glyph/config.py`
- Modify: `backend/src/glyph/ocr.py`
- Modify: `backend/src/glyph/documents.py`
- Modify: `backend/tests/test_ocr.py`
- Modify: `backend/tests/test_documents.py`

**Step 1: Write timeout tests first**

Monkeypatch `subprocess.run` to raise `subprocess.TimeoutExpired` for:

- `pdftotext` extraction.
- Unlimited-OCR command execution.
- `pdftoppm` page rendering.

Assert each call receives the configured timeout and maps to a concise domain/API error without an absolute path.

**Step 2: Verify RED**

Run: `.venv/bin/pytest backend/tests/test_ocr.py backend/tests/test_documents.py -q`

Expected: timeout assertions fail because OCR/page rendering currently omit limits.

**Step 3: Add timeout settings**

Add positive integer `ocr_timeout_seconds` and `page_render_timeout_seconds`, with defaults of 300 and 30 seconds. Document both variables.

**Step 4: Resolve and execute safely**

Resolve `pdftotext` and `pdftoppm` with `shutil.which`, pass explicit argument arrays and timeouts, keep `shell=False`, and convert `TimeoutExpired` into stable errors. Limit stored/displayed stderr to a short suffix and never include document contents or absolute paths.

**Step 5: Run security/static checks**

Run:

```bash
.venv/bin/pytest -q
.venv/bin/bandit -q -r backend/src/glyph
.venv/bin/ruff check backend/src backend/tests
.venv/bin/mypy backend/src/glyph
```

Expected: tests/static checks pass. Any remaining low Bandit subprocess warnings must be locally justified with narrow `# nosec` annotations, never a broad global skip.

**Step 6: Commit**

```bash
git add .env.example backend/src/glyph backend/tests
git commit -m "fix: bound external document processes"
```

### Task 7: Surface stale state and actionable errors in the frontend

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/Reader.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/Reader.test.tsx`

**Step 1: Write failing API-error and stale-state tests**

Add tests proving:

- A backend `{ "detail": "..." }` response becomes the visible message.
- A stale document card is labeled clearly.
- Opening last-good stale output displays a warning that it was generated from an older source.
- A processing conflict does not falsely display `Processed ...`.

**Step 2: Verify RED**

Run: `npm test -- --run`

Expected: new tests fail because API helpers discard details and Reader has no stale warning.

**Step 3: Implement typed API errors**

Create a small `ApiError` carrying HTTP status and safe backend detail. Ensure non-JSON responses still produce a stable fallback.

**Step 4: Implement lifecycle messaging**

Render stale/missing status in the library and a semantic `role="alert"` warning in the reader. Keep the current visual language; do not redesign unrelated components.

**Step 5: Verify frontend**

Run:

```bash
npm test -- --run
npm run build
```

Expected: all tests and TypeScript production build pass.

**Step 6: Commit**

```bash
git add frontend/src
git commit -m "fix: explain stale documents and API failures"
```

### Task 8: Add reproducible CI, dependency maintenance, and contributor guidance

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/dependabot.yml`
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Modify: `README.md`
- Modify: `frontend/package-lock.json`
- Modify: `scripts/setup.sh`

**Step 1: Repair audited frontend transitive dependencies**

Run `npm audit fix`, inspect the lockfile diff, then run:

```bash
npm audit --audit-level=high
npm test -- --run
npm run build
```

Expected: zero high vulnerabilities, tests pass, build succeeds, and only compatible transitive versions change.

**Step 2: Add CI workflow**

Create separate backend and frontend jobs on pull requests and pushes to `main`. Pin action major versions, use Python 3.11 and Node 22, cache dependencies, install `poppler-utils`, and run exactly the documented local gates. Backend coverage must be at least 85%.

**Step 3: Add dependency maintenance**

Configure weekly Dependabot updates for pip, npm, and GitHub Actions, with small open-PR limits.

**Step 4: Add contributor and security docs**

Document setup, architecture boundaries, TDD expectations, quality commands, issue/PR expectations, supported local deployment, private vulnerability reporting, data backup, migration behavior, new environment variables, and the fact that uploaded document contents may be sent to the selected CLI provider.

**Step 5: Make local setup install the tested dev environment**

Update setup so contributors receive the same backend tools CI runs. Keep runtime use simple and idempotent.

**Step 6: Validate workflow syntax and all commands locally**

Run the backend and frontend command sets from a clean shell. Parse workflow YAML with an available parser or Python YAML dependency to catch syntax errors.

**Step 7: Commit**

```bash
git add .github CONTRIBUTING.md SECURITY.md README.md frontend/package-lock.json scripts/setup.sh
git commit -m "ci: enforce reliability quality gates"
```

### Task 9: Perform the completion audit and smoke test

**Files:**
- Modify if needed: `docs/plans/2026-08-12-reliability-baseline-design.md`
- Modify if needed: `README.md`

**Step 1: Run every backend gate**

```bash
.venv/bin/ruff check backend/src backend/tests
.venv/bin/ruff format --check backend/src backend/tests
.venv/bin/mypy backend/src/glyph
.venv/bin/pytest --cov=glyph --cov-report=term-missing --cov-fail-under=85
.venv/bin/bandit -q -r backend/src/glyph
.venv/bin/pip-audit
```

Expected: every command exits zero.

**Step 2: Run every frontend gate**

```bash
cd frontend
npm ci
npm audit --audit-level=high
npm test -- --run
npm run build
```

Expected: every command exits zero.

**Step 3: Run a manual local smoke test**

Start Glyph in mock mode, upload a valid small PDF, refresh/restart, process it, open the reader, mutate a `book/` source, observe the stale warning, and inject an adapter failure during reprocessing. Confirm the last-good reader content remains intact.

**Step 4: Audit each design requirement against evidence**

Map every design goal to a test, command, migration result, API response, or rendered UI state. Treat missing evidence as incomplete and fix it before claiming completion.

**Step 5: Verify repository hygiene**

Run:

```bash
git diff --check
git status --short
git log --oneline --decorate -12
```

Expected: no uncommitted files, no generated data tracked, and the history contains the planned reviewable commits.

**Step 6: Commit any final documentation corrections**

```bash
git add README.md docs
git commit -m "docs: finalize reliability baseline guidance"
```

Skip this commit if no documentation changes are necessary.
