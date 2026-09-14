#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=env.sh
source "$(dirname "$0")/env.sh"
exec python3 "$POLY2_ROOT/signals.py"
