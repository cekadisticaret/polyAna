#!/usr/bin/env python3
"""Binance USD-M mark + last + hesap pozisyonu — websocket, REST yok.

fstream `/market` `!markPrice@arr` + `!miniTicker@arr`
→ `/tmp/binance_mark_cache.json`
`/private` ACCOUNT_UPDATE → `/tmp/binance_um_positions.json`

  python3 binance_ws_marks.py          # daemon (flock)
  python3 binance_ws_marks.py status   # yaş / sembol sayısı
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
import sys
import threading
import time
from pathlib import Path

import websockets

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from binance_fapi_guard import (  # noqa: E402
    MARK_CACHE_FILE,
    MARK_LOCK_FILE,
    fapi_blocked,
    get_mark,
    marks_age,
    marks_count,
    position_state,
    write_positions_bulk,
)

# 2026-04-23: /market = mark/ticker, /public = bookTicker
WS_URL = (
    "wss://fstream.binance.com/market/stream"
    "?streams=!markPrice@arr/!miniTicker@arr"
)
BOOK_WS_URL = (
    "wss://fstream.binance.com/public/stream"
    "?streams=gpsusdt@bookTicker/xauusdt@bookTicker"
)
_WRITE_MIN_GAP = 0.8
_rows: dict[str, dict] = {}
_last_write = 0.0
_dirty = False
_started = False
_lock_fd: int | None = None


def _try_lock() -> int | None:
    MARK_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(MARK_LOCK_FILE), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    try:
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
    except OSError:
        pass
    return fd


def _apply_mark_arr(items) -> None:
    global _dirty
    if not isinstance(items, list):
        return
    for it in items:
        if not isinstance(it, dict):
            continue
        sym = str(it.get("s") or "").upper()
        if not sym:
            continue
        row = _rows.setdefault(sym, {})
        try:
            px = float(it.get("p") or 0)
            if px > 0:
                row["mark"] = px
        except (TypeError, ValueError):
            pass
        try:
            ix = float(it.get("i") or 0)
            if ix > 0:
                row["index"] = ix
        except (TypeError, ValueError):
            pass
        try:
            row["funding"] = float(it.get("r") or 0)
        except (TypeError, ValueError):
            pass
        try:
            nf = int(it.get("T") or 0)
            if nf:
                row["next_fund"] = nf
        except (TypeError, ValueError):
            pass
        _dirty = True


def _apply_mini_arr(items) -> None:
    global _dirty
    if not isinstance(items, list):
        return
    for it in items:
        if not isinstance(it, dict):
            continue
        sym = str(it.get("s") or "").upper()
        if not sym:
            continue
        try:
            last = float(it.get("c") or 0)
        except (TypeError, ValueError):
            continue
        if last <= 0:
            continue
        _rows.setdefault(sym, {})["last"] = last
        _dirty = True


def _apply_book(it) -> None:
    global _dirty
    if not isinstance(it, dict):
        return
    sym = str(it.get("s") or "").upper()
    if not sym:
        return
    row = _rows.setdefault(sym, {})
    try:
        bid = float(it.get("b") or 0)
        ask = float(it.get("a") or 0)
    except (TypeError, ValueError):
        return
    if bid > 0:
        row["bid"] = bid
    if ask > 0:
        row["ask"] = ask
    try:
        row["bid_qty"] = float(it.get("B") or 0)
        row["ask_qty"] = float(it.get("A") or 0)
    except (TypeError, ValueError):
        pass
    _dirty = True


def _ingest(msg: dict) -> None:
    if not isinstance(msg, dict):
        return
    stream = str(msg.get("stream") or "")
    data = msg.get("data")
    if "markPrice" in stream:
        _apply_mark_arr(data)
    elif "miniTicker" in stream:
        _apply_mini_arr(data)
    elif "bookTicker" in stream:
        _apply_book(data if isinstance(data, dict) else None)
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        if "p" in data[0] and "s" in data[0] and data[0].get("e") == "markPriceUpdate":
            _apply_mark_arr(data)
        elif data[0].get("e") == "24hrMiniTicker":
            _apply_mini_arr(data)


def _flush(*, force: bool = False) -> None:
    global _last_write, _dirty
    if not _rows:
        return
    now = time.time()
    if not force and (not _dirty or now - _last_write < _WRITE_MIN_GAP):
        return
    payload = {
        "updated_at": now,
        "src": "fstream",
        "n": len(_rows),
        "rows": _rows,
    }
    tmp = Path(str(MARK_CACHE_FILE) + ".tmp")
    raw = json.dumps(payload, separators=(",", ":"))
    tmp.write_text(raw)
    os.replace(tmp, MARK_CACHE_FILE)
    _last_write = now
    _dirty = False


async def _run_book() -> None:
    backoff = 1.0
    while True:
        try:
            async with websockets.connect(
                BOOK_WS_URL,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
                max_size=2_000_000,
                open_timeout=15,
                proxy=None,
            ) as ws:
                backoff = 1.0
                print("[ws-book] connected GPS/XAU", flush=True)
                async for raw in ws:
                    try:
                        _ingest(json.loads(raw))
                        _flush()
                    except Exception as e:
                        print(f"[ws-book] parse: {e}", flush=True)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[ws-book] reconnect {backoff:.0f}s: {e}", flush=True)
            await asyncio.sleep(backoff)
            backoff = min(20.0, backoff * 1.7)


async def _run_socket() -> None:
    backoff = 1.0
    while True:
        try:
            async with websockets.connect(
                WS_URL,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
                max_size=8_000_000,
                open_timeout=15,
                proxy=None,
            ) as ws:
                backoff = 1.0
                print(f"[ws-marks] connected n={len(_rows)}", flush=True)
                async for raw in ws:
                    try:
                        _ingest(json.loads(raw))
                        _flush()
                    except Exception as e:
                        print(f"[ws-marks] parse: {e}", flush=True)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[ws-marks] reconnect {backoff:.0f}s: {e}", flush=True)
            await asyncio.sleep(backoff)
            backoff = min(20.0, backoff * 1.7)


def _futures_client():
    kripto = str(_ROOT / "AgustosKripto")
    if kripto not in sys.path:
        sys.path.insert(0, kripto)
    from binance_futures_client import BinanceFuturesClient
    return BinanceFuturesClient()


def _seed_positions() -> int:
    """REST yok — son WS önbelleği kalsın."""
    return 0


def _apply_wallet(msg: dict) -> None:
    a = msg.get("a") or {}
    bals = a.get("B") or []
    usdt = next(
        (b for b in bals if isinstance(b, dict) and str(b.get("a") or "").upper() == "USDT"),
        None,
    )
    if not usdt:
        return
    try:
        wallet = float(usdt.get("wb") or 0)
    except (TypeError, ValueError):
        return
    upnl = 0.0
    for p in a.get("P") or []:
        if not isinstance(p, dict):
            continue
        try:
            upnl += float(p.get("up") or p.get("unRealizedProfit") or 0)
        except (TypeError, ValueError):
            pass
    fx = str(_ROOT / "EylulForex")
    if fx not in sys.path:
        sys.path.insert(0, fx)
    from binance_um_wallet import apply_ws
    apply_ws(wallet=wallet, unrealized=upnl)


def _apply_account_update(msg: dict) -> None:
    ps = ((msg.get("a") or {}).get("P")) or []
    if ps:
        write_positions_bulk(ps, src="user_ws")
    try:
        _apply_wallet(msg)
    except Exception as e:
        print(f"[ws-user] wallet: {e}", flush=True)


def _seed_account() -> bool:
    """REST yok — cüzdan ACCOUNT_UPDATE ile gelir."""
    return False


async def _run_user() -> None:
    """İmzalı hesap: listenKey + /private ACCOUNT_UPDATE — positionRisk REST yok."""
    backoff = 8.0
    while True:
        try:
            if fapi_blocked():
                print("[ws-user] ban — 30s", flush=True)
                await asyncio.sleep(30)
                continue
            c = _futures_client()
            if not c.configured():
                await asyncio.sleep(60)
                continue
            key = c.listen_key_create()
            n = await asyncio.to_thread(_seed_positions)
            await asyncio.to_thread(_seed_account)
            print(f"[ws-user] listenKey seed={n}", flush=True)
            url = f"wss://fstream.binance.com/private/ws?listenKey={key}"
            async with websockets.connect(
                url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
                open_timeout=15,
                proxy=None,
            ) as ws:
                backoff = 8.0

                async def _keepalive():
                    while True:
                        await asyncio.sleep(30 * 60)
                        try:
                            await asyncio.to_thread(c.listen_key_keepalive)
                        except Exception as e:
                            print(f"[ws-user] keepalive: {e}", flush=True)
                            return

                ka = asyncio.create_task(_keepalive())
                try:
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except Exception:
                            continue
                        ev = str(msg.get("e") or "")
                        if ev == "ACCOUNT_UPDATE":
                            _apply_account_update(msg)
                        elif ev == "listenKeyExpired":
                            print("[ws-user] listenKey expired", flush=True)
                            break
                finally:
                    ka.cancel()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[ws-user] reconnect {backoff:.0f}s: {e}", flush=True)
            await asyncio.sleep(backoff)
            backoff = min(60.0, backoff * 1.5)


async def _run_all() -> None:
    await asyncio.gather(_run_socket(), _run_book(), _run_user())


def start_background() -> bool:
    """Dashboard yedek yazıcı — flock alınırsa thread açar, alınmazsa False."""
    global _started, _lock_fd
    if _started:
        return True
    fd = _try_lock()
    if fd is None:
        return False
    _lock_fd = fd
    _started = True

    def _thread():
        try:
            asyncio.run(_run_all())
        except Exception as e:
            print(f"[ws-marks] thread: {e}", flush=True)

    threading.Thread(target=_thread, name="binance-ws-marks", daemon=True).start()
    return True


def _print_status() -> int:
    age = marks_age()
    n = marks_count()
    sample = []
    for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT", "GPSUSDT", "XAUUSDT"):
        px = get_mark(s, max_age=60)
        sample.append(f"{s}={px}" if px else f"{s}=—")
    pos = []
    for s in ("GPSUSDT", "XAUUSDT"):
        st = position_state(s, max_age=1800)
        pos.append(f"{s}={st[0] if st else '—'}")
    print(
        f"age={age:.1f}s n={n} file={MARK_CACHE_FILE} "
        + " ".join(sample) + " pos " + " ".join(pos)
    )
    return 0 if age < 20 and n > 0 else 1


def main() -> int:
    if (sys.argv[1:] or [""])[0] == "status":
        return _print_status()
    print("[ws-marks] start", flush=True)
    while True:
        fd = _try_lock()
        if fd is None:
            print("[ws-marks] lock busy — 20s", flush=True)
            time.sleep(20)
            continue
        global _lock_fd
        _lock_fd = fd
        try:
            asyncio.run(_run_all())
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            print(f"[ws-marks] crash: {e}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    raise SystemExit(main())
