#!/usr/bin/env python3
"""
run_both.py — Paper + Binance tek tarama, iki sistem
Analizi bir kez çalıştırır, aynı sonuçları her ikisine verir.
Sapma nedeni olan bağımsız veri çekme tamamen ortadan kalkar.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from crypto_futures_list import FUTURES_SYMBOLS
import paper_trader_alternatif  as paper
import binance_trader_alternatif as binance

def now_str():
    now = datetime.now(timezone.utc)
    return f"{now.strftime('%d.%m.%Y')} {(now.hour+3)%24:02d}:{now.strftime('%M')} İST"

def main():
    pairs = [s + "USDT" for s in FUTURES_SYMBOLS]

    now_utc    = datetime.now(timezone.utc)
    is_new_15m = now_utc.minute % 15 <= 4

    if is_new_15m:
        # Her iki sistemin açık pozisyonlarını da tarama setine ekle
        paper_state   = paper.load_state()
        binance_state = binance.load_state()

        paper_open   = {p["symbol"] for p in paper_state.get("open", [])}
        binance_open = set(binance_state.get("positions", {}).keys())

        scan_set = list(set(pairs) | paper_open | binance_open)

        print(f"\n🔀 run_both | {now_str()} | {len(scan_set)} coin taranıyor...")
        scan_start = datetime.now(timezone.utc)

        results = {}
        with ThreadPoolExecutor(max_workers=30) as ex:
            futures = {ex.submit(paper.analyze_confluence, sym): sym for sym in scan_set}
            for f in as_completed(futures):
                sym = futures[f]
                try:
                    results[sym] = f.result()
                except Exception:
                    results[sym] = None

        elapsed = round((datetime.now(timezone.utc) - scan_start).total_seconds(), 1)
        print(f"   ✅ Tek tarama tamamlandı: {elapsed}s ({sum(1 for v in results.values() if v)} sinyal)")
    else:
        results = None  # Yeni bar değil, tarama yapılmaz

    # Her iki sistem aynı results ile çalışır
    paper.run_scan(pairs,   precomputed_results=results)
    binance.run_scan(pairs, precomputed_results=results)


if __name__ == "__main__":
    main()
