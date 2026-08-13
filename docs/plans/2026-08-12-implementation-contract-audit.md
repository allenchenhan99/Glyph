# Implementation Contract Milestone Audit

**Branch:** `feat/implementation-contract`
**Base:** `b0ef27226df6dd0d3ca20c4fed974a1c44ba428f` (`feat/research-map`)
**Reviewed implementation head:** `eeb42db`
**Acceptance date:** 2026-08-13 (Asia/Taipei)

## Disposition

The eighteen-task Implementation Contract plan is implemented. Automated quality gates, the deterministic benchmark, isolated-data browser scenarios, migration and recovery checks, branch-scope checks, and four rounds of independent review passed. No Critical or Important finding remains unresolved. The branch is ready to merge, subject to the repository owner's normal pull-request process.

## Automated quality gates

All commands ran from the milestone worktree with Python 3.11 and the checked-in frontend lockfile.

| Gate | Command | Result |
| --- | --- | --- |
| Backend lint | `ruff check src tests` | Passed; zero findings |
| Backend format | `ruff format --check src tests` | Passed; 60 files already formatted |
| Backend typing | `mypy src/glyph` | Passed; 31 source files, zero issues |
| Backend tests and coverage | `pytest --cov=glyph --cov-report=term --cov-fail-under=85` | 348 passed; 91.54% coverage |
| Backend static security | `bandit -q -r src/glyph` | Passed; zero findings |
| Python dependency audit | `pip-audit --skip-editable` | Passed; zero known vulnerabilities; editable `glyph-backend` reported as skipped |
| Frontend tests | `npm run test:coverage` | 13 files and 125 tests passed; configured coverage thresholds passed |
| Frontend production build | `npm run build` | Passed; 1,716 modules transformed |
| Frontend dependency audit | `npm audit --audit-level=high` | Passed; zero vulnerabilities |
| Contract benchmark | `pytest tests/test_contract_benchmark.py -q` | 16 passed |

The virtual environment initially inherited vulnerable bootstrap releases of `pip` and `setuptools`. They were upgraded to `pip 26.2.1` and `setuptools 84.0.0`, after which the audit was rerun instead of suppressed. No project manifest or lockfile changed. The production build retains Vite's advisory that the 549.60 kB main bundle exceeds 500 kB; this is not a correctness or security failure.

## Benchmark acceptance

The three checked-in gold fixtures (monthly accounting, daily price, and intentionally incomplete cross-market long/short) met every non-negotiable invariant:

- unsupported silent-default rate: **0%**;
- required missing-blocker detection: **100%**;
- false-ready count: **0**;
- accepted evidence coverage: **100%**;
- JSON validity: **100%**;
- identical deterministic mock-run diff count: **0**;
- failed generation preserves the previous active version: **passed**.

## Browser and service acceptance

The backend and Vite frontend ran in mock mode against isolated directories under `/tmp`; no acceptance documents, SQLite files, exports, or screenshots were added to Git.

1. A monthly accounting fixture was discovered in the isolated book, processed from the Library, mapped, and converted into a 16-item Contract. A cross-market fixture produced 15 typed items and exactly two blockers: weighting and transaction cost.
2. All six Traditional Chinese review steps were traversed. Exact English evidence, aligned Traditional Chinese context, and Reader open/return were verified.
3. Supported items exposed confirm, question, and reasoned-correction controls. Questioning a supported item changed backend readiness to blocked; acceptance then found that the open Contract still showed the pre-save audit. A red regression test was added before fixing the client to refetch the active Contract after each saved resolution and ignore a refetch for a document that is no longer active.
4. The cross-market Contract exposed no weighting or zero-cost default. A reasoned `equal_weight` decision resolved weighting. Transaction cost offered neither a mandatory-item N/A escape nor a generic truthy override: it required a reason and stored the structured scalar `gross_replication`. Readiness became `implementation_ready` only after all 15 items were reviewed and backend re-audit reported zero blockers.
5. JSON English and bilingual Markdown exports both returned HTTP 200 from the active version. Contract creation with an invalid provider returned a safe public failure while the previous active Contract remained readable and implementation-ready.
6. Restarting both services against the same data recovered both documents, three Contract versions, and 20 append-only resolutions. The fully reviewed cross-market Contract remained 15/15 and implementation-ready.
7. Changing the monthly source marked its old Map and Contract stale and disabled resume. Reprocessing preserved 11 blocks under the old source hash and wrote 13 under the new hash; `PRAGMA foreign_key_check` returned no rows. The old Contract still cited 11 old blocks.
8. Historical Contract navigation loaded the selected stale version. Its Reader evidence link requested the exact old source hash and displayed the old “six months” block after the source had changed to seven months. Because Glyph does not retain versioned source binaries, all 22 old Reader block sides displayed an explicit original-page-unavailable label and exposed zero links to the current seven-month PDF. The page endpoint also rejects an obsolete requested source hash with `409`. Version diff reported `evidence_changed` for all 16 affected items. The bounded, batched history query and exact historical Research Map version link are additionally covered by automated tests; the mock fixture did not contain a Contract evidence row linked to a Research Map node for a browser click.
9. At a 390 x 844 touch viewport, document and body widths equaled the 390 px viewport with no horizontal overflow. Tab navigation produced visible `:focus-visible`, and Enter opened Contract history. A final Lighthouse mobile snapshot on the historical Reader scored **100 accessibility** and **100 best practices**.
10. Acceptance removed Chrome's missing-field-name advisory by adding stable decision-field names under a red regression test. After reload, the console contained only development messages and the absent favicon 404; no uncaught application error appeared.

The browser automation file chooser rejected fixture paths outside its upload allowlist. Cross-market upload therefore used multipart HTTP against the same running service; processing, Map and Contract generation, decisions, evidence navigation, history, readiness, persistence, and export were then exercised through the UI.

## Defects found and fixed during completion review

The first independent review reported two Critical and six Important findings. All were fixed before the final gates:

- preserved both Research and Contract evidence across source changes, enabled SQLite foreign keys on every runtime connection, and verified old evidence with `foreign_key_check`;
- included `item_key` in stable signatures and resolution carry-forward keys to prevent cross-item decisions from carrying;
- added supported-item confirm, question, and correction controls; limited N/A to optional items; and made gross replication a structured scalar decision;
- made version diff include type changes and historical Reader/Map navigation request the exact selected lineage;
- correlated late history, diff, and activation responses to the active document; and bounded history to a maximum of 100 versions with batched loading;
- replaced a focus timing assertion with an observable wait to remove the frontend flake.

Browser acceptance additionally found and fixed the stale open-audit defect described above, plus the non-blocking decision-field semantics warning. Final type checking also exposed and removed a now-unused suppression comment on the SQLite foreign-key event handler.

The second independent review then found four Important trust gaps. Each received a red regression test before the implementation changed:

- after saving, both the open Contract and its Library summary now suppress readiness until the authoritative backend audit reloads; failure becomes **Readiness unverified** with an explicit retry instead of leaving a false-ready label;
- Contract Reader and Research Map deep links now correlate both document ID and request sequence, so a previous document's late response cannot switch the current surface;
- historical text snapshots no longer link to a current source page, and the page endpoint independently rejects an obsolete requested hash;
- a decision on an identical regenerated item continues the lineage revision number, supersedes the carried effective decision, and exports in timestamp order.

The third independent review found three remaining Important boundary cases. Each was reproduced under a red test and closed before the final gates:

- when the authoritative post-save Contract reload succeeds but the subsequent Library refresh fails, the active document's Library card now derives readiness, blockers, and review counts from the open active Contract instead of its retained list snapshot;
- once a Contract version has any descendant, its items are read-only, including after historical activation; sequential and concurrent ancestor/descendant regression tests prove only the lineage tip can append and the revision chain cannot fork;
- generated Reader page URLs now carry the retained source SHA-256, and the page endpoint recomputes the actual on-disk hash before serving or reusing a cached page image. A copied URL returns `409` after the file changes even when the catalog has not refreshed.

The fourth independent review found two final API/UI consistency gaps and prompted a related concurrency audit:

- the API now exposes authoritative `is_resolvable` state; only the active, unique lineage tip accepts decisions. Ancestors and inactive tips show a read-only alert and disabled decision controls while evidence navigation remains available, so the client never performs a knowingly doomed optimistic save;
- generation follows the unique lineage tip rather than whichever history version is active, refuses a pre-existing fork without changing activation, and shares a per-document mutation coordinator with resolution and activation in the API, worker, and CLI. A barrier-based race regression proves generation commits first, the waiting ancestor decision returns `409`, and the new tip contains no lost or phantom resolution.

## Migration, backup, and recovery

The backend gate includes migration tests proving revision `0004_implementation_contracts` preserves Reader and Research Map rows, creates no Contract rows, and declares the required foreign keys and uniqueness constraints. Revision `0005_contract_job_map_selection` preserves existing jobs.

For the final operator-level recovery check, both services were stopped before copying the isolated `data/` and `book/` trees. Original, backup, and restored SQLite files had identical SHA-256 `ecc4721ffd812423d46e275e68666d13289f73349b9f755215858736e463a7c9`. On the restored copy:

- `PRAGMA integrity_check` returned `ok`;
- `PRAGMA foreign_key_check` returned no rows;
- document count was 2 and preserved block count was 38;
- Contract version count was 3 and resolution count was 20;
- Alembic revision was `0005_contract_job_map_selection`;
- both source PDFs were restored.

Glyph intentionally provides forward startup migrations but no automatic backup or supported automatic downgrade. Operators must stop Glyph and protect both directories before upgrading, as documented in `docs/implementation-contract.md`.

## Security disposition

- Provider output is untrusted and passes strict Pydantic, domain, evidence, and deterministic audit validation before persistence.
- Providers cannot set `human_decision`, append resolutions, or choose readiness.
- CLI invocation uses an argument vector without a shell, bounded request and response sizes, timeout enforcement, and redacted public errors.
- Bandit, `pip-audit`, and `npm audit` are clean.
- Papers, evidence, translations, provider caches, and exports remain local unless the configured provider sends them elsewhere; telemetry remains off by default.

## Independent review

Four independent reviews covered base `b0ef2722` through the final completion content. The first through fourth rounds found, respectively, two Critical and six Important issues, four Important issues, three Important issues, and two Important issues plus a related generation/resolution race. Every finding was reproduced and fixed under regression coverage. The final targeted disposition independently reran backend (**348 passed**), frontend (**125 passed**), production build, Ruff, mypy, and `git diff --check`; it reported **no Critical or Important findings** and assessed the branch **ready to merge**.

Residual Minor findings are accepted and documented: the mutation coordinator is process-local within Glyph's supported single-process boundary; same-document decisions and activation wait while a generation provider call holds the coordinator; and the production bundle retains Vite's approximately 550 kB chunk advisory.

## Known limitations and follow-up candidates

- The deterministic mock recognizes fixture grammar; it is not a semantic natural-language parser. Representative real-paper extraction quality and ontology coverage still need separate evaluation.
- The production JavaScript bundle is 549.60 kB before gzip; route or component code splitting is a performance follow-up.
- Glyph preserves historical Reader text and evidence coordinates, but not versioned source binaries or page images. Historical original-page verification therefore requires an operator backup of the old `book/` contents; Glyph disables the link when it cannot prove the current file matches.
- Glyph does not yet create automatic backups or support automatic schema downgrade.
- The repository does not include a favicon. This does not affect Contract correctness or the Lighthouse accessibility and best-practices scores.

## Branch scope

`git diff --check` passed before committing this audit. The base-to-head diff contains the Implementation Contract design and plan, schema and migrations, backend and frontend implementation, fixtures and tests, operator and security documentation, and the completion fixes described above. No generated user data, virtual environment, build output, or local-path screenshot is tracked.
