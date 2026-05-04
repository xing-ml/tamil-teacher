#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${TAMIL_PYTHON:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="${TAMIL_PYTHON_FALLBACK:-python}"
fi

"$PYTHON_BIN" "$SCRIPT_DIR/tamil_daily_lesson.py"
