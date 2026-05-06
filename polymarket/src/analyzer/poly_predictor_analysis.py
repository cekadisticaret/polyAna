"""
Polymarket 1 Saatlik Fiyat Tahmin Motoru — v2
BTC ve ETH için "1 saat sonra şu anki fiyattan yüksek mi düşük mü?" sorusunu cevaplar.

Metodoloji:
  1. 1h kline verisi → ATR, EMA, RSI, MACD, ADX          (teknik)
  2. CVD 5m / 30m                                         (hacim delta)
  3. Order Book imbalance, Büyük işlem yönü, Taker oranı  (order flow)
  4. Funding rate, L/S oranı, Likidasyon                  (futures sentiment)
  5. Çoklu faktör skorlaması → birleşik olasılık
"""

import asyncio
import math
import json
import os
import aiohttp
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

STATE_FILE   = "/opt/cripto/poly_state.json"
HISTORY_FILE = "/opt/cripto/poly_history.json"


def save_predictions(predictions: list) -> None:
    data = {}
    for p in predictions:
        data[p.symbol] = {
            "current_price": p.current_price,
            "predicted_dir": p.predicted_dir,
            "timestamp":     p.timestamp,
        }
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[POLY] State yazılamadı: {e}")


def load_predictions() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────
# TEKNİK YARDIMCI HESAPLAMALAR (değişmedi)
# ─────────────────────────────────────────────────────────────

def _ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return [values[-1]] * len(values) if values else []
    k = 2.0 / (period + 1)
    result = [0.0] * len(values)
    result[period - 1] = sum(values[:period]) / period
    for i in range(period, len(values)):
        result[i] = values[i] * k + result[i - 1] * (1 - k)
    return result


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = losses = 0.0
    for i in range(1, period + 1):
        diff = closes[-period - 1 + i] - closes[-period - 2 + i]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(closes: list[float]) -> tuple[float, float]:
    if len(closes) < 26:
        return 0.0, 0.0
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = [ema12[i] - ema26[i] for i in range(len(closes))]
    signal = _ema(macd_line[25:], 9)
    return macd_line[-1], signal[-1] if signal else 0.0


def _atr_list(klines: list[dict], period: int = 14) -> list[float]:
    trs = []
    for i in range(1, len(klines)):
        tr = max(
            klines[i]["high"] - klines[i]["low"],
            abs(klines[i]["high"] - klines[i - 1]["close"]),
            abs(klines[i]["low"]  - klines[i - 1]["close"]),
        )
        trs.append(tr)
    if len(trs) < period:
        return [sum(trs) / len(trs)] * len(trs) if trs else [0.0]
    atr_vals = [sum(trs[:period]) / period]
    for i in range(period, len(trs)):
        atr_vals.append((atr_vals[-1] * (period - 1) + trs[i]) / period)
    return atr_vals


def _adx(klines: list[dict], period: int = 14) -> tuple[float, float, float]:
    if len(klines) < period * 2:
        return 25.0, 25.0, 25.0

    plus_dm_list, minus_dm_list, tr_list = [], [], []
    for i in range(1, len(klines)):
        h, l, ph, pl, pc = (
            klines[i]["high"], klines[i]["low"],
            klines[i - 1]["high"], klines[i - 1]["low"],
            klines[i - 1]["close"],
        )
        up   = h - ph
        down = pl - l
        plus_dm_list.append(up   if up > down and up > 0   else 0.0)
        minus_dm_list.append(down if down > up and down > 0 else 0.0)
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))

    def wilder_smooth(vals, p):
        res = [sum(vals[:p])]
        for i in range(p, len(vals)):
            res.append(res[-1] - res[-1] / p + vals[i])
        return res

    atr14   = wilder_smooth(tr_list, period)
    plus14  = wilder_smooth(plus_dm_list, period)
    minus14 = wilder_smooth(minus_dm_list, period)

    dx_list = []
    for i in range(len(atr14)):
        if atr14[i] == 0:
            dx_list.append(0.0)
            continue
        pdi = 100 * plus14[i]  / atr14[i]
        mdi = 100 * minus14[i] / atr14[i]
        dx  = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0
        dx_list.append(dx)

    adx = sum(dx_list[-period:]) / period if len(dx_list) >= period else sum(dx_list) / max(len(dx_list), 1)
    last_atr = atr14[-1]
    pdi = 100 * plus14[-1]  / last_atr if last_atr else 25.0
    mdi = 100 * minus14[-1] / last_atr if last_atr else 25.0
    return adx, pdi, mdi


# ─────────────────────────────────────────────────────────────
# VERİ ÇEKME — TEKNİK
# ─────────────────────────────────────────────────────────────

async def _fetch_klines(symbol: str, tf: str = "1h", limit: int = 60) -> list[dict]:
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {"symbol": symbol, "interval": tf, "limit": limit}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params,
                             timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
        if not isinstance(data, list):
            print(f"[POLY] {symbol} kline beklenmeyen yanıt (dict/hata): {data}")
            return []
        return [
            {
                "open":      float(k[1]),
                "high":      float(k[2]),
                "low":       float(k[3]),
                "close":     float(k[4]),
                "volume":    float(k[5]),
                "taker_buy": float(k[9]),
            }
            for k in data
        ]
    except Exception as e:
        print(f"[POLY] {symbol} kline hata: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# VERİ ÇEKME — ORDER FLOW
# ─────────────────────────────────────────────────────────────

async def _fetch_cvd(symbol: str) -> tuple[float, float]:
    """
    CVD oranı: (taker_buy - taker_sell) / total_vol → [-1, +1]
    Döner: (cvd_5m, cvd_30m) — pozitif = net alış baskısı
    """
    async def get_ratio(tf: str, limit: int) -> float:
        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {"symbol": symbol, "interval": tf, "limit": limit}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, params=params,
                                 timeout=aiohttp.ClientTimeout(total=8)) as r:
                    data = await r.json()
            if not isinstance(data, list):
                return 0.0
            total_vol = sum(float(k[5]) for k in data)
            taker_buy = sum(float(k[9]) for k in data)
            if total_vol == 0:
                return 0.0
            return (2 * taker_buy - total_vol) / total_vol
        except Exception:
            return 0.0

    cvd_5m, cvd_30m = await asyncio.gather(
        get_ratio("5m", 6),   # son ~30 dakika
        get_ratio("30m", 2),  # son ~1 saat
    )
    return cvd_5m, cvd_30m


async def _fetch_orderbook_imbalance(symbol: str) -> float:
    """Bid oranı (0-1). >0.5 alış ağır. Hata → 0.5"""
    url = "https://fapi.binance.com/fapi/v1/depth"
    params = {"symbol": symbol, "limit": 20}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params,
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                data = await r.json()
        bid_vol = sum(float(b[1]) for b in data["bids"])
        ask_vol = sum(float(a[1]) for a in data["asks"])
        total = bid_vol + ask_vol
        return bid_vol / total if total > 0 else 0.5
    except Exception:
        return 0.5


async def _fetch_large_trades(symbol: str) -> float:
    """Son 1000 aggTrade'den büyük olanların (üst %10) alış oranı. >0.5 bullish."""
    url = "https://fapi.binance.com/fapi/v1/aggTrades"
    params = {"symbol": symbol, "limit": 1000}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params,
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                trades = await r.json()
        if not trades:
            return 0.5
        sizes = sorted([float(t["q"]) for t in trades], reverse=True)
        threshold = sizes[max(0, len(sizes) // 10)]
        large = [t for t in trades if float(t["q"]) >= threshold]
        if not large:
            return 0.5
        # m=False → taker buyer (BUY), m=True → taker seller (SELL)
        buy_vol  = sum(float(t["q"]) for t in large if not t["m"])
        sell_vol = sum(float(t["q"]) for t in large if t["m"])
        total = buy_vol + sell_vol
        return buy_vol / total if total > 0 else 0.5
    except Exception:
        return 0.5


async def _fetch_taker_ratio(symbol: str) -> float:
    """Futures taker alış/satış oranı (son 5dk). >0.5 bullish. Hata → 0.5"""
    url = "https://fapi.binance.com/futures/data/takerlongshortRatio"
    params = {"symbol": symbol, "period": "5m", "limit": 1}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params,
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                data = await r.json()
        if data and isinstance(data, list):
            buy  = float(data[0]["buyVol"])
            sell = float(data[0]["sellVol"])
            total = buy + sell
            return buy / total if total > 0 else 0.5
        return 0.5
    except Exception:
        return 0.5


async def _fetch_funding_rate(symbol: str) -> float:
    """Anlık funding rate. Yüksek pozitif = aşırı iyimser (bearish signal)."""
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    params = {"symbol": symbol}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params,
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                data = await r.json()
        return float(data.get("lastFundingRate", 0))
    except Exception:
        return 0.0


async def _fetch_long_short_ratio(symbol: str) -> float:
    """Global L/S hesap oranı (son 5dk). >0.5 = long baskın. Hata → 0.5"""
    url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
    params = {"symbol": symbol, "period": "5m", "limit": 1}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params,
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                data = await r.json()
        if data and isinstance(data, list):
            return float(data[0]["longAccount"])
        return 0.5
    except Exception:
        return 0.5


async def _fetch_liquidations(symbol: str) -> tuple[float, float]:
    """Son likidasyonlar: (long_liq_usd, short_liq_usd). Hata → (0, 0)"""
    url = "https://fapi.binance.com/fapi/v1/allForceOrders"
    params = {"symbol": symbol, "limit": 100}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params,
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                data = await r.json()
        if not isinstance(data, list):
            return 0.0, 0.0
        # LONG likidasyon → sistem SATIYOR (S=SELL)
        # SHORT likidasyon → sistem ALIYOR (S=BUY)
        long_liq  = sum(float(t.get("q", 0)) * float(t.get("ap", t.get("p", 0)))
                        for t in data if t.get("S") == "SELL")
        short_liq = sum(float(t.get("q", 0)) * float(t.get("ap", t.get("p", 0)))
                        for t in data if t.get("S") == "BUY")
        return long_liq, short_liq
    except Exception:
        return 0.0, 0.0


# ─────────────────────────────────────────────────────────────
# SKORLAMA
# ─────────────────────────────────────────────────────────────

def _technical_score(
    rsi: float,
    macd_val: float,
    macd_sig: float,
    adx: float,
    plus_di: float,
    minus_di: float,
    ema9: float,
    ema21: float,
    ema50: float,
) -> tuple[int, list[str]]:
    """Teknik indikatör skoru. Maks ±38."""
    score = 0
    factors = []

    # EMA hizası (±12)
    if ema9 > ema21 > ema50:
        score += 12
        factors.append("✅ EMA hizası: Tam yükseliş dizisi")
    elif ema9 < ema21 < ema50:
        score -= 12
        factors.append("❌ EMA hizası: Tam düşüş dizisi")
    elif ema9 > ema21:
        score += 5
        factors.append("➕ EMA: Hızlı &gt; Yavaş (zayıf yükseliş)")
    elif ema9 < ema21:
        score -= 5
        factors.append("➖ EMA: Hızlı &lt; Yavaş (zayıf düşüş)")

    # ADX trend gücü (±10)
    if adx > 30:
        if plus_di > minus_di:
            score += 10
            factors.append(f"✅ ADX:{adx:.0f} güçlü — +DI baskın (yükseliş trendi)")
        else:
            score -= 10
            factors.append(f"❌ ADX:{adx:.0f} güçlü — -DI baskın (düşüş trendi)")
    elif adx > 20:
        if plus_di > minus_di:
            score += 5
            factors.append(f"➕ ADX:{adx:.0f} orta — +DI öne geçiyor")
        else:
            score -= 5
            factors.append(f"➖ ADX:{adx:.0f} orta — -DI öne geçiyor")
    else:
        factors.append(f"⚪ ADX:{adx:.0f} düşük — yön belirsiz")

    # RSI (±8)
    if rsi >= 60:
        score += 8
        factors.append(f"✅ RSI:{rsi:.0f} — güçlü momentum")
    elif rsi >= 50:
        score += 3
        factors.append(f"➕ RSI:{rsi:.0f} — hafif yükseliş tarafı")
    elif rsi <= 40:
        score -= 8
        factors.append(f"❌ RSI:{rsi:.0f} — zayıf momentum")
    elif rsi <= 50:
        score -= 3
        factors.append(f"➖ RSI:{rsi:.0f} — hafif düşüş tarafı")

    # MACD (±8)
    if macd_val > macd_sig and macd_val > 0:
        score += 8
        factors.append("✅ MACD: Pozitif ve sinyal üzerinde")
    elif macd_val > macd_sig:
        score += 4
        factors.append("➕ MACD: Sinyal üzerinde (crossover)")
    elif macd_val < macd_sig and macd_val < 0:
        score -= 8
        factors.append("❌ MACD: Negatif ve sinyal altında")
    elif macd_val < macd_sig:
        score -= 4
        factors.append("➖ MACD: Sinyal altında (bearish cross)")

    return score, factors


def _orderflow_score(
    cvd_5m: float,
    cvd_30m: float,
    ob_imbalance: float,
    large_buy: float,
    taker_ratio: float,
    funding_rate: float,
    long_short: float,
    long_liq: float,
    short_liq: float,
) -> tuple[int, list[str]]:
    """Order flow skoru. Maks ±53."""
    score = 0
    factors = []

    # CVD 5m (±10)
    if cvd_5m > 0.05:
        score += 10
        factors.append(f"✅ CVD 5dk: +{cvd_5m*100:.1f}% (net alış baskısı)")
    elif cvd_5m > 0:
        score += 4
        factors.append(f"➕ CVD 5dk: +{cvd_5m*100:.1f}% (hafif alış)")
    elif cvd_5m < -0.05:
        score -= 10
        factors.append(f"❌ CVD 5dk: {cvd_5m*100:.1f}% (net satış baskısı)")
    else:
        score -= 4
        factors.append(f"➖ CVD 5dk: {cvd_5m*100:.1f}% (hafif satış)")

    # CVD 30m (±8)
    if cvd_30m > 0.05:
        score += 8
        factors.append(f"✅ CVD 30dk: +{cvd_30m*100:.1f}% (alış baskısı sürüyor)")
    elif cvd_30m > 0:
        score += 3
        factors.append(f"➕ CVD 30dk: +{cvd_30m*100:.1f}%")
    elif cvd_30m < -0.05:
        score -= 8
        factors.append(f"❌ CVD 30dk: {cvd_30m*100:.1f}% (satış baskısı sürüyor)")
    else:
        score -= 3
        factors.append(f"➖ CVD 30dk: {cvd_30m*100:.1f}%")

    # Order Book İmbalance (±8)
    ob_pct = ob_imbalance * 100
    if ob_imbalance > 0.60:
        score += 8
        factors.append(f"✅ OB İmbalance: %{ob_pct:.0f} (alış ağır)")
    elif ob_imbalance > 0.50:
        score += 3
        factors.append(f"➕ OB İmbalance: %{ob_pct:.0f} (hafif alış)")
    elif ob_imbalance < 0.40:
        score -= 8
        factors.append(f"❌ OB İmbalance: %{ob_pct:.0f} (satış ağır)")
    else:
        score -= 3
        factors.append(f"➖ OB İmbalance: %{ob_pct:.0f} (hafif satış)")

    # Büyük İşlemler (±8)
    lt_pct = large_buy * 100
    if large_buy > 0.65:
        score += 8
        factors.append(f"✅ Büyük işlemler: ALIŞ yönü (%{lt_pct:.0f})")
    elif large_buy > 0.50:
        score += 3
        factors.append(f"➕ Büyük işlemler: hafif alış (%{lt_pct:.0f})")
    elif large_buy < 0.35:
        score -= 8
        factors.append(f"❌ Büyük işlemler: SATIŞ yönü (%{100-lt_pct:.0f})")
    else:
        score -= 3
        factors.append(f"➖ Büyük işlemler: hafif satış (%{100-lt_pct:.0f})")

    # Taker Oranı (±6)
    tk_pct = taker_ratio * 100
    if taker_ratio > 0.60:
        score += 6
        factors.append(f"✅ Alış oranı: %{tk_pct:.0f} (taker alıcılar baskın)")
    elif taker_ratio > 0.50:
        score += 2
        factors.append(f"➕ Alış oranı: %{tk_pct:.0f}")
    elif taker_ratio < 0.40:
        score -= 6
        factors.append(f"❌ Alış oranı: %{tk_pct:.0f} (taker satıcılar baskın)")
    else:
        score -= 2
        factors.append(f"➖ Alış oranı: %{tk_pct:.0f}")

    # Funding Rate (±5) — kontrarian
    fr_pct = funding_rate * 100
    if funding_rate > 0.0003:
        score -= 5
        factors.append(f"❌ Funding: %{fr_pct:.4f} (aşırı iyimser — düzeltme riski)")
    elif funding_rate > 0.0001:
        score -= 2
        factors.append(f"➖ Funding: %{fr_pct:.4f} (yükseliş tarafı ağır)")
    elif funding_rate < -0.0001:
        score += 5
        factors.append(f"✅ Funding: %{fr_pct:.4f} (negatif — dip sinyali)")
    else:
        factors.append(f"⚪ Funding: %{fr_pct:.4f} (normal)")

    # L/S Oranı (±3) — kontrarian
    ls_pct = long_short * 100
    if long_short > 0.65:
        score -= 3
        factors.append(f"➖ L/S oranı: %{ls_pct:.0f} long (aşırı iyimser)")
    elif long_short < 0.40:
        score += 3
        factors.append(f"➕ L/S oranı: %{ls_pct:.0f} long (aşırı kötümser)")
    else:
        factors.append(f"⚪ L/S oranı: %{ls_pct:.0f} long")

    # Likidasyon (±5)
    total_liq = long_liq + short_liq
    if total_liq > 0:
        net_liq = short_liq - long_liq
        if net_liq > total_liq * 0.30:
            score += 5
            factors.append(f"✅ Likidasyon: short ağırlıklı (${short_liq/1000:.0f}K)")
        elif net_liq < -total_liq * 0.30:
            score -= 5
            factors.append(f"❌ Likidasyon: long ağırlıklı (${long_liq/1000:.0f}K)")
        else:
            factors.append(f"⚪ Likidasyon: dengeli")
    else:
        factors.append("⚪ Likidasyon: nötr")

    return score, factors


# ─────────────────────────────────────────────────────────────
# TAHMİN MOTORU
# ─────────────────────────────────────────────────────────────

@dataclass
class PolyPrediction:
    symbol:        str
    current_price: float
    prob_up:       float
    prob_down:     float
    expected_low:  float
    expected_high: float
    atr_1h:        float
    rsi:           float
    macd_bull:     bool
    adx:           float
    trend:         str
    factors:       list[str]
    nearest_round: float
    round_side:    str
    predicted_dir: str
    timestamp:     float = 0.0


def _nearest_round(price: float, symbol: str) -> float:
    step = 500 if "BTC" in symbol else 50
    return round(price / step) * step


async def predict(symbol: str) -> "PolyPrediction | None":
    # Teknik veri + order flow verisi paralel çek
    klines_task = _fetch_klines(symbol, "1h", 60)
    (
        klines,
        (cvd_5m, cvd_30m),
        ob_imb,
        large_buy,
        taker,
        funding,
        ls_ratio,
        (long_liq, short_liq),
    ) = await asyncio.gather(
        klines_task,
        _fetch_cvd(symbol),
        _fetch_orderbook_imbalance(symbol),
        _fetch_large_trades(symbol),
        _fetch_taker_ratio(symbol),
        _fetch_funding_rate(symbol),
        _fetch_long_short_ratio(symbol),
        _fetch_liquidations(symbol),
    )

    if len(klines) < 30:
        return None

    closes  = [k["close"] for k in klines]
    current = closes[-1]

    # ATR
    atr_vals = _atr_list(klines)
    atr_1h   = atr_vals[-1] if atr_vals else current * 0.01

    # EMA
    ema9_list  = _ema(closes, 9)
    ema21_list = _ema(closes, 21)
    ema50_list = _ema(closes, 50)
    ema9  = ema9_list[-1]
    ema21 = ema21_list[-1]
    ema50 = ema50_list[-1]

    # RSI / MACD / ADX
    rsi_val             = _rsi(closes)
    macd_val, macd_sig  = _macd(closes)
    adx, plus_di, minus_di = _adx(klines)

    # Trend yönü
    if adx > 20 and plus_di > minus_di and ema9 > ema21:
        trend = "YUKARI"
    elif adx > 20 and minus_di > plus_di and ema9 < ema21:
        trend = "AŞAĞI"
    else:
        trend = "YATAY"

    # Teknik skor
    tech_score, tech_factors = _technical_score(
        rsi_val, macd_val, macd_sig,
        adx, plus_di, minus_di,
        ema9, ema21, ema50,
    )

    # Order flow skoru
    flow_score, flow_factors = _orderflow_score(
        cvd_5m, cvd_30m,
        ob_imb, large_buy, taker,
        funding, ls_ratio,
        long_liq, short_liq,
    )

    # Birleşik olasılık — teknik maks ±38, flow maks ±53 → toplam ±91
    # Divisor 160 → maks sapma ±0.57, clamp [0.10, 0.90]
    total_score = tech_score + flow_score
    prob_up = 0.50 + total_score / 160.0
    prob_up = max(0.10, min(0.90, prob_up))

    # Tüm faktörler birleşik (teknik önce, order flow sonra)
    all_factors = tech_factors + flow_factors

    # Beklenen aralık
    expected_low  = current - atr_1h
    expected_high = current + atr_1h

    # En yakın yuvarlak seviye
    nearest   = _nearest_round(current, symbol)
    round_side = "ÜZERİNDE" if current >= nearest else "ALTINDA"

    import time as _time
    predicted_dir = "UP" if prob_up >= 0.50 else "DOWN"

    return PolyPrediction(
        symbol        = symbol,
        current_price = current,
        prob_up       = prob_up,
        prob_down     = 1.0 - prob_up,
        expected_low  = expected_low,
        expected_high = expected_high,
        atr_1h        = atr_1h,
        rsi           = rsi_val,
        macd_bull     = macd_val > macd_sig,
        adx           = adx,
        trend         = trend,
        factors       = all_factors,
        nearest_round = nearest,
        round_side    = round_side,
        predicted_dir = predicted_dir,
        timestamp     = _time.time(),
    )


async def predict_all() -> list[PolyPrediction]:
    results = []
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        pred = await predict(sym)
        if pred:
            results.append(pred)
    if results:
        save_predictions(results)
    return results


# ─────────────────────────────────────────────────────────────
# GEÇMİŞ KAYIT / GÜNLÜK RAPOR
# ─────────────────────────────────────────────────────────────

def load_history() -> dict:
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_history(history: dict) -> None:
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception as e:
        print(f"[POLY] History yazılamadı: {e}")


def record_outcome(symbol: str, entry_price: float, exit_price: float,
                   predicted_dir: str, target_hour: str, timestamp: float) -> "bool | None":
    history = load_history()
    if symbol not in history:
        history[symbol] = []

    already = any(e["target_hour"] == target_hour and abs(e["timestamp"] - timestamp) < 60
                  for e in history[symbol])
    if already:
        return None

    actual_up = exit_price > entry_price
    if predicted_dir == "UP":
        correct = actual_up
    elif predicted_dir == "DOWN":
        correct = not actual_up
    else:
        correct = None

    history[symbol].append({
        "timestamp":     timestamp,
        "target_hour":   target_hour,
        "entry_price":   entry_price,
        "exit_price":    exit_price,
        "predicted_dir": predicted_dir,
        "correct":       correct,
    })

    history[symbol] = history[symbol][-48:]
    save_history(history)
    return correct


def daily_stats() -> dict:
    import time
    cutoff  = time.time() - 86400
    history = load_history()
    stats   = {}
    for symbol, entries in history.items():
        recent = [e for e in entries if e["timestamp"] >= cutoff]
        seen_hours = {}
        for e in recent:
            h = e["target_hour"]
            if h not in seen_hours:
                seen_hours[h] = e
        unique  = list(seen_hours.values())
        correct = sum(1 for e in unique if e["correct"] is True)
        wrong   = sum(1 for e in unique if e["correct"] is False)
        neutral = sum(1 for e in unique if e["correct"] is None)
        total   = correct + wrong
        stats[symbol] = {
            "correct":  correct,
            "wrong":    wrong,
            "neutral":  neutral,
            "total":    total,
            "rate":     correct / total if total > 0 else 0.0,
        }
    return stats