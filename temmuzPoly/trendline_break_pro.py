"""
Trendline Break Pro — 5m BTC trend çizgisi kırılım sinyali.

Swing pivot (high/low) noktalarından trend çizgisi kurar;
kapanmış mumda destek/direnç kırılımını tespit eder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PIVOT_LEFT = 4
PIVOT_RIGHT = 4
LOOKBACK = 120
MIN_PIVOT_GAP = 5
BREAK_BUFFER_PCT = 0.015  # fiyatın çizgi üstü/altı toleransı (%)


@dataclass
class TrendlineSignal:
    direction: str | None
    label: str
    skip_reason: str | None = None
    line_type: str | None = None
    line_price: float | None = None
    close_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "label": self.label,
            "skip_reason": self.skip_reason,
            "line_type": self.line_type,
            "line_price": self.line_price,
            "close_price": self.close_price,
        }


def _find_pivots(klines: list[dict]) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """(index, price) pivot high / low listeleri."""
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    n = len(klines)
    for i in range(PIVOT_LEFT, n - PIVOT_RIGHT):
        seg = klines[i - PIVOT_LEFT : i + PIVOT_RIGHT + 1]
        h = klines[i]["high"]
        l = klines[i]["low"]
        if h >= max(k["high"] for k in seg):
            highs.append((i, h))
        if l <= min(k["low"] for k in seg):
            lows.append((i, l))
    return highs, lows


def _filter_pivots(pivots: list[tuple[int, float]], *, descending: bool) -> list[tuple[int, float]]:
    """Zigzag — ardışık pivotlarda yön tutarlılığı."""
    if not pivots:
        return []
    out = [pivots[0]]
    for idx, price in pivots[1:]:
        last_idx, last_price = out[-1]
        if idx - last_idx < MIN_PIVOT_GAP:
            if descending and price > last_price:
                out[-1] = (idx, price)
            elif not descending and price < last_price:
                out[-1] = (idx, price)
            continue
        if descending:
            if price < out[-1][1]:
                out.append((idx, price))
        else:
            if price > out[-1][1]:
                out.append((idx, price))
    return out


def _line_at(i1: int, p1: float, i2: int, p2: float, idx: int) -> float:
    if i2 == i1:
        return p1
    return p1 + (p2 - p1) * (idx - i1) / (i2 - i1)


def analyze(klines: list[dict] | None = None) -> TrendlineSignal | None:
    """
    Son kapanmış 5m mumda trendline kırılımı.
    UP  → iniş direnç çizgisi yukarı kırıldı
    DOWN → yükseliş destek çizgisi aşağı kırıldı
    """
    if not klines or len(klines) < PIVOT_LEFT + PIVOT_RIGHT + 10:
        return None

    window = klines[-LOOKBACK:] if len(klines) > LOOKBACK else klines
    if len(window) < 20:
        return None

    # Sinyal: son kapanmış mum (açık mum hariç)
    closed = window[:-1] if len(window) > 1 else window
    idx = len(closed) - 1
    if idx < 10:
        return None

    close = closed[idx]["close"]
    buf = BREAK_BUFFER_PCT / 100.0

    raw_h, raw_l = _find_pivots(closed)
    highs = _filter_pivots(raw_h, descending=True)
    lows = _filter_pivots(raw_l, descending=False)

    # Direnç kırılımı (iniş trendi)
    if len(highs) >= 2:
        (i1, h1), (i2, h2) = highs[-2], highs[-1]
        if h2 < h1 and i2 > i1:
            res = _line_at(i1, h1, i2, h2, idx)
            if close > res * (1 + buf):
                return TrendlineSignal(
                    direction="UP",
                    label=f"TL-Pro ↑ direnç kırıldı  {h1:.0f}→{h2:.0f}  close>{res:.0f}",
                    line_type="resistance",
                    line_price=round(res, 2),
                    close_price=round(close, 2),
                )

    # Destek kırılımı (yükseliş trendi)
    if len(lows) >= 2:
        (i1, l1), (i2, l2) = lows[-2], lows[-1]
        if l2 > l1 and i2 > i1:
            sup = _line_at(i1, l1, i2, l2, idx)
            if close < sup * (1 - buf):
                return TrendlineSignal(
                    direction="DOWN",
                    label=f"TL-Pro ↓ destek kırıldı  {l1:.0f}→{l2:.0f}  close<{sup:.0f}",
                    line_type="support",
                    line_price=round(sup, 2),
                    close_price=round(close, 2),
                )

    return TrendlineSignal(
        direction=None,
        label="TL-Pro → kırılım yok",
        skip_reason="Trendline kırılımı yok",
        close_price=round(close, 2),
    )


if __name__ == "__main__":
    from btc_5m_105_algo import fetch_klines_5m

    kl = fetch_klines_5m()
    sig = analyze(kl)
    print(sig)
