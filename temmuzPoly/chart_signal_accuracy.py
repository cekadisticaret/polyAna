"""Grafik MC / YT / TAHMİN / TAHMİN2 saatlik başarı takibi."""
from __future__ import annotations

import json
import os
from typing import Any

import requests

_DIR = os.path.dirname(os.path.abspath(__file__))
ACCURACY_FILE = os.path.join(_DIR, "chart_signal_accuracy.json")
PREV_FILE = os.path.join(_DIR, "chart_signal_prev.json")
FUTURES = "https://fapi.binance.com"
SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
TRACK_KEYS = ("MC", "YT", "TAHMIN", "TAHMIN2", "T2_LM", "T2_ST", "T2_ADX", "T2_LZ", "T2_CVD")
_MIN_WR_SAMPLES = 5


def _empty() -> dict:
    return {k: {"total": 0, "correct": 0, "by_sym": {}} for k in TRACK_KEYS}


def _load() -> dict:
    if not os.path.isfile(ACCURACY_FILE):
        return _empty()
    try:
        with open(ACCURACY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        base = _empty()
        for k in TRACK_KEYS:
            if k in data and isinstance(data[k], dict):
                base[k] = {
                    "total": int(data[k].get("total") or 0),
                    "correct": int(data[k].get("correct") or 0),
                    "by_sym": data[k].get("by_sym") if isinstance(data[k].get("by_sym"), dict) else {},
                }
        return base
    except Exception:
        return _empty()


def _save(acc: dict) -> None:
    with open(ACCURACY_FILE, "w", encoding="utf-8") as f:
        json.dump(acc, f, indent=2, ensure_ascii=False)


def _fetch(pair: str, interval: str, limit: int) -> list[dict]:
    r = requests.get(
        f"{FUTURES}/fapi/v1/klines",
        params={"symbol": pair, "interval": interval, "limit": limit},
        timeout=12,
    )
    r.raise_for_status()
    out: list[dict] = []
    for x in r.json():
        out.append({
            "time": int(x[0]) // 1000,
            "open": float(x[1]),
            "high": float(x[2]),
            "low": float(x[3]),
            "close": float(x[4]),
            "volume": float(x[5]),
        })
    return out


def _vote_mc(mc: dict | None) -> str | None:
    if not mc or not mc.get("ok"):
        return None
    cur = mc.get("current") or {}
    d = cur.get("direction")
    if d in ("UP", "DOWN"):
        return d
    b = int(cur.get("bull_score") or 0)
    e = int(cur.get("bear_score") or 0)
    if e > b:
        return "DOWN"
    if b > e:
        return "UP"
    return None


def _vote_yt(yt: dict | None) -> str | None:
    if not yt or not yt.get("ok"):
        return None
    d = (yt.get("current") or {}).get("direction")
    return d if d in ("UP", "DOWN") else None


def _vote_tahmin(mc: dict | None, yt: dict | None) -> str | None:
    votes = [v for v in (_vote_mc(mc), _vote_yt(yt)) if v]
    if not votes:
        return None
    up = votes.count("UP")
    dn = votes.count("DOWN")
    if up > dn:
        return "UP"
    if dn > up:
        return "DOWN"
    return None


def _vote_t2(t2: dict | None) -> str | None:
    if not t2 or not t2.get("ok"):
        return None
    d = (t2.get("current") or {}).get("direction")
    return d if d in ("UP", "DOWN") else None


def _compute_signals(candles: list[dict], ref_price: float | None, dec: int = 2) -> dict:
    from chart_multi_confirm_signals import compute_multi_confirm_signals
    from chart_tahmin2_signals import compute_tahmin2_signals
    from chart_yon_tahmin_signals import compute_yon_tahmin_signals

    mc = compute_multi_confirm_signals(candles, dec=dec)
    yt = compute_yon_tahmin_signals(candles, dec=dec)
    t2 = compute_tahmin2_signals(candles, ref_price=ref_price, dec=dec)
    parts: dict[str, str | None] = {}
    for v in (t2.get("votes") or []):
        tag = str(v.get("tag") or "").upper()
        if tag in ("LM", "ST", "ADX", "LZ", "CVD"):
            d = v.get("dir")
            parts[tag] = d if d in ("UP", "DOWN") else None
    return {
        "mc": _vote_mc(mc),
        "yt": _vote_yt(yt),
        "tahmin": _vote_tahmin(mc, yt),
        "tahmin2": _vote_t2(t2),
        "parts": parts,
    }


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


def _apply_prediction(acc: dict, sym: str, pred: dict, actual: str) -> None:
    mapping = {
        "mc": "MC",
        "yt": "YT",
        "tahmin": "TAHMIN",
        "tahmin2": "TAHMIN2",
    }
    for pk, ak in mapping.items():
        d = pred.get(pk)
        if d in ("UP", "DOWN"):
            _bump(acc, ak, sym, d == actual)
    for tag, d in (pred.get("parts") or {}).items():
        ak = f"T2_{tag}"
        if ak in acc and d in ("UP", "DOWN"):
            _bump(acc, ak, sym, d == actual)


def _wr_entry(entry: dict | None, sym: str | None = None) -> dict | None:
    if not entry:
        return None
    if sym:
        sub = (entry.get("by_sym") or {}).get(sym)
        if sub and int(sub.get("total") or 0) >= _MIN_WR_SAMPLES:
            t, c = int(sub["total"]), int(sub["correct"])
            return {"wr": round(c / t * 100, 1), "total": t}
    t = int(entry.get("total") or 0)
    if t >= _MIN_WR_SAMPLES:
        c = int(entry.get("correct") or 0)
        return {"wr": round(c / t * 100, 1), "total": t}
    return None


def _consensus_wr(path: str, sym: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        entry = data.get("_consensus")
        return _wr_entry(entry, sym)
    except Exception:
        return None


def get_signal_wr_bundle(symbol: str, timeframe: str = "1h") -> dict:
    sym = symbol.replace("USDT", "")
    acc = _load()
    try:
        from chart_algo_panel import get_algo_panel_wr
        alg_wr = get_algo_panel_wr(symbol, timeframe)
    except Exception:
        alg_wr = {
            "alg1": _consensus_wr(os.path.join(_DIR, "algo_accuracy.json"), sym),
            "alg2": _consensus_wr(os.path.join(_DIR, "algo_accuracy_v2.json"), sym),
        }
    out: dict[str, Any] = {
        "mc": _wr_entry(acc.get("MC"), sym),
        "yt": _wr_entry(acc.get("YT"), sym),
        "tahmin": _wr_entry(acc.get("TAHMIN"), sym),
        "tahmin2": _wr_entry(acc.get("TAHMIN2"), sym),
        "tahmin2_parts": {
            "LM": _wr_entry(acc.get("T2_LM"), sym),
            "ST": _wr_entry(acc.get("T2_ST"), sym),
            "ADX": _wr_entry(acc.get("T2_ADX"), sym),
            "LZ": _wr_entry(acc.get("T2_LZ"), sym),
            "CVD": _wr_entry(acc.get("T2_CVD"), sym),
        },
        "alg1": alg_wr.get("alg1"),
        "alg2": alg_wr.get("alg2"),
    }
    return out


def _predict_for_sym(sym: str, pair: str) -> dict:
    candles = _fetch(pair, "1m", 120)
    if len(candles) < 60:
        candles = _fetch(pair, "1h", 80)
    ref = None
    h1 = _fetch(pair, "1h", 3)
    if h1:
        ref = float(h1[-1]["open"])
    dec = 1 if sym == "BTC" else 2
    return _compute_signals(candles, ref, dec=dec)


def update_hourly() -> None:
    """Önceki saatin tahminlerini kapat, yeni tahminleri kaydet."""
    acc = _load()
    prev: dict = {}
    if os.path.isfile(PREV_FILE):
        try:
            with open(PREV_FILE, encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}

    updated = False
    if prev.get("predictions"):
        for sym, pair in SYMBOLS.items():
            h1 = _fetch(pair, "1h", 4)
            if len(h1) < 3:
                continue
            prev_bar, last_bar = h1[-3], h1[-2]
            if last_bar["close"] == prev_bar["close"]:
                continue
            actual = "UP" if last_bar["close"] > prev_bar["open"] else "DOWN"
            pred = prev["predictions"].get(sym)
            if pred:
                _apply_prediction(acc, sym, pred, actual)
                updated = True

    if updated:
        _save(acc)

    predictions = {sym: _predict_for_sym(sym, pair) for sym, pair in SYMBOLS.items()}
    with open(PREV_FILE, "w", encoding="utf-8") as f:
        json.dump({"predictions": predictions}, f, indent=2, ensure_ascii=False)


def ensure_backfill(max_hours: int = 150) -> None:
    """Dosya boşsa 1h mumlarla geçmiş saatleri doldur."""
    acc = _load()
    if sum(int(acc[k].get("total") or 0) for k in TRACK_KEYS) >= max_hours:
        return
    for sym, pair in SYMBOLS.items():
        h1 = _fetch(pair, "1h", min(max_hours + 65, 500))
        if len(h1) < 65:
            continue
        dec = 1 if sym == "BTC" else 2
        for i in range(60, len(h1) - 1):
            window = h1[max(0, i - 79): i + 1]
            candles = [
                {
                    "time": j,
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "volume": b["volume"],
                }
                for j, b in enumerate(window)
            ]
            ref = float(h1[i]["open"])
            nxt = h1[i + 1]
            if nxt["close"] == h1[i]["close"]:
                continue
            actual = "UP" if nxt["close"] > ref else "DOWN"
            pred = _compute_signals(candles, ref, dec=dec)
            _apply_prediction(acc, sym, pred, actual)
    _save(acc)


def update_consensus_accuracy(
    prev_consensus: dict,
    kl_by_sym: dict[str, list],
    acc_path: str,
    *,
    name: str = "Konsensüs",
) -> None:
    """algo_signals / v2 — önceki saat konsensüs WR."""
    if not prev_consensus:
        return
    acc: dict = {}
    if os.path.isfile(acc_path):
        try:
            with open(acc_path, encoding="utf-8") as f:
                acc = json.load(f)
        except Exception:
            acc = {}
    entry = acc.setdefault("_consensus", {"name": name, "total": 0, "correct": 0, "by_sym": {}})
    if not entry.get("name"):
        entry["name"] = name
    updated = False
    for sym, kl in kl_by_sym.items():
        if len(kl) < 3:
            continue
        cons = prev_consensus.get(sym)
        if not cons:
            continue
        up = int(cons.get("UP") or 0)
        dn = int(cons.get("DOWN") or 0)
        if up > dn:
            pred = "UP"
        elif dn > up:
            pred = "DOWN"
        else:
            continue
        prev_close = kl[-3]["c"] if isinstance(kl[-3], dict) and "c" in kl[-3] else kl[-3]["close"]
        curr_close = kl[-2]["c"] if isinstance(kl[-2], dict) and "c" in kl[-2] else kl[-2]["close"]
        if curr_close == prev_close:
            continue
        actual = "UP" if curr_close > prev_close else "DOWN"
        ok = pred == actual
        entry["total"] += 1
        entry["correct"] += int(ok)
        by = entry.setdefault("by_sym", {})
        if sym not in by:
            by[sym] = {"total": 0, "correct": 0}
        by[sym]["total"] += 1
        by[sym]["correct"] += int(ok)
        updated = True
    if updated:
        with open(acc_path, "w", encoding="utf-8") as f:
            json.dump(acc, f, indent=2, ensure_ascii=False)
