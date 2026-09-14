#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
exec python3 "$ROOT/src/signal_generator.py"
