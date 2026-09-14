#!/usr/bin/env bash
# Slotu bitmiş ama PM'de henüz sonuçlanmamış pozisyonlar için tekrar kapatma denemesi.
# Saatlik :02 kapanışında market resolve olmamışsa pozisyon bir sonraki saate sarkmasın.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

pending=$(python3 - "$ROOT" <<'PY'
import json, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

root = sys.argv[1]
try:
    with open(f"{root}/data/poly_trader_a2_05_live_state.json", encoding="utf-8") as f:
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
  # Sarkan pozisyon yok ama redeem bekleyen kazanç olabilir
  exec "$ROOT/bin/redeem.sh"
fi

echo "[$(date '+%F %T')] retry close — $pending sarkan pozisyon"
exec "$ROOT/bin/live_close.sh"
