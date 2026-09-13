# Evidence-linked summaries

Open a processed document in **Full Reader** and choose **Generate summary**. Generation is explicit: importing, translating, or opening a document does not send an additional summary request. Glyph shows the provider before generation.

Summaries use the existing research provider (`GLYPH_AI_MODE`: `claude_cli`, `codex_cli`, or `mock`) and `GLYPH_CLI_MODEL`. This configuration is separate from Translation settings and its OrcaRouter key. The mock produces labeled development excerpts; it does not evaluate summarization quality.

## Reading a summary

The panel groups claims into a document overview and sections. Expand a claim to read its exact source quotation, then choose **Go to source page** to focus the cited Reader block. Links appear only for blocks present in the displayed Reader. Historical quotations remain visible when their original blocks are no longer in that view.

Every published claim has an exact quotation from an allowed source block. Glyph checks block membership, offsets, section membership, and quotation text before publication. These checks establish citation integrity; they do not prove that a model's interpretation follows from the quotation. Claims remain **AI drafts** that need human checking.

## Progress and recovery

The summary job is stored locally. You can reload or leave the Reader and return to observe the job. A failed or interrupted attempt retains the last published version and offers retry. Restart does not automatically send summary requests again. Research Map's existing restart policy remains separate.

Changing or reprocessing the Reader makes a prior summary stale. A fingerprint of the actual block set detects identical-file reprocessing too, where the file hash stays the same but block identities change. Generation checks source and Reader identity again before publishing; a conflicting change cannot activate a new summary for the wrong snapshot.

From a Research Map or Implementation Contract citation view, use **Full Reader** to generate a summary of the current document. This keeps generation tied to the current Reader rather than the historical evidence being inspected.

## Request limits

CLI generation batches section input and rejects a source block longer than 12,000 characters rather than truncating it. Quotes are limited to 2,000 characters, section prompts to 60,000 characters, and overview prompts to 120,000 characters with at most 200 accepted quotes. Exceeding a limit fails explicitly and preserves any previous version. These are character limits, not guarantees that a particular model has sufficient context capacity.

## API

- `GET /api/documents/{id}/summaries`: current state, provider, last published version, and latest job.
- `POST /api/documents/{id}/summaries`: explicitly queue generation and return HTTP 202.

The state is `not_generated`, `generating`, `available`, `stale`, or `failed`. A generating or failed state may include a previous version. Provider output that fails evidence or coverage validation is not published.
