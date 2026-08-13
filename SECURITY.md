# Security Policy

## Supported version

Glyph is pre-1.0. Security fixes are made on the latest `main` branch; older commits and forks are not supported release lines.

## Report a vulnerability privately

Use GitHub's **Security** tab and select **Report a vulnerability** to open a private security advisory with the maintainers. Include affected revision, impact, minimal reproduction steps, and suggested mitigation when available. Do not include private documents, credentials, provider responses, or exploit details in a public issue.

If private vulnerability reporting is unavailable, open a public issue containing only a request for a private maintainer contact. Do not disclose the vulnerability there. Please allow the maintainers time to reproduce and coordinate a fix before public disclosure.

## Deployment and trust model

Glyph is a trusted, single-user local application. Its development servers bind to loopback and do not implement user authentication, tenant isolation, TLS termination, or hardened internet-facing deployment. Do not expose either service directly to a network or run it as a shared multi-user service.

Uploaded and discovered documents are untrusted input. Glyph bounds uploads and external processes, but Poppler, OCR tools, AI CLIs, and their dependencies remain part of the attack surface. Keep them patched and process sensitive documents only on a machine and provider account appropriate for that data.

When `GLYPH_AI_MODE` selects Claude Code or Codex CLI, extracted document text is sent to that provider under the authenticated user's account, terms, retention policy, and usage limits. Glyph does not copy provider credentials into its database.

Research Map sends bounded Reader blocks to the selected CLI in two schema-constrained phases: evidence candidate extraction, then synthesis from validated evidence. Prompts mark document content as untrusted data and Glyph supplies no tool or network access to the CLI invocation. These controls do not make model output trustworthy; inspect exact evidence and original pages.

Research Map jobs run in one local process and one worker. This is not a hardened distributed queue and must not be scaled by starting multiple public-facing application processes. Failed generation retains the previous active version and records a sanitized public error; local server logs can contain diagnostic context and must be protected.

Implementation Contract treats document text, provider JSON, formulas, Markdown, and code-like strings as untrusted data. The provider receives bounded, delimited Reader content with strict schemas and no Glyph-supplied tool or network access. Provider output cannot supply trusted document, Map, block, page, path, or source identity and cannot set readiness. The backend derives identity, validates exact quote anchors and optional Map links, rejects unknown vocabulary and unsafe structured strings, and computes readiness deterministically.

Glyph stores and exports generated formulas and code-like values as inert data; it does not execute them. Human decisions are append-only overlays with reasons and item signatures, so provider drafts and earlier decisions remain auditable. Contract generation, recovery, validation, or persistence failure preserves the prior active contract. Contract jobs share the process-local single-worker deployment boundary described above.

JSON and Markdown exports can contain source quotations, translated context, document and Map identifiers, content hashes, implementation choices, and decision history. Write exports only to trusted local paths, protect them like the source document, inspect them before sharing, and never pipe generated fields directly into a shell, interpreter, SQL client, template engine, or code-execution service. Local provider cache and server logs under the configured data/runtime environment may contain sensitive diagnostic context and must not be attached to public reports.

## Data, backups, and upgrades

The SQLite database, uploads, rendered pages, and AI cache are stored under `data/`; discovered input files are stored under `book/` unless overridden. Stop Glyph before making a consistent backup, then copy both directories to protected storage. Treat backups as sensitive because they may contain complete source text and translations.

Application startup applies forward Alembic migrations. Before upgrading across revisions, back up `data/` and `book/`. The compatibility, Research Map, and `0004_implementation_contracts` migrations preserve public legacy/Reader data and reject unknown partial schemas instead of deleting data. Immutable maps and contracts retain cited historical Reader blocks, so deleting only current document outputs is not a safe erasure procedure. There is no automatic downgrade, backup, secure-delete, or retention-policy facility.
