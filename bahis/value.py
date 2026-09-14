"""Value bet — vig’siz (fair) implied + CLV. Emir yok.

Piyasa implied = 1/oran ham; bookmaker marjı (overround) yüzünden
üç seçimin toplamı 1’i aşar. Kenar ham implied’e bakılırsa model
şişer. Karşılaştırma daima orantılı de-vig (fair) ile yapılır.

Eşik %4 (3–5 bant). Bunun altında örneklem hatası kenardan büyük.
CLV (kapanış çizgisi) uzun vadede P&L’den güvenilir.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

TR = ZoneInfo("Europe/Istanbul")
MIN_EDGE = 0.04
CLV_LOG = os.path.join(os.path.dirname(__file__), "data", "clv_log.jsonl")
_1X2 = (("1", "home"), ("X", "draw"), ("2", "away"))


def implied_raw(odds: float | None) -> float | None:
    if not odds or float(odds) <= 1:
        return None
    return 1.0 / float(odds)


def de_vig(book: dict[str, float]) -> dict | None:
    """Orantılı overround. book: seçim → decimal oran."""
    raw: dict[str, float] = {}
    for k, o in book.items():
        p = implied_raw(o)
        if p is None:
            return None
        raw[k] = p
    tot = sum(raw.values())
    if tot <= 0:
        return None
    return {
        "sum": round(tot, 4),
        "overround": round(tot - 1, 4),
        "pct": round((tot - 1) * 100, 1),
        "raw": {k: round(v, 4) for k, v in raw.items()},
        "fair": {k: round(v / tot, 4) for k, v in raw.items()},
    }


def book_1x2(odds: dict | None) -> dict[str, float] | None:
    out = {}
    for sel, field in _1X2:
        o = (odds or {}).get(field)
        if not o or float(o) <= 1:
            return None
        out[sel] = float(o)
    return out


def book_ou(odds: dict | None) -> dict[str, float] | None:
    ou = (odds or {}).get("ou25") or {}
    over, under = ou.get("over"), ou.get("under")
    if not over or not under or float(over) <= 1 or float(under) <= 1:
        return None
    return {"over": float(over), "under": float(under)}


def fair_1x2(odds: dict | None) -> dict | None:
    b = book_1x2(odds)
    return de_vig(b) if b else None


def fair_sel(odds: dict | None, sel: str, field: str | None = None) -> float | None:
    """1X2 için üçlü de-vig; tek oran kalırsa ham implied."""
    pack = fair_1x2(odds)
    if pack and sel in pack["fair"]:
        return pack["fair"][sel]
    o = (odds or {}).get(field or sel)
    return implied_raw(o)


def fair_ou_sel(odds: dict | None, sel: str) -> float | None:
    b = book_ou(odds)
    if not b:
        return None
    pack = de_vig(b)
    return pack["fair"].get(sel) if pack else None


def edges(model_p: float, odds: float, fair: float | None = None,
          min_edge: float = MIN_EDGE) -> dict:
    implied = implied_raw(odds)
    if implied is None:
        return {
            "odds": None, "implied": None, "impliedFair": None,
            "edge": 0.0, "edgeFair": 0.0, "isValue": False,
        }
    fair_p = fair if fair is not None else implied
    edge = model_p - implied
    edge_f = model_p - fair_p
    return {
        "odds": round(float(odds), 2),
        "implied": round(implied, 4),
        "impliedFair": round(fair_p, 4),
        "edge": round(edge, 4),
        "edgeFair": round(edge_f, 4),
        "isValue": edge_f >= min_edge,
    }


def clv_1x2(pick: str, taken: dict | None, close: dict | None) -> dict | None:
    """Pozitif CLV = kapanış bizim seçimi kısalttı (piyasayı yendik)."""
    field = {"1": "home", "X": "draw", "2": "away"}.get(pick)
    if not field:
        return None
    o_t = (taken or {}).get(field)
    o_c = (close or {}).get(field)
    if not o_t or not o_c or float(o_t) <= 1 or float(o_c) <= 1:
        return None
    fair_t = fair_1x2(taken)
    fair_c = fair_1x2(close)
    p_t = (fair_t["fair"][pick] if fair_t else implied_raw(o_t)) or 0
    p_c = (fair_c["fair"][pick] if fair_c else implied_raw(o_c)) or 0
    return {
        "pick": pick,
        "odds_taken": round(float(o_t), 3),
        "odds_close": round(float(o_c), 3),
        "fair_taken": round(p_t, 4),
        "fair_close": round(p_c, 4),
        "clv": round(p_c - p_t, 4),
        "clv_price": round(float(o_t) / float(o_c) - 1, 4),
        "beat": float(o_t) > float(o_c),
    }


def append_clv(row: dict) -> None:
    rec = {
        "ts": datetime.now(TR).isoformat(timespec="seconds"),
        **row,
    }
    os.makedirs(os.path.dirname(CLV_LOG), exist_ok=True)
    with open(CLV_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def clv_stats(rows: list[dict] | None = None) -> dict:
    if rows is None:
        rows = _read_log()
    graded = [r for r in rows if r.get("clv") is not None]
    if not graded:
        return {"n": 0, "beat_n": 0, "beat_pct": None, "mean": None}
    beat_n = sum(1 for r in graded if r.get("beat"))
    mean = sum(float(r.get("clv") or 0) for r in graded) / len(graded)
    return {
        "n": len(graded),
        "beat_n": beat_n,
        "beat_pct": round(100 * beat_n / len(graded), 1),
        "mean": round(mean, 4),
    }


def _read_log(limit: int = 4000) -> list[dict]:
    if not os.path.isfile(CLV_LOG):
        return []
    out = []
    try:
        with open(CLV_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out[-limit:]
