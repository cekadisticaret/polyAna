#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if pgrep -f "$ROOT/dashboard/app.py" > /dev/null; then
  exit 0
fi
echo "[$(date '+%F %T')] dashboard down → restart"
setsid "$ROOT/scripts/dashboard.sh" >> /tmp/a205_dashboard.log 2>&1 < /dev/null &
