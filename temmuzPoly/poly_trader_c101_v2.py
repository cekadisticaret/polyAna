#!/usr/bin/env python3
"""C1#01 V2 — aynı model, gerçek alınabilir fiyata karşı.

C1#01 ile **tek farkı fiyat kaynağı ve kenar eşiği**; model, veri toplama,
Kelly kademelendirmesi, settle mantığı birebir aynı. İkisi bilerek paralel
koşuyor çünkü farklı soruları ölçüyorlar:

  C1#01     Gamma `outcomePrices` (son işlem fiyatı) · eşik 5 puan
            → "model doğru tarafı seçiyor mu?" — fiyat kurgusal, yön gerçek
  C1#01 V2  CLOB best_ask (gerçekten ödenecek fiyat) · eşik 3 puan
            → "bu işten para kazanılır mı?" — hem yön hem maliyet gerçek

Neden ikisi birden: 2026-08-14'te fiyat kaynağı ask'e çevrilince ölçülen
ortalama kenar 7,1 puandan 1,6 puana düştü ve defter işlem açmayı bıraktı.
Eski ölçümün yapay olduğunun kanıtı `overround` — mid'e karşı tam 0,0000
çıkıyordu, ki gerçek bir emir defterinde imkânsız. Ama "kenar sahteydi"
demek "model kötü" demek değil; ikisi ayrı iddia ve ayrı ölçülmeli.

`poly_trader_c101.py` **dokunulmaz** — modül olarak import edilip yalnız
globalleri yönlendirilir (projede `analiz6_v4` → `analiz6_v3` ile aynı kalıp).
Aynı süreçte iki defter birlikte koşamaz; cron ayrı süreçler başlattığı için
sorun değil.

Cron: :02 close · :05 open · :25 backfill
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import poly_trader_c101 as base  # noqa: E402
from c101_signal import evaluate as _evaluate  # noqa: E402
from pm_trader_helpers import pm_best_ask, pm_find_market  # noqa: E402

# ── Bu defterin kimliği ───────────────────────────────────────
EDGE_MIN = float(os.environ.get("C101_V2_EDGE_MIN") or 0.03)

base.STATE_FILE = os.path.join(_DIR, "poly_trader_c101_v2_state.json")
base.HISTORY_FILE = os.path.join(_DIR, "poly_trader_c101_v2_history.json")
base.CALIB_FILE = os.path.join(_DIR, "c101_v2_calibration.jsonl")
base.LABEL = "C1#01 V2"
base.BOOK_KEY = "c101_v2"
base.ALGO_NAME = "OPUS-OHLCV V2 · gerçek ask'e karşı adil fiyat"
base.INITIAL_BALANCE = 1000.0


def pm_prices(symbol: str, now_utc: datetime) -> dict | None:
    """İki tarafın CLOB best_ask'i — gerçekten ödenecek fiyat.

    Gamma mid'i `up_mid`/`down_mid` alanlarında saklanır ki iki defterin aynı
    slotta neye baktığı sonradan karşılaştırılabilsin. Ask okunamazsa mid'e
    düşülür ve `quote_src` bunu söyler.
    """
    et_hour = (now_utc - timedelta(hours=4)).hour
    pm = pm_find_market(symbol, et_hour, now_utc)
    if not pm or pm.get("closed"):
        return None
    op = pm.get("outcome_prices") or []
    if len(op) < 2:
        return None
    try:
        up_mid, down_mid = float(op[0]), float(op[1])
    except (ValueError, TypeError):
        return None
    up_ask = pm_best_ask(pm["up_token"])
    down_ask = pm_best_ask(pm["down_token"])
    up_p = up_ask if up_ask is not None else up_mid
    down_p = down_ask if down_ask is not None else down_mid
    if not (0.01 < up_p < 0.99 and 0.01 < down_p < 0.99):
        return None
    return {
        "slug": pm["slug"],
        "title": pm.get("title", ""),
        "up": up_p,
        "down": down_p,
        "quote_src": "ask" if (up_ask is not None and down_ask is not None) else "mid",
        "up_mid": round(up_mid, 4),
        "down_mid": round(down_mid, 4),
        "overround": round(up_p + down_p - 1.0, 4),
    }


def evaluate(model: dict, pm_up_price: float, pm_down_price: float) -> dict:
    """Ortak motor, bu defterin eşiğiyle."""
    return _evaluate(model, pm_up_price, pm_down_price, edge_min=EDGE_MIN)


base.pm_prices = pm_prices
base.evaluate = evaluate

_MODES = {
    "open": base.run_open, "close": base.run_close, "preview": base.run_preview,
    "stats": base.run_stats, "calib": base.run_calib, "compare": base.run_compare,
    "backfill": base.run_backfill,
}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    fn = _MODES.get(mode)
    if not fn:
        print(f"Bilinmeyen mod: {mode}\nKullanım: {' | '.join(_MODES)}")
        sys.exit(1)
    fn()
