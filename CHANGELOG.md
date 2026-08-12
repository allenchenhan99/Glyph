# Changelog

Notable user-facing changes are documented here. Glyph is pre-1.0 and does not yet have a stable release cadence.

## Unreleased

### Added

- Compatible Alembic migrations for existing and new local databases.
- Upload size and signature validation with collision-safe storage.
- Source freshness states for changed and missing documents.
- OCR, page-rendering, and AI CLI timeouts with sanitized failures.
- Automated backend and frontend quality, coverage, security, and dependency gates.
- Evidence-backed Research Maps with six controlled quant-research categories.
- Exact bilingual Reader anchors, five-step guided review, and Map/Reader deep links.
- Immutable map versions, deterministic diffs, append-only human review, and source staleness.
- Persistent single-worker generation jobs with restart recovery and mock/CLI providers.
- Auditable Implementation Contracts with typed values, four explicit origins, deterministic backend readiness, and blocker-aware six-step review.
- Immutable contract versions, exact-signature decision carry-forward, deterministic diffs, append-only human resolution history, and Contract–Map–Reader deep links.
- `glyph-contract` local generation/inspection/export commands and freshly audited JSON/Markdown exports with explicit readiness warnings.

### Changed

- The document catalog now includes browser uploads after refresh and restart.
- Reader snapshot replacement is atomic and concurrent processing returns a conflict.
- Failed processing jobs retain safe public errors and are never presented as successful.
- The UI presents backend-safe error details and warns when a reader snapshot is stale.
- Research Map is the primary document research action; Full Reader remains available for deep reading.
- Library rows expose batched verification progress, evidence gaps, and current/stale map state.
- Research Maps can now open a bounded implementation handoff without generating or executing strategy code.
- Contract generation and export preserve missing assumptions instead of substituting provider or UI defaults, and failures preserve the prior active version.
