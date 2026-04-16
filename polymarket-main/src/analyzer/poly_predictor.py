"""
╔══════════════════════════════════════════════════════════════════╗
║  POLYMARKET TAHMİN MOTORU v1.2                                   ║
║  v1.2 Winrate İyileştirmeleri:                                   ║
║  [W1] Geçmiş sinyal accuracy → dinamik ağırlık geri bildirimi   ║
║  [W2] Rejime göre dinamik sinyal ağırlıkları (trend/ranging)    ║
║  [W3] Tahmin zamanı :10'a çekildi (kapanış kıyı filtresi)       ║
║  [W4] Volatilite filtresi — yüksek ATR'da confidence yumuşatma  ║
║  [W5] ETH-SOL çapraz korelasyon sinyali                         ║
║  [W6] Makro haber saati filtresi                                 ║
║  [W7] Likidasyon cascade tespiti                                 ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
# WebSocket proxy sorununu önle — Cursor/IDE sandbox proxy değişkenlerini temizle
for _pv in ["SOCKS_PROXY","SOCKS5_PROXY","socks_proxy","socks5_proxy",
            "HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy",
            "ALL_PROXY","all_proxy"]:
    os.environ.pop(_pv, None)

import asyncio
import json
import time
import re
import aiohttp
import websockets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv
import math
from src.config import Config
from src.trading.portfolio_snapshot import portfolio_snapshot_values
from src.data.market_fetcher import build_slug, fetch_single_event_by_slug
from src.trading.clob_orders import place_buy_for_up_down

load_dotenv()

# Ana proje: TELEGRAM_TOKEN / TELEGRAM_CHAT — polymarket-main .env: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT", "") or os.getenv("TELEGRAM_CHAT_ID", "")

# ── Polymarket ──
POLY_PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY", "")
POLY_FUNDER      = os.getenv("POLY_FUNDER", "")
POLY_API_KEY     = os.getenv("POLY_API_KEY", "")
POLY_API_SECRET  = os.getenv("POLY_API_SECRET", "")
POLY_API_PASS    = os.getenv("POLY_API_PASSPHRASE", "")
BET_SIZE_USDC    = float(os.getenv("POLY_BET_SIZE", "5"))
PREDICTIONS_FILE = os.path.join(os.path.dirname(__file__), "poly_predictions.json")
BET_DRY_RUN      = os.getenv("POLY_DRY_RUN", "true").lower() != "false"
CLOB_HOST        = "https://clob.polymarket.com"
GAMMA_HOST       = "https://gamma-api.polymarket.com"

SYMBOLS = ["ETHUSDT", "SOLUSDT"]

OB_CLEANUP_PCT      = 0.05
OB_CLEANUP_INTERVAL = 300
SIGNAL_MIN_SAMPLES  = 8       # [W1] accuracy hesabı için min örnek
ATR_HIGH_VOL_PCT    = 0.009   # [W4] %0.9 üstü = yüksek volatilite
MACRO_UTC_HOURS     = {12, 13, 14}  # [W6] FOMC/CPI/NFP saatleri (UTC)
PREDICTION_MINUTE   = 10      # [W3] :10'da tahmin — kapanış kıyısından uzak


def _symbol_icon(sym_short: str) -> str:
    """Telegram / konsol için kısa sembol ikonu."""
    return {"ETH": "Ξ", "SOL": "◎"}.get(sym_short, sym_short)


# ─────────────────────────────────────────────────────────────
# VERİ YAPILARI
# ─────────────────────────────────────────────────────────────

@dataclass
class Tick:
    ts:     float
    price:  float
    qty:    float
    usd:    float
    is_buy: bool


@dataclass
class Prediction:
    symbol:        str
    ts:            float
    current_price: float
    target_time:   str      # "20:00 İST"
    direction:     str      # "YUKARI" / "AŞAĞI" / "NÖTR"
    probability:   float    # 0.0 - 1.0
    confidence:    str      # "YÜKSEK" / "ORTA" / "DÜŞÜK"
    signals:       dict
    reasoning:     str
    bull_pct:      float = 0.0
    bear_pct:      float = 0.0
    h1_high:       float = 0.0
    h1_low:        float = 0.0
    key_level:     float = 0.0
    regime:        str = "UNKNOWN"   # [W2] TREND / RANGING / MIXED
    vol_level:     str = "NORMAL"    # [W4] NORMAL / HIGH
    macro_caution: bool = False      # [W6]


class SymbolState:
    def __init__(self, symbol: str):
        self.symbol    = symbol
        self.ticks: deque[Tick] = deque(maxlen=10000)
        self.price     = 0.0
        self.ob_bids: dict[float, float] = {}
        self.ob_asks: dict[float, float] = {}
        self.liq_data: list[dict] = []
        self.klines_1h: list[dict] = []
        self.funding_rate = 0.0
        self._last_ob_cleanup = 0.0

    # ── FİX 1: Order book memory leak önleme ──
    def cleanup_orderbook(self):
        """
        Mevcut fiyattan OB_CLEANUP_PCT dışındaki seviyeleri sil.
        Her OB_CLEANUP_INTERVAL saniyede bir çalışır.
        """
        now = time.time()
        if now - self._last_ob_cleanup < OB_CLEANUP_INTERVAL:
            return
        if self.price <= 0:
            return

        low_bound  = self.price * (1 - OB_CLEANUP_PCT)
        high_bound = self.price * (1 + OB_CLEANUP_PCT)

        self.ob_bids = {p: q for p, q in self.ob_bids.items() if p >= low_bound}
        self.ob_asks = {p: q for p, q in self.ob_asks.items() if p <= high_bound}
        self._last_ob_cleanup = now

    # ── FİX 2: liq_data temizliği ayrı metoda taşındı ──
    def cleanup_liq(self):
        """30 dakikadan eski likidasyon verilerini temizle."""
        cutoff = time.time() - 1800
        self.liq_data = [l for l in self.liq_data if l["ts"] >= cutoff]

    # CVD hesapları
    def cvd(self, seconds: int) -> float:
        cutoff = time.time() - seconds
        buy = sell = 0.0
        for t in self.ticks:
            if t.ts < cutoff: continue
            if t.is_buy: buy  += t.usd
            else:         sell += t.usd
        return buy - sell

    def buy_ratio(self, seconds: int = 300) -> float:
        cutoff = time.time() - seconds
        buy = sell = 0.0
        for t in self.ticks:
            if t.ts < cutoff: continue
            if t.is_buy: buy  += t.usd
            else:         sell += t.usd
        total = buy + sell
        return (buy / total * 100) if total > 0 else 50.0

    def large_trade_bias(self, min_usd: float = 100_000, seconds: int = 300) -> str:
        cutoff = time.time() - seconds
        buy_usd = sell_usd = 0.0
        for t in self.ticks:
            if t.ts < cutoff or t.usd < min_usd: continue
            if t.is_buy: buy_usd  += t.usd
            else:         sell_usd += t.usd
        if buy_usd > sell_usd * 1.5:  return "BUY"
        if sell_usd > buy_usd * 1.5:  return "SELL"
        return "NEUTRAL"

    # Order book imbalance
    def ob_imbalance(self, levels: int = 10) -> float:
        self.cleanup_orderbook()   # her imbalance sorgusunda periyodik temizlik
        bid_v = sum(p * q for p, q in sorted(self.ob_bids.items(), reverse=True)[:levels])
        ask_v = sum(p * q for p, q in sorted(self.ob_asks.items())[:levels])
        total = bid_v + ask_v
        return (bid_v / total * 100) if total > 0 else 50.0

    # Likidasyon bias
    def liq_bias(self, seconds: int = 600) -> str:
        self.cleanup_liq()
        cutoff = time.time() - seconds
        long_liq = short_liq = 0.0
        for l in self.liq_data:
            if l["ts"] < cutoff: continue
            if l["side"] == "BUY":  long_liq  += l["usd"]
            else:                    short_liq += l["usd"]
        if short_liq > long_liq * 1.5 and short_liq > 50_000:
            return "BULL"
        if long_liq > short_liq * 1.5 and long_liq > 50_000:
            return "BEAR"
        return "NEUTRAL"

    def liq_cascade(self, window: int = 300, min_count: int = 3, min_usd: float = 150_000) -> str:
        """[W7] Hızlanan likidasyon cascade tespiti."""
        self.cleanup_liq()
        cut = time.time() - window
        rec = [l for l in self.liq_data if l["ts"] >= cut]
        if len(rec) < min_count:
            return "NONE"
        lu = sum(l["usd"] for l in rec if l["side"] == "BUY")
        su = sum(l["usd"] for l in rec if l["side"] == "SELL")
        if lu + su < min_usd:
            return "NONE"
        if su > lu * 1.3:  return "BULL_CASCADE"
        if lu > su * 1.3:  return "BEAR_CASCADE"
        return "NONE"


states = {sym: SymbolState(sym) for sym in SYMBOLS}


# ─────────────────────────────────────────────────────────────
# [W1] SİNYAL ACCURACY GERİ BİLDİRİMİ
# ─────────────────────────────────────────────────────────────

_signal_accuracy: dict[str, tuple[int, int]] = {}


def _compute_signal_accuracy():
    global _signal_accuracy
    cutoff  = time.time() - 48 * 3600
    checked = [p for p in _load_predictions()
               if p.get("checked") and p.get("target_ts", 0) >= cutoff
               and "signal_votes" in p]
    acc: dict[str, list] = defaultdict(list)
    for p in checked:
        correct = int(p.get("correct", False))
        for sig_key, vote in p.get("signal_votes", {}).items():
            if vote == 0:
                continue
            is_bull_vote = (vote == 1)
            is_bull_pred = (p.get("direction") == "YUKARI")
            if is_bull_vote == is_bull_pred:
                acc[sig_key].append(correct)
    _signal_accuracy = {k: (sum(v), len(v)) for k, v in acc.items()
                        if len(v) >= SIGNAL_MIN_SAMPLES}


def _wmul(sig_key: str) -> float:
    """[W1] Sinyal accuracy çarpanı: 0.6–1.4, veri yoksa 1.0"""
    if sig_key not in _signal_accuracy:
        return 1.0
    ok, total = _signal_accuracy[sig_key]
    rate = ok / total
    if rate < 0.50: return 0.6
    if rate < 0.60: return 0.8
    if rate < 0.70: return 1.0
    return 1.4


# ─────────────────────────────────────────────────────────────
# [W5] ETH-SOL ÇAPRAZ KORELASYON
# ─────────────────────────────────────────────────────────────

def _cross_signal(sym: str) -> str:
    other = "SOLUSDT" if sym == "ETHUSDT" else "ETHUSDT"
    if other not in states:
        return "NEUTRAL"
    own_cvd = states[sym].cvd(300)
    oth_cvd = states[other].cvd(300)
    if own_cvd > 0 and oth_cvd > 0:   return "CONFIRM_BULL"
    if own_cvd < 0 and oth_cvd < 0:   return "CONFIRM_BEAR"
    if own_cvd * oth_cvd < 0:         return "DIVERGE"
    return "NEUTRAL"


# ─────────────────────────────────────────────────────────────
# [W6] MAKRO SAAT FİLTRESİ
# ─────────────────────────────────────────────────────────────

def _is_macro_hour() -> bool:
    return datetime.now(timezone.utc).hour in MACRO_UTC_HOURS


# ─────────────────────────────────────────────────────────────
# TAHMİN MOTORU
# ─────────────────────────────────────────────────────────────

def _ema(values: list[float], period: int) -> list[float]:
    """
    EMA hesapla. period-1 öncesi indisler NaN yerine 0.0 döner;
    çağıran kod yalnızca son değerleri kullanmalı.
    """
    n = len(values)
    if n < period:
        return [0.0] * n
    k = 2.0 / (period + 1)
    r = [0.0] * n
    r[period - 1] = sum(values[:period]) / period
    for i in range(period, n):
        r[i] = values[i] * k + r[i - 1] * (1 - k)
    return r


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    g = l = 0.0
    for i in range(1, period + 1):
        d = closes[-period - 1 + i] - closes[-period - 2 + i]
        if d > 0: g += d
        else:      l -= d
    ag, al = g / period, l / period
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def _macd_hist(closes: list[float]) -> float:
    """
    ── FİX 4: EMA'nın 0.0 doldurma bölgesi atlanarak güvenli indeks kullanılır ──
    MACD için en az 35 kapanış gerekir (26 EMA + 9 sinyal).
    """
    if len(closes) < 35:
        return 0.0
    ef = _ema(closes, 12)
    es = _ema(closes, 26)
    # 0.0 dolu bölgeyi atla: 26. indisten itibaren anlamlı
    macd_line = [ef[i] - es[i] for i in range(25, len(closes))]
    if len(macd_line) < 9:
        return 0.0
    sig = _ema(macd_line, 9)
    # Sinyal EMA'nın anlamlı son değeri (9-1 = 8. indisten itibaren dolu)
    if len(sig) < 9:
        return 0.0
    return macd_line[-1] - sig[-1]


def _adx(highs: list[float], lows: list[float], closes: list[float],
         period: int = 14) -> tuple[float, float, float]:
    n = len(closes)
    if n < period * 2:
        return 0.0, 0.0, 0.0
    tr_l = pdm_l = ndm_l = [0.0]
    for i in range(1, n):
        tr   = max(highs[i] - lows[i],
                   abs(highs[i] - closes[i - 1]),
                   abs(lows[i]  - closes[i - 1]))
        up   = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        tr_l  = tr_l  + [tr]
        pdm_l = pdm_l + [up   if up > down and up > 0   else 0.0]
        ndm_l = ndm_l + [down if down > up and down > 0 else 0.0]

    def ws(d, p):
        r = [0.0] * len(d)
        if len(d) <= p:
            return r
        r[p] = sum(d[1:p + 1])
        for i in range(p + 1, len(d)):
            r[i] = r[i - 1] - r[i - 1] / p + d[i]
        return r

    at = ws(tr_l, period)
    pm = ws(pdm_l, period)
    nm = ws(ndm_l, period)
    pdi = [100 * pm[i] / at[i] if at[i] > 0 else 0 for i in range(n)]
    ndi = [100 * nm[i] / at[i] if at[i] > 0 else 0 for i in range(n)]
    dx  = [100 * abs(pdi[i] - ndi[i]) / (pdi[i] + ndi[i])
           if (pdi[i] + ndi[i]) > 0 else 0 for i in range(n)]
    adx_s = ws(dx, period)
    return round(adx_s[-1], 2), round(pdi[-1], 2), round(ndi[-1], 2)


def _chop(highs: list[float], lows: list[float], closes: list[float],
          period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    wh = max(highs[-period:])
    wl = min(lows[-period:])
    if wh - wl == 0:
        return 50.0
    atr_sum = sum(
        max(highs[-period + i] - lows[-period + i],
            abs(highs[-period + i] - closes[-period + i - 1]),
            abs(lows[-period + i]  - closes[-period + i - 1]))
        for i in range(period)
    )
    return round(100 * math.log10(atr_sum / (wh - wl)) / math.log10(period), 2)


def _atr_ratio(highs: list[float], lows: list[float], closes: list[float],
               period: int = 14) -> float:
    """[W4] ATR/fiyat oranı — volatilite seviyesi için."""
    if len(closes) < period + 1:
        return 0.0
    trs = [max(highs[i] - lows[i],
               abs(highs[i] - closes[i - 1]),
               abs(lows[i]  - closes[i - 1]))
           for i in range(len(closes) - period, len(closes))]
    atr = sum(trs) / period
    return atr / closes[-1] if closes[-1] > 0 else 0.0


def generate_prediction(state: SymbolState) -> Optional[Prediction]:
    """Tüm sinyalleri birleştir → 1 saatlik yön tahmini üret (v1.2)"""
    if state.price <= 0:
        return None

    signals: dict = {}
    signal_votes: dict = {}
    bull_pts = bear_pts = total_w = 0.0

    # ── Rejim tespiti [W2] ──
    kl_raw = state.klines_1h
    regime = "UNKNOWN"; chop_val = 50.0; adx_val = 0.0; atr_r = 0.0; vol_level = "NORMAL"
    if len(kl_raw) >= 55:
        c_all = [k["close"] for k in kl_raw]
        h_all = [k["high"]  for k in kl_raw]
        l_all = [k["low"]   for k in kl_raw]
        adx_val, _, _ = _adx(h_all, l_all, c_all)
        chop_val      = _chop(h_all, l_all, c_all)
        atr_r         = _atr_ratio(h_all, l_all, c_all)
        if adx_val > 22 and chop_val < 55:   regime = "TREND"
        elif chop_val > 58:                   regime = "RANGING"
        else:                                 regime = "MIXED"
        if atr_r > ATR_HIGH_VOL_PCT:          vol_level = "HIGH"

    # [W2] Rejime göre taban ağırlıklar
    if regime == "TREND":
        W_CVD5, W_CVD30, W_OB, W_LARGE, W_LIQ, W_BR = 2.5, 1.5, 1.5, 2.5, 1.5, 0.8
        W_RSI,  W_MACD,  W_EMA, W_REGIME, W_FUND    = 2.5, 2.5, 2.5, 1.5, 1.0
    elif regime == "RANGING":
        W_CVD5, W_CVD30, W_OB, W_LARGE, W_LIQ, W_BR = 3.5, 2.5, 3.0, 3.0, 2.0, 1.2
        W_RSI,  W_MACD,  W_EMA, W_REGIME, W_FUND    = 1.5, 1.5, 1.5, 0.5, 1.0
    else:
        W_CVD5, W_CVD30, W_OB, W_LARGE, W_LIQ, W_BR = 3.0, 2.0, 2.0, 3.0, 2.0, 1.0
        W_RSI,  W_MACD,  W_EMA, W_REGIME, W_FUND    = 2.0, 2.0, 2.0, 1.0, 1.0

    def add(key: str, base_w: float, vote: int, label: str):
        nonlocal bull_pts, bear_pts, total_w
        w = base_w * _wmul(key)
        signal_votes[key] = vote
        if vote == 1:    bull_pts += w
        elif vote == -1: bear_pts += w
        total_w += w
        signals[key] = label

    # 1. CVD 5dk
    cvd5 = state.cvd(300)
    add("cvd_5m", W_CVD5, 1 if cvd5 > 0 else -1,
        f"{'🟢' if cvd5>0 else '🔴'} CVD 5dk: {'+' if cvd5>0 else ''}${cvd5/1000:.1f}K")

    # 2. CVD 30dk
    cvd30 = state.cvd(1800)
    add("cvd_30m", W_CVD30, 1 if cvd30 > 0 else -1,
        f"{'🟢' if cvd30>0 else '🔴'} CVD 30dk: {'+' if cvd30>0 else ''}${cvd30/1000:.1f}K")

    # 3. OB imbalance
    imb = state.ob_imbalance()
    if imb >= 62:
        add("ob_imb", W_OB, 1,  f"🟢 OB İmbalance: %{imb:.1f} (alış ağır)")
    elif imb <= 38:
        add("ob_imb", W_OB, -1, f"🔴 OB İmbalance: %{imb:.1f} (satış ağır)")
    else:
        add("ob_imb", W_OB, 0,  f"⚪ OB İmbalance: %{imb:.1f} (nötr)")

    # 4. Büyük işlemler
    lt = state.large_trade_bias(100_000, 300)
    if lt == "BUY":    add("large_trades", W_LARGE, 1,  "🟢 Büyük işlemler: ALIŞ yönü")
    elif lt == "SELL": add("large_trades", W_LARGE, -1, "🔴 Büyük işlemler: SATIŞ yönü")
    else:              add("large_trades", W_LARGE, 0,  "⚪ Büyük işlemler: nötr")

    # 5. Likidasyon bias
    liq = state.liq_bias(600)
    if liq == "BULL":   add("liquidation", W_LIQ, 1,  "🟢 Likidasyon: short'lar temizlendi")
    elif liq == "BEAR":  add("liquidation", W_LIQ, -1, "🔴 Likidasyon: long'lar temizlendi")
    else:                add("liquidation", W_LIQ, 0,  "⚪ Likidasyon: nötr")

    # 6. Alış oranı
    br = state.buy_ratio(300)
    if br >= 60:   add("buy_ratio", W_BR, 1,  f"🟢 Alış oranı: %{br:.0f}")
    elif br <= 40:  add("buy_ratio", W_BR, -1, f"🔴 Alış oranı: %{br:.0f}")
    else:           add("buy_ratio", W_BR, 0,  f"⚪ Alış oranı: %{br:.0f}")

    # [W7] Likidasyon cascade
    casc = state.liq_cascade()
    if casc == "BULL_CASCADE":
        w = 2.5 * _wmul("liq_cascade")
        bull_pts += w; total_w += w; signal_votes["liq_cascade"] = 1
        signals["liq_cascade"] = "🟢 Cascade: short likidasyon hızlanıyor ↑"
    elif casc == "BEAR_CASCADE":
        w = 2.5 * _wmul("liq_cascade")
        bear_pts += w; total_w += w; signal_votes["liq_cascade"] = -1
        signals["liq_cascade"] = "🔴 Cascade: long likidasyon hızlanıyor ↓"

    # [W5] Çapraz korelasyon
    cross = _cross_signal(state.symbol)
    if cross == "CONFIRM_BULL":
        w = 1.5 * _wmul("cross_corr")
        bull_pts += w; total_w += w; signal_votes["cross_corr"] = 1
        signals["cross_corr"] = "🟢 Korelasyon: ETH+SOL aynı yönde ↑"
    elif cross == "CONFIRM_BEAR":
        w = 1.5 * _wmul("cross_corr")
        bear_pts += w; total_w += w; signal_votes["cross_corr"] = -1
        signals["cross_corr"] = "🔴 Korelasyon: ETH+SOL aynı yönde ↓"
    elif cross == "DIVERGE":
        signal_votes["cross_corr"] = 0
        signals["cross_corr"] = "⚠️ Korelasyon: ETH↔SOL ayrışıyor"

    # 7. Kline teknik
    kl = state.klines_1h
    if len(kl) >= 55:
        c = [k["close"] for k in kl]
        h = [k["high"]  for k in kl]
        l = [k["low"]   for k in kl]
        rsi_v = _rsi(c); macd_h = _macd_hist(c)
        ema9 = _ema(c, 9); ema21 = _ema(c, 21); ema50 = _ema(c, 50)
        adx, pdi, ndi = _adx(h, l, c); chop = _chop(h, l, c)

        # RSI
        if 50 < rsi_v < 70:   add("rsi", W_RSI, 1,  f"🟢 RSI: {rsi_v:.0f} (momentum)")
        elif 30 < rsi_v < 50: add("rsi", W_RSI, -1, f"🔴 RSI: {rsi_v:.0f} (zayıf)")
        elif rsi_v >= 70:     add("rsi", W_RSI, 0,  f"⚠️ RSI: {rsi_v:.0f} (aşırı alım)")
        else:                 add("rsi", W_RSI, 0,  f"⚠️ RSI: {rsi_v:.0f} (aşırı satım)")

        # MACD
        add("macd", W_MACD, 1 if macd_h > 0 else -1,
            f"{'🟢' if macd_h>0 else '🔴'} MACD: {'pozitif' if macd_h>0 else 'negatif'} histogram")

        # EMA
        if ema9[-1] > ema21[-1] > ema50[-1]:    add("ema", W_EMA, 1,  "🟢 EMA: 9↑21↑50 (yükseliş)")
        elif ema9[-1] < ema21[-1] < ema50[-1]:   add("ema", W_EMA, -1, "🔴 EMA: 9↓21↓50 (düşüş)")
        else:                                     add("ema", W_EMA, 0,  "⚪ EMA: karışık")

        # Rejim sinyali
        if adx > 22 and chop < 55 and pdi > ndi:
            add("regime", W_REGIME, 1,  f"🟢 Rejim: trend yukarı (ADX:{adx:.0f} Chop:{chop:.0f})")
        elif adx > 22 and chop < 55 and ndi > pdi:
            add("regime", W_REGIME, -1, f"🔴 Rejim: trend aşağı (ADX:{adx:.0f} Chop:{chop:.0f})")
        elif chop > 60:
            add("regime", W_REGIME, 0,  f"⚪ Rejim: ranging (Chop:{chop:.0f})")
        else:
            add("regime", W_REGIME, 0,  f"⚪ Rejim: belirsiz (ADX:{adx:.0f})")

        # Funding
        fr = state.funding_rate
        if fr > 0.0005:    add("funding", W_FUND, -1, f"⚠️ Funding: %{fr*100:.3f} (long ödüyor)")
        elif fr < -0.0003: add("funding", W_FUND, 1,  f"🟢 Funding: %{fr*100:.3f} (short ödüyor)")
        else:              add("funding", W_FUND, 0,  f"⚪ Funding: %{fr*100:.3f} (normal)")

    if total_w == 0:
        return None

    bull_pct_val = round(bull_pts / total_w * 100) if total_w else 50
    bear_pct_val = round(bear_pts / total_w * 100) if total_w else 50
    # Telegram’daki ▲▼ yüzdeleriyle aynı kural: büyük olan yön (eşitlikte ham puan)
    if bull_pct_val > bear_pct_val:
        direction = "YUKARI"
    elif bear_pct_val > bull_pct_val:
        direction = "AŞAĞI"
    else:
        direction = "YUKARI" if bull_pts >= bear_pts else "AŞAĞI"
    raw_prob  = (bull_pts / total_w if bull_pts > bear_pts
                 else bear_pts / total_w if bear_pts > bull_pts else 0.5)
    prob = max(0.50, min(0.85, 0.5 + (raw_prob - 0.5) * 0.7))

    gap = abs(bull_pts - bear_pts)
    confidence = ("YÜKSEK" if gap >= total_w * 0.4
                  else "ORTA" if gap >= total_w * 0.2 else "DÜŞÜK")

    # [W4] Yüksek volatilite → YÜKSEK → ORTA
    if vol_level == "HIGH" and confidence == "YÜKSEK":
        confidence = "ORTA"
        signals["volatility"] = f"⚠️ Yüksek ATR: %{atr_r*100:.2f} — güven düşürüldü"
    else:
        signals["volatility"] = f"⚪ ATR: %{atr_r*100:.2f}"

    # [W6] Makro saat → YÜKSEK → ORTA
    macro_caution = _is_macro_hour()
    if macro_caution and confidence == "YÜKSEK":
        confidence = "ORTA"
        signals["macro"] = "⚠️ Makro saat — güven düşürüldü"
    elif macro_caution:
        signals["macro"] = "⚠️ Makro saat"

    now_utc    = datetime.now(timezone.utc)
    target_ist = (now_utc.hour + 1 + 3) % 24
    target_time = f"{target_ist:02d}:00 İST"

    kl2 = state.klines_1h
    h1_high = max(k["high"] for k in kl2[-3:]) if len(kl2) >= 3 else 0.0
    h1_low  = min(k["low"]  for k in kl2[-3:]) if len(kl2) >= 3 else 0.0

    p    = state.price
    step = 500 if p > 10_000 else 100 if p > 1_000 else 10 if p > 100 else 1
    key_level = round(round(p / step) * step, 2)

    pred = Prediction(
        symbol        = state.symbol,
        ts            = time.time(),
        current_price = state.price,
        target_time   = target_time,
        direction     = direction,
        probability   = prob,
        confidence    = confidence,
        signals       = signals,
        reasoning     = (f"Rejim:{regime} | Vol:{vol_level} | "
                         f"Boğa:{bull_pts:.1f}/{total_w:.1f} | Ayı:{bear_pts:.1f}/{total_w:.1f}"),
        bull_pct      = bull_pct_val,
        bear_pct      = bear_pct_val,
        h1_high       = h1_high,
        h1_low        = h1_low,
        key_level     = key_level,
        regime        = regime,
        vol_level     = vol_level,
        macro_caution = macro_caution,
    )
    pred._signal_votes = signal_votes  # type: ignore[attr-defined]
    return pred


# ─────────────────────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────────────────────

def fmt_price(p: float) -> str:
    return f"${p:,.2f}"

def prob_bar(prob: float) -> str:
    n = int(prob * 10)
    return "█" * n + "░" * (10 - n)

async def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print(f"[TG] {msg[:100]}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json={
                "chat_id":    TELEGRAM_CHAT,
                "text":       msg,
                "parse_mode": "HTML"
            }, timeout=aiohttp.ClientTimeout(total=10)) as r:
                resp = await r.json()
                if resp.get("ok"):
                    print(f"[TG OK] Mesaj gönderildi (msg_id={resp['result']['message_id']})")
                else:
                    print(f"[TG HATA] {resp.get('description','?')} — parse_mode kaldırılıyor")
                    async with s.post(url, json={
                        "chat_id": TELEGRAM_CHAT,
                        "text":    msg[:4000],
                    }, timeout=aiohttp.ClientTimeout(total=10)) as r2:
                        resp2 = await r2.json()
                        if resp2.get("ok"):
                            print(f"[TG OK] Mesaj parse_mode'suz gönderildi")
                        else:
                            print(f"[TG HATA2] {resp2.get('description','?')}")
    except Exception as e:
        print(f"[TG HATA] {e}")


def _build_coin_block(pred: Prediction) -> str:
    """Tek coin için detay bloğu üretir (v1.2: rejim/vol/macro badge)."""
    sym   = pred.symbol.replace("USDT", "")
    icon  = _symbol_icon(sym)
    d_ico = "📉" if pred.direction == "AŞAĞI" else "📈" if pred.direction == "YUKARI" else "➡️"

    rsi_sig = pred.signals.get("rsi", "")
    rsi_m   = re.search(r'[\d.]+', rsi_sig)
    rsi_v   = float(rsi_m.group()) if rsi_m else 0.0

    reg_sig = pred.signals.get("regime", "")
    adx_m   = re.search(r'ADX:([\d.]+)', reg_sig)
    adx_v   = float(adx_m.group(1)) if adx_m else 0.0

    trend_str = "AŞAĞI" if pred.direction == "AŞAĞI" else "YUKARI"
    trend_ico = "🔴" if trend_str == "AŞAĞI" else "🟢"
    p = pred.current_price
    kl = pred.key_level
    kl_rel = "ÜZERİNDE" if p >= kl else "ALTINDA"

    h_range = f"🔧 1h: ${pred.h1_low:,.0f} – ${pred.h1_high:,.0f}\n" if pred.h1_high else ""
    regime_badge = {"TREND": "📈TREND", "RANGING": "↔️RANGE", "MIXED": "〰️MIXED"}.get(pred.regime, "❓")
    badges = (f"{regime_badge}"
              f"{'  ⚡YÜK.VOL' if pred.vol_level == 'HIGH' else ''}"
              f"{'  📰MAKRO' if pred.macro_caution else ''}")

    return (
        f"{icon} <b>{sym}</b>  ${p:,.2f}  {d_ico}\n"
        f"▲ YUKARI: <b>{pred.bull_pct}%</b>  |  ▼ AŞAĞI: <b>{pred.bear_pct}%</b>\n"
        f"{h_range}"
        f"{trend_ico} Trend: {trend_str}  |  RSI:{rsi_v:.0f}  |  ADX:{adx_v:.0f}\n"
        f"🔍 {badges}\n"
        f"🎯 Yakın seviye: ${kl:,.0f} ({kl_rel})"
    )


def _bet_status_line(sym: str, pred: "Prediction", bet: Optional[dict]) -> str:
    """Coin için işlem durumu satırı."""
    icon = _symbol_icon(sym.replace("USDT", ""))
    name = sym.replace("USDT", "")
    if pred.direction == "NÖTR":
        return f"⏭ {icon} {name} → girilmedi (nötr)"
    if not Config.POLYMARKET_BOT_ENABLED:
        return f"⏭ {icon} {name} → girilmedi (bot kapalı)"
    if not bet:
        return f"⏭ {icon} {name} → girilmedi (market yok / emir hatası)"
    amount = bet.get("amount") or bet.get("size") or bet.get("cost")
    odds   = bet.get("odds") or bet.get("price")
    payout = bet.get("payout") or bet.get("winnings")
    if amount and odds:
        pay_str = f" → kazanırsak: ${payout:.2f}" if payout else ""
        return f"💰 {icon} {name} → ${float(amount):.2f} girildi  (odds: {float(odds):.2f}{pay_str})"
    return f"💰 {icon} {name} → girildi"


async def send_unified_prediction(preds: list, past_results: list, bet_results: Optional[dict] = None):
    """ETH + SOL tahminlerini tek mesajda gönderir."""
    if not preds:
        return

    target_time = preds[0].target_time

    prev_block = ""
    if past_results:
        seen = {}
        for r in sorted(past_results, key=lambda x: x.get("target_ts", 0)):
            seen[r["symbol"]] = r
        past_results = list(seen.values())
        correct = [r for r in past_results if r.get("correct")]
        prev_lines = []
        for r in past_results:
            ok   = r.get("correct", False)
            icon = "✅" if ok else "❌"
            sym  = r["symbol"].replace("USDT", "")
            s_ic = _symbol_icon(sym)
            ep   = r.get("price", 0)
            ap   = r.get("actual_price", 0)
            diff = ap - ep
            line = (f"{icon} {s_ic} {sym}  ${ep:,.2f} → ${ap:,.2f}  "
                    f"({'+' if diff>=0 else ''}{diff:,.2f})  Tahmin: {r['direction']}")
            amt  = r.get("bet_amount")
            odds = r.get("bet_odds")
            pay  = r.get("bet_payout")
            if amt and odds:
                if ok and pay:
                    profit = float(pay) - float(amt)
                    line += f"\n   💰 ${float(amt):.2f} @ {float(odds):.2f} → <b>+${profit:.2f} kazandı</b>"
                elif ok:
                    line += f"\n   💰 ${float(amt):.2f} @ {float(odds):.2f} → <b>kazandı</b>"
                else:
                    line += f"\n   💸 ${float(amt):.2f} @ {float(odds):.2f} → <b>-${float(amt):.2f} kaybetti</b>"
            prev_lines.append(line)
        score = f"{len(correct)}/{len(past_results)} doğru"
        prev_block = (
            f"─────────────────────\n"
            f"📋 <b>Geçen saat sonucu: {score}</b>\n"
            + "\n".join(prev_lines) + "\n"
        )

    coin_blocks = []
    for pred in preds:
        coin_blocks.append(_build_coin_block(pred))

    bet_lines = []
    for pred in preds:
        bet = (bet_results or {}).get(pred.symbol)
        bet_lines.append(_bet_status_line(pred.symbol, pred, bet))

    try:
        snap = portfolio_snapshot_values()
        col  = snap.get("collateral_usdc")
        pos  = snap.get("positions_mark_usdc")
        npos = snap.get("open_positions_count") or 0
        tot  = snap.get("portfolio_total_usdc")

        # CLOB API anlık güncellenemeyebilir; yerleştirilen bet tutarını
        # collateral'dan düş (bakiye henüz yansımamışsa göster)
        placed_total = sum(
            b["amount"] for b in (bet_results or {}).values()
            if isinstance(b, dict) and b.get("amount")
        )
        if col is not None and placed_total > 0:
            col = col - placed_total
            if tot is not None:
                tot = tot - placed_total

        col_s = f"${col:.2f} USDC" if col is not None else "—"
        pos_s = f"${pos:.2f} ({npos} adet)" if pos is not None else "—"
        tot_s = f"${tot:.2f} USDC" if tot is not None else "—"
        portfolio_block = (
            f"─────────────────────\n"
            f"💎 <b>Polymarket Bakiye</b>\n"
            f"💵 Kullanılabilir: <b>{col_s}</b>\n"
            f"📊 Açık pozisyonlar: <b>{pos_s}</b>\n"
            f"💰 Toplam: <b>{tot_s}</b>\n"
        )
    except Exception as e:
        print(f"[PORTFÖY HATA] {e}")
        portfolio_block = ""

    msg = (
        f"🎯 <b>CEMPOLYX2</b>\n"
        f"⏰ Hedef: <b>{target_time}</b>\n"
        f"{prev_block}"
        f"─────────────────────\n"
        + "\n─────────────────────\n".join(coin_blocks)
        + f"\n─────────────────────\n"
        + "\n".join(bet_lines) + "\n"
        + f"{portfolio_block}"
        f"─────────────────────\n"
        f"─────────────────────\n"
        f"─────────────────────"
    )

    await send_telegram(msg)


# ─────────────────────────────────────────────────────────────
# TAHMİN KAYIT & SONUÇ DOĞRULAMA
# ─────────────────────────────────────────────────────────────

def _load_predictions() -> list:
    if not os.path.exists(PREDICTIONS_FILE):
        return []
    try:
        with open(PREDICTIONS_FILE) as f:
            return json.load(f)
    except Exception:
        return []

def _save_predictions(preds: list):
    with open(PREDICTIONS_FILE, "w") as f:
        json.dump(preds, f, indent=2, ensure_ascii=False)

def record_prediction(pred: "Prediction", bet: Optional[dict] = None):
    """Tahmini dosyaya kaydet (v1.2: signal_votes, regime, vol_level, bet)."""
    now       = datetime.now(timezone.utc)
    target_ts = now.replace(minute=0, second=0, microsecond=0).timestamp() + 3600

    entry: dict = {
        "symbol":       pred.symbol,
        "direction":    pred.direction,
        "price":        pred.current_price,
        "confidence":   pred.confidence,
        "target_ts":    target_ts,
        "sent_ts":      now.timestamp(),
        "checked":      False,
        "regime":       pred.regime,
        "vol_level":    pred.vol_level,
        "signal_votes": getattr(pred, "_signal_votes", {}),
    }
    if bet:
        entry["bet_amount"] = bet.get("amount") or bet.get("size") or bet.get("cost")
        entry["bet_odds"]   = bet.get("odds")   or bet.get("price")
        entry["bet_payout"] = bet.get("payout") or bet.get("winnings")

    preds = _load_predictions()
    preds.append(entry)
    _save_predictions(preds)
    target_h = (now.hour + 1) % 24
    print(f"[KAYIT] {pred.symbol} {pred.direction} → hedef {target_h:02d}:00 UTC kaydedildi")


async def fetch_price_at(symbol: str, target_ts: float) -> float:
    """target_ts anındaki 1h kapanış fiyatını döner."""
    start_ms = int(target_ts * 1000) - 3600_000
    end_ms   = int(target_ts * 1000)
    url = "https://fapi.binance.com/fapi/v1/klines"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params={
                "symbol":    symbol,
                "interval":  "1h",
                "startTime": start_ms,
                "endTime":   end_ms,
                "limit":     1,
            }, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
        if data:
            return float(data[-1][4])
    except Exception as e:
        print(f"[PRICE_AT] {e}")
    return 0.0


async def check_past_predictions():
    """
    target_ts geçmiş, henüz kontrol edilmemiş tahminleri doğrula.
    """
    now   = time.time()
    preds = _load_predictions()
    updated = False

    for p in preds:
        if p.get("checked"):
            continue
        if p["target_ts"] > now:
            continue

        symbol      = p["symbol"]
        direction   = p["direction"]
        entry_price = p["price"]
        target_ts   = p["target_ts"]

        actual_price = await fetch_price_at(symbol, target_ts)
        if actual_price <= 0:
            continue

        change_pct = (actual_price - entry_price) / entry_price * 100
        actual_dir = "YUKARI" if change_pct >= 0 else "AŞAĞI"
        correct    = (direction == actual_dir)

        sym_short = symbol.replace("USDT", "")
        print(f"[SONUÇ] {sym_short} → tahmin:{direction} gerçek:{actual_dir} "
              f"({'✅' if correct else '❌'})")

        p["checked"]      = True
        p["actual_dir"]   = actual_dir
        p["actual_price"] = actual_price
        p["change_pct"]   = round(change_pct, 3)
        p["correct"]      = correct
        updated = True

    if updated:
        _save_predictions(preds)


# ─────────────────────────────────────────────────────────────
# POLYMARKET BAHİS (stub — ana uygulama pipeline'ı kullanır)
# ─────────────────────────────────────────────────────────────

async def send_daily_report():
    """Son 24 saatin tahminlerini değerlendirir, Telegram'a gönderir."""
    cutoff = time.time() - 86400
    preds  = [p for p in _load_predictions()
              if p.get("checked") and p.get("target_ts", 0) >= cutoff]

    if not preds:
        await send_telegram("📊 <b>Günlük Tahmin Raporu</b>\nSon 24 saatte değerlendirilen tahmin yok.")
        return

    by_sym: dict = defaultdict(list)
    for p in preds:
        by_sym[p["symbol"]].append(p)

    now_ist = datetime.now(timezone.utc)

    lines = [
        f"📊 <b>POLYX2 — Günlük Tahmin Raporu</b>",
        f"🗓 {now_ist.strftime('%d.%m.%Y')}  |  Son 24 saat",
        f"━━━━━━━━━━━━━━━━━━━━",
    ]

    total_ok = total_all = 0
    for sym in SYMBOLS:
        items = by_sym.get(sym)
        if not items:
            continue
        ok   = sum(1 for i in items if i.get("correct"))
        fail = len(items) - ok
        n    = len(items)
        total_ok  += ok
        total_all += n
        rate  = ok / n * 100 if n else 0
        icon  = _symbol_icon(sym.replace("USDT", ""))
        medal = "🥇" if rate >= 70 else "✅" if rate >= 50 else "⚠️"
        name  = sym.replace("USDT", "")

        dirs_ok   = {}
        dirs_fail = {}
        for d in ("YUKARI", "AŞAĞI"):
            d_items = [i for i in items if i["direction"] == d]
            dirs_ok[d]   = sum(1 for i in d_items if i.get("correct"))
            dirs_fail[d] = len(d_items) - dirs_ok[d]

        lines.append(
            f"{icon} <b>{name}</b>  {medal}\n"
            f"   ✅ {ok} başarılı  ❌ {fail} başarısız  — %{rate:.0f}\n"
            f"   📈 Yukarı: {dirs_ok['YUKARI']}✅ {dirs_fail['YUKARI']}❌  "
            f"│  📉 Aşağı: {dirs_ok['AŞAĞI']}✅ {dirs_fail['AŞAĞI']}❌"
        )

    overall = total_ok / total_all * 100 if total_all else 0
    medal_g  = "🥇" if overall >= 70 else "✅" if overall >= 50 else "⚠️"
    lines += [
        f"━━━━━━━━━━━━━━━━━━━━",
        f"{medal_g} <b>Genel: {total_ok} başarılı  {total_all-total_ok} başarısız  (%{overall:.0f})</b>",
    ]

    await send_telegram("\n".join(lines))
    print(f"[RAPOR] Gönderildi — {total_ok}/{total_all} doğru ({overall:.0f}%)")


_COIN_MAP = {"ETHUSDT": "ethereum", "SOLUSDT": "solana"}
_DIR_MAP  = {"YUKARI": "UP", "AŞAĞI": "DOWN"}

_ET = ZoneInfo("America/New_York")


async def find_market(coin: str, direction: str, price: float) -> Optional[dict]:
    """
    Cari ET saati için coin'e ait Gamma market objesini döndürür.
    clobTokenIds yoksa None döner.
    """
    now_et = datetime.now(timezone.utc).astimezone(_ET)
    cur_et = now_et.replace(minute=0, second=0, microsecond=0)
    slug   = build_slug(coin, cur_et)

    loop  = asyncio.get_event_loop()
    event = await loop.run_in_executor(None, fetch_single_event_by_slug, slug)

    if not event or not isinstance(event, dict):
        print(f"[BET] Event bulunamadı: {slug}")
        return None

    markets = event.get("markets") or []
    if not markets or not isinstance(markets[0], dict):
        print(f"[BET] Market listesi boş: {slug}")
        return None

    market = markets[0]
    if not market.get("clobTokenIds"):
        print(f"[BET] clobTokenIds eksik: {slug}")
        return None

    return market


async def place_bet(pred: "Prediction") -> Optional[dict]:
    """
    Tahmin yönüne (YUKARI/AŞAĞI) Polymarket CLOB emri açar; güven seviyesi emri engellemez.
    Başarılıysa {"amount", "odds", "payout", "order_response"} döner; aksi hâlde None.
    """
    if not Config.POLYMARKET_BOT_ENABLED:
        return None
    if pred.direction not in _DIR_MAP:
        return None

    coin = _COIN_MAP.get(pred.symbol)
    if not coin:
        print(f"[BET] Bilinmeyen sembol: {pred.symbol}")
        return None

    up_down = _DIR_MAP[pred.direction]
    market  = await find_market(coin, up_down, pred.current_price)
    if not market:
        return None

    notional = Config.POLYMARKET_ORDER_USDC

    # Mevcut odds (outcomePrices[0]=UP, [1]=DOWN)
    try:
        prices_raw = market.get("outcomePrices", "[]")
        prices = json.loads(prices_raw) if isinstance(prices_raw, str) else list(prices_raw)
        idx  = 0 if up_down == "UP" else 1
        odds = float(prices[idx]) if len(prices) > idx else None
    except (IndexError, TypeError, ValueError):
        odds = None

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: place_buy_for_up_down(market, up_or_down=up_down, notional_usdc=notional),
        )
        exec_price = result.get("execution_price") if isinstance(result, dict) else None
        shares     = result.get("shares")          if isinstance(result, dict) else None
        order_resp = result.get("order", result)   if isinstance(result, dict) else result

        # Gerçek çalıştırma fiyatını kullan; yoksa Gamma outcomePrices fallback
        actual_price = exec_price or odds
        payout = round(shares, 2) if shares else (round(notional / actual_price, 2) if actual_price and actual_price > 0.01 else None)
        display_odds = round(exec_price, 4) if exec_price else odds

        oid = order_resp.get("orderID") or order_resp.get("orderId") or order_resp.get("id") if isinstance(order_resp, dict) else "?"
        print(f"[BET] ✅ {coin} {up_down} ${notional:.2f} @ {display_odds} ({shares} hisse) → orderID:{oid}")
        return {
            "amount":         notional,
            "odds":           display_odds,
            "payout":         payout,
            "order_response": order_resp,
        }
    except Exception as e:
        print(f"[BET HATA] {coin} {up_down}: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# BİNANCE VERİ ÇEKME
# ─────────────────────────────────────────────────────────────

async def fetch_klines(symbol: str) -> list[dict]:
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {"symbol": symbol, "interval": "1h", "limit": 100}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params,
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                return [{"close": float(k[4]), "high": float(k[2]),
                         "low": float(k[3]), "open": float(k[1]),
                         "volume": float(k[5])} for k in data]
    except Exception as e:
        print(f"[KLINES HATA] {e}")
        return []


async def fetch_funding(symbol: str) -> float:
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params={"symbol": symbol},
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                return float(data.get("lastFundingRate", 0))
    except Exception as e:
        print(f"[FUNDING HATA] {e}")
        return 0.0


# ─────────────────────────────────────────────────────────────
# WEBSOCKET STREAMLER
# ─────────────────────────────────────────────────────────────

async def trade_stream():
    streams = "/".join(f"{s.lower()}@aggTrade" for s in SYMBOLS)
    url     = f"wss://fstream.binance.com/stream?streams={streams}"
    while True:
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                print("[WS] Trade stream bağlandı")
                async for raw in ws:
                    msg  = json.loads(raw)
                    data = msg.get("data", {})
                    sym  = data.get("s", "")
                    if sym not in states: continue
                    price  = float(data.get("p", 0))
                    qty    = float(data.get("q", 0))
                    is_buy = not data.get("m", True)
                    if price > 0:
                        tick = Tick(
                            ts=data.get("T", time.time()*1000)/1000,
                            price=price, qty=qty, usd=price*qty, is_buy=is_buy
                        )
                        states[sym].ticks.append(tick)
                        states[sym].price = price
        except Exception as e:
            print(f"[WS TRADE] {e} — yeniden bağlanıyor")
            await asyncio.sleep(3)


async def orderbook_stream():
    streams = "/".join(f"{s.lower()}@depth10@100ms" for s in SYMBOLS)
    url     = f"wss://fstream.binance.com/stream?streams={streams}"
    while True:
        try:
            async with websockets.connect(url, ping_interval=20,
                                          max_size=2**23) as ws:
                print("[WS] OrderBook stream bağlandı")
                async for raw in ws:
                    msg  = json.loads(raw)
                    data = msg.get("data", {})
                    sym  = None
                    for s in SYMBOLS:
                        if s.lower() in msg.get("stream", ""):
                            sym = s; break
                    if not sym: continue
                    st = states[sym]
                    for b in data.get("b", []):
                        p, q = float(b[0]), float(b[1])
                        if q == 0: st.ob_bids.pop(p, None)
                        else:       st.ob_bids[p] = q
                    for a in data.get("a", []):
                        p, q = float(a[0]), float(a[1])
                        if q == 0: st.ob_asks.pop(p, None)
                        else:       st.ob_asks[p] = q
        except Exception as e:
            print(f"[WS OB] {e} — yeniden bağlanıyor")
            await asyncio.sleep(3)


async def liquidation_stream():
    url = "wss://fstream.binance.com/ws/!forceOrder@arr"
    while True:
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                print("[WS] Likidasyon stream bağlandı")
                async for raw in ws:
                    data  = json.loads(raw)
                    order = data.get("o", {})
                    sym   = order.get("s", "")
                    if sym not in states: continue
                    price = float(order.get("ap", order.get("p", 0)))
                    qty   = float(order.get("q", 0))
                    usd   = price * qty
                    side  = order.get("S", "")
                    if usd > 10_000:
                        states[sym].liq_data.append({
                            "ts": time.time(), "side": side, "usd": usd
                        })
                        # ── FİX 2: cleanup_liq metodu kullanılıyor ──
                        states[sym].cleanup_liq()
        except Exception as e:
            print(f"[WS LIQ] {e} — yeniden bağlanıyor")
            await asyncio.sleep(3)


# ─────────────────────────────────────────────────────────────
# TAHMİN DÖNGÜSÜ — her saat PREDICTION_MINUTE geçe (cron open ile uyumlu)
# ─────────────────────────────────────────────────────────────

async def fetch_orderbook_rest(symbol: str):
    """OB snapshot — WebSocket dolmadan önce REST'ten alır."""
    url = "https://fapi.binance.com/fapi/v1/depth"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params={"symbol": symbol, "limit": 20},
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
        st = states[symbol]
        for b in data.get("bids", []):
            st.ob_bids[float(b[0])] = float(b[1])
        for a in data.get("asks", []):
            st.ob_asks[float(a[0])] = float(a[1])
    except Exception as e:
        print(f"[REST OB] {e}")


async def fetch_recent_trades_rest(symbol: str):
    """Son 500 işlem — CVD için REST'ten alır."""
    url = "https://fapi.binance.com/fapi/v1/aggTrades"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params={"symbol": symbol, "limit": 500},
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
        st = states[symbol]
        for t in data:
            price  = float(t["p"])
            qty    = float(t["q"])
            is_buy = not t.get("m", True)
            st.ticks.append(Tick(
                ts     = t["T"] / 1000,
                price  = price,
                qty    = qty,
                usd    = price * qty,
                is_buy = is_buy,
            ))
            if price > 0:
                st.price = price
    except Exception as e:
        print(f"[REST TRADES] {e}")


def _in_quiet_hours() -> bool:
    """Türkiye saatiyle (UTC+3) 23:00–05:00 arası → sessiz saat (CLOB emri yok)."""
    ist_hour = (datetime.now(timezone.utc).hour + 3) % 24
    return ist_hour >= 23 or ist_hour < 5


async def _do_prediction(label: str = ""):
    """Kline + funding + REST snapshot çek, tahmin üret, Telegram'a gönder."""

    quiet = _in_quiet_hours()
    if quiet:
        ist_hour = (datetime.now(timezone.utc).hour + 3) % 24
        print(f"[TAHMİN] Sessiz saatler ({ist_hour:02d}:xx İST) — tahmin gönderilecek, işlem açılmayacak.")

    await check_past_predictions()
    _compute_signal_accuracy()  # [W1] her tahmin öncesi accuracy güncelle

    for sym in SYMBOLS:
        kl = await fetch_klines(sym)
        if kl:
            states[sym].klines_1h = kl
        states[sym].funding_rate = await fetch_funding(sym)
        if not states[sym].ob_bids:
            await fetch_orderbook_rest(sym)
        if not states[sym].ticks:
            await fetch_recent_trades_rest(sym)

    preds = [generate_prediction(states[sym]) for sym in SYMBOLS]
    preds = [p for p in preds if p]

    if not preds:
        print("[TAHMİN] Yeterli veri yok.")
        return

    all_preds    = _load_predictions()
    now_ts       = time.time()
    past_results = [
        p for p in all_preds
        if p.get("checked") and p.get("target_ts", 0) > now_ts - 3600
    ]

    bet_results: dict[str, Optional[dict]] = {}
    for pred in preds:
        if not quiet and pred.direction != "NÖTR":
            bet_results[pred.symbol] = await place_bet(pred)
        else:
            bet_results[pred.symbol] = None
        record_prediction(pred, bet_results[pred.symbol])

    # Bet gönderilmişse CLOB/chain state güncellensin; bakiye anlık yansımayabilir
    if any(v is not None for v in bet_results.values()):
        await asyncio.sleep(6)

    await send_unified_prediction(preds, past_results, bet_results)


async def prediction_loop():
    """
    Her saat PREDICTION_MINUTE (:10) geçe tahmin üret (`src.main open` cron ile uyumlu).

    Köşe case: dakika == PREDICTION_MINUTE iken bir sonraki saatin :10'una gidilir.
    """
    print("[TAHMİN] Bekleniyor — ilk veri dolsun (2 dk)...")
    await asyncio.sleep(120)

    _daily_report_sent_date = None
    PM = PREDICTION_MINUTE

    while True:
        now   = datetime.now(timezone.utc)
        ist_h = (now.hour + 3) % 24
        ist_m = now.minute
        today = now.strftime("%Y-%m-%d")

        # Gece 00:00 İST → günlük rapor
        if ist_h == 0 and ist_m < 5 and _daily_report_sent_date != today:
            try:
                await send_daily_report()
                _daily_report_sent_date = today
                print("[RAPOR] Günlük rapor gönderildi.")
            except Exception as e:
                print(f"[RAPOR HATA] {e}")

        mins = now.minute
        secs = now.second

        if mins < PM:
            wait = (PM - mins) * 60 - secs
            target_h = now.hour
        else:
            wait = (60 - mins + PM) * 60 - secs
            target_h = (now.hour + 1) % 24

        wait = max(30, wait)
        print(f"[TAHMİN] Sonraki gönderim: {target_h:02d}:{PM:02d} UTC ({wait//60} dk {wait%60} sn sonra)")
        await asyncio.sleep(wait)

        try:
            await _do_prediction()
        except Exception as e:
            print(f"[TAHMİN HATA] _do_prediction: {e}")
            import traceback; traceback.print_exc()


# ─────────────────────────────────────────────────────────────
# TERMİNAL DISPLAY
# ─────────────────────────────────────────────────────────────

async def display_loop():
    await asyncio.sleep(10)
    while True:
        try:
            print("\033[H\033[J", end="")
            now = datetime.now().strftime("%H:%M:%S")
            print(f"╔══════════════════════════════════════════════════╗")
            print(f"║  POLYMARKET TAHMİN MOTORU v1.2  │  {now}  ║")
            print(f"╠══════════════════════════════════════════════════╣")
            print(f"║  Sonraki tahmin: her saat :{PREDICTION_MINUTE:02d}              ║")
            print(f"╠══════════════════════════════════════════════════╣")
            for sym in SYMBOLS:
                st   = states[sym]
                cvd5 = st.cvd(300)
                imb  = st.ob_imbalance()
                br   = st.buy_ratio(300)
                liq  = st.liq_bias(600)
                casc = st.liq_cascade()
                name = sym.replace("USDT", "")
                print(f"║  {name:<4}  Fiyat: ${st.price:>12,.2f}  ║")
                print(f"║       CVD5m: {cvd5/1000:>+8.1f}K  OB:%{imb:.0f}  AlışR:%{br:.0f}  ║")
                print(f"║       Liq:{liq:<9} Cascade:{casc:<15}║")
                print(f"║       Tick:{len(st.ticks):>5}  Funding:%{st.funding_rate*100:.3f}         ║")
            if _signal_accuracy:
                print(f"╠══════════════════════════════════════════════════╣")
                print(f"║  Sinyal Accuracy (son 48h):                      ║")
                for sig, (ok, total) in sorted(_signal_accuracy.items()):
                    rate = ok / total * 100
                    bar  = "█" * int(rate / 10) + "░" * (10 - int(rate / 10))
                    print(f"║  {sig:<14} {bar} %{rate:.0f} ({ok}/{total})  ║")
            print(f"╚══════════════════════════════════════════════════╝")
            print("  Ctrl+C ile durdur")
        except Exception as e:
            print(f"[DISPLAY HATA] {e}")
        await asyncio.sleep(5)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

async def main():
    print("=" * 52)
    print("  POLYMARKET TAHMİN MOTORU v1.2 başlatılıyor...")
    print(f"  Semboller: {', '.join(SYMBOLS)}")
    print(f"  Tahmin dakikası: :{PREDICTION_MINUTE:02d}")
    print(f"  Telegram: {'✅' if TELEGRAM_TOKEN else '❌ .env dosyasını doldur'}")
    print("=" * 52)

    await send_telegram(
        f"🔮 <b>Polymarket Tahmin Motoru v1.2 Başladı</b>\n"
        f"📊 ETH + SOL · 1 Saatlik Tahminler\n"
        f"🧠 Dinamik ağırlıklar + Cascade + Korelasyon aktif\n"
        f"⏰ Her saat :{PREDICTION_MINUTE:02d}'de bildirim gelecek"
    )

    await asyncio.gather(
        trade_stream(),
        orderbook_stream(),
        liquidation_stream(),
        prediction_loop(),
        display_loop(),
    )


async def main_loop():
    """main()'i sonsuz döngüde çalıştır — crash sonrası otomatik yeniden başlat."""
    while True:
        try:
            await main()
        except Exception as e:
            print(f"[MAIN HATA] {e} — 60 saniye sonra yeniden başlatılıyor...")
            import traceback; traceback.print_exc()
            await asyncio.sleep(60)


if __name__ == "__main__":
    import sys
    if "--now" in sys.argv:
        async def _run_now():
            print("🔮 Manuel tahmin başlatıldı...")
            _compute_signal_accuracy()  # [W1]
            for sym in SYMBOLS:
                await fetch_orderbook_rest(sym)
                await fetch_recent_trades_rest(sym)
            await _do_prediction("(Manuel)")
        asyncio.run(_run_now())
    elif "--daily" in sys.argv:
        asyncio.run(send_daily_report())
    else:
        try:
            asyncio.run(main_loop())
        except KeyboardInterrupt:
            print("\nTahmin motoru durduruldu.")