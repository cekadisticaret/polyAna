#!/usr/bin/env bash
# Dashboard ayakta değilse yeniden başlatır (cron watchdog).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if pgrep -f "$ROOT/dashboard/app.py" > /dev/null; then
  exit 0
fi

echo "[$(date '+%F %T')] dashboard down → restart"
setsid "$ROOT/bin/dashboard.sh" >> /tmp/poly2_dashboard.log 2>&1 < /dev/null &
