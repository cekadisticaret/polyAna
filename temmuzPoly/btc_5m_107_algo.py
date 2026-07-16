"""
5M 107 BTC — 105 konsensüs + Trendline Break Pro

105'in 4-algo motoru ile trendline_break_pro aynı yönde olmalı.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from btc_5m_105_algo import (
    SignalResult,
    TOTAL_ALGOS,
    analyze as analyze_105,
    fetch_klines_5m,
    format_signal,
    trade_amount,
)
from trendline_break_pro import TrendlineSignal, analyze as analyze_trendline

TRADE_AMOUNT = 5.0


@dataclass
class Signal107(SignalResult):
    trendline_label: str | None = None
    trendline_line: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["trendline_label"] = self.trendline_label
        d["trendline_line"] = self.trendline_line
        return d


def analyze(
    klines: list[dict] | None = None,
    orderbook: dict | None = None,
    *,
    symbol: str = "BTCUSDT",
) -> Signal107 | None:
    sig105 = analyze_105(klines=klines, orderbook=orderbook, symbol=symbol)
    if sig105 is None:
        return None

    kl = klines
    if kl is None:
        try:
            kl = fetch_klines_5m(symbol)
        except Exception:
            return None

    tl: TrendlineSignal | None = analyze_trendline(kl)

    base_labels = list(sig105.labels)
    tl_label = tl.label if tl else "TL-Pro — veri yok"
    if tl and tl.label and tl.label not in base_labels:
        base_labels.append(tl.label)

    if sig105.direction is None:
        return Signal107(
            direction=None,
            consensus=sig105.consensus,
            amount=0.0,
            entry_price=sig105.entry_price,
            momentum=sig105.momentum,
            votes=sig105.votes,
            labels=base_labels,
            skip_reason=sig105.skip_reason,
            raw_direction=sig105.raw_direction,
            trendline_label=tl_label,
            trendline_line=tl.line_price if tl else None,
        )

    if tl is None or tl.direction is None:
        return Signal107(
            direction=None,
            consensus=sig105.consensus,
            amount=0.0,
            entry_price=sig105.entry_price,
            momentum=sig105.momentum,
            votes=sig105.votes,
            labels=base_labels,
            raw_direction=sig105.direction,
            skip_reason=tl.skip_reason if tl else "Trendline veri yok",
            trendline_label=tl_label,
            trendline_line=tl.line_price if tl else None,
        )

    if tl.direction != sig105.direction:
        return Signal107(
            direction=None,
            consensus=sig105.consensus,
            amount=0.0,
            entry_price=sig105.entry_price,
            momentum=sig105.momentum,
            votes=sig105.votes,
            labels=base_labels,
            raw_direction=sig105.direction,
            skip_reason=(
                f"Trendline çelişki: 105→{sig105.direction}  TL→{tl.direction}"
            ),
            trendline_label=tl_label,
            trendline_line=tl.line_price,
        )

    return Signal107(
        direction=sig105.direction,
        consensus=sig105.consensus,
        amount=TRADE_AMOUNT,
        entry_price=sig105.entry_price,
        momentum=sig105.momentum,
        votes=sig105.votes,
        labels=base_labels,
        skip_reason=None,
        trendline_label=tl_label,
        trendline_line=tl.line_price,
    )


def format_signal_107(result: Signal107 | None) -> str:
    if result is None:
        return "Veri alınamadı"
    if result.direction is None:
        extra = result.skip_reason or f"konsensüs yok ({result.consensus}/{TOTAL_ALGOS})"
        return f"Sinyal yok — {extra} | TL: {result.trendline_label or '—'}"
    icons = " ".join("🟢" if v > 0 else "🔴" if v < 0 else "⚪" for v in result.votes)
    return (
        f"{result.direction} ({result.consensus}/{TOTAL_ALGOS}) ${result.amount:.0f} "
        f"@ {result.entry_price:,.2f} | mom={result.momentum}\n"
        f"{icons}\n" + " | ".join(result.labels)
    )


if __name__ == "__main__":
    sig = analyze()
    print(format_signal_107(sig))
    if sig:
        import json
        print(json.dumps(sig.to_dict(), ensure_ascii=False, indent=2))
