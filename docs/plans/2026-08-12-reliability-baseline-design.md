# Glyph Reliability Baseline Design

## Status

Implemented and verified on 2026-08-12. The project owner delegated the first-stage plan decision, and the completed design preserves existing SQLite data and previously processed reader content by default. See the [completion audit](2026-08-12-reliability-baseline-audit.md) for traceable evidence.

## Product boundary

Glyph remains a local-first FastAPI, SQLite, and React application for aligned source and Traditional Chinese reading. This stage hardens the existing product promise; it does not add chat, collaboration, cloud accounts, or a distributed worker system.

## Goals

1. Uploaded documents remain visible after refresh and restart.
2. A failed first processing attempt records a failed job without partial reader data.
3. A failed reprocessing attempt preserves the last successful reader data.
4. A changed source file is explicitly marked stale and never presented as current output.
5. Existing SQLite databases migrate in place without deleting user data.
6. Upload and external-process boundaries enforce file type, size, timeout, and safe-path rules.
7. CI enforces backend tests, frontend tests, production build, formatting, lint, type checking, dependency auditing, and a coverage floor.

## Non-goals

- Background workers, cancellation, or distributed job queues.
- Search, annotations, bookmarks, or reading-progress persistence.
- Replacing SQLite or rewriting the React interface.
- Improving AI summaries, section hierarchy, or virtualized rendering.
- Authentication or exposing Glyph as a network service.

## Considered approaches

### A. Patch individual routes

Change the list query, add a few upload checks, and wrap the existing pipeline in error handling. This is the smallest diff, but it leaves persistence rules distributed across route handlers and makes later worker extraction risky. It also does not provide a credible migration or quality-gate story.

### B. Incremental reliability boundary — selected

Keep the current stack and API shape while making document lifecycle, migrations, input validation, and output replacement explicit. OCR and AI work still run synchronously, but expensive work finishes before a savepoint-protected output replacement. Existing data remains readable, and the boundary can later move behind a worker without changing reader persistence semantics.

This gives the best balance of low migration risk, testability, and forward compatibility.

### C. Queue-first rewrite

Introduce a worker, broker, repository layer, and new job API immediately. This solves future scale concerns but combines product correctness, deployment complexity, and schema migration in one release. It is too risky for a codebase with no CI or release history.

## Architecture

### Document catalog and lifecycle

`GET /api/documents` first synchronizes supported files from `book/`, then queries the database for every registered document, including uploads. Missing local files remain registered but are marked `missing`; they are not silently deleted.

The document stores two hashes:

- `content_hash`: the current source bytes.
- `processed_content_hash`: the source bytes used by the last successful reader output.

Lifecycle rules:

- A new book file is `discovered`; a new upload is `uploaded`.
- Successful processing sets `processed_content_hash = content_hash` and status `completed`.
- Discovery of changed bytes preserves existing output and sets status `stale`.
- A reader may show last-good stale output only with an explicit stale warning.
- A missing source cannot be processed or rendered and is marked `missing`.
- Failed initial processing sets the document to `failed`.
- Failed reprocessing restores the prior stable status (`completed` or `stale`) while the job records the failure.

This separates job outcome from the validity of the last successful document output.

### Compatible database migrations

Alembic becomes the schema authority. A new database is created by migrations. On an existing Glyph database without an Alembic version, startup validates the recognizable legacy tables, applies the existing `formula_latex` compatibility fix if needed, stamps the legacy baseline, and upgrades forward. Unknown or partially incompatible schemas fail with an actionable error instead of being recreated.

The reliability migration adds nullable `processed_content_hash`, so old documents remain valid records. Existing completed documents are backfilled from `content_hash`, because their output was produced before the hashes could diverge.

### Atomic processing

OCR and AI parsing build an in-memory `ParsedDocument` before any reader output is deleted. Replacement of pages, sections, blocks, summaries, document status, and `processed_content_hash` occurs inside one database savepoint and is flushed before the savepoint commits.

If replacement fails, the savepoint rolls back all output mutations. The outer request transaction then records a failed job and restores the document's previous stable status. Tests inject a failure after deletion has begun to prove rollback behavior, rather than only simulating an AI failure before persistence.

Overlapping processing of the same document is rejected with HTTP 409 through a process-local per-document lock. This is sufficient for the supported single-process local deployment; moving this invariant to a durable worker lease is deferred to the background-job stage.

### Upload safety

Uploads are streamed to a temporary file in bounded chunks. The server rejects a request when it exceeds the configurable byte limit, deletes the temporary file, and returns HTTP 413. It validates both the normalized extension and file signature for PDF, PNG, and JPEG.

Accepted files are atomically moved to a UUID-based storage name under `data/uploads`; the original sanitized filename remains the user-facing title. Existing files are never overwritten by a same-name upload.

Defaults and environment variables:

- `GLYPH_MAX_UPLOAD_BYTES`: 50 MiB.
- `GLYPH_OCR_TIMEOUT_SECONDS`: 300 seconds.
- `GLYPH_PAGE_RENDER_TIMEOUT_SECONDS`: 30 seconds.

All external commands use argument arrays with `shell=False`, resolved executables, explicit timeouts, captured output, and bounded error messages. Timeout failures become domain errors and never leave partial output committed.

### API and UI behavior

The existing endpoints remain stable. `DocumentOut.status` gains the meaningful `stale` and `missing` states. The reader displays a visible warning when opening last-good stale output. The frontend preserves backend error details for size, type, missing-source, conflict, and timeout failures instead of replacing them with one generic message.

### Quality gates

Python development dependencies and tool configuration live in `backend/pyproject.toml`. The local and CI commands are deterministic:

- `ruff check backend/src backend/tests`
- `ruff format --check backend/src backend/tests`
- `mypy backend/src/glyph`
- `pytest --cov=glyph --cov-fail-under=85`
- `bandit -q -r backend/src/glyph` with reviewed subprocess findings configured explicitly
- `pip-audit`
- `npm ci`
- `npm audit --audit-level=high`
- `npm test -- --run`
- `npm run build`

GitHub Actions runs backend and frontend jobs on pull requests and pushes to `main`. Dependabot tracks Python and npm dependencies weekly.

## Error handling and observability

Expected input and process failures use domain exceptions mapped to stable HTTP status codes. Job errors store a concise safe message; full tracebacks go to structured application logs. Absolute local paths are removed from public document payloads and error messages.

The health endpoint remains lightweight. It does not claim OCR or AI readiness; richer readiness diagnostics belong to a later operational stage.

## Testing strategy

Every behavior change follows red-green-refactor. Required integration tests cover:

1. Upload, list, restart, and duplicate-name behavior.
2. File-size and signature rejection with temporary-file cleanup.
3. Source hash changes and stale reader signaling.
4. Initial processing failure with no partial data.
5. Persistence-stage reprocessing failure with last-good data intact.
6. Successful reprocessing atomically replacing all old outputs.
7. Same-document processing conflict.
8. Legacy database migration and data preservation.
9. External command timeout mapping.
10. Frontend rendering of stale state and actionable API errors.

The final verification also runs the complete backend/frontend suites, production build, static checks, dependency audits, and a manual local upload/process/read smoke test.

## Rollout

Changes are split into reviewable commits: test/tool baseline, migrations, catalog lifecycle, upload safety, atomic processing, subprocess limits, frontend error states, and CI/documentation. No destructive database reset is part of setup or upgrade. The release notes will call this the reliability baseline and document new environment variables and migration backup guidance.
