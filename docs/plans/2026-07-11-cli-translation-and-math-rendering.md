# CLI Translation and Math Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce genuine Traditional Chinese translations through Codex or Claude CLI and render formula blocks as typeset LaTeX.

**Architecture:** Keep deterministic OCR and block splitting in Glyph, then pass bounded block batches through a provider-neutral CLI adapter with schema-validated JSON output. Persist a dedicated `formula_latex` value and render it with KaTeX in React, retaining explicit fallbacks for failed or legacy formula data.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, SQLite, Codex CLI, Claude CLI, React 19, TypeScript, KaTeX, Vitest, pytest.

## Global Constraints

- All implementation remains under the repository root.
- Live translation uses an authenticated Codex or Claude CLI and does not require an API key.
- Translation output must be Traditional Chinese, never prefixed English placeholder text.
- Formula source is preserved while mathematical display uses rendered LaTeX.
- User-owned files under `book/` are never committed.

---

### Task 1: CLI Translation Adapter

**Files:**
- Create: `backend/src/glyph/cli_ai.py`
- Modify: `backend/src/glyph/config.py`
- Modify: `backend/src/glyph/ai.py`
- Test: `backend/tests/test_cli_ai.py`

**Interfaces:**
- Consumes: deterministic `ParsedBlock` candidates from `glyph.ai`.
- Produces: `CliAiAdapter.parse_translate_and_summarize(page_text) -> ParsedDocument` and schema-validated CLI batch results.

- [ ] **Step 1: Write failing tests** for Claude/Codex command construction, stdin transport, Traditional Chinese translation, formula LaTeX, and malformed/partial output rejection.
- [ ] **Step 2: Run `pytest tests/test_cli_ai.py -v`** and confirm failures are caused by the missing adapter.
- [ ] **Step 3: Implement provider-neutral batching and subprocess execution** using `claude -p --tools '' --json-schema ...` or `codex exec --ephemeral --sandbox read-only --output-schema ...`, with timeout and strict result coverage checks.
- [ ] **Step 4: Add configuration** for `GLYPH_AI_MODE`, `GLYPH_CLI_MODEL`, `GLYPH_CLI_BATCH_SIZE`, and `GLYPH_CLI_TIMEOUT_SECONDS`.
- [ ] **Step 5: Run `pytest tests/test_cli_ai.py -v`** and confirm all adapter tests pass.

### Task 2: Persist Formula LaTeX

**Files:**
- Modify: `backend/src/glyph/models.py`
- Modify: `backend/src/glyph/schemas.py`
- Modify: `backend/src/glyph/pipeline.py`
- Modify: `backend/src/glyph/main.py`
- Modify: `backend/src/glyph/documents.py`
- Test: `backend/tests/test_pipeline.py`
- Test: `backend/tests/test_reader_payload.py`

**Interfaces:**
- Consumes: `ParsedBlock.formula_latex: str | None`.
- Produces: persisted `Block.formula_latex` and `BlockOut.formula_latex`.

- [ ] **Step 1: Add failing persistence and reader payload assertions** for formula LaTeX.
- [ ] **Step 2: Run the focused backend tests** and confirm the field is absent.
- [ ] **Step 3: Add the nullable model/schema field and startup SQLite column migration**, then pass the value through pipeline persistence and reader serialization.
- [ ] **Step 4: Run all backend tests** and confirm existing databases and new test databases both work.

### Task 3: Render Mathematics in React

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/Reader.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/Reader.test.tsx`

**Interfaces:**
- Consumes: `ReaderBlock.formula_latex: string | null`.
- Produces: KaTeX-rendered HTML/MathML with explicit invalid/missing formula fallback.

- [ ] **Step 1: Add a failing reader test** asserting rendered KaTeX markup exists and raw LaTeX is not presented as a code block.
- [ ] **Step 2: Run the focused frontend test** and confirm the current `<pre>` implementation fails it.
- [ ] **Step 3: Install KaTeX and implement a focused `MathFormula` component** using `renderToString` with safe output and visible error fallback.
- [ ] **Step 4: Update styles** for readable display math, horizontal overflow, contrast, and mobile sizing.
- [ ] **Step 5: Run frontend tests and production build**.

### Task 4: Actual Book Verification

**Files:**
- Modify: `README.md`
- Runtime only: `data/glyph.sqlite3`

**Interfaces:**
- Consumes: authenticated local CLI and the user-owned book.
- Produces: reprocessed reader data with real Traditional Chinese and rendered formulas.

- [ ] **Step 1: Smoke-test each installed CLI with one schema-constrained translation batch** and select the first authenticated provider.
- [ ] **Step 2: Reprocess a representative page range or fixture** and inspect translation completeness plus formula LaTeX validity.
- [ ] **Step 3: Reprocess the complete book** with the selected CLI configuration.
- [ ] **Step 4: Inspect paragraph and formula rows in the running browser** at desktop and mobile widths.
- [ ] **Step 5: Run backend tests, frontend tests, frontend build, and `git diff --check`**, then document exact runtime configuration in `README.md`.
