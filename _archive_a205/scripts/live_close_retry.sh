#!/usr/bin/env bash
# Slotu bitmiş ama PM'de henüz sonuçlanmamış pozisyonlar için tekrar kapatma.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$(dirname "$0")/env.sh"

pending=$(python3 - "$ROOT" <<'PY'
import json, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

root = sys.argv[1]
try:
    with open(f"{root}/data/live_state.json", encoding="utf-8") as f:
        state = json.load(f)
except FileNotFoundError:
    print(0)
    raise SystemExit

now = datetime.now(ZoneInfo("Europe/Istanbul"))
stale = 0
for pos in state.get("open_positions", []):
    raw = pos.get("entry_time_tr")
    if not raw:
        continue
    entry = datetime.fromisoformat(raw)
    slot_end = entry.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    if now >= slot_end + timedelta(minutes=3):
        stale += 1
print(stale)
PY
)

if [ "$pending" -eq 0 ]; then
  exec "$ROOT/scripts/run_redeem.py" || true
fi

echo "[$(date '+%F %T')] retry close — $pending sarkan pozisyon"
exec "$ROOT/scripts/live_close.sh"
