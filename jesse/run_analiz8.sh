#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/python poly_analiz8_jesse.py "$@"
