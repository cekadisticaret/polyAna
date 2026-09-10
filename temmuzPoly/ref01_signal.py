"""REF01 — saatlik yol referans çizgisi.

TREND: ilk |6| bps yönü, ref kesişi yok, şu an aynı yönde ≥20 bps.
FADE: ilk kesiş :15 öncesi, şu an ters tarafta ≥12 bps.

Kaynak: `temmuzPoly/hourly_path` (WS `binance_ws_marks` → `apply_prices`). Emir yok.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_DIR = Path(__file__).resolve().parent
_TZ = ZoneInfo("Europe/Istanbul")
PATH_DIR = _DIR / "hourly_path"
PATH_LATEST = PATH_DIR / "latest.json"

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
COINS = ("BTC", "ETH", "SOL")

FIRST_BPS = 6.0
TREND_BPS = 18.0
FADE_BPS = 10.0
FADE_CROSS_BEFORE = 15  # dakika < 15
ASK_MAX = 0.75


def now_tr() -> datetime:
    return datetime.now(_TZ)


def coin_of(symbol: str) -> str:
    s = str(symbol or "").upper().replace("USDT", "").replace("USD", "")
    return s if s in COINS else s[:3]


def norm_symbol(symbol: str) -> str:
    c = coin_of(symbol)
    return f"{c}USDT" if c in COINS else str(symbol or "").upper()


def _num(v, default=None):
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _hour_key(dt: datetime | None = None) -> str:
    t = (dt or now_tr()).astimezone(_TZ)
    return t.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d_%H")


def load_hour(hour_key: str | None = None) -> dict:
    key = hour_key or _hour_key()
    fp = PATH_DIR / f"{key}.json"
    data = _load(fp) if fp.is_file() else {}
    if data.get("hour_key") == key:
        return data
    latest = _load(PATH_LATEST)
    if latest.get("hour_key") == key:
        return latest
    return data or latest


def _minute_bps(row: dict, ref: float | None) -> float | None:
    b = _num(row.get("d_bps"))
    if b is not None:
        return b
    b = _num(row.get("bps"))
    if b is not None:
        return b
    px = _num(row.get("px"))
    if px is None or not ref:
        return None
    return (px - ref) / ref * 10000.0


def path_series(symbol: str, hour_key: str | None = None) -> dict:
    coin = coin_of(symbol)
    data = load_hour(hour_key)
    row = (data.get("coins") or {}).get(coin) or {}
    if not isinstance(row, dict):
        row = {}
    ref = _num(row.get("ref"))
    pts: list[tuple[int, float]] = []
    for m in row.get("minutes") or []:
        if not isinstance(m, dict):
            continue
        try:
            mn = int(m.get("m"))
        except (TypeError, ValueError):
            continue
        b = _minute_bps(m, ref)
        if b is None:
            continue
        pts.append((mn, float(b)))
    pts.sort()
    now_bps = _num(row.get("now_vs_ref_bps"))
    if now_bps is None and pts:
        now_bps = pts[-1][1]
    return {
        "hour_key": data.get("hour_key") or hour_key,
        "ref": ref,
        "bps": now_bps,
        "pts": pts,
    }


def _first_side(pts: list[tuple[int, float]], need: float) -> tuple[int, float, str] | None:
    for mn, b in pts:
        if abs(b) >= need:
            return mn, b, ("UP" if b > 0 else "DOWN")
    return None


def _cross_min(pts: list[tuple[int, float]], after_m: int, side: str) -> int | None:
    sign = 1 if side == "UP" else -1
    for mn, b in pts:
        if mn <= after_m:
            continue
        if sign > 0 and b <= 0:
            return mn
        if sign < 0 and b >= 0:
            return mn
    return None


def _deny(sym: str, reason: str, detail: str, **extra) -> dict:
    out = {
        "allow": False,
        "symbol": sym,
        "direction": None,
        "mode": None,
        "reason": reason,
        "detail": detail,
        "ask_max": ASK_MAX,
        "path_bps": extra.get("path_bps"),
        "first_side": extra.get("first_side"),
        "cross_min": extra.get("cross_min"),
    }
    return out


def decide(symbol: str, minute: int | None = None, hour_key: str | None = None) -> dict:
    sym = norm_symbol(symbol)
    if minute is not None and (minute < 1 or minute > 50):
        return _deny(sym, "dakika", f"dk {minute} giriş dışı")
    path = path_series(sym, hour_key)
    bps = path.get("bps")
    pts = path.get("pts") or []
    first = _first_side(pts, FIRST_BPS)
    if not first:
        return _deny(sym, "yol düz", f"ilk {FIRST_BPS:.0f} bps yok · şimdi {bps}")
    first_m, first_b, first_side = first
    cross = _cross_min(pts, first_m, first_side)
    extra = {"path_bps": bps, "first_side": first_side, "cross_min": cross}

    if bps is None:
        return _deny(sym, "yol yok", "bps yok", **extra)
    now_side = "UP" if bps > 0 else ("DOWN" if bps < 0 else None)

    if cross is not None and cross < FADE_CROSS_BEFORE:
        if now_side and now_side != first_side and abs(bps) >= FADE_BPS:
            return {
                "allow": True,
                "symbol": sym,
                "direction": now_side,
                "mode": "fade",
                "ask_max": ASK_MAX,
                "path_bps": bps,
                "first_side": first_side,
                "cross_min": cross,
                "reason": "fade",
                "detail": (
                    f"fade {first_side}→{now_side} kesiş :{cross:02d} "
                    f"{bps:+.1f}bps"
                ),
            }
        return _deny(
            sym, "fade bekliyor",
            f"kesiş :{cross:02d} · {first_side} · şimdi {bps:+.1f}bps",
            **extra,
        )

    if cross is not None:
        return _deny(
            sym, "geç kesiş",
            f"kesiş :{cross:02d} · trend yok",
            **extra,
        )
    if now_side == first_side and abs(bps) >= TREND_BPS:
        return {
            "allow": True,
            "symbol": sym,
            "direction": first_side,
            "mode": "trend",
            "ask_max": ASK_MAX,
            "path_bps": bps,
            "first_side": first_side,
            "cross_min": None,
            "reason": "trend",
            "detail": f"trend {first_side} {bps:+.1f}bps kesişsiz",
        }
    return _deny(
        sym, "trend bekliyor",
        f"{first_side} · şimdi {bps:+.1f}bps · {TREND_BPS:.0f} yok",
        **extra,
    )
