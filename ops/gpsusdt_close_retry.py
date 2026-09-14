#!/usr/bin/env python3
"""GPSUSDT canlı kapanış — emir açmaz.

CoptC `live_close_fail` / `bn_status_unknown` deyince (veya --now)
Binance MARKET reduceOnly ile kapatır. 4 deneme, 6 sn ara.
Pozisyon yoksa (--2022) başarılı sayılır.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_AGUSTOS = _ROOT / "AgustosKripto"
for p in (str(_ROOT), str(_AGUSTOS)):
    if p not in sys.path:
        sys.path.insert(0, p)

_ENV = _ROOT / ".env"
if _ENV.exists():
    for line in _ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

SYMBOL = "GPSUSDT"
ATTEMPTS = 4
SLEEP_SEC = 6.0
_FLAT_MARKERS = (
    "ReduceOnly Order is rejected",
    "-2022",
    "position does not exist",
    "No need to change position",
)


def _is_flat_err(err: str) -> bool:
    low = (err or "").lower()
    return any(m.lower() in low for m in _FLAT_MARKERS)


def _book() -> dict:
    token = (os.environ.get("GPSUSDT_API_TOKEN") or "").strip()
    req = urllib.request.Request(
        "http://127.0.0.1:5050/forex/api/gpsusdt?limit=1",
        headers={"X-Gpsusdt-Token": token, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode())


def _ws_amt() -> float | None:
    try:
        from binance_fapi_guard import cached_positions
        rows = cached_positions(SYMBOL) or []
        if not rows:
            return 0.0
        return float((rows[0] or {}).get("positionAmt") or 0)
    except Exception:
        return None


def _should_retry(book: dict, *, force: bool) -> tuple[bool, str]:
    reject = book.get("last_reject") or {}
    reason = str(reject.get("reason") or "")
    detail = str(reject.get("detail") or "")
    amt = _ws_amt()
    if amt is not None and abs(amt) <= 1e-9:
        return False, "bn_flat"
    if _is_flat_err(detail):
        return False, "already_flat_2022"
    if force:
        return True, "now"
    if reason == "live_close_fail" or "bn_status_unknown" in detail or reason == "bn_status_unknown":
        return True, f"{reason}:{detail}"
    return False, reason or "no_reject"


def _qty_side(book: dict) -> tuple[float, str]:
    try:
        from binance_fapi_guard import cached_positions
        for r in cached_positions(SYMBOL) or []:
            amt = float(r.get("positionAmt") or 0)
            if abs(amt) > 0:
                return abs(amt), "SELL" if amt > 0 else "BUY"
    except Exception:
        pass
    pos = (book.get("positions") or [None])[0] or {}
    qty = abs(float(pos.get("qty") or pos.get("volume") or 0))
    side = str(pos.get("side") or pos.get("dir") or "").lower()
    if side in ("buy", "long", "al"):
        close_side = "SELL"
    elif side in ("sell", "short", "sat"):
        close_side = "BUY"
    else:
        close_side = "SELL"
    return qty, close_side


def close_once(qty: float, close_side: str) -> dict:
    from binance_futures_client import BinanceFuturesClient, BinanceFuturesError

    c = BinanceFuturesClient()
    if not c.configured():
        return {"ok": False, "error": "keys_missing"}
    try:
        order = c.new_order(
            symbol=SYMBOL,
            side=close_side,
            type="MARKET",
            quantity=qty,
            reduceOnly="true",
        )
    except BinanceFuturesError as e:
        msg = str(e)
        if _is_flat_err(msg):
            return {"ok": True, "already_flat": True, "error": msg[:160]}
        return {"ok": False, "error": msg[:160]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}

    oid = order.get("orderId")
    status = str(order.get("status") or "")
    exe = float(order.get("executedQty") or 0)
    avg = float(order.get("avgPrice") or 0)
    if oid and status not in ("FILLED", "PARTIALLY_FILLED"):
        try:
            q = c.query_order(SYMBOL, int(oid))
            status = str(q.get("status") or status)
            exe = float(q.get("executedQty") or exe)
            avg = float(q.get("avgPrice") or avg)
            order = q
        except Exception:
            pass
    filled = status == "FILLED" or exe > 0
    return {
        "ok": filled,
        "order_id": oid,
        "status": status,
        "qty": exe,
        "price": avg,
        "error": None if filled else (status or "unfilled"),
    }


def run(*, force: bool = False) -> dict:
    try:
        book = _book()
    except Exception as e:
        return {"ok": False, "error": f"book:{e}"[:160]}
    go, why = _should_retry(book, force=force)
    if not go:
        print(f"[GPSUSDT] close skip · {why}", flush=True)
        return {"ok": True, "skipped": True, "reason": why}
    qty, close_side = _qty_side(book)
    if qty <= 0:
        print("[GPSUSDT] close skip · qty=0", flush=True)
        return {"ok": True, "already_flat": True, "reason": "qty0"}
    print(
        f"[GPSUSDT] LIVE CLOSE {close_side} qty={qty} why={why}",
        flush=True,
    )
    last: dict = {}
    for i in range(ATTEMPTS):
        last = close_once(qty, close_side)
        last["try"] = i + 1
        if last.get("ok"):
            tag = "FLAT" if last.get("already_flat") else "OK"
            print(
                f"[GPSUSDT] {tag} try={i+1} qty={last.get('qty')} "
                f"@{last.get('price')} orderId={last.get('order_id')}",
                flush=True,
            )
            return last
        print(f"[GPSUSDT] retry {i+1}/{ATTEMPTS} · {last.get('error')}", flush=True)
        if i + 1 < ATTEMPTS:
            time.sleep(SLEEP_SEC)
    return last or {"ok": False, "error": "no_attempt"}


if __name__ == "__main__":
    force = "--now" in sys.argv or "-f" in sys.argv
    out = run(force=force)
    sys.exit(0 if out.get("ok") else 1)
