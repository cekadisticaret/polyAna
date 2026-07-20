"""
Analiz31 MR skorlama (Yama v1.2 — trend rejimi + SOL filtresi + yüksek gate)
"""

from typing import Dict, List, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo
from config import (
    _MR_UP_GATE, _MR_DOWN_GATE,
    _MR_UP_GATE_KILLZONE, _MR_DOWN_GATE_KILLZONE,
    _KILL_ZONE_ET_HOURS, _CRASH_EMA50_PCT,
    _GATE_FLOOR, _TREND_REGIME_ADX, _TREND_REGIME_DI_SPREAD,
    _SOL_DOWN_EXTRA_GATE, _SOL_MOMENTUM_CVD_MIN, _SOL_MOMENTUM_RSI_MIN,
    _SOL_ALLOWED_HOURS_IST,
)


def get_kill_zone_adjustment() -> Tuple[int, int]:
    et_hour = datetime.now(ZoneInfo("America/New_York")).hour
    if et_hour in _KILL_ZONE_ET_HOURS:
        return _MR_UP_GATE_KILLZONE, _MR_DOWN_GATE_KILLZONE
    return _MR_UP_GATE, _MR_DOWN_GATE


def is_trend_regime(features: Dict) -> Tuple[bool, str]:
    """Güçlü trend rejiminde MR tamamen kapalı."""
    f1h = features.get("1h", {})
    if not f1h.get("valid"):
        return False, ""

    adx = f1h.get("adx", 0)
    plus_di = f1h.get("plus_di", 25)
    minus_di = f1h.get("minus_di", 25)
    di_spread = abs(plus_di - minus_di)

    if adx >= _TREND_REGIME_ADX and di_spread >= _TREND_REGIME_DI_SPREAD:
        dir_label = "UPTREND" if plus_di > minus_di else "DOWNTREND"
        return True, (
            f"🚫 Trend rejimi (ADX:{adx:.0f}, DIΔ:{di_spread:.0f}, {dir_label}) — MR kapalı"
        )
    return False, ""


def sol_symbol_hour_allowed(symbol: str, hour_ist: int | None) -> Tuple[bool, str]:
    """SOL yalnızca belirli İST saatlerinde MR açar."""
    if symbol != "SOLUSDT" or hour_ist is None:
        return True, "OK"
    if hour_ist not in _SOL_ALLOWED_HOURS_IST:
        return False, f"🚫 SOL — {hour_ist:02d}:00 İST MR penceresi dışı"
    return True, "OK"


def short_term_momentum_up(features: Dict) -> bool:
    """Kısa vadeli yukarı momentum — SOL DOWN için engel."""
    f1h = features.get("1h", {})
    f15m = features.get("15m", {})
    cvd_5m, cvd_delta = _cvd_momentum(features)

    if cvd_5m > _SOL_MOMENTUM_CVD_MIN or cvd_delta > 0.01:
        return True
    if f15m.get("valid") and f15m.get("macd_bull"):
        return True
    if f1h.get("rsi", 50) > _SOL_MOMENTUM_RSI_MIN:
        return True
    if f1h.get("streak_dir") == 1 and f1h.get("streak", 0) >= 2:
        return True
    if f1h.get("current", 0) > f1h.get("ema9", 0) > f1h.get("ema21", 0):
        return True
    return False


def get_dynamic_gates(features: Dict, symbol: str = "") -> Tuple[int, int]:
    """Piyasa rejimine göre dinamik gate'ler — taban 75, yalnızca yukarı ayarlanır."""
    f1h = features.get("1h", {})
    htf = features.get("htf_bias", {})

    base_up, base_down = get_kill_zone_adjustment()
    htf_score = htf.get("score", 0)

    if htf_score >= 2:
        base_down += 15
    elif htf_score <= -2:
        base_up += 15

    adx = f1h.get("adx", 20)
    if adx > 35:
        base_up += 10
        base_down += 10
    elif adx > 25:
        base_up += 5
        base_down += 5

    plus_di = f1h.get("plus_di", 25)
    minus_di = f1h.get("minus_di", 25)
    di_spread = abs(plus_di - minus_di)

    if di_spread > 15:
        if plus_di > minus_di:
            base_down += 10
        else:
            base_up += 10

    if symbol == "SOLUSDT":
        base_down += _SOL_DOWN_EXTRA_GATE

    return max(_GATE_FLOOR, base_up), max(_GATE_FLOOR, base_down)


def _trend_filter(features: Dict, direction: str) -> Tuple[bool, str]:
    """Trend karşıtı MR'ı engelle."""
    f1h = features.get("1h", {})
    htf = features.get("htf_bias", {})

    if not f1h.get("valid"):
        return False, "Invalid data"

    adx = f1h.get("adx", 0)
    plus_di = f1h.get("plus_di", 25)
    minus_di = f1h.get("minus_di", 25)
    htf_score = htf.get("score", 0)

    is_strong_trend = adx > 30 and abs(plus_di - minus_di) > 10

    if direction == "DOWN":
        if is_strong_trend and plus_di > minus_di:
            return False, f"🚫 Strong UPTREND (ADX:{adx:.0f}, +DI>{minus_di:.0f}) — DOWN blocked"
        if htf_score >= 3:
            return False, f"🚫 Bullish HTF (score:{htf_score}) — DOWN blocked"
        if short_term_momentum_up(features):
            return False, "🚫 Kısa vadeli momentum UP — DOWN blocked"

    elif direction == "UP":
        if is_strong_trend and minus_di > plus_di:
            return False, f"🚫 Strong DOWNTREND (ADX:{adx:.0f}, -DI>{plus_di:.0f}) — UP blocked"
        if htf_score <= -3:
            return False, f"🚫 Bearish HTF (score:{htf_score}) — UP blocked"

    return True, "OK"


def _cvd_momentum(features: Dict) -> Tuple[float, float]:
    """CVD değişim hızı (momentum)."""
    cvd_5m = features.get("cvd_5m", 0)
    cvd_30m = features.get("cvd_30m", 0)
    cvd_delta = cvd_5m - (cvd_30m / 6)
    return cvd_5m, cvd_delta


def mr_confluence_up(features: Dict, symbol: str = "") -> Tuple[int, List[str]]:
    f1h = features.get("1h", {})
    f15m = features.get("15m", {})
    htf = features.get("htf_bias", {})

    if not f1h.get("valid"):
        return 0, ["Invalid 1h data"]

    allowed, reason = _trend_filter(features, "UP")
    if not allowed:
        return -999, [reason]

    s = 0
    factors = []

    bullish_8 = f1h.get("bullish_8", 4)
    if bullish_8 == 0: s += 34
    elif bullish_8 == 1: s += 30
    elif bullish_8 == 2: s += 22
    elif bullish_8 == 3: s += 10
    elif bullish_8 == 4: s += 0
    elif bullish_8 == 5: s -= 8
    else: s -= 16
    factors.append(f"1h MR: {bullish_8}/8 bullish")

    rsi = f1h.get("rsi", 50)
    if rsi < 10: s += 30
    elif rsi < 20: s += 22
    elif rsi < 30: s += 13
    elif rsi < 40: s += 5
    elif rsi < 60: s += 0
    elif rsi < 70: s -= 5
    else: s -= 14
    factors.append(f"RSI5: {rsi:.0f}")

    streak = f1h.get("streak", 1)
    streak_dir = f1h.get("streak_dir", 1)
    if streak_dir == -1 and streak >= 5: s += 26; factors.append(f"Streak: {streak} down -> reversal")
    elif streak_dir == -1 and streak == 4: s += 18; factors.append("Streak: 4 down -> reversal")
    elif streak_dir == -1 and streak == 3: s += 9

    if f15m.get("valid"):
        if f15m.get("macd_bull") and not f1h.get("macd_bull"):
            s += 8; factors.append("15m MACD crossover (early)")
        if f15m.get("rsi", 50) < 30 and f1h.get("rsi", 50) < 40:
            s += 6; factors.append("15m+1h RSI oversold")
        if f15m.get("bullish_8", 4) <= 2 and f1h.get("bullish_8", 4) <= 3:
            s += 5; factors.append("15m+1h both oversold")

    cvd_5m, cvd_delta = _cvd_momentum(features)

    if cvd_5m < -0.10 and cvd_delta < -0.02:
        s += 16; factors.append(f"CVD5 capitulation accelerating: {cvd_5m*100:.0f}%")
    elif cvd_5m < -0.10:
        s += 10; factors.append(f"CVD5 capitulation: {cvd_5m*100:.0f}%")
    elif cvd_5m < -0.03:
        s += 7

    cvd_30m = features.get("cvd_30m", 0)
    if cvd_30m < -0.08: s += 8
    elif cvd_30m < -0.02: s += 3

    if cvd_delta > 0.05:
        s += 5; factors.append("CVD momentum loss (reversal early)")

    if rsi < 30 and cvd_5m < -0.05 and bullish_8 <= 2:
        s += 10; factors.append("⭐ Full confluence")

    htf_score = htf.get("score", 0)
    if htf_score >= 2:
        s += 5; factors.append("HTF bullish alignment")
    elif htf_score <= -2:
        s -= 8; factors.append("⚠️ HTF bearish — UP risky")

    return s, factors


def mr_confluence_down(features: Dict, symbol: str = "") -> Tuple[int, List[str]]:
    f1h = features.get("1h", {})
    f15m = features.get("15m", {})
    htf = features.get("htf_bias", {})

    if not f1h.get("valid"):
        return 0, ["Invalid 1h data"]

    if symbol == "SOLUSDT" and short_term_momentum_up(features):
        return -999, ["🚫 SOL DOWN — kısa vadeli momentum UP (HTF bearish olsa bile)"]

    allowed, reason = _trend_filter(features, "DOWN")
    if not allowed:
        return -999, [reason]

    s = 0
    factors = []

    bullish_8 = f1h.get("bullish_8", 4)
    if bullish_8 == 8: s += 34
    elif bullish_8 == 7: s += 30
    elif bullish_8 == 6: s += 22
    elif bullish_8 == 5: s += 10
    elif bullish_8 == 4: s += 0
    elif bullish_8 == 3: s -= 8
    else: s -= 16
    factors.append(f"1h MR-DOWN: {bullish_8}/8 bullish")

    rsi = f1h.get("rsi", 50)
    if rsi > 90: s += 30
    elif rsi > 80: s += 22
    elif rsi > 70: s += 13
    elif rsi > 60: s += 5
    elif rsi > 40: s += 0
    elif rsi > 30: s -= 5
    else: s -= 14
    factors.append(f"RSI5: {rsi:.0f}")

    streak = f1h.get("streak", 1)
    streak_dir = f1h.get("streak_dir", 1)
    if streak_dir == 1 and streak >= 5: s += 26; factors.append(f"Streak: {streak} up -> reversal DOWN")
    elif streak_dir == 1 and streak == 4: s += 18; factors.append("Streak: 4 up -> reversal DOWN")
    elif streak_dir == 1 and streak == 3: s += 9

    if f15m.get("valid"):
        if not f15m.get("macd_bull") and f1h.get("macd_bull"):
            s += 8; factors.append("15m MACD bearish cross")
        if f15m.get("rsi", 50) > 70 and f1h.get("rsi", 50) > 60:
            s += 6; factors.append("15m+1h RSI overbought")

    cvd_5m, cvd_delta = _cvd_momentum(features)

    if cvd_5m > 0.10 and cvd_delta > 0.02:
        s += 16; factors.append(f"CVD5 overbought accelerating: {cvd_5m*100:.0f}%")
    elif cvd_5m > 0.10:
        s += 10; factors.append(f"CVD5 overbought: {cvd_5m*100:.0f}%")
    elif cvd_5m > 0.03:
        s += 7

    cvd_30m = features.get("cvd_30m", 0)
    if cvd_30m > 0.08: s += 8
    elif cvd_30m > 0.02: s += 3

    if cvd_delta < -0.05:
        s += 5; factors.append("CVD momentum loss (reversal early)")

    if rsi > 70 and cvd_5m > 0.05 and bullish_8 >= 6:
        s += 10; factors.append("⭐ Full DOWN confluence")

    htf_score = htf.get("score", 0)
    if htf_score <= -2:
        s += 5; factors.append("HTF bearish alignment")
    elif htf_score >= 2:
        s -= 8; factors.append("⚠️ HTF bullish — DOWN risky")

    return s, factors


def apply_crash_gate(features: Dict, up_score: int, up_factors: List[str]) -> Tuple[int, List[str]]:
    f1h = features.get("1h", {})
    if not f1h.get("valid"):
        return up_score, up_factors

    ema50 = f1h.get("ema50", 0)
    current = f1h.get("current", 0)
    if ema50 > 0:
        dev_pct = (current - ema50) / ema50 * 100
        if dev_pct < _CRASH_EMA50_PCT:
            return -999, [f"🚫 Crash zone EMA50 {dev_pct:+.1f}% — UP blocked"]

    return up_score, up_factors
