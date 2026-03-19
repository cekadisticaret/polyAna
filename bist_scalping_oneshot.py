#!/usr/bin/env python3
"""
Tek sefer: 427 hisse 15m AL taraması (seans filtresi YOK), en fazla 10 tanesine Telegram.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from bist_scanner import BIST_TICKERS
from bist_scalping_alerts import analyze_ticker, tg_send

TOP_N = 10


def main():
    found = []
    with ThreadPoolExecutor(max_workers=30) as ex:
        fut = {ex.submit(analyze_ticker, t, True): t for t in BIST_TICKERS}
        for f in as_completed(fut):
            try:
                r = f.result()
                if r and r.get("long_entry"):
                    found.append(r)
            except Exception:
                pass

    found.sort(key=lambda x: (-x.get("long_score", 0), -x.get("real_rr", 0)))
    top = found[:TOP_N]

    if not top:
        tg_send(
            "<b>BIST 15m tek seferlik tarama</b>\n"
            "AL koşullarını (min conf, R:R, EMA cross vb.) sağlayan hisse bulunamadı."
        )
        print("AL yok.")
        return

    lines = [
        f"<b>BIST 15m — tek seferlik tarama</b> ({len(found)} AL, ilk {len(top)})\n",
        "<i>Not: Seans filtresi kapalı; canlı bot kurallarından farklı olabilir.</i>\n",
    ]
    for r in top:
        t = r["ticker"]
        lines.append(
            f"• <b>{t}</b> → {r['entry']} ₺ | TP1 {r['tp1']} | Skor {r['long_score']}/6 | R:R {r['real_rr']}"
        )
    if len(found) > TOP_N:
        lines.append(f"\n… ve {len(found) - TOP_N} hisse daha (listede kesildi).")

    tg_send("\n".join(lines))
    print(f"Gönderildi: {len(top)} / toplam AL {len(found)}")


if __name__ == "__main__":
    main()
