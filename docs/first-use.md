# Your first research session

Start with a small public document whose contents you can check. The getting-started guide shows your current local setup and links to the next available actions. Hide it when you no longer need it; **Show getting started** brings it back. Existing documents and reviews remain available.

## Choose providers

Three capabilities are independent:

| Capability | Configuration | What the check establishes |
| --- | --- | --- |
| Translation | **Translation settings**, or `GLYPH_TRANSLATION_PROVIDER` | CLI executable availability, or a locally configured OrcaRouter model and key |
| Summaries, Research Maps, Implementation Contracts | `GLYPH_AI_MODE` in `.env`; restart after changes | Research CLI executable availability |
| Document extraction | Poppler; `GLYPH_OCR_MODE` for scans | Local extraction tools or OCR adapter configuration |

These checks make no model requests. They do not verify authentication, balance, model access, or output quality. Translation settings do not change the research provider. An API key entered in the interface lasts only for the backend session.

For a deterministic workflow trial, use `GLYPH_AI_MODE=mock` and `GLYPH_TRANSLATION_PROVIDER=mock`. The workspace explicitly names the features producing development output. This trial checks navigation and processing, not translation or research quality. `GLYPH_OCR_MODE=mock` still extracts real text from text-layer PDFs with Poppler; it cannot read scanned images.

## Follow one document

1. **Upload your first document**, or place a PDF in the configured book directory and select **Refresh**.
2. Select **Process**. Resolve any readiness errors, then follow progress. Reloading restores the job; cancellation and retry preserve the last successful Reader.
3. Open **Full Reader**, inspect the aligned blocks, and explicitly **Generate summary**. Follow quotations back to their source before trusting a claim.
4. Open **Research Map**, generate a draft, and review its claims and evidence gaps.
5. From a current Map, **Build Implementation Contract**. Review its assumptions and blockers before exporting. A generated contract is not automatically ready to implement.

Returning workspaces offer continuation buttons based on their saved documents, maps and contracts. Missing or changed source files keep their previously stored reading and review results; restoring the source is required for processing and page rendering.

## Startup and recovery

`./scripts/dev.sh` opens the interface even if the selected research CLI is absent, so translation settings and setup guidance remain reachable. Install and authenticate the research CLI before generating research output.

The defaults are backend port 8000 and frontend port 5173. Set `GLYPH_BACKEND_PORT` and `GLYPH_FRONTEND_PORT` when either is occupied. The Vite proxy follows the backend port; an occupied frontend port causes an explicit failure rather than silently selecting another port. Exported `GLYPH_*` variables and `ORCAROUTER_API_KEY` take precedence over `.env` defaults when using this script.

If the backend cannot be reached, inspect its startup terminal and select **Retry connection** after fixing the issue. Invalid configuration produces recovery guidance naming the variable without echoing its value.

An unsupported database schema opens a recovery page instead of the research workspace. Glyph leaves that database unchanged and rejects document operations. Keep the old database, choose a **new empty** `GLYPH_DATA_DIR`, and update `GLYPH_DATABASE_URL` too if you set it explicitly. Restart Glyph. This creates a separate workspace; it does not import the old desktop database. Do not delete or reset the original to clear the message.

`GET /api/workspace` exposes these local capabilities and a `ready` or `blocked` state. A diagnostic backend returns `blocked` from `/api/health` and HTTP 503 for document operations; HTTP 200 from health alone does not establish readiness.

## Verification scope

The stage-three browser check used an isolated empty workspace and a generated text PDF: discovery, processing, Reader, Research Map, contract generation and resumption, keyboard hide/reopen, reload persistence, and translation-setting refresh. Model output was deterministic mock output. Synthetic unsupported-schema tests verify that the database bytes remain unchanged. Public-document content quality is evaluated separately in stage four of the [roadmap](plans/2026-09-13-product-roadmap.md).
