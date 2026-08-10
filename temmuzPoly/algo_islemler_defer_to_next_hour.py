#!/usr/bin/env python3
"""Algoritma-islemler tüm sanal defterler: açık pozisyonları iptal + bir sonraki saate open ertele.

Kullanım:
  python3 algo_islemler_defer_to_next_hour.py          # sonraki saat başı
  python3 algo_islemler_defer_to_next_hour.py clear    # ertelemeyi kaldır
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_TZ_TR = ZoneInfo("Europe/Istanbul")

ALGO_ISLEMLER_KEYS = [
    "analiz1", "analiz2",
    "analiz6", "analiz6_v2", "analiz6_v3", "analiz15",
    "b1_01", "b1_02", "b1_mum",
] + [f"a2_{i:02d}" for i in range(1, 18)]


def _state_path(key: str) -> str:
    return os.path.join(_DIR, f"poly_trader_{key}_state.json")


def _next_hour_start(now_tr: datetime) -> datetime:
    base = now_tr.replace(minute=0, second=0, microsecond=0)
    if now_tr.minute == 0 and now_tr.second == 0:
        return base + timedelta(hours=1)
    return base + timedelta(hours=1)


def defer_all() -> None:
    sys.path.insert(0, _DIR)
    from pm_balance_guard import set_algo_islemler_open_after

    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    start_tr = _next_hour_start(now_tr)
    set_algo_islemler_open_after(start_tr, source="algo_islemler_defer_to_next_hour")

    cleared_books = 0
    cleared_pos = 0
    for key in ALGO_ISLEMLER_KEYS:
        path = _state_path(key)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            continue
        open_pos = state.get("open_positions") or []
        if not open_pos:
            continue
        n = len(open_pos)
        state["open_positions"] = []
        state["defer_cleared_at_tr"] = now_tr.isoformat()
        state["defer_note"] = f"open {start_tr.strftime('%H:%M')} İST sonrası — {n} poz iptal"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        cleared_books += 1
        cleared_pos += n
        print(f"  {key}: {n} açık pozisyon iptal")

    print(
        f"✓ Algoritma-islemler open → {start_tr.strftime('%d.%m.%Y %H:%M')} İST sonrası\n"
        f"  İptal edilen defter: {cleared_books}  |  pozisyon: {cleared_pos}"
    )


def clear_defer() -> None:
    sys.path.insert(0, _DIR)
    from pm_balance_guard import clear_algo_islemler_open_after
    clear_algo_islemler_open_after(source="algo_islemler_defer_to_next_hour")
    print("✓ Algoritma-islemler open ertelemesi kaldırıldı")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        clear_defer()
    else:
        defer_all()
