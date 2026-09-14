#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
python3 "$ROOT/scripts/run_paper.py" close || true
python3 "$ROOT/scripts/run_live.py" close
python3 "$ROOT/scripts/run_redeem.py" || true
