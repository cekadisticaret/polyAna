"""
╔══════════════════════════════════════════════════════════════════╗
║  POLYMARKET TAHMİN MOTORU v1.0  [PASİF]                         ║
║  Aktif: polymarket-main/src/analyzer/poly_predictor.py           ║
║                                                                  ║
║  Mantık:                                                         ║
║  Her saat başı BTC ve ETH için şunu tahmin eder:                 ║
║  "1 saat sonra fiyat şu anki seviyenin üzerinde mi altında mı?" ║
║                                                                  ║
║  Kullanılan sinyaller:                                           ║
║  1. CVD momentum (alış/satış baskısı)                           ║
║  2. Order book imbalance                                         ║
║  3. Likidasyon bias                                              ║
║  4. Piyasa rejimi (ADX + Choppiness)                            ║
║  5. RSI + MACD momentum                                          ║
║  6. Funding rate yönü                                            ║
║  7. Volatilite (ATR oranı)                                       ║
║                                                                  ║
║  Çalıştır: python poly_predictor.py                              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
raise SystemExit("poly_predictor.py [KÖK] pasif — polymarket-main/src/analyzer/poly_predictor.py kullan.")

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
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv
import os
import math

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT",  "")

# ── Polymarket ──
POLY_PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY", "")
POLY_FUNDER      = os.getenv("POLY_FUNDER", "")
POLY_API_KEY     = os.getenv("POLY_API_KEY", "")
POLY_API_SECRET  = os.getenv("POLY_API_SECRET", "")
POLY_API_PASS    = os.getenv("POLY_API_PASSPHRASE", "")
BET_SIZE_USDC      = float(os.getenv("POLY_BET_SIZE", "5"))
PREDICTIONS_FILE   = os.path.join(os.path.dirname(__file__), "poly_predictions.json")
PAPER_BETS_FILE    = os.path.join(os.path.dirname(__file__), "poly_paper_bets.json")
PAPER_BET_SIZE     = float(os.getenv("POLY_BET_SIZE", "5"))
PAPER_START_BAL    = 300.0
BET_DRY_RUN      = os.getenv("POLY_DRY_RUN", "true").lower() != "false"
CLOB_HOST        = "https://clob.polymarket.com"
GAMMA_HOST       = "https://gamma-api.polymarket.com"

SYMBOLS = ["SOLUSDT", "ETHUSDT"]

# Bahis girişi — SOL ve ETH için aynı kurallar (bull_pct / bear_pct, 0–100)
MIN_WIN_DIRECTION_PCT = 50.0   # kazanan yön bunun üstünde olmalı
MAX_BALANCED_SIDE_PCT = 35.0   # ▲ ve ▼ ikisi de bunun altındaysa girilmez

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
    bull_pct:      float = 0.0   # % bull puan
    bear_pct:      float = 0.0   # % bear puan
    h1_high:       float = 0.0
    h1_low:        float = 0.0
    key_level:     float = 0.0   # en yakın yuvarlak seviye


class SymbolState:
    def __init__(self, symbol: str):
        self.symbol    = symbol
        self.ticks: deque[Tick] = deque(maxlen=10000)
        self.price     = 0.0
        self.ob_bids   = {}
        self.ob_asks   = {}
        self.liq_data: list[dict] = []
        self.klines_1h: list[dict] = []
        self.funding_rate = 0.0

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
        bid_v = sum(p * q for p, q in sorted(self.ob_bids.items(), reverse=True)[:levels])
        ask_v = sum(p * q for p, q in sorted(self.ob_asks.items())[:levels])
        total = bid_v + ask_v
        return (bid_v / total * 100) if total > 0 else 50.0

    # Likidasyon bias
    def liq_bias(self, seconds: int = 600) -> str:
        cutoff = time.time() - seconds
        long_liq = short_liq = 0.0
        for l in self.liq_data:
            if l["ts"] < cutoff: continue
            if l["side"] == "BUY":  long_liq  += l["usd"]
            else:                    short_liq += l["usd"]
        if short_liq > long_liq * 1.5 and short_liq > 50_000:
            return "BULL"   # Short'lar temizlendi → yukarı
        if long_liq > short_liq * 1.5 and long_liq > 50_000:
            return "BEAR"   # Long'lar temizlendi → aşağı
        return "NEUTRAL"


states = {sym: SymbolState(sym) for sym in SYMBOLS}


# ─────────────────────────────────────────────────────────────
# TAHMİN MOTORU
# ─────────────────────────────────────────────────────────────

def _ema(values, period):
    if len(values) < period:
        return [0.0] * len(values)
    k = 2.0 / (period + 1)
    r = [0.0] * len(values)
    r[period - 1] = sum(values[:period]) / period
    for i in range(period, len(values)):
        r[i] = values[i] * k + r[i-1] * (1 - k)
    return r

def _rsi(closes, period=14):
    if len(closes) < period + 1: return 50.0
    g = l = 0.0
    for i in range(1, period + 1):
        d = closes[-period-1+i] - closes[-period-2+i]
        if d > 0: g += d
        else:      l -= d
    ag, al = g/period, l/period
    if al == 0: return 100.0
    return 100 - 100/(1 + ag/al)

def _macd_hist(closes):
    if len(closes) < 35: return 0.0
    ef = _ema(closes, 12)
    es = _ema(closes, 26)
    ml = [ef[i] - es[i] for i in range(len(closes))]
    sig = _ema(ml[25:], 9)
    return ml[-1] - (sig[-1] if sig else 0)

def _adx(highs, lows, closes, period=14):
    n = len(closes)
    if n < period * 2: return 0.0, 0.0, 0.0
    tr_l = pdm_l = ndm_l = [0.0]
    for i in range(1, n):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        up   = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        tr_l  = tr_l  + [tr]
        pdm_l = pdm_l + [up   if up > down and up > 0   else 0.0]
        ndm_l = ndm_l + [down if down > up and down > 0 else 0.0]

    def ws(d, p):
        r = [0.0]*len(d)
        if len(d) <= p: return r
        r[p] = sum(d[1:p+1])
        for i in range(p+1, len(d)):
            r[i] = r[i-1] - r[i-1]/p + d[i]
        return r

    at = ws(tr_l, period); pm = ws(pdm_l, period); nm = ws(ndm_l, period)
    pdi = [100*pm[i]/at[i] if at[i]>0 else 0 for i in range(n)]
    ndi = [100*nm[i]/at[i] if at[i]>0 else 0 for i in range(n)]
    dx  = [100*abs(pdi[i]-ndi[i])/(pdi[i]+ndi[i]) if (pdi[i]+ndi[i])>0 else 0 for i in range(n)]
    adx_s = ws(dx, period)
    return round(adx_s[-1],2), round(pdi[-1],2), round(ndi[-1],2)

def _chop(highs, lows, closes, period=14):
    if len(closes) < period+1: return 50.0
    wh = max(highs[-period:]); wl = min(lows[-period:])
    if wh-wl == 0: return 50.0
    atr_sum = sum(max(highs[-period+i]-lows[-period+i],
                      abs(highs[-period+i]-closes[-period+i-1]),
                      abs(lows[-period+i]-closes[-period+i-1]))
                  for i in range(period))
    return round(100*math.log10(atr_sum/(wh-wl))/math.log10(period), 2)


def generate_prediction(state: SymbolState) -> Optional[Prediction]:
    """
    Tüm sinyalleri birleştir → 1 saatlik yön tahmini üret
    """
    if state.price <= 0:
        return None

    signals  = {}
    bull_pts = 0
    bear_pts = 0
    total_w  = 0

    # ── 1. CVD 5dk (ağırlık: 3) ──
    cvd5 = state.cvd(300)
    w = 3
    if cvd5 > 0:
        bull_pts += w
        signals["cvd_5m"] = f"🟢 CVD 5dk: +${cvd5/1000:.1f}K (alış baskısı)"
    else:
        bear_pts += w
        signals["cvd_5m"] = f"🔴 CVD 5dk: ${cvd5/1000:.1f}K (satış baskısı)"
    total_w += w

    # ── 2. CVD 30dk (ağırlık: 2) ──
    cvd30 = state.cvd(1800)
    w = 2
    if cvd30 > 0:
        bull_pts += w
        signals["cvd_30m"] = f"🟢 CVD 30dk: +${cvd30/1000:.1f}K"
    else:
        bear_pts += w
        signals["cvd_30m"] = f"🔴 CVD 30dk: ${cvd30/1000:.1f}K"
    total_w += w

    # ── 3. Order Book İmbalance (ağırlık: 2) ──
    imb = state.ob_imbalance()
    w = 2
    if imb >= 62:
        bull_pts += w
        signals["ob_imb"] = f"🟢 OB İmbalance: %{imb:.1f} (alış ağır)"
    elif imb <= 38:
        bear_pts += w
        signals["ob_imb"] = f"🔴 OB İmbalance: %{imb:.1f} (satış ağır)"
    else:
        signals["ob_imb"] = f"⚪ OB İmbalance: %{imb:.1f} (nötr)"
    total_w += w

    # ── 4. Büyük işlem yönü (ağırlık: 3) ──
    lt_bias = state.large_trade_bias(100_000, 300)
    w = 3
    if lt_bias == "BUY":
        bull_pts += w
        signals["large_trades"] = f"🟢 Büyük işlemler: ALIŞ yönü"
    elif lt_bias == "SELL":
        bear_pts += w
        signals["large_trades"] = f"🔴 Büyük işlemler: SATIŞ yönü"
    else:
        signals["large_trades"] = f"⚪ Büyük işlemler: nötr"
    total_w += w

    # ── 5. Likidasyon bias (ağırlık: 2) ──
    liq = state.liq_bias(600)
    w = 2
    if liq == "BULL":
        bull_pts += w
        signals["liquidation"] = f"🟢 Likidasyon: short'lar temizlendi"
    elif liq == "BEAR":
        bear_pts += w
        signals["liquidation"] = f"🔴 Likidasyon: long'lar temizlendi"
    else:
        signals["liquidation"] = f"⚪ Likidasyon: nötr"
    total_w += w

    # ── 6. Alış oranı (ağırlık: 1) ──
    br = state.buy_ratio(300)
    w = 1
    if br >= 60:
        bull_pts += w
        signals["buy_ratio"] = f"🟢 Alış oranı: %{br:.0f}"
    elif br <= 40:
        bear_pts += w
        signals["buy_ratio"] = f"🔴 Alış oranı: %{br:.0f}"
    else:
        signals["buy_ratio"] = f"⚪ Alış oranı: %{br:.0f}"
    total_w += w

    # ── 7. Kline bazlı teknik (1H) ──
    kl = state.klines_1h
    if len(kl) >= 55:
        c  = [k["close"]  for k in kl]
        h  = [k["high"]   for k in kl]
        l  = [k["low"]    for k in kl]
        v  = [k["volume"] for k in kl]

        rsi_v   = _rsi(c)
        macd_h  = _macd_hist(c)
        ema9    = _ema(c, 9)
        ema21   = _ema(c, 21)
        ema50   = _ema(c, 50)
        adx, pdi, ndi = _adx(h, l, c)
        chop    = _chop(h, l, c)

        # RSI (ağırlık: 2)
        w = 2
        if 50 < rsi_v < 70:
            bull_pts += w
            signals["rsi"] = f"🟢 RSI: {rsi_v:.0f} (momentum)"
        elif 30 < rsi_v < 50:
            bear_pts += w
            signals["rsi"] = f"🔴 RSI: {rsi_v:.0f} (zayıf)"
        elif rsi_v >= 70:
            signals["rsi"] = f"⚠️ RSI: {rsi_v:.0f} (aşırı alım)"
        else:
            signals["rsi"] = f"⚠️ RSI: {rsi_v:.0f} (aşırı satım — dönüş olabilir)"
        total_w += w

        # MACD (ağırlık: 2)
        w = 2
        if macd_h > 0:
            bull_pts += w
            signals["macd"] = f"🟢 MACD: pozitif histogram"
        else:
            bear_pts += w
            signals["macd"] = f"🔴 MACD: negatif histogram"
        total_w += w

        # EMA düzeni (ağırlık: 2)
        w = 2
        ema_bull = ema9[-1] > ema21[-1] > ema50[-1]
        ema_bear = ema9[-1] < ema21[-1] < ema50[-1]
        if ema_bull:
            bull_pts += w
            signals["ema"] = f"🟢 EMA: 9↑21↑50 (yükseliş dizisi)"
        elif ema_bear:
            bear_pts += w
            signals["ema"] = f"🔴 EMA: 9↓21↓50 (düşüş dizisi)"
        else:
            signals["ema"] = f"⚪ EMA: karışık"
        total_w += w

        # ADX + Choppiness (ağırlık: 1)
        w = 1
        if adx > 25 and chop < 50 and pdi > ndi:
            bull_pts += w
            signals["regime"] = f"🟢 Rejim: trend yukarı (ADX:{adx:.0f} Chop:{chop:.0f})"
        elif adx > 25 and chop < 50 and ndi > pdi:
            bear_pts += w
            signals["regime"] = f"🔴 Rejim: trend aşağı (ADX:{adx:.0f} Chop:{chop:.0f})"
        elif chop > 60:
            signals["regime"] = f"⚪ Rejim: ranging (Chop:{chop:.0f}) — tahmin güvenilirliği düşük"
        else:
            signals["regime"] = f"⚪ Rejim: belirsiz (ADX:{adx:.0f})"
        total_w += w

        # Funding rate (ağırlık: 1)
        w = 1
        fr = state.funding_rate
        if fr > 0.0005:
            bear_pts += w
            signals["funding"] = f"⚠️ Funding: %{fr*100:.3f} (yüksek — long ödüyor)"
        elif fr < -0.0003:
            bull_pts += w
            signals["funding"] = f"🟢 Funding: %{fr*100:.3f} (negatif — short ödüyor)"
        else:
            signals["funding"] = f"⚪ Funding: %{fr*100:.3f} (normal)"
        total_w += w

        # ── 8. Hacim spike — 1h (ağırlık: 2) [Pine v6.0] ──
        w = 2
        vol_avg_20 = sum(v[-21:-1]) / 20 if len(v) >= 21 else 0.0
        if vol_avg_20 > 0:
            vol_ratio_1h = v[-1] / vol_avg_20
            last_bull = c[-1] > kl[-1]["open"]
            if vol_ratio_1h >= 1.2:
                if last_bull:
                    bull_pts += w
                    signals["vol_spike"] = f"🟢 Hacim spike: ×{vol_ratio_1h:.1f} (yükseliş mumu)"
                else:
                    bear_pts += w
                    signals["vol_spike"] = f"🔴 Hacim spike: ×{vol_ratio_1h:.1f} (düşüş mumu)"
            else:
                signals["vol_spike"] = f"⚪ Hacim: ×{vol_ratio_1h:.1f} (normal)"
        else:
            signals["vol_spike"] = f"⚪ Hacim: veri yok"
        total_w += w

        # ── 9. EMA50 uzaklık filtresi (ağırlık: 2) [Pine v6.0] ──
        # Fiyat EMA50'ye yakınsa güvenilir; çok uzaksa olası mean reversion
        w = 2
        price_dist_pct = (state.price - ema50[-1]) / ema50[-1] * 100 if ema50[-1] > 0 else 0.0
        abs_dist = abs(price_dist_pct)
        if abs_dist > 5.0:
            # Overextended — dönüş riski; zıt yönde puan ver
            if price_dist_pct > 0:
                bear_pts += w
                signals["ema_dist"] = f"⚠️ EMA uzaklık: +%{price_dist_pct:.1f} (aşırı uzak yukarı — dönüş riski)"
            else:
                bull_pts += w
                signals["ema_dist"] = f"⚠️ EMA uzaklık: %{price_dist_pct:.1f} (aşırı uzak aşağı — dönüş riski)"
        elif price_dist_pct > 0:
            bull_pts += w
            signals["ema_dist"] = f"🟢 EMA uzaklık: +%{price_dist_pct:.1f} (EMA üstünde, normal mesafe)"
        else:
            bear_pts += w
            signals["ema_dist"] = f"🔴 EMA uzaklık: %{price_dist_pct:.1f} (EMA altında)"
        total_w += w

    # ── KARAR ──
    if total_w == 0:
        return None

    bull_pct = bull_pts / total_w
    bear_pct = bear_pts / total_w

    # Yön — eşitlik durumunda mevcut trendle aynı yön (varsayılan YUKARI)
    if bull_pts >= bear_pts:
        direction = "YUKARI"
        raw_prob  = bull_pct if bull_pts > bear_pts else 0.5
    else:
        direction = "AŞAĞI"
        raw_prob  = bear_pct

    # Olasılık sigmoid ile yumuşat (0.5-0.85 arasında tut)
    prob = 0.5 + (raw_prob - 0.5) * 0.7
    prob = max(0.50, min(0.85, prob))

    # Güven seviyesi — NÖTR kaldırıldı, yön her zaman YUKARI veya AŞAĞI
    gap = abs(bull_pts - bear_pts)
    if gap >= total_w * 0.20:       # ~5/25 puan fark yeterli
        confidence = "YÜKSEK"
    elif gap >= total_w * 0.10:     # ~2.5/25 puan fark
        confidence = "ORTA"
    else:
        confidence = "DÜŞÜK"

    # Ranging market — Chop > 68 ise sadece YÜKSEK → ORTA'ya indir, ORTA'ya dokunma
    kl_check = state.klines_1h
    if len(kl_check) >= 55:
        _h = [k["high"] for k in kl_check[-14:]]
        _l = [k["low"]  for k in kl_check[-14:]]
        _c = [k["close"] for k in kl_check[-14:]]
        _atr14 = sum(max(_h[i]-_l[i], abs(_h[i]-_c[i-1]), abs(_l[i]-_c[i-1]))
                     for i in range(1, len(_h)))
        _hl14  = max(_h) - min(_l)
        _chop_check = 100 * _atr14 / _hl14 if _hl14 > 0 else 100
        if _chop_check > 68 and confidence == "YÜKSEK":
            confidence = "ORTA"

    # Hedef saat IST
    now_utc     = datetime.now(timezone.utc)
    target_ist  = (now_utc.hour + 1 + 3) % 24
    target_time = f"{target_ist:02d}:00 İST"

    # 1h high/low (son 3 bar)
    kl      = state.klines_1h
    h1_high = max(k["high"] for k in kl[-3:]) if len(kl) >= 3 else 0.0
    h1_low  = min(k["low"]  for k in kl[-3:]) if len(kl) >= 3 else 0.0

    # En yakın yuvarlak seviye
    p = state.price
    step      = 500 if p > 10_000 else 100 if p > 1_000 else 10 if p > 100 else 1
    key_level = round(round(p / step) * step, 2)

    reasoning = (
        f"Boğa puanı: {bull_pts}/{total_w} | "
        f"Ayı puanı: {bear_pts}/{total_w} | "
        f"Fark: {gap}"
    )

    return Prediction(
        symbol        = state.symbol,
        ts            = time.time(),
        current_price = state.price,
        target_time   = target_time,
        direction     = direction,
        probability   = prob,
        confidence    = confidence,
        signals       = signals,
        reasoning     = reasoning,
        bull_pct      = round(bull_pts / total_w * 100) if total_w else 50,
        bear_pct      = round(bear_pts / total_w * 100) if total_w else 50,
        h1_high       = h1_high,
        h1_low        = h1_low,
        key_level     = key_level,
    )


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
    """Tek coin için detay bloğu üretir."""
    sym   = pred.symbol.replace("USDT", "")
    icon  = "◎" if sym == "SOL" else "Ξ" if sym == "ETH" else sym
    d_ico = "📉" if pred.direction == "AŞAĞI" else "📈" if pred.direction == "YUKARI" else "➡️"
    conf_ico = "🔥" if pred.confidence == "YÜKSEK" else "⚡" if pred.confidence == "ORTA" else "💤"

    p = pred.current_price

    return (
        f"{icon} <b>{sym}</b>  ${p:,.2f}  {d_ico} <b>{pred.direction}</b>\n"
        f"▲ {pred.bull_pct}%  |  ▼ {pred.bear_pct}%  |  {conf_ico} {pred.confidence}"
    )


async def send_prediction(pred: Prediction):
    """Tek tahmin — birleşik mesaj _do_prediction'da oluşturuluyor, bu sadece bet tetikler."""
    bet_result = None
    if pred.confidence == "YÜKSEK" and pred.direction != "NÖTR":
        bet_result = await place_bet(pred)
    sym_short = pred.symbol.replace("USDT", "")
    print(f"[TAHMİN] {sym_short} → {pred.direction} %{pred.probability*100:.0f} "
          f"({pred.confidence}) | Bahis: {bet_result.get('status','—') if bet_result else '—'}")
    return bet_result


async def _fetch_poly_portfolio() -> str:
    """Gerçek Polymarket bakiyesini çeker; hata/veri yoksa boş string döner."""
    try:
        import sys as _sys
        _pm = os.path.join(os.path.dirname(os.path.abspath(__file__)), "polymarket-main")
        if _pm not in _sys.path:
            _sys.path.insert(0, _pm)
        from src.trading.portfolio_snapshot import portfolio_snapshot_values
        loop = asyncio.get_event_loop()
        snap = await loop.run_in_executor(None, portfolio_snapshot_values)
        col   = snap.get("collateral_usdc")
        pos   = snap.get("positions_mark_usdc")
        npos  = snap.get("open_positions_count") or 0
        total = snap.get("portfolio_total_usdc")
        if col is None and pos is None:
            return ""
        lines = ["─────────────────────", "💎 <b>Polymarket Bakiye</b>"]
        if col is not None:
            lines.append(f"💵 Kullanılabilir: <b>${col:.2f} USDC</b>")
        if pos is not None:
            lines.append(f"📊 Açık pozisyonlar: <b>${pos:.2f}</b> ({npos} adet)")
        if total is not None:
            lines.append(f"💰 Toplam: <b>${total:.2f} USDC</b>")
        return "\n".join(lines) + "\n"
    except Exception as e:
        print(f"[BAKIYE HATA] {e}")
        return ""


async def send_unified_prediction(preds: list, past_results: list, paper_results: dict = None):
    """BTC + ETH tahminlerini tek mesajda gönderir."""
    if not preds:
        return

    target_time = preds[0].target_time

    # ── Geçen saat sonucu ──
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
            s_ic = "◎" if sym == "SOL" else "Ξ"
            ep   = r.get("price", 0)
            ap   = r.get("actual_price", 0)
            diff = ap - ep
            prev_lines.append(
                f"{icon} {s_ic} {sym}  ${ep:,.2f} → ${ap:,.2f}  "
                f"({'+' if diff>=0 else ''}{diff:,.2f})  Tahmin: {r['direction']}"
            )
        score = f"{len(correct)}/{len(past_results)} doğru"
        prev_block = (
            f"─────────────────────\n"
            f"📋 <b>Geçen saat sonucu: {score}</b>\n"
            + "\n".join(prev_lines) + "\n"
        )

    # ── Coin blokları ──
    coin_blocks = []
    for pred in preds:
        coin_blocks.append(_build_coin_block(pred))

    poly_block = await _fetch_poly_portfolio()

    msg = (
        f"🎯 <b>POLYX2 - aiproject3</b>\n"
        f"⏰ Hedef: <b>{target_time}</b>\n"
        f"{prev_block}"
        f"─────────────────────\n"
        + "\n─────────────────────\n".join(coin_blocks)
        + "\n"
        + (poly_block if poly_block else "")
        + f"─────────────────────\n"
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


# ── Paper Trading (sanal cüzdan) ──────────────────────────────

def _load_paper() -> dict:
    if os.path.exists(PAPER_BETS_FILE):
        try:
            with open(PAPER_BETS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": PAPER_START_BAL, "bets": []}

def _save_paper(data: dict):
    with open(PAPER_BETS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

async def record_paper_bet(pred: "Prediction", target_ts: float) -> Optional[dict]:
    """
    Gerçek Polymarket odds'larıyla sanal bahis kaydeder.
    Başarılı olursa bet dict döner, aksi hâlde None.
    """
    if pred.direction == "NÖTR":
        return None

    market = await find_market(pred.symbol, pred.direction, pred.current_price)
    if not market:
        print(f"[PAPER] Market bulunamadı — bahis kaydedilmedi")
        return None

    bet_price = market["bet_price"]
    payout    = round(PAPER_BET_SIZE / bet_price, 2)
    profit    = round(payout - PAPER_BET_SIZE, 2)

    data    = _load_paper()
    balance = data["balance"]

    if balance < PAPER_BET_SIZE:
        print(f"[PAPER] Yetersiz bakiye (${balance:.2f}) — bahis atlandı")
        return None

    data["balance"] = round(balance - PAPER_BET_SIZE, 2)

    bet = {
        "symbol":      pred.symbol,
        "direction":   pred.direction,
        "confidence":  pred.confidence,
        "entry_price": pred.current_price,
        "bet_amount":  PAPER_BET_SIZE,
        "bet_price":   bet_price,
        "payout_win":  payout,
        "profit_win":  profit,
        "question":    market["question"],
        "target_ts":   target_ts,
        "sent_ts":     time.time(),
        "settled":     False,
        "won":         None,
        "pnl":         None,
    }
    data["bets"].append(bet)
    _save_paper(data)
    print(f"[PAPER] Bahis kaydedildi: {pred.symbol} {pred.direction} "
          f"${PAPER_BET_SIZE} → kazanırsak ${payout:.2f} | odds:{bet_price:.2f} | "
          f"Bakiye: ${data['balance']:.2f}")
    return {"placed": True, "payout": payout, "odds": bet_price, "balance": data["balance"]}

def settle_paper_bets(preds: list):
    """check_past_predictions sonrası çözülen bahisleri kapat, bakiyeyi güncelle."""
    data = _load_paper()
    updated = False

    for bet in data["bets"]:
        if bet["settled"]:
            continue
        # Eşleşen tahmini bul
        match = next(
            (p for p in preds
             if p.get("checked")
             and p["symbol"] == bet["symbol"]
             and abs(p["target_ts"] - bet["target_ts"]) < 60),
            None
        )
        if not match:
            continue

        won = match.get("correct", False)
        if won:
            pnl = bet["profit_win"]
            data["balance"] = round(data["balance"] + bet["payout_win"], 2)
        else:
            pnl = -bet["bet_amount"]

        bet["settled"] = True
        bet["won"]     = won
        bet["pnl"]     = pnl
        updated = True
        icon = "✅" if won else "❌"
        print(f"[PAPER] {icon} {bet['symbol']} {bet['direction']} "
              f"{'KAZANDI' if won else 'KAYBETTİ'} | "
              f"PnL: ${pnl:+.2f} | Bakiye: ${data['balance']:.2f}")

    if updated:
        _save_paper(data)

def paper_summary() -> str:
    """Günlük rapora eklenecek sanal cüzdan özeti."""
    data  = _load_paper()
    bal   = data["balance"]
    bets  = data["bets"]
    total_bets    = len(bets)
    settled       = [b for b in bets if b["settled"]]
    won_bets      = [b for b in settled if b["won"]]
    total_pnl     = sum(b["pnl"] for b in settled)
    open_bets     = [b for b in bets if not b["settled"]]
    open_exposure = sum(b["bet_amount"] for b in open_bets)

    lines = [
        f"💼 <b>Sanal Cüzdan</b>",
        f"Bakiye      : <b>${bal:.2f}</b>  (başlangıç: $300)",
        f"Toplam PnL  : <b>${total_pnl:+.2f}</b>",
        f"Bahisler    : {len(won_bets)}/{len(settled)} kazandı",
        f"Açık pozisyon: {len(open_bets)} bahis (${open_exposure:.0f} risk)",
    ]
    if open_bets:
        lines.append("Açık bahisler:")
        for b in open_bets[-3:]:
            sym = b["symbol"].replace("USDT","")
            lines.append(f"  • {sym} {b['direction']} ${b['bet_amount']} → ${b['payout_win']:.2f}")
    return "\n".join(lines)


async def record_prediction(pred: "Prediction") -> Optional[dict]:
    """Tahmini dosyaya kaydet ve sanal Polymarket bahsi aç. Paper bet sonucunu döner."""
    now      = datetime.now(timezone.utc)
    target_h = now.hour + 1
    target_ts = now.replace(minute=0, second=0, microsecond=0).timestamp() + 3600

    # DÜŞÜK güven → kaydetme, bahis açma
    if pred.confidence == "DÜŞÜK":
        reason = f"güven düşük (DÜŞÜK)"
        print(f"[ATLANDI] {pred.symbol} {pred.direction} → {reason}")
        return {"placed": False, "reason": reason}

    bp = float(pred.bull_pct)
    br = float(pred.bear_pct)
    if bp <= MAX_BALANCED_SIDE_PCT and br <= MAX_BALANCED_SIDE_PCT:
        reason = f"sinyal dengeli (▲%{bp:.0f} ▼%{br:.0f})"
        print(f"[ATLANDI] {pred.symbol} {pred.direction} → {reason}")
        return {"placed": False, "reason": reason}
    win_pct = bp if pred.direction == "YUKARI" else br
    if win_pct <= MIN_WIN_DIRECTION_PCT:
        reason = f"kazanan yön %{win_pct:.0f} (min %{MIN_WIN_DIRECTION_PCT:.0f})"
        print(f"[ATLANDI] {pred.symbol} {pred.direction} → {reason}")
        return {"placed": False, "reason": reason}

    preds = _load_predictions()
    preds.append({
        "symbol":    pred.symbol,
        "direction": pred.direction,
        "price":     pred.current_price,
        "confidence":pred.confidence,
        "target_ts": target_ts,
        "sent_ts":   now.timestamp(),
        "checked":   False,
    })
    _save_predictions(preds)
    print(f"[KAYIT] {pred.symbol} {pred.direction} → hedef {target_h:02d}:00 UTC kaydedildi")

    # Sanal bahis — gerçek Polymarket odds'larıyla
    return await record_paper_bet(pred, target_ts)


async def fetch_price_at(symbol: str, target_ts: float) -> float:
    """target_ts anındaki 1h kapanış fiyatını döner."""
    start_ms = int(target_ts * 1000) - 3600_000   # 1 saat öncesi
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
            return float(data[-1][4])   # close fiyatı
    except Exception as e:
        print(f"[PRICE_AT] {e}")
    return 0.0


async def check_past_predictions():
    """
    target_ts geçmiş, henüz kontrol edilmemiş tahminleri doğrula.
    Her biri için sonuç bildirimi gönder.
    """
    now   = time.time()
    preds = _load_predictions()
    # Artık aktif olmayan semboller varsa temizle (örn. BTC → SOL geçişi)
    preds = [p for p in preds if p.get("symbol") in SYMBOLS]
    updated = False

    for p in preds:
        if p.get("checked"):
            continue
        if p["target_ts"] > now:
            continue   # henüz hedef saat gelmemiş

        symbol    = p["symbol"]
        direction = p["direction"]
        entry_price = p["price"]
        target_ts   = p["target_ts"]

        actual_price = await fetch_price_at(symbol, target_ts)
        if actual_price <= 0:
            continue   # veri gelmedi, bekle

        # Gerçek yön — eşik altında bile en yakın yönü kullan
        change_pct = (actual_price - entry_price) / entry_price * 100
        if change_pct >= 0:
            actual_dir = "YUKARI"
        else:
            actual_dir = "AŞAĞI"

        # Tahmin doğru mu?
        correct = (direction == actual_dir)

        # Hedef saat İST
        target_dt  = datetime.fromtimestamp(target_ts, tz=timezone.utc)
        target_ist = (target_dt.hour + 3) % 24
        sent_dt    = datetime.fromtimestamp(p["sent_ts"], tz=timezone.utc)
        sent_ist   = (sent_dt.hour + 3) % 24

        sym_short  = symbol.replace("USDT", "")
        result_emoji = "✅" if correct else "❌"
        dir_emoji    = "📈" if actual_dir == "YUKARI" else "📉"
        pred_emoji   = "📈" if direction  == "YUKARI" else "📉"
        conf_emoji   = {"YÜKSEK": "💎", "ORTA": "✅", "DÜŞÜK": "⚠️"}.get(p["confidence"], "")

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
        # Çözülen tahminlere göre sanal bahisleri kapat
        settle_paper_bets(preds)


# ─────────────────────────────────────────────────────────────
# POLYMARKET BAHİS
# ─────────────────────────────────────────────────────────────

async def send_daily_report():
    """Son 24 saatin tahminlerini saat-saat kaydeder, Telegram'a gönderir."""
    cutoff = time.time() - 86400
    all_preds = _load_predictions()
    # Checked ve unchecked — hepsini dahil et (bazıları henüz kapanmamış olabilir)
    recent = [p for p in all_preds if p.get("target_ts", 0) >= cutoff and p.get("symbol") in SYMBOLS]

    now_utc = datetime.now(timezone.utc)
    now_ist_h = (now_utc.hour + 3) % 24
    date_str  = now_utc.strftime("%d.%m.%Y")

    if not recent:
        await send_telegram(
            f"📊 <b>POLYX2 — Günlük Rapor</b>\n"
            f"🗓 {date_str}  |  16:00 İST\n\n"
            "Son 24 saatte tahmin yok."
        )
        return

    from collections import defaultdict
    by_sym = defaultdict(dict)  # sym -> {ist_hour: pred}
    for p in recent:
        # target_ts = tahmin edilen SAAT (bir sonraki tam saat)
        # tahmin yapıldığı saat = target_ts - 3600
        pred_ist_h = int((p["target_ts"] - 3600 + 3 * 3600) % 86400 // 3600)
        key = (p["symbol"], pred_ist_h)
        # Aynı saat için son tahmin geçerli
        if key not in by_sym or p.get("target_ts", 0) > by_sym[key].get("target_ts", 0):
            by_sym[key] = p

    # Saatleri sırala
    all_hours = sorted({h for (_, h) in by_sym.keys()})

    # ── Özet (per coin) ──
    lines = [
        f"📊 <b>POLYX2 — Günlük Rapor</b>",
        f"🗓 {date_str}  |  16:00 İST",
        f"━━━━━━━━━━━━━━━━━━━━",
    ]

    total_ok = total_all = 0
    for sym in ["SOLUSDT", "ETHUSDT"]:
        items = [v for (s, h), v in by_sym.items() if s == sym]
        if not items:
            continue
        checked = [i for i in items if i.get("checked")]
        ok   = sum(1 for i in checked if i.get("correct"))
        fail = len(checked) - ok
        n    = len(checked)
        total_ok  += ok
        total_all += n
        rate  = ok / n * 100 if n else 0
        icon  = "◎" if "SOL" in sym else "Ξ"
        medal = "🥇" if rate >= 70 else "✅" if rate >= 50 else "⚠️"
        name  = sym.replace("USDT", "")
        dirs_ok = {"YUKARI": 0, "ASAGI": 0}
        dirs_fail = {"YUKARI": 0, "ASAGI": 0}
        for i in checked:
            d = "YUKARI" if i.get("direction") == "YUKARI" else "ASAGI"
            if i.get("correct"):
                dirs_ok[d] += 1
            else:
                dirs_fail[d] += 1
        lines.append(
            f"{icon} <b>{name}</b>  {medal}  {ok}/{n} (%{rate:.0f})\n"
            f"   📈 Yukarı: {dirs_ok['YUKARI']}✅ {dirs_fail['YUKARI']}❌  "
            f"│  📉 Aşağı: {dirs_ok['ASAGI']}✅ {dirs_fail['ASAGI']}❌"
        )

    overall = total_ok / total_all * 100 if total_all else 0
    medal_g = "🥇" if overall >= 70 else "✅" if overall >= 50 else "⚠️"
    lines += [
        f"━━━━━━━━━━━━━━━━━━━━",
        f"{medal_g} <b>Genel: {total_ok}/{total_all} (%{overall:.0f})</b>",
    ]

    # ── Saat Saat Tablo ──
    lines.append(f"━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📋 <b>Saat Saat Detay (Son 24h)</b>")
    lines.append(f"<code>IST  │ SOL           │ ETH</code>")
    lines.append(f"<code>─────┼───────────────┼───────────────</code>")

    for h in all_hours:
        sol_p = by_sym.get(("SOLUSDT", h))
        eth_p = by_sym.get(("ETHUSDT", h))

        def fmt(p):
            if not p:
                return "—             "
            dir_short = "UP " if p.get("direction") == "YUKARI" else "DWN"
            if not p.get("checked"):
                return f"? {dir_short}          "
            ok = p.get("correct", False)
            icon2 = "✅" if ok else "❌"
            return f"{icon2} {dir_short}          "

        lines.append(f"<code>{h:02d}:00│ {fmt(sol_p)[:13]} │ {fmt(eth_p)[:13]}</code>")

    # ── Polymarket Bakiye ──
    poly_block = await _fetch_poly_portfolio()
    if poly_block:
        lines.append(poly_block.rstrip())

    await send_telegram("\n".join(lines))
    print(f"[RAPOR] Gönderildi — {total_ok}/{total_all} doğru ({overall:.0f}%)")


def _build_updown_slug(coin_name: str, dt_et) -> str:
    """ET datetime'dan 'bitcoin-up-or-down-april-1-2026-2pm-et' slug üretir."""
    full = "solana" if coin_name == "SOL" else "ethereum"
    month = dt_et.strftime("%B").lower()   # "march", "april" ...
    day   = str(dt_et.day)                 # "1", "31"
    year  = str(dt_et.year)
    hr    = dt_et.hour                     # 0-23
    hr12  = hr % 12 or 12
    ampm  = "am" if hr < 12 else "pm"
    return f"{full}-up-or-down-{month}-{day}-{year}-{hr12}{ampm}-et"


async def find_market(coin: str, direction: str, price: float) -> Optional[dict]:
    """
    'Bitcoin/Ethereum Up or Down - Hourly' marketini slug ile bulur.
    Gamma API'den conditionId alır, CLOB API'den token_id çeker.
    direction: "YUKARI" → Up token | "AŞAĞI" → Down token
    """
    from datetime import timedelta
    coin_name = "SOL" if "SOL" in coin else "ETH"
    full_name = "Solana" if coin_name == "SOL" else "Ethereum"

    # ET = UTC-4 (EDT). Saatlik market için bir sonraki tam saati hesapla.
    now_utc = datetime.now(timezone.utc)
    et_offset = timedelta(hours=-4)
    now_et  = now_utc + et_offset
    # Tahmin bir sonraki saat için → next_et
    next_et = now_et.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    # Denenecek saatler: sonraki saat ve mevcut saat
    candidates = [next_et, now_et.replace(minute=0, second=0, microsecond=0)]

    for dt in candidates:
        slug = _build_updown_slug(coin_name, dt)
        url  = f"{GAMMA_HOST}/events?slug={slug}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    events = await r.json()
        except Exception as e:
            print(f"[POLY] Event arama hatası ({slug}): {e}")
            continue

        if not isinstance(events, list):
            events = events.get("events", [])
        if not events:
            continue

        event  = events[0]
        markets = event.get("markets", [])
        if not markets:
            continue

        m = markets[0]
        condition_id = m.get("conditionId", "")
        volume       = float(event.get("volume", 0))

        if not condition_id:
            continue

        # CLOB API'den token_id çek
        clob_url = f"{CLOB_HOST}/markets/{condition_id}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(clob_url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    clob = await r.json()
        except Exception as e:
            print(f"[POLY] CLOB market hatası: {e}")
            continue

        if not clob.get("accepting_orders"):
            continue

        tokens = clob.get("tokens", [])
        up_tok   = next((t for t in tokens if t.get("outcome","").upper() == "UP"),   None)
        down_tok = next((t for t in tokens if t.get("outcome","").upper() == "DOWN"), None)

        if not up_tok or not down_tok:
            continue

        up_price   = float(up_tok.get("price",   0.5))
        down_price = float(down_tok.get("price", 0.5))

        if direction == "YUKARI":
            token_id  = up_tok["token_id"]
            bet_side  = "up"
            bet_price = up_price
        else:
            token_id  = down_tok["token_id"]
            bet_side  = "down"
            bet_price = down_price

        if not (0.05 <= bet_price <= 0.95):
            continue

        result = {
            "token_id":     token_id,
            "up_token_id":  up_tok["token_id"],
            "down_token_id":down_tok["token_id"],
            "question":     m.get("question", event.get("title", "")),
            "bet_side":     bet_side,
            "bet_price":    round(bet_price, 3),
            "volume":       volume,
            "market_id":    condition_id,
            "min_size":     float(m.get("orderMinSize") or 5),
            "slug":         slug,
        }
        print(f"[POLY] Market bulundu: {result['question'][:60]} | "
              f"Up:%{up_price*100:.0f} Down:%{down_price*100:.0f} | hacim:${volume:,.0f}")
        return result

    print(f"[POLY] {full_name} için aktif Up/Down marketi bulunamadı")
    return None


async def place_bet(pred: Prediction) -> Optional[dict]:
    """
    YÜKSEK güven tahminlerinde Polymarket CLOB'a FAK emir gönderir.
    clob_orders.py (FAK + retry) kullanır; polymarket-main/.env kimlik bilgileri geçerli.
    Sonuç hourly_trades DB'ye kaydedilir.
    """
    if pred.confidence != "YÜKSEK" or pred.direction == "NÖTR":
        return None

    market = await find_market(pred.symbol, pred.direction, pred.current_price)
    if not market:
        print(f"[POLY] {pred.symbol} için uygun market bulunamadı")
        return {"status": "no_market"}

    if BET_DRY_RUN:
        print(f"[POLY DRY RUN] {pred.symbol} → {pred.direction} | "
              f"{market['bet_side'].upper()} | ${BET_SIZE_USDC} | "
              f"fiyat:{market['bet_price']} | {market['question'][:50]}")
        return {
            "status":    "dry_run",
            "question":  market["question"],
            "bet_side":  market["bet_side"],
            "bet_price": market["bet_price"],
            "size":      BET_SIZE_USDC,
        }

    direction_en = "UP" if pred.direction == "YUKARI" else "DOWN"
    try:
        import sys as _sys
        _pm_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "polymarket-main")
        if _pm_path not in _sys.path:
            _sys.path.insert(0, _pm_path)
        from src.trading.clob_orders import place_buy_for_up_down
        from src.data.hourly_trades import init_hourly_table, insert_trade

        market_dict = {
            "slug":         market["slug"],
            "clobTokenIds": json.dumps([market["up_token_id"], market["down_token_id"]]),
            "orderMinSize": market["min_size"],
        }

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: place_buy_for_up_down(
                market_dict, up_or_down=direction_en, notional_usdc=BET_SIZE_USDC
            ),
        )
        resp_s = json.dumps(resp, ensure_ascii=False)[:2000] if isinstance(resp, dict) else repr(resp)[:2000]
        oid = str(resp.get("orderID") or resp.get("orderId") or "") if isinstance(resp, dict) else ""
        print(f"[POLY] Emir gönderildi: {pred.symbol} → {direction_en} | oid={oid or '?'}")

        # DB kaydı
        try:
            from zoneinfo import ZoneInfo
            from datetime import timedelta
            _ET = ZoneInfo("America/New_York")
            _TR = ZoneInfo("Europe/Istanbul")
            now_utc = datetime.now(timezone.utc)
            cur_et  = now_utc.astimezone(_ET).replace(minute=0, second=0, microsecond=0)
            tr_now  = now_utc.astimezone(_TR)
            td = tr_now.date()
            if tr_now.hour < 16:
                td = td - timedelta(days=1)
            coin = "solana" if "SOL" in pred.symbol else "ethereum"
            init_hourly_table()
            insert_trade(
                coin=coin,
                slug=market["slug"],
                prediction=direction_en,
                predicted_at=now_utc.isoformat(),
                trade_date_et=td.isoformat(),
                et_clock_label=f"{cur_et.hour:02d}:00 ET",
                order_id=oid or None,
                order_response=resp_s,
                error=None,
            )
            print(f"[POLY DB] Kayıt eklendi: {coin} {direction_en}")
        except Exception as db_e:
            print(f"[POLY DB] Kayıt hatası: {db_e}")

        return resp

    except Exception as e:
        print(f"[POLY] Bahis hatası: {e}")
        import traceback; traceback.print_exc()
        return {"status": "error", "error": str(e)}


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
    except:
        return []


async def fetch_funding(symbol: str) -> float:
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params={"symbol": symbol},
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                return float(data.get("lastFundingRate", 0))
    except:
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
                        # 30 dk'dan eski veriyi temizle
                        cutoff = time.time() - 1800
                        states[sym].liq_data = [
                            l for l in states[sym].liq_data if l["ts"] >= cutoff
                        ]
        except Exception as e:
            print(f"[WS LIQ] {e} — yeniden bağlanıyor")
            await asyncio.sleep(3)


# ─────────────────────────────────────────────────────────────
# TAHMİN DÖNGÜSÜ — her saat başı
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


async def _do_prediction(label: str = ""):
    """Kline + funding + REST snapshot çek, tahmin üret, Telegram'a gönder."""
    now = datetime.now()

    # ── Geçmiş tahminlerin sonucunu kontrol et ──
    await check_past_predictions()

    for sym in SYMBOLS:
        kl = await fetch_klines(sym)
        if kl:
            states[sym].klines_1h = kl
        states[sym].funding_rate = await fetch_funding(sym)
        # OB ve CVD verisi yoksa REST'ten doldur
        if not states[sym].ob_bids:
            await fetch_orderbook_rest(sym)
        if not states[sym].ticks:
            await fetch_recent_trades_rest(sym)

    preds = [generate_prediction(states[sym]) for sym in SYMBOLS]
    preds = [p for p in preds if p]

    if not preds:
        print("[TAHMİN] Yeterli veri yok.")
        return

    # ── BTC 1h trend filtresi — SOL için ──
    # BTC son 1h mumu düşüşse ve SOL YUKARI diyorsa → DÜŞÜK güven
    # BTC son 1h mumu yükselişse ve SOL AŞAĞI diyorsa → DÜŞÜK güven
    try:
        btc_kl = await fetch_klines("BTCUSDT")
        if btc_kl and len(btc_kl) >= 2:
            btc_last = btc_kl[-2]
            btc_dir  = "YUKARI" if btc_last["close"] >= btc_last["open"] else "AŞAĞI"
            for pred in preds:
                if "SOL" in pred.symbol and pred.direction != btc_dir:
                    if pred.confidence == "YÜKSEK":
                        pred.confidence = "ORTA"
                        print(f"[BTC FİLTRE] {pred.symbol} {pred.direction} ↔ BTC {btc_dir} — YÜKSEK→ORTA")
    except Exception as e:
        print(f"[BTC FİLTRE HATA] {e}")

    # Geçmiş kontrol — hangileri bu saat kapandı?
    all_preds   = _load_predictions()
    now_ts      = time.time()
    past_results = [
        p for p in all_preds
        if p.get("checked")
        and p.get("target_ts", 0) > now_ts - 3600
        and p.get("symbol") in SYMBOLS
    ]

    # Paper bet'leri önce kaydet → sonuçlarla mesajı gönder
    paper_results = {}
    for pred in preds:
        paper_results[pred.symbol] = await record_prediction(pred)

    # Birleşik tahmin mesajı (paper bet bilgisiyle)
    await send_unified_prediction(preds, past_results, paper_results=paper_results)

    # Gerçek bahis (dry_run'da sadece loglar)
    for pred in preds:
        await send_prediction(pred)


async def prediction_loop():
    """Her saat :12'de tahmin üret (İST: XX:15 civarı)."""
    print("[TAHMİN] Bekleniyor — ilk veri dolsun (2 dk)...")
    await asyncio.sleep(120)

    _daily_report_sent_date = None   # aynı gün iki kez gönderme
    PM = 12  # her saat kaçıncı dakikada tetiklensin

    while True:
        now     = datetime.now(timezone.utc)
        ist_h   = (now.hour + 3) % 24
        ist_m   = now.minute
        today   = now.strftime("%Y-%m-%d")

        # Her gün 16:00 İST (13:00 UTC) → günlük rapor
        if ist_h == 16 and ist_m < 15 and _daily_report_sent_date != today:
            try:
                await send_daily_report()
                _daily_report_sent_date = today
                print("[RAPOR] Günlük rapor gönderildi.")
            except Exception as e:
                print(f"[RAPOR HATA] {e}")

        mins = now.minute

        if mins < PM:
            wait = (PM - mins) * 60 - now.second
        else:
            wait = (60 - mins + PM) * 60 - now.second

        wait = max(30, wait)
        target_h = (now.hour + (1 if mins >= PM else 0)) % 24
        target_ist_h = (target_h + 3) % 24
        print(f"[TAHMİN] Sonraki gönderim: {target_h:02d}:{PM:02d} UTC = {target_ist_h:02d}:{PM:02d} IST ({wait//60} dk {wait%60} sn sonra)")
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
            next_h = (datetime.now().hour + 1) % 24

            print("╔══════════════════════════════════════════════════╗")
            print(f"║  POLYMARKET TAHMİN MOTORU  │  {now}  ║")
            print("╠══════════════════════════════════════════════════╣")
            print(f"║  Sonraki tahmin: {next_h:02d}:12  ║")
            print("╠══════════════════════════════════════════════════╣")

            for sym in SYMBOLS:
                st     = states[sym]
                cvd5   = st.cvd(300)
                imb    = st.ob_imbalance()
                br     = st.buy_ratio(300)
                liq    = st.liq_bias(600)
                name   = sym.replace("USDT", "")

                print(f"║  {name:<4}  Fiyat: ${st.price:>12,.2f}  ║")
                print(f"║       CVD5m: {cvd5/1000:>+8.1f}K  "
                      f"OB: %{imb:.0f}  AlışR: %{br:.0f}  ║")
                print(f"║       Liq: {liq:<8}  "
                      f"Tick: {len(st.ticks):>5}  Funding: %{st.funding_rate*100:.3f}  ║")

            print("╚══════════════════════════════════════════════════╝")
            print("  Ctrl+C ile durdur")
        except:
            pass
        await asyncio.sleep(5)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

async def main():
    print("=" * 52)
    print("  POLYMARKET TAHMİN MOTORU başlatılıyor...")
    print(f"  Semboller: {', '.join(SYMBOLS)}")
    print(f"  Telegram: {'✅' if TELEGRAM_TOKEN else '❌ .env dosyasını doldur'}")
    print("=" * 52)

    await send_telegram(
        f"🔮 <b>Polymarket Tahmin Motoru Başladı</b>\n"
        f"📊 SOL + ETH · 1 Saatlik Tahminler\n"
        f"⏰ Her saat başı Telegram'a bildirim gelecek"
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
