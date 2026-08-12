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

## Data, backups, and upgrades

The SQLite database, uploads, rendered pages, and AI cache are stored under `data/`; discovered input files are stored under `book/` unless overridden. Stop Glyph before making a consistent backup, then copy both directories to protected storage. Treat backups as sensitive because they may contain complete source text and translations.

Application startup applies forward Alembic migrations. Before upgrading across revisions, back up `data/` and `book/`. The compatibility migration preserves the public legacy schema and rejects unknown partial schemas instead of deleting data. There is no automatic downgrade or backup facility.
