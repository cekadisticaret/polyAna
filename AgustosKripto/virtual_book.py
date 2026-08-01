#!/usr/bin/env python3
"""Sanal Binance Futures defteri — $300 / $15×15x / saatlik max 6 işlem.

Poly koduna dokunmaz. AgustosKripto Algoritmalar + Analizler runner'ları kullanır.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

from atr_profit_lock import (
    atr_from_klines,
    init_lock_fields,
    lock_summary,
    should_skip_hourly_close,
    should_stop_out,
    update_lock,
)
from fee_utils import DEFAULT_TAKER_FEE, estimate_fee, net_pnl

_TZ = ZoneInfo("Europe/Istanbul")
# Sanal defter — Binance USDT-M taker varsayılanı
TAKER_FEE_RATE = float(os.environ.get("VIRTUAL_TAKER_FEE", DEFAULT_TAKER_FEE))

# Kısa TTL — dashboard poll her seferinde Binance'e gitmesin
_KLINE_CACHE: dict[str, tuple[float, list]] = {}
_KLINE_TTL_SEC = 30.0
_STATUS_CACHE: dict[str, tuple[float, dict]] = {}
_STATUS_TTL_SEC = 30.0
_SNAP_DIR = "/tmp/agustos_snap"
_SNAP_MAX_AGE_SEC = 60.0


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


def fetch_all_klines(symbols: list[str] | None = None, limit: int = 80) -> dict[str, list]:
    """Paralel + TTL cache — dashboard yavaşlığının ana çözümü."""
    syms = list(symbols or SYMBOLS)
    out: dict[str, list] = {}
    need: list[str] = []
    now = time.time()
    for sym in syms:
        ck = f"{sym}|1h|{limit}"
        hit = _KLINE_CACHE.get(ck)
        if hit and (now - hit[0]) < _KLINE_TTL_SEC:
            out[sym] = hit[1]
        else:
            need.append(sym)
    if need:
        def _one(sym: str):
            try:
                return sym, fetch_klines(sym, "1h", limit, use_cache=True)
            except Exception as e:
                print(f"[virtual_book] kline {sym}: {e}")
                return sym, []
        with ThreadPoolExecutor(max_workers=min(8, len(need))) as pool:
            futs = [pool.submit(_one, s) for s in need]
            for fut in as_completed(futs):
                sym, kl = fut.result()
                out[sym] = kl
    return out


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
    entry_fee = float(pos.get("entry_fee") or 0)
    if entry_fee <= 0:
        entry_fee = estimate_fee(entry_notional, TAKER_FEE_RATE)
    exit_fee = estimate_fee(exit_notional, TAKER_FEE_RATE)
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
    entry_fee = float(pos.get("entry_fee") or 0)
    if entry_fee <= 0:
        entry_fee = estimate_fee(entry_notional, TAKER_FEE_RATE)
    exit_fee = estimate_fee(exit_notional, TAKER_FEE_RATE)
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
    remaining = []
    for pos in opens:
        sym = pos.get("symbol") or ""
        kl = cache.get(sym)
        if kl is None:
            try:
                kl = fetch_klines(sym, "1h", 80)
                cache[sym] = kl
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
        pos2, _ch = update_lock(pos, upnl_net)
        if should_skip_hourly_close(pos2, upnl_net):
            remaining.append(pos2)
            held += 1
            print(
                f"[{label}] HOLD {sym} runner stop{pos2.get('stop_level')} "
                f"uPnL={upnl_net:+.2f}"
            )
            continue
        tur_pnl += _settle_close(
            state, history, pos2, exit_px=exit_px, label=label, reason="hourly",
        )
        closed += 1

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
    }


def trail_positions(
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
    remaining = []
    for pos in opens:
        sym = pos.get("symbol") or ""
        kl = cache.get(sym)
        if kl is None:
            try:
                kl = fetch_klines(sym, "1h", 80)
                cache[sym] = kl
            except Exception as e:
                print(f"[{label}] trail kline {sym}: {e}")
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
        pos2, ch = update_lock(pos, upnl_net)
        if ch:
            updated += 1
            print(
                f"[{label}] trail {sym} stop{pos2.get('stop_level')} "
                f"peak={pos2.get('peak_upnl')} lock={pos2.get('stop_upnl')} "
                f"uPnL={upnl_net:+.2f}"
            )
        if should_stop_out(pos2, upnl_net):
            tur_pnl += _settle_close(
                state, history, pos2, exit_px=mark, label=label, reason="atr_stop",
            )
            closed += 1
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
) -> dict:
    """candidates: [{symbol, side LONG|SHORT, signal, algo?, score?}, ...]

    Entry = son kapanmış 1h mum close (slot açılışı).
    margin/leverage/max_opens verilmezse global varsayılan ($15×15x / max 6).
    """
    m = MARGIN_USD if margin_usd is None else float(margin_usd)
    lev = LEVERAGE if leverage is None else int(leverage)
    max_n = MAX_OPENS_PER_HOUR if max_opens is None else int(max_opens)
    notional = m * lev

    state = load_state(state_path)
    if state.get("open_positions"):
        return {
            "ok": False,
            "skipped": "already_open",
            "open": len(state["open_positions"]),
            "balance": state["balance"],
        }

    slot = slot_label()
    if state.get("last_open_slot") == slot and state.get("open_positions"):
        return {"ok": False, "skipped": "same_slot", "balance": state["balance"]}

    cache = kl_cache or {}
    opened = []
    for cand in candidates[:max_n]:
        sym = (cand.get("symbol") or "").upper()
        side = cand.get("side")
        if side not in ("LONG", "SHORT"):
            continue
        kl = cache.get(sym)
        if not kl:
            try:
                kl = fetch_klines(sym, "1h", 3)
                cache[sym] = kl
            except Exception as e:
                print(f"[{label}] entry {sym}: {e}")
                continue
        if len(kl) < 2:
            continue
        entry = float(kl[-2]["c"])
        qty = qty_from_entry(entry, margin_usd=m, leverage=lev)
        if qty <= 0:
            continue
        entry_fee = estimate_fee(notional, TAKER_FEE_RATE)
        # ATR için yeterli bar — cache'te 80 yoksa çek
        kl_atr = kl if len(kl) >= 30 else cache.get(sym)
        if not kl_atr or len(kl_atr) < 30:
            try:
                kl_atr = fetch_klines(sym, "1h", 80)
                cache[sym] = kl_atr
            except Exception:
                kl_atr = kl
        pos = init_lock_fields(
            {
                "symbol": sym,
                "side": side,
                "signal": cand.get("signal") or ("UP" if side == "LONG" else "DOWN"),
                "algo": cand.get("algo") or label,
                "score": cand.get("score"),
                "qty": qty,
                "leverage": lev,
                "margin_usd": m,
                "entry_price": entry,
                "notional": notional,
                "entry_fee": entry_fee,
                "entry_time_tr": now_tr_iso(),
                "slot": slot,
                "virtual": True,
            },
            atr=atr_from_klines(kl_atr or []),
            price=entry,
        )
        opened.append(pos)
        print(
            f"[{label}] open {sym} {side} @{entry} qty={qty} "
            f"margin=${m}x{lev} fee≈${entry_fee:.4f}"
        )

    state["open_positions"] = opened
    state["last_open_slot"] = slot
    save_state(state_path, state)
    return {
        "ok": True,
        "opened": len(opened),
        "positions": opened,
        "balance": state["balance"],
    }


def book_status(
    state_path: str,
    history_path: str,
    *,
    label: str,
    kl_cache: dict | None = None,
    live_marks: bool = True,
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
            kl = cache.get(sym)
            if kl is None and sym:
                try:
                    kl = fetch_klines(sym, "1h", 2)
                    cache[sym] = kl
                except Exception:
                    kl = []
            if kl:
                mark = float(kl[-1]["c"])
        gross = futures_pnl(side, entry, mark, qty)
        entry_notional = float(pos.get("notional") or (entry * qty))
        exit_notional = mark * qty
        entry_fee = float(pos.get("entry_fee") or 0)
        if entry_fee <= 0:
            entry_fee = estimate_fee(entry_notional, TAKER_FEE_RATE)
        exit_fee = estimate_fee(exit_notional, TAKER_FEE_RATE)
        commission = round(entry_fee + exit_fee, 6)
        pnl = net_pnl(gross, commission)
        upnl += pnl
        upnl_gross += gross
        open_commission += commission
        pos_view, _ = update_lock(dict(pos), pnl)
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
    return {
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
