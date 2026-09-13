<p align="center">
  <img src="docs/assets/glyph-icon.png" width="128" height="128" alt="Glyph — an ivory open book with a terracotta fold" />
</p>
<h1 align="center">Glyph</h1>
<p align="center"><strong>Read the paper. Trace the evidence. Define the implementation.</strong></p>
<p align="center">A local-first research workspace for Traditional Chinese readers.</p>

[![CI](https://github.com/allenchenhan99/Glyph/actions/workflows/ci.yml/badge.svg)](https://github.com/allenchenhan99/Glyph/actions/workflows/ci.yml)

Glyph is a local-first, evidence-first research workspace for Chinese-speaking quantitative-finance readers. It turns PDFs and document images into aligned source/Traditional Chinese blocks, then maps a paper's research question, data, signal, method, result, and limitations back to exact bilingual evidence.

Glyph is currently pre-1.0. It is designed for a trusted single user on one machine, not as an authenticated or internet-facing service.

## From paper to implementation

| Step | What you get |
| --- | --- |
| **Import** | Upload a PDF or document image, or discover files in `book/`. Sources and processing artifacts stay in your local workspace. |
| **Read** | Aligned original and Traditional Chinese text, paired hover states, accessible formulas, and links to source pages. |
| **Summarize** | Explicitly generate document and section drafts with exact source quotations, version checks, and keyboard navigation back to evidence. |
| **Map the research** | Versioned Research Maps connect the research question, data, signal, method, findings, and limitations to exact evidence. |
| **Review the claims** | A five-step review lets you confirm, question, or correct claims while preserving the original AI draft. |
| **Define the implementation** | Build a typed Implementation Contract from an explicit Map version, review six steps, compare revisions, and export JSON or Markdown. |

Glyph distinguishes author-stated facts, derived values, human decisions, and missing information. Evidence gaps and conflicts remain visible; exported contracts do not execute code or imply that a strategy is ready to trade.

Processing checks local readiness before enqueueing a persistent background job, validates block coverage, and caches successful translation batches. Changed or missing source files retain their last readable result, and failed reprocessing does not replace it. Upload limits and external-tool timeouts bound local processing.

The [product roadmap](docs/plans/2026-09-13-product-roadmap.md) tracks phased improvements and their acceptance criteria.

**Current limits:** Glyph is pre-1.0 and intended for a trusted single user. Summary claims are AI drafts: exact quotation checks establish citation integrity, not the correctness of a model's interpretation. Scanned documents require a separately configured OCR adapter. Summaries, Research Maps and Implementation Contracts use the configured research provider; OrcaRouter currently supports document translation only. Mock mode is labeled development output, not real model evaluation.

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

Open `http://127.0.0.1:5173`, place a document in `book/` or upload one, then select **Process** and **Research Map**. Generate the map, follow the five-step review, and open exact evidence in the full Reader. From a current Map, select **Build Implementation Contract** for the six-step implementation review and a typed export. Set `GLYPH_FRONTEND_PORT` in `.env` if that port is occupied.

Process first checks document and provider readiness, then shows queued/running progress. Refreshing the browser restores job state. Cancel stops work at a safe boundary; an in-flight external call may finish first. After a backend restart, unfinished work is marked interrupted and can be retried with current settings and compatible cached batches. See the [processing guide](docs/document-processing.md) for recovery and API details.

In **Full Reader**, choose **Generate summary** to request an evidence-linked overview and section claims. Expand a claim to inspect its exact quotation and jump to the source block. Failed attempts retain the previous version; changed Reader content makes it stale. Summary generation is explicit and uses a persistent job. See the [summary guide](docs/evidence-linked-summaries.md) for provider configuration and validation limits.

Uploaded files are stored under `data/uploads/` with internal UUID names while their original display names remain in the catalog. A changed source is marked **stale** and keeps its last-good reader available until reprocessing succeeds. A removed source is marked **missing**; stored text remains readable, but processing and page rendering are blocked until the source returns.

## Translation providers

Open **Translation settings** in the workspace to choose Claude Code, Codex CLI, or OrcaRouter. Changes apply to new document-processing runs. Summaries, Research Maps and Implementation Contracts continue to use `GLYPH_AI_MODE` from your environment.

For OrcaRouter:

1. Create an account and obtain your own API key.
2. Select **OrcaRouter**, enter a text-model ID with JSON output support, and paste the key.
3. Apply settings, then process a document. Check the provider's model pricing and account limits before a large run.

For persistent local configuration, add the following to your ignored `.env` file:

```dotenv
GLYPH_AI_MODE=claude_cli
GLYPH_TRANSLATION_PROVIDER=orcarouter
GLYPH_ORCAROUTER_MODEL=your-text-model-id
ORCAROUTER_API_KEY=your-api-key
```

Keep `GLYPH_AI_MODE` set to your authenticated Claude Code or Codex CLI for research generation. The translation override does not change that provider.

Keys entered in the interface remain in backend memory and are never returned by the settings API. Restarting the backend clears session overrides and restores environment configuration. Glyph sends requests to `https://api.orcarouter.ai/v1/chat/completions`; a referral URL is an optional signup link, not an API endpoint or credential.

[Create an OrcaRouter account](https://www.orcarouter.ai/ref/ref_790f54197e176818f92b) · [Browse models](https://www.orcarouter.ai/models)

**Referral disclosure:** Glyph may receive 5% of eligible referred usage. Using the referral link is optional; translation uses your account and your API key.

## Privacy Model

Glyph does not commit or upload runtime artifacts to this repository. The following stay local and are ignored by git:

- documents in `book/`;
- uploaded files, rendered pages, SQLite databases, screenshots, and AI cache under `data/`;
- `.env` and project-local `.claude/` or `.codex/` settings;
- Python environments, Node dependencies, build output, and logs.

Only `book/.gitkeep` is tracked so the input directory exists after cloning. CLI credentials remain in the provider's own user-level credential store; Glyph neither reads nor copies those files.

Local-first describes storage and application execution, not offline model inference. Text sent for translation is processed by the selected Claude, OpenAI, or OrcaRouter service (including its upstream model provider) under your account's terms and usage limits. Research Map and Contract generation also send evidence text to the configured CLI provider. External OCR has its own data-handling behavior. Do not process sensitive material unless that provider arrangement is appropriate for it.

## OCR Modes

`GLYPH_OCR_MODE=mock` is the default development mode. Despite the name, it uses Poppler text extraction for text-backed PDFs and deterministic behavior for tests. It does not perform real OCR: scanned PDFs and images are rejected with a configuration message. Plain-text development fixtures remain explicitly labeled as fixtures. Configure an OCR adapter before processing scanned PDFs or document photos.

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
| `GLYPH_TRANSLATION_PROVIDER` | `GLYPH_AI_MODE` | Optional translation-only provider override, including `orcarouter` |
| `GLYPH_ORCAROUTER_MODEL` | unset | Exact OrcaRouter text-model ID; required for OrcaRouter |
| `ORCAROUTER_API_KEY` | unset | Your OrcaRouter API key; keep it in ignored local configuration |
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
| `GLYPH_CONTRACT_CLI_BLOCK_BATCH_SIZE` | `8` | Reader blocks per Implementation Contract extraction request |
| `GLYPH_BOOK_DIR` | `book/` | Optional source-document directory override |
| `GLYPH_DATA_DIR` | `data/` | Optional runtime-data directory override |
| `GLYPH_DATABASE_URL` | local SQLite | Optional SQLAlchemy database URL |

OrcaRouter uses one worker, at most eight blocks per batch (or a lower `GLYPH_CLI_BATCH_SIZE`), and `GLYPH_CLI_TIMEOUT_SECONDS` for its request timeout. Truncated responses are split into smaller batches; an oversized single block fails with an actionable message.

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

Database changes are managed by Alembic and applied automatically at backend startup. The migration bootstrap recognizes the original public schema and preserves its data; it rejects unknown partial schemas instead of resetting them. Back up `data/` and `book/` before upgrading. See the [Research Map guide](docs/research-map.md) and [Implementation Contract guide](docs/implementation-contract.md) for evidence guarantees, version/review semantics, recovery, exports, and trust boundaries, and [CONTRIBUTING.md](CONTRIBUTING.md) for pull-request expectations.

## Project Layout

```text
book/          ignored user documents
data/          ignored SQLite, uploads, page images, and AI cache
backend/       FastAPI, SQLAlchemy, OCR, CLI and OrcaRouter adapters
frontend/      React, TypeScript, Vite, and KaTeX reader
scripts/       setup and local development commands
docs/plans/    architecture and implementation decisions
docs/adr/      durable architectural decisions
```

## Contributing and Security

Issues and focused pull requests are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md), and use the private process in [SECURITY.md](SECURITY.md) for vulnerabilities. Do not attach real documents, databases, credentials, or unsanitized provider output to public reports.

## License

[MIT](LICENSE)
