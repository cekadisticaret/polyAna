#!/usr/bin/env python3
"""B1#05 aday havuzunu canlı tut.

B1#05 her saat "coin başına en yüksek WR'li defteri" seçer ve bunu havuzdaki
24 defterin `poly_trader_<key>_history.json` dosyalarından hesaplar. Ana
projede o defterlerin hepsi kendi cron'uyla koşup geçmişini büyütüyor; CoptC'de
yalnız B1#03 MUM ve B1#05 koşuyor. Takipçi olmasaydı kalan 23 defterin geçmişi
kurulum gününde donar, eşleme de sabitlenirdi.

Takipçi para riske atmaz: her saat 23 motorun yönünü kaydeder (`record`), bir
sonraki saat gerçekleşen kapanışla notlandırıp geçmişe yazar (`grade`). Kayıtlar
`shadow: true` ile işaretlenir — tohum olarak gelen gerçek işlemlerden ayrılsın.

    python3 pool_tracker.py record   # :05, sinyaller üretildikten sonra
    python3 pool_tracker.py grade    # :02, saat kapandıktan sonra
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from b1_05_signal import SYMBOLS, source_keys, resolve_from_book, _HISTORY_ALIASES
from poly_predictor_analysis import _fetch_klines

_TZ_TR = ZoneInfo("Europe/Istanbul")
_PENDING = os.path.join(_DIR, "pool_pending.json")

# CoptC'de kendi trader'ıyla koşan defterler — geçmişlerini kendileri yazar,
# takipçi dokunursa aynı saat iki kez sayılır.
_SELF_MANAGED = {"b1_mum", "analiz1"}


def pool_keys() -> list[str]:
    return [k for k in source_keys() if k not in _SELF_MANAGED]


def _history_path(key: str) -> str:
    return os.path.join(_DIR, f"poly_trader_{_HISTORY_ALIASES.get(key, key)}_history.json")


def _load(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


async def record() -> None:
    """Her motorun bu saatki yönünü beklemeye al."""
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    keys = pool_keys()

    tasks = [resolve_from_book(k, s) for k in keys for s in SYMBOLS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    pending = _load(_PENDING, [])
    slot = now_tr.strftime("%Y-%m-%dT%H")
    pending = [p for p in pending if p.get("slot") != slot]  # aynı saat tekrarı

    added = 0
    for (key, sym), res in zip(((k, s) for k in keys for s in SYMBOLS), results):
        if isinstance(res, Exception) or not isinstance(res, tuple):
            continue
        direction, price, algo_name = res
        if direction not in ("UP", "DOWN") or not price:
            continue
        pending.append({
            "slot": slot,
            "book": key,
            "symbol": sym,
            "predicted_dir": direction,
            "entry_price": float(price),
            "entry_time_tr": now_tr.isoformat(),
            "entry_hour_tr": now_tr.hour,
            "entry_dow": now_tr.weekday(),
            "entry_is_weekend": now_tr.weekday() >= 5,
            "algo_name": algo_name,
        })
        added += 1

    _save(_PENDING, pending)
    print(f"[havuz record] {now_tr:%H:%M} İST — {len(keys)} defter, {added} yön kaydedildi")


async def grade() -> None:
    """Bekleyen kayıtları gerçekleşen kapanışla notla, geçmişe yaz."""
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    pending = _load(_PENDING, [])
    if not pending:
        print("[havuz grade] bekleyen kayıt yok")
        return

    slot_now = now_tr.strftime("%Y-%m-%dT%H")
    fresh, due, stale = [], [], 0
    for p in pending:
        if p.get("slot") == slot_now:
            fresh.append(p)
            continue
        # Kayıt bir sonraki saatin kapanışıyla notlanır. Sistem durup da kayıt
        # saatlerce beklerse "şimdiki" fiyatla notlamak uydurma sonuç üretir.
        try:
            age_h = (now_tr - datetime.fromisoformat(p["entry_time_tr"])).total_seconds() / 3600
        except Exception:
            age_h = 99
        if age_h <= 3:
            due.append(p)
        else:
            stale += 1

    if stale:
        print(f"[havuz grade] {stale} bayat kayıt atıldı (3 saatten eski)")
    if not due:
        _save(_PENDING, fresh)
        print("[havuz grade] bu saatin kayıtları henüz olgunlaşmadı")
        return

    prices: dict[str, float] = {}
    for sym in {p["symbol"] for p in due}:
        kl = await _fetch_klines(sym, "1h", 2)
        if kl:
            prices[sym] = float(kl[-1]["close"])

    by_book: dict[str, list[dict]] = {}
    unresolved = []
    for p in due:
        exit_price = prices.get(p["symbol"])
        if not exit_price:
            unresolved.append(p)
            continue
        actual = "UP" if exit_price >= p["entry_price"] else "DOWN"
        by_book.setdefault(p["book"], []).append({
            "symbol": p["symbol"],
            "predicted_dir": p["predicted_dir"],
            "actual_dir": actual,
            "win": p["predicted_dir"] == actual,
            "entry_price": p["entry_price"],
            "exit_price": exit_price,
            "entry_time_tr": p["entry_time_tr"],
            "entry_hour_tr": p["entry_hour_tr"],
            "entry_dow": p["entry_dow"],
            "entry_is_weekend": p["entry_is_weekend"],
            "amount": 0.0,
            "exit_time_tr": now_tr.isoformat(),
            "pnl": 0.0,
            "algo_signal": p["predicted_dir"],
            "algo_name": p.get("algo_name"),
            "shadow": True,
        })

    total = 0
    for key, recs in by_book.items():
        path = _history_path(key)
        hist = _load(path, [])
        hist.extend(recs)
        _save(path, hist)
        total += len(recs)

    keep = fresh + unresolved
    _save(_PENDING, keep)
    wins = sum(1 for r in (x for v in by_book.values() for x in v) if r["win"])
    print(f"[havuz grade] {now_tr:%H:%M} İST — {total} kayıt notlandı "
          f"({wins} isabet) · {len(by_book)} defter · bekleyen {len(keep)}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "record"
    asyncio.run(grade() if mode == "grade" else record())
