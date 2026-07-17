"""
Güncellenmiş MR skorlama (Multi-TF)
"""

from typing import Dict, List, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo
from config import (
    _MR_UP_GATE, _MR_DOWN_GATE,
    _MR_UP_GATE_KILLZONE, _MR_DOWN_GATE_KILLZONE,
    _KILL_ZONE_ET_HOURS, _CRASH_EMA50_PCT,
)


def get_kill_zone_adjustment() -> Tuple[int, int]:
    et_hour = datetime.now(ZoneInfo("America/New_York")).hour
    if et_hour in _KILL_ZONE_ET_HOURS:
        return _MR_UP_GATE_KILLZONE, _MR_DOWN_GATE_KILLZONE
    return _MR_UP_GATE, _MR_DOWN_GATE


def mr_confluence_up(features: Dict) -> Tuple[int, List[str]]:
    f1h = features.get("1h", {})
    f15m = features.get("15m", {})
    htf = features.get("htf_bias", {})

    if not f1h.get("valid"):
        return 0, ["Invalid 1h data"]

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

    cvd_5m = features.get("cvd_5m", 0)
    cvd_30m = features.get("cvd_30m", 0)

    if cvd_5m < -0.10: s += 16; factors.append(f"CVD5 capitulation: {cvd_5m*100:.0f}%")
    elif cvd_5m < -0.03: s += 7

    if cvd_30m < -0.08: s += 8
    elif cvd_30m < -0.02: s += 3

    if rsi < 30 and cvd_5m < -0.05 and bullish_8 <= 2:
        s += 10; factors.append("⭐ Full confluence")

    htf_score = htf.get("score", 0)
    if htf_score >= 2:
        s += 5; factors.append("HTF bullish alignment")
    elif htf_score <= -2:
        s -= 8; factors.append("⚠️ HTF bearish — UP risky")

    return s, factors


def mr_confluence_down(features: Dict) -> Tuple[int, List[str]]:
    f1h = features.get("1h", {})
    f15m = features.get("15m", {})
    htf = features.get("htf_bias", {})

    if not f1h.get("valid"):
        return 0, ["Invalid 1h data"]

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

    cvd_5m = features.get("cvd_5m", 0)
    cvd_30m = features.get("cvd_30m", 0)

    if cvd_5m > 0.10: s += 16; factors.append(f"CVD5 overbought: {cvd_5m*100:.0f}%")
    elif cvd_5m > 0.03: s += 7

    if cvd_30m > 0.08: s += 8
    elif cvd_30m > 0.02: s += 3

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
