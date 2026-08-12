# Glyph Reliability Baseline Completion Audit

## Result

The reliability baseline was completed and verified on 2026-08-12. All seven design goals have automated or end-to-end evidence, every documented quality gate exits successfully, and no smoke-test runtime data is part of the repository.

## Goal traceability

| Design goal | Evidence |
| --- | --- |
| Uploads survive refresh and restart | `test_uploaded_document_remains_in_catalog_after_refresh_and_restart`; browser smoke uploaded `smoke-upload.pdf`, refreshed, restarted both services, and found the same catalog entry. |
| Initial processing failures leave no partial reader | `test_initial_persistence_failure_leaves_no_reader_snapshot` verifies empty pages, blocks, sections, and summaries plus a failed job. |
| Failed reprocessing preserves last-good data | `test_persistence_failure_keeps_last_good_reader_snapshot` injects failure after new persistence begins and compares the complete reader snapshot; browser smoke injected an unconfigured OCR adapter and retained the old rendered text. |
| Changed sources are explicitly stale | Document lifecycle tests cover changed, missing, restored, and unchanged sources; Reader tests require a `role=alert` stale warning; browser smoke observed both the stale card label and warning while old content remained visible. |
| Existing databases migrate without deletion | Database tests create new schemas at Alembic head, migrate the public legacy schema, backfill successful hashes, preserve reader data, and reject unknown partial schemas. |
| File and process boundaries are bounded | Upload tests cover signatures, size, cleanup, basename handling, and same-name isolation. OCR/CLI tests cover executable resolution, argv execution, timeouts, sanitized errors, and content-addressed page-image caching. Bandit reports no findings. |
| CI enforces the local quality contract | `.github/workflows/ci.yml` contains independent backend and frontend jobs; the workflow YAML was parsed locally, and Dependabot covers pip, npm, and GitHub Actions. |

Additional contract evidence discovered during the smoke test is captured by the frontend test `treats a failed processing job as an error even when the request succeeded`. Backend processing now distinguishes a failed job resource from HTTP transport success and sanitizes unexpected internal failures before returning `error_message`.

## Final automated verification

Backend commands and results:

- Ruff lint: passed.
- Ruff format check: 21 files formatted.
- mypy: 11 source files checked with no issues.
- pytest: 54 tests passed.
- coverage: 89.99%, above the required 85% floor.
- Bandit: exited successfully with no findings.
- pip-audit: no known third-party vulnerabilities; the local editable `glyph-backend` package is intentionally not a PyPI audit target.

Frontend commands and results after a clean `npm ci`:

- npm audit: 0 vulnerabilities.
- Vitest: 13 tests passed.
- coverage: 70.07% statements, 45.45% branches, 67.44% functions, and 70.49% lines; all configured thresholds passed.
- TypeScript and Vite production build: passed.

## Manual browser smoke test

Glyph ran with isolated local data and mock AI. The test:

1. Uploaded a signature-valid small PDF and confirmed it remained after refresh and a full service restart.
2. Processed the upload and opened its aligned source/Traditional Chinese reader.
3. Processed a `book/` document, changed its source bytes, refreshed, and observed `Source changed — reprocess required`.
4. Reopened the reader and observed the stale alert while version-one text remained visible.
5. Restarted with an intentionally unconfigured Unlimited-OCR adapter and reprocessed the stale document.
6. Observed the safe adapter error, no false `Processed` message, the stale state, and the unchanged old reader content.
7. Confirmed the browser console contained no errors.

## Remaining product boundary

This milestone makes the supported trusted, single-user local deployment reliable; it does not turn the Vite/FastAPI development servers into an authenticated network service. Background jobs, cancellation, distributed coordination, generated AI summaries, stable releases, and hosted deployment remain later milestones rather than hidden claims of this baseline.
