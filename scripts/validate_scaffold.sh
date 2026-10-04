#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PYTHON="${PYTHON:-$ROOT/apps/api/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo "Install Python 3.12+ dependencies with make install, or set PYTHON to a 3.12+ executable." >&2
  exit 1
fi
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 12), "Python 3.12+ required"'
PYTHONPYCACHEPREFIX="$ROOT/apps/api/.cache/bytecode" "$PYTHON" -m compileall -q \
  "$ROOT/apps/api/src" "$ROOT/apps/api/tests" "$ROOT/apps/api/migrations"

echo "Python source compiles."
echo "For dependency-backed validation run: make validate"
