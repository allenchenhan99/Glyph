#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]] || [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
  echo "Dependencies are missing. Run ./scripts/setup.sh first." >&2
  exit 1
fi

AI_MODE="${GLYPH_AI_MODE:-claude_cli}"
FRONTEND_PORT="${GLYPH_FRONTEND_PORT:-5173}"
case "$AI_MODE" in
  claude_cli)
    CLI_COMMAND="claude"
    ;;
  codex_cli)
    CLI_COMMAND="codex"
    ;;
  mock)
    CLI_COMMAND=""
    ;;
  *)
    echo "Unsupported GLYPH_AI_MODE: $AI_MODE" >&2
    exit 1
    ;;
esac

if [[ -n "$CLI_COMMAND" ]] && ! command -v "$CLI_COMMAND" >/dev/null 2>&1; then
  echo "$CLI_COMMAND CLI was not found. Install and authenticate it, or change GLYPH_AI_MODE." >&2
  exit 1
fi

if ! command -v pdftotext >/dev/null 2>&1 || ! command -v pdftoppm >/dev/null 2>&1; then
  echo "Warning: Poppler is missing. PDF extraction and page previews will not work." >&2
fi

backend_pid=""
frontend_pid=""

cleanup() {
  if [[ -n "$backend_pid" ]]; then
    kill "$backend_pid" 2>/dev/null || true
  fi
  if [[ -n "$frontend_pid" ]]; then
    kill "$frontend_pid" 2>/dev/null || true
  fi
}

trap cleanup EXIT
trap 'exit 130' INT TERM HUP

echo "Starting Glyph backend at http://127.0.0.1:8000"
(
  cd "$ROOT_DIR/backend"
  exec "$ROOT_DIR/.venv/bin/python" -m uvicorn glyph.main:app --reload --host 127.0.0.1 --port 8000
) &
backend_pid=$!

echo "Starting Glyph frontend at http://127.0.0.1:$FRONTEND_PORT"
(
  cd "$ROOT_DIR/frontend"
  exec npm run dev -- --port "$FRONTEND_PORT"
) &
frontend_pid=$!

while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
  sleep 1
done

echo "A Glyph service stopped unexpectedly; shutting down the other service." >&2
exit 1
