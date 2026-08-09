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
    p.add_argument("cmd", choices=["fetch", "info"])
    p.add_argument("--days", type=int, default=90)
    args = p.parse_args()
    if args.cmd == "info":
        info()
        return
    syms = _symbols()
    print(f"{len(syms)} coin × {args.days} gün 1m indiriliyor…")
    asyncio.run(fetch_all(syms, args.days))
    print()
    info()


if __name__ == "__main__":
    main()
