#!/usr/bin/env python3
"""USDT-M evreninde 24s en çok artan / azalan — fapi yok (spot public ticker).

  python3 AgustosKripto/Test/day_movers.py
  python3 AgustosKripto/Test/day_movers.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_DIR, "..", ".."))
_OUT = os.path.join(_DIR, "data", "day_movers.json")
_TZ = ZoneInfo("Europe/Istanbul")
_TICKER_URLS = (
    "https://data-api.binance.vision/api/v3/ticker/24hr",
    "https://api.binance.com/api/v3/ticker/24hr",
)


def _universe() -> set[str]:
    if _DIR not in sys.path:
        sys.path.insert(0, _DIR)
    from catalog import TEST_UNIVERSE  # noqa: WPS433
    return set(TEST_UNIVERSE)


def _fetch_tickers() -> list[dict]:
    last_err: Exception | None = None
    for url in _TICKER_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "aiProject/day_movers"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.load(resp)
            if isinstance(data, list) and data:
                return data
        except Exception as e:
            last_err = e
    raise RuntimeError(f"24s ticker yok: {last_err}")


def scan(*, n: int = 30) -> dict:
    allow = _universe()
    rows = []
    for t in _fetch_tickers():
        sym = str(t.get("symbol") or "").upper()
        if sym not in allow:
            continue
        try:
            pct = float(t.get("priceChangePercent") or 0)
            last = float(t.get("lastPrice") or 0)
            qv = float(t.get("quoteVolume") or 0)
        except (TypeError, ValueError):
            continue
        if last <= 0:
            continue
        rows.append({
            "symbol": sym,
            "name": sym.replace("USDT", ""),
            "pct": round(pct, 2),
            "last": last,
            "quote_vol": round(qv, 0),
        })
    up = sorted((r for r in rows if r["pct"] > 0), key=lambda x: -x["pct"])[:n]
    down = sorted((r for r in rows if r["pct"] < 0), key=lambda x: x["pct"])[:n]
    scan = []
    for r in up + down:
        sym = r["symbol"]
        if sym not in scan:
            scan.append(sym)
    return {
        "ok": True,
        "src": "spot_ticker_24hr",
        "note": "fapi kapalı — 24s rolling, evren USDT-M listesi; scan=aktif 30+30",
        "asof_tr": datetime.now(_TZ).isoformat(timespec="seconds"),
        "universe_hit": len(rows),
        "up": up,
        "down": down,
        "scan": scan,
    }


def save(data: dict) -> None:
    os.makedirs(os.path.dirname(_OUT), exist_ok=True)
    tmp = _OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _OUT)


def _fmt(rows: list[dict]) -> str:
    lines = []
    for i, r in enumerate(rows, 1):
        lines.append(
            f"{i:2d}. {r['name']:<14} {r['pct']:+7.2f}%  last {r['last']:.6g}"
        )
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=30, help="yön başına kaç coin (30+30 = 60 tarama)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    data = scan(n=args.n)
    save(data)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(f"24s hareket · evren {data['universe_hit']} · {data['asof_tr']}")
    print("\nYÜKSELEN")
    print(_fmt(data["up"]))
    print("\nDÜŞEN")
    print(_fmt(data["down"]))


if __name__ == "__main__":
    main()
