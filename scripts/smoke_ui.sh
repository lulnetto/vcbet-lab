#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_BIN="${CONDA_BIN:-/home/otten/miniforge3/bin/conda}"
CONDA_ENV="${CONDA_ENV:-ubet}"
PYTHON_BIN="${PYTHON_BIN:-}"
BASE_URL="${VCBET_SMOKE_BASE_URL:-http://127.0.0.1:8011}"
SMOKE_HOST_PORT="${BASE_URL#http://}"
SMOKE_HOST_PORT="${SMOKE_HOST_PORT#https://}"
SMOKE_HOST="${SMOKE_HOST_PORT%%:*}"
SMOKE_PORT="${SMOKE_HOST_PORT##*:}"
SMOKE_PORT="${SMOKE_PORT%%/*}"
SMOKE_TMP="$(mktemp -d)"
SERVER_PID=""
STARTED_SERVER=0

cleanup() {
  if [[ "$STARTED_SERVER" -eq 1 && -n "$SERVER_PID" ]]; then
    if kill -0 "$SERVER_PID" 2>/dev/null; then
      kill -TERM -- "-$SERVER_PID" 2>/dev/null || kill "$SERVER_PID" 2>/dev/null || true
      wait "$SERVER_PID" 2>/dev/null || true
    fi
  fi
  rm -rf "$SMOKE_TMP"
}
trap cleanup EXIT

cd "$PROJECT_ROOT"

echo "[ui-smoke] VCBet web UI runtime smoke"

curl_ok() {
  curl -fsS -o /dev/null "$1"
}

check_url() {
  local path="$1"
  curl_ok "$BASE_URL$path"
  echo "[ui-smoke] ok $path"
}

find_node() {
  if command -v node >/dev/null 2>&1; then
    command -v node
    return 0
  fi
  if [[ -x "/mnt/c/Program Files/nodejs/node.exe" ]]; then
    printf '%s\n' "/mnt/c/Program Files/nodejs/node.exe"
    return 0
  fi
  return 1
}

service_command() {
  if [[ -n "$PYTHON_BIN" ]]; then
    printf '%s\n' "$PYTHON_BIN"
    return 0
  fi
  local conda_root conda_python
  conda_root="$(cd "$(dirname "$CONDA_BIN")/.." && pwd)"
  conda_python="$conda_root/envs/$CONDA_ENV/bin/python"
  if [[ -x "$conda_python" ]]; then
    printf '%s\n' "$conda_python"
    return 0
  fi
  printf '%s\n' "$CONDA_BIN run --no-capture-output -n $CONDA_ENV python"
}

if curl_ok "$BASE_URL/health" 2>/dev/null; then
  echo "[ui-smoke] reusing running service at $BASE_URL"
else
  echo "[ui-smoke] starting service at $BASE_URL"
  read -r -a SERVICE_CMD <<<"$(service_command)"
  VCBET_SERVICE_JOBS_DIR="$SMOKE_TMP/jobs" \
  VCBET_SERVICE_LOGS_DIR="$SMOKE_TMP/logs" \
  VCBET_SERVICE_HOST="$SMOKE_HOST" \
  VCBET_SERVICE_PORT="$SMOKE_PORT" \
  setsid "${SERVICE_CMD[@]}" run_service.py \
    >"$SMOKE_TMP/service.log" 2>&1 &
  SERVER_PID="$!"
  STARTED_SERVER=1

  ready=0
  for _ in {1..60}; do
    if curl_ok "$BASE_URL/health" 2>/dev/null || curl_ok "$BASE_URL/" 2>/dev/null; then
      ready=1
      break
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "[ui-smoke] FAIL: service exited before becoming ready" >&2
      sed -n '1,120p' "$SMOKE_TMP/service.log" >&2 || true
      exit 1
    fi
    sleep 1
  done

  if [[ "$ready" -ne 1 ]]; then
    echo "[ui-smoke] FAIL: service did not become ready within 60s" >&2
    sed -n '1,120p' "$SMOKE_TMP/service.log" >&2 || true
    exit 1
  fi
fi

check_url "/"
check_url "/health"
check_url "/static/css/tokens.css"
check_url "/static/css/layout.css"
check_url "/static/css/components.css"
check_url "/static/css/tables.css"
check_url "/static/js/api.js"
check_url "/static/js/state.js"
check_url "/static/js/components.js"
check_url "/static/js/screens.js"
check_url "/static/js/app.js"

NODE_BIN="$(find_node || true)"
if [[ -z "$NODE_BIN" ]]; then
  echo "[ui-smoke] FAIL: node not found; JS syntax check requires node" >&2
  exit 1
fi

for js_file in \
  vcbet/service/static/js/api.js \
  vcbet/service/static/js/state.js \
  vcbet/service/static/js/components.js \
  vcbet/service/static/js/screens.js \
  vcbet/service/static/js/app.js
do
  "$NODE_BIN" --check "$js_file" >/dev/null
  echo "[ui-smoke] ok js syntax $js_file"
done

echo "[ui-smoke] PASS"
