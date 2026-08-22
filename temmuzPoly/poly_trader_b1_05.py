"""
B1#05 — coin başına en iyi motor (B1#03 MUM ve MELEZ de aday havuzunda)

Dashboard'daki "Sembol Başarı Oranı · coin başına en iyi" kartının defteri.
Kurulduğunda eşleme: BTC→A2#02 (%63,0 · 17/27) · ETH→B1#03 MUM (%63,0 · 17/27)
· SOL→A15 (%66,7 · 6/9) → birleşik %63,5 (40/63). Eşleme sabit değil, her open
turunda geçmişten yeniden hesaplanır.

B1#01 iskeletini yeniden kullanır — poly_trader_b1_01.py DOKUNULMAZ.
Ayrı state/history. Sanal defter; gerçek para emri yok.

Modlar: close / open / preview / weekly / stats
Cron: :01 close · :02:30 open (kaynak defterler :02'de açtıktan sonra)
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import poly_trader_b1_01 as base
from b1_05_signal import SYMBOLS, resolve_live_signal

_DIR = os.path.dirname(os.path.abspath(__file__))

# B1#01 modülünün kendi dosyası değişmez; yalnız bu süreçteki globalleri yönlendirilir
base.SYMBOLS = SYMBOLS
base._resolve_signal = resolve_live_signal
base.STATE_FILE = os.path.join(_DIR, "poly_trader_b1_05_state.json")
base.HISTORY_FILE = os.path.join(_DIR, "poly_trader_b1_05_history.json")
base.WEEKLY_IMG = "/tmp/poly_b1_05_weekly_heatmap.png"
base.LABEL = "B1#05"
base.BOOK_KEY = "b1_05"
base.ALGO_NAME = "Coin başına en iyi motor (MUM+MELEZ dahil)"


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
