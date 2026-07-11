# Document Translation Reader Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local book/document parsing and Traditional Chinese translation app in `Glyph/` with document discovery/upload, OCR/AI pipeline adapters, section summaries, progress, and an aligned two-column reader.

**Architecture:** FastAPI owns ingestion, SQLite persistence, background processing, OCR and AI adapter boundaries, and reader payloads. React/Vite owns the local-first work surface, upload/process controls, job progress, section rail, and virtualized aligned reader.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Pydantic, pytest, PyMuPDF optional runtime, React, TypeScript, Vite, Vitest, React Testing Library.

---

### Task 1: Backend Project Skeleton

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/glyph/__init__.py`
- Create: `backend/src/glyph/config.py`
- Create: `backend/src/glyph/main.py`
- Create: `backend/tests/test_health.py`

**Step 1: Write the failing test**

Create `backend/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from glyph.main import create_app


def test_health_reports_ok_and_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(tmp_path / "book"))
    app = create_app()
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["book_dir"].endswith("book")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_health.py -v`
Expected: FAIL because `glyph.main` does not exist.

**Step 3: Write minimal implementation**

Create FastAPI app factory and settings loader. `Settings` should expose `book_dir`, `data_dir`, `database_url`, `ocr_mode`, and `ai_mode`.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_health.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat: add backend health skeleton"
```

### Task 2: Persistence and Document Discovery

**Files:**
- Create: `backend/src/glyph/database.py`
- Create: `backend/src/glyph/models.py`
- Create: `backend/src/glyph/schemas.py`
- Create: `backend/src/glyph/documents.py`
- Modify: `backend/src/glyph/main.py`
- Test: `backend/tests/test_documents.py`

**Step 1: Write the failing test**

Test that supported files in `book/` are discovered and unsupported files are ignored:

```python
def test_documents_endpoint_discovers_supported_book_files(tmp_path, monkeypatch):
    book = tmp_path / "book"
    book.mkdir()
    (book / "sample.pdf").write_bytes(b"%PDF-1.4")
    (book / "page.png").write_bytes(b"fake")
    (book / "notes.txt").write_text("ignore")
    monkeypatch.setenv("GLYPH_BOOK_DIR", str(book))
    monkeypatch.setenv("GLYPH_DATA_DIR", str(tmp_path / "data"))

    response = TestClient(create_app()).get("/api/documents")

    assert response.status_code == 200
    names = [item["title"] for item in response.json()]
    assert names == ["page.png", "sample.pdf"]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_documents.py -v`
Expected: FAIL because `/api/documents` does not exist.

**Step 3: Write minimal implementation**

Implement SQLite tables for documents/jobs/pages/blocks/sections/summaries, database initialization, content hashing, and `GET /api/documents`.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_documents.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat: discover local book documents"
```

### Task 3: Upload Endpoint

**Files:**
- Modify: `backend/src/glyph/documents.py`
- Test: `backend/tests/test_uploads.py`

**Step 1: Write the failing test**

Create a test that uploads a PDF file and expects a registered document with stored source path.

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_uploads.py -v`
Expected: FAIL because upload route is missing.

**Step 3: Write minimal implementation**

Implement `POST /api/documents/upload`, validate `.pdf`, `.png`, `.jpg`, `.jpeg`, save to `data/uploads`, register document, and reject unsupported types with HTTP 400.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_uploads.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat: upload source documents"
```

### Task 4: OCR and AI Pipeline Adapters

**Files:**
- Create: `backend/src/glyph/pipeline.py`
- Create: `backend/src/glyph/ocr.py`
- Create: `backend/src/glyph/ai.py`
- Modify: `backend/src/glyph/documents.py`
- Modify: `backend/src/glyph/schemas.py`
- Test: `backend/tests/test_pipeline.py`

**Step 1: Write the failing tests**

Test that mock OCR and mock AI processing create blocks, translations, sections, and summaries for a document.

**Step 2: Run tests to verify failure**

Run: `cd backend && pytest tests/test_pipeline.py -v`
Expected: FAIL because pipeline modules do not exist.

**Step 3: Write minimal implementation**

Implement:

- `MockOcrAdapter`: reads text from simple fixtures or returns deterministic text for images/PDFs.
- `UnlimitedOcrAdapter`: checks configuration and raises a clear unavailable error until configured.
- `MockAiAdapter`: splits text by headings, blank lines, list markers, and question numbers; translates by prefixing deterministic Traditional Chinese text; builds section summaries.
- job state transitions: `queued`, `running`, `completed`, `failed`.
- `POST /api/documents/{id}/process`.
- `GET /api/jobs/{id}`.

**Step 4: Run tests to verify pass**

Run: `cd backend && pytest tests/test_pipeline.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat: process documents through OCR and AI adapters"
```

### Task 5: Reader Payload API

**Files:**
- Modify: `backend/src/glyph/documents.py`
- Modify: `backend/src/glyph/schemas.py`
- Test: `backend/tests/test_reader_payload.py`

**Step 1: Write the failing test**

Process a document, fetch `/api/documents/{id}/reader`, and assert aligned blocks include `source_text`, `translated_text`, `section_path`, `page_number`, and `block_type`.

**Step 2: Run test to verify failure**

Run: `cd backend && pytest tests/test_reader_payload.py -v`
Expected: FAIL because reader route is missing.

**Step 3: Write minimal implementation**

Implement reader, sections, and summary endpoints.

**Step 4: Run test to verify pass**

Run: `cd backend && pytest tests/test_reader_payload.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat: expose aligned reader payload"
```

### Task 6: Frontend Skeleton and API Client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/App.test.tsx`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/test/setup.ts`

**Step 1: Write the failing test**

Render the app with mocked API responses and assert the document picker shows discovered files.

**Step 2: Run test to verify failure**

Run: `cd frontend && npm test -- --run`
Expected: FAIL because frontend does not exist.

**Step 3: Write minimal implementation**

Implement React app shell, API client, document list, status labels, upload input, and process/open actions.

**Step 4: Run test to verify pass**

Run: `cd frontend && npm test -- --run`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend
git commit -m "feat: add frontend document picker"
```

### Task 7: Aligned Reader UI

**Files:**
- Create: `frontend/src/Reader.tsx`
- Create: `frontend/src/Reader.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/styles.css`

**Step 1: Write the failing test**

Render reader blocks and verify source and translation text appear in paired rows. Simulate mouse hover and assert both sides receive hover state.

**Step 2: Run test to verify failure**

Run: `cd frontend && npm test -- --run src/Reader.test.tsx`
Expected: FAIL because `Reader` does not exist.

**Step 3: Write minimal implementation**

Implement a two-column reader with thin separators, synchronized hover, section rail, progress, and simple virtualization by rendering a window based on scroll position.

**Step 4: Run test to verify pass**

Run: `cd frontend && npm test -- --run src/Reader.test.tsx`
Expected: PASS.

**Step 5: Commit**

```bash
git add frontend
git commit -m "feat: add aligned translation reader"
```

### Task 8: Local Runtime and Documentation

**Files:**
- Create: `README.md`
- Create: `.gitignore`
- Create: `book/.gitkeep`
- Modify: `backend/pyproject.toml`
- Modify: `frontend/package.json`

**Step 1: Write smoke verification**

Document commands and ensure backend/frontend scripts exist:

```bash
cd backend && pytest
cd frontend && npm test -- --run
cd frontend && npm run build
```

**Step 2: Run smoke verification**

Expected: all tests and build pass.

**Step 3: Write documentation**

Document setup, running backend, running frontend, OCR configuration, mock mode, and where to place files in `book/`.

**Step 4: Start dev server**

Run backend and frontend dev servers, then report the local URL.

**Step 5: Commit**

```bash
git add README.md .gitignore book backend frontend
git commit -m "docs: document local Glyph workflow"
```
