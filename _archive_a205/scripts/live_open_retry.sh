#!/usr/bin/env bash
# :05:10 TR — paper'da var, live'da eksik semboller için tekrar aç
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$(dirname "$0")/env.sh"

pending=$(python3 - "$ROOT" <<'PY'
import json, sys
from datetime import datetime
from zoneinfo import ZoneInfo

root = sys.argv[1]
now = datetime.now(ZoneInfo("Europe/Istanbul"))
hour = now.hour

try:
    with open(f"{root}/data/paper_state.json", encoding="utf-8") as f:
        paper = json.load(f)
except FileNotFoundError:
    paper = {"open_positions": []}

try:
    with open(f"{root}/data/live_state.json", encoding="utf-8") as f:
        live = json.load(f)
except FileNotFoundError:
    live = {"open_positions": []}

paper_syms = {
    p.get("symbol")
    for p in paper.get("open_positions") or []
    if p.get("entry_hour_tr") == hour
}
live_syms = {
    p.get("symbol")
    for p in live.get("open_positions") or []
    if p.get("entry_hour_tr") == hour
}
print(len(paper_syms - live_syms))
PY
)

if [ "$pending" -eq 0 ]; then
  exit 0
fi

echo "[$(date '+%F %T')] retry open — $pending eksik pozisyon"
# Yalnız live tarafı — paper open tekrar çalışırsa mükerrer kayıt oluşur
exec python3 "$ROOT/scripts/run_live.py" open
