#!/usr/bin/env python3
"""A2#05 V2 — aynı sinyal, sinyalin kendi güven derecesiyle süzülmüş.

A2#05'in kendisi (`poly_trader_a2.py`, algo #5) **hiç değişmedi**; sinyal
fonksiyonu `algo_signals.mean_reversion` aylardır byte byte aynı. Bu defter
onun bir kopyası değil, aynı sinyali **tek bir ek kuralla** koşturan ayrı bir
defter: yalnız **1,0 ≤ |z| < 1,5** iken işlem aç.

Neden z, neden fiyat değil
──────────────────────────
`mean_reversion` z-skorunu hesaplıyor, eşiği geçince "UP"/"DOWN" diyor ve
**büyüklüğü çöpe atıyor** — z=−0,6 ile z=−3,0 aynı sinyali, aynı kademeyi
üretiyor. Bu bilgi hiç ölçülmemişti. 341 işlemin giriş anındaki z'si yeniden
kuruldu (%99,1 yön tutarlılığı) ve temiz tek tepeli bir eğri çıktı:

    |z|            n    başabaşa fark    net
    0,50 – 0,75   54         +0,9      +  6,51
    0,75 – 1,00   73         +5,6      +102,79
    1,00 – 1,25   58        +17,1      +434,91
    1,25 – 1,50   43        +20,9      +302,85
    1,50 – 1,75   32        +10,2      +108,12
    1,75 – 2,00   19         −2,1      −  3,13
    2,00 +        26         +2,1      + 21,22

Mekanizma: 1,0 altında ortalamadan sapma yok, dönecek bir şey yok; 1,5 üstünde
hareket artık gürültü değil **trend**, yani mean reversion trende karşı durup
kaybediyor. Kodun kendi eşikleri (0,5 ve 1,5) ">1,5"i en güçlü kademe sayıyor —
kenarın öldüğü yer tam orası.

Bu kural, V2'nin 16.08'e kadar taşıdığı **fiyat bandı kuralının yerine** geçti.
O kural dört sınavın hiçbirini geçemedi; bu dördünü de geçiyor:

  · Sınır hassasiyeti yok — 20 alt/üst kombinasyonu +11,6 ile +18,7 arasında.
  · Üç coinde birden — BTC +16,2 · ETH +26,6 · SOL +13,9 (bant dışında ~0).
  · Walk-forward — ilk yarı +16,3, ikinci yarı +20,9 puan.
  · Gün kümelenmesi — t_gün +3,24 (fiyat bandı 0,40–0,50 yalnız +1,28'e düşüyordu).

Fiyattan bağımsız: her z kovasının ortalama bileti ~0,50.

**Örneklem küçük:** 341 işlem / 9 gün, gün bazında n=8. Dört kova denendiği için
Bonferroni eşiği t≈3,5, ölçülen 3,24 — "güçlü işaret", "kanıtlanmış" değil.
Defterin varlık sebebi kuralı ileriye dönük veriyle sınamak.

Gölge günlüğü
─────────────
`a2_05_v2_zlog.jsonl` — açılan **ve** z kapısına takılan her slot yazılır;
`zbackfill` modu sonucu Binance mumundan doldurur. Böylece 1,5–1,7 gibi
komşu bantların cevabı kasa riske girmeden, işlem açmadan gelir.

Güvenlik: `live_mirror=False`. `algo_num=5` sinyali okumak için gerekli ama
o numara gerçek para aynasına (`poly_trader_a2_05_live`) bağlı; bu defter
onu **hiçbir koşulda** tetiklemez.

Cron: :02 close · :05 open · :25 zbackfill · Cmt 21:00 weekly
"""
from __future__ import annotations

import asyncio
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from poly_a2_algo_trader_core import A2Config, run_mode  # noqa: E402

ALGO_NUM = 5
BOOK_KEY = "a2_05_v2"
Z_LO = float(os.environ.get("A2_05_V2_Z_LO") or 1.0)
Z_HI = float(os.environ.get("A2_05_V2_Z_HI") or 1.5)
ZLOG = os.path.join(_DIR, "a2_05_v2_zlog.jsonl")

CONFIG = A2Config(
    algo_num=ALGO_NUM,
    key=BOOK_KEY,
    label="A2#05 V2 Mean Reversion (z kapısı)",
    algo_name="Mean Reversion (Z-Score) · yalnız 1,0 ≤ |z| < 1,5",
    state_file=os.path.join(_DIR, f"poly_trader_{BOOK_KEY}_state.json"),
    history_file=os.path.join(_DIR, f"poly_trader_{BOOK_KEY}_history.json"),
    z_gate=(Z_LO, Z_HI),
    shadow_log=ZLOG,
    live_mirror=False,
)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode in ("zbackfill", "zstats"):
        from a2_05_v2_zlog import main as zlog_main
        raise SystemExit(zlog_main(mode, ZLOG))
    asyncio.run(run_mode(mode, [CONFIG]))
