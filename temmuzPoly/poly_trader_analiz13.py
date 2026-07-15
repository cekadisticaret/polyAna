"""
13. ANALİZ — Çift Konsensüs Sanal (10 + filtreler)

10. Analiz ile aynı çift konsensüs mantığı, ekstra:
  - Sistem B min skor: 2/4 (zayıf ±1/4 elenir)
  - İşlem tutarı: $10 / $15 / $20 (zayıf / orta / güçlü tier)
  - Saatlik elenme nedeni Telegram (debug)

$300 sanal başlangıç. Telegram: 10. Analiz kanalı.

Modlar: close / open / weekly / stats
Cron: 0 * * * * close | 3 * * * * open | 0 21 * * 6 weekly
"""
import asyncio
import sys

from poly_analiz_dual_core import (
    CONFIG_A13,
    analyze as _analyze,
    run_close as _run_close,
    run_open as _run_open,
    run_weekly as _run_weekly,
    run_stats as _run_stats,
)

CFG = CONFIG_A13


async def analyze(symbol: str) -> dict | None:
    return await _analyze(symbol, CFG)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "open"
    if cmd == "close":
        asyncio.run(_run_close(CFG))
    elif cmd == "open":
        asyncio.run(_run_open(CFG))
    elif cmd == "weekly":
        _run_weekly(CFG)
    elif cmd == "stats":
        _run_stats(CFG)
    else:
        print(f"Bilinmeyen mod: {cmd}")
