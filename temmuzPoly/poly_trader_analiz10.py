"""
10. ANALİZ — Çift Konsensüs Sanal

Sistem A: poly_predictor (Analiz 1/5)
Sistem B: Trend + MR + OrderFlow + Funding (Analiz 4/9)

$300 sanal, işlem $12/$16/$20 (sembol WR — 1. Analiz mantığı). Saatlik elenme nedeni Telegram.

Modlar: close / open / weekly / stats
Cron: 0 * * * * close | 5 * * * * open | 0 21 * * 6 weekly
"""
import asyncio
import sys

from poly_analiz_dual_core import (
    CONFIG_A10,
    analyze as _analyze,
    run_close as _run_close,
    run_open as _run_open,
    run_weekly as _run_weekly,
    run_stats as _run_stats,
)

CFG = CONFIG_A10


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
