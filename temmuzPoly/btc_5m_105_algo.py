"""
5M 105 BTC — Sinyal motoru (102 + MR veto + Trend nötr band)

102'nin 4-algo konsensüsü + ek filtreler:
  1. MR -1 iken UP için 3/4 konsensüs gerekir (2/4 yetmez)
  2. Trend nötr band: zayıf E20/E50 cross veya slope → 0 oy

Kullanım:
  python3 temmuzPoly/btc_5m_105_algo.py
"""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

# ── Config ────────────────────────────────────────────────────
SYMBOL = "BTCUSDT"
MIN_CONSENSUS = 2
MIN_CONSENSUS_UP_VS_MR = 3  # MR -1 iken UP için
TOTAL_ALGOS = 4
TREND_NEUTRAL_CROSS_PCT = 0.06   # |E20-E50|/fiyat %
TREND_NEUTRAL_SLOPE_PCT = 0.03   # 3 bar E20 slope %
MOMENTUM_BARS = 3
TRADE_AMOUNT_UP = 8.0
TRADE_AMOUNT_DOWN = 8.0
KLINES_LIMIT = 150

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

MOMENTUM_FILTER_ENABLED = os.getenv("PM_5M_105_MOMENTUM_FILTER", "true").lower() in (
    "1", "true", "yes",
)


# ── Binance veri ──────────────────────────────────────────────
def _binance_get(path: str, params: dict | None = None) -> dict | list:
    base = "https://fapi.binance.com"
    qs = urllib.parse.urlencode(params or {})
    url = f"{base}{path}?{qs}" if qs else f"{base}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def fetch_klines_5m(symbol: str = SYMBOL, limit: int = KLINES_LIMIT) -> list[dict]:
    raw = _binance_get("/fapi/v1/klines", {"symbol": symbol, "interval": "5m", "limit": limit})
    return [
        {
            "open_time": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in raw
    ]


def fetch_orderbook(symbol: str = SYMBOL) -> dict:
    return _binance_get("/fapi/v1/depth", {"symbol": symbol, "limit": 20})


# ── Teknik hesaplamalar ───────────────────────────────────────
def ema(values: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi_14(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in diffs]
    losses = [max(-d, 0) for d in diffs]
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def bollinger(closes: list[float], period: int = 20) -> tuple[float, float, float]:
    w = closes[-period:] if len(closes) >= period else closes
    mid = sum(w) / len(w)
    std = math.sqrt(sum((x - mid) ** 2 for x in w) / len(w))
    return mid + 2 * std, mid, mid - 2 * std


def macd_12_26_9(closes: list[float]) -> tuple[float, float]:
    if len(closes) < 26:
        return 0.0, 0.0
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    macd_line = [a - b for a, b in zip(ema12, ema26)]
    signal = ema(macd_line[-9:], 9) if len(macd_line) >= 9 else [macd_line[-1]]
    return macd_line[-1], signal[-1]


# ── 4 Algoritma ───────────────────────────────────────────────
def algo_a1_rsi_macd_ema(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines]
    rsi = rsi_14(closes)
    macd_v, signal_v = macd_12_26_9(closes)
    e20 = ema(closes, 20)
    e50 = ema(closes, 50) if len(closes) >= 50 else e20

    rsi_v = +1 if rsi < 40 else -1 if rsi > 60 else 0
    macd_v2 = +1 if macd_v > signal_v else -1 if macd_v < signal_v else 0
    ema_v = +1 if e20[-1] > e50[-1] else -1

    score = rsi_v + macd_v2 + ema_v
    vote = +1 if score >= 2 else -1 if score <= -2 else 0
    arr = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    return vote, (
        f"A1 {arr}  RSI:{rsi:.0f}  "
        f"MACD:{'↑' if macd_v2 > 0 else '↓' if macd_v2 < 0 else '→'}  "
        f"EMA:{'↑' if ema_v > 0 else '↓'}"
    )


def algo_trend(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines]
    e20 = ema(closes, 20)
    e50 = ema(closes, 50) if len(closes) >= 50 else ema(closes, 20)
    cross = e20[-1] - e50[-1]
    slope = e20[-1] - e20[-4] if len(e20) >= 4 else 0
    pct = cross / closes[-1] * 100
    slope_pct = slope / closes[-1] * 100 if closes[-1] else 0

    if abs(pct) < TREND_NEUTRAL_CROSS_PCT or abs(slope_pct) < TREND_NEUTRAL_SLOPE_PCT:
        return 0, f"Trend →  nötr (cross:{pct:+.2f}% slope:{slope_pct:+.3f}%)"

    if cross > 0 and slope > 0:
        return +1, f"Trend ↑  E20>E50 ({pct:+.2f}%)"
    if cross < 0 and slope < 0:
        return -1, f"Trend ↓  E20<E50 ({pct:+.2f}%)"
    return 0, f"Trend →  karışık ({pct:+.2f}%)"


def algo_mr(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines]
    rsi = rsi_14(closes)
    upper, _, lower = bollinger(closes, 20)
    price = closes[-1]

    rsi_v = +1 if rsi <= 35 else -1 if rsi >= 65 else 0
    bb_v = +1 if price <= lower else -1 if price >= upper else 0

    vote = max(-1, min(1, rsi_v + bb_v))
    arr = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    bb_lbl = "alt" if price <= lower else "üst" if price >= upper else "orta"
    return vote, f"MR {arr}  RSI:{rsi:.0f}  BB:{bb_lbl}"


def algo_orderflow_v2(klines: list[dict], ob: dict) -> tuple[int, str]:
    """CVD/OB çelişince canlı orderbook öncelikli (102)."""
    window = klines[-20:]
    cvd_delta = sum(
        k["volume"] if k["close"] >= k["open"] else -k["volume"] for k in window
    )
    total_vol = sum(k["volume"] for k in window) or 1
    cvd_r = cvd_delta / total_vol

    bids = sum(float(b[1]) for b in ob.get("bids", [])[:10])
    asks = sum(float(a[1]) for a in ob.get("asks", [])[:10])
    ob_r = (bids - asks) / (bids + asks) if (bids + asks) else 0

    cvd_v = +1 if cvd_r > 0.05 else -1 if cvd_r < -0.05 else 0
    ob_v = +1 if ob_r > 0.10 else -1 if ob_r < -0.10 else 0

    if cvd_v == ob_v:
        vote = cvd_v
    elif ob_v != 0:
        vote = ob_v
    elif cvd_v != 0:
        vote = cvd_v
    else:
        vote = 0

    tag = "v2" if cvd_v != ob_v and ob_v != 0 else ""
    arr = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    return vote, f"OF{tag} {arr}  CVD:{cvd_r:+.2f}  OB:{ob_r:+.2f}"


def recent_momentum(klines: list[dict], n: int = MOMENTUM_BARS) -> str:
    """Son n kapanmış 5m mum (açık mum hariç)."""
    if len(klines) < n + 1:
        return "MIXED"
    closed = klines[-(n + 1):-1]
    ups = sum(1 for k in closed if k["close"] >= k["open"])
    if ups >= n - 1:
        return "UP"
    if ups <= 1:
        return "DOWN"
    return "MIXED"


def trade_amount(direction: str) -> float:
    return TRADE_AMOUNT_UP if direction == "UP" else TRADE_AMOUNT_DOWN


@dataclass
class SignalResult:
    direction: str | None
    consensus: int
    amount: float
    entry_price: float
    momentum: str
    votes: list[int]
    labels: list[str]
    skip_reason: str | None = None
    raw_direction: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "consensus": self.consensus,
            "amount": self.amount,
            "entry_price": self.entry_price,
            "momentum": self.momentum,
            "votes": self.votes,
            "labels": self.labels,
            "skip_reason": self.skip_reason,
            "raw_direction": self.raw_direction,
        }


def analyze(
    klines: list[dict] | None = None,
    orderbook: dict | None = None,
    *,
    momentum_filter: bool | None = None,
) -> SignalResult | None:
    """
    5M 102 sinyal motoru.

    klines/orderbook verilmezse Binance'ten çeker.
    direction None → işlem yok (konsensüs veya momentum filtresi).
    """
    if momentum_filter is None:
        momentum_filter = MOMENTUM_FILTER_ENABLED

    try:
        if klines is None:
            klines = fetch_klines_5m()
        if orderbook is None:
            orderbook = fetch_orderbook()
    except Exception as e:
        print(f"[btc_5m_105_algo] Veri hatası: {e}", flush=True)
        return None

    v1, l1 = algo_a1_rsi_macd_ema(klines)
    v2, l2 = algo_trend(klines)
    v3, l3 = algo_mr(klines)
    v4, l4 = algo_orderflow_v2(klines, orderbook)

    votes = [v1, v2, v3, v4]
    labels = [l1, l2, l3, l4]
    up_v = sum(1 for v in votes if v > 0)
    down_v = sum(1 for v in votes if v < 0)
    entry_price = klines[-1]["open"]
    momentum = recent_momentum(klines)

    if up_v >= MIN_CONSENSUS and up_v > down_v:
        if v3 < 0 and up_v < MIN_CONSENSUS_UP_VS_MR:
            return SignalResult(
                direction=None,
                consensus=up_v,
                amount=0.0,
                entry_price=entry_price,
                momentum=momentum,
                votes=votes,
                labels=labels,
                raw_direction="UP",
                skip_reason=(
                    f"MR veto: aşırı alım (MR↓), UP için {MIN_CONSENSUS_UP_VS_MR}/{TOTAL_ALGOS} gerekli ({up_v}/{TOTAL_ALGOS})"
                ),
            )
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
            skip_reason=None,
        )

    if momentum_filter:
        if direction == "DOWN" and momentum == "UP":
            return SignalResult(
                direction=None,
                consensus=consensus,
                amount=0.0,
                entry_price=entry_price,
                momentum=momentum,
                votes=votes,
                labels=labels,
                raw_direction="DOWN",
                skip_reason=(
                    f"momentum filtresi: son {MOMENTUM_BARS} 5m mum yükseliş, DOWN engellendi"
                ),
            )
        if direction == "UP" and momentum == "DOWN":
            return SignalResult(
                direction=None,
                consensus=consensus,
                amount=0.0,
                entry_price=entry_price,
                momentum=momentum,
                votes=votes,
                labels=labels,
                raw_direction="UP",
                skip_reason=(
                    f"momentum filtresi: son {MOMENTUM_BARS} 5m mum düşüş, UP engellendi"
                ),
            )

    return SignalResult(
        direction=direction,
        consensus=consensus,
        amount=trade_amount(direction),
        entry_price=entry_price,
        momentum=momentum,
        votes=votes,
        labels=labels,
        skip_reason=None,
    )


def format_signal(result: SignalResult | None) -> str:
    if result is None:
        return "Veri alınamadı"
    if result.direction is None:
        extra = result.skip_reason or f"konsensüs yok ({result.consensus}/{TOTAL_ALGOS})"
        return f"Sinyal yok — {extra} | momentum={result.momentum}"
    icons = " ".join("🟢" if v > 0 else "🔴" if v < 0 else "⚪" for v in result.votes)
    return (
        f"{result.direction} ({result.consensus}/{TOTAL_ALGOS}) ${result.amount:.0f} "
        f"@ {result.entry_price:,.2f} | mom={result.momentum}\n"
        f"{icons}\n" + " | ".join(result.labels)
    )


if __name__ == "__main__":
    sig = analyze()
    print(format_signal(sig))
    if sig:
        print(json.dumps(sig.to_dict(), ensure_ascii=False, indent=2))
