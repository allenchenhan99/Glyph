# Changelog

Notable user-facing changes are documented here. Glyph is pre-1.0 and does not yet have a stable release cadence.

## Unreleased

### Added

- Compatible Alembic migrations for existing and new local databases.
- Upload size and signature validation with collision-safe storage.
- Source freshness states for changed and missing documents.
- OCR, page-rendering, and AI CLI timeouts with sanitized failures.
- Automated backend and frontend quality, coverage, security, and dependency gates.

### Changed

- The document catalog now includes browser uploads after refresh and restart.
- Reader snapshot replacement is atomic and concurrent processing returns a conflict.
- Failed processing jobs retain safe public errors and are never presented as successful.
- The UI presents backend-safe error details and warns when a reader snapshot is stale.
