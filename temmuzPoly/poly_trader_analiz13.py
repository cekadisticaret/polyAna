"""
13. ANALİZ — Çift Konsensüs Sanal (10 + filtreler, SOL only)

10. Analiz ile aynı çift konsensüs mantığı, ekstra:
  - Sistem B min skor: 1/4 (10. Analiz ile aynı)
  - İşlem tutarı: $10 sabit
  - Saatlik elenme nedeni Telegram (debug)

$300 sanal başlangıç. Telegram: 10. Analiz kanalı.

Modlar: close / open / weekly / stats
Cron: 0 * * * * close | 5 * * * * open | 0 21 * * 6 weekly
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
