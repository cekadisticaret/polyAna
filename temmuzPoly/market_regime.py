#!/usr/bin/env python3
"""BTC/ETH/SOL 1s piyasa bandı — ADX (trend) + ATR oranı (agresif).

Ölçüm kuralı (saatlik mum):
  ADX < 20 ve vol sakin → durgun
  ADX ≥ 25              → trend
  ATR / medyan ≥ 1.45   → canlı (agresif; ADX'i ezer)
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from algo_signals import SYMBOLS, fetch_klines

_CACHE_PATH = "/tmp/market_regime.json"
_CACHE_TTL = 45.0
_ADX_P = 14
_ATR_P = 14
_ATR_LOOK = 48


def _true_ranges(kl: list[dict]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(kl)):
        h, l, pc = kl[i]["h"], kl[i]["l"], kl[i - 1]["c"]
        out.append(max(h - l, abs(h - pc), abs(l - pc)))
    return out


def _wilder_atr_series(kl: list[dict], p: int = _ATR_P) -> list[float]:
    trs = _true_ranges(kl)
    if len(trs) < p:
        return []
    atr = sum(trs[:p]) / p
    series = [atr]
    for t in trs[p:]:
        atr = (atr * (p - 1) + t) / p
        series.append(atr)
    return series


def _adx_pack(kl: list[dict], p: int = _ADX_P) -> tuple[float, float, float]:
    if len(kl) < p * 2 + 5:
        return 0.0, 0.0, 0.0
    pdm, mdm, trs = [], [], []
    for i in range(1, len(kl)):
        up = kl[i]["h"] - kl[i - 1]["h"]
        dn = kl[i - 1]["l"] - kl[i]["l"]
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
        trs.append(max(
            kl[i]["h"] - kl[i]["l"],
            abs(kl[i]["h"] - kl[i - 1]["c"]),
            abs(kl[i]["l"] - kl[i - 1]["c"]),
        ))
    if len(trs) < p:
        return 0.0, 0.0, 0.0
    atr_s = sum(trs[:p])
    ps = sum(pdm[:p])
    ms = sum(mdm[:p])
    dx_list: list[float] = []
    for i in range(p, len(trs)):
        atr_s = atr_s - atr_s / p + trs[i]
        ps = ps - ps / p + pdm[i]
        ms = ms - ms / p + mdm[i]
        pdi = 100 * ps / atr_s if atr_s else 0.0
        mdi = 100 * ms / atr_s if atr_s else 0.0
        sm = pdi + mdi
        dx_list.append(100 * abs(pdi - mdi) / sm if sm else 0.0)
    if len(dx_list) < p:
        return 0.0, 0.0, 0.0
    adx = sum(dx_list[:p]) / p
    for v in dx_list[p:]:
        adx = (adx * (p - 1) + v) / p
    pdi = 100 * ps / atr_s if atr_s else 0.0
    mdi = 100 * ms / atr_s if atr_s else 0.0
    return round(adx, 1), round(pdi, 1), round(mdi, 1)


def _classify(adx: float, atr_ratio: float) -> str:
    if atr_ratio >= 1.45:
        return "live"
    if adx >= 25:
        return "trend"
    if adx < 20 and atr_ratio < 1.20:
        return "range"
    if adx >= 22:
        return "trend"
    if atr_ratio >= 1.25:
        return "live"
    return "range"


_LABEL = {"range": "Durgun", "trend": "Trend", "live": "Canlı"}
_HINT = {
    "range": "yatay · yeşil kartlar",
    "trend": "yönlü · sarı kartlar",
    "live": "agresif vol · mor kartlar",
}


def _one(sym: str, pair: str) -> dict[str, Any]:
    kl = fetch_klines(pair, "1h", 80)
    adx, pdi, mdi = _adx_pack(kl)
    atrs = _wilder_atr_series(kl)
    last = atrs[-1] if atrs else 0.0
    window = atrs[-_ATR_LOOK:] if atrs else []
    med = sorted(window)[len(window) // 2] if window else last
    ratio = (last / med) if med else 1.0
    if pdi > mdi and adx >= 20:
        direction = "UP"
    elif mdi > pdi and adx >= 20:
        direction = "DOWN"
    else:
        direction = "NEUTRAL"
    regime = _classify(adx, ratio)
    return {
        "symbol": sym,
        "regime": regime,
        "label": _LABEL[regime],
        "adx": adx,
        "plus_di": pdi,
        "minus_di": mdi,
        "atr_ratio": round(ratio, 2),
        "dir": direction,
        "price": round(float(kl[-1]["c"]), 4) if kl else None,
    }


def snapshot(*, force: bool = False) -> dict[str, Any]:
    if not force and os.path.isfile(_CACHE_PATH):
        try:
            raw = json.load(open(_CACHE_PATH))
            if time.time() - float(raw.get("ts") or 0) < _CACHE_TTL:
                return raw.get("data") or {}
        except Exception:
            pass
    coins = []
    err = None
    for sym, pair in SYMBOLS.items():
        try:
            coins.append(_one(sym, pair))
        except Exception as e:
            err = str(e)
            coins.append({
                "symbol": sym, "regime": "range", "label": "—",
                "adx": None, "atr_ratio": None, "dir": "NEUTRAL", "error": str(e),
            })
    votes = {"range": 0, "trend": 0, "live": 0}
    for c in coins:
        if c.get("adx") is not None:
            votes[c.get("regime") or "range"] += 1
    overall = max(votes, key=votes.get) if any(votes.values()) else "range"
    if list(votes.values()).count(votes[overall]) > 1 and sum(votes.values()) >= 2:
        if votes["live"]:
            overall = "live"
        elif votes["trend"] == votes["range"]:
            overall = "range"
    data = {
        "ok": True,
        "tf": "1h",
        "overall": overall,
        "overall_label": _LABEL[overall],
        "hint": _HINT[overall],
        "votes": votes,
        "coins": coins,
        "error": err,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    try:
        tmp = _CACHE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"ts": time.time(), "data": data}, f)
        os.replace(tmp, _CACHE_PATH)
    except Exception:
        pass
    return data
