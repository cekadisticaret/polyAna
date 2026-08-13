#!/usr/bin/env python3
"""B1#03 MUM LIVE — gerçek Polymarket.

Sanal B1#03 MUM defterinin açtığı pozisyonları birebir aynalar (bağımsız sinyal
çözmez) — sanal :05'te açtığı için live :06'da koşar (~10 sn buffer).

Tek otorite **dashboard Ayarlar anahtarı** (`b1_mum_live`); varsayılan kapalı.
İşlem miktarları `/ayarlar` → İşlem Miktarları → B1#03 MUM Live (düş/orta/yük WR).

Cron: close :02 · open :06 (sanal :05 state yazıldıktan sonra) · :12 settle retry
"""
from __future__ import annotations

from poly_a2_algo_live_core import A2LiveSpec, main

SPEC = A2LiveSpec(
    algo_num=0,
    algo_name="Sonnet mum confluence (1h · ±15 eşik)",
    label="B1#03 MUM Live",
    amount_system="b1_mum",
    env_flag="PM_B1_MUM_LIVE_ENABLED",
    default_amount=8.0,
    book_tag="b1_mum_live",
    sanal_book="b1_mum",
    sanal_label="B1#03 MUM ANALİZ",
)

if __name__ == "__main__":
    main(SPEC)
