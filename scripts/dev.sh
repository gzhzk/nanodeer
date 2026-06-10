#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/demo/frontend"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
BACKEND_HOST="127.0.0.1"
BACKEND_PORT="20266"
FRONTEND_PORT="20265"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}"

WITH_FRONTEND=false
PIDS=()

log() {
  printf '[nanodeer-dev] %s\n' "$*"
}

die() {
  printf '[nanodeer-dev] error: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  local pid
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}

trap cleanup EXIT INT TERM

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command '$1'"
}

http_ready() {
  local url="$1"
  curl --noproxy '*' -fsS --max-time 1 "$url" >/dev/null 2>&1
}

wait_for_http() {
  local url="$1"
  local name="$2"
  local pid="${3:-}"
  local i
  for i in {1..40}; do
    if http_ready "$url"; then
      return 0
    fi
    if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
      die "${name} exited before becoming ready at ${url}"
    fi
    sleep 0.5
  done
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    log "warning: ${name} process is running, but ${url} did not answer readiness checks"
    return 0
  fi
  die "${name} did not become ready at ${url}"
}

check_prerequisites() {
  require_cmd bash
  require_cmd curl

  [[ -x "$PYTHON_BIN" ]] || die "project Python not found at ${PYTHON_BIN}. Create it and install the package first."
  [[ -f "$ROOT_DIR/config.yaml" ]] || die "config.yaml missing. Copy config.yaml.example and configure provider/API key."

  if "$WITH_FRONTEND"; then
    [[ -d "$FRONTEND_DIR/node_modules" ]] || die "frontend dependencies missing. Run: cd demo/frontend && npm install"
  fi

  if [[ ! -f "$ROOT_DIR/.env" ]]; then
    log "warning: .env not found. Provider API keys must be available from the shell environment."
  fi

  if command -v docker >/dev/null 2>&1 && ! docker info >/dev/null 2>&1; then
    log "warning: Docker is not reachable. Tool sandbox startup may fail."
  fi
}

start_backend() {
  if http_ready "${BACKEND_URL}/health"; then
    log "backend already listening at ${BACKEND_URL}"
    return
  fi

  log "starting backend at ${BACKEND_URL}"
  (
    cd "$ROOT_DIR"
    exec "$PYTHON_BIN" -m nanodeer.cli.api
  ) &
  local pid="$!"
  PIDS+=("$pid")
  wait_for_http "${BACKEND_URL}/health" "backend" "$pid"
}

start_frontend() {
  if http_ready "$FRONTEND_URL"; then
    log "frontend already listening at ${FRONTEND_URL}"
    return
  fi

  log "starting demo frontend at ${FRONTEND_URL}"
  (
    cd "$FRONTEND_DIR"
    exec ./node_modules/.bin/next dev --turbopack -H 127.0.0.1 -p "$FRONTEND_PORT"
  ) &
  local pid="$!"
  PIDS+=("$pid")
  wait_for_http "$FRONTEND_URL" "frontend" "$pid"
}

main() {
  for arg in "$@"; do
    case "$arg" in
      --with-frontend) WITH_FRONTEND=true ;;
    esac
  done

  check_prerequisites
  start_backend

  if "$WITH_FRONTEND"; then
    start_frontend
    log "frontend (demo): ${FRONTEND_URL}"
  fi

  log "ready"
  log "backend: ${BACKEND_URL}"
  log "press Ctrl-C to stop"

  wait
}

main "$@"
