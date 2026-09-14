#!/usr/bin/env python3
"""1 dakikalık OHLC cache — maker fill simülasyonu için.

Yalnızca fill tespitine gereken alanlar tutulur (t/high/low/close), npz olarak
sıkıştırılır: 30 coin × 90 gün ≈ 3.9M mum, ~60 MB.

  python3 AgustosKripto/Test/minute_data.py fetch --days 90
  python3 AgustosKripto/Test/minute_data.py info
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

CACHE_DIR = os.path.join(_DIR, "data", "minute_cache")
BASE_URL = "https://fapi.binance.com/fapi/v1/klines"
MINUTE_MS = 60_000
# fapi klines limit=1000 → ağırlık 5; dakikalık bütçe 2400.
# 3 paralel × 0.4s bekleme ≈ 7.5 istek/sn ≈ 2250 ağırlık/dk (limit altı).
CONCURRENCY = 3
REQ_SLEEP = 0.4


def path_for(sym: str) -> str:
    return os.path.join(CACHE_DIR, f"{sym}_1m.npz")


def load_minutes(sym: str) -> dict | None:
    """{t, high, low, close} — t artan sıralı int64 ms."""
    p = path_for(sym)
    if not os.path.exists(p):
        return None
    d = np.load(p)
    return {"t": d["t"], "high": d["high"], "low": d["low"], "close": d["close"]}


def _symbols() -> list[str]:
    import importlib.util as ilu

    spec = ilu.spec_from_file_location("kripto_test_catalog", os.path.join(_DIR, "catalog.py"))
    mod = ilu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return list(mod.TEST_SYMBOLS)


async def _get(session, params: dict) -> list | None:
    """429/ağ hatasında üstel bekleyerek yeniden dene; pes etme."""
    import aiohttp

    for attempt in range(8):
        try:
            async with session.get(
                BASE_URL, params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                if r.status in (418, 429):
                    wait = float(r.headers.get("Retry-After") or 0) or min(60, 3 * 2 ** attempt)
                    await asyncio.sleep(wait)
                    continue
                if r.status >= 500:
                    await asyncio.sleep(min(30, 2 ** attempt))
                    continue
                data = await r.json()
            return data if isinstance(data, list) else None
        except Exception:
            await asyncio.sleep(min(30, 2 ** attempt))
    return None


async def _fetch_symbol(session, sym: str, start_ms: int, end_ms: int) -> int:
    ts: list[int] = []
    hi: list[float] = []
    lo: list[float] = []
    cl: list[float] = []

    prev = load_minutes(sym)
    if prev is not None and len(prev["t"]) and int(prev["t"][0]) <= start_ms + MINUTE_MS:
        # Mevcut cache'i koru, yalnızca eksik kuyruğu tamamla
        ts = prev["t"].tolist()
        hi = prev["high"].tolist()
        lo = prev["low"].tolist()
        cl = prev["close"].tolist()
        cur = int(prev["t"][-1]) + 1
    else:
        cur = start_ms

    while cur < end_ms:
        data = await _get(session, {
            "symbol": sym, "interval": "1m",
            "startTime": cur, "endTime": end_ms, "limit": 1000,
        })
        if data is None or not data:
            break
        for k in data:
            ts.append(int(k[0]))
            hi.append(float(k[2]))
            lo.append(float(k[3]))
            cl.append(float(k[4]))
        last = int(data[-1][0])
        if last + 1 <= cur:
            break
        cur = last + 1
        await asyncio.sleep(REQ_SLEEP)

    if not ts:
        return 0
    t = np.array(ts, dtype=np.int64)
    order = np.argsort(t, kind="stable")
    t = t[order]
    uniq = np.concatenate(([True], np.diff(t) > 0))
    os.makedirs(CACHE_DIR, exist_ok=True)
    np.savez_compressed(
        path_for(sym),
        t=t[uniq],
        high=np.array(hi, dtype=np.float32)[order][uniq],
        low=np.array(lo, dtype=np.float32)[order][uniq],
        close=np.array(cl, dtype=np.float32)[order][uniq],
    )
    return int(uniq.sum())


async def fetch_all(symbols: list[str], days: int) -> None:
    import aiohttp

    end_ms = int(time.time() * 1000) // MINUTE_MS * MINUTE_MS
    start_ms = end_ms - days * 24 * 60 * MINUTE_MS
    sem = asyncio.Semaphore(CONCURRENCY)
    done = 0
    t0 = time.time()

    async with aiohttp.ClientSession() as session:
        async def one(sym: str):
            nonlocal done
            async with sem:
                n = await _fetch_symbol(session, sym, start_ms, end_ms)
            done += 1
            print(f"  [{done:2}/{len(symbols)}] {sym:12} {n:7,} mum  ({time.time()-t0:.0f}s)", flush=True)

        await asyncio.gather(*(one(s) for s in symbols))


VISION_DAILY = (
    "https://data.binance.vision/data/futures/um/daily/klines/"
    "{sym}/1m/{sym}-1m-{day}.zip"
)


def _merge_npz(sym: str, ts, hi, lo, cl) -> int:
    """Var olan cache ile birleştir, sırala, tekilleştir."""
    if not ts:
        prev = load_minutes(sym)
        return 0 if prev is None else int(len(prev["t"]))
    t = np.asarray(ts, dtype=np.int64)
    h = np.asarray(hi, dtype=np.float32)
    l = np.asarray(lo, dtype=np.float32)
    c = np.asarray(cl, dtype=np.float32)
    prev = load_minutes(sym)
    if prev is not None and len(prev["t"]):
        t = np.concatenate([prev["t"], t])
        h = np.concatenate([prev["high"], h])
        l = np.concatenate([prev["low"], l])
        c = np.concatenate([prev["close"], c])
    order = np.argsort(t, kind="stable")
    t, h, l, c = t[order], h[order], l[order], c[order]
    uniq = np.concatenate(([True], np.diff(t) > 0))
    os.makedirs(CACHE_DIR, exist_ok=True)
    np.savez_compressed(path_for(sym), t=t[uniq], high=h[uniq], low=l[uniq], close=c[uniq])
    return int(uniq.sum())


def fetch_vision_days(symbols: list[str], days: int, end_date: str | None = None) -> None:
    """data.binance.vision günlük zip — fapi yok.

    Cache'in kuyruğunu (ve istenirse geçmişi) tamamlar. 30 coin × 10 gün
    birkaç dakikadır; 90 gün ~1000 zip, ağ + disk.
    """
    import csv
    import io
    import urllib.request
    import zipfile
    from datetime import datetime, timedelta, timezone

    end = datetime.now(timezone.utc).date()
    if end_date:
        end = datetime.fromisoformat(end_date).date()
    start = end - timedelta(days=days - 1)
    print(f"vision {len(symbols)} coin × {days} gün  {start} → {end}", flush=True)

    day = start
    fetched = missed = 0
    t0 = time.time()
    while day <= end:
        ds = day.isoformat()
        for i, sym in enumerate(symbols, 1):
            url = VISION_DAILY.format(sym=sym, day=ds)
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    raw = resp.read()
            except Exception:
                missed += 1
                continue
            ts, hi, lo, cl = [], [], [], []
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    name = zf.namelist()[0]
                    with zf.open(name) as fh:
                        text = io.TextIOWrapper(fh, encoding="utf-8")
                        for row in csv.reader(text):
                            if not row or not row[0].isdigit():
                                continue
                            ts.append(int(row[0]))
                            hi.append(float(row[2]))
                            lo.append(float(row[3]))
                            cl.append(float(row[4]))
            except Exception:
                missed += 1
                continue
            _merge_npz(sym, ts, hi, lo, cl)
            fetched += 1
        print(f"  {ds}  zip={fetched}  eksik={missed}  ({time.time()-t0:.0f}s)", flush=True)
        day += timedelta(days=1)
    print(f"bitti {fetched} zip · {missed} atlandı · {time.time()-t0:.0f}s")


def info() -> None:
    if not os.path.isdir(CACHE_DIR):
        print("cache yok")
        return
    tot = 0
    mb = 0.0
    for f in sorted(os.listdir(CACHE_DIR)):
        if not f.endswith(".npz"):
            continue
        p = os.path.join(CACHE_DIR, f)
        d = np.load(p)
        n = len(d["t"])
        tot += n
        mb += os.path.getsize(p) / 1e6
        span = (int(d["t"][-1]) - int(d["t"][0])) / (24 * 3600_000)
        print(f"  {f[:-8]:12} {n:8,} mum · {span:.1f} gün")
    print(f"\ntoplam {tot:,} mum · {mb:.0f} MB")


def main() -> None:
    p = argparse.ArgumentParser(description="1m OHLC cache")
    p.add_argument("cmd", choices=["fetch", "fetch_vision", "info"])
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--end", default=None, help="YYYY-MM-DD (UTC, vision)")
    args = p.parse_args()
    if args.cmd == "info":
        info()
        return
    syms = _symbols()
    if args.cmd == "fetch_vision":
        fetch_vision_days(syms, args.days, args.end)
        print()
        info()
        return
    print(f"{len(syms)} coin × {args.days} gün 1m indiriliyor (fapi)…")
    asyncio.run(fetch_all(syms, args.days))
    print()
    info()


if __name__ == "__main__":
    main()
