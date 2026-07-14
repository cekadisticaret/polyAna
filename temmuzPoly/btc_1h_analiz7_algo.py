"""
BTC/USDT 1 Saatlik Gelişmiş Sinyal Motoru v2.0 — 7. Analiz

6 algo konsensüs (≥3/6): A1, Trend+ST+ADX, MR, Orderflow v2, Volume, Ichimoku
Filtreler: momentum, ADX≥25, hacim≥1.3x, 4H HTF onayı
MACD 12/26/9, RSI 30/70, Ichimoku, SuperTrend v2, HMA

Kullanım:
  python3 temmuzPoly/btc_1h_analiz7_algo.py
  python3 -c "from btc_1h_analiz7_algo import analyze; print(analyze().to_dict())"
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SYMBOL = "BTCUSDT"
INTERVAL = "1h"
HTF_INTERVAL = "4h"

MIN_CONSENSUS = 3
TOTAL_ALGOS = 6

RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

EMA_SHORT = 9
EMA_TREND_FAST = 20
EMA_TREND_SLOW = 50

BB_PERIOD = 20
BB_STD = 2.0

ADX_PERIOD = 14
ADX_MIN = 25

VOLUME_PERIOD = 20
VOLUME_MIN_RATIO = 1.3

MOMENTUM_BARS = 3

OB_DEPTH = 100
OB_RATIO_THRESHOLD = 0.08

ST_PERIOD = 10
ST_MULTIPLIER = 3.0
ICHI_TENKAN = 9
ICHI_KIJUN = 26
ICHI_SENKOU = 52
HMA_PERIOD = 16

ATR_PERIOD = 14
SL_MULTIPLIER = 2.0
TP_MULTIPLIER = 4.0
TRAILING_ACTIVATION = 1.5
TRAILING_STEP = 0.75

MAX_POSITION_PCT = 0.08
BASE_TRADE_AMOUNT = 15.0
DEFAULT_PORTFOLIO = 500.0

PAPER_TRADING = os.getenv("PM_1H_PAPER_TRADING", "true").lower() in ("1", "true", "yes")

MAX_RETRIES = 3
RETRY_DELAY = 1.5

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

MOMENTUM_FILTER_ENABLED = os.getenv("PM_1H_MOMENTUM_FILTER", "true").lower() in ("1", "true", "yes")
ADX_FILTER_ENABLED = os.getenv("PM_1H_ADX_FILTER", "true").lower() in ("1", "true", "yes")
VOLUME_FILTER_ENABLED = os.getenv("PM_1H_VOLUME_FILTER", "true").lower() in ("1", "true", "yes")
HTF_CONFIRMATION = os.getenv("PM_1H_HTF_CONFIRMATION", "true").lower() in ("1", "true", "yes")
SUPERTREND_FILTER = os.getenv("PM_1H_SUPERTREND_FILTER", "true").lower() in ("1", "true", "yes")


class BinanceAPIError(Exception):
    pass


def _binance_get(path: str, params: dict | None = None, base: str = "https://fapi.binance.com") -> dict | list:
    qs = urllib.parse.urlencode(params or {})
    url = f"{base}{path}?{qs}" if qs else f"{base}{path}"

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))

    raise BinanceAPIError(f"API çağrısı {MAX_RETRIES} denemede başarısız: {last_error}")


def fetch_klines(symbol: str = SYMBOL, interval: str = INTERVAL, limit: int = 300) -> list[dict]:
    raw = _binance_get("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    return [
        {
            "open_time": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "close_time": int(k[6]),
            "quote_volume": float(k[7]),
            "trades": int(k[8]),
        }
        for k in raw
    ]


def fetch_orderbook(symbol: str = SYMBOL, limit: int = OB_DEPTH) -> dict:
    return _binance_get("/fapi/v1/depth", {"symbol": symbol, "limit": limit})


def fetch_24h_stats(symbol: str = SYMBOL) -> dict:
    return _binance_get("/fapi/v1/ticker/24hr", {"symbol": symbol})


def ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return values.copy()
    k = 2 / (period + 1)
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def sma(values: list[float], period: int) -> list[float]:
    out = []
    for i in range(len(values)):
        if i < period - 1:
            out.append(sum(values[: i + 1]) / (i + 1))
        else:
            out.append(sum(values[i - period + 1 : i + 1]) / period)
    return out


def rsi(closes: list[float], period: int = 14) -> list[float]:
    if len(closes) < period + 1:
        return [50.0] * len(closes)

    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in diffs]
    losses = [max(-d, 0) for d in diffs]

    rsi_vals = [50.0]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(diffs)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi_vals.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_vals.append(100 - (100 / (1 + rs)))

    return rsi_vals


def atr(klines: list[dict], period: int = 14) -> list[float]:
    if len(klines) < 2:
        return [0.0]

    trs = []
    for i in range(1, len(klines)):
        high = klines[i]["high"]
        low = klines[i]["low"]
        prev_close = klines[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    if len(trs) < period:
        return [sum(trs) / len(trs)] * len(trs)

    atr_vals = [sum(trs[:period]) / period]
    for i in range(period, len(trs)):
        atr_vals.append((atr_vals[-1] * (period - 1) + trs[i]) / period)

    return atr_vals


def adx(klines: list[dict], period: int = 14) -> list[float]:
    if len(klines) < period * 2:
        return [25.0]

    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    closes = [k["close"] for k in klines]

    plus_dm = [0.0]
    minus_dm = [0.0]
    trs = [highs[0] - lows[0]]

    for i in range(1, len(klines)):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]

        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)

        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)

    atr_vals = [sum(trs[1 : period + 1]) / period]
    plus_di = [sum(plus_dm[1 : period + 1]) / period]
    minus_di = [sum(minus_dm[1 : period + 1]) / period]

    for i in range(period + 1, len(klines)):
        atr_vals.append((atr_vals[-1] * (period - 1) + trs[i]) / period)
        plus_di.append((plus_di[-1] * (period - 1) + plus_dm[i]) / period)
        minus_di.append((minus_di[-1] * (period - 1) + minus_dm[i]) / period)

    dx_vals = []
    for pdi, mdi, atr_val in zip(plus_di, minus_di, atr_vals):
        if pdi + mdi == 0:
            dx_vals.append(0.0)
        else:
            dx_vals.append(abs(pdi - mdi) / (pdi + mdi) * 100)

    adx_vals = [sum(dx_vals[:period]) / period]
    for i in range(period, len(dx_vals)):
        adx_vals.append((adx_vals[-1] * (period - 1) + dx_vals[i]) / period)

    return adx_vals


def bollinger(closes: list[float], period: int = 20, std_mult: float = 2.0) -> tuple[list[float], list[float], list[float]]:
    mid = sma(closes, period)
    upper, lower = [], []

    for i in range(len(closes)):
        if i < period - 1:
            std = 0.0
        else:
            window = closes[i - period + 1 : i + 1]
            m = sum(window) / period
            std = math.sqrt(sum((x - m) ** 2 for x in window) / period)

        upper.append(mid[i] + std_mult * std)
        lower.append(mid[i] - std_mult * std)

    return upper, mid, lower


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[list[float], list[float], list[float]]:
    if len(closes) < slow:
        return [0.0], [0.0], [0.0]

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)

    min_len = min(len(ema_fast), len(ema_slow))
    ema_fast = ema_fast[-min_len:]
    ema_slow = ema_slow[-min_len:]

    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal)

    min_len2 = min(len(macd_line), len(signal_line))
    macd_line = macd_line[-min_len2:]
    signal_line = signal_line[-min_len2:]
    histogram = [m - s for m, s in zip(macd_line, signal_line)]

    return macd_line, signal_line, histogram


def vwap(klines: list[dict]) -> list[float]:
    vwap_vals = []
    cum_pv = 0.0
    cum_vol = 0.0

    for k in klines:
        typical = (k["high"] + k["low"] + k["close"]) / 3
        pv = typical * k["volume"]
        cum_pv += pv
        cum_vol += k["volume"]
        vwap_vals.append(cum_pv / cum_vol if cum_vol > 0 else typical)

    return vwap_vals


def supertrend(klines: list[dict], period: int = ST_PERIOD, multiplier: float = ST_MULTIPLIER) -> tuple[list[float], list[bool]]:
    """SuperTrend: değerler ve yön (True=UP)."""
    atr_vals = atr(klines, period)
    upper_band: list[float] = []
    lower_band: list[float] = []
    st_vals: list[float] = []
    trend: list[bool] = []

    for i in range(len(klines)):
        if i < period:
            upper_band.append(klines[i]["high"])
            lower_band.append(klines[i]["low"])
            st_vals.append(klines[i]["close"])
            trend.append(True)
            continue

        mid = (klines[i]["high"] + klines[i]["low"]) / 2
        atr_i = atr_vals[i - period] if i - period < len(atr_vals) else atr_vals[-1]
        ub = mid + multiplier * atr_i
        lb = mid - multiplier * atr_i

        if i == period:
            upper_band.append(ub)
            lower_band.append(lb)
            st_vals.append(ub if klines[i]["close"] <= ub else lb)
            trend.append(klines[i]["close"] > ub)
        else:
            if klines[i]["close"] > upper_band[-1]:
                trend.append(True)
            elif klines[i]["close"] < lower_band[-1]:
                trend.append(False)
            else:
                trend.append(trend[-1])

            if trend[-1]:
                upper_band.append(ub)
                lower_band.append(max(lb, lower_band[-1]))
                st_vals.append(lower_band[-1])
            else:
                upper_band.append(min(ub, upper_band[-1]))
                lower_band.append(lb)
                st_vals.append(upper_band[-1])

    return st_vals, trend


def ichimoku(klines: list[dict]) -> dict:
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    closes = [k["close"] for k in klines]

    def donchian(h, l, p):
        out = []
        for i in range(len(h)):
            if i < p - 1:
                out.append((h[i] + l[i]) / 2)
            else:
                out.append((max(h[i - p + 1 : i + 1]) + min(l[i - p + 1 : i + 1])) / 2)
        return out

    return {
        "tenkan": donchian(highs, lows, ICHI_TENKAN),
        "kijun": donchian(highs, lows, ICHI_KIJUN),
        "senkou_a": [(t + k) / 2 for t, k in zip(donchian(highs, lows, ICHI_TENKAN), donchian(highs, lows, ICHI_KIJUN))],
        "senkou_b": donchian(highs, lows, ICHI_SENKOU),
        "chikou": closes[:-26] if len(closes) > 26 else closes,
    }


def _wma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    weights = list(range(1, period + 1))
    total_w = sum(weights)
    return sum(values[-(period - i)] * weights[i] for i in range(period)) / total_w


def wma_series(values: list[float], period: int) -> list[float]:
    out = []
    weights = list(range(1, period + 1))
    weight_sum = sum(weights)
    for i in range(len(values)):
        if i < period - 1:
            w = weights[: i + 1]
            ws = sum(w)
            out.append(sum(values[j] * w[j] for j in range(len(w))) / ws)
        else:
            window = values[i - period + 1 : i + 1]
            out.append(sum(window[j] * weights[j] for j in range(period)) / weight_sum)
    return out


def hull_ma(values: list[float], period: int = HMA_PERIOD) -> list[float]:
    half_period = period // 2
    sqrt_period = int(math.sqrt(period))
    wma_half = wma_series(values, half_period)
    wma_full = wma_series(values, period)
    min_len = min(len(wma_half), len(wma_full))
    raw_hma = [2 * h - f for h, f in zip(wma_half[-min_len:], wma_full[-min_len:])]
    return wma_series(raw_hma, sqrt_period)


def get_htf_trend(symbol: str = SYMBOL) -> dict:
    try:
        htf_klines = fetch_klines(symbol, HTF_INTERVAL, limit=200)
        closes = [k["close"] for k in htf_klines]

        e20 = ema(closes, 20)
        e50 = ema(closes, 50)
        adx_vals = adx(htf_klines, 14)
        _, st_trend = supertrend(htf_klines, ST_PERIOD, ST_MULTIPLIER)

        trend_direction = "NEUTRAL"
        if e20[-1] > e50[-1] and st_trend[-1]:
            trend_direction = "UP"
        elif e20[-1] < e50[-1] and not st_trend[-1]:
            trend_direction = "DOWN"

        return {
            "direction": trend_direction,
            "strength": adx_vals[-1] if adx_vals else 25.0,
            "ema20": e20[-1] if e20 else closes[-1],
            "ema50": e50[-1] if e50 else closes[-1],
            "supertrend": "UP" if st_trend[-1] else "DOWN",
        }
    except Exception as e:
        print(f"[btc_1h_analiz7_algo] HTF trend alınamadı: {e}", flush=True)
        return {"direction": "NEUTRAL", "strength": 25.0, "ema20": 0, "ema50": 0, "supertrend": "NEUTRAL"}


def algo_a1_rsi_macd_ema(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines]

    rsi_vals = rsi(closes, 14)
    rsi_current = rsi_vals[-1] if rsi_vals else 50.0

    macd_line, signal_line, histogram = macd(closes, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    macd_current = macd_line[-1] if macd_line else 0.0
    signal_current = signal_line[-1] if signal_line else 0.0
    hist_current = histogram[-1] if histogram else 0.0
    hist_prev = histogram[-2] if len(histogram) > 1 else hist_current

    e9 = ema(closes, EMA_SHORT)
    e20 = ema(closes, EMA_TREND_FAST)
    e50 = ema(closes, EMA_TREND_SLOW) if len(closes) >= EMA_TREND_SLOW else e20
    hma_vals = hull_ma(closes, HMA_PERIOD)
    hma_current = hma_vals[-1] if hma_vals else closes[-1]

    if rsi_current < RSI_OVERSOLD:
        rsi_vote = +1
    elif rsi_current > RSI_OVERBOUGHT:
        rsi_vote = -1
    else:
        rsi_vote = 0

    if macd_current > signal_current and hist_current > hist_prev and hist_current > 0:
        macd_vote = +1
    elif macd_current < signal_current and hist_current < hist_prev and hist_current < 0:
        macd_vote = -1
    else:
        macd_vote = 0

    if e9[-1] > e20[-1] > e50[-1] and closes[-1] > hma_current:
        trend_vote = +1
    elif e9[-1] < e20[-1] < e50[-1] and closes[-1] < hma_current:
        trend_vote = -1
    else:
        trend_vote = 0

    score = rsi_vote + macd_vote + trend_vote
    vote = +1 if score >= 2 else -1 if score <= -2 else 0

    arr = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    return vote, (
        f"A1 {arr}  RSI:{rsi_current:.1f}  "
        f"MACD:{'↑' if macd_vote > 0 else '↓' if macd_vote < 0 else '→'}  "
        f"EMA/HMA:{'↑' if trend_vote > 0 else '↓' if trend_vote < 0 else '→'}"
    )


def algo_trend(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines]

    e20 = ema(closes, EMA_TREND_FAST)
    e50 = ema(closes, EMA_TREND_SLOW) if len(closes) >= EMA_TREND_SLOW else ema(closes, EMA_TREND_FAST)

    adx_vals = adx(klines, ADX_PERIOD)
    adx_current = adx_vals[-1] if adx_vals else 25.0
    _, st_trend = supertrend(klines, ST_PERIOD, ST_MULTIPLIER)
    st_current = st_trend[-1] if st_trend else True

    cross = e20[-1] - e50[-1]
    slope_20 = e20[-1] - e20[-5] if len(e20) >= 5 else 0
    slope_50 = e50[-1] - e50[-5] if len(e50) >= 5 else 0

    pct = cross / closes[-1] * 100
    strength_ok = adx_current >= ADX_MIN

    if cross > 0 and slope_20 > 0 and slope_50 > 0 and st_current and strength_ok:
        return +1, f"Trend ↑  E20>E50 ({pct:+.2f}%) ST:UP ADX:{adx_current:.1f}"
    if cross < 0 and slope_20 < 0 and slope_50 < 0 and not st_current and strength_ok:
        return -1, f"Trend ↓  E20<E50 ({pct:+.2f}%) ST:DOWN ADX:{adx_current:.1f}"
    return 0, f"Trend →  karışık ({pct:+.2f}%) ST:{'UP' if st_current else 'DOWN'} ADX:{adx_current:.1f}"


def algo_mr(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines]

    rsi_vals = rsi(closes, 14)
    rsi_current = rsi_vals[-1] if rsi_vals else 50.0

    upper, mid, lower = bollinger(closes, BB_PERIOD, BB_STD)
    price = closes[-1]

    vwap_vals = vwap(klines)
    vwap_current = vwap_vals[-1] if vwap_vals else price

    if rsi_current <= RSI_OVERSOLD:
        rsi_vote = +1
    elif rsi_current >= RSI_OVERBOUGHT:
        rsi_vote = -1
    else:
        rsi_vote = 0

    bb_range = upper[-1] - lower[-1]
    bb_position = (price - lower[-1]) / bb_range if bb_range > 0 else 0.5

    if bb_position <= 0.05:
        bb_vote = +1
    elif bb_position >= 0.95:
        bb_vote = -1
    else:
        bb_vote = 0

    vwap_vote = +1 if price < vwap_current * 0.995 else -1 if price > vwap_current * 1.005 else 0

    rsi_min = min(rsi_vals[-14:]) if len(rsi_vals) >= 14 else 30
    rsi_max = max(rsi_vals[-14:]) if len(rsi_vals) >= 14 else 70
    stoch_rsi = (rsi_current - rsi_min) / (rsi_max - rsi_min) if rsi_max - rsi_min > 0 else 0.5
    stoch_vote = +1 if stoch_rsi < 0.2 else -1 if stoch_rsi > 0.8 else 0

    score = rsi_vote + bb_vote + vwap_vote + stoch_vote
    vote = +1 if score >= 2 else -1 if score <= -2 else 0

    arr = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    return vote, f"MR {arr}  RSI:{rsi_current:.1f}  BB:{bb_position:.2f}  StochRSI:{stoch_rsi:.2f}"


def algo_orderflow_v2(klines: list[dict], ob: dict) -> tuple[int, str]:
    window = klines[-20:]

    cvd_delta = sum(k["volume"] if k["close"] >= k["open"] else -k["volume"] for k in window)
    total_vol = sum(k["volume"] for k in window) or 1
    cvd_r = cvd_delta / total_vol

    bids = ob.get("bids", [])
    asks = ob.get("asks", [])

    bid_qty = sum(float(b[1]) for b in bids[:50])
    ask_qty = sum(float(a[1]) for a in asks[:50])
    ob_r = (bid_qty - ask_qty) / (bid_qty + ask_qty) if (bid_qty + ask_qty) > 0 else 0

    best_bid = float(bids[0][0]) if bids else 0
    best_ask = float(asks[0][0]) if asks else 0
    spread = (best_ask - best_bid) / ((best_bid + best_ask) / 2) * 100 if best_bid > 0 else 0

    bid_imbalance = sum(float(b[1]) for b in bids[:5])
    ask_imbalance = sum(float(a[1]) for a in asks[:5])
    imbalance_r = (bid_imbalance - ask_imbalance) / (bid_imbalance + ask_imbalance) if (bid_imbalance + ask_imbalance) > 0 else 0

    cvd_v = +1 if cvd_r > 0.05 else -1 if cvd_r < -0.05 else 0
    ob_v = +1 if ob_r > OB_RATIO_THRESHOLD else -1 if ob_r < -OB_RATIO_THRESHOLD else 0
    imb_v = +1 if imbalance_r > 0.15 else -1 if imbalance_r < -0.15 else 0

    votes_of = [cvd_v, ob_v, imb_v]
    non_zero = [v for v in votes_of if v != 0]
    if not non_zero:
        vote = 0
    elif len(set(non_zero)) == 1:
        vote = non_zero[0]
    elif ob_v == imb_v and ob_v != 0:
        vote = ob_v
    else:
        vote = ob_v

    tag = "v2" if len(set(non_zero)) > 1 else ""
    arr = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    return vote, f"OF{tag} {arr}  CVD:{cvd_r:+.3f}  OB:{ob_r:+.3f}  Imb:{imbalance_r:+.3f}"


def algo_ichimoku(klines: list[dict]) -> tuple[int, str]:
    if len(klines) < ICHI_SENKOU + 26:
        return 0, "Ichi →  yetersiz veri"

    ichi = ichimoku(klines)
    price = klines[-1]["close"]
    tenkan = ichi["tenkan"][-1] if ichi["tenkan"] else price
    kijun = ichi["kijun"][-1] if ichi["kijun"] else price
    senkou_a = ichi["senkou_a"][-26] if len(ichi["senkou_a"]) > 26 else price
    senkou_b = ichi["senkou_b"][-26] if len(ichi["senkou_b"]) > 26 else price

    cloud_top = max(senkou_a, senkou_b)
    cloud_bottom = min(senkou_a, senkou_b)
    tk_cross = tenkan - kijun
    above_cloud = price > cloud_top
    below_cloud = price < cloud_bottom
    chikou = ichi["chikou"][-1] if ichi["chikou"] else price
    chikou_ok = chikou > price if above_cloud else chikou < price if below_cloud else True

    if above_cloud and tk_cross > 0 and chikou_ok:
        vote = +1
    elif below_cloud and tk_cross < 0 and chikou_ok:
        vote = -1
    else:
        vote = 0

    arr = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    cloud_pos = "üst" if above_cloud else "alt" if below_cloud else "içinde"
    return vote, f"Ichi {arr}  TK:{tk_cross:+.2f}  Cloud:{cloud_pos}  Chikou:{'OK' if chikou_ok else 'ZAYIF'}"


def algo_volume(klines: list[dict]) -> tuple[int, str]:
    if len(klines) < VOLUME_PERIOD + 1:
        return 0, "Vol →  yetersiz veri"

    volumes = [k["volume"] for k in klines]
    current_vol = volumes[-1]
    avg_vol = sum(volumes[-VOLUME_PERIOD:]) / VOLUME_PERIOD

    vol_trend = sum(1 for i in range(-5, 0) if volumes[i] > avg_vol)
    price_change = (klines[-1]["close"] - klines[-2]["close"]) / klines[-2]["close"] * 100
    vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0

    quote_volumes = [k.get("quote_volume", k["volume"] * k["close"]) for k in klines]
    current_qv = quote_volumes[-1]
    avg_qv = sum(quote_volumes[-VOLUME_PERIOD:]) / VOLUME_PERIOD
    qv_ratio = current_qv / avg_qv if avg_qv > 0 else 1.0

    if vol_ratio >= VOLUME_MIN_RATIO and qv_ratio >= VOLUME_MIN_RATIO * 0.9 and vol_trend >= 3:
        if price_change > 0:
            vote = +1
        elif price_change < 0:
            vote = -1
        else:
            vote = 0
    else:
        vote = 0

    arr = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    return vote, f"Vol {arr}  ratio:{vol_ratio:.2f}x  QV:{qv_ratio:.2f}x  trend:{vol_trend}/5"


def recent_momentum(klines: list[dict], n: int = MOMENTUM_BARS) -> str:
    if len(klines) < n + 1:
        return "MIXED"
    closed = klines[-(n + 1) : -1]
    ups = sum(1 for k in closed if k["close"] >= k["open"])
    if ups >= n - 1:
        return "UP"
    if ups <= 1:
        return "DOWN"
    return "MIXED"


def calculate_position_size(
    direction: str,
    atr_val: float,
    price: float,
    portfolio_value: float = DEFAULT_PORTFOLIO,
) -> float:
    if atr_val <= 0 or price <= 0:
        return BASE_TRADE_AMOUNT

    risk_per_trade = portfolio_value * 0.015
    stop_distance = atr_val * SL_MULTIPLIER
    position_size = risk_per_trade / stop_distance * price

    max_position = portfolio_value * MAX_POSITION_PCT
    position_size = min(position_size, max_position, BASE_TRADE_AMOUNT * 2.5)
    position_size = max(position_size, BASE_TRADE_AMOUNT * 0.75)

    return round(position_size, 2)


def calculate_levels(price: float, atr_val: float, direction: str) -> dict:
    if direction == "UP":
        sl = price - atr_val * SL_MULTIPLIER
        tp = price + atr_val * TP_MULTIPLIER
        trail_activation = price + atr_val * TRAILING_ACTIVATION
    else:
        sl = price + atr_val * SL_MULTIPLIER
        tp = price - atr_val * TP_MULTIPLIER
        trail_activation = price - atr_val * TRAILING_ACTIVATION

    return {
        "stop_loss": round(sl, 2),
        "take_profit": round(tp, 2),
        "trailing_activation": round(trail_activation, 2),
        "trailing_step": round(atr_val * TRAILING_STEP, 2),
        "risk_reward": round(TP_MULTIPLIER / SL_MULTIPLIER, 2),
    }


@dataclass
class SignalResult:
    direction: str | None
    consensus: int
    amount: float
    entry_price: float
    momentum: str
    votes: list[int]
    labels: list[str]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    atr: float = 0.0
    adx: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_activation: float = 0.0
    trailing_step: float = 0.0
    risk_reward: float = 0.0
    htf_trend: str = "NEUTRAL"
    htf_strength: float = 0.0
    htf_supertrend: str = "NEUTRAL"
    volume_ratio: float = 0.0
    supertrend_direction: bool = True
    skip_reason: str | None = None
    raw_direction: str | None = None
    paper_mode: bool = PAPER_TRADING

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "consensus": self.consensus,
            "amount": self.amount,
            "entry_price": self.entry_price,
            "momentum": self.momentum,
            "votes": self.votes,
            "labels": self.labels,
            "timestamp": self.timestamp,
            "atr": self.atr,
            "adx": self.adx,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "trailing_activation": self.trailing_activation,
            "trailing_step": self.trailing_step,
            "risk_reward": self.risk_reward,
            "htf_trend": self.htf_trend,
            "htf_strength": self.htf_strength,
            "htf_supertrend": self.htf_supertrend,
            "volume_ratio": self.volume_ratio,
            "supertrend": "UP" if self.supertrend_direction else "DOWN",
            "skip_reason": self.skip_reason,
            "raw_direction": self.raw_direction,
            "paper_mode": self.paper_mode,
        }


def analyze(
    klines: list[dict] | None = None,
    orderbook: dict | None = None,
    *,
    symbol: str = SYMBOL,
    momentum_filter: bool | None = None,
    adx_filter: bool | None = None,
    volume_filter: bool | None = None,
    htf_confirmation: bool | None = None,
    supertrend_filter: bool | None = None,
    portfolio_value: float = DEFAULT_PORTFOLIO,
) -> SignalResult | None:
    if momentum_filter is None:
        momentum_filter = MOMENTUM_FILTER_ENABLED
    if adx_filter is None:
        adx_filter = ADX_FILTER_ENABLED
    if volume_filter is None:
        volume_filter = VOLUME_FILTER_ENABLED
    if htf_confirmation is None:
        htf_confirmation = HTF_CONFIRMATION
    if supertrend_filter is None:
        supertrend_filter = SUPERTREND_FILTER

    try:
        if klines is None:
            klines = fetch_klines(symbol, INTERVAL, 300)
        if orderbook is None:
            orderbook = fetch_orderbook(symbol, OB_DEPTH)
    except Exception as e:
        print(f"[btc_1h_analiz7_algo] Veri hatası: {e}", flush=True)
        return None

    atr_vals = atr(klines, ATR_PERIOD)
    atr_current = atr_vals[-1] if atr_vals else 0.0

    adx_vals = adx(klines, ADX_PERIOD)
    adx_current = adx_vals[-1] if adx_vals else 25.0

    volumes = [k["volume"] for k in klines]
    volume_ratio = (
        volumes[-1] / (sum(volumes[-VOLUME_PERIOD:]) / VOLUME_PERIOD)
        if len(volumes) >= VOLUME_PERIOD else 1.0
    )

    _, st_trend = supertrend(klines, ST_PERIOD, ST_MULTIPLIER)
    st_current = st_trend[-1] if st_trend else True

    htf_data = get_htf_trend(symbol) if htf_confirmation else {
        "direction": "NEUTRAL", "strength": 25.0, "supertrend": "NEUTRAL",
    }

    v1, l1 = algo_a1_rsi_macd_ema(klines)
    v2, l2 = algo_trend(klines)
    v3, l3 = algo_mr(klines)
    v4, l4 = algo_orderflow_v2(klines, orderbook)
    v5, l5 = algo_volume(klines)
    v6, l6 = algo_ichimoku(klines)

    votes = [v1, v2, v3, v4, v5, v6]
    labels = [l1, l2, l3, l4, l5, l6]

    up_v = sum(1 for v in votes if v > 0)
    down_v = sum(1 for v in votes if v < 0)
    entry_price = klines[-1]["close"]
    momentum = recent_momentum(klines)

    if up_v >= MIN_CONSENSUS and up_v > down_v:
        direction, consensus = "UP", up_v
    elif down_v >= MIN_CONSENSUS and down_v > up_v:
        direction, consensus = "DOWN", down_v
    else:
        return SignalResult(
            direction=None,
            consensus=max(up_v, down_v),
            amount=0.0,
            entry_price=entry_price,
            momentum=momentum,
            votes=votes,
            labels=labels,
            atr=atr_current,
            adx=adx_current,
            volume_ratio=volume_ratio,
            htf_trend=htf_data["direction"],
            htf_strength=htf_data["strength"],
            htf_supertrend=htf_data.get("supertrend", "NEUTRAL"),
            supertrend_direction=st_current,
            skip_reason=f"Konsensüs yok ({max(up_v, down_v)}/{TOTAL_ALGOS})",
        )

    if momentum_filter:
        if direction == "DOWN" and momentum == "UP":
            return SignalResult(
                direction=None, consensus=consensus, amount=0.0,
                entry_price=entry_price, momentum=momentum, votes=votes, labels=labels,
                atr=atr_current, adx=adx_current, volume_ratio=volume_ratio,
                htf_trend=htf_data["direction"], htf_strength=htf_data["strength"],
                raw_direction="DOWN",
                skip_reason=f"Momentum filtresi: Son {MOMENTUM_BARS} mum yükseliş, DOWN engellendi",
            )
        if direction == "UP" and momentum == "DOWN":
            return SignalResult(
                direction=None, consensus=consensus, amount=0.0,
                entry_price=entry_price, momentum=momentum, votes=votes, labels=labels,
                atr=atr_current, adx=adx_current, volume_ratio=volume_ratio,
                htf_trend=htf_data["direction"], htf_strength=htf_data["strength"],
                raw_direction="UP",
                skip_reason=f"Momentum filtresi: Son {MOMENTUM_BARS} mum düşüş, UP engellendi",
            )

    if adx_filter and adx_current < ADX_MIN:
        return SignalResult(
            direction=None, consensus=consensus, amount=0.0,
            entry_price=entry_price, momentum=momentum, votes=votes, labels=labels,
            atr=atr_current, adx=adx_current, volume_ratio=volume_ratio,
            htf_trend=htf_data["direction"], htf_strength=htf_data["strength"],
            raw_direction=direction,
            skip_reason=f"ADX filtresi: Trend gücü yetersiz ({adx_current:.1f} < {ADX_MIN})",
        )

    if volume_filter and volume_ratio < VOLUME_MIN_RATIO:
        return SignalResult(
            direction=None, consensus=consensus, amount=0.0,
            entry_price=entry_price, momentum=momentum, votes=votes, labels=labels,
            atr=atr_current, adx=adx_current, volume_ratio=volume_ratio,
            htf_trend=htf_data["direction"], htf_strength=htf_data["strength"],
            raw_direction=direction,
            skip_reason=f"Hacim filtresi: Hacim yetersiz ({volume_ratio:.2f}x < {VOLUME_MIN_RATIO}x)",
        )

    if supertrend_filter:
        if direction == "DOWN" and st_current:
            return SignalResult(
                direction=None, consensus=consensus, amount=0.0,
                entry_price=entry_price, momentum=momentum, votes=votes, labels=labels,
                atr=atr_current, adx=adx_current, volume_ratio=volume_ratio,
                supertrend_direction=st_current,
                htf_trend=htf_data["direction"], htf_strength=htf_data["strength"],
                htf_supertrend=htf_data.get("supertrend", "NEUTRAL"),
                raw_direction="DOWN",
                skip_reason="SuperTrend filtresi: ST UP, DOWN engellendi",
            )
        if direction == "UP" and not st_current:
            return SignalResult(
                direction=None, consensus=consensus, amount=0.0,
                entry_price=entry_price, momentum=momentum, votes=votes, labels=labels,
                atr=atr_current, adx=adx_current, volume_ratio=volume_ratio,
                supertrend_direction=st_current,
                htf_trend=htf_data["direction"], htf_strength=htf_data["strength"],
                htf_supertrend=htf_data.get("supertrend", "NEUTRAL"),
                raw_direction="UP",
                skip_reason="SuperTrend filtresi: ST DOWN, UP engellendi",
            )

    if htf_confirmation and htf_data["direction"] != "NEUTRAL":
        if direction == "DOWN" and htf_data["direction"] == "UP" and htf_data["strength"] > 25:
            return SignalResult(
                direction=None, consensus=consensus, amount=0.0,
                entry_price=entry_price, momentum=momentum, votes=votes, labels=labels,
                atr=atr_current, adx=adx_current, volume_ratio=volume_ratio,
                htf_trend=htf_data["direction"], htf_strength=htf_data["strength"],
                raw_direction="DOWN",
                skip_reason=f"HTF onay: 4H trend UP (ADX:{htf_data['strength']:.1f}), DOWN engellendi",
            )
        if direction == "UP" and htf_data["direction"] == "DOWN" and htf_data["strength"] > 25:
            return SignalResult(
                direction=None, consensus=consensus, amount=0.0,
                entry_price=entry_price, momentum=momentum, votes=votes, labels=labels,
                atr=atr_current, adx=adx_current, volume_ratio=volume_ratio,
                htf_trend=htf_data["direction"], htf_strength=htf_data["strength"],
                raw_direction="UP",
                skip_reason=f"HTF onay: 4H trend DOWN (ADX:{htf_data['strength']:.1f}), UP engellendi",
            )

    amount = calculate_position_size(direction, atr_current, entry_price, portfolio_value)
    levels = calculate_levels(entry_price, atr_current, direction)

    return SignalResult(
        direction=direction,
        consensus=consensus,
        amount=amount,
        entry_price=entry_price,
        momentum=momentum,
        votes=votes,
        labels=labels,
        atr=atr_current,
        adx=adx_current,
        volume_ratio=volume_ratio,
        htf_trend=htf_data["direction"],
        htf_strength=htf_data["strength"],
        htf_supertrend=htf_data.get("supertrend", "NEUTRAL"),
        supertrend_direction=st_current,
        stop_loss=levels["stop_loss"],
        take_profit=levels["take_profit"],
        trailing_activation=levels["trailing_activation"],
        trailing_step=levels["trailing_step"],
        risk_reward=levels["risk_reward"],
    )


def format_signal(result: SignalResult | None) -> str:
    if result is None:
        return "❌ Veri alınamadı"

    if result.direction is None:
        extra = result.skip_reason or f"Konsensüs yok ({result.consensus}/{TOTAL_ALGOS})"
        return (
            f"⛔ SİNYAL YOK — {extra}\n"
            f"   Momentum: {result.momentum} | ATR: {result.atr:.2f} | ADX: {result.adx:.1f}\n"
            f"   HTF: {result.htf_trend} (ADX:{result.htf_strength:.1f}) | ST: {'UP' if result.supertrend_direction else 'DOWN'}\n"
            f"   Vol: {result.volume_ratio:.2f}x"
        )

    icons = " ".join("🟢" if v > 0 else "🔴" if v < 0 else "⚪" for v in result.votes)
    mode = "📘 PAPER" if result.paper_mode else "💰 LIVE"

    return (
        f"{'🟢 LONG' if result.direction == 'UP' else '🔴 SHORT'} "
        f"({result.consensus}/{TOTAL_ALGOS}) {mode}\n"
        f"💵 Miktar: ${result.amount:.2f} | Giriş: {result.entry_price:,.2f}\n"
        f"🛑 SL: {result.stop_loss:,.2f} | 🎯 TP: {result.take_profit:,.2f} | R:R {result.risk_reward:.1f}\n"
        f"📊 ATR: {result.atr:.2f} | ADX: {result.adx:.1f} | Vol: {result.volume_ratio:.2f}x\n"
        f"📈 HTF: {result.htf_trend} (ADX:{result.htf_strength:.1f}) | Momentum: {result.momentum}\n"
        f"{icons}\n" + " | ".join(result.labels)
    )


def log_signal(result: SignalResult | None, filename: str = "btc_1h_analiz7_signals.log") -> None:
    if result is None:
        return

    log_entry = {
        "timestamp": result.timestamp,
        "direction": result.direction,
        "consensus": result.consensus,
        "entry": result.entry_price,
        "amount": result.amount,
        "atr": result.atr,
        "adx": result.adx,
        "htf": result.htf_trend,
        "skip_reason": result.skip_reason,
    }

    with open(filename, "a") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    print("=" * 60)
    print("BTC/USDT 1H Gelişmiş Sinyal Motoru v2.0 — 7. Analiz")
    print("=" * 60)

    sig = analyze()
    print(format_signal(sig))

    if sig:
        print("\n" + "-" * 40)
        print("JSON Çıktı:")
        print(json.dumps(sig.to_dict(), ensure_ascii=False, indent=2))
        log_signal(sig)
