#!/usr/bin/env python3
"""Top-30 algo katalog backtest — 1Y P&L özeti + Telegram bildirimi."""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(_DIR, "backtest_algo_catalog_1y.json")
STAKE = 10.0  # $/sinyal (PM sim: 0.50 token, kazanç ≈ stake)


def _load_env():
    env_path = os.path.join(_DIR, "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


def _pnl_row(r: dict) -> dict:
    wins = int(r["correct"])
    total = int(r["total"])
    losses = total - wins
    pnl = round((wins - losses) * STAKE, 2)
    spent = round(total * STAKE, 2)
    roi = round(pnl / spent * 100, 2) if spent else 0.0
    return {**r, "wins": wins, "losses": losses, "pnl": pnl, "spent": spent, "roi_pct": roi}


def build_report(data: dict, top_n: int = 30) -> str:
    period = f"{data.get('period_start', '?')} → {data.get('period_end', '?')}"
    syms = ", ".join(s.replace("USDT", "") for s in data.get("symbols", []))
    rows = [_pnl_row(r) for r in data.get("top", [])[:top_n]]
    total_pnl = sum(r["pnl"] for r in rows)
    profitable = sum(1 for r in rows if r["pnl"] > 0)
    sep = "━" * 28

    lines = [
        sep,
        f"📊 <b>TOP {top_n} ALGO — 1Y P&amp;L</b>",
        f"📅 {period} · {syms} · 1h",
        f"💵 Simülasyon: ${STAKE:.0f}/sinyal (PM 0.50 token)",
        f"📈 Toplam: {'+' if total_pnl >= 0 else ''}${total_pnl:,.0f} · {profitable}/{len(rows)} kârlı",
        sep,
        "",
    ]
    for i, r in enumerate(rows, 1):
        icon = "🟢" if r["pnl"] >= 0 else "🔴"
        pnl_s = f"{'+' if r['pnl'] >= 0 else ''}${r['pnl']:,.0f}"
        lines.append(
            f"{i:2d}. {icon} <b>#{r['id']}</b> {r['name'][:28]}\n"
            f"    WR {r['wr']}% · {r['wins']}W/{r['losses']}L · {pnl_s} · ROI {r['roi_pct']:+.1f}%"
        )
    lines.extend(["", sep, "<i>Her sinyal bağımsız $10 stake (sınırsız sermaye sim.)</i>"])
    return "\n".join(lines)


def tg_send(text: str) -> None:
    token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT") or os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        raise RuntimeError("TELEGRAM_TOKEN / TELEGRAM_CHAT .env içinde yok")
    chunks: list[str] = []
    if len(text) <= 4000:
        chunks = [text]
    else:
        part, buf = [], text.split("\n")
        cur = ""
        for line in buf:
            if len(cur) + len(line) + 1 > 3900:
                chunks.append(cur)
                cur = line
            else:
                cur = cur + "\n" + line if cur else line
        if cur:
            chunks.append(cur)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for i, chunk in enumerate(chunks):
        body = urllib.parse.urlencode({
            "chat_id": chat,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        req = urllib.request.Request(url, data=body)
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
        print(f"[TG] Parça {i + 1}/{len(chunks)} gönderildi")


def main():
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    send = "--send" in sys.argv or "-s" in sys.argv

    if not os.path.exists(RESULT_FILE):
        print(f"Sonuç yok: {RESULT_FILE} — önce backtest_algo_catalog.py çalıştır")
        sys.exit(1)

    with open(RESULT_FILE) as f:
        data = json.load(f)

    rows = [_pnl_row(r) for r in data.get("top", [])[:top_n]]
    for i, r in enumerate(rows, 1):
        sign = "+" if r["pnl"] >= 0 else ""
        print(f"{i:2d}. #{r['id']:2d}  WR {r['wr']:5.1f}%  P&L {sign}${r['pnl']:,.0f}  {r['name']}")

    report = build_report(data, top_n)
    out_pnl = os.path.join(_DIR, "backtest_algo_catalog_top30_pnl.json")
    with open(out_pnl, "w") as f:
        json.dump({
            "period_start": data.get("period_start"),
            "period_end": data.get("period_end"),
            "stake": STAKE,
            "top": rows,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nKaydedildi: {out_pnl}")

    if send:
        _load_env()
        tg_send(report)
    else:
        print("\n--- Telegram önizleme ---\n")
        print(report.replace("<b>", "").replace("</b>", "").replace("&amp;", "&"))


if __name__ == "__main__":
    main()
