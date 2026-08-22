"""
Polymarket 1 Saatlik Fiyat Tahmin Motoru

Kaynak: lab/v4/analyzer_v4.py (Tur 22 — Simetrik MR confluence, kalibre edilmiş)
Yedek (önceki prod v5): lab/backups/30-05-2026/poly_predictor_analysis_prod_v5_30052026.py

Strateji: Simetrik MR (UP + DOWN mean-reversion).
  - _MR_UP_GATE   = 45  (oversold → UP reversal)
  - _MR_DOWN_GATE = 40  (overbought → DOWN reversal)
  - Kill Zone (ET 9–11): gate 62/55; predict(kill_zone=False) ile kapatılabilir (varsayılan açık)
  - RSI(5), 8-mum MR, streak reversal, CVD teyidi, 30dk CVD flow
  - Trend-takip park edildi (backtest'te sinyali seyreltti)

Backtest (Ara'25–May'26, 6 ay):
  %56.0 doğruluk, +$752/ay ortalama, 6/6 ay pozitif, min ay +$390
"""
import asyncio
import json
import os
import sys
import aiohttp
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


STATE_FILE   = "/opt/cripto/poly_state.json"
HISTORY_FILE = "/opt/cripto/poly_history.json"

_CONF_HIGH = 0.65
_CONF_MED  = 0.57

_slot_utc_ms: int | None = None

# ── SMC Crash Savunması sabitleri ─────────────────────────────────────────────
_ET_ZONE = ZoneInfo("America/New_York")
# Kill Zone ET saatleri: 09h %47.2, 10h %49.2, 11h %52.5 — üçü de breakeven altı
# Backtest: KZ={9,10,11} → v4'e göre +$22 PnL / 7 ay | 17h %56.3 (iyi saat, KZ dışı)
_KILL_ZONE_ET_HOURS: frozenset[int] = frozenset({9, 10, 11})
# EMA50 crash eşiği: -3% çok erken tetikleniyor, %54.8 acc slotları engelliyor (net negatif)
# -8% eşiği yalnızca gerçek kriz koşullarını yakalar, normal dönemde pasif kalır
_CRASH_EMA50_PCT: float = -8.0


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
# TEKNİK YARDIMCI HESAPLAMALAR
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


def _rsi(closes: list[float], period: int = 5) -> float:
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
# VERİ ÇEKME
# ─────────────────────────────────────────────────────────────

async def _fetch_klines(symbol: str, tf: str = "1h", limit: int = 60) -> list[dict]:
    try:
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from binance_fapi_guard import public_klines  # noqa: WPS433
        data = public_klines(symbol, tf, limit)
        if not isinstance(data, list):
            return []
        return [
            {
                "open":      float(k[1]),
                "high":      float(k[2]),
                "low":       float(k[3]),
                "close":     float(k[4]),
                "volume":    float(k[5]),
                "taker_buy": float(k[9]) if len(k) > 9 else 0.0,
            }
            for k in data
        ]
    except Exception as e:
        print(f"[POLY prod] {symbol} kline hata: {e}")
        return []


async def _fetch_cvd(symbol: str) -> tuple[float, float]:
    def get_ratio(tf: str, limit: int) -> float:
        try:
            _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if _root not in sys.path:
                sys.path.insert(0, _root)
            from binance_fapi_guard import public_klines
            data = public_klines(symbol, tf, limit)
            if not isinstance(data, list):
                return 0.0
            total_vol = sum(float(k[5]) for k in data)
            taker_buy = sum(float(k[9]) for k in data if len(k) > 9)
            if total_vol == 0:
                return 0.0
            return (2 * taker_buy - total_vol) / total_vol
        except Exception:
            return 0.0

    return get_ratio("5m", 6), get_ratio("30m", 2)


async def _fetch_orderbook_imbalance(symbol: str) -> float:
    return 0.5


async def _fetch_large_trades(symbol: str) -> float:
    return 0.5


async def _fetch_taker_ratio(symbol: str) -> float:
    return 0.5


async def _fetch_funding_rate(symbol: str) -> float:
    try:
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from binance_fapi_guard import ws_premium
        hit = ws_premium(symbol)
        if hit:
            return float(hit.get("last_funding_rate") or 0)
    except Exception:
        pass
    return 0.0


async def _fetch_long_short_ratio(symbol: str) -> float:
    return 0.5


async def _fetch_liquidations(symbol: str) -> tuple[float, float]:
    return 0.0, 0.0


# ─────────────────────────────────────────────────────────────
# SKORLAMA
# ─────────────────────────────────────────────────────────────

def _momentum_score(klines: list[dict]) -> tuple[int, list[str]]:
    if len(klines) < 8:
        return 5, []
    recent = klines[-8:]
    bullish = sum(1 for k in recent if k["close"] >= k["open"])

    volumes = [k["volume"] for k in klines[-10:]] if len(klines) >= 10 else [k["volume"] for k in klines]
    avg_vol = sum(volumes) / len(volumes) if volumes else 1
    vol_mult = 1.3 if klines[-1]["volume"] > avg_vol * 1.5 else 1.0

    score = 20
    factors = []
    if bullish >= 7:
        score = int(-60 * vol_mult)
        factors.append(f"Strong MR: {bullish}/8 yukselis -> dusus")
    elif bullish >= 6:
        score = int(-38 * vol_mult)
        factors.append(f"Mean Reversion: {bullish}/8 yukselis -> dusus")
    elif bullish >= 5:
        score = -22
        factors.append(f"Mean Reversion: {bullish}/8 yukselis -> dusus olasi")
    elif bullish <= 1:
        score = int(65 * vol_mult)
        factors.append(f"Strong MR: {8-bullish}/8 dusus -> yukselis")
    elif bullish <= 2:
        score = int(48 * vol_mult)
        factors.append(f"Mean Reversion: {8-bullish}/8 dusus -> yukselis")
    elif bullish <= 3:
        score = 28
        factors.append(f"Mean Reversion: {8-bullish}/8 dusus -> yukselis olasi")

    streak = 1
    last_dir = 1 if klines[-1]["close"] >= klines[-1]["open"] else -1
    for i in range(len(klines) - 2, max(len(klines) - 12, -1), -1):
        d = 1 if klines[i]["close"] >= klines[i]["open"] else -1
        if d == last_dir:
            streak += 1
        else:
            break
    if streak >= 7:
        bonus = -55 if last_dir == 1 else 55
        score += bonus
        factors.append(f"EXTREME streak: {streak} ardisik -> %70+ reversal")
    elif streak >= 6:
        bonus = -42 if last_dir == 1 else 42
        score += bonus
        factors.append(f"Strong streak: {streak} ardisik -> guclu reversal")
    elif streak >= 5:
        bonus = -32 if last_dir == 1 else 32
        score += bonus
        factors.append(f"Streak: {streak} ardisik -> reversal")
    elif streak >= 4:
        bonus = -22 if last_dir == 1 else 22
        score += bonus
        factors.append(f"Streak bonus: {streak} ardisik")
    elif streak >= 3:
        bonus = -10 if last_dir == 1 else 10
        score += bonus
        factors.append(f"Streak: {streak} ardisik")
    return score, factors


def _mr_confluence_score(
    klines: list[dict], rsi5: float, cvd_5m: float, cvd_30m: float = 0.0,
) -> tuple[int, list[str]]:
    """UP-only MR confluence + 30dk CVD teyidi (v4 — flow varyantı)."""
    recent = klines[-8:]
    bullish = sum(1 for k in recent if k["close"] >= k["open"])
    last_dir = 1 if klines[-1]["close"] >= klines[-1]["open"] else -1
    streak = 1
    for i in range(len(klines) - 2, max(len(klines) - 12, -1), -1):
        d = 1 if klines[i]["close"] >= klines[i]["open"] else -1
        if d == last_dir:
            streak += 1
        else:
            break

    s = 0
    factors = []
    if bullish == 0: s += 34
    elif bullish == 1: s += 30
    elif bullish == 2: s += 22
    elif bullish == 3: s += 10
    elif bullish == 4: s += 0
    elif bullish == 5: s -= 8
    else: s -= 16
    factors.append(f"MR: {bullish}/8 yukselis")

    if rsi5 < 10: s += 30
    elif rsi5 < 20: s += 22
    elif rsi5 < 30: s += 13
    elif rsi5 < 40: s += 5
    elif rsi5 < 60: s += 0
    elif rsi5 < 70: s -= 5
    else: s -= 14
    factors.append(f"RSI5: {rsi5:.0f}")

    if last_dir == -1 and streak >= 5: s += 26; factors.append(f"Streak: {streak} dusus -> reversal")
    elif last_dir == -1 and streak == 4: s += 18; factors.append("Streak: 4 dusus -> reversal")
    elif last_dir == -1 and streak == 3: s += 9
    elif last_dir == 1 and streak >= 5: s -= 16

    if cvd_5m < -0.10: s += 16; factors.append(f"CVD5 kapitulasyon: {cvd_5m*100:.0f}%")
    elif cvd_5m < -0.03: s += 7
    elif cvd_5m > 0.10: s += 3

    if cvd_30m < -0.08: s += 8
    elif cvd_30m < -0.02: s += 3
    elif cvd_30m > 0.08: s += 2

    if rsi5 < 30 and cvd_5m < -0.05 and bullish <= 2:
        s += 10; factors.append("⭐ Tam confluence")
    return s, factors


def _technical_score(
    rsi: float, macd_val: float, macd_sig: float,
    adx: float, plus_di: float, minus_di: float,
    ema9: float, ema21: float, ema50: float,
) -> tuple[int, list[str]]:
    """Teknik skor — maks ±28 (eşit ağırlık ~±7)."""
    score = 0
    factors = []

    if ema9 > ema21 > ema50:
        score += 7
        factors.append("✅ EMA: Tam yükseliş dizisi")
    elif ema9 < ema21 < ema50:
        score -= 7
        factors.append("❌ EMA: Tam düşüş dizisi")
    elif ema9 > ema21:
        score += 3
        factors.append("➕ EMA: Hızlı > Yavaş")
    elif ema9 < ema21:
        score -= 3
        factors.append("➖ EMA: Hızlı < Yavaş")

    if adx > 30:
        score += 7 if plus_di > minus_di else -7
        factors.append(f"✅ ADX:{adx:.0f} güçlü")
    elif adx > 20:
        score += 3 if plus_di > minus_di else -3
        factors.append(f"➕ ADX:{adx:.0f} orta")

    if rsi >= 60:
        score += 7
        factors.append(f"✅ RSI:{rsi:.0f}")
    elif rsi >= 50:
        score += 3
        factors.append(f"➕ RSI:{rsi:.0f}")
    elif rsi <= 40:
        score -= 7
        factors.append(f"❌ RSI:{rsi:.0f}")
    elif rsi <= 50:
        score -= 3
        factors.append(f"➖ RSI:{rsi:.0f}")

    if macd_val > macd_sig and macd_val > 0:
        score += 7
        factors.append("✅ MACD: Pozitif + sinyal üzerinde")
    elif macd_val > macd_sig:
        score += 3
        factors.append("➕ MACD: Crossover bullish")
    elif macd_val < macd_sig and macd_val < 0:
        score -= 7
        factors.append("❌ MACD: Negatif + sinyal altında")
    elif macd_val < macd_sig:
        score -= 3
        factors.append("➖ MACD: Crossover bearish")

    return score, factors


def _orderflow_score(
    cvd_5m: float, cvd_30m: float,
    ob_imbalance: float, large_buy: float, taker_ratio: float,
    funding_rate: float, long_short: float,
    long_liq: float, short_liq: float,
) -> tuple[int, list[str]]:
    """Flow skoru — maks ±56 (eşit ağırlık ~±7)."""
    score = 0
    factors = []

    if cvd_5m > 0.05:
        score += 7
        factors.append(f"✅ CVD 5m: +{cvd_5m*100:.1f}%")
    elif cvd_5m > 0:
        score += 3
        factors.append(f"➕ CVD 5m: +{cvd_5m*100:.1f}%")
    elif cvd_5m < -0.05:
        score -= 7
        factors.append(f"❌ CVD 5m: {cvd_5m*100:.1f}%")
    else:
        score -= 3
        factors.append(f"➖ CVD 5m: {cvd_5m*100:.1f}%")

    if cvd_30m > 0.05:
        score += 7
        factors.append(f"✅ CVD 30m: +{cvd_30m*100:.1f}%")
    elif cvd_30m > 0:
        score += 3
        factors.append(f"➕ CVD 30m: +{cvd_30m*100:.1f}%")
    elif cvd_30m < -0.05:
        score -= 7
        factors.append(f"❌ CVD 30m: {cvd_30m*100:.1f}%")
    else:
        score -= 3
        factors.append(f"➖ CVD 30m: {cvd_30m*100:.1f}%")

    ob_pct = ob_imbalance * 100
    if ob_imbalance > 0.58:
        score += 7
        factors.append(f"OB: %{ob_pct:.0f}")
    elif ob_imbalance > 0.53:
        score += 3
        factors.append(f"OB: %{ob_pct:.0f}")
    elif ob_imbalance < 0.42:
        score -= 7
        factors.append(f"OB: %{ob_pct:.0f}")
    elif ob_imbalance < 0.47:
        score -= 3
        factors.append(f"OB: %{ob_pct:.0f}")

    if large_buy > 0.63:
        score += 7
        factors.append(f"Buyuk islem: ALIS")
    elif large_buy > 0.53:
        score += 3
        factors.append(f"Buyuk islem: hafif alis")
    elif large_buy < 0.37:
        score -= 7
        factors.append(f"Buyuk islem: SATIS")
    elif large_buy < 0.47:
        score -= 3
        factors.append(f"Buyuk islem: hafif satis")

    if taker_ratio > 0.58:
        score += 7
        factors.append(f"Taker: %{taker_ratio*100:.0f}")
    elif taker_ratio > 0.53:
        score += 3
        factors.append(f"Taker: %{taker_ratio*100:.0f}")
    elif taker_ratio < 0.42:
        score -= 7
        factors.append(f"Taker: %{taker_ratio*100:.0f}")
    elif taker_ratio < 0.47:
        score -= 3
        factors.append(f"Taker: %{taker_ratio*100:.0f}")

    if funding_rate > 0.0003:
        score -= 7
        factors.append(f"❌ Funding: aşırı iyimser")
    elif funding_rate > 0.0001:
        score -= 3
        factors.append(f"➖ Funding: yükseliş tarafı ağır")
    elif funding_rate < -0.0001:
        score += 7
        factors.append(f"✅ Funding: negatif")
    else:
        factors.append(f"⚪ Funding: normal")

    if long_short > 0.65:
        score -= 7
        factors.append(f"➖ L/S: %{long_short*100:.0f} long (aşırı)")
    elif long_short < 0.40:
        score += 7
        factors.append(f"➕ L/S: %{long_short*100:.0f} long (kötümser)")
    else:
        factors.append(f"⚪ L/S: %{long_short*100:.0f}")

    total_liq = long_liq + short_liq
    if total_liq > 0:
        net_liq = short_liq - long_liq
        if net_liq > total_liq * 0.30:
            score += 7
            factors.append(f"✅ Likidasyon: short ağırlıklı")
        elif net_liq < -total_liq * 0.30:
            score -= 7
            factors.append(f"❌ Likidasyon: long ağırlıklı")
        else:
            factors.append("⚪ Likidasyon: dengeli")
    else:
        factors.append("⚪ Likidasyon: nötr")

    return score, factors


def _mr_confluence_down_score(
    klines: list[dict], rsi5: float, cvd_5m: float, cvd_30m: float,
) -> tuple[int, list[str]]:
    """DOWN-only mean-reversion confluence — fiyat aşırı yükseldi, geri döner."""
    recent = klines[-8:]
    bullish = sum(1 for k in recent if k["close"] >= k["open"])

    last_dir = 1 if klines[-1]["close"] >= klines[-1]["open"] else -1
    streak = 1
    for i in range(len(klines) - 2, max(len(klines) - 12, -1), -1):
        d = 1 if klines[i]["close"] >= klines[i]["open"] else -1
        if d == last_dir:
            streak += 1
        else:
            break

    s = 0
    factors = []

    if bullish == 8: s += 34
    elif bullish == 7: s += 30
    elif bullish == 6: s += 22
    elif bullish == 5: s += 10
    elif bullish == 4: s += 0
    elif bullish == 3: s -= 8
    else: s -= 16
    factors.append(f"MR-DOWN: {bullish}/8 yukselis")

    if rsi5 > 90: s += 30
    elif rsi5 > 80: s += 22
    elif rsi5 > 70: s += 13
    elif rsi5 > 60: s += 5
    elif rsi5 > 40: s += 0
    elif rsi5 > 30: s -= 5
    else: s -= 14
    factors.append(f"RSI5: {rsi5:.0f}")

    if last_dir == 1 and streak >= 5: s += 26; factors.append(f"Streak: {streak} yukselis -> reversal DOWN")
    elif last_dir == 1 and streak == 4: s += 18; factors.append("Streak: 4 yukselis -> reversal DOWN")
    elif last_dir == 1 and streak == 3: s += 9
    elif last_dir == -1 and streak >= 5: s -= 16

    if cvd_5m > 0.10: s += 16; factors.append(f"CVD5 asiri alim: {cvd_5m*100:.0f}%")
    elif cvd_5m > 0.03: s += 7
    elif cvd_5m < -0.10: s += 3

    if cvd_30m > 0.08: s += 8
    elif cvd_30m > 0.02: s += 3
    elif cvd_30m < -0.08: s += 2

    if rsi5 > 70 and cvd_5m > 0.05 and bullish >= 6:
        s += 10; factors.append("⭐ Tam DOWN confluence")

    return s, factors


def _trend_follow_score(
    adx: float, plus_di: float, minus_di: float,
    ema9: float, ema21: float, ema50: float,
    rsi: float, cvd_5m: float, price_dir: int,
) -> tuple[int, str, list[str]]:
    """Trend-takip skoru — park edildi, tetiklenmez (ADX eşiği 999)."""
    if plus_di > minus_di and ema9 > ema21:
        trend_dir = "UP"
        di_spread = plus_di - minus_di
    elif minus_di > plus_di and ema9 < ema21:
        trend_dir = "DOWN"
        di_spread = minus_di - plus_di
    else:
        return 0, "NONE", []

    s = 0
    factors = [f"Trend-takip: {trend_dir}"]

    if trend_dir == "UP":
        if ema9 > ema21 > ema50:
            s += 30; factors.append("✅ EMA tam yukarı dizilim")
        else:
            s += 15; factors.append("➕ EMA kısmi yukarı")
    else:
        if ema9 < ema21 < ema50:
            s += 30; factors.append("✅ EMA tam aşağı dizilim")
        else:
            s += 15; factors.append("➕ EMA kısmi aşağı")

    if adx > 40:
        s += 20; factors.append(f"✅ ADX {adx:.0f} — çok güçlü")
    elif adx > 30:
        s += 15; factors.append(f"✅ ADX {adx:.0f} — güçlü")
    else:
        s += 10; factors.append(f"➕ ADX {adx:.0f} — trend var")

    if di_spread > 15:
        s += 10; factors.append(f"✅ DI spread {di_spread:.0f}")
    elif di_spread > 8:
        s += 5

    if trend_dir == "UP":
        if rsi > 65:
            s += 10; factors.append(f"✅ RSI {rsi:.0f} — trend teyit")
        elif rsi > 55:
            s += 5
    else:
        if rsi < 35:
            s += 10; factors.append(f"✅ RSI {rsi:.0f} — trend teyit")
        elif rsi < 45:
            s += 5

    if trend_dir == "UP" and cvd_5m > 0.05:
        s += 8; factors.append(f"✅ CVD teyit: {cvd_5m*100:.0f}%")
    elif trend_dir == "DOWN" and cvd_5m < -0.05:
        s += 8; factors.append(f"✅ CVD teyit: {cvd_5m*100:.0f}%")

    if (trend_dir == "UP" and price_dir == 1) or (trend_dir == "DOWN" and price_dir == -1):
        s += 5; factors.append("✅ Fiyat yönü uyumlu")

    return s, trend_dir, factors


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


def _liquidity_sweep_score(klines: list[dict]) -> tuple[int, int]:
    """
    ICT Liquidity Sweep teyidi (Katman 2).

    Son mum önceki 10 mumun swing low/high'ını wick ile geçip close ile geri döndü mü?
    Bu "stop hunt tamamlandı → reversal yüksek olasılıklı" sinyalidir.

    Backtest (BTC+SOL, 14k slot):
      sweep_low  → UP  %53.1  (baseline %50.2)
      sweep_high → DOWN %54.6 (baseline %49.8)

    Returns:
        (sweep_up_bonus, sweep_down_bonus) — confluence skoruna eklenecek puan
    """
    if len(klines) < 12:
        return 0, 0
    recent    = klines[-1]
    prior     = klines[-11:-1]
    prior_low  = min(k["low"]  for k in prior)
    prior_high = max(k["high"] for k in prior)

    sweep_up   = 15 if (recent["low"]  < prior_low  and recent["close"] > prior_low)  else 0
    sweep_down = 15 if (recent["high"] > prior_high and recent["close"] < prior_high) else 0
    return sweep_up, sweep_down


def _resolve_mr_gates(kill_zone: bool, ref_ms: int | None = None) -> tuple[int, int]:
    """kill_zone=False → her zaman 45/40. Varsayılan True → ET 9–11'de 62/55."""
    if not kill_zone:
        return 45, 40
    if ref_ms is None:
        ref_ms = _slot_utc_ms if _slot_utc_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    cur_et_hour = datetime.fromtimestamp(ref_ms / 1000, tz=_ET_ZONE).hour
    if cur_et_hour in _KILL_ZONE_ET_HOURS:
        return 62, 55
    return 45, 40


async def predict(symbol: str, *, preloaded: dict | None = None, kill_zone: bool = True) -> "PolyPrediction | None":
    if preloaded:
        klines = preloaded["klines"]
        cvd_5m, cvd_30m = preloaded["cvd"]
        ob_imb     = preloaded["ob"]
        large_buy  = preloaded["large"]
        taker      = preloaded["taker"]
        funding    = preloaded["funding"]
        ls_ratio   = preloaded["ls"]
        long_liq, short_liq = preloaded["liq"]
    else:
        (
            klines,
            (cvd_5m, cvd_30m),
            ob_imb, large_buy, taker, funding, ls_ratio,
            (long_liq, short_liq),
        ) = await asyncio.gather(
            _fetch_klines(symbol, "1h", 60),
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

    atr_vals = _atr_list(klines)
    atr_1h   = atr_vals[-1] if atr_vals else current * 0.01

    ema9  = _ema(closes, 9)[-1]
    ema21 = _ema(closes, 21)[-1]
    ema50 = _ema(closes, 50)[-1]
    ema50_dev_pct = (current - ema50) / ema50 * 100 if ema50 else 0.0

    rsi_val            = _rsi(closes)
    macd_val, macd_sig = _macd(closes)
    adx, plus_di, minus_di = _adx(klines)

    if adx > 20 and plus_di > minus_di and ema9 > ema21:
        trend = "YUKARI"
    elif adx > 20 and minus_di > plus_di and ema9 < ema21:
        trend = "AŞAĞI"
    else:
        trend = "YATAY"

    tech_score, tech_factors = _technical_score(
        rsi_val, macd_val, macd_sig, adx, plus_di, minus_di, ema9, ema21, ema50,
    )
    flow_score, flow_factors = _orderflow_score(
        cvd_5m, cvd_30m, ob_imb, large_buy, taker, funding, ls_ratio, long_liq, short_liq,
    )
    mom_score, mom_factors = _momentum_score(klines)

    # ── Rejim kapısı: simetrik MR (trend modu park edildi) ───────
    _ADX_TREND_THRESHOLD = 999
    _TREND_GATE = 999

    # Katman 3: Kill Zone — ET 9–11 gate sıkılaştırma (kill_zone=False ile devre dışı)
    _ref_ms = _slot_utc_ms if _slot_utc_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    _MR_UP_GATE, _MR_DOWN_GATE = _resolve_mr_gates(kill_zone, _ref_ms)

    price_dir_count = sum(
        1 for i in range(-3, 0)
        if len(closes) >= abs(i) + 1 and closes[i] >= closes[i - 1]
    )
    price_dir = 1 if price_dir_count >= 2 else -1

    trend_score, trend_dir, trend_factors = _trend_follow_score(
        adx, plus_di, minus_di, ema9, ema21, ema50, rsi_val, cvd_5m, price_dir,
    )
    conf_up_score, conf_up_factors     = _mr_confluence_score(klines, rsi_val, cvd_5m, cvd_30m)
    conf_down_score, conf_down_factors = _mr_confluence_down_score(klines, rsi_val, cvd_5m, cvd_30m)

    # ── Katman 2: Liquidity Sweep teyidi ─────────────────────────
    # Stop hunt tamamlandıysa reversal kalitesi artar
    _sweep_up, _sweep_down = _liquidity_sweep_score(klines)
    conf_up_score   += _sweep_up
    conf_down_score += _sweep_down
    if _sweep_up:
        conf_up_factors.append("✅ Liquidity sweep LOW → UP reversal teyit")
    if _sweep_down:
        conf_down_factors.append("✅ Liquidity sweep HIGH → DOWN reversal teyit")

    # ── Katman 1: EMA50 Rejim Kapısı ─────────────────────────────
    # Crash bölgesi: fiyat EMA50'nin %8+ altında → UP MR çalışmıyor (gerçek kriz eşiği)
    # -3% eşiği backtest'te net negatif: %54.8 acc slotları da engelliyordu
    if ema50_dev_pct < _CRASH_EMA50_PCT:
        conf_up_score   = -999
        conf_up_factors = [f"🚫 Crash bölgesi EMA50 {ema50_dev_pct:+.1f}% — UP engellendi"]

    import time as _time

    if adx >= _ADX_TREND_THRESHOLD and trend_score >= _TREND_GATE and trend_dir != "NONE":
        total_score = trend_score
        predicted_dir = trend_dir
        all_factors = trend_factors
    elif conf_up_score >= _MR_UP_GATE or conf_down_score >= _MR_DOWN_GATE:
        if conf_up_score >= conf_down_score:
            total_score = conf_up_score
            predicted_dir = "UP"
            all_factors = conf_up_factors
        else:
            total_score = conf_down_score
            predicted_dir = "DOWN"
            all_factors = conf_down_factors
    else:
        predicted_dir = None
        total_score = max(conf_up_score, conf_down_score)

    prob = max(0.50, min(0.90, 0.50 + total_score / 200.0)) if predicted_dir else 0.0
    if predicted_dir == "UP":
        prob_up, prob_down = prob, 1.0 - prob
    elif predicted_dir == "DOWN":
        prob_down, prob_up = prob, 1.0 - prob
    else:
        prob_up = prob_down = 0.0

    if predicted_dir is None:
        return None

    return PolyPrediction(
        symbol=symbol, current_price=current,
        prob_up=prob_up, prob_down=prob_down,
        expected_low=current - atr_1h, expected_high=current + atr_1h,
        atr_1h=atr_1h, rsi=rsi_val, macd_bull=macd_val > macd_sig,
        adx=adx, trend=trend, factors=all_factors,
        nearest_round=_nearest_round(current, symbol),
        round_side="ÜZERİNDE" if current >= _nearest_round(current, symbol) else "ALTINDA",
        predicted_dir=predicted_dir, timestamp=_time.time(),
    )


async def predict_status(symbol: str, *, kill_zone: bool = True) -> dict:
    """PolyPred teşhis: gate altı olsa bile ham skorları döner."""
    pred = await predict(symbol, kill_zone=kill_zone)
    if pred:
        return {
            "predicted_dir": pred.predicted_dir,
            "conf_a": round(max(pred.prob_up, pred.prob_down), 3),
            "conf_up_score": None,
            "conf_down_score": None,
            "mr_up_gate": None,
            "mr_down_gate": None,
            "reason": None,
        }
    try:
        (
            klines,
            (cvd_5m, cvd_30m),
            ob_imb, large_buy, taker, funding, ls_ratio,
            (long_liq, short_liq),
        ) = await asyncio.gather(
            _fetch_klines(symbol, "1h", 60),
            _fetch_cvd(symbol),
            _fetch_orderbook_imbalance(symbol),
            _fetch_large_trades(symbol),
            _fetch_taker_ratio(symbol),
            _fetch_funding_rate(symbol),
            _fetch_long_short_ratio(symbol),
            _fetch_liquidations(symbol),
        )
    except Exception as e:
        return {"predicted_dir": None, "conf_a": 0.0, "reason": f"A veri hatası: {e}"}

    if len(klines) < 30:
        return {"predicted_dir": None, "conf_a": 0.0, "reason": "A yetersiz veri"}

    closes = [k["close"] for k in klines]
    rsi_val = _rsi(closes)
    ema50 = _ema(closes, 50)[-1]
    ema50_dev_pct = (closes[-1] - ema50) / ema50 * 100 if ema50 else 0.0
    _ref_ms = _slot_utc_ms if _slot_utc_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    mr_up_gate, mr_down_gate = _resolve_mr_gates(kill_zone, _ref_ms)

    conf_up_score, _ = _mr_confluence_score(klines, rsi_val, cvd_5m, cvd_30m)
    conf_down_score, _ = _mr_confluence_down_score(klines, rsi_val, cvd_5m, cvd_30m)
    sweep_up, sweep_down = _liquidity_sweep_score(klines)
    conf_up_score += sweep_up
    conf_down_score += sweep_down
    if ema50_dev_pct < _CRASH_EMA50_PCT:
        conf_up_score = -999

    reason = (
        f"UP:{conf_up_score}/{mr_up_gate} DOWN:{conf_down_score}/{mr_down_gate}"
    )
    return {
        "predicted_dir": None,
        "conf_a": 0.0,
        "conf_up_score": conf_up_score,
        "conf_down_score": conf_down_score,
        "mr_up_gate": mr_up_gate,
        "mr_down_gate": mr_down_gate,
        "reason": reason,
    }


async def predict_all() -> list[PolyPrediction]:
    results = []
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        pred = await predict(sym)
        if pred:
            results.append(pred)
    if results:
        save_predictions(results)
    return results
