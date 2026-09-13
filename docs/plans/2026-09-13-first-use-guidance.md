# First-use guidance implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let a new user configure providers, import a document, read it, and continue into Research Maps and Implementation Contracts using visible next actions, while returning users retain their workspace.

**Architecture:** Add a read-only workspace capability endpoint backed by local configuration checks, not model requests. The frontend displays provider-specific development labels and a dismissible/reopenable getting-started guide using existing actions and document state. Unsupported legacy databases produce a diagnostic app with safe recovery guidance and no document mutations.

**Tech Stack:** Existing FastAPI/SQLAlchemy, React/TypeScript, pytest/Vitest, shell startup scripts and Vite.

## API contract

`GET /api/workspace` returns:

```ts
type Workspace = {
  status: 'ready' | 'blocked'
  development_features: string[]
  translation: { provider: string; configured: boolean; message: string }
  research: { provider: string; configured: boolean; message: string }
  ocr: { provider: string; configured: boolean; message: string }
  recovery: string | null
}
```

`configured` describes local configuration/executable availability only. Never imply authenticated access, balance, or output quality. `development_features` names translation when translation is mock, and summaries/Research Maps/Implementation Contracts when research AI is mock. Mock OCR used for real PDF text extraction alone must not mislabel real model output as deterministic development output. OCR capability explains text-PDF extraction versus configured scanned-image OCR.

## Task 1: Capability checks and safe startup (backend owner)

- Create `workspace.py` and `tests/test_workspace.py`; register in `main.py`.
- Reuse local preflight provider/OCR rules; expose no keys, credential values, document paths, or document text. Make no external provider calls.
- Add failing tests for CLI absent/present, OrcaRouter incomplete/valid configuration, research/translation independence, precise mock labels, and OCR availability.
- On unsupported schema (`DatabaseMigrationError`) start a diagnostic app: workspace returns blocked + recovery, health reports blocked, document/API mutation routes return 503. Keep the original database bytes unchanged. On invalid configuration provide a generic actionable diagnostic without echoing secrets.
- Recovery: keep the existing database, choose a new empty `GLYPH_DATA_DIR`, and also update `GLYPH_DATABASE_URL` if explicitly set. Restart. Do not move, delete, reset, or automatically convert the old database. Test with a synthetic legacy DB and hash before/after; all application tests use isolated environment paths.

## Task 2: First-use interface (frontend owner)

- Add `GettingStarted.tsx`, API guards/types, and tests; integrate in `App.tsx` and `SettingsPage.tsx`.
- Load workspace state on entry and after applying settings. Show the actual translation and research provider independently. Display a persistent concise label only for features using deterministic mocks.
- Empty workspace shows import guidance and accessible actions for provider settings and upload. A guide describes Import → Process/Full Reader → Summary/Research Map → Implementation Contract without requiring completion or navigating automatically.
- Guide can be hidden and reopened; failure to access localStorage cannot break the app. Derive document milestones from actual document state; never claim authentication or completed reviews from configuration alone.
- Returning users keep their document list and existing navigation. Missing/stale documents with retained Reader/Map/Contract results must remain accessible.
- Blocked workspace shows recovery guidance; unreachable backend shows actionable retry guidance without asserting a hard-coded port. No fix/reset/migration button.
- Use semantic buttons, visible focus, and readable contrast. Test empty/returning states, settings refresh, hide/reopen persistence, keyboard actions, blocked state, network retry, and existing Map/Contract behavior.

## Task 3: Startup and docs (primary owner)

- Allow the UI to start when the research CLI is absent, with a warning and capability guidance, so translation provider configuration is still reachable.
- Support an explicit `GLYPH_BACKEND_PORT` in `scripts/dev.sh` and Vite proxy, retaining 8000 as default; use strict frontend port selection. Do not stop unrelated services.
- Document provider separation, deterministic trial mode, public-document-first workflow, and unsupported-database recovery. Keep implementation/configuration details in setup guidance where they help the user choose a remedy.

## Task 4: Verify and integrate

- Run backend quality/coverage and frontend coverage/audit/build gates. Browser-test an isolated empty workspace through a processed Reader and research/contract entry points; verify keyboard controls and returning-user state.
- Use fixture model output only for workflow checks and say so. Existing private data remains untouched.
- Record evidence in the roadmap, create a focused PR, and merge after CI passes.
