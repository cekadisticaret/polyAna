#!/usr/bin/env python3
"""Algoritma-islemler — açık pozisyonları kapat, bakiyeyi $1000'e sıfırla, cron open'a bırak.

Kullanım:
  python3 algo_islemler_fresh_start.py           # close + reset $1000
  python3 algo_islemler_fresh_start.py --reset-only   # sadece bakiye (close atla)
  python3 algo_islemler_fresh_start.py --reset-only --keep-open  # bakiye $1000, açık pozisyonlar kalır

Not: open çalıştırmaz — :05 / :06 cron kendi açar.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_TZ_TR = ZoneInfo("Europe/Istanbul")
_BALANCE = 1000.0

# poly_dashboard._ALGO_ISLEMLER_KEYS ile birebir aynı olmalı. Dashboard'ı buradan
# import etmek Flask'ı da çekeceği için liste elle tutuluyor; yeni defter eklerken
# --check ile tutarlılığı doğrula.
ALGO_ISLEMLER_KEYS = [
    "analiz1", "analiz2",
    "analiz6", "analiz6_v2", "analiz6_v3", "melez", "analiz15",
    "b1_01", "b1_02", "b1_mum", "b1_04", "b1_05",
    "c101", "c101_v2", "x101", "combo",
] + [f"a2_{i:02d}" for i in range(1, 18)] + ["a2_05_v2"]

# Dosya adı defter anahtarından farklı olanlar
_STATE_FILE_KEY = {"melez": "analiz6_v4"}

# Kendi `close` moduyla koşan defterler (A2 Top-17 toplu kapanıyor, ayrı)
_STANDALONE_CLOSE = [
    "analiz1", "analiz2", "analiz6", "analiz6_v2", "analiz6_v3", "analiz15",
    "b1_01", "b1_02", "b1_mum", "b1_04", "b1_05",
    "melez", "c101", "c101_v2", "x101", "combo", "a2_05_v2",
]

# Betik adı defter anahtarından farklı olanlar
_CLOSE_SCRIPT = {"melez": "poly_trader_analiz6_v4.py", "combo": "poly_trader_e01.py"}


def _state_path(key: str) -> str:
    return os.path.join(_DIR, f"poly_trader_{_STATE_FILE_KEY.get(key, key)}_state.json")


def _history_path(key: str) -> str:
    return os.path.join(_DIR, f"poly_trader_{_STATE_FILE_KEY.get(key, key)}_history.json")


def _run_close_all() -> None:
    py = sys.executable
    for key in _STANDALONE_CLOSE:
        script = os.path.join(_DIR, _CLOSE_SCRIPT.get(key, f"poly_trader_{key}.py"))
        if not os.path.isfile(script):
            print(f"[close] {key} — betik yok, atlandı ({os.path.basename(script)})")
            continue
        print(f"[close] {key} …")
        subprocess.run([py, script, "close"], cwd=_DIR, check=False)
    a2 = os.path.join(_DIR, "poly_trader_a2.py")
    if os.path.isfile(a2):
        print("[close] A2 Top-17 (batch) …")
        subprocess.run([py, a2, "close", "all"], cwd=_DIR, check=False)


def _archive_history(key: str, stamp: str) -> int:
    """Geçmişi tarihli klasöre taşı, defteri boş bırak. Silme yok, taşıma var."""
    path = _history_path(key)
    if not os.path.exists(path):
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            hist = json.load(f)
    except Exception:
        return 0
    n = len(hist) if isinstance(hist, list) else 0
    if not n:
        return 0
    arc_dir = os.path.join(_DIR, f"_archive_{stamp}")
    os.makedirs(arc_dir, exist_ok=True)
    with open(os.path.join(arc_dir, os.path.basename(path)), "w", encoding="utf-8") as f:
        json.dump(hist, f, indent=2, ensure_ascii=False)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([], f)
    return n


def _reset_balances(
    now_tr: datetime, *, wipe_history: bool = False, keep_open: bool = False,
) -> tuple[int, int, int, int]:
    reset_n = 0
    cleared_open = 0
    kept_open = 0
    archived = 0
    stamp = now_tr.strftime("%Y%m%d_%H%M")
    for key in ALGO_ISLEMLER_KEYS:
        path = _state_path(key)
        if not os.path.exists(path):
            print(f"  ATLANDI {key} — state dosyası yok ({os.path.basename(path)})")
            continue
        try:
            with open(path, encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            print(f"  ATLANDI {key} — state okunamadı")
            continue
        if wipe_history:
            archived += _archive_history(key, stamp)
        open_n = len(state.get("open_positions") or [])
        if keep_open:
            kept_open += open_n
        else:
            cleared_open += open_n
            state["open_positions"] = []
        state["balance"] = _BALANCE
        state["total_pnl"] = 0.0
        state["balance_reset_at_tr"] = now_tr.isoformat()
        note_parts = [f"algoritma-islemler toplu reset ${_BALANCE:.0f}"]
        if keep_open and open_n:
            note_parts.append(f"açık {open_n} poz korundu")
        if wipe_history:
            note_parts.append("geçmiş arşivlendi")
        else:
            note_parts.append("geçmiş korundu")
        state["balance_reset_note"] = " — ".join(note_parts)
        state.pop("defer_cleared_at_tr", None)
        state.pop("defer_note", None)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        reset_n += 1
        extra = f"  ({open_n} açık)" if keep_open and open_n else ""
        print(f"  reset {key} → ${_BALANCE:.0f}{extra}")
    return reset_n, cleared_open, archived, kept_open


def main() -> None:
    parser = argparse.ArgumentParser(description="Algoritma-islemler fresh start ($1000)")
    parser.add_argument("--reset-only", action="store_true", help="close atla, sadece bakiye sıfırla")
    parser.add_argument("--keep-open", action="store_true",
                        help="açık pozisyonları state'te bırak (--reset-only ile)")
    parser.add_argument("--wipe-history", action="store_true",
                        help="geçmişi _archive_<tarih>/ klasörüne taşıyıp defteri boşalt")
    parser.add_argument("--check", action="store_true",
                        help="hiçbir şey yazma; hangi defterin dosyası var/yok göster")
    args = parser.parse_args()

    sys.path.insert(0, _DIR)

    if args.check:
        eksik = [k for k in ALGO_ISLEMLER_KEYS if not os.path.exists(_state_path(k))]
        print(f"{len(ALGO_ISLEMLER_KEYS)} defter tanımlı, {len(eksik)} tanesinin state dosyası yok")
        for k in eksik:
            print(f"  EKSİK {k} → {os.path.basename(_state_path(k))}")
        return

    if args.keep_open and not args.reset_only:
        parser.error("--keep-open yalnızca --reset-only ile kullanılabilir (close açık pozisyonları kapatır)")

    from pm_balance_guard import clear_algo_islemler_open_after
    clear_algo_islemler_open_after(source="algo_islemler_fresh_start")

    if not args.reset_only:
        _run_close_all()
    # Damga close turundan SONRA alınır: close sırasında kapanan pozisyonların
    # exit_time'ı damgadan büyük olursa dashboard onları yeni skora sayar.
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    reset_n, cleared, archived, kept = _reset_balances(
        now_tr, wipe_history=args.wipe_history, keep_open=args.keep_open,
    )
    nxt = (now_tr.hour + 1) % 24
    arc = f"\n  Arşivlenen işlem: {archived}" if args.wipe_history else ""
    open_line = (
        f"  Korunan açık pozisyon: {kept}"
        if args.keep_open
        else f"  Kalan açık temizlendi: {cleared}"
    )
    print(
        f"\n✓ {reset_n} defter → ${_BALANCE:.0f}  |{open_line}{arc}\n"
        f"  Sonraki otomatik open: ~{nxt:02d}:05–:06 İST (cron)\n"
        f"  Manuel open çalıştırılmadı."
    )


if __name__ == "__main__":
    main()
