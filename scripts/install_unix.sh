#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
  done
fi
if [[ -z "$PYTHON" ]]; then
  echo "Python 3.10+ is required." >&2
  exit 1
fi
"$PYTHON" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -r requirements.txt
if ! python -m pip install -r requirements-ai.txt; then
  echo "Core app installed. Optional AI pack failed; retry with scripts/install_ai_unix.sh." >&2
fi
echo "KaraokeSesh installation complete. Run ./run_linux.sh or ./run_macos.command"
