# Public-document quality acceptance

## Goal and scope

Publish a reproducible, small acceptance corpus and an honest baseline of Glyph's document quality. Completing this milestone means the checks and report exist, failures are characterized and covered by regression checks, and the documentation reflects demonstrated limits. It does not require pretending every format is supported or claiming broad translation accuracy from a small sample.

## Corpus

Keep downloaded PDFs, rendered pages, databases, caches, and raw model responses outside git. Commit a manifest with source URLs, rights references, SHA-256, page selections, derivation commands, and expected results. Use two independently published sources, covering prose, formulas, tables, and a clearly labeled rasterized scan derivative:

- NIST Technical Note 1297 (1994), *Guidelines for Evaluating and Expressing the Uncertainty of NIST Measurement Results*, Barry N. Taylor and Chris E. Kuyatt. [Source](https://www.nist.gov/pml/nist-technical-note-1297), [rights](https://www.nist.gov/open/copyright-fair-use-and-licensing-statements-srd-data-software-and-technical-series-publications). Attribution: Republished courtesy of the National Institute of Standards and Technology.
- Ross, Chase P., Landon J. Ross, and Sharon Y. Ross (2022), *Cash-Hedged Stock Returns*, FEDS 2022-055. [Source](https://www.federalreserve.gov/econres/feds/cash-hedged-stock-returns.htm), [website rights](https://www.federalreserve.gov/disclaimer.htm). Cite the Federal Reserve Board; exclude third-party quoted material from committed excerpts. This is a preliminary working paper, not a verified investment result.

Candidate physical PDF pages: NIST 14 (formulas), 15 (table); FEDS 4 (prose), 38 (table). Inspect rendered pages before freezing expectations. A raster derivative must use a selected public page and be described as an artificial scan, not an independent historical scan.

## Acceptance rubric

| Dimension | Required evidence |
| --- | --- |
| Extraction | Expected page count and independently selected text anchors with numerator/denominator; label this sampled anchor recall, not whole-document completeness |
| Block alignment | Exact source identity, page references, unique block ordering, nonempty translated counterparts; distinguish structural alignment from semantic accuracy |
| Formulas | Compare selected rendered formulas with extracted operators, variable indices and Reader representation; record loss explicitly |
| Tables | Check selected row/column/value associations, not merely the presence of numbers anywhere in text |
| Evidence | Validate exact quotations and source revision; exercise browser navigation on a public source |
| Recovery | Scans without OCR fail clearly without fabricated content; failures/retries preserve a previous Reader where applicable |
| Live output | A bounded public excerpt through an installed real provider; record provider/model, scope and manual interpretation checks separately from deterministic runs |

## Implementation sequence

1. Freeze source provenance, hashes, page selections and a concise ground-truth rubric after visual inspection.
2. Add a reproducible corpus runner using isolated temporary storage, explicit download and live-model opt-ins, bounded subprocess/network timeouts, and machine-readable results. The default run must not call a model or use the user's workspace.
3. Add meaningful offline tests for the runner's checks and regression fixtures for actual defects discovered. Record expected unsupported cases as limitations, not successful extraction.
4. Run the real extraction path, deterministic workflow checks, and one bounded live-model evaluation. Inspect formulas/tables and verify a source-evidence jump in the browser.
5. Publish a baseline report with exact commands, versions, pass/fail counts, manual observations and remaining limits. Update README claims if evidence shows a gap.
6. Run applicable repository gates; review, PR and merge. Mark the roadmap and active goal complete only after the report and all required work are integrated.
