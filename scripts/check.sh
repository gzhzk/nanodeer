#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

PYTHON_BIN="${PYTHON_BIN:-}"
RUN_FRONTEND="${RUN_FRONTEND:-1}"

log() {
  printf '[nanodeer-check] %s\n' "$*"
}

die() {
  printf '[nanodeer-check] error: %s\n' "$*" >&2
  exit 1
}

find_python() {
  if [[ -n "$PYTHON_BIN" ]]; then
    [[ -x "$PYTHON_BIN" || "$(command -v "$PYTHON_BIN" 2>/dev/null)" ]] || die "PYTHON_BIN is not executable: $PYTHON_BIN"
    return
  fi

  local candidate
  for candidate in "$ROOT_DIR/.venv/bin/python" python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      return
    fi
  done

  die "Python not found. Create a venv, then install dev deps: pip install -e '.[dev]'"
}

require_python_deps() {
  "$PYTHON_BIN" - <<'PY' || die "pytest is missing. Install dev deps: $PYTHON_BIN -m pip install -e '.[dev]'"
import pytest  # noqa: F401
import pytest_asyncio  # noqa: F401
PY
}

run_python_tests() {
  log "running Python tests"
  "$PYTHON_BIN" -m pytest "$@"
}

run_frontend_lint() {
  [[ "$RUN_FRONTEND" == "1" ]] || return 0

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    log "skipping frontend lint: frontend/node_modules missing. Run: cd frontend && npm install"
    return 0
  fi

  log "running frontend lint"
  (cd "$FRONTEND_DIR" && npm run lint)
}

main() {
  cd "$ROOT_DIR"

  find_python
  log "using Python: $PYTHON_BIN"
  require_python_deps

  if [[ "$#" -gt 0 ]]; then
    run_python_tests "$@"
  else
    run_python_tests tests
  fi

  run_frontend_lint
  log "check complete"
}

main "$@"
