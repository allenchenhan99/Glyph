# Public CLI Release Design

## Goal

Publish Glyph as a clean public repository that another person can clone, connect to their own authenticated Claude Code or Codex CLI, and run without receiving any of the original developer's books, runtime data, credentials, caches, or machine-specific paths.

## Public Boundary

The public repository contains application source, tests, generic setup scripts, example configuration, architecture documentation, and an empty `book/.gitkeep`. It excludes source documents, uploaded files, rendered pages, SQLite databases, AI batch caches, screenshots, logs, local environment files, CLI project settings, Python environments, and dependency build output.

CLI authentication remains entirely user-owned. Glyph invokes `claude` or `codex` from `PATH`; it does not read, copy, or commit files from a user's home-directory CLI configuration. `.claude/` and `.codex/` are ignored defensively if users create project-local settings.

## Clone Experience

The supported public workflow is:

1. Clone the repository.
2. Run `./scripts/setup.sh` to create a project virtual environment and install frontend dependencies.
3. Copy `.env.example` to `.env` and choose `claude_cli` or `codex_cli`.
4. Confirm the selected CLI is installed and authenticated.
5. Put personal documents in `book/` or use upload.
6. Run `./scripts/dev.sh` and open the local frontend.

The README distinguishes text-backed PDF support from scanned-image OCR. Poppler is required for PDF text extraction and page rendering. Unlimited-OCR remains an optional external installation selected through environment configuration.

## Publication Strategy

The existing development history stays local because it contains machine-specific paths and generated artifacts in old commits. Publication uses a new orphan branch containing one reviewed snapshot commit with a GitHub noreply author email. The empty public GitHub repository receives that snapshot as `main`.

The release uses an MIT license under `Glyph contributors`, avoiding personal contact details while allowing cloning, modification, and redistribution.

## Verification

Before publication, run backend tests, frontend tests, production build, shell syntax checks, ignore assertions, secret/path scans, and `git diff --check`. After pushing, clone the public `main` into a temporary directory, verify no private/runtime files exist, run setup, rerun both test suites and build, and confirm the remote default branch is `main`.
