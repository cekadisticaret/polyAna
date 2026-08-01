"""Grafik ALG1/ALG2 — 5m / 15m / 1h konsensüs (slot başında kilitlenir)."""
from __future__ import annotations

import json
import os
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

_DIR = os.path.dirname(os.path.abspath(__file__))
import sys as _sys
if _DIR not in _sys.path:
    _sys.path.insert(0, _DIR)
_TZ_TR = timezone(timedelta(hours=3))
_FUTURES = "https://fapi.binance.com"
_SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}

_PANEL_CACHE: dict[tuple, tuple[float, dict]] = {}
_PANEL_CACHE_TTL = 45.0
_MIN_WR_SAMPLES = 5
ACCURACY_FILE = os.path.join(_DIR, "chart_algo_panel_accuracy.json")

_TF_CFG = {
    "5m":  {"interval": "5m",  "htf": "15m", "limit": 200, "htf_limit": 120, "secs": 300},
    "15m": {"interval": "15m", "htf": "1h",  "limit": 200, "htf_limit": 100, "secs": 900},
}


def _slot_window_start(tf: str, now: float | None = None) -> int:
    ts = int(now if now is not None else _time.time())
    secs = _TF_CFG[tf]["secs"]
    return ts - (ts % secs)


def _consensus_dir(c: dict | None) -> str | None:
    if not c:
        return None
    up = int(c.get("UP") or 0)
    dn = int(c.get("DOWN") or 0)
    if up > dn:
        return "UP"
    if dn > up:
        return "DOWN"
    return None


def _load_acc() -> dict:
    if not os.path.isfile(ACCURACY_FILE):
        return {}
    try:
        with open(ACCURACY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_acc(acc: dict) -> None:
    with open(ACCURACY_FILE, "w", encoding="utf-8") as f:
        json.dump(acc, f, indent=2, ensure_ascii=False)


def _wr_entry(entry: dict | None, sym: str) -> dict | None:
    if not entry:
        return None
    sub = (entry.get("by_sym") or {}).get(sym)
    if sub and int(sub.get("total") or 0) >= _MIN_WR_SAMPLES:
        t, c = int(sub["total"]), int(sub["correct"])
        return {"wr": round(c / t * 100, 1), "total": t}
    t = int(entry.get("total") or 0)
    if t >= _MIN_WR_SAMPLES:
        c = int(entry.get("correct") or 0)
        return {"wr": round(c / t * 100, 1), "total": t}
    return None


def _bump(acc: dict, key: str, sym: str, ok: bool) -> None:
    if key not in acc:
        acc[key] = {"total": 0, "correct": 0, "by_sym": {}}
    acc[key]["total"] += 1
    acc[key]["correct"] += int(ok)
    by = acc[key].setdefault("by_sym", {})
    if sym not in by:
        by[sym] = {"total": 0, "correct": 0}
    by[sym]["total"] += 1
    by[sym]["correct"] += int(ok)


def _fetch_kline_at(pair: str, interval: str, open_ts: int) -> dict | None:
    try:
        r = requests.get(
            f"{_FUTURES}/fapi/v1/klines",
            params={"symbol": pair, "interval": interval, "startTime": open_ts * 1000, "limit": 1},
            timeout=12,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return None
        x = rows[0]
        if int(x[0]) // 1000 != open_ts:
            return None
        o, c = float(x[1]), float(x[4])
        if c == o:
            return None
        return {"open": o, "close": c, "actual": "UP" if c > o else "DOWN"}
    except Exception:
        return None


def _slot_actual(sym: str, tf: str, window_start: int) -> str | None:
    pair = _SYMBOLS.get(sym)
    if not pair:
        return None
    bar = _fetch_kline_at(pair, _TF_CFG[tf]["interval"], window_start)
    return bar["actual"] if bar else None


def _build_full_consensus(tf: str) -> tuple[dict, dict]:
    import algo_signals as sig
    import algo_signals_v2 as sig2

    cfg = _TF_CFG[tf]
    _, cons_v1, _ = sig._build_all_signals(cfg["interval"], cfg["htf"], cfg["limit"], cfg["htf_limit"])
    _, cons_v2 = sig2._build_signals(cfg["interval"], cfg["htf"], cfg["limit"], cfg["htf_limit"])
    return cons_v1, cons_v2


def _prev_path(tf: str) -> str:
    return os.path.join(_DIR, f"chart_algo_panel_prev_{tf}.json")


def update_wr(timeframe: str) -> None:
    """Kapalı slot için ALG1/ALG2 WR güncelle, yeni slot tahminini kaydet."""
    tf = timeframe.lower()
    if tf not in _TF_CFG:
        return
    ws = _slot_window_start(tf)
    path = _prev_path(tf)
    prev: dict = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}

    acc = _load_acc()
    prev_ws = prev.get("window_start")
    updated = False
    if prev_ws and int(prev_ws) < ws:
        for sym in _SYMBOLS:
            actual = _slot_actual(sym, tf, int(prev_ws))
            if not actual:
                continue
            d1 = _consensus_dir((prev.get("v1") or {}).get(sym))
            d2 = _consensus_dir((prev.get("v2") or {}).get(sym))
            if d1:
                _bump(acc, f"ALG1_{tf}", sym, d1 == actual)
                updated = True
            if d2:
                _bump(acc, f"ALG2_{tf}", sym, d2 == actual)
                updated = True

    if updated:
        _save_acc(acc)

    if prev.get("window_start") != ws:
        try:
            v1, v2 = _build_full_consensus(tf)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"window_start": ws, "v1": v1, "v2": v2}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[chart_algo_panel] prev save {tf}: {e}")


def get_algo_panel_wr(symbol: str, timeframe: str = "1h") -> dict[str, dict | None]:
    sym = symbol.replace("USDT", "")
    tf = (timeframe or "1h").lower()
    if tf in _TF_CFG:
        update_wr(tf)
        acc = _load_acc()
        return {
            "alg1": _wr_entry(acc.get(f"ALG1_{tf}"), sym),
            "alg2": _wr_entry(acc.get(f"ALG2_{tf}"), sym),
        }
    from chart_signal_accuracy import _consensus_wr
    return {
        "alg1": _consensus_wr(os.path.join(_DIR, "algo_accuracy.json"), sym),
        "alg2": _consensus_wr(os.path.join(_DIR, "algo_accuracy_v2.json"), sym),
    }


def run_wr_update() -> None:
    """Cron — 5m + 15m slot WR."""
    update_wr("5m")
    update_wr("15m")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "update_wr":
        run_wr_update()
    else:
        run_wr_update()


def _consensus_to_panel(c: dict, *, total: int, tf: str, period: str) -> dict:
    up = int(c.get("UP") or 0)
    dn = int(c.get("DOWN") or 0)
    neu = int(c.get("NEUTRAL") or 0)
    tot = int(c.get("total") or total)
    if up > dn:
        direction = "UP"
    elif dn > up:
        direction = "DOWN"
    else:
        direction = "NEUTRAL"
    return {
        "direction": direction,
        "up": up,
        "down": dn,
        "neutral": neu,
        "total": tot,
        "timeframe": tf,
        "period_label": period,
    }


def _load_hourly_file_panel(symbol: str) -> dict:
    """1h — cron dosyalarından."""
    sym = symbol.replace("USDT", "")
    out: dict = {"v1": None, "v2": None, "timeframe": "1h"}
    for key, path, default_total in (
        ("v1", "/tmp/algo_signals.json", 34),
        ("v2", "/tmp/algo_signals_v2.json", 17),
    ):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            c = (data.get("consensus") or {}).get(sym)
            if not isinstance(c, dict):
                continue
            ps = data.get("period_start") or ""
            pe = data.get("period_end") or ""
            period = f"{ps}–{pe}" if ps and pe else ps or "1h"
            out[key] = _consensus_to_panel(c, total=default_total, tf="1h", period=period)
            out[key]["updated"] = data.get("updated")
        except Exception:
            continue
    return out


def _compute_intraday_panel(symbol: str, timeframe: str, window_start: int) -> dict:
    """5m / 15m — algo kütüphanesinden canlı konsensüs."""
    cfg = _TF_CFG.get(timeframe)
    if not cfg:
        return _load_hourly_file_panel(symbol)

    sym = symbol.replace("USDT", "")
    cache_key = (sym, timeframe, window_start)
    now = _time.time()
    cached = _PANEL_CACHE.get(cache_key)
    if cached and now - cached[0] < _PANEL_CACHE_TTL:
        return cached[1]

    import algo_signals as sig
    import algo_signals_v2 as sig2

    iv = cfg["interval"]
    htf = cfg["htf"]
    _, cons_v1, _ = sig._build_all_signals(iv, htf, cfg["limit"], cfg["htf_limit"])
    _, cons_v2 = sig2._build_signals(iv, htf, cfg["limit"], cfg["htf_limit"])

    slot_dt = datetime.fromtimestamp(window_start, _TZ_TR)
    if timeframe == "5m":
        end_dt = slot_dt + timedelta(minutes=5)
        period = slot_dt.strftime("%H:%M") + "–" + end_dt.strftime("%H:%M")
    else:
        end_dt = slot_dt + timedelta(minutes=15)
        period = slot_dt.strftime("%H:%M") + "–" + end_dt.strftime("%H:%M")

    out = {
        "timeframe": timeframe,
        "v1": _consensus_to_panel(
            cons_v1.get(sym, {}), total=34, tf=timeframe, period=period,
        ) if sym in cons_v1 else None,
        "v2": _consensus_to_panel(
            cons_v2.get(sym, {}), total=17, tf=timeframe, period=period,
        ) if sym in cons_v2 else None,
    }
    _PANEL_CACHE[cache_key] = (now, out)
    if len(_PANEL_CACHE) > 64:
        cutoff = now - 300
        for k in list(_PANEL_CACHE):
            if _PANEL_CACHE[k][0] < cutoff:
                del _PANEL_CACHE[k]
    return out


def load_algo_panel(symbol: str, timeframe: str = "1h", window_start: int | None = None) -> dict:
    """Grafik pill'leri — 1h dosya, 5m/15m canlı hesap."""
    tf = (timeframe or "1h").lower()
    if tf in _TF_CFG:
        update_wr(tf)
    if tf == "1h":
        return _load_hourly_file_panel(symbol)
    if tf in ("5m", "15m") and window_start:
        return _compute_intraday_panel(symbol, tf, int(window_start))
    if tf in ("5m", "15m"):
        return _compute_intraday_panel(symbol, tf, int(_time.time()) // 300 * 300 if tf == "5m" else int(_time.time()) // 900 * 900)
    return _load_hourly_file_panel(symbol)
