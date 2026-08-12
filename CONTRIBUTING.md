# Contributing to Glyph

Thank you for helping make long-form reading more accessible. Glyph is pre-1.0, so discuss large changes in an issue before investing in implementation. Focused bug fixes and documentation improvements can go directly to a pull request.

## Development setup

Glyph supports macOS and Linux (or WSL) with Python 3.11+, Node.js 22+, npm, and Poppler. Clone the repository, then run:

```bash
./scripts/setup.sh
cp .env.example .env
```

For deterministic local development, set `GLYPH_AI_MODE=mock`. Start the app with `./scripts/dev.sh`; the backend listens on `127.0.0.1:8000` and the frontend on `127.0.0.1:5173` by default.

## Architecture boundaries

- `backend/src/glyph/documents.py` owns the document catalog, upload boundary, and source freshness.
- `backend/src/glyph/pipeline.py` owns processing coordination and atomic reader snapshot replacement.
- `backend/src/glyph/ocr.py` and `backend/src/glyph/cli_ai.py` are external-process trust boundaries. Keep argv execution, timeouts, and sanitized errors intact.
- `backend/migrations/` is the only supported schema evolution path. Never replace migrations with `create_all()` or destructive startup resets.
- `frontend/src/api.ts` validates data at the HTTP boundary; components consume typed values.

Runtime documents and generated data belong in ignored `book/` and `data/` paths. Never add real user documents, databases, credentials, AI cache entries, or generated page images to a commit.

## Change workflow

1. Add or update a test that demonstrates the intended behavior and observe it fail.
2. Make the smallest coherent implementation change.
3. Run the relevant focused tests, then every quality gate below.
4. Update configuration, migrations, and documentation in the same pull request when behavior changes.

Backend gates, run from the repository root:

```bash
.venv/bin/ruff check backend/src backend/tests
.venv/bin/ruff format --check backend/src backend/tests
.venv/bin/mypy backend/src/glyph
.venv/bin/pytest --cov=glyph --cov-report=term-missing --cov-fail-under=85
.venv/bin/bandit -q -r backend/src/glyph
.venv/bin/pip-audit
```

Frontend gates:

```bash
cd frontend
npm audit --audit-level=high
npm run test:coverage
npm run build
```

The frontend coverage gate starts at 60% for statements, functions, and lines, and 40% for branches. New behavior should be directly tested; do not reduce thresholds to make a pull request pass.

## Issues and pull requests

An actionable issue includes the observed behavior, expected behavior, reproduction steps, platform, Python/Node versions, selected OCR and AI modes, and a sanitized log excerpt when relevant. Never post document contents, tokens, local paths, or provider credentials.

A pull request should explain the user-facing outcome, link its issue when one exists, call out data/schema/security effects, and list the exact verification commands run. Keep unrelated refactors separate. CI must pass before review, and reviewers may ask for migration or rollback evidence when persisted data changes.

Use [SECURITY.md](SECURITY.md) instead of a public issue for suspected vulnerabilities.
