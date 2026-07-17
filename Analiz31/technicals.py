"""
Teknik indikatörler
"""

from typing import List, Tuple


def ema(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return [sum(values) / len(values)] * len(values) if values else []

    k = 2.0 / (period + 1)
    result = [0.0] * len(values)
    result[period - 1] = sum(values[:period]) / period

    for i in range(period, len(values)):
        result[i] = values[i] * k + result[i - 1] * (1 - k)

    return result


def rsi(closes: List[float], period: int = 5) -> float:
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


def macd(closes: List[float]) -> Tuple[float, float]:
    if len(closes) < 26:
        return 0.0, 0.0

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    macd_line = [ema12[i] - ema26[i] for i in range(len(closes))]
    signal = ema(macd_line[25:], 9)

    return macd_line[-1], signal[-1] if signal else 0.0


def atr(klines: List[dict], period: int = 14) -> List[float]:
    trs = []
    for i in range(1, len(klines)):
        tr = max(
            klines[i]["high"] - klines[i]["low"],
            abs(klines[i]["high"] - klines[i - 1]["close"]),
            abs(klines[i]["low"] - klines[i - 1]["close"]),
        )
        trs.append(tr)

    if len(trs) < period:
        return [sum(trs) / len(trs)] * len(trs) if trs else [0.0]

    atr_vals = [sum(trs[:period]) / period]
    for i in range(period, len(trs)):
        atr_vals.append((atr_vals[-1] * (period - 1) + trs[i]) / period)

    return atr_vals


def adx(klines: List[dict], period: int = 14) -> Tuple[float, float, float]:
    if len(klines) < period * 2:
        return 25.0, 25.0, 25.0

    plus_dm, minus_dm, tr_list = [], [], []
    for i in range(1, len(klines)):
        h, l = klines[i]["high"], klines[i]["low"]
        ph, pl, pc = klines[i-1]["high"], klines[i-1]["low"], klines[i-1]["close"]

        up, down = h - ph, pl - l
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))

    def wilder(vals, p):
        res = [sum(vals[:p])]
        for i in range(p, len(vals)):
            res.append(res[-1] - res[-1] / p + vals[i])
        return res

    atr14 = wilder(tr_list, period)
    plus14 = wilder(plus_dm, period)
    minus14 = wilder(minus_dm, period)

    dx_list = []
    for i in range(len(atr14)):
        if atr14[i] == 0:
            dx_list.append(0.0)
            continue
        pdi = 100 * plus14[i] / atr14[i]
        mdi = 100 * minus14[i] / atr14[i]
        dx = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) > 0 else 0.0
        dx_list.append(dx)

    adx_val = sum(dx_list[-period:]) / period if len(dx_list) >= period else 25.0
    last_atr = atr14[-1]
    pdi = 100 * plus14[-1] / last_atr if last_atr else 25.0
    mdi = 100 * minus14[-1] / last_atr if last_atr else 25.0

    return adx_val, pdi, mdi


def higher_timeframe_bias(klines_4h: List[dict], klines_1d: List[dict]) -> dict:
    bias = {"4h": "NEUTRAL", "1d": "NEUTRAL", "score": 0}

    if len(klines_4h) >= 21:
        closes_4h = [k["close"] for k in klines_4h]
        ema9_4h = ema(closes_4h, 9)[-1]
        ema21_4h = ema(closes_4h, 21)[-1]

        if ema9_4h > ema21_4h:
            bias["4h"] = "BULLISH"
            bias["score"] += 1
        elif ema9_4h < ema21_4h:
            bias["4h"] = "BEARISH"
            bias["score"] -= 1

    if len(klines_1d) >= 9:
        closes_1d = [k["close"] for k in klines_1d]
        ema9_1d = ema(closes_1d, 9)[-1] if len(closes_1d) >= 9 else closes_1d[-1]

        if closes_1d[-1] > ema9_1d:
            bias["1d"] = "BULLISH"
            bias["score"] += 2
        else:
            bias["1d"] = "BEARISH"
            bias["score"] -= 2

    return bias
