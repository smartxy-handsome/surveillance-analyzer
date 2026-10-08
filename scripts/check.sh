#!/usr/bin/env bash
# One-command verification: lint + backend tests + frontend typecheck/tests/build.
# Run from anywhere; paths are resolved relative to the repo root.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

declare -a STEPS=()
declare -a RESULTS=()

run_step() {
  local name="$1"; shift
  STEPS+=("$name")
  echo ""
  echo "==> $name"
  if "$@"; then
    RESULTS+=("PASS")
  else
    RESULTS+=("FAIL")
  fi
}

run_step "ruff (backend lint)"        uv run ruff check src/ tests/
run_step "pytest (backend tests)"     uv run pytest tests/ -q
run_step "vitest (frontend tests)"    npm --prefix frontend test
# build runs vue-tsc first, so this also covers the frontend typecheck
run_step "vite build (frontend)"      npm --prefix frontend run build

echo ""
echo "==================== summary ===================="
failed=0
for i in "${!STEPS[@]}"; do
  printf "%-30s %s\n" "${STEPS[$i]}" "${RESULTS[$i]}"
  [ "${RESULTS[$i]}" == "FAIL" ] && failed=1
done
exit $failed
