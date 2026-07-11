# Public CLI Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a privacy-safe Glyph repository that fresh clones can run with each user's own Claude or Codex CLI login.

**Architecture:** Keep authentication outside the repository and treat the CLI executable as the provider boundary. Add repository-level setup and development scripts, strict ignore rules, generic environment configuration, and publish one clean orphan snapshot to the empty GitHub repository.

**Tech Stack:** Bash, Python 3.11+, FastAPI, SQLite, Node.js/npm, React, Claude Code CLI, Codex CLI, git, GitHub CLI.

## Global Constraints

- Never commit any file under `book/` except `book/.gitkeep`.
- Never commit `data/`, SQLite, uploads, rendered pages, AI cache, screenshots, `.env`, `.claude/`, or `.codex/`.
- Do not publish the existing development history or machine-specific absolute paths.
- The public remote is `https://github.com/allenchenhan99/Glyph.git` and the public default branch is `main`.
- CLI authentication belongs to each user and must not be copied into project configuration.

---

### Task 1: Privacy Boundary

**Files:**
- Modify: `.gitignore`
- Modify: `docs/plans/2026-07-11-document-translation-reader-design.md`
- Modify: `docs/plans/2026-07-11-cli-translation-and-math-rendering.md`
- Create: `.env.example`

**Interfaces:**
- Consumes: local runtime paths used by Glyph.
- Produces: a repository snapshot in which user documents, runtime state, credentials, and machine paths cannot be staged accidentally.

- [ ] Add explicit ignore rules for `book/*` with only `.gitkeep` re-included, `data/`, `.env*` with `.env.example` re-included, CLI settings, databases, logs, and local third-party checkouts.
- [ ] Replace developer-specific absolute paths in current documentation with repository-relative descriptions.
- [ ] Add generic CLI configuration to `.env.example` without secrets or personal paths.
- [ ] Verify with `git check-ignore` that representative private files are ignored and `.env.example` plus `book/.gitkeep` remain trackable.
- [ ] Run a repository scan for usernames, home paths, secrets, tokens, and source-document names outside ignored directories.

### Task 2: Fresh-Clone Workflow

**Files:**
- Create: `scripts/setup.sh`
- Create: `scripts/dev.sh`
- Create: `LICENSE`
- Modify: `README.md`

**Interfaces:**
- Consumes: Python 3.11+, npm, Poppler, and an authenticated `claude` or `codex` executable.
- Produces: `./scripts/setup.sh` for deterministic dependency installation and `./scripts/dev.sh` for concurrent local backend/frontend startup.

- [ ] Implement setup with `python3 -m venv .venv`, editable backend dev dependencies, and `npm ci` in `frontend/`.
- [ ] Implement development startup that loads optional `.env`, validates the configured CLI command, starts FastAPI and Vite, and terminates both children on exit.
- [ ] Add an MIT license owned by `Glyph contributors`.
- [ ] Rewrite README quick start, prerequisites, provider selection, privacy model, OCR modes, troubleshooting, tests, and directory behavior for an unfamiliar clone user.
- [ ] Verify both scripts with `bash -n` and assert executable permissions.

### Task 3: Local Release Verification and Commit

**Files:**
- Modify: all current intended backend/frontend/public-release files.
- Exclude: `book/<personal-document>.pdf` and every ignored runtime artifact.

**Interfaces:**
- Consumes: current feature worktree.
- Produces: one tested local feature commit from which the public snapshot can be exported.

- [ ] Run `pytest -q` in `backend/`.
- [ ] Run `npm test -- --run` and `npm run build` in `frontend/`.
- [ ] Run `bash -n scripts/setup.sh scripts/dev.sh`, `git diff --check`, ignore assertions, and a tracked-file privacy scan.
- [ ] Stage intended paths explicitly and confirm personal documents plus runtime data are absent from `git diff --cached --name-only`.
- [ ] Commit the complete tested implementation on `feat/document-translation-reader`.

### Task 4: Clean Public Main

**Files:**
- Create in temporary worktree: a clean snapshot of the committed feature tree.

**Interfaces:**
- Consumes: committed feature branch tree.
- Produces: orphan branch `public-main` with one privacy-reviewed initial commit pushed to remote `main`.

- [ ] Add and verify the empty GitHub repository as `origin`.
- [ ] Create a temporary orphan worktree and export only the committed tree into it.
- [ ] Confirm the orphan tree has one pending snapshot, no git history parent, no ignored private files, and no machine paths.
- [ ] Commit with a GitHub noreply author email and push `public-main:main` with upstream tracking.
- [ ] Set and verify the GitHub repository default branch as `main`.

### Task 5: Remote Fresh-Clone Verification

**Files:**
- Runtime only: temporary fresh clone outside the project.

**Interfaces:**
- Consumes: `origin/main` as an unaffiliated clone would receive it.
- Produces: evidence that the published repository installs, tests, builds, and excludes all private/runtime artifacts.

- [ ] Clone `origin/main` into a new temporary directory.
- [ ] Inspect tracked files and scan for local paths, credentials, source documents, SQLite, caches, and uploads.
- [ ] Run `./scripts/setup.sh` from the fresh clone.
- [ ] Run backend tests, frontend tests, frontend production build, and shell syntax checks from the fresh clone.
- [ ] Verify GitHub URL, public visibility, default branch, initial commit, and final remote tree.
