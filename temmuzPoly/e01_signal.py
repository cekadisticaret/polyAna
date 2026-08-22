"""COMBO — A1 + C1#01 + A2#05 V2 oy birliği.

Kaynakların o saatteki açık pozisyonuna bakar. Sinyal üretmez.
Çatışma (biri UP biri DOWN) → açma.
Sessiz = o defter o coinde pozisyon açmamış.

Kademe (taban $36):
  1 oy + 2 sessiz → $24
  2 oy + 1 sessiz → $36
  3 oy aynı yön  → $48
"""
from __future__ import annotations

import json
from pathlib import Path

_DIR = Path(__file__).resolve().parent

SOURCES = (
    ("analiz1", "A1", _DIR / "poly_trader_analiz1_state.json"),
    ("c101", "C1#01", _DIR / "poly_trader_c101_state.json"),
    ("a2_05_v2", "A2#05 V2", _DIR / "poly_trader_a2_05_v2_state.json"),
)
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
BASE_USD = 36.0
STAKE_BY_VOTES = {1: 24.0, 2: 36.0, 3: 48.0}


def _stake_by_votes() -> dict[int, float]:
    try:
        from pm_trader_helpers import load_sanal_wr_amounts
        low, mid, high = load_sanal_wr_amounts("combo")
        return {1: float(low), 2: float(mid), 3: float(high)}
    except Exception:
        return dict(STAKE_BY_VOTES)


def norm_symbol(sym: str) -> str:
    s = str(sym or "").upper().replace("/", "").replace("-", "")
    if s in ("BTC", "ETH", "SOL"):
        return f"{s}USDT"
    if s.endswith("USDT"):
        return s
    return s


def _dir_of(pos: dict) -> str | None:
    raw = (
        pos.get("predicted_dir")
        or pos.get("pm_token_dir")
        or pos.get("algo_signal")
        or ""
    )
    d = str(raw).upper()
    if d in ("UP", "LONG", "BUY"):
        return "UP"
    if d in ("DOWN", "SHORT", "SELL"):
        return "DOWN"
    return None


def _load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def source_votes(hour_tr: int) -> dict[str, dict[str, str | None]]:
    """kaynak → {BTCUSDT: UP|DOWN|None, ...}."""
    out: dict[str, dict[str, str | None]] = {}
    for key, _lab, path in SOURCES:
        votes = {s: None for s in SYMBOLS}
        st = _load_state(path)
        for pos in st.get("open_positions") or []:
            if int(pos.get("entry_hour_tr") or -1) != int(hour_tr):
                continue
            sym = norm_symbol(pos.get("symbol") or "")
            if sym not in votes:
                continue
            d = _dir_of(pos)
            if d:
                votes[sym] = d
        out[key] = votes
    return out


def decide(symbol: str, hour_tr: int) -> dict:
    sym = norm_symbol(symbol)
    src = source_votes(hour_tr)
    ballots: list[tuple[str, str]] = []
    silent: list[str] = []
    detail = []
    for key, lab, _p in SOURCES:
        d = (src.get(key) or {}).get(sym)
        if d:
            ballots.append((lab, d))
            detail.append(f"{lab}={d}")
        else:
            silent.append(lab)
            detail.append(f"{lab}=sessiz")
    ups = [lab for lab, d in ballots if d == "UP"]
    downs = [lab for lab, d in ballots if d == "DOWN"]
    if ups and downs:
        return {
            "allow": False,
            "symbol": sym,
            "direction": None,
            "stake": 0.0,
            "votes": len(ballots),
            "silent": silent,
            "ups": ups,
            "downs": downs,
            "reason": "catisma",
            "detail": " · ".join(detail),
        }
    if not ballots:
        return {
            "allow": False,
            "symbol": sym,
            "direction": None,
            "stake": 0.0,
            "votes": 0,
            "silent": silent,
            "ups": [],
            "downs": [],
            "reason": "hepsi_sessiz",
            "detail": " · ".join(detail),
        }
    direction = "UP" if ups else "DOWN"
    n = len(ballots)
    stake = float(_stake_by_votes().get(n) or 0)
    return {
        "allow": stake > 0,
        "symbol": sym,
        "direction": direction,
        "stake": stake,
        "votes": n,
        "silent": silent,
        "ups": ups,
        "downs": downs,
        "reason": f"{n}_oy",
        "detail": " · ".join(detail),
        "base_usd": BASE_USD,
    }
