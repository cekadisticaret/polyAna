#!/usr/bin/env python3
"""A2#05 V2 gölge günlüğü — açılan ve z kapısına takılan slotların sonucu.

Amaç: komşu z bantlarının (ör. 1,5–1,7) cevabını **işlem açmadan** öğrenmek.
Kapıya takılan slot da kaydedildiği için eşik ileride veriden ayarlanabilir;
bunun için defteri riske atıp o bandı canlı denemek gerekmez.

    zbackfill : sonucu bilinmeyen satırları Binance 1h mumundan doldurur
    zstats    : |z| kovası bazında başabaşa göre kenar tablosu

Sonuç ölçütü: giriş saatinin 1h mumunun kapanışı, kayıtlı `entry_price`in
üstünde mi. Defterin kendi kapanışı :02'de fiyat çektiği için iki dakikalık
fark var; `zstats` bunu alınan işlemlerde defterin gerçek kaydıyla karşılaştırıp
uyum oranını basar (düşükse tablo değil yöntem sorgulanmalı).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import urllib.request
from collections import defaultdict
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_TZ_TR = ZoneInfo("Europe/Istanbul")
HOUR_MS = 3_600_000


def _read(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def _write(path: str, rows: list[dict]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _hour_ms(ts_tr: str) -> int:
    d = dt.datetime.fromisoformat(ts_tr).replace(minute=0, second=0, microsecond=0)
    return int(d.timestamp()) * 1000


def _fetch_close(symbol: str, open_ms: int) -> float | None:
    url = (f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}"
           f"&interval=1h&startTime={open_ms}&limit=1")
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.load(r)
    except Exception as e:
        print(f"[zlog] {symbol} mum hatası: {e}", file=sys.stderr)
        return None
    if not data or int(data[0][0]) != open_ms:
        return None
    return float(data[0][4])


def backfill(path: str) -> int:
    rows = _read(path)
    if not rows:
        print("[zlog] günlük boş")
        return 0
    now_ms = int(dt.datetime.now(dt.timezone.utc).timestamp()) * 1000
    filled = 0
    cache: dict[tuple[str, int], float | None] = {}
    for r in rows:
        if r.get("actual_dir") or not r.get("ts_tr") or r.get("entry_price") is None:
            continue
        h = _hour_ms(r["ts_tr"])
        if h + HOUR_MS > now_ms:      # saat henüz kapanmadı
            continue
        key = (r["symbol"], h)
        if key not in cache:
            cache[key] = _fetch_close(r["symbol"], h)
        close = cache[key]
        if close is None:
            continue
        r["exit_price"] = close
        r["actual_dir"] = "UP" if close > float(r["entry_price"]) else "DOWN"
        r["win"] = (r["actual_dir"] == r.get("direction"))
        filled += 1
    if filled:
        _write(path, rows)
    print(f"[zlog] {filled} satır dolduruldu ({len(rows)} toplam)")
    return 0


def _breakeven(r: dict) -> float:
    """Biletin ima ettiği başabaş WR — ücret dahil (fee ≈ size×0,07×p×(1−p))."""
    p = r.get("pm_price")
    if not p:
        return 0.5
    p = float(p)
    return min(0.999, p * (1 + 0.07 * (1 - p)))


def stats(path: str) -> int:
    rows = [r for r in _read(path) if r.get("win") is not None]
    if not rows:
        print("[zlog] henüz sonuçlanmış satır yok — önce zbackfill")
        return 0

    hist_path = os.path.join(_DIR, "poly_trader_a2_05_v2_history.json")
    agree = None
    if os.path.exists(hist_path):
        book = {}
        for t in json.load(open(hist_path)):
            if t.get("entry_time_tr"):
                book[(t["symbol"], t["entry_time_tr"][:13])] = t.get("win")
        m = [(r, book.get((r["symbol"], r["ts_tr"][:13]))) for r in rows if r.get("taken")]
        m = [(r, b) for r, b in m if b is not None]
        if m:
            agree = 100 * sum(1 for r, b in m if r["win"] == b) / len(m)

    print(f"gölge günlüğü: {len(rows)} sonuçlanmış slot")
    if agree is not None:
        print(f"defterle uyum (alınan işlemler): %{agree:.1f}  "
              f"— düşükse sonuç ölçütü sorgulanmalı")
    print("\n|z| kovası      n   WR%   gereken   fark      durum")
    buckets = [(0.0, 0.75), (0.75, 1.0), (1.0, 1.25), (1.25, 1.5),
               (1.5, 1.75), (1.75, 2.0), (2.0, 99.0)]
    for lo, hi in buckets:
        g = [r for r in rows if r.get("z") is not None and lo <= abs(r["z"]) < hi]
        if not g:
            continue
        wr = 100 * sum(1 for r in g if r["win"]) / len(g)
        need = 100 * sum(_breakeven(r) for r in g) / len(g)
        taken = sum(1 for r in g if r.get("taken"))
        tag = "AÇILDI" if taken == len(g) else ("atlandı" if not taken else f"{taken}/{len(g)} açıldı")
        hi_s = "  +" if hi > 90 else f"-{hi:.2f}"
        print(f"  {lo:.2f}{hi_s}  {len(g):4d}  {wr:5.1f}  {need:7.1f}  {wr - need:+6.1f}    {tag}")

    print("\nkapı içi / kapı dışı")
    for lbl, sel in (("kapı içi (açıldı)", lambda r: r.get("taken")),
                     ("kapı dışı (atlandı)", lambda r: not r.get("taken"))):
        g = [r for r in rows if sel(r)]
        if not g:
            continue
        wr = 100 * sum(1 for r in g if r["win"]) / len(g)
        need = 100 * sum(_breakeven(r) for r in g) / len(g)
        se = math.sqrt((need / 100) * (1 - need / 100) / len(g)) * 100
        print(f"  {lbl:<22} n={len(g):4d}  fark {wr - need:+6.1f} puan  t={(wr - need) / se:+5.2f}")

    by_day = defaultdict(list)
    for r in rows:
        by_day[r["ts_tr"][:10]].append(r)
    print(f"\n{len(by_day)} gün · gün başına ort {len(rows) / len(by_day):.1f} slot")
    return 0


def main(mode: str, path: str) -> int:
    return backfill(path) if mode == "zbackfill" else stats(path)


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "zstats"
    main(m, os.path.join(_DIR, "a2_05_v2_zlog.jsonl"))
