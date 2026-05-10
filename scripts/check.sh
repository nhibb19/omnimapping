#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x ".venv/bin/python" && "${PYTHON_BIN}" == "python3" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

"${PYTHON_BIN}" main.py --verify
"${PYTHON_BIN}" -m unittest discover -s tests
"${PYTHON_BIN}" dashboard.py --smoke-test
