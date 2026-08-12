# Glyph

[![CI](https://github.com/allenchenhan99/Glyph/actions/workflows/ci.yml/badge.svg)](https://github.com/allenchenhan99/Glyph/actions/workflows/ci.yml)

Glyph is a local-first, evidence-first research workspace for Chinese-speaking quantitative-finance readers. It turns PDFs and document images into aligned source/Traditional Chinese blocks, then maps a paper's research question, data, signal, method, result, and limitations back to exact bilingual evidence.

Glyph is currently pre-1.0. It is designed for a trusted single user on one machine, not as an authenticated or internet-facing service.

## Current Capabilities

- Discover `.pdf`, `.png`, `.jpg`, and `.jpeg` files placed in `book/`.
- Upload documents through the browser.
- Extract text-backed PDFs with Poppler or call an external Unlimited-OCR checkout for scanned material.
- Translate bounded block batches through Claude Code or Codex CLI without storing an API key in Glyph.
- Validate block coverage, retry invalid batches, and resume from a local AI cache.
- Preserve the previous readable result when reprocessing fails.
- Detect changed or missing source files without deleting the last readable result.
- Bound uploads and external tools by content type, size, and timeout.
- Read source and Traditional Chinese side by side with paired hover states.
- Render reconstructed formulas as accessible KaTeX/MathML with links to original pages.
- Generate immutable Research Map versions with a controlled quantitative-finance ontology.
- Validate exact evidence anchors before claim synthesis and expose partial/conflicting states.
- Complete a bounded five-step review with verbatim English and aligned Traditional Chinese evidence.
- Confirm, question, or correct claims without overwriting the AI draft.
- Deep-link Map evidence into Reader blocks and preserve context on return.

Section summaries currently use deterministic placeholder text. Full AI-generated document and section summaries remain a future milestone.

## Requirements

- macOS or Linux. Windows users should use WSL.
- Python 3.11 or newer.
- Node.js 22 or newer with npm.
- Poppler (`pdftotext` and `pdftoppm`) for PDF extraction and page previews.
- One authenticated CLI provider:
  - [Claude Code setup](https://docs.anthropic.com/en/docs/claude-code/getting-started)
  - [OpenAI Codex CLI setup](https://help.openai.com/en/articles/11096431)

On macOS, Poppler can be installed with Homebrew:

```bash
brew install poppler
```

## Quick Start

```bash
git clone https://github.com/allenchenhan99/Glyph.git
cd Glyph
./scripts/setup.sh
cp .env.example .env
```

Choose the provider in `.env`:

```dotenv
GLYPH_AI_MODE=claude_cli
```

or:

```dotenv
GLYPH_AI_MODE=codex_cli
```

Install and authenticate that CLI using its official setup flow, then verify it is on `PATH`:

```bash
claude --version
# or
codex --version
```

Start both services:

```bash
./scripts/dev.sh
```

Open `http://127.0.0.1:5173`, place a document in `book/` or upload one, then select **Process** and **Research Map**. Generate the map, follow the five-step review, and open exact evidence in the full Reader. Set `GLYPH_FRONTEND_PORT` in `.env` if that port is occupied.

Uploaded files are stored under `data/uploads/` with internal UUID names while their original display names remain in the catalog. A changed source is marked **stale** and keeps its last-good reader available until reprocessing succeeds. A removed source is marked **missing**; stored text remains readable, but processing and page rendering are blocked until the source returns.

## Privacy Model

Glyph does not commit or upload runtime artifacts to this repository. The following stay local and are ignored by git:

- documents in `book/`;
- uploaded files, rendered pages, SQLite databases, screenshots, and AI cache under `data/`;
- `.env` and project-local `.claude/` or `.codex/` settings;
- Python environments, Node dependencies, build output, and logs.

Only `book/.gitkeep` is tracked so the input directory exists after cloning. CLI credentials remain in the provider's own user-level credential store; Glyph neither reads nor copies those files.

Local-first describes storage and application execution, not offline model inference. Text sent for translation is processed by the selected Claude or OpenAI service under that user's account, plan, retention policy, and usage limits. Do not process sensitive material unless that provider arrangement is appropriate for it.

## OCR Modes

`GLYPH_OCR_MODE=mock` is the default development mode. Despite the name, it uses Poppler text extraction for text-backed PDFs and deterministic behavior for tests. It is not sufficient for scanned PDFs or document photos.

For scanned material, install [Baidu Unlimited-OCR](https://github.com/baidu/Unlimited-OCR) separately and configure:

```dotenv
GLYPH_OCR_MODE=unlimited_ocr
GLYPH_UNLIMITED_OCR_REPO=/absolute/path/to/Unlimited-OCR
```

Alternatively, provide a wrapper command with `{input}` and `{output_dir}` placeholders:

```dotenv
GLYPH_OCR_MODE=unlimited_ocr
GLYPH_UNLIMITED_OCR_COMMAND=python /path/to/wrapper.py --input {input} --output_dir {output_dir}
```

Unlimited-OCR has its own model, hardware, and dependency requirements. Follow its upstream documentation before enabling this mode.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `GLYPH_AI_MODE` | `claude_cli` | `claude_cli`, `codex_cli`, or deterministic `mock` |
| `GLYPH_CLI_MODEL` | provider default | Optional CLI model override |
| `GLYPH_CLI_BATCH_SIZE` | `24` | Blocks sent per CLI invocation |
| `GLYPH_CLI_CONCURRENCY` | `3` | Concurrent CLI workers |
| `GLYPH_CLI_TIMEOUT_SECONDS` | `300` | Timeout for one CLI invocation |
| `GLYPH_FRONTEND_PORT` | `5173` | Vite development-server port |
| `GLYPH_MAX_UPLOAD_BYTES` | `52428800` | Maximum accepted upload size in bytes |
| `GLYPH_OCR_MODE` | `mock` | Text-backed extraction or `unlimited_ocr` |
| `GLYPH_OCR_TIMEOUT_SECONDS` | `300` | Timeout for one OCR invocation |
| `GLYPH_PAGE_RENDER_TIMEOUT_SECONDS` | `30` | Timeout for rendering one PDF page |
| `GLYPH_RESEARCH_JOB_MAX_ATTEMPTS` | `2` | Interrupted map-job attempts before safe failure |
| `GLYPH_RESEARCH_CLI_BLOCK_BATCH_SIZE` | `12` | Reader blocks per Research Map extraction request |
| `GLYPH_BOOK_DIR` | `book/` | Optional source-document directory override |
| `GLYPH_DATA_DIR` | `data/` | Optional runtime-data directory override |
| `GLYPH_DATABASE_URL` | local SQLite | Optional SQLAlchemy database URL |

Lower `GLYPH_CLI_CONCURRENCY` if the selected CLI account reports usage or rate limits. Successful batches remain cached under `data/ai-cache/` and are reused on the next processing attempt.

## Development

Use deterministic mock adapters while developing:

```dotenv
GLYPH_AI_MODE=mock
GLYPH_OCR_MODE=mock
```

Run every backend gate from the repository root:

```bash
.venv/bin/ruff check backend/src backend/tests
.venv/bin/ruff format --check backend/src backend/tests
.venv/bin/mypy backend/src/glyph
.venv/bin/pytest --cov=glyph --cov-report=term-missing --cov-fail-under=85
.venv/bin/bandit -q -r backend/src/glyph
.venv/bin/pip-audit
```

Then run the frontend gates:

```bash
cd frontend
npm audit --audit-level=high
npm run test:coverage
npm run build
```

The backend API runs on `http://127.0.0.1:8000`; Vite proxies `/api` requests from `http://127.0.0.1:5173`.

Database changes are managed by Alembic and applied automatically at backend startup. The migration bootstrap recognizes the original public schema and preserves its data; it rejects unknown partial schemas instead of resetting them. Back up `data/` and `book/` before upgrading. See the [Research Map guide](docs/research-map.md) for evidence guarantees, version/review semantics, recovery, and trust boundaries, and [CONTRIBUTING.md](CONTRIBUTING.md) for pull-request expectations.

## Project Layout

```text
book/          ignored user documents
data/          ignored SQLite, uploads, page images, and AI cache
backend/       FastAPI, SQLAlchemy, OCR and CLI adapters
frontend/      React, TypeScript, Vite, and KaTeX reader
scripts/       setup and local development commands
docs/plans/    architecture and implementation decisions
docs/adr/      durable architectural decisions
```

## Contributing and Security

Issues and focused pull requests are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md), and use the private process in [SECURITY.md](SECURITY.md) for vulnerabilities. Do not attach real documents, databases, credentials, or unsanitized provider output to public reports.

## License

[MIT](LICENSE)
