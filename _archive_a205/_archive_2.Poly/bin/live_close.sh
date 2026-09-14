#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=env.sh
source "$(dirname "$0")/env.sh"
python3 "$POLY2_ROOT/run_live.py" close
# Kazananları hemen nakde çevir — para bir sonraki açılışta kullanılabilsin
python3 "$POLY2_ROOT/run_redeem.py" || true
