#!/usr/bin/env python3
"""ALGO3 → saatlik UP/DOWN. Cron :01 + :04:40 → /tmp/f1_signals.json

F1-01 HMM        rejim (trend / range / vol)
F1-02 MVRV       makro timing + boyut ipucu
F1-03 SOPR       makro timing
F1-04 OI         setup onayı (kaldıraç)
F1-05 KAMA       giriş
F1-06 Chandelier stop / yön
F1-07 Funding    delta-nötr kanat (funding yönü)

Glassnode/Coinglass yoksa Binance mum + WS funding yedeği.
Emir açmaz.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)
_ALGO3 = os.path.join(_ROOT, "ALGO3")
for p in (_DIR, _ROOT, _ALGO3):
    if p not in sys.path:
        sys.path.insert(0, p)

from algo_signals import fetch_klines  # noqa: E402

_TZ = ZoneInfo("Europe/Istanbul")
OUT_FILE = "/tmp/f1_signals.json"
SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}

F1_META = [
    (1, "HMM Rejim", "rejim"),
    (2, "MVRV Z-Score", "makro"),
    (3, "SOPR", "makro"),
    (4, "OI Likidasyon", "onay"),
    (5, "KAMA", "giriş"),
    (6, "Chandelier Exit", "stop"),
    (7, "Funding Arb", "delta"),
]


def _closes(kl: list[dict]) -> pd.Series:
    return pd.Series([float(k["c"]) for k in kl], dtype=float)


def _ohlc(kl: list[dict]) -> tuple[pd.Series, pd.Series, pd.Series]:
    h = pd.Series([float(k["h"]) for k in kl], dtype=float)
    l = pd.Series([float(k["l"]) for k in kl], dtype=float)
    c = pd.Series([float(k["c"]) for k in kl], dtype=float)
    return h, l, c


def _to_dir(raw: str | None) -> str:
    s = (raw or "").upper()
    if s in ("UP", "BUY", "STRONG_BUY", "SETUP_LONG", "ACCUMULATION",
             "CAPITULATION_BUY", "LONG"):
        return "UP"
    if s in ("DOWN", "SELL", "STRONG_SELL", "SETUP_SHORT", "OVERVALUED",
             "EXTREME_RISK", "PROFIT_TAKING", "SHORT"):
        return "DOWN"
    return "NEUTRAL"


def _sig_hmm(kl: list[dict]) -> tuple[str, str]:
    """Trend → son getiri; range → SMA dönüş; vol → yok."""
    prices = _closes(kl)
    if len(prices) < 60:
        return "NEUTRAL", "az mum"
    try:
        from hmm_regime_detector import HMMRegimeDetector
        out = HMMRegimeDetector(lookback=min(90, len(prices))).run(prices)
        regime = str(out.get("current_regime") or "UNKNOWN")
    except Exception as e:
        rets = prices.pct_change().dropna()
        vol = float(rets.tail(20).std() or 0)
        med = float(rets.tail(80).std() or 1e-9)
        regime = "VOLATILE" if vol > 1.6 * med else (
            "TREND" if abs(float(rets.tail(8).sum())) > 1.2 * med else "RANGE"
        )
        regime = f"{regime}"
        _ = e
    last = float(prices.iloc[-1] / prices.iloc[-2] - 1) if len(prices) > 1 else 0
    sma = float(prices.tail(20).mean())
    px = float(prices.iloc[-1])
    if regime == "TREND":
        return ("UP" if last > 0 else "DOWN"), f"HMM TREND {last:+.3%}"
    if regime == "RANGE":
        return ("DOWN" if px > sma else "UP"), f"HMM RANGE vs SMA {px/sma-1:+.2%}"
    return "NEUTRAL", f"HMM {regime}"


def _sig_mvrv(kl: list[dict], asset: str) -> tuple[str, str]:
    try:
        from mvrv_zscore import MVRVZScore
        if os.getenv("GLASSNODE_API_KEY"):
            out = MVRVZScore().run(asset)
            return _to_dir(out.get("signal")), out.get("description") or "MVRV"
    except Exception:
        pass
    px = _closes(kl)
    if len(px) < 80:
        return "NEUTRAL", "MVRV yedek az veri"
    win = px.tail(200) if len(px) >= 200 else px
    z = float((win.iloc[-1] - win.mean()) / (win.std() or 1e-9))
    if z > 1.8:
        return "DOWN", f"MVRV yedek z={z:.2f} pahalı"
    if z < -1.0:
        return "UP", f"MVRV yedek z={z:.2f} ucuz"
    return "NEUTRAL", f"MVRV yedek z={z:.2f}"


def _sig_sopr(kl: list[dict], asset: str) -> tuple[str, str]:
    try:
        from sopr_indicator import SOPRIndicator
        if os.getenv("GLASSNODE_API_KEY"):
            out = SOPRIndicator().run(asset)
            return _to_dir(out.get("signal")), out.get("description") or "SOPR"
    except Exception:
        pass
    px = _closes(kl)
    if len(px) < 24:
        return "NEUTRAL", "SOPR yedek az veri"
    ma = float(px.tail(24).mean())
    last = float(px.iloc[-1])
    ratio = last / ma if ma else 1.0
    if ratio < 0.97:
        return "UP", f"SOPR yedek px/MA24={ratio:.3f}"
    if ratio > 1.04:
        return "DOWN", f"SOPR yedek px/MA24={ratio:.3f}"
    return "NEUTRAL", f"SOPR yedek {ratio:.3f}"


def _sig_oi(kl: list[dict], pair: str) -> tuple[str, str]:
    """Kalabalık long + yükseliş → DOWN; kalabalık short → UP."""
    fund = None
    try:
        from binance_fapi_guard import ws_premium
        prem = ws_premium(pair)
        if prem:
            fund = float(prem.get("last_funding_rate") or 0)
    except Exception:
        fund = None
    px = _closes(kl)
    ret8 = float(px.iloc[-1] / px.iloc[-8] - 1) if len(px) >= 8 else 0
    vols = [float(k.get("v") or 0) for k in kl]
    vol_ratio = (vols[-1] / (sum(vols[-24:]) / 24)) if len(vols) >= 24 and sum(vols[-24:]) else 1.0
    if fund is not None and fund > 0.00015 and ret8 > 0:
        return "DOWN", f"OI fade long fund={fund:.4%} ret8={ret8:+.2%}"
    if fund is not None and fund < -0.00015 and ret8 < 0:
        return "UP", f"OI fade short fund={fund:.4%} ret8={ret8:+.2%}"
    if vol_ratio > 1.8 and ret8 > 0.012:
        return "DOWN", f"OI yedek vol×{vol_ratio:.1f} sıkışma"
    if vol_ratio > 1.8 and ret8 < -0.012:
        return "UP", f"OI yedek vol×{vol_ratio:.1f} short squeeze"
    return "NEUTRAL", "OI yapı nötr"


def _sig_kama(kl: list[dict]) -> tuple[str, str]:
    from kama_indicator import KAMAIndicator
    out = KAMAIndicator().generate_signal(_closes(kl))
    return _to_dir(out.get("signal")), out.get("description") or "KAMA"


def _sig_chand(kl: list[dict]) -> tuple[str, str]:
    from chandelier_exit import ChandelierExit
    h, l, c = _ohlc(kl)
    if len(c) < 30:
        return "NEUTRAL", "Chandelier az mum"
    out = ChandelierExit().generate_signal(h, l, c, current_position=None)
    trend = str(out.get("trend") or "")
    if trend in ("UP", "DOWN"):
        return trend, out.get("action") or trend
    return _to_dir(out.get("signal")), out.get("action") or "Chandelier"


def _sig_funding(pair: str) -> tuple[str, str]:
    """Pozitif funding → DOWN (long kalabalık); negatif → UP. Arb kanadı."""
    try:
        from binance_fapi_guard import ws_premium
        prem = ws_premium(pair)
        if not prem:
            return "NEUTRAL", "funding WS yok"
        fr = float(prem.get("last_funding_rate") or 0)
        apr = fr * 3 * 365
        if fr > 0.0001 and apr >= 0.08:
            return "DOWN", f"funding +{fr:.4%} APR {apr:.0%}"
        if fr < -0.0001 and abs(apr) >= 0.08:
            return "UP", f"funding {fr:.4%} APR {apr:.0%}"
        return "NEUTRAL", f"funding {fr:.4%} eşik altı"
    except Exception as e:
        return "NEUTRAL", f"funding hata {e}"


def decide(num: int, short: str, kl: list[dict]) -> tuple[str, str]:
    pair = SYMBOLS[short]
    if num == 1:
        return _sig_hmm(kl)
    if num == 2:
        return _sig_mvrv(kl, short)
    if num == 3:
        return _sig_sopr(kl, short)
    if num == 4:
        return _sig_oi(kl, pair)
    if num == 5:
        return _sig_kama(kl)
    if num == 6:
        return _sig_chand(kl)
    if num == 7:
        return _sig_funding(pair)
    return "NEUTRAL", "bilinmeyen"


def run() -> dict:
    now = datetime.now(_TZ)
    kl_1h = {}
    for short, pair in SYMBOLS.items():
        try:
            kl_1h[short] = fetch_klines(pair, "1h", 220)
        except Exception as e:
            print(f"[F1] {pair} mum yok: {e}")
            kl_1h[short] = []
    signals: dict[str, dict] = {}
    notes: dict[str, dict] = {}
    for num, name, _role in F1_META:
        row, note = {}, {}
        for short in SYMBOLS:
            kl = kl_1h.get(short) or []
            if num != 7 and len(kl) < 40:
                row[short], note[short] = "NEUTRAL", "az mum"
                continue
            d, why = decide(num, short, kl)
            row[short], note[short] = d, why
            print(f"[F1#{num:02d} {name}] {short} {d} — {why}")
        signals[str(num)] = row
        notes[str(num)] = note
    out = {
        "updated": now.strftime("%H:%M"),
        "updated_at_tr": now.isoformat(timespec="seconds"),
        "period_start": f"{now.hour:02d}:00",
        "signals": signals,
        "notes": notes,
        "written_hour": now.hour,
        "written_ts": datetime.now(timezone.utc).timestamp(),
    }
    with open(OUT_FILE, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"[F1] yazıldı {OUT_FILE}")
    return out


if __name__ == "__main__":
    run()
