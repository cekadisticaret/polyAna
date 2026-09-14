#!/usr/bin/env bash
# :05:10 TR — ilk açılışta başarısız kalan semboller için tekrar dene.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

pending=$(python3 - "$ROOT" <<'PY'
import json, sys
from datetime import datetime
from zoneinfo import ZoneInfo

root = sys.argv[1]
now = datetime.now(ZoneInfo("Europe/Istanbul"))
hour = now.hour

try:
    with open(f"{root}/data/algo_signals_v2.json", encoding="utf-8") as f:
        sig = (json.load(f).get("signals") or {}).get("5") or {}
except FileNotFoundError:
    print(0)
    raise SystemExit

try:
    with open(f"{root}/data/poly_trader_a2_05_live_state.json", encoding="utf-8") as f:
        state = json.load(f)
except FileNotFoundError:
    state = {"open_positions": []}

open_syms = {
    p.get("symbol")
    for p in state.get("open_positions") or []
    if p.get("entry_hour_tr") == hour
}
need = 0
for sym, short in [("BTCUSDT", "BTC"), ("ETHUSDT", "ETH"), ("SOLUSDT", "SOL")]:
    direction = (sig.get(short) or "").upper()
    if direction in ("UP", "DOWN") and sym not in open_syms:
        need += 1
print(need)
PY
)

if [ "$pending" -eq 0 ]; then
  exit 0
fi

echo "[$(date '+%F %T')] retry open — $pending eksik pozisyon"
exec "$ROOT/bin/live_open.sh"
