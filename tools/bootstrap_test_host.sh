#!/usr/bin/env bash

# Prepare an isolated Python environment for the uNode tests on Linux.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$PROJECT_ROOT/.venv"

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$PROJECT_ROOT/requirements-test.txt"

echo
echo "Test environment ready: $VENV"
echo "Run offline tests with: tools/test.sh"
echo "Run hardware tests with: tools/test.sh --integration --rp2040-port auto"
