"""
Multi-timeframe feature engineering
"""

from typing import Dict, List
from technicals import ema, rsi, macd, atr, adx, higher_timeframe_bias


def extract_all_features(data: Dict) -> Dict:
    tf = data["timeframes"]
    features = {
        "1h": extract_tf_features(tf.get("1h", []), "1h"),
        "15m": extract_tf_features(tf.get("15m", []), "15m"),
        "4h": extract_tf_features(tf.get("4h", []), "4h"),
        "1d": extract_tf_features(tf.get("1d", []), "1d"),
    }

    features["htf_bias"] = higher_timeframe_bias(
        tf.get("4h", []), tf.get("1d", [])
    )

    features["cvd_5m"] = data.get("cvd_5m", 0)
    features["cvd_30m"] = data.get("cvd_30m", 0)
    features["orderbook"] = data.get("orderbook", 0.5)

    return features


def extract_tf_features(klines: List[dict], tf_name: str) -> Dict:
    if len(klines) < 10:
        return {"valid": False}

    closes = [k["close"] for k in klines]
    volumes = [k["volume"] for k in klines]

    current = closes[-1]
    prev = closes[-2] if len(closes) > 1 else current

    ema9 = ema(closes, 9)[-1] if len(closes) >= 9 else current
    ema21 = ema(closes, 21)[-1] if len(closes) >= 21 else current
    ema50 = ema(closes, 50)[-1] if len(closes) >= 50 else current

    rsi_val = rsi(closes, 5)
    macd_val, macd_sig = macd(closes)

    atr_vals = atr(klines, 14)
    atr_val = atr_vals[-1] if atr_vals else current * 0.01

    adx_val, plus_di, minus_di = adx(klines, 14)

    recent = klines[-8:] if len(klines) >= 8 else klines
    bullish_count = sum(1 for k in recent if k["close"] >= k["open"])

    streak = 1
    last_dir = 1 if klines[-1]["close"] >= klines[-1]["open"] else -1
    for i in range(len(klines) - 2, max(len(klines) - 12, -1), -1):
        d = 1 if klines[i]["close"] >= klines[i]["open"] else -1
        if d == last_dir:
            streak += 1
        else:
            break

    avg_vol = sum(volumes[-10:]) / min(10, len(volumes))
    vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1.0

    return {
        "valid": True,
        "current": current,
        "change_pct": (current - prev) / prev * 100 if prev > 0 else 0,
        "ema9": ema9,
        "ema21": ema21,
        "ema50": ema50,
        "ema9_above_21": ema9 > ema21,
        "ema21_above_50": ema21 > ema50,
        "price_above_ema9": current > ema9,
        "rsi": rsi_val,
        "macd": macd_val,
        "macd_signal": macd_sig,
        "macd_bull": macd_val > macd_sig,
        "adx": adx_val,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "trending": adx_val > 20,
        "atr": atr_val,
        "atr_pct": atr_val / current * 100,
        "bullish_8": bullish_count,
        "bearish_8": 8 - bullish_count,
        "streak": streak,
        "streak_dir": last_dir,
        "volume_ratio": vol_ratio,
        "high_volume": vol_ratio > 1.5,
    }
