# Document Translation Reader Design

## Goal

Build Glyph as a local-first app for parsing books and research material from `book/` or uploads, splitting them into readable source blocks, translating each block to Traditional Chinese, and presenting an aligned reader with progress, sections, and AI summaries.

## Project Boundary

All implementation lives under the repository root.

Primary directories:

- `book/`: user-managed input files for PDFs and images.
- `backend/`: FastAPI service, pipeline, persistence, and tests.
- `frontend/`: React/Vite reader UI, document picker, job progress, and tests.
- `data/`: local runtime artifacts, SQLite database, uploads, rendered pages, OCR output, and cached AI output.
- `docs/plans/`: design and implementation plans.

## Recommended Architecture

Use a Python backend with FastAPI, SQLite, and background jobs, plus a React/Vite frontend. This keeps PDF/image handling, PyMuPDF rendering, Unlimited-OCR integration, AI block parsing, translation, and summaries in the Python ecosystem while letting the frontend focus on a fast aligned reading experience.

The first version is single-user and local-first. It avoids Postgres, Redis, and Celery until there is a real multi-user or high-throughput need.

## Pipeline

The document processing pipeline has these stages:

1. Discover or upload a source file.
2. Register the document with a content hash and metadata.
3. Convert PDF pages to images when needed.
4. Run OCR through an OCR adapter.
5. Normalize OCR output into raw page text.
6. Use an AI parser to split text into semantic blocks.
7. Translate each block into Traditional Chinese.
8. Build a section tree and progress metadata.
9. Generate whole-document and per-section summaries.
10. Cache every intermediate result so failed or partial jobs can resume.

## OCR Integration

Unlimited-OCR is integrated behind an adapter boundary instead of being called directly in web request handlers. The adapter supports these modes:

- `mock`: deterministic local fallback for tests and development.
- `unlimited_ocr`: shell or Python invocation of the checked-out Unlimited-OCR repo.
- future modes: vLLM/SGLang/OpenAI-compatible endpoint if the Unlimited-OCR deployment is exposed through an API.

The app should report OCR worker availability in the UI. If Unlimited-OCR is not configured or GPU dependencies are missing, the app remains usable for development through mock OCR and text extraction.

## AI Responsibilities

AI is involved after OCR, not only for translation. The AI layer should:

- clean OCR artifacts while preserving meaning;
- classify headings, paragraphs, list items, examples, equations, and questions;
- split content into stable reading blocks;
- translate each block to Traditional Chinese;
- build or refine the section tree;
- generate concise whole-document and section-level summaries;
- mark low-confidence or malformed blocks for user inspection.

The first version uses deterministic local implementations and mockable interfaces so the app works without live model credentials. Real model adapters can be enabled through environment configuration.

## Data Model

Core entities:

- `Document`: id, title, source path, content hash, file type, processing status, timestamps.
- `ProcessingJob`: id, document id, status, current stage, progress percentage, error message, timestamps.
- `Page`: id, document id, page number, image path, raw OCR text.
- `Block`: id, document id, order index, page number, block type, source text, translated text, section id, confidence.
- `Section`: id, document id, title, path, order index, parent id, summary.
- `Summary`: id, document id, optional section id, summary text, generated timestamp.

Bounding boxes are optional for version one because OCR engines differ in whether they return stable layout coordinates. The aligned reader is driven by block order first.

## Backend API

Initial endpoints:

- `GET /api/health`
- `GET /api/documents`
- `POST /api/documents/upload`
- `POST /api/documents/{id}/process`
- `GET /api/jobs/{id}`
- `GET /api/documents/{id}/reader`
- `GET /api/documents/{id}/sections`
- `GET /api/documents/{id}/summary`

## Frontend UX

The first screen is a work surface, not a landing page. It shows:

- documents discovered from `book/`;
- uploaded files;
- each document's processing status;
- commands to process or open the reader.

The reader shows a two-column aligned view:

- left column: source text;
- right column: Traditional Chinese translation;
- each block separated by a very thin line;
- hover on either side highlights the full source/translation row without selecting text;
- large documents render through virtualization;
- a section rail shows table of contents, progress, and summaries.

The visual style should be quiet and study-oriented: dense enough for long reading sessions, clear typography, restrained color, and no card-heavy marketing layout.

## Error Handling

Failures are explicit and recoverable:

- unavailable OCR worker shows an actionable status;
- failed jobs keep their last successful artifact;
- individual AI parse/translation failures preserve source text and mark the block;
- users can rerun processing.

## Testing Strategy

Backend tests cover:

- `book/` discovery;
- upload validation;
- document hash registration;
- job state transitions;
- mock OCR output;
- block splitting;
- Traditional Chinese translation adapter contract;
- section and summary generation;
- reader payload shape.

Frontend tests cover:

- document picker rendering;
- upload interaction;
- processing status display;
- reader two-column alignment;
- hover synchronization;
- section progress display.

End-to-end smoke verification should process a sample text-backed fixture through mock OCR and open it in the reader.

## Version One Scope

Version one must provide a complete local workflow:

- scan `book/` for PDF/PNG/JPG/JPEG files;
- upload supported files;
- process a selected document through the pipeline;
- display source and Traditional Chinese blocks side by side;
- show sections, progress, and summaries;
- expose OCR/AI adapters that can be swapped for Unlimited-OCR and real model calls.

Out of scope for the first version:

- multi-user accounts;
- collaborative annotations;
- full OCR bounding-box interaction;
- cloud deployment;
- distributed job queues.
