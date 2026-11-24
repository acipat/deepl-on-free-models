#!/usr/bin/env bash
# Developer launcher for Linux/macOS (the Windows entry point is run.bat).
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python -m deepl_ofm "$@"
