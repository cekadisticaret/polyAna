#!/usr/bin/env python3
"""CEBU Live — Test `/kripto/test/cebu` sanal defterin Binance aynası.

Sinyal çözmez. Sanal state'te ne açıksa aynı coin/yön açılır, sanal kapanınca
canlı da kapanır. Isolated $7×20x.

A1#39 Live / CR6 dokunulmaz. Manuel open yok — cron sanal turundan sonra.

  python3 AgustosKripto/crypto_futures_b1_mum.py close|open|trail|scan|status
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)
_TEST = os.path.join(_DIR, "Test")
sys.path.insert(0, _DIR)

_ENV_FILE = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from crypto_futures_trader import (  # noqa: E402
    close_market,
    estimate_qty,
    get_positions,
    load_config,
    open_market,
    usdt_balance,
    _client,
    _is_dry,
)
from fee_utils import get_taker_rate, net_pnl  # noqa: E402
from virtual_book import now_tr_iso  # noqa: E402

_TZ_TR = ZoneInfo("Europe/Istanbul")
PAPER_STATE = os.path.join(_TEST, "data", "test_cebu_state.json")
PAPER_HIST = os.path.join(_TEST, "data", "test_cebu_history.json")
STATE_FILE = os.path.join(_DIR, "crypto_futures_b1_mum_state.json")
HISTORY_FILE = os.path.join(_DIR, "crypto_futures_b1_mum_history.json")
CONTROL_FILE = os.path.join(_DIR, "crypto_futures_b1_mum_control.json")
USDT_CACHE_FILE = os.path.join(_DIR, "crypto_futures_b1_mum_usdt.json")
MARK_CACHE_FILE = os.path.join(_DIR, "crypto_futures_b1_mum_marks.json")
LABEL = "CEBU Live"
ALGO_NAME = "CEBU · sabit coin→motor"
MARGIN_USD = 7.0
LEVERAGE = 20
STATE_LOCK_WAIT_SEC = 90.0


def _env_enabled() -> bool:
    return os.getenv("CRYPTO_FUTURES_B1_MUM_ENABLED", "true").lower() in ("1", "true", "yes")


def get_live_control() -> dict:
    data = {
        "live_paused": False,
        "updated_at_tr": None,
        "updated_by": None,
        "reason": "Test cebu ayna · $7×20x",
    }
    if os.path.exists(CONTROL_FILE):
        try:
            with open(CONTROL_FILE) as f:
                raw = json.load(f) or {}
            if isinstance(raw, dict):
                data.update(raw)
        except Exception:
            pass
    data["live_paused"] = bool(data.get("live_paused"))
    return data


def is_live_paused() -> bool:
    return bool(get_live_control().get("live_paused"))


def save_live_control(data: dict, *, source: str = "dashboard") -> dict:
    out = get_live_control()
    out.update(data or {})
    out["live_paused"] = bool(out.get("live_paused"))
    out["updated_at_tr"] = datetime.now(_TZ_TR).isoformat()
    out["updated_by"] = source
    tmp = CONTROL_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONTROL_FILE)
    return out


def set_live_paused(paused: bool, *, source: str = "dashboard") -> dict:
    return save_live_control({"live_paused": bool(paused)}, source=source)


def toggle_live_paused(*, source: str = "dashboard") -> dict:
    return set_live_paused(not is_live_paused(), source=source)


def _opens_allowed() -> bool:
    return _env_enabled() and not is_live_paused()


def _atomic_write_json(path: str, data) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class StateLockBusy(RuntimeError):
    pass


@contextlib.contextmanager
def state_lock(wait_sec: float | None = None):
    limit = STATE_LOCK_WAIT_SEC if wait_sec is None else float(wait_sec)
    lock_path = STATE_FILE + ".lock"
    fh = open(lock_path, "w")
    deadline = time.monotonic() + limit
    got = False
    try:
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                got = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise StateLockBusy(f"state kilidi {limit:.0f}s içinde alınamadı") from None
                time.sleep(0.5)
        yield
    finally:
        if got:
            with contextlib.suppress(Exception):
                fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"open_positions": [], "total_pnl": 0.0, "total_commission": 0.0}
    try:
        with open(STATE_FILE) as f:
            st = json.load(f)
        if not isinstance(st, dict):
            return {"open_positions": [], "total_pnl": 0.0, "total_commission": 0.0}
        st.setdefault("open_positions", [])
        st.setdefault("total_pnl", 0.0)
        st.setdefault("total_commission", 0.0)
        st.setdefault("bn_flat_slots", {})
        return st
    except Exception:
        return {"open_positions": [], "total_pnl": 0.0, "total_commission": 0.0}


def save_state(st: dict) -> None:
    st["updated_at_tr"] = now_tr_iso()
    _atomic_write_json(STATE_FILE, st)


def load_history() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE) as f:
            rows = json.load(f)
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def save_history(rows: list) -> None:
    _atomic_write_json(HISTORY_FILE, rows[-800:])


def _load_json(path: str):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def paper_opens() -> dict[str, dict]:
    raw = _load_json(PAPER_STATE) or {}
    out: dict[str, dict] = {}
    for p in raw.get("open_positions") or []:
        sym = str(p.get("symbol") or "").upper()
        side = str(p.get("side") or "").upper()
        if sym and side in ("LONG", "SHORT"):
            out[sym] = p
    return out


def _paper_slot(pp: dict | None) -> str:
    if not isinstance(pp, dict):
        return ""
    return str(pp.get("slot") or pp.get("entry_time_tr") or pp.get("paper_entry_time_tr") or "")


def _refresh_usdt_from_um() -> dict | None:
    try:
        fx = os.path.join(_ROOT, "EylulForex")
        if fx not in sys.path:
            sys.path.insert(0, fx)
        from binance_um_wallet import fetch  # noqa: WPS433
        acc = fetch(force=True) or {}
        if acc.get("wallet") is None:
            return None
        usdt = {
            "asset": "USDT",
            "balance": float(acc["wallet"]),
            "available": acc.get("available"),
            "equity": acc.get("equity"),
            "unrealized": acc.get("unrealized"),
        }
        _save_usdt_cache(usdt)
        return {
            "asset": "USDT",
            "balance": float(acc["wallet"]),
            "available": float(acc["available"]) if acc.get("available") is not None else None,
            "cached": True,
            "cached_at_tr": now_tr_iso(),
        }
    except Exception:
        return None


def _account_isolated_empty() -> bool:
    try:
        fx = os.path.join(_ROOT, "EylulForex")
        if fx not in sys.path:
            sys.path.insert(0, fx)
        from binance_um_wallet import fetch  # noqa: WPS433
        acc = fetch() or {}
        w = float(acc.get("wallet") or 0)
        a = float(acc.get("available") or 0)
        u = float(acc.get("unrealized") or 0)
        return w > 0 and abs(w - a) < 0.08 and abs(u) < 0.08
    except Exception:
        return False


def _chain_positions() -> dict[str, dict] | None:
    """Sembol → borsa satırı. None = okunamadı (hayalet sayma)."""
    try:
        c = _client()
        if not c.configured():
            return None
        return {str(p.get("symbol") or "").upper(): p for p in get_positions(c)}
    except Exception:
        if _account_isolated_empty():
            return {}
        return None


def _on_chain(chain: dict[str, dict] | None, pos: dict) -> bool | None:
    if chain is None:
        return None
    row = chain.get(str(pos.get("symbol") or "").upper())
    if not row:
        return False
    return str(row.get("side") or "").upper() == str(pos.get("side") or "").upper()


def _settle_flat(pos: dict, reason: str, exit_px: float = 0.0) -> dict:
    """Emir atmadan yerel kapanış — kullanıcı Binance'te kapattı."""
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("qty") or 0)
    mark = float(exit_px or 0)
    if mark <= 0:
        pub = _public_marks([str(pos.get("symbol") or "")])
        mark = float(pub.get(str(pos.get("symbol") or "").upper()) or 0) or entry
    gross = _mark_pnl(pos, mark)
    rate = 0.0005
    try:
        rate = float(get_taker_rate(None, pos.get("symbol") or "BTCUSDT") or 0.0005)
    except Exception:
        pass
    commission = abs(entry * qty) * rate + abs(mark * qty) * rate
    pnl = net_pnl(gross, commission)
    return {
        **pos,
        "exit_price": mark,
        "exit_time_tr": now_tr_iso(),
        "pnl_gross": round(gross, 4),
        "commission": round(commission, 6),
        "pnl": round(pnl, 4),
        "close_reason": reason,
        "close_order_id": None,
        "dry_run": False,
        "bn_flat": True,
    }


def _paper_close_reason(sym: str) -> str:
    hist = _load_json(PAPER_HIST)
    if not isinstance(hist, list):
        return "paper_close"
    for t in reversed(hist):
        if str(t.get("symbol") or "").upper() == sym:
            return str(t.get("close_reason") or "paper_close")
    return "paper_close"


def _load_usdt_cache() -> dict | None:
    if not os.path.exists(USDT_CACHE_FILE):
        return None
    try:
        with open(USDT_CACHE_FILE) as f:
            data = json.load(f)
        if not isinstance(data, dict) or data.get("balance") is None:
            return None
        return {
            "asset": data.get("asset") or "USDT",
            "balance": float(data["balance"]),
            "available": float(data["available"]) if data.get("available") is not None else None,
            "cached": True,
            "cached_at_tr": data.get("cached_at_tr") or "",
        }
    except Exception:
        return None


def _save_usdt_cache(usdt: dict) -> None:
    if not usdt or usdt.get("balance") is None:
        return
    try:
        with open(USDT_CACHE_FILE, "w") as f:
            json.dump({
                "asset": usdt.get("asset") or "USDT",
                "balance": float(usdt["balance"]),
                "available": usdt.get("available"),
                "cached_at_tr": now_tr_iso(),
            }, f)
    except Exception:
        pass


def _load_mark_cache() -> dict[str, dict]:
    if not os.path.exists(MARK_CACHE_FILE):
        return {}
    try:
        with open(MARK_CACHE_FILE) as f:
            data = json.load(f)
        rows = (data or {}).get("positions") or {}
        return {str(k).upper(): v for k, v in rows.items() if isinstance(v, dict)}
    except Exception:
        return {}


def _save_mark_cache(rows: dict[str, dict]) -> None:
    if not rows:
        return
    try:
        with open(MARK_CACHE_FILE, "w") as f:
            json.dump({
                "cached_at_tr": now_tr_iso(),
                "positions": {str(k).upper(): v for k, v in rows.items()},
            }, f)
    except Exception:
        pass


_MARK_MEM: dict = {"at": 0.0, "px": {}}


def _http_json(url: str, timeout: float = 8.0):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "aiProject-b1mum/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else {}


def _public_marks(symbols: list[str]) -> dict[str, float]:
    """fapi mark; IP ban'de data-api spot (kart için yeterli)."""
    want = [str(s).upper() for s in symbols if s]
    if not want:
        return {}
    now = time.time()
    if now - float(_MARK_MEM.get("at") or 0) < 5:
        hit = {s: float(_MARK_MEM["px"][s]) for s in want if s in _MARK_MEM.get("px", {})}
        if len(hit) == len(want):
            return hit
    out: dict[str, float] = {}
    try:
        from binance_fapi_guard import get_last, get_mark
        for s in want:
            px = get_mark(s) or get_last(s)
            if px:
                out[s] = float(px)
    except Exception:
        pass
    if len(out) < len(want):
        for host in (
            "https://data-api.binance.vision/api/v3/ticker/price",
            "https://api.binance.com/api/v3/ticker/price",
        ):
            missing = [s for s in want if s not in out]
            if not missing:
                break
            try:
                if len(missing) == 1:
                    d = _http_json(f"{host}?symbol={missing[0]}")
                    rows = [d] if isinstance(d, dict) else d
                else:
                    rows = _http_json(host)
                if isinstance(rows, dict):
                    rows = [rows]
                for r in rows or []:
                    sym = str((r or {}).get("symbol") or "").upper()
                    px = float((r or {}).get("price") or 0)
                    if sym in missing and px > 0:
                        out[sym] = px
            except Exception:
                continue
    if out:
        _MARK_MEM["at"] = now
        px = dict(_MARK_MEM.get("px") or {})
        px.update(out)
        _MARK_MEM["px"] = px
    return out


def _mark_pnl(pos: dict, mark: float) -> float:
    """Binance uygulaması: (mark − giriş) × adet; kapanış komisyonu yok."""
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("qty") or 0)
    side = (pos.get("side") or "LONG").upper()
    if entry <= 0 or qty <= 0 or mark <= 0:
        return 0.0
    signed = (mark - entry) if side == "LONG" else (entry - mark)
    return round(signed * qty, 4)


def _close_one(pos: dict, reason: str, *, chain: dict | None = None) -> dict:
    if _on_chain(chain, pos) is False:
        return _settle_flat(pos, reason if reason.startswith("bn_") else "bn_flat")
    r = close_market(pos["symbol"], qty=float(pos.get("qty") or 0) or None)
    exit_px = float(r.get("mark_price") or pos.get("entry_price") or 0)
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("qty") or 0)
    side = pos.get("side") or "LONG"
    signed = (exit_px - entry) if side == "LONG" else (entry - exit_px)
    pnl_gross = signed * qty
    commission = float(r.get("commission") or 0)
    if not commission:
        try:
            rate = float(get_taker_rate(None, pos["symbol"]) or 0.0005)
        except Exception:
            rate = 0.0005
        commission = abs(entry * qty) * rate + abs(exit_px * qty) * rate
    pnl = float(r["pnl"]) if r.get("pnl") is not None else net_pnl(pnl_gross, commission)
    return {
        **pos,
        "exit_price": exit_px,
        "exit_time_tr": r.get("exit_time_tr") or now_tr_iso(),
        "pnl_gross": round(pnl_gross, 4),
        "commission": round(commission, 6),
        "pnl": round(pnl, 4),
        "close_reason": reason,
        "close_order_id": (r.get("order") or {}).get("orderId"),
        "dry_run": r.get("dry_run"),
    }


def _place(paper: dict) -> dict | None:
    sym = str(paper.get("symbol") or "").upper()
    side = str(paper.get("side") or "").upper()
    if not sym or side not in ("LONG", "SHORT"):
        return None
    est = estimate_qty(sym, MARGIN_USD, LEVERAGE)
    if not est.get("ok"):
        print(f"[{LABEL}] {sym} min lot yok — atlandı")
        return None
    r = open_market(
        sym,
        side,
        margin_usd=MARGIN_USD,
        leverage=LEVERAGE,
        margin_type="ISOLATED",
        skip_max_positions=True,
        allow_excluded=True,
        skip_allowlist=True,
    )
    if not r.get("ok"):
        print(f"[{LABEL}] {sym} giriş yok ({r.get('reason') or 'fail'})")
        return None
    entry = float(
        r.get("entry_price")
        or (r.get("order") or {}).get("avgPrice")
        or r.get("mark_price")
        or 0
    )
    return {
        "strategy": LABEL,
        "symbol": sym,
        "side": side,
        "signal": paper.get("signal") or ("UP" if side == "LONG" else "DOWN"),
        "score": paper.get("score"),
        "algo": paper.get("cebu_src_name") or paper.get("algo") or ALGO_NAME,
        "interval": paper.get("interval") or "1h",
        "qty": float(r.get("qty") or 0),
        "leverage": LEVERAGE,
        "margin_usd": MARGIN_USD,
        "entry_price": entry,
        "notional": float(r.get("notional") or 0),
        "entry_time_tr": r.get("entry_time_tr") or now_tr_iso(),
        "paper_entry_time_tr": paper.get("entry_time_tr"),
        "slot": paper.get("slot"),
        "order_id": (r.get("order") or {}).get("orderId"),
        "entry_type": "taker",
        "entry_fee": r.get("entry_fee"),
        "dry_run": r.get("dry_run"),
        "virtual": False,
        "paper_mirror": True,
    }


def _sync(*, allow_open: bool) -> dict:
    if not _env_enabled():
        return {"ok": False, "skipped": "env_disabled"}
    paper = paper_opens()
    with state_lock():
        state = load_state()
        history = load_history()
        live = list(state.get("open_positions") or [])
        closed, opened, errors = [], [], []
        skip_slots = dict(state.get("bn_flat_slots") or {})
        chain = _chain_positions()

        keep: list[dict] = []
        for pos in live:
            sym = str(pos.get("symbol") or "").upper()
            side = str(pos.get("side") or "").upper()
            want = paper.get(sym)
            on = _on_chain(chain, pos)
            if on is False:
                try:
                    rec = _settle_flat(pos, "bn_flat")
                    closed.append(rec)
                    history.append(rec)
                    state["total_pnl"] = round(float(state.get("total_pnl") or 0) + float(rec.get("pnl") or 0), 4)
                    state["total_commission"] = round(
                        float(state.get("total_commission") or 0) + float(rec.get("commission") or 0), 6,
                    )
                    slot = pos.get("slot") or _paper_slot(want)
                    if slot:
                        skip_slots[sym] = slot
                    print(f"[{LABEL}] CLOSE[bn_flat] {pos.get('side')} {sym} pnl={rec.get('pnl', 0):+.4f}")
                except Exception as e:
                    print(f"[{LABEL}] bn_flat hata {sym}: {e}")
                    errors.append({"symbol": sym, "error": str(e), "op": "bn_flat"})
                continue
            if want and str(want.get("side") or "").upper() == side:
                keep.append(pos)
                continue
            reason = _paper_close_reason(sym) if not want else "paper_flip"
            try:
                rec = _close_one(pos, reason, chain=chain)
                closed.append(rec)
                history.append(rec)
                state["total_pnl"] = round(float(state.get("total_pnl") or 0) + float(rec.get("pnl") or 0), 4)
                state["total_commission"] = round(
                    float(state.get("total_commission") or 0) + float(rec.get("commission") or 0), 6,
                )
                print(f"[{LABEL}] CLOSE[{reason}] {pos.get('side')} {sym} pnl={rec.get('pnl', 0):+.4f}")
            except Exception as e:
                print(f"[{LABEL}] CLOSE hata {sym}: {e}")
                errors.append({"symbol": sym, "error": str(e), "op": "close"})
                keep.append(pos)

        for sym in list(skip_slots):
            if _paper_slot(paper.get(sym)) != skip_slots[sym]:
                skip_slots.pop(sym, None)
        state["bn_flat_slots"] = skip_slots

        held = {str(p.get("symbol") or "").upper() for p in keep}
        if allow_open and _opens_allowed():
            for sym, pp in paper.items():
                if sym in held:
                    continue
                if skip_slots.get(sym) and skip_slots.get(sym) == _paper_slot(pp):
                    print(f"[{LABEL}] {sym} atlandı — aynı slot Binance'te elle kapatıldı")
                    continue
                try:
                    pos = _place(pp)
                    if not pos:
                        errors.append({"symbol": sym, "error": "not_filled", "op": "open"})
                        continue
                    keep.append(pos)
                    held.add(sym)
                    opened.append(pos)
                    print(
                        f"[{LABEL}] OPEN {pos['side']} {sym} qty={pos['qty']} "
                        f"paper={pp.get('slot')} dry={pos.get('dry_run')}"
                    )
                except Exception as e:
                    print(f"[{LABEL}] OPEN hata {sym}: {e}")
                    errors.append({"symbol": sym, "error": str(e), "op": "open"})
        elif allow_open and not _opens_allowed():
            print(f"[{LABEL}] open kapalı (paused) · paper={len(paper)} live={len(keep)}")

        state["open_positions"] = keep
        save_state(state)
        save_history(history)
        return {
            "ok": True,
            "paper": list(paper),
            "opened": len(opened),
            "closed": len(closed),
            "held": len(keep),
            "paused": is_live_paused(),
            "errors": errors,
        }


def run_close() -> dict:
    return _sync(allow_open=False)


def run_open() -> dict:
    return _sync(allow_open=True)


def run_trail() -> dict:
    return _sync(allow_open=False)


def run_scan() -> dict:
    return _sync(allow_open=True)


def _enrich(
    pos: dict,
    chain: dict | None,
    *,
    public_mark: float = 0.0,
    refresh_price: bool = True,
) -> dict:
    live = dict(chain or {})
    entry = float(live.get("entry_price") or pos.get("entry_price") or 0)
    qty = abs(float(live.get("position_amt") or 0)) or float(pos.get("qty") or 0)
    view = {**pos, "entry_price": entry, "qty": qty}
    mark = float(live.get("mark_price") or 0) or float(public_mark or 0)
    mark_src = str(live.get("mark_src") or "")
    if not mark_src:
        if live.get("unrealized_pnl") is not None and float(live.get("mark_price") or 0) > 0:
            mark_src = "binance"
        elif mark > 0:
            mark_src = "public"
    if mark <= 0 and refresh_price:
        try:
            from binance_fapi_guard import get_last, get_mark
            mark = float(get_mark(pos["symbol"]) or get_last(pos["symbol"]) or 0)
            if mark > 0:
                mark_src = "ws"
        except Exception:
            mark = 0
    if mark <= 0:
        mark = entry
        mark_src = "entry"
        upnl = 0.0
    else:
        chain_upnl = live.get("unrealized_pnl")
        chain_mark = float(live.get("mark_price") or 0)
        if (
            chain_upnl is not None
            and chain_mark > 0
            and abs(chain_mark - mark) / max(chain_mark, 1e-9) < 0.0005
        ):
            upnl = round(float(chain_upnl), 4)
            mark_src = "binance"
        else:
            upnl = _mark_pnl(view, mark)
    iso = float(live.get("isolated_wallet") or 0) or float(pos.get("margin_usd") or MARGIN_USD)
    name = (pos.get("symbol") or "").replace("USDT", "")
    return {
        **view,
        "name": name,
        "current": mark,
        "mark_price": mark,
        "unrealized_pnl": upnl,
        "roe": round(upnl / iso * 100.0, 2) if iso else None,
        "liq_price": float(live.get("liquidation_price") or 0) or None,
        "mark_src": mark_src,
        "lock_armed": False,
        "mirror_note": "sanal CEBU ayna",
    }


def status_block(*, refresh_price: bool = True) -> dict:
    cfg = load_config()
    dry = _is_dry(cfg)
    state = load_state()
    history = load_history()
    opens = list(state.get("open_positions") or [])
    ctrl = get_live_control()
    paper = paper_opens()
    usdt = None
    chain_map = _load_mark_cache()
    live_err = None
    if refresh_price:
        try:
            c = _client(cfg)
            if c.configured():
                usdt = usdt_balance(c)
                fresh = {}
                for p in get_positions(c):
                    fresh[str(p["symbol"]).upper()] = p
                if fresh:
                    chain_map.update(fresh)
                    _save_mark_cache(chain_map)
                _save_usdt_cache(usdt)
        except Exception as e:
            live_err = str(e)
    if usdt is None:
        usdt = _refresh_usdt_from_um() or _load_usdt_cache()
    pub = _public_marks([str(p.get("symbol") or "") for p in opens])
    if pub:
        for sym, px in pub.items():
            row = dict(chain_map.get(sym) or {})
            old_mark = float(row.get("mark_price") or 0)
            row["symbol"] = sym
            row["mark_price"] = px
            row["mark_src"] = "public"
            if old_mark and abs(old_mark - px) / max(old_mark, 1e-9) > 0.0005:
                row.pop("unrealized_pnl", None)
            chain_map[sym] = row
        _save_mark_cache(chain_map)
    cards = [
        _enrich(
            p,
            chain_map.get(str(p.get("symbol") or "").upper()),
            public_mark=float(pub.get(str(p.get("symbol") or "").upper()) or 0),
            refresh_price=refresh_price and not live_err,
        )
        for p in opens
    ]
    wins = sum(1 for t in history if float(t.get("pnl") or 0) > 0)
    n = len(history)
    recent = []
    for t in list(reversed(history))[:20]:
        sym = (t.get("symbol") or "").upper()
        recent.append({
            "symbol": sym,
            "name": sym.replace("USDT", "") if sym.endswith("USDT") else sym,
            "side": t.get("side"),
            "algo": t.get("algo") or ALGO_NAME,
            "interval": t.get("interval") or "1h",
            "leverage": t.get("leverage") or LEVERAGE,
            "margin_usd": t.get("margin_usd") or MARGIN_USD,
            "entry_price": t.get("entry_price"),
            "exit_price": t.get("exit_price"),
            "pnl": round(float(t.get("pnl") or 0), 4),
            "entry_time_tr": t.get("entry_time_tr") or "",
            "exit_time_tr": t.get("exit_time_tr") or "",
            "close_reason": t.get("close_reason") or "",
        })
    return {
        "ok": True,
        "label": LABEL,
        "algo": ALGO_NAME,
        "book_uid": "cebu",
        "margin_usd": MARGIN_USD,
        "leverage": LEVERAGE,
        "live_paused": bool(ctrl.get("live_paused")),
        "live_control": ctrl,
        "env_enabled": _env_enabled(),
        "enabled": _opens_allowed(),
        "dry_run": dry,
        "error": live_err,
        "usdt": usdt,
        "open_count": len(cards),
        "cards": cards,
        "open_positions": opens,
        "paper_open": list(paper),
        "paper_count": len(paper),
        "total_pnl": round(float(state.get("total_pnl") or 0), 4),
        "total_commission": round(float(state.get("total_commission") or 0), 6),
        "trade_count": n,
        "win_rate": round(100.0 * wins / n, 1) if n else None,
        "recent_trades": recent,
        "updated_at_tr": state.get("updated_at_tr") or "",
    }


def main() -> None:
    p = argparse.ArgumentParser(description="CEBU Live — Test cebu Binance aynası")
    p.add_argument("cmd", choices=["open", "close", "trail", "scan", "status", "reconcile"])
    args = p.parse_args()
    if args.cmd == "open":
        r = run_open()
    elif args.cmd == "close":
        r = run_close()
    elif args.cmd == "trail":
        r = run_trail()
    elif args.cmd == "scan":
        r = run_scan()
    elif args.cmd == "reconcile":
        r = run_close()
    else:
        r = status_block()
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
