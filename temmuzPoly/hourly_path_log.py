#!/usr/bin/env python3
"""Saatlik BTC/ETH/SOL yol kaydı — algoritma işlemlerinden ayrı.

Referans = o saatin 1h açılışı (PTB çizgisi). Emir yok.
Güncelleme: `binance_ws_marks.py` WS → `apply_prices()` (disk ~15 sn / dakika değişimi).
Yedek: `python3 temmuzPoly/hourly_path_log.py tick` (WS önbelleği).
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from binance_fapi_guard import get_last, get_mark, public_klines  # noqa: E402

_TZ = ZoneInfo("Europe/Istanbul")
_OUT = _DIR / "hourly_path"
_LOCK = _OUT / ".lock"
_KEEP_DAYS = 21
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def now_tr() -> datetime:
    return datetime.now(_TZ)


def hour_start(dt: datetime | None = None) -> datetime:
    t = (dt or now_tr()).astimezone(_TZ)
    return t.replace(minute=0, second=0, microsecond=0)


def hour_key(dt: datetime | None = None) -> str:
    return hour_start(dt).strftime("%Y-%m-%d_%H")


def _path(key: str) -> Path:
    return _OUT / f"{key}.json"


def _rnd(sym: str, px: float) -> float:
    if sym.startswith("BTC"):
        return round(float(px), 2)
    if sym.startswith("ETH"):
        return round(float(px), 2)
    return round(float(px), 4)


def _live_px(sym: str) -> float | None:
    px = get_last(sym) or get_mark(sym)
    try:
        v = float(px or 0)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _empty_coin(sym: str) -> dict:
    return {
        "symbol": sym,
        "ref": None,
        "ref_src": None,
        "last": None,
        "end": None,
        "hi": None,
        "lo": None,
        "max_up_usd": 0.0,
        "max_dn_usd": 0.0,
        "max_up_bps": 0.0,
        "max_dn_bps": 0.0,
        "now_vs_ref_usd": 0.0,
        "now_vs_ref_bps": 0.0,
        "above_n": 0,
        "below_n": 0,
        "flat_n": 0,
        "winner": None,
        "minutes": [],
    }


def _empty_hour(hs: datetime) -> dict:
    return {
        "hour_tr": hs.isoformat(),
        "hour_key": hs.strftime("%Y-%m-%d_%H"),
        "updated_at_tr": now_tr().isoformat(),
        "sealed": False,
        "coins": {sym.replace("USDT", ""): _empty_coin(sym) for sym in SYMBOLS},
    }


def load_hour(key: str) -> dict:
    fp = _path(key)
    if not fp.is_file():
        hs = datetime.strptime(key, "%Y-%m-%d_%H").replace(tzinfo=_TZ)
        return _empty_hour(hs)
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        hs = datetime.strptime(key, "%Y-%m-%d_%H").replace(tzinfo=_TZ)
        return _empty_hour(hs)
    if not isinstance(data, dict):
        hs = datetime.strptime(key, "%Y-%m-%d_%H").replace(tzinfo=_TZ)
        return _empty_hour(hs)
    data.setdefault("coins", {})
    for sym in SYMBOLS:
        coin = sym.replace("USDT", "")
        if coin not in data["coins"] or not isinstance(data["coins"][coin], dict):
            data["coins"][coin] = _empty_coin(sym)
    return data


def save_hour(data: dict) -> None:
    _OUT.mkdir(parents=True, exist_ok=True)
    data["updated_at_tr"] = now_tr().isoformat()
    key = data["hour_key"]
    raw = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = _path(key).with_suffix(".json.tmp")
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, _path(key))
    if key == hour_key():
        latest = _OUT / "latest.json"
        tmp2 = _OUT / "latest.json.tmp"
        tmp2.write_text(raw, encoding="utf-8")
        os.replace(tmp2, latest)


def _delta(px: float, ref: float) -> tuple[float, float, float]:
    d_usd = round(px - ref, 6)
    if ref <= 0:
        return d_usd, 0.0, 0.0
    d_pct = (px - ref) / ref * 100.0
    d_bps = d_pct * 100.0
    return d_usd, round(d_bps, 3), round(d_pct, 5)


def _hour_open(sym: str, hs: datetime) -> float | None:
    start_ms = int(hs.timestamp() * 1000)
    try:
        rows = public_klines(sym, "1h", 1, start_time_ms=start_ms)
    except Exception:
        rows = []
    if not rows:
        return None
    try:
        o = float(rows[0][1])
    except (TypeError, ValueError, IndexError):
        return None
    return o if o > 0 else None


def _minute_klines(sym: str, hs: datetime) -> list:
    start_ms = int(hs.timestamp() * 1000)
    try:
        rows = public_klines(sym, "1m", 60, start_time_ms=start_ms)
    except Exception:
        return []
    return rows if isinstance(rows, list) else []


def _min_idx(row: dict) -> int:
    try:
        return int(row.get("m"))
    except (TypeError, ValueError):
        return -1


def _dedup_minutes(coin: dict) -> None:
    seen: dict[int, dict] = {}
    for row in coin.get("minutes") or []:
        m = _min_idx(row)
        if m < 0:
            continue
        prev = seen.get(m)
        if prev is None:
            seen[m] = row
            continue
        if row.get("h") is not None:
            prev["h"] = row["h"]
        if row.get("l") is not None:
            prev["l"] = row["l"]
        prev.update({k: row[k] for k in ("t", "px", "d_usd", "d_bps", "d_pct") if k in row})
    coin["minutes"] = [seen[m] for m in sorted(seen)]


def _upsert_minute(coin: dict, m: int, tlabel: str, px: float, hi: float | None, lo: float | None) -> None:
    mins = coin.setdefault("minutes", [])
    row = None
    for existing in mins:
        if _min_idx(existing) == m:
            row = existing
            break
    if row is None:
        row = {"m": m}
        mins.append(row)
    ref = float(coin["ref"] or px)
    d_usd, d_bps, d_pct = _delta(px, ref)
    row["t"] = tlabel
    row["px"] = px
    if hi is not None:
        row["h"] = hi
    if lo is not None:
        row["l"] = lo
    row["d_usd"] = round(d_usd, 6)
    row["d_bps"] = d_bps
    row["d_pct"] = d_pct
    mins.sort(key=lambda r: int(r.get("m") or 0))
    coin["last"] = px


def _recompute(coin: dict) -> None:
    ref = coin.get("ref")
    mins = coin.get("minutes") or []
    if ref is None or not mins:
        return
    ref = float(ref)
    hi = lo = None
    max_up = max_dn = 0.0
    above = below = flat = 0
    for row in mins:
        px = float(row.get("px") or 0)
        h = float(row["h"]) if row.get("h") is not None else px
        l = float(row["l"]) if row.get("l") is not None else px
        if px <= 0:
            continue
        hi = h if hi is None else max(hi, h)
        lo = l if lo is None else min(lo, l)
        max_up = max(max_up, h - ref)
        max_dn = max(max_dn, ref - l)
        if px > ref:
            above += 1
        elif px < ref:
            below += 1
        else:
            flat += 1
    last = float(coin.get("last") or mins[-1].get("px") or 0)
    d_usd, d_bps, _ = _delta(last, ref) if last else (0.0, 0.0, 0.0)
    coin["hi"] = _rnd(coin["symbol"], hi) if hi else None
    coin["lo"] = _rnd(coin["symbol"], lo) if lo else None
    coin["max_up_usd"] = round(max_up, 6)
    coin["max_dn_usd"] = round(max_dn, 6)
    coin["max_up_bps"] = round(max_up / ref * 10000, 3) if ref else 0.0
    coin["max_dn_bps"] = round(max_dn / ref * 10000, 3) if ref else 0.0
    coin["now_vs_ref_usd"] = round(d_usd, 6)
    coin["now_vs_ref_bps"] = d_bps
    coin["above_n"] = above
    coin["below_n"] = below
    coin["flat_n"] = flat
    if coin.get("sealed") or coin.get("end") is not None:
        if last > ref:
            coin["winner"] = "UP"
        elif last < ref:
            coin["winner"] = "DOWN"
        else:
            coin["winner"] = "FLAT"


def _ensure_ref(coin: dict, sym: str, hs: datetime, fallback: float | None) -> None:
    if coin.get("ref"):
        return
    o = _hour_open(sym, hs)
    if o:
        coin["ref"] = _rnd(sym, o)
        coin["ref_src"] = "hour_open"
        return
    if fallback:
        coin["ref"] = _rnd(sym, fallback)
        coin["ref_src"] = "first_tick"


def _backfill_coin(coin: dict, sym: str, hs: datetime) -> None:
    rows = _minute_klines(sym, hs)
    start_ms = int(hs.timestamp() * 1000)
    for k in rows:
        try:
            ts = int(k[0])
            o, h, l, c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
        except (TypeError, ValueError, IndexError):
            continue
        m = int((ts - start_ms) // 60000)
        if m < 0 or m > 59:
            continue
        tlabel = (hs + timedelta(minutes=m)).strftime("%H:%M")
        _upsert_minute(
            coin, m, tlabel, _rnd(sym, c),
            _rnd(sym, h), _rnd(sym, l),
        )
        if o and not coin.get("ref"):
            coin["ref"] = _rnd(sym, o)
            coin["ref_src"] = "first_1m_open"


def _seal(data: dict) -> None:
    data["sealed"] = True
    for coin in data.get("coins", {}).values():
        _dedup_minutes(coin)
        if coin.get("last") is not None:
            coin["end"] = coin["last"]
        _recompute(coin)
        if coin.get("ref") and coin.get("end"):
            if coin["end"] > coin["ref"]:
                coin["winner"] = "UP"
            elif coin["end"] < coin["ref"]:
                coin["winner"] = "DOWN"
            else:
                coin["winner"] = "FLAT"


def _prune() -> None:
    cut = now_tr() - timedelta(days=_KEEP_DAYS)
    for fp in _OUT.glob("20*.json"):
        try:
            key = fp.stem
            dt = datetime.strptime(key, "%Y-%m-%d_%H").replace(tzinfo=_TZ)
        except ValueError:
            continue
        if dt < cut:
            try:
                fp.unlink()
            except OSError:
                pass


def _lock():
    _OUT.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(_LOCK), os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _seal_previous_hour(hs: datetime) -> None:
    prev_key = hour_key(hs - timedelta(seconds=1))
    if prev_key == hour_key(hs):
        return
    prev = load_hour(prev_key)
    if not prev.get("coins") or prev.get("sealed"):
        return
    prev_hs = hour_start(hs - timedelta(seconds=1))
    for sym in SYMBOLS:
        ck = sym.replace("USDT", "")
        _backfill_coin(prev["coins"][ck], sym, prev_hs)
        _recompute(prev["coins"][ck])
    _seal(prev)
    save_hour(prev)


def apply_prices(
    prices: dict[str, float],
    t: datetime | None = None,
    *,
    backfill_gaps: bool = False,
) -> dict:
    """WS / önbellek fiyatlarıyla güncelle — REST yok (ref yoksa 1h open bir kez)."""
    fd = _lock()
    try:
        t = (t or now_tr()).astimezone(_TZ)
        hs = hour_start(t)
        key = hour_key(t)
        data = load_hour(key)
        m = t.minute
        tlabel = t.strftime("%H:%M")

        _seal_previous_hour(hs)

        for sym in SYMBOLS:
            coin_k = sym.replace("USDT", "")
            coin = data["coins"][coin_k]
            live = prices.get(sym)
            if live is None:
                live = prices.get(coin_k)
            if live is not None:
                try:
                    live = float(live)
                except (TypeError, ValueError):
                    live = None
            if live is not None and live <= 0:
                live = None
            _ensure_ref(coin, sym, hs, live)
            _dedup_minutes(coin)
            if backfill_gaps:
                have = {_min_idx(r) for r in (coin.get("minutes") or [])}
                if len(have) < min(m + 1, 60):
                    _backfill_coin(coin, sym, hs)
            if live:
                _upsert_minute(coin, m, tlabel, _rnd(sym, live), None, None)
            if not coin.get("ref") and live:
                coin["ref"] = _rnd(sym, live)
                coin["ref_src"] = "first_tick"
            _dedup_minutes(coin)
            _recompute(coin)

        save_hour(data)
        _prune()
        return data
    finally:
        os.close(fd)


def tick(*, backfill_gaps: bool = False) -> dict:
    """Yedek tur — fiyatlar WS önbelleğinden (`get_last` / `get_mark`)."""
    prices: dict[str, float] = {}
    for sym in SYMBOLS:
        live = _live_px(sym)
        if live:
            prices[sym] = live
    if not prices:
        return load_hour(hour_key())
    return apply_prices(prices, backfill_gaps=backfill_gaps)


def _fmt_coin(coin: dict) -> str:
    name = coin.get("symbol", "?").replace("USDT", "")
    ref = coin.get("ref")
    last = coin.get("last")
    if ref is None or last is None:
        return f"{name} —"
    sign = "+" if coin.get("now_vs_ref_usd", 0) >= 0 else ""
    return (
        f"{name} ref={ref} now={last} {sign}{coin.get('now_vs_ref_usd')} "
        f"({coin.get('now_vs_ref_bps')}bps) "
        f"max+{coin.get('max_up_usd')}/-{coin.get('max_dn_usd')} "
        f"n={len(coin.get('minutes') or [])}"
    )


def run_status() -> None:
    latest = _OUT / "latest.json"
    if not latest.is_file():
        print("hourly_path — henüz kayıt yok")
        return
    data = json.loads(latest.read_text(encoding="utf-8"))
    print(f"hourly_path {data.get('hour_key')} · güncel {data.get('updated_at_tr', '')[:16]}")
    for coin in data.get("coins", {}).values():
        print(" ", _fmt_coin(coin))


def backfill_hours(n: int = 24) -> int:
    """Geçmiş saatleri 1m mumdan doldurur. Emir yok."""
    fd = _lock()
    wrote = 0
    try:
        now = now_tr()
        cur = hour_start(now)
        for i in range(1, max(1, n) + 1):
            hs = cur - timedelta(hours=i)
            key = hour_key(hs)
            data = load_hour(key)
            for sym in SYMBOLS:
                ck = sym.replace("USDT", "")
                coin = data["coins"][ck]
                _ensure_ref(coin, sym, hs, None)
                _backfill_coin(coin, sym, hs)
                _dedup_minutes(coin)
                if coin.get("minutes"):
                    coin["last"] = coin["minutes"][-1].get("px")
            _seal(data)
            save_hour(data)
            wrote += 1
            print(f"backfill {key} · " + " · ".join(_fmt_coin(c) for c in data["coins"].values()))
        return wrote
    finally:
        os.close(fd)


def main() -> int:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "tick").strip().lower()
    if mode in ("status", "dump"):
        run_status()
        return 0
    if mode == "backfill":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        backfill_hours(n)
        return 0
    data = tick()
    t = now_tr().strftime("%H:%M")
    bits = [_fmt_coin(c) for c in data.get("coins", {}).values()]
    print(f"[hourly_path] {t} · {data.get('hour_key')} · " + " · ".join(bits))
    return 0


if __name__ == "__main__":
    sys.exit(main())
