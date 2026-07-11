# CLI Translation and Math Rendering Design

## Goal

Replace Glyph's placeholder Traditional Chinese text with real translations produced through an authenticated Codex or Claude CLI, and render mathematical formulas as typeset LaTeX in the reader.

## Translation Boundary

The backend owns a CLI AI adapter selected through `GLYPH_AI_MODE`. `claude_cli` is the recommended default for live processing and `codex_cli` is an equivalent selectable provider. Both run non-interactively, disable model tools, require a JSON Schema response, and receive document text through standard input rather than shell arguments.

The adapter first performs deterministic block splitting so source coverage remains auditable. It then sends bounded batches of blocks to the CLI and requires exactly one result for every supplied block ID. Each result contains a genuine Traditional Chinese translation and, for formula blocks, a normalized LaTeX expression. Missing, duplicated, reordered, or malformed results fail the processing job explicitly. Glyph never presents source English with a translation prefix as if it were translated.

The mock adapter remains available only for automated tests and offline development. Its output is labelled deterministic test data and is not the live reader mode.

## Formula Data Flow

Formula blocks retain their original OCR text in `source_text`. A new nullable `formula_latex` field stores the display expression produced by the CLI. The reader payload exposes that field directly so presentation code does not attempt to infer mathematics from prose.

For a formula row, both columns render `formula_latex` with KaTeX. Any surrounding source wording remains visible on the left, while translated explanatory wording remains visible on the right. KaTeX's generated MathML provides an accessible representation. Invalid LaTeX is shown as a clearly marked rendering error alongside the original OCR text instead of a blank region.

## Persistence and Compatibility

SQLite startup migration adds the nullable `formula_latex` column to existing `blocks` tables. Reprocessing a document replaces its existing blocks, translations, sections, and summaries using the selected CLI adapter. Old rows remain readable before reprocessing, but formulas without `formula_latex` use an explicit unrendered fallback.

## Performance and Failure Handling

Blocks are translated in bounded batches to avoid one CLI process per paragraph. Prompt size and batch size are configurable, with conservative defaults suitable for long books. CLI timeout, non-zero exit status, invalid JSON, schema mismatch, and coverage mismatch include actionable errors in the processing job.

Document processing remains synchronous in the current architecture. The UI keeps the existing processing state and only exposes completed output after the full run succeeds.

## Verification

Backend tests cover CLI command construction, structured-output validation, complete block coverage, real Traditional Chinese output contracts, LaTeX persistence, and migration compatibility. Frontend tests assert that formulas are rendered by KaTeX rather than displayed as raw LaTeX text. Final verification reprocesses representative pages from the actual book and visually inspects paragraphs and formulas in the browser before running the complete book pipeline.
