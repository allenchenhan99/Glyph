#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

# Explicit launch environment overrides .env defaults, including isolated workspaces.
glyph_env_names=()
glyph_env_values=()
while IFS= read -r glyph_env_name; do
  case "$glyph_env_name" in
    GLYPH_*|ORCAROUTER_API_KEY)
      glyph_env_names+=("$glyph_env_name")
      glyph_env_values+=("${!glyph_env_name}")
      ;;
  esac
done < <(compgen -e)

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

for glyph_env_index in "${!glyph_env_names[@]}"; do
  printf -v "${glyph_env_names[$glyph_env_index]}" '%s' "${glyph_env_values[$glyph_env_index]}"
  export "${glyph_env_names[$glyph_env_index]}"
done
unset glyph_env_names glyph_env_values glyph_env_name glyph_env_index

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]] || [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
  echo "Dependencies are missing. Run ./scripts/setup.sh first." >&2
  exit 1
fi

AI_MODE="${GLYPH_AI_MODE:-claude_cli}"
FRONTEND_PORT="${GLYPH_FRONTEND_PORT:-5173}"
BACKEND_PORT="${GLYPH_BACKEND_PORT:-8000}"
for glyph_port in "$FRONTEND_PORT" "$BACKEND_PORT"; do
  if [[ ! "$glyph_port" =~ ^[0-9]{1,5}$ ]] || (( 10#$glyph_port < 1 || 10#$glyph_port > 65535 )); then
    echo "GLYPH_FRONTEND_PORT and GLYPH_BACKEND_PORT must be integers from 1 to 65535." >&2
    exit 1
  fi
done
export GLYPH_BACKEND_PORT="$BACKEND_PORT"
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
    CLI_COMMAND=""
    echo "GLYPH_AI_MODE is invalid; the workspace will show configuration recovery guidance." >&2
    ;;
esac

if [[ -n "$CLI_COMMAND" ]] && ! command -v "$CLI_COMMAND" >/dev/null 2>&1; then
  echo "$CLI_COMMAND CLI was not found. Research features need setup; the workspace can still open for translation settings." >&2
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

echo "Starting Glyph backend at http://127.0.0.1:$BACKEND_PORT"
(
  cd "$ROOT_DIR/backend"
  exec "$ROOT_DIR/.venv/bin/python" -m uvicorn glyph.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT"
) &
backend_pid=$!

echo "Starting Glyph frontend at http://127.0.0.1:$FRONTEND_PORT"
(
  cd "$ROOT_DIR/frontend"
  exec npm run dev -- --port "$FRONTEND_PORT" --strictPort
) &
frontend_pid=$!

while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
  sleep 1
done

echo "A Glyph service stopped unexpectedly; shutting down the other service." >&2
exit 1
