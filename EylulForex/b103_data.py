"""B1#03 spot/chart — CEM01 kotasyon, B1#03 MUM sinyal, ayrı defter.

forex_data.py / forex_book.py / forex_signal.py değiştirilmez.
"""
from __future__ import annotations

from forex_data import (
    BOOK_LEVEL_TF,
    _BAR_SEC,
    _YF,
    bar_remaining,
    forex_quote,
    get_xau_klines,
    paxg_tick_score,
)


def forex_spot(timeframe: str = "1m") -> dict:
    tf = timeframe if timeframe in _YF else "1m"
    q = forex_quote()
    q["timeframe"] = tf
    q["bar_sec"] = _BAR_SEC[tf]
    q["bar_left"] = bar_remaining(tf)
    q["algo"] = "b103"
    q["name"] = "XAUUSD · B1#03"
    q["signal_tf"] = "1h"
    q["level_tf"] = BOOK_LEVEL_TF
    try:
        q["tick"] = paxg_tick_score()
    except Exception:
        q["tick"] = {"score": 0.0, "n": 0}
    try:
        from b103_signal import live_signal, rail_signals, sr_levels
        q["signal"] = live_signal("1h")
        q["rail"] = q["signal"].get("rail") or rail_signals()
        rows, _ = get_xau_klines(BOOK_LEVEL_TF, 120)
        levels = sr_levels(rows)
    except Exception as e:
        q["signal"] = {
            "direction": "NEUTRAL", "confidence": 0.0, "is_stable": False,
            "engine": "b1_mum", "error": str(e)[:160],
        }
        q["rail"] = {}
        levels = {}
    q["book_levels"] = {
        "support": (levels or {}).get("nearest_support"),
        "resistance": (levels or {}).get("nearest_resistance"),
        "tf": BOOK_LEVEL_TF,
    }
    try:
        from b103_book import apply_signal
        q["book"] = apply_signal(
            q.get("signal"), q.get("bid"), q.get("ask"),
            rail=q.get("rail"), levels=levels, book="b103",
        )
    except Exception as e:
        q["book"] = {"ok": False, "error": str(e)[:160]}
    return q


def forex_chart(timeframe: str = "1m", limit: int | None = None, plain: bool = False) -> dict:
    tf = timeframe if timeframe in _YF else "1m"
    n = _YF[tf][2]
    if limit is not None:
        n = max(20, min(500, int(limit)))
    try:
        rows, src = get_xau_klines(tf, n)
        q = forex_quote()
    except Exception as e:
        return {
            "ok": False, "symbol": "XAUUSD", "name": "B1#03",
            "timeframe": tf, "algo": "b103", "error": str(e)[:200],
            "candles": [], "bid": None, "ask": None, "mid": None,
        }
    dec = 2
    candles = [
        {
            "time": c["time"],
            "open": round(c["open"], dec),
            "high": round(c["high"], dec),
            "low": round(c["low"], dec),
            "close": round(c["close"], dec),
            "volume": round(c.get("volume") or 0, 2),
        }
        for c in rows
    ]
    out = {
        "ok": True,
        "symbol": "XAUUSD",
        "name": "B1#03 MUM",
        "timeframe": tf,
        "price_tf": tf,
        "dec": dec,
        "candles": candles,
        "source": src,
        "bar_sec": _BAR_SEC[tf],
        "bar_left": bar_remaining(tf),
        "algo": "b103",
        **{k: q[k] for k in ("mid", "bid", "ask", "spread", "live_price") if k in q},
        "day_high": q.get("day_high"),
        "day_low": q.get("day_low"),
    }
    try:
        out["tick"] = paxg_tick_score()
    except Exception:
        out["tick"] = {"score": 0.0, "n": 0}
    try:
        from b103_signal import overlay_signals, rail_signals, sr_levels
        from forex_data import get_xau_klines as _kl

        def _fn(iv, lim=120):
            r, _ = _kl(iv, lim)
            return r

        sig, marks = overlay_signals(tf, candles, klines_fn=_fn)
        out["signal"] = sig
        out["signal_markers"] = marks
        out["rail"] = sig.get("rail") or rail_signals(klines_fn=_fn)
        out["levels"] = sr_levels(candles)
    except Exception as e:
        out["signal"] = {
            "direction": "NEUTRAL", "confidence": 0.0, "is_stable": False,
            "engine": "b1_mum", "error": str(e)[:160],
        }
        out["signal_markers"] = []
        out["rail"] = {}
        out["levels"] = {"ok": False, "error": str(e)[:160]}
    try:
        from b103_book import snapshot
        out["book"] = snapshot(out.get("bid"), out.get("ask"), book="b103")
    except Exception:
        out["book"] = None
    return out
