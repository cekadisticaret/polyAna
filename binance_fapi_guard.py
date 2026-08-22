"""Binance Futures (fapi) IP ban — ortak devre kesici + public kline + WS mark.

Okuma (klines/ticker/depth/premium) fapi'ye gitmez — urllib/requests kesilir.
Mum spot/data-api + `/tmp` dosya önbelleği (cron süreçleri paylaşır).
Emir / listenKey yalnız `allow_fapi()` ile geçer (binance_futures_client).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

_FILE = Path("/tmp/binance_fapi_ban.json")
_RE = re.compile(r"banned until (\d+)", re.I)
_KLINE_CACHE: dict[str, tuple[float, list]] = {}
_KLINE_TTL = 25.0
_KLINE_DIR = Path("/tmp/binance_kline_cache")
_KLINE_FILE_TTL = 25.0
_KLINE_HIST_TTL = 300.0
MARK_CACHE_FILE = Path("/tmp/binance_mark_cache.json")
MARK_LOCK_FILE = Path("/tmp/binance_ws_marks.lock")
MARK_MAX_AGE = 20.0
_mark_mem: tuple[float, dict] = (0.0, {})
_KLINE_HOSTS = (
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
)
_tls = threading.local()
_block_installed = False
_ORIG_URLOPEN = urllib.request.urlopen


class FapiReadDenied(RuntimeError):
    """Ham fapi REST — okuma yasak."""


@contextmanager
def allow_fapi():
    """Yalnız imzalı emir / listenKey."""
    old = bool(getattr(_tls, "allow", False))
    _tls.allow = True
    try:
        yield
    finally:
        _tls.allow = old


def _fapi_url(url) -> bool:
    if hasattr(url, "get_full_url"):
        url = url.get_full_url()
    elif hasattr(url, "full_url"):
        url = url.full_url
    return "fapi.binance.com" in str(url)


def _urlopen_guarded(url, *args, **kwargs):
    if _fapi_url(url) and not bool(getattr(_tls, "allow", False)):
        raise FapiReadDenied("fapi REST kapalı — WS / public_klines")
    return _ORIG_URLOPEN(url, *args, **kwargs)


def install_fapi_read_block() -> None:
    """urllib + requests: fapi.binance.com yalnız allow_fapi ile."""
    global _block_installed
    if _block_installed:
        return
    urllib.request.urlopen = _urlopen_guarded  # type: ignore[assignment]
    try:
        import requests.sessions
        orig = requests.sessions.Session.request

        def _req(self, method, url, *a, **kw):
            if _fapi_url(url) and not bool(getattr(_tls, "allow", False)):
                raise FapiReadDenied("fapi REST kapalı — WS / public_klines")
            return orig(self, method, url, *a, **kw)

        requests.sessions.Session.request = _req  # type: ignore[method-assign]
    except Exception:
        pass
    try:
        import aiohttp.client
        orig_aio = aiohttp.client.ClientSession._request

        async def _aio(self, method, str_or_url, *a, **kw):
            if _fapi_url(str_or_url) and not bool(getattr(_tls, "allow", False)):
                raise FapiReadDenied("fapi REST kapalı — WS / public_klines")
            return await orig_aio(self, method, str_or_url, *a, **kw)

        aiohttp.client.ClientSession._request = _aio  # type: ignore[method-assign]
    except Exception:
        pass
    _block_installed = True


def ban_until() -> float:
    try:
        d = json.loads(_FILE.read_text())
        return float(d.get("until") or 0)
    except Exception:
        return 0.0


def fapi_blocked() -> bool:
    return time.time() < ban_until()


def fapi_ok() -> bool:
    return not fapi_blocked()


def ban_msg() -> str:
    left = max(0, int(ban_until() - time.time()))
    if left <= 0:
        return "Binance fapi ban bitti"
    m, s = divmod(left, 60)
    return f"Binance fapi IP ban · {m}dk {s}sn kaldı"


def status() -> dict:
    left = max(0, int(ban_until() - time.time()))
    blocked = left > 0
    return {
        "blocked": blocked,
        "left_sec": left,
        "msg": ban_msg() if blocked else "",
    }


def note_418(text: str = "", extra_sec: float = 90.0) -> float:
    until = 0.0
    m = _RE.search(str(text or ""))
    if m:
        raw = int(m.group(1))
        until = raw / 1000.0 if raw > 10_000_000_000 else float(raw)
    if until <= time.time():
        until = time.time() + extra_sec
    try:
        _FILE.write_text(json.dumps({
            "until": until,
            "at": time.time(),
            "note": str(text)[:240],
        }))
    except OSError:
        pass
    return until


def _kline_file(ck: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in ck)
    return _KLINE_DIR / f"{safe}.json"


def public_klines(
    symbol: str,
    interval: str = "1h",
    limit: int = 80,
    start_time_ms: int | None = None,
) -> list:
    """Ham kline — yalnız spot/data-api. fapi yok. Süreç + dosya önbelleği."""
    sym = (symbol or "").upper()
    start = int(start_time_ms) if start_time_ms else 0
    ck = f"{sym}|{interval}|{int(limit)}|{start}"
    now = time.time()
    ttl = _KLINE_HIST_TTL if start else _KLINE_TTL
    hit = _KLINE_CACHE.get(ck)
    if hit and now - hit[0] < ttl:
        return hit[1]
    fp = _kline_file(ck)
    try:
        if fp.is_file() and now - fp.stat().st_mtime < ttl:
            raw = json.loads(fp.read_text())
            if isinstance(raw, list) and raw:
                _KLINE_CACHE[ck] = (now, raw)
                return raw
    except Exception:
        pass
    qs = f"symbol={sym}&interval={interval}&limit={int(limit)}"
    if start:
        qs += f"&startTime={start}"
    last_err: Exception | None = None
    for base in _KLINE_HOSTS:
        url = f"{base}?{qs}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "aiProject/1.0"})
            with _ORIG_URLOPEN(req, timeout=10) as resp:
                raw = json.load(resp)
            if isinstance(raw, list) and raw:
                _KLINE_CACHE[ck] = (now, raw)
                try:
                    _KLINE_DIR.mkdir(parents=True, exist_ok=True)
                    tmp = Path(str(fp) + ".tmp")
                    tmp.write_text(json.dumps(raw, separators=(",", ":")))
                    os.replace(tmp, fp)
                except OSError:
                    pass
                return raw
        except Exception as e:
            last_err = e
            continue
    if last_err:
        raise last_err
    return []


def _load_marks() -> dict:
    global _mark_mem
    try:
        mtime = MARK_CACHE_FILE.stat().st_mtime
    except OSError:
        return {}
    if _mark_mem[0] == mtime and _mark_mem[1]:
        return _mark_mem[1]
    try:
        d = json.loads(MARK_CACHE_FILE.read_text())
    except Exception:
        return {}
    if not isinstance(d, dict):
        return {}
    _mark_mem = (mtime, d)
    return d


def marks_age() -> float:
    ts = float(_load_marks().get("updated_at") or 0)
    if ts <= 0:
        return 1e9
    return max(0.0, time.time() - ts)


def marks_fresh(max_age: float = MARK_MAX_AGE) -> bool:
    return marks_age() < float(max_age)


def marks_count() -> int:
    d = _load_marks()
    n = d.get("n")
    if n is not None:
        try:
            return int(n)
        except (TypeError, ValueError):
            pass
    return len(d.get("rows") or {})


def _row(symbol: str) -> dict:
    rows = _load_marks().get("rows") or {}
    hit = rows.get((symbol or "").upper())
    return hit if isinstance(hit, dict) else {}


def get_mark(symbol: str, max_age: float = MARK_MAX_AGE) -> float | None:
    if not marks_fresh(max_age):
        return None
    try:
        px = float(_row(symbol).get("mark") or 0)
    except (TypeError, ValueError):
        return None
    return px if px > 0 else None


def get_last(symbol: str, max_age: float = MARK_MAX_AGE) -> float | None:
    if not marks_fresh(max_age):
        return None
    try:
        px = float(_row(symbol).get("last") or 0)
    except (TypeError, ValueError):
        return None
    return px if px > 0 else None


def get_book(symbol: str, max_age: float = MARK_MAX_AGE) -> dict | None:
    """WS bid/ask. Yoksa None — REST yok."""
    if not marks_fresh(max_age):
        return None
    row = _row(symbol)
    try:
        bid = float(row.get("bid") or 0)
        ask = float(row.get("ask") or 0)
    except (TypeError, ValueError):
        return None
    if bid <= 0 and ask <= 0:
        return None
    try:
        bq = float(row.get("bid_qty") or 0)
        aq = float(row.get("ask_qty") or 0)
    except (TypeError, ValueError):
        bq = aq = 0.0
    return {
        "symbol": (symbol or "").upper(),
        "bid": bid,
        "ask": ask,
        "bid_qty": bq,
        "ask_qty": aq,
        "bidPrice": bid,
        "askPrice": ask,
    }


def ws_premium(symbol: str, max_age: float = MARK_MAX_AGE) -> dict | None:
    """mark / index / funding — taze WS satırı, yoksa None (REST yedek)."""
    if not marks_fresh(max_age):
        return None
    row = _row(symbol)
    try:
        mark = float(row.get("mark") or 0)
    except (TypeError, ValueError):
        mark = 0.0
    if mark <= 0:
        return None
    try:
        index = float(row.get("index") or 0)
    except (TypeError, ValueError):
        index = 0.0
    try:
        funding = float(row.get("funding") or 0)
    except (TypeError, ValueError):
        funding = 0.0
    try:
        nxt = int(row.get("next_fund") or 0)
    except (TypeError, ValueError):
        nxt = 0
    return {
        "mark": mark,
        "index": index or mark,
        "last_funding_rate": funding,
        "next_funding_time": nxt,
    }


POS_CACHE_FILE = Path("/tmp/binance_um_positions.json")
POS_MAX_AGE = 1800.0
POS_BAN_MAX_AGE = 3600.0
_pos_mem: tuple[float, dict] = (0.0, {})


def _load_pos() -> dict:
    global _pos_mem
    try:
        mtime = POS_CACHE_FILE.stat().st_mtime
    except OSError:
        return {}
    if _pos_mem[0] == mtime and _pos_mem[1]:
        return _pos_mem[1]
    try:
        d = json.loads(POS_CACHE_FILE.read_text())
    except Exception:
        return {}
    if not isinstance(d, dict):
        return {}
    _pos_mem = (mtime, d)
    return d


def write_position(
    symbol: str,
    *,
    amt: float,
    entry: float = 0.0,
    mark: float = 0.0,
    upnl: float = 0.0,
    leverage: float = 0.0,
    margin_type: str = "",
    src: str = "rest",
) -> None:
    sym = (symbol or "").upper()
    if not sym:
        return
    d = dict(_load_pos() or {})
    rows = dict(d.get("rows") or {})
    rows[sym] = {
        "symbol": sym,
        "positionAmt": float(amt),
        "entryPrice": float(entry or 0),
        "markPrice": float(mark or 0),
        "unRealizedProfit": float(upnl or 0),
        "leverage": float(leverage or 0),
        "marginType": margin_type or "",
        "src": src,
    }
    payload = {"updated_at": time.time(), "src": src, "rows": rows}
    tmp = Path(str(POS_CACHE_FILE) + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    os.replace(tmp, POS_CACHE_FILE)
    _pos_mem = (POS_CACHE_FILE.stat().st_mtime, payload)


def write_positions_bulk(items: list[dict], *, src: str = "rest") -> None:
    d = dict(_load_pos() or {})
    rows = dict(d.get("rows") or {})
    now = time.time()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        sym = str(it.get("symbol") or it.get("s") or "").upper()
        if not sym:
            continue
        try:
            amt = float(it.get("positionAmt") or it.get("pa") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        rows[sym] = {
            "symbol": sym,
            "positionAmt": amt,
            "entryPrice": float(it.get("entryPrice") or it.get("ep") or 0),
            "markPrice": float(it.get("markPrice") or it.get("mp") or 0),
            "unRealizedProfit": float(it.get("unRealizedProfit") or it.get("up") or 0),
            "leverage": float(it.get("leverage") or 0),
            "marginType": str(it.get("marginType") or it.get("mt") or ""),
            "src": src,
        }
    payload = {"updated_at": now, "src": src, "rows": rows}
    tmp = Path(str(POS_CACHE_FILE) + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    os.replace(tmp, POS_CACHE_FILE)
    _pos_mem = (POS_CACHE_FILE.stat().st_mtime, payload)


def cached_positions(symbol: str | None = None) -> list[dict]:
    """WS/önbellek pozisyon satırları — fapi GET yok."""
    want = (symbol or "").upper() or None
    out: list[dict] = []
    for r in (_load_pos().get("rows") or {}).values():
        if not isinstance(r, dict):
            continue
        if want and str(r.get("symbol") or "").upper() != want:
            continue
        out.append(r)
    return out


def position_state(symbol: str, max_age: float | None = None) -> tuple[str, dict | None] | None:
    """Taze önbellek: ('open', row) | ('flat', None). Yok/bayat: None."""
    d = _load_pos()
    ts = float(d.get("updated_at") or 0)
    if ts <= 0:
        return None
    if max_age is None:
        max_age = POS_BAN_MAX_AGE if fapi_blocked() else POS_MAX_AGE
    if time.time() - ts > float(max_age):
        return None
    row = (d.get("rows") or {}).get((symbol or "").upper())
    if not isinstance(row, dict):
        return None
    try:
        amt = float(row.get("positionAmt") or 0)
    except (TypeError, ValueError):
        return None
    if abs(amt) > 0:
        return "open", row
    return "flat", None


install_fapi_read_block()
