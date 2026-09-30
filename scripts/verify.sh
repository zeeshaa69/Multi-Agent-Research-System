#!/usr/bin/env bash
# Runs every quality gate. Exits non-zero on the first failure.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"

echo "== ruff (lint) =="; $PY -m ruff check src tests
echo "== ruff (format check) =="; $PY -m ruff format --check src tests
echo "== mypy (types) =="; $PY -m mypy
echo "== pytest =="; $PY -m pytest -q
echo "== offline end-to-end (CLI) =="
out="$($PY -m researcher.cli run "What are the costs, risks and environmental effects of the Harborview Tidal Pilot?" --offline)"
for label in "[Source-supported]" "[Uncertain]" "[Conflicting]" "[Generated synthesis]"; do
  grep -qF "$label" <<<"$out" || { echo "missing $label in offline report"; exit 1; }
done
echo "offline report contains all four statement labels"
echo "== frontend =="
(cd frontend && npm ci --silent && npm run lint && npm run typecheck && npm run build)
echo "ALL CHECKS PASSED"
