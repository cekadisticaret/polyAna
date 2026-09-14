#!/usr/bin/env bash
# Aktarım sonrası botu geri aç: cron'ları etkinleştir + Live anahtarını kaldır.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! crontab -l 2>/dev/null | grep -q '^#PAUSED# '; then
  echo "cron zaten aktif (duraklatılmış satır yok)"
else
  crontab -l 2>/dev/null | sed -E 's|^#PAUSED# ||' | crontab -
  echo "cron satırları geri açıldı"
fi

"${ROOT}/.venv/bin/python3" - <<'PY'
import sys
sys.path.insert(0, "/root/aiProject/src")
from bootstrap import init
init()
from balance_guard import set_group_paused, is_group_paused
set_group_paused("a2_05_live", False, source="bot_resume")
print("a2_05_live paused :", is_group_paused("a2_05_live"))
PY

echo
echo "aktif cron:"
crontab -l | grep -E 'aiProject/scripts' || echo "  (yok)"
