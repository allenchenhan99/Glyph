# Public-document acceptance corpus

This corpus measures a small, explicit set of behaviors. It is not a certification of financial research, a representative estimate of translation accuracy, or evidence that every page is complete.

`corpus.json` pins two publicly available sources by SHA-256 and selects physical PDF pages, numbered from one. Downloaded PDFs, page derivatives, model responses and runtime databases stay outside git. Source rights and attribution links are in the manifest; the material is not endorsed by NIST or the Federal Reserve Board.

## Ground truth

The selected pages were visually inspected before fixing these expectations:

| Case | Expected source behavior |
| --- | --- |
| NIST physical page 14 (printed page 9) | Read the left column before the right. Equations B-1 and B-2 include an equals sign, a summation with limits, powers/indices, and a less-than-or-equal relation. Text anchors alone cannot verify these formulas. |
| NIST physical page 15 (printed page 10) | Table B.1 has 28 data rows and six probability columns. Five sampled rows must preserve their ordered numeric values under the column headers. This is 5 sampled rows, not 28-row completeness. |
| FEDS physical page 4 (printed page 3) | Single-column prose describes three hedging steps, cash/non-cash decomposition, a $100/$50 example, $1.00/$1.01 valuation, and 0.8% annual return. The last sentence continues onto the next page. |
| FEDS physical page 38 (printed page 37) | The first panel has five cash-share columns (Low, 2, 3, 4, High). Sampled Small, Big and Average rows must preserve column order. Other return and standard-deviation panels are not covered by this automated row check. |
| NIST page 15 raster derivative | A 100-dpi PNG made with `pdftoppm` contains no text layer. The default extraction adapter must refuse it with OCR setup guidance, not fabricate text. This is an artificial scan, not a historical scan corpus. |

Whitespace is normalized for text-anchor and passage matching. Table checks compare complete line token sequences, so a right value under the wrong column fails. Checks are applied separately to extracted page text and the prepared Reader blocks. The latter catches line/row structure lost during block preparation.

Every extracted page is counted, but a page containing any text is not necessarily complete. Exact-quote evidence validation proves that a quotation exists in extracted text; it does not prove the extraction matches the original visual page or that a claim follows from the quotation.

## Run extraction checks

Install the backend and Poppler using the project setup guide. Use an external directory:

```bash
.venv/bin/python -m glyph.quality \
  --manifest docs/quality/corpus.json \
  --corpus-dir /tmp/glyph-quality-corpus \
  --output /tmp/glyph-quality-report.json \
  --download
```

Omit `--download` to require existing local files. Missing files and mismatched hashes fail explicitly; they do not silently skip acceptance. The report records content-check failures without treating a completed measurement as a product quality pass. These checks make no model requests and do not load the user's database or application settings.

## Run a bounded live translation

This opt-in command sends one selected public page to your authenticated CLI account. It makes at most three provider attempts, with a 120-second timeout per attempt, and saves source/translated blocks outside git:

```bash
.venv/bin/python scripts/evaluate_live_quality.py \
  --manifest docs/quality/corpus.json \
  --corpus-dir /tmp/glyph-quality-corpus \
  --case feds-prose --provider claude --model sonnet \
  --output /tmp/glyph-quality-live-feds.json --run-live
```

Use a full model identifier when pinning a repeatable evaluation. An alias such as `sonnet` can change; the current adapter does not expose the resolved model identity. The report records the requested value and CLI version. Successful adapter validation proves block coverage and nonempty output, not semantic quality.

To evaluate real summary claims on the same bounded public page, add `--task summary` and choose another output filename. This invokes the production section/overview provider and exact-quote validation without a database or mock summary generation. Compare every accepted claim against both its quotation and the page; exact-quote acceptance alone is not a semantic score.

For manual evaluation, compare all source/translated text against the rendered page. Check the six numeric anchors ($100, $50, $1.00, $1.01, 0.8%, 2006), the three-step direction, the distinction between cash and non-cash returns, beta dispersion, both named pricing models, Traditional Chinese, and whether the page-ending incomplete sentence was improperly completed. Record failures and uncertainty; never infer a broad accuracy percentage from this one page.
