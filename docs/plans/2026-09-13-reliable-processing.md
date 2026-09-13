# Reliable Processing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver Stage 1 of the product roadmap with preflight, durable processing jobs and recoverable user-visible progress.

**Architecture:** SQLite job records and one local worker; short transaction boundaries and an atomic Reader replacement. A separate frontend processing component owns preflight and job state without changing research navigation.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, Python, React/TypeScript, Vitest.

---

### Task 1: Backend preflight and no fabricated OCR
Files: backend/src/glyph/ocr.py, new processing_preflight.py, documents.py; tests in test_ocr.py and new test_processing_preflight.py.
Write failing tests for scanned images without OCR, missing CLI/key/model, unavailable source, valid text PDFs, and bounded failure. Implement actionable preflight responses; remove placeholder OCR success. Run focused pytest tests before proceeding.

### Task 2: Durable worker and migration
Files: models.py, schemas.py, new processing_jobs.py, pipeline.py, cli_ai.py, main.py, documents.py; new Alembic revision under backend/alembic/versions; new test_processing_jobs.py plus migration/API regressions.
Write failing tests for prompt enqueue, active-job uniqueness, published progress, cooperative cancel, snapshot preservation, source mutation, shutdown/restart and retry cache. Implement job transitions with short transactions, progress/cancel callbacks and captured credentials. Never persist API keys. Preserve provider configuration boundaries.

### Task 3: Frontend processing flow
Files: frontend/src/types.ts, api.ts, new DocumentProcessing.tsx and tests, App.tsx/App.test.tsx, styles.css.
Write failing tests for blocked preflight, queue/poll/complete, page reload recovery, cancellation, failed retry, errors and unmount cleanup. Implement isolated processing state with accessible progress/status and actionable controls. Retain existing Reader, Research Map and Contract interactions.

### Task 4: Integration and evidence
Update README and this roadmap with actual semantics. Run ruff check/format, mypy, pytest coverage >=85%, Bandit, pip-audit; npm audit at high threshold, coverage and build. Browser-check isolated data, use no private documents and make no paid model calls for deterministic acceptance. Review diff, create PR and integrate only after required checks pass.
