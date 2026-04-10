"""
╔══════════════════════════════════════════════════════════════════╗
║  POLYMARKET TAHMİN MOTORU v1.1                                   ║
║  ETH/SOL · 1 Saatlik Fiyat Tahmini · Telegram Bildirimi          ║
║                                                                  ║
║  Mantık:                                                         ║
║  Her saat başı ETH ve SOL için şunu tahmin eder:                 ║
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
import math

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

# Order book temizliği — fiyattan bu kadar uzak seviyeleri sil (% olarak)
OB_CLEANUP_PCT = 0.05   # ±%5 dışı sil
OB_CLEANUP_INTERVAL = 300  # 5 dakikada bir


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
        self.cleanup_liq()   # ── FİX 2: her sorguda temizle ──
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

        rsi_v   = _rsi(c)
        macd_h  = _macd_hist(c)   # FİX 4 uygulandı
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

    # ── KARAR ──
    if total_w == 0:
        return None

    bull_pct = bull_pts / total_w
    bear_pct = bear_pts / total_w

    if bull_pts >= bear_pts:
        direction = "YUKARI"
        raw_prob  = bull_pct if bull_pts > bear_pts else 0.5
    else:
        direction = "AŞAĞI"
        raw_prob  = bear_pct

    # ── FİX 5: Olasılık yorumu düzeltildi (lineer ölçekleme, sigmoid değil) ──
    # raw_prob [0.5, 1.0] → prob [0.50, 0.85] arasında lineer ölçekleme
    prob = 0.5 + (raw_prob - 0.5) * 0.7
    prob = max(0.50, min(0.85, prob))

    gap = abs(bull_pts - bear_pts)
    if gap >= total_w * 0.4:
        confidence = "YÜKSEK"
    elif gap >= total_w * 0.2:
        confidence = "ORTA"
    else:
        confidence = "DÜŞÜK"

    now_utc     = datetime.now(timezone.utc)
    target_ist  = (now_utc.hour + 1 + 3) % 24
    target_time = f"{target_ist:02d}:00 İST"

    kl      = state.klines_1h
    h1_high = max(k["high"] for k in kl[-3:]) if len(kl) >= 3 else 0.0
    h1_low  = min(k["low"]  for k in kl[-3:]) if len(kl) >= 3 else 0.0

    p    = state.price
    step = 500 if p > 10_000 else 100 if p > 1_000 else 10 if p > 100 else 1
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
    icon  = _symbol_icon(sym)
    d_ico = "📉" if pred.direction == "AŞAĞI" else "📈" if pred.direction == "YUKARI" else "➡️"

    rsi_v = adx_v = 0.0
    for k, v in pred.signals.items():
        if k == "rsi":
            m = re.search(r'[\d.]+', v)
            if m: rsi_v = float(m.group())
        if k == "regime":
            m = re.search(r'ADX:([\d.]+)', v)
            if m: adx_v = float(m.group(1))

    trend_str = "AŞAĞI" if pred.bear_pct > pred.bull_pct else "YUKARI"
    trend_ico = "🔴" if trend_str == "AŞAĞI" else "🟢"

    p  = pred.current_price
    kl = pred.key_level
    kl_rel = "ÜZERİNDE" if p >= kl else "ALTINDA"

    sig_lines = []
    for k, v in pred.signals.items():
        raw = v.replace("🟢 ", "").replace("🔴 ", "").replace("⚪ ", "").replace("⚠️ ", "")
        if "🟢" in v:   sig_lines.append(f"✅ {raw}")
        elif "🔴" in v: sig_lines.append(f"❌ {raw}")
        else:            sig_lines.append(f"➕ {raw}")

    sigs = "\n".join(sig_lines)

    h_range = ""
    if pred.h1_high and pred.h1_low:
        h_range = f"🔧 1h Aralık: ${pred.h1_low:,.0f} – ${pred.h1_high:,.0f}\n"

    return (
        f"{icon} <b>{sym}</b>  ${p:,.2f}  {d_ico}\n"
        f"▲ YUKARI: <b>{pred.bull_pct}%</b>  |  ▼ AŞAĞI: <b>{pred.bear_pct}%</b>\n"
        f"{h_range}"
        f"{trend_ico} Trend: {trend_str}  |  RSI:{rsi_v:.0f}  |  ADX:{adx_v:.0f}\n"
        f"🎯 Yakın seviye: ${kl:,.0f} ({kl_rel})\n"
        f"{sigs}"
    )


async def send_prediction(pred: Prediction):
    """Tek tahmin — yüksek güvenle bet tetikle."""
    bet_result = None
    if pred.confidence == "YÜKSEK" and pred.direction != "NÖTR":
        bet_result = await place_bet(pred)
    sym_short = pred.symbol.replace("USDT", "")
    print(f"[TAHMİN] {sym_short} → {pred.direction} %{pred.probability*100:.0f} "
          f"({pred.confidence}) | Bahis: {bet_result.get('status','—') if bet_result else '—'}")
    return bet_result


async def send_unified_prediction(preds: list, past_results: list):
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
            prev_lines.append(
                f"{icon} {s_ic} {sym}  ${ep:,.0f} → ${ap:,.0f}  "
                f"({'+' if diff>=0 else ''}{diff:,.0f})  Tahmin: {r['direction']}"
            )
        score = f"{len(correct)}/{len(past_results)} doğru"
        prev_block = (
            f"─────────────────────\n"
            f"📋 <b>Geçen saat sonucu: {score}</b>\n"
            + "\n".join(prev_lines) + "\n"
        )

    coin_blocks = []
    for pred in preds:
        coin_blocks.append(_build_coin_block(pred))

    msg = (
        f"🎯 <b>POLYX2 - AIPROJECT</b>\n"
        f"⏰ Hedef: <b>{target_time}</b>\n"
        f"{prev_block}"
        f"─────────────────────\n"
        + "\n─────────────────────\n".join(coin_blocks)
        + f"\n─────────────────────\n"
        f"⚠️ <i>Bu tahmin yatırım tavsiyesi değildir.</i>"
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

def record_prediction(pred: "Prediction"):
    """Tahmini dosyaya kaydet."""
    now      = datetime.now(timezone.utc)
    target_ts = now.replace(minute=0, second=0, microsecond=0).timestamp() + 3600

    preds = _load_predictions()
    preds.append({
        "symbol":     pred.symbol,
        "direction":  pred.direction,
        "price":      pred.current_price,
        "confidence": pred.confidence,
        "target_ts":  target_ts,
        "sent_ts":    now.timestamp(),
        "checked":    False,
    })
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


async def find_market(coin: str, direction: str, price: float) -> Optional[dict]:
    """
    Polymarket piyasa araması ana pipeline'da yapılır.
    Bu dosyada işlem yok — kasıtlı stub.
    """
    return None


async def place_bet(pred: Prediction) -> Optional[dict]:
    """
    Polymarket emri ana pipeline'da verilir.
    Bu dosyada işlem yok — kasıtlı stub.
    Dönen değer: None (bahis atlanır, log'a yazılır).
    """
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

    await check_past_predictions()

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

    await send_unified_prediction(preds, past_results)

    for pred in preds:
        await send_prediction(pred)
        record_prediction(pred)


async def prediction_loop():
    """
    Her saat :04'ünde tahmin üret.

    ── FİX 3: Zamanlama hatası düzeltildi ──
    Önceki formülde mins==4 durumunda wait=3600 oluyordu (1 saat atlanıyordu).
    Yeni mantık: dakika < 4 ise bu saatin :04'ünü bekle,
                 dakika >= 4 ise bir sonraki saatin :04'ünü bekle.
    """
    print("[TAHMİN] Bekleniyor — ilk veri dolsun (2 dk)...")
    await asyncio.sleep(120)

    _daily_report_sent_date = None

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

        # ── FİX 3: köşe case'i ayrıca ele alındı ──
        if mins < 4:
            # Aynı saatin :04'üne kadar bekle
            wait = (4 - mins) * 60 - secs
            target_h = now.hour
        else:
            # Bir sonraki saatin :04'üne kadar bekle (mins==4 dahil)
            wait = (60 - mins + 4) * 60 - secs
            target_h = (now.hour + 1) % 24

        wait = max(30, wait)
        print(f"[TAHMİN] Sonraki gönderim: {target_h:02d}:04 UTC ({wait//60} dk {wait%60} sn sonra)")
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
            now    = datetime.now().strftime("%H:%M:%S")
            next_h = (datetime.now().hour + 1) % 24

            print("╔══════════════════════════════════════════════════╗")
            print(f"║  POLYMARKET TAHMİN MOTORU  │  {now}  ║")
            print("╠══════════════════════════════════════════════════╣")
            print(f"║  Sonraki tahmin: {next_h:02d}:04  ║")
            print("╠══════════════════════════════════════════════════╣")

            for sym in SYMBOLS:
                st   = states[sym]
                cvd5 = st.cvd(300)
                imb  = st.ob_imbalance()
                br   = st.buy_ratio(300)
                liq  = st.liq_bias(600)
                name = sym.replace("USDT", "")

                print(f"║  {name:<4}  Fiyat: ${st.price:>12,.2f}  ║")
                print(f"║       CVD5m: {cvd5/1000:>+8.1f}K  "
                      f"OB: %{imb:.0f}  AlışR: %{br:.0f}  ║")
                print(f"║       Liq: {liq:<8}  "
                      f"Tick: {len(st.ticks):>5}  Funding: %{st.funding_rate*100:.3f}  ║")

            print("╚══════════════════════════════════════════════════╝")
            print("  Ctrl+C ile durdur")
        except Exception as e:
            print(f"[DISPLAY HATA] {e}")
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
        f"📊 ETH + SOL · 1 Saatlik Tahminler\n"
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