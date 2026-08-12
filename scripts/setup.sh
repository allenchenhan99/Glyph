#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python was not found. Install Python 3.11 or newer." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Glyph requires Python 3.11 or newer." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm was not found. Install Node.js 22 or newer." >&2
  exit 1
fi

if ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 22 ? 0 : 1)'; then
  echo "Glyph requires Node.js 22 or newer." >&2
  exit 1
fi

echo "Creating Python environment..."
"$PYTHON_BIN" -m venv "$ROOT_DIR/.venv"
"$ROOT_DIR/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$ROOT_DIR/.venv/bin/python" -m pip install -e "$ROOT_DIR/backend[dev]"

echo "Installing frontend dependencies..."
npm --prefix "$ROOT_DIR/frontend" ci

mkdir -p "$ROOT_DIR/book" "$ROOT_DIR/data"

if ! command -v pdftotext >/dev/null 2>&1 || ! command -v pdftoppm >/dev/null 2>&1; then
  echo "Warning: Poppler is missing. Install it before processing PDFs." >&2
fi

echo "Setup complete. Copy .env.example to .env, select a CLI provider, then run ./scripts/dev.sh."
