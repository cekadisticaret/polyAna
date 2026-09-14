#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
exec "${ROOT}/.venv/bin/python3" "$ROOT/dashboard/app.py"
