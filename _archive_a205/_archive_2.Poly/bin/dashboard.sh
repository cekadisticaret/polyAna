#!/usr/bin/env bash
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "$0")/env.sh"
exec python3 "$POLY2_ROOT/dashboard/app.py"
