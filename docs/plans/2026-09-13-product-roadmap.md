# Glyph product milestones

Status: active. Approved by the user on 2026-09-13; execute in order, record evidence before marking a milestone complete.

## Stage 1 — Reliable document processing (complete)

Integrated in [PR #10](https://github.com/allenchenhan99/Glyph/pull/10), squash commit `077921e`. Both GitHub CI jobs passed; the merged tree matches the tested branch.

- Preflight reports source availability/type, extraction capability, OCR configuration, translation provider configuration, and actionable blockers before enqueueing. It makes no paid model request and must not claim credentials are authenticated.
- A persistent job is returned promptly from Process. Browser reload discovers the latest job and progress. Only one active job per document is allowed.
- Progress reports actual stage and translated blocks where known, without inventing a page total.
- Cancellation is cooperative at safe stage/batch boundaries; an in-flight external call may finish first. Cancelled/failed work preserves the prior Reader snapshot.
- Restarted jobs become clearly interrupted and can be retried using valid cached batches. Never persist a session API key or silently change provider to resume work.
- Source mutation during processing must not publish a Reader for the wrong source revision.
- Acceptance: backend/frontend regression gates, migration preservation, cancellation/restart tests, browser flow using isolated data. Retain Research Map and Implementation Contract behavior.

Validation on 2026-09-13: 457 backend tests passed (91.27% coverage), 142 frontend tests passed; backend lint/format/types/Bandit/dependency audit and frontend production build/high-severity dependency audit passed. Browser checks used an isolated SQLite database, a generated one-page PDF, a PNG, and a delayed deterministic model: preflight blocked missing OCR; queued work survived page reload; cancellation retained the Reader; a deliberately terminated/restarted server surfaced interrupted work without replay. Migration tests preserve completed history and interrupt previous active jobs. These are reliability checks, not live translation-quality evaluation. Preflight samples PDF text availability; it does not establish whole-document extraction completeness.

The local historical desktop database has a different, unsupported schema and was not migrated or modified. This stage verifies the supported public schema migration only. First-use guidance must explain recovery for unsupported databases without overwriting them.

## Stage 2 — Evidence-linked summaries (implemented; integration pending)

- Replace deterministic summary placeholders with structured document/section summaries linked to exact source blocks.
- Validate evidence coverage and source revision before publication; unsupported claims cannot appear as verified findings.
- Distinguish not generated, generating, available, stale and failed summaries; failure preserves a previous usable version.
- Acceptance: supported/unsupported evidence fixtures, provider failure and source-change tests, Reader navigation to evidence.

Validation on 2026-09-13: 505 backend tests passed (91.63% coverage), including evidence rejection, migration preservation, source/Reader change checks, durable job recovery, and bounded CLI stage validation/cache eviction. Frontend: 154 tests passed, including historical Map source selection and exact-block focus. Browser checks with an isolated generated PDF and delayed mock verified reload during generation, keyboard quote expansion/source focus, failure retaining a prior version, successful retry, and identical-file reprocessing marking summaries stale without duplicate Reader rows. The dark summary rail was visually checked and contrast corrected. These tests establish workflow and citation integrity, not live-model semantic quality.

## Stage 3 — First-use guidance (planned)

- Guide provider setup, document import, first reading, Research Map, and Implementation Contract without forcing every step.
- Show meaningful empty states, next actions and recoverable errors, with an explicit development-mode label.
- Acceptance: a first-time user can complete the path from an empty workspace, keyboard interaction works, returning users can resume their existing work.

## Stage 4 — Representative quality acceptance (planned)

- Maintain a small, licensed/public corpus covering text-backed, scanned, equation-heavy and table-heavy papers; keep large files outside git and record source/license/hash.
- Measure extraction completeness, translation alignment, formula fidelity, evidence navigation and recovery behavior against explicit expected results.
- Label deterministic tests separately from live model evaluation. Never call a mock run a translation-quality pass.
- Acceptance: reproducible report with failures and limitations, regression checks for discovered issues, no private documents or credentials committed.

## Delivery rules

Use a focused branch/PR per milestone, preserve local/private artifacts, and run the repository gates before integration. The roadmap remains active until each acceptance criterion is met; implementation progress is not evidence of completion.
