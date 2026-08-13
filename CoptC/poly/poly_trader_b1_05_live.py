#!/usr/bin/env python3
"""B1#05 LIVE — gerçek Polymarket $4–5–6.

Sanal B1#05 defterinin açtığı pozisyonları birebir aynalar (bağımsız sinyal
çözmez) — sanal :06'da (~3 sn) açtığı için live :06:30'da koşar.

Tek otorite **dashboard Ayarlar anahtarı** (`b1_05_live`); varsayılan kapalı.
`.env` bayrağı yalnız geriye uyumluluk yedeği, tanımlı olması gerekmez.

Uyarı: B1#05'in A2#05 slotlarındaki backfill ölçümü kenar bulamadı
(%51,6 · edge +0,6 puan · −$30,65; aynı slotlarda A2#05 %56,2 · +$178,82).
Bu yüzden kademe en düşük tutuldu ve defter kapalı başlar.

Cron: close :02 · open :06:30 (`sleep 30` — cron dakika hassasiyetinde) · :12 settle retry

Ayna tam olmalı: sanal ne açtıysa live de onu açar (`min_profit_ratio=None`).
2026-08-12 23:07 slotunda ikisi de bozulmuştu — sanal BTC'ye 0.725'ten girdi ama
live 0.77'de kâr eşiğine takılıp atladı, ETH'de ise 59 sn gecikme 0.335 yerine
0.45 ödetti. Zamanlama :06:30'a çekildi, kapı kaldırıldı.
"""
from __future__ import annotations

from poly_a2_algo_live_core import A2LiveSpec, main

SPEC = A2LiveSpec(
    algo_num=0,  # A2 ailesinden değil — dosya/etiket alanları aşağıda açıkça verildi
    algo_name="Coin başına en iyi motor",
    label="B1#05 Live",
    amount_system="b1_05",
    env_flag="PM_B1_05_LIVE_ENABLED",
    default_amount=5.0,
    book_tag="b1_05_live",
    sanal_book="b1_05",
    sanal_label="B1#05",
    # Sanal B1#05'te PM kotasyon kapısı yok; live'da olması aynayı bozuyordu.
    min_profit_ratio=None,
)

if __name__ == "__main__":
    main(SPEC)
