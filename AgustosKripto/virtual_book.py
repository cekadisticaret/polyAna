#!/usr/bin/env python3
"""Sanal Binance Futures defteri — $300 / $15×15x / saatlik max 6 işlem.

Poly koduna dokunmaz. AgustosKripto Algoritmalar + Analizler runner'ları kullanır.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

from atr_profit_lock import (
    LOSS_STOP_MIN_AGE_MIN,
    atr_from_klines,
    init_lock_fields,
    lock_summary,
    loss_stop_threshold,
    should_loss_stop,
    should_skip_hourly_close,
    should_stop_out,
    update_lock,
)
from fee_utils import DEFAULT_TAKER_FEE, estimate_fee, get_taker_rate, net_pnl

_TZ = ZoneInfo("Europe/Istanbul")
# Sanal defter — Binance USDT-M taker varsayılanı (gerçek oran alınamazsa fallback)
TAKER_FEE_RATE = float(os.environ.get("VIRTUAL_TAKER_FEE", DEFAULT_TAKER_FEE))

# Kısa TTL — dashboard poll her seferinde Binance'e gitmesin
_KLINE_CACHE: dict[str, tuple[float, list]] = {}
_KLINE_TTL_SEC = 30.0
_STATUS_CACHE: dict[str, tuple[float, dict]] = {}
_STATUS_TTL_SEC = 30.0
_SNAP_DIR = "/tmp/agustos_snap"
_SNAP_MAX_AGE_SEC = 60.0

# ── Gerçek Binance komisyon oranı (sanal defterler için de) ─────────────
# Emir açılmaz; sadece "gerçekten açılsaydı" ne kadar komisyon keseceğini
# öğrenmek için commissionRate API'si sorgulanır (dosya cache 6 saat).
_FEE_CACHE_PATH = "/tmp/agustos_snap/_fee_rate_cache.json"
_FEE_CACHE_TTL_SEC = 6 * 3600.0
_real_fee_client = None
_fee_client_tried = False


def _get_real_fee_client():
    global _real_fee_client, _fee_client_tried
    if _fee_client_tried:
        return _real_fee_client
    _fee_client_tried = True
    try:
        from binance_futures_client import BinanceFuturesClient

        client = BinanceFuturesClient()
        _real_fee_client = client if client.configured() else None
    except Exception as e:
        print(f"[virtual_book] fee client init: {e}")
        _real_fee_client = None
    return _real_fee_client


def _load_fee_cache() -> dict:
    try:
        with open(_FEE_CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_fee_cache(cache: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_FEE_CACHE_PATH), exist_ok=True)
        tmp = _FEE_CACHE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cache, f)
        os.replace(tmp, _FEE_CACHE_PATH)
    except Exception:
        pass


def real_taker_rate(symbol: str = "BTCUSDT") -> float:
    """Binance'ten gerçek taker komisyon oranını çek (6h dosya cache + fallback)."""
    sym = (symbol or "BTCUSDT").upper()
    cache = _load_fee_cache()
    hit = cache.get(sym)
    if hit and (time.time() - float(hit.get("ts") or 0)) < _FEE_CACHE_TTL_SEC:
        return float(hit.get("rate") or TAKER_FEE_RATE)
    client = _get_real_fee_client()
    try:
        rate = get_taker_rate(client, sym)
    except Exception as e:
        print(f"[virtual_book] real_taker_rate {sym}: {e}")
        rate = TAKER_FEE_RATE
    cache[sym] = {"rate": rate, "ts": time.time()}
    _save_fee_cache(cache)
    return float(rate or TAKER_FEE_RATE)


# ── Dosya kilidi — eşzamanlı cron (close/open/trail/scan) yarışını önler ──
@contextlib.contextmanager
def book_lock(state_path: str):
    lock_path = state_path + ".lock"
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fh, fcntl.LOCK_UN)
        finally:
            fh.close()


def write_snapshot(key: str, data: dict) -> None:
    try:
        os.makedirs(_SNAP_DIR, exist_ok=True)
        path = os.path.join(_SNAP_DIR, f"{key}.json")
        tmp = path + ".tmp"
        payload = {"ts": time.time(), "data": data}
        with open(tmp, "w") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[virtual_book] snapshot write {key}: {e}")


def read_snapshot(key: str, max_age: float | None = None) -> dict | None:
    """Disk snapshot — API'yi anında döndürmek için (Binance beklemeden)."""
    max_age = _SNAP_MAX_AGE_SEC if max_age is None else max_age
    path = os.path.join(_SNAP_DIR, f"{key}.json")
    try:
        with open(path) as f:
            payload = json.load(f)
        ts = float(payload.get("ts") or 0)
        if time.time() - ts > max_age:
            return None
        data = payload.get("data")
        if isinstance(data, dict):
            data = dict(data)
            data["_from_snapshot"] = True
            data["_snapshot_age_sec"] = round(time.time() - ts, 1)
            return data
    except Exception:
        return None
    return None

DEPOSIT = 300.0
MARGIN_USD = 15.0
LEVERAGE = 15
MAX_OPENS_PER_HOUR = 6
NOTIONAL = MARGIN_USD * LEVERAGE  # 225

# Saatlik tarama evreni (max 6 seçim için)
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "LTCUSDT", "NEARUSDT", "SUIUSDT", "APTUSDT", "ARBUSDT",
    "OPUSDT", "INJUSDT", "TIAUSDT",
]


def now_tr() -> datetime:
    return datetime.now(_TZ)


def now_tr_iso() -> str:
    return now_tr().isoformat()


def in_weekend_pause_tr(now: datetime | None = None) -> bool:
    """Cum 22:00 – Pzt 11:00 İST — sanal Algoritma/Analiz open/close/trail yok."""
    n = now or now_tr()
    if n.tzinfo is None:
        n = n.replace(tzinfo=_TZ)
    else:
        n = n.astimezone(_TZ)
    dow, h = n.weekday(), n.hour  # Mon=0 … Fri=4 Sat=5 Sun=6
    if dow == 4 and h >= 22:
        return True
    if dow in (5, 6):
        return True
    if dow == 0 and h < 11:
        return True
    return False


def new_state() -> dict:
    return {
        "balance": DEPOSIT,
        "deposit": DEPOSIT,
        "open_positions": [],
        "total_pnl": 0.0,
        "total_commission": 0.0,
        "updated_at_tr": "",
        "last_open_slot": "",
    }


def reset_book(
    state_path: str,
    *,
    balance: float = DEPOSIT,
    clear_history_path: str | None = None,
) -> dict:
    """Açık pozisyonları düş, bakiyeyi deposit'e çek (sanal reset)."""
    st = new_state()
    bal = float(balance)
    st["balance"] = bal
    st["deposit"] = bal
    st["open_positions"] = []
    st["total_pnl"] = 0.0
    st["total_commission"] = 0.0
    st["last_open_slot"] = ""
    save_state(state_path, st)
    if clear_history_path:
        save_json(clear_history_path, [])
    # status cache invalid
    try:
        _STATUS_CACHE.clear()
    except Exception:
        pass
    return st


def load_json(path: str, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return default() if callable(default) else default


def save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_state(path: str) -> dict:
    st = load_json(path, new_state)
    if "balance" not in st:
        st = new_state()
    st.setdefault("open_positions", [])
    st.setdefault("total_pnl", 0.0)
    st.setdefault("total_commission", 0.0)
    st.setdefault("deposit", DEPOSIT)
    return st


def save_state(path: str, state: dict) -> None:
    state["updated_at_tr"] = now_tr_iso()
    save_json(path, state)


def load_history(path: str) -> list:
    return load_json(path, list)


def save_history(path: str, history: list) -> None:
    save_json(path, history)


def fetch_klines(symbol: str, interval: str = "1h", limit: int = 80, *, use_cache: bool = True) -> list[dict]:
    ck = f"{symbol}|{interval}|{limit}"
    if use_cache:
        hit = _KLINE_CACHE.get(ck)
        if hit and (time.time() - hit[0]) < _KLINE_TTL_SEC:
            return hit[1]
    url = (
        f"https://fapi.binance.com/fapi/v1/klines?"
        f"symbol={symbol}&interval={interval}&limit={limit}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "AgustosKripto/1.0"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        raw = json.load(resp)
    out = []
    for k in raw:
        out.append({
            "t": int(k[0]) // 1000,
            "o": float(k[1]),
            "h": float(k[2]),
            "l": float(k[3]),
            "c": float(k[4]),
            "v": float(k[5]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })
    if use_cache:
        _KLINE_CACHE[ck] = (time.time(), out)
    return out


def fetch_all_klines(
    symbols: list[str] | None = None,
    limit: int = 80,
    *,
    interval: str = "1h",
) -> dict[str, list]:
    """Paralel + TTL cache — dashboard yavaşlığının ana çözümü."""
    syms = list(symbols or SYMBOLS)
    iv = interval or "1h"
    out: dict[str, list] = {}
    need: list[str] = []
    now = time.time()
    for sym in syms:
        ck = f"{sym}|{iv}|{limit}"
        hit = _KLINE_CACHE.get(ck)
        if hit and (now - hit[0]) < _KLINE_TTL_SEC:
            out[sym] = hit[1]
        else:
            need.append(sym)
    if need:
        def _one(sym: str):
            try:
                return sym, fetch_klines(sym, iv, limit, use_cache=True)
            except Exception as e:
                print(f"[virtual_book] kline {sym} {iv}: {e}")
                return sym, []
        with ThreadPoolExecutor(max_workers=min(8, len(need))) as pool:
            futs = [pool.submit(_one, s) for s in need]
            for fut in as_completed(futs):
                sym, kl = fut.result()
                out[sym] = kl
    return out


# Adaydan pozisyona taşınan ek alanlar — kenar kapısı kademesi ve süre sınırı
_CAND_CARRY = ("max_hold_h", "edge_tier", "edge_skill_pct", "edge_t", "edge_hours")


def _pos_interval(pos: dict) -> str:
    return str(pos.get("interval") or "1h")


def _can_settle_interval(interval: str) -> bool:
    """4h pozisyonlar yalnızca 4h mum kapanışında settle edilir."""
    if interval != "4h":
        return True
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).hour % 4 == 0


def cached_status(key: str, builder) -> dict:
    hit = _STATUS_CACHE.get(key)
    if hit and (time.time() - hit[0]) < _STATUS_TTL_SEC:
        return hit[1]
    # Disk snapshot varsa hemen dön (arka plan ısıtma ile taze kalır)
    snap = read_snapshot(key)
    if snap is not None:
        _STATUS_CACHE[key] = (time.time(), snap)
        return snap
    data = builder()
    _STATUS_CACHE[key] = (time.time(), data)
    write_snapshot(key, data)
    return data


def refresh_status(key: str, builder) -> dict:
    """Zorla yenile + snapshot yaz (prewarm thread)."""
    data = builder()
    _STATUS_CACHE[key] = (time.time(), data)
    write_snapshot(key, data)
    return data


def qty_from_entry(
    entry: float,
    *,
    margin_usd: float | None = None,
    leverage: int | None = None,
) -> float:
    if entry <= 0:
        return 0.0
    m = MARGIN_USD if margin_usd is None else float(margin_usd)
    lev = LEVERAGE if leverage is None else int(leverage)
    return round((m * lev) / entry, 6)


def futures_pnl(side: str, entry: float, exit_px: float, qty: float) -> float:
    if side == "LONG":
        return round((exit_px - entry) * qty, 4)
    return round((entry - exit_px) * qty, 4)


def slot_label(dt: datetime | None = None) -> str:
    d = dt or now_tr()
    return f"{d.strftime('%Y-%m-%d')} {d.hour:02d}:00"


def _virtual_upnl_net(pos: dict, mark: float) -> tuple[float, float, float]:
    """(gross, net, commission)."""
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("qty") or qty_from_entry(entry))
    side = pos.get("side") or "LONG"
    pnl_gross = futures_pnl(side, entry, mark, qty)
    entry_notional = float(pos.get("notional") or (entry * qty))
    exit_notional = mark * qty
    rate = real_taker_rate(pos.get("symbol") or "BTCUSDT")
    entry_fee = float(pos.get("entry_fee") or 0)
    if entry_fee <= 0:
        entry_fee = estimate_fee(entry_notional, rate)
    exit_fee = estimate_fee(exit_notional, rate)
    commission = round(entry_fee + exit_fee, 6)
    return pnl_gross, net_pnl(pnl_gross, commission), commission


def _settle_close(
    state: dict,
    history: list,
    pos: dict,
    *,
    exit_px: float,
    label: str,
    reason: str,
) -> float:
    """Tek pozisyon kapat; net pnl döner."""
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("qty") or qty_from_entry(entry))
    side = pos.get("side") or "LONG"
    pnl_gross = futures_pnl(side, entry, exit_px, qty)
    entry_notional = float(pos.get("notional") or (entry * qty))
    exit_notional = exit_px * qty
    rate = real_taker_rate(pos.get("symbol") or "BTCUSDT")
    entry_fee = float(pos.get("entry_fee") or 0)
    if entry_fee <= 0:
        entry_fee = estimate_fee(entry_notional, rate)
    exit_fee = estimate_fee(exit_notional, rate)
    commission = round(entry_fee + exit_fee, 6)
    pnl = net_pnl(pnl_gross, commission)
    state["balance"] = round(float(state["balance"]) + pnl, 2)
    state["total_pnl"] = round(float(state.get("total_pnl") or 0) + pnl, 4)
    state["total_commission"] = round(
        float(state.get("total_commission") or 0) + commission, 6
    )
    history.append({
        **pos,
        "exit_price": exit_px,
        "exit_time_tr": now_tr_iso(),
        "pnl_gross": pnl_gross,
        "entry_fee": entry_fee,
        "exit_fee": exit_fee,
        "commission": commission,
        "pnl": pnl,
        "win": pnl >= 0,
        "close_reason": reason,
        "book": label,
    })
    print(
        f"[{label}] close {pos.get('symbol')} {side} {entry}→{exit_px} "
        f"gross={pnl_gross:+.2f} fee={commission:.4f} net={pnl:+.2f} ({reason})"
    )
    return pnl


def close_all_positions(
    state_path: str,
    history_path: str,
    *,
    label: str,
    kl_cache: dict[str, list] | None = None,
) -> dict:
    with book_lock(state_path):
        return _close_all_positions_locked(
            state_path, history_path, label=label, kl_cache=kl_cache,
        )


def _close_all_positions_locked(
    state_path: str,
    history_path: str,
    *,
    label: str,
    kl_cache: dict[str, list] | None = None,
) -> dict:
    """Açık sanal pozisyonları 1h mum kapanışına göre kapat.

    ATR runner (kâr + stop_level>=1) saatlik close'ta hold edilir.
    """
    state = load_state(state_path)
    history = load_history(history_path)
    opens = list(state.get("open_positions") or [])
    if not opens:
        return {"ok": True, "closed": 0, "held": 0, "pnl": 0.0, "balance": state["balance"]}

    cache = kl_cache or {}
    closed = 0
    held = 0
    tur_pnl = 0.0
    closed_atr_syms: list[str] = []
    remaining = []
    for pos in opens:
        sym = pos.get("symbol") or ""
        iv = _pos_interval(pos)
        if not _can_settle_interval(iv):
            remaining.append(pos)
            held += 1
            continue
        kl = cache.get(f"{sym}|{iv}")
        if kl is None:
            try:
                kl = fetch_klines(sym, iv, 80)
                cache[f"{sym}|{iv}"] = kl
            except Exception:
                remaining.append(pos)
                continue
        if len(kl) < 2:
            remaining.append(pos)
            continue
        # Bir önceki tamamlanmış mum kapanışı (settle)
        exit_px = float(kl[-2]["c"])
        if not float(pos.get("atr_usd") or 0):
            pos = init_lock_fields(
                pos,
                atr=atr_from_klines(kl),
                price=float(pos.get("entry_price") or exit_px),
            )
        _g, upnl_net, _c = _virtual_upnl_net(pos, exit_px)
        ts_now = now_tr_iso()
        pos2, _ch = update_lock(pos, upnl_net, ts=ts_now, mark=exit_px)
        if should_skip_hourly_close(pos2, upnl_net):
            remaining.append(pos2)
            held += 1
            print(
                f"[{label}] HOLD {sym} runner stop{pos2.get('stop_level')} "
                f"uPnL={upnl_net:+.2f}"
            )
            continue
        tur_pnl += _settle_close(
            state, history, pos2, exit_px=exit_px, label=label,
            reason=f"{iv}_close",
        )
        closed += 1
        if int(pos2.get("stop_level") or 0) >= 1 and sym:
            closed_atr_syms.append(sym.upper())

    state["open_positions"] = remaining
    save_state(state_path, state)
    save_history(history_path, history)
    return {
        "ok": True,
        "closed": closed,
        "held": held,
        "pnl": round(tur_pnl, 4),
        "balance": state["balance"],
        "total_pnl": state["total_pnl"],
        "total_commission": state.get("total_commission", 0),
        "closed_atr_syms": closed_atr_syms,
    }


def trail_positions(
    state_path: str,
    history_path: str,
    *,
    label: str,
    kl_cache: dict[str, list] | None = None,
) -> dict:
    with book_lock(state_path):
        return _trail_positions_locked(
            state_path, history_path, label=label, kl_cache=kl_cache,
        )


def _trail_positions_locked(
    state_path: str,
    history_path: str,
    *,
    label: str,
    kl_cache: dict[str, list] | None = None,
) -> dict:
    """ATR peak/stop güncelle; stop vurulursa mark ile kapat."""
    state = load_state(state_path)
    history = load_history(history_path)
    opens = list(state.get("open_positions") or [])
    if not opens:
        return {"ok": True, "closed": 0, "updated": 0, "balance": state["balance"]}

    cache = kl_cache or {}
    closed = 0
    updated = 0
    tur_pnl = 0.0
    closed_symbols: list[str] = []
    remaining = []
    for pos in opens:
        sym = pos.get("symbol") or ""
        iv = _pos_interval(pos)
        kl = cache.get(f"{sym}|{iv}")
        if kl is None:
            try:
                kl = fetch_klines(sym, iv, 80)
                cache[f"{sym}|{iv}"] = kl
            except Exception as e:
                print(f"[{label}] trail kline {sym} {iv}: {e}")
                remaining.append(pos)
                continue
        if not kl:
            remaining.append(pos)
            continue
        mark = float(kl[-1]["c"])
        if not float(pos.get("atr_usd") or 0):
            pos = init_lock_fields(
                pos,
                atr=atr_from_klines(kl),
                price=float(pos.get("entry_price") or mark),
            )
        _g, upnl_net, _c = _virtual_upnl_net(pos, mark)
        ts_now = now_tr_iso()
        pos2, ch = update_lock(pos, upnl_net, ts=ts_now, mark=mark)
        if ch:
            updated += 1
            print(
                f"[{label}] trail {sym} stop{pos2.get('stop_level')} "
                f"peak={pos2.get('peak_upnl')} lock={pos2.get('stop_upnl')} "
                f"uPnL={upnl_net:+.2f}"
            )
        age_min = position_age_minutes(pos2)
        if should_loss_stop(pos2, upnl_net) and age_min >= LOSS_STOP_MIN_AGE_MIN:
            tur_pnl += _settle_close(
                state, history, pos2, exit_px=mark, label=label, reason="atr_loss",
            )
            closed += 1
            if sym:
                closed_symbols.append(sym.upper())
            print(
                f"[{label}] ATR LOSS {sym} uPnL={upnl_net:+.2f} "
                f"limit={loss_stop_threshold(pos2):+.2f} age={age_min:.1f}dk"
            )
        elif should_stop_out(pos2, upnl_net):
            tur_pnl += _settle_close(
                state, history, pos2, exit_px=mark, label=label, reason="atr_stop",
            )
            closed += 1
            if sym:
                closed_symbols.append(sym.upper())
        else:
            remaining.append(pos2)

    state["open_positions"] = remaining
    save_state(state_path, state)
    save_history(history_path, history)
    return {
        "ok": True,
        "closed": closed,
        "updated": updated,
        "pnl": round(tur_pnl, 4),
        "balance": state["balance"],
        "closed_symbols": closed_symbols,
    }


def position_age_minutes(pos: dict, *, now: datetime | None = None) -> float:
    """Pozisyon açılalı kaç dakika geçti — flip-flop koruması için."""
    ts = pos.get("entry_time_tr")
    if not ts:
        return 0.0
    try:
        opened = datetime.fromisoformat(str(ts))
    except Exception:
        return 0.0
    ref = now or now_tr()
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=_TZ)
    return max(0.0, (ref - opened).total_seconds() / 60.0)


def close_reversal_positions(
    state_path: str,
    history_path: str,
    *,
    label: str,
    reversed_symbols: set[str],
    kl_cache: dict[str, list] | None = None,
    reason: str = "signal_reversal",
) -> dict:
    if not reversed_symbols:
        return {"ok": True, "closed": 0, "closed_symbols": []}
    with book_lock(state_path):
        return _close_reversal_positions_locked(
            state_path, history_path, label=label,
            reversed_symbols=reversed_symbols, kl_cache=kl_cache, reason=reason,
        )


def _close_reversal_positions_locked(
    state_path: str,
    history_path: str,
    *,
    label: str,
    reversed_symbols: set[str],
    kl_cache: dict[str, list] | None = None,
    reason: str = "signal_reversal",
) -> dict:
    """Verilen sembolleri ATR beklemeden anlık fiyattan kapat.

    reversed_symbols: bu turda genuine ters sinyal + min bekleme süresi
    dolan sembollerin seti (üst katman — engine.py — belirler).
    reason: kapanış etiketi — PRO defterlerinde süre sınırı için "max_hold".
    """
    state = load_state(state_path)
    history = load_history(history_path)
    opens = list(state.get("open_positions") or [])
    if not opens:
        return {"ok": True, "closed": 0, "closed_symbols": []}

    cache = kl_cache or {}
    closed = 0
    tur_pnl = 0.0
    closed_symbols: list[str] = []
    remaining = []
    for pos in opens:
        sym = (pos.get("symbol") or "").upper()
        if sym not in reversed_symbols:
            remaining.append(pos)
            continue
        iv = _pos_interval(pos)
        kl = cache.get(f"{sym}|{iv}") or cache.get(sym)
        if not kl:
            try:
                kl = fetch_klines(sym, iv, 2)
            except Exception:
                remaining.append(pos)
                continue
        if not kl:
            remaining.append(pos)
            continue
        mark = float(kl[-1]["c"])
        tur_pnl += _settle_close(
            state, history, pos, exit_px=mark, label=label, reason=reason,
        )
        closed += 1
        closed_symbols.append(sym)

    state["open_positions"] = remaining
    save_state(state_path, state)
    save_history(history_path, history)
    return {
        "ok": True,
        "closed": closed,
        "pnl": round(tur_pnl, 4),
        "balance": state["balance"],
        "closed_symbols": closed_symbols,
    }


def open_signals(
    state_path: str,
    history_path: str,
    *,
    label: str,
    candidates: list[dict],
    kl_cache: dict[str, list] | None = None,
    margin_usd: float | None = None,
    leverage: int | None = None,
    max_opens: int | None = None,
    blocked_syms: set[str] | None = None,
    entry_price_mode: str = "closed",
    bypass_slot_gate: bool = False,
) -> dict:
    with book_lock(state_path):
        return _open_signals_locked(
            state_path, history_path, label=label, candidates=candidates,
            kl_cache=kl_cache, margin_usd=margin_usd, leverage=leverage,
            max_opens=max_opens, blocked_syms=blocked_syms,
            entry_price_mode=entry_price_mode, bypass_slot_gate=bypass_slot_gate,
        )


def _open_signals_locked(
    state_path: str,
    history_path: str,
    *,
    label: str,
    candidates: list[dict],
    kl_cache: dict[str, list] | None = None,
    margin_usd: float | None = None,
    leverage: int | None = None,
    max_opens: int | None = None,
    blocked_syms: set[str] | None = None,
    entry_price_mode: str = "closed",
    bypass_slot_gate: bool = False,
) -> dict:
    """candidates: [{symbol, side LONG|SHORT, signal, algo?, score?}, ...]

    Entry = son kapanmış mum close (varsayılan) veya entry_price_mode="live"
    ile son (henüz oluşan) mumun anlık fiyatı — sinyal formülü değişmez,
    sadece emrin hangi fiyattan girdiği değişir.
    ATR runner açıkken de yeni saatte boş kota kadar ek open yapılır
    (aynı sembol tekrarlanmaz; toplam ≤ max_opens).
    margin/leverage/max_opens verilmezse global varsayılan ($15×15x / max 6).
    bypass_slot_gate=True: saatlik "tek seferlik" kilidini atlar — sık
    aralıklı "boş slot doldur" taramaları için (Kripto Test scan).
    """
    m = MARGIN_USD if margin_usd is None else float(margin_usd)
    lev = LEVERAGE if leverage is None else int(leverage)
    max_n = MAX_OPENS_PER_HOUR if max_opens is None else int(max_opens)
    notional = m * lev

    state = load_state(state_path)
    existing = list(state.get("open_positions") or [])
    held_syms = {
        str(p.get("symbol") or "").upper()
        for p in existing
        if p.get("symbol")
    }
    extra_block = {str(s).upper() for s in (blocked_syms or set()) if s}

    slot = slot_label()
    if not bypass_slot_gate:
        # Bu saat için open zaten koştuysa tekrar ekleme
        if state.get("last_open_slot") == slot:
            return {
                "ok": False,
                "skipped": "same_slot",
                "open": len(existing),
                "balance": state["balance"],
            }

    slots_left = max(0, max_n - len(existing))
    if slots_left <= 0:
        return {
            "ok": False,
            "skipped": "max_open",
            "open": len(existing),
            "max_opens": max_n,
            "balance": state["balance"],
        }

    cache = kl_cache or {}
    opened = []
    for cand in candidates:
        if len(opened) >= slots_left:
            break
        sym = (cand.get("symbol") or "").upper()
        side = cand.get("side")
        if not sym or side not in ("LONG", "SHORT"):
            continue
        if sym in held_syms or sym in extra_block:
            continue  # ATR runner / cooldown / mevcut açık
        iv = str(cand.get("interval") or "1h")
        kl = cache.get(f"{sym}|{iv}")
        if not kl:
            try:
                kl = fetch_klines(sym, iv, 3)
                cache[f"{sym}|{iv}"] = kl
            except Exception as e:
                print(f"[{label}] entry {sym} {iv}: {e}")
                continue
        if len(kl) < 2:
            continue
        entry = float(kl[-1]["c"]) if entry_price_mode == "live" else float(kl[-2]["c"])
        # Aday kendi marjını verebilir (kenar kapısı kademesi) — yoksa defter marjı
        m_c = float(cand.get("margin_usd") or m)
        notional_c = m_c * lev
        qty = qty_from_entry(entry, margin_usd=m_c, leverage=lev)
        if qty <= 0:
            continue
        rate = real_taker_rate(sym)
        entry_fee = estimate_fee(notional_c, rate)
        kl_atr = kl if len(kl) >= 30 else cache.get(f"{sym}|{iv}")
        if not kl_atr or len(kl_atr) < 30:
            try:
                kl_atr = fetch_klines(sym, iv, 80)
                cache[f"{sym}|{iv}"] = kl_atr
            except Exception:
                kl_atr = kl
        pos = init_lock_fields(
            {
                "symbol": sym,
                "side": side,
                "signal": cand.get("signal") or ("UP" if side == "LONG" else "DOWN"),
                "algo": cand.get("algo") or label,
                "score": cand.get("score"),
                "interval": iv,
                "qty": qty,
                "leverage": lev,
                "margin_usd": m_c,
                "entry_price": entry,
                "notional": notional_c,
                "entry_fee": entry_fee,
                "entry_time_tr": now_tr_iso(),
                "slot": slot,
                "virtual": True,
                **{k: cand[k] for k in _CAND_CARRY if cand.get(k) is not None},
            },
            atr=atr_from_klines(kl_atr or []),
            price=entry,
        )
        opened.append(pos)
        held_syms.add(sym)
        print(
            f"[{label}] open {sym} {side} @{entry} qty={qty} {iv} "
            f"margin=${m_c}x{lev} fee≈${entry_fee:.4f} "
            f"(held={len(existing)} +new={len(opened)}/{slots_left})"
        )

    if not opened:
        return {
            "ok": True,
            "opened": 0,
            "positions": [],
            "held": len(existing),
            "balance": state["balance"],
            "skipped": "no_candidates" if candidates else "empty",
        }

    state["open_positions"] = existing + opened
    if not bypass_slot_gate:
        state["last_open_slot"] = slot
    save_state(state_path, state)
    return {
        "ok": True,
        "opened": len(opened),
        "positions": opened,
        "held": len(existing),
        "open": len(existing) + len(opened),
        "balance": state["balance"],
    }


def format_closed_trade(t: dict) -> dict:
    """Kapanmış sanal futures işlemini dashboard geçmiş satırına çevirir."""
    side = (t.get("side") or "LONG").upper()
    sym = t.get("symbol") or ""
    return {
        "symbol": sym,
        "name": sym.replace("USDT", ""),
        "side": side,
        "dir_tr": "YÜKSELİR" if side == "LONG" else "DÜŞER",
        "interval": t.get("interval") or "1h",
        "entry_price": t.get("entry_price"),
        "exit_price": t.get("exit_price"),
        "entry_time_tr": t.get("entry_time_tr") or "",
        "exit_time_tr": t.get("exit_time_tr") or "",
        "pnl": round(float(t.get("pnl") or 0), 4),
        "pnl_gross": round(float(t.get("pnl_gross") or t.get("pnl") or 0), 4),
        "commission": round(float(t.get("commission") or 0), 6),
        "win": bool(t.get("win")),
        "close_reason": t.get("close_reason") or "",
        "slot": t.get("slot") or "",
        "margin_usd": t.get("margin_usd"),
        "leverage": t.get("leverage"),
    }


def book_status(
    state_path: str,
    history_path: str,
    *,
    label: str,
    kl_cache: dict | None = None,
    live_marks: bool = True,
    recent_limit: int = 0,
) -> dict:
    state = load_state(state_path)
    history = load_history(history_path)
    opens = list(state.get("open_positions") or [])
    cache = kl_cache if kl_cache is not None else {}
    cards = []
    upnl = 0.0
    upnl_gross = 0.0
    open_commission = 0.0
    for pos in opens:
        sym = pos.get("symbol") or ""
        entry = float(pos.get("entry_price") or 0)
        qty = float(pos.get("qty") or 0)
        side = pos.get("side") or "LONG"
        mark = entry
        if live_marks:
            iv = _pos_interval(pos)
            kl = cache.get(f"{sym}|{iv}")
            if kl is None and sym:
                try:
                    kl = fetch_klines(sym, iv, 2)
                    cache[f"{sym}|{iv}"] = kl
                except Exception:
                    kl = []
            if kl:
                mark = float(kl[-1]["c"])
        gross = futures_pnl(side, entry, mark, qty)
        entry_notional = float(pos.get("notional") or (entry * qty))
        exit_notional = mark * qty
        rate = real_taker_rate(sym)
        entry_fee = float(pos.get("entry_fee") or 0)
        if entry_fee <= 0:
            entry_fee = estimate_fee(entry_notional, rate)
        exit_fee = estimate_fee(exit_notional, rate)
        commission = round(entry_fee + exit_fee, 6)
        pnl = net_pnl(gross, commission)
        upnl += pnl
        upnl_gross += gross
        open_commission += commission
        pos_view, _ = update_lock(dict(pos), pnl, ts=now_tr_iso(), mark=mark)
        ls = lock_summary(pos_view)
        margin = float(pos.get("margin_usd") or MARGIN_USD)
        cards.append({
            **pos_view,
            "name": sym.replace("USDT", ""),
            "current": mark,
            "unrealized_pnl_gross": gross,
            "unrealized_pnl": pnl,
            "commission_est": commission,
            "entry_fee": entry_fee,
            "exit_fee_est": exit_fee,
            "close_val": round(margin + pnl, 4),
            "close_pnl": pnl,
            "dir_tr": "YÜKSELİR" if side == "LONG" else "DÜŞER",
            **ls,
        })
    wins = sum(1 for t in history if t.get("win"))
    n = len(history)
    hist_commission = round(
        sum(float(t.get("commission") or 0) for t in history), 6
    )
    out = {
        "label": label,
        "balance": state.get("balance"),
        "deposit": state.get("deposit", DEPOSIT),
        "total_pnl": state.get("total_pnl", 0.0),
        "total_commission": state.get("total_commission", hist_commission),
        "open_count": len(opens),
        "unrealized_pnl_gross": round(upnl_gross, 4),
        "unrealized_pnl": round(upnl, 4),
        "open_commission_est": round(open_commission, 4),
        "equity": round(float(state.get("balance") or 0) + upnl, 2),
        "taker_fee_rate": TAKER_FEE_RATE,
        "history_n": n,
        "wins": wins,
        "wr": round(wins / n * 100, 1) if n else None,
        "cards": cards,
        "margin_usd": MARGIN_USD,
        "leverage": LEVERAGE,
        "max_opens": MAX_OPENS_PER_HOUR,
        "updated_at_tr": state.get("updated_at_tr"),
    }
    if recent_limit > 0 and history:
        lim = min(int(recent_limit), n)
        out["recent_history"] = [
            format_closed_trade(t) for t in reversed(history[-lim:])
        ]
    return out
