#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
python3 "$ROOT/scripts/run_paper.py" open
python3 "$ROOT/scripts/run_live.py" open
