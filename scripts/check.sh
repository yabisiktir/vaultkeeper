#!/usr/bin/env bash
# Everything CI checks, in the order it checks it (see .github/workflows/build.yml
# — the `test` job). Run before you push.
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"

RUFF=$([ -x .venv/bin/ruff ] && echo .venv/bin/ruff || echo ruff)
PY=$([ -x .venv/bin/python ] && echo .venv/bin/python || echo python)

# The suite is Qt; CI runs it headless and so do we, or GUI tests pop windows.
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"

echo "== the bundled 7-Zip is committed, not fetched =="
"$PY" scripts/fetch_tools.py --check

echo "== pytest =="
"$PY" -m pytest -q

echo "== ruff check src tests scripts docs =="
"$RUFF" check src tests scripts docs

echo "== all checks passed =="
