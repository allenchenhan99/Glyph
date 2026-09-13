# Glyph product milestones

Status: active. Approved by the user on 2026-09-13; execute in order, record evidence before marking a milestone complete.

## Stage 1 — Reliable document processing (in progress)

- Preflight reports source availability/type, extraction capability, OCR configuration, translation provider configuration, and actionable blockers before enqueueing. It makes no paid model request and must not claim credentials are authenticated.
- A persistent job is returned promptly from Process. Browser reload discovers the latest job and progress. Only one active job per document is allowed.
- Progress reports actual stage and translated blocks where known, without inventing a page total.
- Cancellation is cooperative at safe stage/batch boundaries; an in-flight external call may finish first. Cancelled/failed work preserves the prior Reader snapshot.
- Restarted jobs become clearly interrupted and can be retried using valid cached batches. Never persist a session API key or silently change provider to resume work.
- Source mutation during processing must not publish a Reader for the wrong source revision.
- Acceptance: backend/frontend regression gates, migration preservation, cancellation/restart tests, browser flow using isolated data. Retain Research Map and Implementation Contract behavior.

## Stage 2 — Evidence-linked summaries (planned)

- Replace deterministic summary placeholders with structured document/section summaries linked to exact source blocks.
- Validate evidence coverage and source revision before publication; unsupported claims cannot appear as verified findings.
- Distinguish not generated, generating, available, stale and failed summaries; failure preserves a previous usable version.
- Acceptance: supported/unsupported evidence fixtures, provider failure and source-change tests, Reader navigation to evidence.

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
