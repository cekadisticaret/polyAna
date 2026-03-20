#!/usr/bin/env python3
"""
Paper Trader Günlük Win Prob Raporu
Her gün 00:00 İST'de çalışır, dünün analizini Telegram'a gönderir.
Cron: 0 21 * * * (21:00 UTC = 00:00 İST)
"""

import paper_trader as pt
import paper_trader_alternatif as pa

def run():
    # Ana paper trader
    data = pt.load_trades()
    print(f"paper_trader     : {len(data.get('closed', []))} kapalı işlem")
    pt.send_win_prob_report(data)

    # Alternatif paper trader
    data_alt = pa.load_state()
    print(f"paper_trader_alt : {len(data_alt.get('closed', []))} kapalı işlem")
    pa.send_win_prob_report(data_alt)

    print("Günlük rapor tamamlandı.")

if __name__ == "__main__":
    run()
