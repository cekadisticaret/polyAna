#!/usr/bin/env python3
"""A2#05 V2 — aynı sinyal, diğer sunucuda ölçülen fiyat tabanıyla.

A2#05'in kendisi (`poly_trader_a2.py`, algo #5) **hiç değişmedi**; sinyal
fonksiyonu `algo_signals.mean_reversion` aylardır byte byte aynı. Bu defter
onun bir kopyası değil, aynı sinyali **tek bir ek kuralla** koşturan ayrı bir
defter: **0,40'ın altındaki bileti alma.**

Kural nereden geldi: kopyalama sunucusunun (209.38.120.96) 38 kapalı işlemi
giriş fiyatına göre gruplandığında zararın tamamı ucuz biletlerden çıktı.

    fiyat aralığı   işlem  isabet  gereken   net
    0,00 – 0,40      11      %9      %33    −20,30
    0,40 – 0,55      12     %67      %49    +10,65
    0,55 – 0,70      12     %75      %63     +7,40
    0,70 – 1,00       3     %67      %76     −1,40

Nedensel okuma: bilet ucuzsa, sinyal üretildikten sonra fiyat sert düşmüş
demektir — piyasa tahmini çoktan yanlışlamıştır. Taban konsaydı net −3,65
yerine +16,65 olurdu. **Örneklem 38 işlem, küçük**; bu defter tam da bu yüzden
var: kuralın gerçekten kenar mı yoksa geriye dönük uydurma mı olduğunu ileriye
dönük veriyle ölçeceğiz.

Üst taraf için ayrı kural yok — A2#05'teki mevcut kâr kapısı (net kazanç ≥
bahsin yarısı) zaten 0,667 üstünü eliyor, 0,75 tavanı ölü kural olurdu.

Güvenlik: `live_mirror=False`. `algo_num=5` sinyali okumak için gerekli ama
o numara gerçek para aynasına (`poly_trader_a2_05_live`) bağlı; bu defter
onu **hiçbir koşulda** tetiklemez.

Cron: :02 close · :05 open · Cmt 21:00 weekly
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
MIN_ENTRY_PRICE = float(os.environ.get("A2_05_V2_MIN_ENTRY_PRICE") or 0.40)

CONFIG = A2Config(
    algo_num=ALGO_NUM,
    key=BOOK_KEY,
    label="A2#05 V2 Mean Reversion (fiyat tabanı)",
    algo_name="Mean Reversion (Z-Score) · 0,40 fiyat tabanı",
    state_file=os.path.join(_DIR, f"poly_trader_{BOOK_KEY}_state.json"),
    history_file=os.path.join(_DIR, f"poly_trader_{BOOK_KEY}_history.json"),
    min_entry_price=MIN_ENTRY_PRICE,
    live_mirror=False,
)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    asyncio.run(run_mode(mode, [CONFIG]))
