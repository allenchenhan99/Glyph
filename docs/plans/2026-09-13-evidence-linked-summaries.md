# Evidence-linked summaries implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Reader summary placeholders with explicitly generated document and section summaries whose quotes resolve to exact source blocks, while retaining prior versions on failure.

**Architecture:** Store immutable summary versions and normalized evidence references independently from disposable Reader summary strings. Generate through a persistent local job with short transactions, then validate both the source hash and a fingerprint of the exact current Reader block set before atomic publication. The existing research AI configuration selects a mock or Claude/Codex CLI provider; translation configuration remains separate and no summary request occurs automatically.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, existing CLI JSON runner, React/TypeScript, pytest and Vitest.

## Contract and boundaries

- `GET /api/documents/{id}/summaries` returns `{status, provider, model, version, job}`. Status is `not_generated`, `generating`, `available`, `stale`, or `failed`. A failed/generating response can retain a previous `version`.
- `POST /api/documents/{id}/summaries` returns HTTP 202 with the same response shape. Duplicate active work returns 409; an absent or stale current Reader cannot generate. Reloading the GET endpoint observes persistent job state; no automatic retry on restart.
- `job` is null or `{id, status, error_message}`; statuses are queued/running/completed/failed/interrupted.
- `version` is null or `{id, source_content_hash, reader_fingerprint, provider, model, created_at, claims}`.
- Each claim is `{id, section_path, text, evidence}`. Null `section_path` identifies the document overview. Other paths must identify a current section. Each evidence item is `{block_id, quote_text, quote_start, quote_end, page_number}`.
- Every published claim needs at least one exact, nonempty quote from the permitted Reader block set; section claims cite their own section. Reject invented IDs, mismatched/ambiguous quotes, bad offsets, foreign blocks and malformed output. Evidence matching proves quotation integrity, not semantic entailment: all generated claims remain labeled AI drafts, never verified findings.
- Include overview and meaningful section coverage, with bounded prompts/batches and explicit failures for unsupported limits instead of silent truncation. Mock output is explicitly labeled development output and uses source-derived excerpts.
- Source hash alone is insufficient after identical-file reprocessing. Current inputs select attached blocks (`section_id IS NOT NULL`) and fingerprint their IDs/order/text. Recheck identity at publication. Retained citations must not produce duplicate default Reader rows; explicit historical Reader requests must continue to navigate existing Research Map/Contract evidence.
- Failed or interrupted generation never deletes the previous version. When its Reader changes, show that version as stale with retained quotes; only navigate directly when the cited block exists in the displayed Reader.
- Keep credentials out of jobs, errors and persistent versions. Do not send private local documents for evaluation.

## Task 1: Domain, persistence, and evidence validation (backend)

Create `summary_domain.py`, `summaries.py`, `summary_schemas.py`, and migration `0007_document_summaries.py`; modify `models.py` and `pipeline.py` for citation retention. Add failing tests for exact evidence, foreign/missing blocks, wrong offsets, section coverage, same-file reprocessing, and migration preservation. Implement immutable versions/evidence and active-job uniqueness, then pass those tests. Stop exposing deterministic legacy strings as real summaries; preserve legacy stored data.

## Task 2: Provider and durable generation (backend)

Create `summary_ai.py`, `summary_cli_ai.py`, `summary_jobs.py`, and `summary_routes.py`; register in `main.py`. Reuse public exact-quote and CLI/cache helpers rather than private Research Map ontology internals. Add failing tests for real structured CLI responses, malformed output, bounded requests, safe provider errors, quick enqueue, duplicate requests, process restart, stale worker/publication and executor rejection. Snapshot inputs before external calls, publish with short atomic transactions, and preserve the prior version on failure. Use only isolated `GLYPH_DATA_DIR` and `GLYPH_BOOK_DIR` for commands importing the application.

## Task 3: Reader summary interaction (frontend)

Create `SummaryPanel.tsx` and its tests; add API guards/types in `api.ts`, `api.test.ts`, and `types.ts`; integrate with `Reader.tsx` and update `Reader.test.tsx`. Add failing tests for not-generated state without placeholders, explicit generation, restored polling, failure retaining a prior version, stale state, mock/AI-draft labels, and keyboard evidence navigation. Display document and section claims with expandable exact quotes. Clean up polling on unmount/document changes and reject stale responses. Existing Map/Contract Reader navigation remains functional.

## Task 4: Verification and integration

Run backend lint/format/types, full pytest coverage (85% minimum), Bandit and dependency audit; run frontend coverage, dependency audit and production build. Exercise generation/reload/evidence navigation/failure recovery in the visible browser with isolated deterministic fixtures. Clearly distinguish these checks from live model quality. Update README, processing guidance and milestone evidence; use a focused PR and merge only after CI passes.
