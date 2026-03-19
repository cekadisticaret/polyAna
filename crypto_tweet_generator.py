#!/usr/bin/env python3
"""
Kripto Tweet İçerik Üretici
Binance 30 dakikalık değişimlere göre Al/Sat önerileri üretir.
@ZekaChain formatında görsel + metin oluşturur.
"""

import urllib.request
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from crypto_futures_list import FUTURES_SYMBOLS


def get_price_change(symbol, interval="30m"):
    """Son 2 mumu al, değişimi hesapla"""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}USDT&interval={interval}&limit=3"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        if len(data) < 2:
            return None
        open_price  = float(data[-2][1])
        close_price = float(data[-2][4])
        current     = float(data[-1][4])
        pct = round((current - open_price) / open_price * 100, 2)
        return {"symbol": symbol, "price": current, "change_pct": pct}
    except Exception:
        return None


def fetch_all_changes():
    results = []
    for sym in FUTURES_SYMBOLS:
        r = get_price_change(sym)
        if r:
            results.append(r)
    return results


if __name__ == "__main__":
    results = fetch_all_changes()
    for r in results:
        print(r)
