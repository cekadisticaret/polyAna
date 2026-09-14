"""Tek Binance USDT-M cüzdan — GPSUSDT / BIN_XAUUSDT aynı sayıyı gösterir.

fapi 418 olunca son başarılı okuma döner; sanal defter bakiyesine düşülmez.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
_CACHE = Path("/tmp/binance_um_wallet.json")
_TTL = 8.0
_mem: tuple[float, dict] | None = None


def _load() -> dict | None:
    try:
        d = json.loads(_CACHE.read_text())
        if d.get("wallet") is None:
            return None
        return d
    except Exception:
        return None


def _save(row: dict) -> None:
    try:
        _CACHE.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _blocked() -> bool:
    try:
        if str(_ROOT) not in sys.path:
            sys.path.insert(0, str(_ROOT))
        from binance_fapi_guard import fapi_blocked
        return bool(fapi_blocked())
    except Exception:
        return False


def fetch(*, force: bool = False) -> dict | None:
    """wallet / available / unrealized / equity — WS önbelleği, REST yok."""
    global _mem
    now = time.time()
    if not force and _mem and now - _mem[0] < _TTL:
        return dict(_mem[1])
    cached = _load()
    if cached:
        _mem = (now, cached)
        return dict(cached)
    return None


def apply_ws(*, wallet: float, available: float | None = None, unrealized: float = 0.0) -> dict:
    """User-data ACCOUNT_UPDATE — REST yok."""
    global _mem
    now = time.time()
    prev = _load() or {}
    avail = available
    if avail is None:
        try:
            avail = float(prev.get("available") or wallet)
        except (TypeError, ValueError):
            avail = wallet
    row = {
        "wallet": round(float(wallet), 4),
        "available": round(float(avail), 4),
        "unrealized": round(float(unrealized), 4),
        "equity": round(float(wallet) + float(unrealized), 4),
        "ts": now,
        "src": "user_ws",
    }
    _save(row)
    _mem = (now, row)
    return dict(row)
