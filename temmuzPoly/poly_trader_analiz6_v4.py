"""
A2#05 X A6V3 MELEZ — BTC: MACD Hist. Div · ETH+SOL: Mean Reversion (Z-Score)

Her sembolde uzun dönem isabet kaydının en iyisi seçildi:
  BTC → MACD Div #26      %55,0  (A6V3 ile aynı motor)
  ETH → Mean Reversion    %54,2  (A2#05 motoru; A6V3'ün RSI Div'i %53,2)
  SOL → Mean Reversion    %53,2  (A2#05 motoru)

V3 iskeletini yeniden kullanır — poly_trader_analiz6_v3.py DOKUNULMAZ.
Ayrı state/history. Sanal defter; gerçek para emri yok.

Modlar: close / open / preview / weekly / stats
Cron: :02 close · :05 open
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import poly_trader_analiz6_v3 as base
from analiz6_v4_signal import SYMBOLS, resolve_live_signal

_DIR = os.path.dirname(os.path.abspath(__file__))

# V3 modülünün kendi dosyası değişmez; yalnız bu süreçteki globalleri yönlendirilir
base.SYMBOLS = SYMBOLS
base._resolve_signal = resolve_live_signal
base.STATE_FILE = os.path.join(_DIR, "poly_trader_analiz6_v4_state.json")
base.HISTORY_FILE = os.path.join(_DIR, "poly_trader_analiz6_v4_history.json")
base.WEEKLY_IMG = "/tmp/poly_analiz6_v4_weekly_heatmap.png"
base.LABEL = "A2#05 X A6V3 MELEZ"
base.BOOK_KEY = "melez"
base.ALGO_NAME = "BTC→MACD Div · ETH/SOL→Mean Rev"


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        asyncio.run(base.run_close())
    elif mode == "preview":
        base.run_preview()
    elif mode == "weekly":
        base.run_weekly()
    elif mode == "stats":
        base.run_stats()
    else:
        asyncio.run(base.run_open())
