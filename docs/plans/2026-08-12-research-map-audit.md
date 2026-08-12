# Research Map v1 completion audit

Date: 2026-08-12  
Branch: `feat/research-map`  
Decision: ready for pull-request review

## Scope checked

The audit covers the approved evidence-first Research Map v1: controlled ontology, exact Reader anchors, immutable versions and deterministic diffs, append-only human review, persistent generation jobs, mock and CLI providers, guided review, Evidence Inspector, Map/Reader deep links, migrations, documentation, and local browser behavior. Formula derivation, cross-paper graphs, accounts, sharing, and cloud deployment remain out of scope.

## Automated evidence

| Gate | Result |
| --- | --- |
| Backend tests and branch coverage | 152 passed; 90.58% total coverage; 85% gate passed |
| Backend formatting and lint | Ruff format and lint passed across source and tests |
| Backend typing | mypy passed across `backend/src/glyph` |
| Backend security scan | Bandit passed with no findings |
| Python dependency audit | No known vulnerabilities; the local unpublished `glyph-backend` package is not on PyPI and was skipped |
| Frontend tests and coverage | 50 passed; 78.29% statements, 81.23% branches, 83.08% functions, 79.58% lines |
| Frontend dependency audit | npm reported zero vulnerabilities |
| Frontend production build | TypeScript and Vite build passed |
| Database compatibility | Fresh schema, recognized legacy schema, data preservation, map migration, and unknown-partial-schema rejection passed |
| Research benchmark | Deterministic empirical-asset-pricing fixture passed exact-anchor, six-category, statistical-evidence, `not_reported`, provider-call, and normalization checks |

The production build reports a non-blocking 501.27 kB JavaScript chunk warning. This does not affect correctness or the current CI gate; code splitting is a measured performance follow-up rather than a release blocker for the local v1 workspace.

## Browser acceptance

The app was started against isolated mock data on loopback and exercised through the real frontend, API, SQLite database, and persistent job executor.

- Discovered and processed an original synthetic empirical-asset-pricing document.
- Generated a map through a queued background job and confirmed all six ontology categories, 11 reviewable core nodes, one explicit `not_reported` evidence gap, and exact bilingual evidence.
- Confirmed, questioned, and corrected three different nodes; the Library summary refreshed to 3/11 without a page reload, while the original AI draft and review note remained visible.
- Followed **View in Reader** to the exact active block, observed its citation badge, and returned with the selected node and Evidence Inspector restored.
- Traversed all five guided-review steps and confirmed the terminal control state.
- Verified visible keyboard focus with a 3 px solid outline.
- Checked desktop (1280×800), tablet (768×900), and mobile (390×844) layouts. The workbench collapsed from three to two to one column without horizontal overflow.
- Modified source bytes, observed stale status immediately, reprocessed, and generated a new version from the stale map. The old version remained readable with its three reviews; the current version became 0/11 because every exact evidence signature changed, and the deterministic diff classified those nodes as `evidence_changed`.
- Restarted both services and confirmed the current version and Library summary persisted.
- Browser console inspection ended with no warnings or errors.

Provider and persistence failure injection, interrupted-job retry limits, optimistic-review rollback, stale conflicts, previous-version survival, and query-count bounds are covered by automated service/API tests because the product UI intentionally exposes no failure-injection controls.

## Trust and operational review

- Exact anchors prove source location, not scientific truth; OCR, translation, author claims, and methods still require human judgment.
- Provider text is treated as untrusted data, constrained by schemas, bounded batches, timeouts, controlled vocabularies, and sanitized public errors.
- Local-first storage does not mean offline inference: authenticated CLI providers may transmit extracted text under their own terms and retention policies.
- The executor is deliberately single-process and single-worker. Glyph has no authentication, TLS, tenant isolation, secure delete, automatic backup, or supported downgrade and must not be exposed directly to a network.
- Upgrade guidance requires stopping Glyph and backing up both `data/` and `book/`; forward migrations preserve recognized legacy Reader data and reject unknown partial schemas.

## Residual follow-ups

1. Expand benchmarks to representative real papers and additional empirical designs before claiming broad extraction quality.
2. Measure production load time and split the frontend bundle if the current chunk materially affects local startup.
3. Design formula derivation and cross-paper comparison as separate milestones that consume, rather than weaken, the evidence/version contracts established here.
