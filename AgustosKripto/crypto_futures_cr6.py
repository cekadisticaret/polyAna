#!/usr/bin/env python3
"""Supertrend Live — Binance Futures (eski CR6 cron/dosya yolu korunur).

Saatlik: Supertrend skor → top-4 alt (BTC/ETH yok, SOL son) → $10×15x.
ATR kâr kilidi + :02/:05 + trail */2.

CLI:
  python3 crypto_futures_cr6.py close
  python3 crypto_futures_cr6.py open
  python3 crypto_futures_cr6.py trail
  python3 crypto_futures_cr6.py status
  python3 crypto_futures_cr6.py preview
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)
sys.path.insert(0, _DIR)
sys.path.insert(0, os.path.join(_DIR, "Analizler"))
sys.path.insert(0, os.path.join(_ROOT, "temmuzPoly"))  # algo_signals

_ENV_FILE = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from algo_signals import fetch_klines as _algo_fetch_klines  # noqa: E402
from atr_profit_lock import (  # noqa: E402
    atr_from_klines,
    init_lock_fields,
    lock_summary,
    should_skip_hourly_close,
    should_stop_out,
    update_lock,
)
from cr6_tg_card import (  # noqa: E402
    render_event_card,
    render_open_card,
    tg_send_photo,
)
from fee_utils import estimate_fee, get_taker_rate, net_pnl  # noqa: E402
from crypto_futures_trader import (  # noqa: E402
    close_market,
    dust_sweep,
    estimate_qty,
    get_positions,
    load_config,
    open_market,
    usdt_balance,
    _client,
    _is_dry,
)
from signals import supertrend_scored  # noqa: E402

_TZ_TR = ZoneInfo("Europe/Istanbul")
STATE_FILE = os.path.join(_DIR, "crypto_futures_cr6_state.json")
HISTORY_FILE = os.path.join(_DIR, "crypto_futures_cr6_history.json")
LABEL = "Supertrend"
STRATEGY = "Supertrend"
ALGO_NAME = "Supertrend"
MARGIN_USD = 10.0
LEVERAGE = 15
TOP_N = 4
# Anlık net zarar ≥ teminatın bu oranı → saatlik/ATR beklemeden market kapat
HARD_SL_FRAC = 0.5  # $10 → -$5

# Sanal Supertrend (a6) ile aynı evren — BTC/ETH yok; SOL yavaş
ST_SYMBOLS = [
    "INJUSDT", "TIAUSDT", "ARBUSDT", "OPUSDT", "1000PEPEUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "LTCUSDT", "NEARUSDT", "SUIUSDT", "APTUSDT",
    "BNBUSDT", "XRPUSDT",
    "SOLUSDT",
]
ST_SLOW = frozenset({"SOLUSDT"})
TIER_MOMENTUM = [
    "INJUSDT", "TIAUSDT", "ARBUSDT", "OPUSDT", "1000PEPEUSDT",
]
TIER_ALT_VOLUME = [
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "LTCUSDT", "TRXUSDT", "SUIUSDT", "APTUSDT", "NEARUSDT",
    "BNBUSDT", "XRPUSDT",
]
TIER_MAJOR = ["SOLUSDT"]  # yalnızca yavaş doldurma
_TIER_RANK = {
    **{s: 1 for s in TIER_MOMENTUM},
    **{s: 2 for s in TIER_ALT_VOLUME},
    **{s: 3 for s in TIER_MAJOR},
}

BOT_TOKEN = os.getenv("TELEGRAM_ANALIZ4_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_ANALIZ4_CHAT_ID", os.getenv("TELEGRAM_CHAT", ""))


def _enabled() -> bool:
    return os.getenv("CRYPTO_FUTURES_CR6_ENABLED", "true").lower() in ("1", "true", "yes")


def _symbols() -> list[str]:
    """Allowlist ∩ Supertrend evreni."""
    cfg = load_config()
    allow = {s.upper() for s in (cfg.get("symbols") or [])}
    return [s for s in ST_SYMBOLS if s in allow] or list(ST_SYMBOLS)


def _tier(symbol: str) -> int:
    return int(_TIER_RANK.get(symbol.upper(), 9))


def _tier_label(symbol: str) -> str:
    t = _tier(symbol)
    if t == 1:
        return "momentum"
    if t == 2:
        return "alt-hacim"
    if t == 3:
        return "slow"
    return "other"


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"open_positions": [], "updated_at_tr": ""}


def save_state(state: dict) -> None:
    state["updated_at_tr"] = datetime.now(_TZ_TR).isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_history(history: list) -> None:
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _tg(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": "true"}
        ).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=12)
    except Exception as e:
        print(f"[{LABEL}] TG hata: {e}")


def _tg_photo(png: bytes, caption: str = "") -> None:
    if not BOT_TOKEN or not CHAT_ID or not png:
        return
    try:
        tg_send_photo(BOT_TOKEN, CHAT_ID, png, caption=caption)
    except Exception as e:
        print(f"[{LABEL}] TG photo hata: {e}")
        if caption:
            _tg(caption)


def _tg_open_card(opened: list[dict]) -> None:
    """ALGO2 tarzı sarı kart — Supertrend canlı açılış."""
    try:
        png = render_open_card(
            opened,
            margin_usd=MARGIN_USD,
            leverage=LEVERAGE,
            title="Supertrend · Futures Açılış",
            panel=f"ST Live · {len(opened)} işlem",
        )
        bits = []
        for p in opened:
            nm = (p.get("symbol") or "").replace("USDT", "")
            arrow = "▲" if p.get("side") == "LONG" else "▼"
            bits.append(f"{nm} {arrow}")
        cap = (
            f"Supertrend açılış ({len(opened)}) ${MARGIN_USD:.0f}×{LEVERAGE}x — "
            + " · ".join(bits)
        )
        _tg_photo(png, cap)
    except Exception as e:
        print(f"[{LABEL}] open card: {e}")
        lines = [f"{LABEL} açılış ({len(opened)}) ${MARGIN_USD:.0f}×{LEVERAGE}x"]
        for p in opened:
            lines.append(
                f"• {p['symbol']} {p['side']} @{p['entry_price']:.4f} "
                f"[{p.get('tier_label', '')}] skor={p['score']}"
            )
        _tg("\n".join(lines))


def _tg_event_card(title: str, hero: str, rows: list[str], footer: str = "") -> None:
    try:
        png = render_event_card(title, hero, rows, footer=footer)
        _tg_photo(png, f"{title} — {hero}")
    except Exception as e:
        print(f"[{LABEL}] event card: {e}")
        _tg(f"{title}\n{hero}\n" + "\n".join(rows))


def score_symbol(symbol: str, kl: list) -> dict:
    sig, score = supertrend_scored(kl)
    price = float(kl[-1]["c"]) if kl else None
    return {
        "symbol": symbol,
        "signal": sig,
        "score": round(float(score), 6),
        "algo": ALGO_NAME,
        "price": price,
        "slow": symbol.upper() in ST_SLOW,
    }


async def _scan_all() -> list[dict]:
    out = []
    for sym in _symbols():
        try:
            kl = await asyncio.to_thread(_algo_fetch_klines, sym, "1h", 80)
        except Exception as e:
            print(f"[{LABEL}] {sym} kline: {e}")
            continue
        if len(kl) < 30:
            continue
        out.append(score_symbol(sym, kl))
    return out


def _slot_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(_TZ_TR)
    start = now.replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    return start, end


def _pick_top(candidates: list[dict], n: int = TOP_N) -> list[dict]:
    """Supertrend: hızlı alt/momentum skor önce; SOL son; BTC/ETH yok."""
    active = [
        c for c in candidates
        if c.get("signal") in ("UP", "DOWN") and float(c.get("score") or 0) > 0
    ]
    fast = [c for c in active if not c.get("slow") and (c.get("symbol") or "") not in ST_SLOW]
    slow = [c for c in active if c.get("slow") or (c.get("symbol") or "") in ST_SLOW]
    fast.sort(key=lambda x: (-float(x.get("score") or 0), x.get("symbol") or ""))
    slow.sort(key=lambda x: (-float(x.get("score") or 0), x.get("symbol") or ""))
    picked: list[dict] = []
    for c in fast + slow:
        if len(picked) >= n:
            break
        if any(p.get("symbol") == c.get("symbol") for p in picked):
            continue
        sym = c.get("symbol") or ""
        picked.append({
            **c,
            "tier": _tier(sym),
            "tier_label": _tier_label(sym),
        })
    return picked


def run_preview() -> dict:
    rows = asyncio.run(_scan_all())
    top = _pick_top(rows)
    print(f"[{LABEL}] preview {len(rows)} coin, top={[(t['symbol'], t['signal'], t['score']) for t in top]}")
    return {"candidates": rows, "top": top}


def _live_upnl_net(pos: dict, mark: float | None = None, *, fee_rate: float | None = None) -> tuple[float, float, float]:
    """(upnl_gross, upnl_net, mark)."""
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("qty") or 0)
    side = pos.get("side") or "LONG"
    px = float(mark) if mark and mark > 0 else 0.0
    if px <= 0:
        try:
            px = _client().mark_price(pos["symbol"])
        except Exception:
            px = entry
    if side == "LONG":
        upnl_gross = (px - entry) * qty
    else:
        upnl_gross = (entry - px) * qty
    upnl_gross = round(upnl_gross, 4)
    entry_notional = float(pos.get("notional") or (entry * qty))
    exit_notional = px * qty
    entry_fee = float(pos.get("entry_fee") or 0)
    rate = fee_rate if fee_rate is not None else get_taker_rate(
        None, pos.get("symbol") or "BTCUSDT", cfg=load_config(),
    )
    if entry_fee <= 0:
        entry_fee = estimate_fee(entry_notional, rate)
    exit_fee = estimate_fee(exit_notional, rate)
    upnl_net = net_pnl(upnl_gross, entry_fee + exit_fee)
    return upnl_gross, upnl_net, px


def _close_one(pos: dict, *, reason: str) -> dict:
    sym = pos.get("symbol")
    qty = float(pos.get("qty") or 0)
    r = close_market(sym, qty=qty if qty > 0 else None)
    exit_px = float(r.get("mark_price") or pos.get("entry_price") or 0)
    entry = float(pos.get("entry_price") or 0)
    side = pos.get("side") or "LONG"
    q = float(r.get("qty") or qty)
    if r.get("pnl_gross") is not None:
        pnl_gross = float(r["pnl_gross"])
    elif side == "LONG":
        pnl_gross = (exit_px - entry) * q
    else:
        pnl_gross = (entry - exit_px) * q
    pnl_gross = round(pnl_gross, 4)
    commission = float(r.get("commission") or 0)
    entry_fee = float(r.get("entry_fee") or 0)
    exit_fee = float(r.get("exit_fee") or 0)
    if commission <= 0:
        rate = get_taker_rate(None, sym or "BTCUSDT", cfg=load_config())
        entry_notional = float(pos.get("notional") or (entry * q))
        exit_notional = exit_px * q
        if entry_fee <= 0:
            entry_fee = estimate_fee(entry_notional, rate)
        if exit_fee <= 0:
            exit_fee = estimate_fee(exit_notional, rate)
        commission = round(entry_fee + exit_fee, 6)
    pnl = float(r["pnl"]) if r.get("pnl") is not None else net_pnl(pnl_gross, commission)
    return {
        **pos,
        "exit_price": exit_px,
        "exit_time_tr": r.get("exit_time_tr"),
        "pnl_gross": pnl_gross,
        "commission": round(commission, 6),
        "entry_fee": round(entry_fee, 6),
        "exit_fee": round(exit_fee, 6),
        "pnl": round(pnl, 4),
        "close_reason": reason,
        "close_order_id": (r.get("order") or {}).get("orderId"),
        "dry_run": r.get("dry_run"),
    }


def run_close() -> dict:
    """Saatlik :02 — ATR runner (kâr + stop_level>=1) hold; diğerleri kapat."""
    state = load_state()
    opens = list(state.get("open_positions") or [])
    if not opens:
        print(f"[{LABEL}] close: açık yok")
        return {"closed": [], "ok": True, "held": []}

    history = load_history()
    closed = []
    remaining = []
    held = []
    for pos in opens:
        sym = pos.get("symbol")
        try:
            _g, upnl_net, _px = _live_upnl_net(pos)
            pos2, _ch = update_lock(pos, upnl_net)
            if should_skip_hourly_close(pos2, upnl_net):
                remaining.append(pos2)
                held.append(pos2)
                print(
                    f"[{LABEL}] HOLD {sym} runner stop{pos2.get('stop_level')} "
                    f"uPnL={upnl_net:+.2f} lock={pos2.get('stop_upnl')}"
                )
                continue
            rec = _close_one(pos2, reason="hourly")
            history.append(rec)
            closed.append(rec)
            print(
                f"[{LABEL}] CLOSE {rec.get('side')} {sym} "
                f"qty={rec.get('qty')} pnl={rec.get('pnl', 0):+.4f}"
            )
        except Exception as e:
            print(f"[{LABEL}] CLOSE hata {sym}: {e}")
            remaining.append(pos)

    save_history(history)
    state["open_positions"] = remaining
    save_state(state)

    if closed:
        rows = [
            f"{c.get('symbol')} {c.get('side')} PnL {c.get('pnl', 0):+.2f}$"
            for c in closed
        ]
        tot = sum(float(c.get("pnl") or 0) for c in closed)
        _tg_event_card(
            "Supertrend · Kapanış",
            f"{len(closed)} işlem · {tot:+.2f}$",
            rows,
            footer=f"Saatlik close · toplam {tot:+.2f}$",
        )
    if held:
        rows = [
            f"{h.get('symbol')} stop{h.get('stop_level')} "
            f"kilit≈${(float(h.get('margin_usd') or 0) + float(h.get('stop_upnl') or 0)):.2f}"
            for h in held
        ]
        _tg_event_card(
            "Supertrend · ATR Runner",
            f"{len(held)} hold · saatlik close atlandı",
            rows,
            footer="Kâr kilidi aktif — stop vurulunca kapanır",
        )
    dust = {}
    try:
        dust = dust_sweep()
    except Exception as e:
        print(f"[{LABEL}] dust_sweep: {e}")
        dust = {"error": str(e)}
    return {
        "ok": True,
        "closed": closed,
        "remaining": remaining,
        "held": held,
        "dust_sweep": dust,
    }


def hard_sl_threshold(pos: dict) -> float:
    """Net uPnL bu seviyenin altına inerse hard SL (negatif)."""
    margin = float(pos.get("margin_usd") or MARGIN_USD)
    return -abs(margin) * float(HARD_SL_FRAC)


def should_hard_sl(pos: dict, upnl_net: float) -> bool:
    return float(upnl_net) <= hard_sl_threshold(pos)


def run_trail() -> dict:
    """*/2 poll — hard SL (%50 teminat) + ATR peak/stop; vurulursa kapat."""
    state = load_state()
    opens = list(state.get("open_positions") or [])
    if not opens:
        return {"ok": True, "closed": [], "updated": 0}

    history = load_history()
    closed = []
    remaining = []
    updated = 0
    hard_closed = []
    atr_closed = []
    for pos in opens:
        sym = pos.get("symbol")
        try:
            # ATR yoksa (eski pozisyon) bir kez hesapla
            if not float(pos.get("atr_usd") or 0):
                try:
                    kl = _algo_fetch_klines(sym, "1h", 80)
                    a = atr_from_klines(kl)
                    pos = init_lock_fields(
                        pos,
                        atr=a,
                        margin_usd=float(pos.get("margin_usd") or MARGIN_USD),
                        leverage=float(pos.get("leverage") or LEVERAGE),
                        price=float(pos.get("entry_price") or 0),
                    )
                except Exception as e:
                    print(f"[{LABEL}] trail ATR {sym}: {e}")
            _g, upnl_net, _px = _live_upnl_net(pos)
            # Hard SL önce — saatlik/ATR runner beklemez
            if should_hard_sl(pos, upnl_net):
                rec = _close_one(pos, reason="hard_sl")
                history.append(rec)
                closed.append(rec)
                hard_closed.append(rec)
                print(
                    f"[{LABEL}] HARD SL {sym} uPnL={upnl_net:+.2f} "
                    f"limit={hard_sl_threshold(pos):+.2f} "
                    f"pnl={rec.get('pnl', 0):+.4f}"
                )
                continue
            pos2, ch = update_lock(pos, upnl_net)
            if ch:
                updated += 1
                print(
                    f"[{LABEL}] trail {sym} stop{pos2.get('stop_level')} "
                    f"peak={pos2.get('peak_upnl')} lock={pos2.get('stop_upnl')} "
                    f"uPnL={upnl_net:+.2f}"
                )
            if should_stop_out(pos2, upnl_net):
                rec = _close_one(pos2, reason="atr_stop")
                history.append(rec)
                closed.append(rec)
                atr_closed.append(rec)
                print(
                    f"[{LABEL}] ATR STOP {sym} lvl={pos2.get('stop_level')} "
                    f"pnl={rec.get('pnl', 0):+.4f}"
                )
            else:
                remaining.append(pos2)
        except Exception as e:
            print(f"[{LABEL}] trail hata {sym}: {e}")
            remaining.append(pos)

    save_history(history)
    state["open_positions"] = remaining
    save_state(state)

    if hard_closed:
        rows = [
            f"{c.get('symbol')} PnL {c.get('pnl', 0):+.2f}$"
            for c in hard_closed
        ]
        tot = sum(float(c.get("pnl") or 0) for c in hard_closed)
        _tg_event_card(
            "Supertrend · Hard SL",
            f"{len(hard_closed)} × −%{int(HARD_SL_FRAC * 100)} teminat · {tot:+.2f}$",
            rows,
            footer=f"Net zarar ≥ teminat×{HARD_SL_FRAC:.0%} — anında kapatıldı",
        )
    if atr_closed:
        rows = [
            f"{c.get('symbol')} stop{c.get('stop_level')} "
            f"PnL {c.get('pnl', 0):+.2f}$"
            for c in atr_closed
        ]
        tot = sum(float(c.get("pnl") or 0) for c in atr_closed)
        _tg_event_card(
            "Supertrend · ATR Stop",
            f"{len(atr_closed)} kilit · {tot:+.2f}$",
            rows,
            footer="Trailing kâr kilidi vuruldu",
        )
    dust = {}
    try:
        dust = dust_sweep()
    except Exception as e:
        print(f"[{LABEL}] dust_sweep: {e}")
        dust = {"error": str(e)}
    return {
        "ok": True,
        "closed": closed,
        "remaining": remaining,
        "updated": updated,
        "dust_sweep": dust,
    }


def run_open() -> dict:
    if not _enabled():
        print(f"[{LABEL}] CRYPTO_FUTURES_CR6_ENABLED=false — open atlandı")
        return {"ok": False, "skipped": "disabled"}

    state = load_state()
    if state.get("open_positions"):
        print(f"[{LABEL}] open: hâlâ {len(state['open_positions'])} açık — önce close")
        return {"ok": False, "skipped": "already_open", "open": state["open_positions"]}

    rows = asyncio.run(_scan_all())
    ranked = _pick_top(rows, n=max(TOP_N + 4, TOP_N))  # min-lot skip için ekstra aday
    print(f"[{LABEL}] scan={len(rows)} ranked={[(r['symbol'], r['signal'], r['score']) for r in ranked]}")

    start, end = _slot_bounds()
    opened = []
    errors = []

    for cand in ranked:
        if len(opened) >= TOP_N:
            break
        sym = cand["symbol"]
        side = "LONG" if cand["signal"] == "UP" else "SHORT"
        est = estimate_qty(sym, MARGIN_USD, LEVERAGE)
        if not est.get("ok"):
            print(f"[{LABEL}] {sym} min lot yok — atlandı")
            errors.append({"symbol": sym, "error": "min_lot"})
            continue
        try:
            r = open_market(
                sym,
                side,
                margin_usd=MARGIN_USD,
                leverage=LEVERAGE,
                margin_type="ISOLATED",
                skip_max_positions=True,  # kota ST TOP_N; paylaşılan state engellemesin
            )
            entry = float((r.get("order") or {}).get("avgPrice") or r.get("mark_price") or 0)
            if entry <= 0:
                entry = float(r.get("mark_price") or cand.get("price") or 0)
            atr_val = None
            try:
                kl_atr = _algo_fetch_klines(sym, "1h", 80)
                atr_val = atr_from_klines(kl_atr)
            except Exception as e:
                print(f"[{LABEL}] ATR {sym}: {e}")
            pos = init_lock_fields(
                {
                    "strategy": STRATEGY,
                    "symbol": sym,
                    "side": side,
                    "signal": cand["signal"],
                    "score": cand["score"],
                    "algo": cand.get("algo") or ALGO_NAME,
                    "tier": cand.get("tier") or _tier(sym),
                    "tier_label": cand.get("tier_label") or _tier_label(sym),
                    "qty": float(r.get("qty") or 0),
                    "leverage": LEVERAGE,
                    "margin_usd": MARGIN_USD,
                    "entry_price": entry,
                    "notional": float(r.get("notional") or 0),
                    "entry_time_tr": r.get("entry_time_tr"),
                    "slot_start_tr": start.isoformat(),
                    "slot_end_tr": end.isoformat(),
                    "order_id": (r.get("order") or {}).get("orderId"),
                    "dry_run": r.get("dry_run"),
                },
                atr=atr_val,
                price=entry,
            )
            opened.append(pos)
            print(
                f"[{LABEL}] OPEN {side} {sym} qty={pos['qty']} "
                f"tier={pos['tier_label']} score={cand['score']} dry={r.get('dry_run')}"
            )
        except Exception as e:
            print(f"[{LABEL}] OPEN hata {sym}: {e}")
            errors.append({"symbol": sym, "error": str(e)})

    state["open_positions"] = opened
    state["last_scan"] = [
        {
            "symbol": r["symbol"],
            "signal": r["signal"],
            "score": r["score"],
            "algo": r["algo"],
            "price": r.get("price"),
            "tier": _tier(r["symbol"]),
            "tier_label": _tier_label(r["symbol"]),
        }
        for r in rows
    ]
    save_state(state)

    if opened:
        _tg_open_card(opened)

    return {
        "ok": True,
        "opened": opened,
        "errors": errors,
        "scan_count": len(rows),
        "dry_run": _is_dry(load_config()),
    }


def _enrich_live(pos: dict, chain: dict | None, *, fee_rate: float | None = None) -> dict:
    """Anlık mark / unrealized PnL kart alanları (komisyon düşülmüş net)."""
    entry = float(pos.get("entry_price") or 0)
    qty = float(pos.get("qty") or 0)
    side = pos.get("side") or "LONG"
    mark = float((chain or {}).get("mark_price") or 0)
    if mark <= 0:
        try:
            mark = _client().mark_price(pos["symbol"])
        except Exception:
            mark = entry
    if side == "LONG":
        upnl_gross = (mark - entry) * qty
        winning = mark >= entry
    else:
        upnl_gross = (entry - mark) * qty
        winning = mark <= entry
    upnl_gross = round(upnl_gross, 4)
    margin = float(pos.get("margin_usd") or MARGIN_USD)
    entry_notional = float(pos.get("notional") or (entry * qty))
    exit_notional = mark * qty
    entry_fee = float(pos.get("entry_fee") or 0)
    rate = fee_rate if fee_rate is not None else get_taker_rate(
        None, pos.get("symbol") or "BTCUSDT", cfg=load_config(),
    )
    if entry_fee <= 0:
        entry_fee = estimate_fee(entry_notional, rate)
    exit_fee = estimate_fee(exit_notional, rate)
    commission_est = round(entry_fee + exit_fee, 6)
    upnl_net = net_pnl(upnl_gross, commission_est)
    # Anlık kapatma ≈ teminat + net unrealized
    close_val = round(margin + upnl_net, 4)
    name = pos["symbol"].replace("USDT", "")
    slot_s = pos.get("slot_start_tr") or ""
    slot_e = pos.get("slot_end_tr") or ""
    try:
        ss = datetime.fromisoformat(slot_s).astimezone(_TZ_TR)
        se = datetime.fromisoformat(slot_e).astimezone(_TZ_TR)
        slot_label = f"{ss.strftime('%H:%M')}-{se.strftime('%H:%M')} İST"
    except Exception:
        slot_label = "1s slot"
    pos_locked, _ = update_lock(dict(pos), upnl_net)
    ls = lock_summary(pos_locked)
    return {
        **pos_locked,
        "name": name,
        "dir_tr": "YÜKSELİR" if side == "LONG" else "DÜŞER",
        "current": round(mark, 4),
        "delta": round(mark - entry, 4),
        "unrealized_pnl_gross": upnl_gross,
        "unrealized_pnl": upnl_net,
        "commission_est": commission_est,
        "entry_fee": entry_fee,
        "exit_fee_est": exit_fee,
        "close_val": close_val,
        "close_pnl": upnl_net,
        "close_pnl_gross": upnl_gross,
        "winning": upnl_net >= 0,
        "slot_label": slot_label,
        "analiz": LABEL,
        "analiz_key": "cr6",
        "closable": True,
        "pm_spent": margin,
        "hard_sl_usd": round(hard_sl_threshold(pos_locked), 2),
        **ls,
    }


def _scan_cache_fresh(state: dict, ttl_sec: int = 60) -> bool:
    ts = state.get("last_scan_at_tr") or ""
    if not ts or not (state.get("last_scan") or []):
        return False
    try:
        t = datetime.fromisoformat(ts)
        if t.tzinfo is None:
            t = t.replace(tzinfo=_TZ_TR)
        return (datetime.now(_TZ_TR) - t.astimezone(_TZ_TR)).total_seconds() < ttl_sec
    except Exception:
        return False


def _waiting_list(scan: list[dict], open_syms: set[str]) -> list[dict]:
    """Supertrend skor sırası — top-N bekleyen; açıklar işaretli."""
    top_syms = {c["symbol"] for c in _pick_top(list(scan or []), n=TOP_N)}
    rows = sorted(
        list(scan or []),
        key=lambda x: (
            0 if x.get("signal") in ("UP", "DOWN") and float(x.get("score") or 0) > 0 else 1,
            _tier(x.get("symbol") or ""),
            -(float(x.get("score") or 0)),
        ),
    )
    active_rank = 0
    out = []
    for r in rows:
        sig = r.get("signal") or "NEUTRAL"
        is_active = sig in ("UP", "DOWN") and float(r.get("score") or 0) > 0
        sym = r.get("symbol") or ""
        if is_active and _tier(sym) in (1, 2):
            active_rank += 1
            rank = active_rank
        else:
            rank = None
        name = sym.replace("USDT", "")
        if name.startswith("1000"):
            name = name  # 1000PEPE
        side = "LONG" if sig == "UP" else "SHORT" if sig == "DOWN" else None
        tier = _tier(sym)
        out.append({
            "symbol": sym,
            "name": name,
            "signal": sig,
            "side": side,
            "dir_tr": "YÜKSELİR" if side == "LONG" else "DÜŞER" if side == "SHORT" else "NÖTR",
            "score": round(float(r.get("score") or 0), 4),
            "algo": r.get("algo") or "",
            "price": r.get("price"),
            "tier": tier,
            "tier_label": _tier_label(sym),
            "rank": rank,
            "is_top": sym in top_syms,
            "is_open": sym in open_syms,
            "waiting": bool(is_active and sym not in open_syms and tier in (1, 2)),
        })
    return out


def refresh_scan(force: bool = False, ttl_sec: int = 60) -> list[dict]:
    """Dashboard için skor taraması (TTL cache → state.last_scan)."""
    state = load_state()
    if not force and _scan_cache_fresh(state, ttl_sec=ttl_sec):
        return list(state.get("last_scan") or [])
    rows = asyncio.run(_scan_all())
    state["last_scan"] = [
        {
            "symbol": r["symbol"],
            "signal": r["signal"],
            "score": r["score"],
            "algo": r["algo"],
            "price": r.get("price"),
            "tier": _tier(r["symbol"]),
            "tier_label": _tier_label(r["symbol"]),
        }
        for r in rows
    ]
    state["last_scan_at_tr"] = datetime.now(_TZ_TR).isoformat()
    # open_positions koru
    save_state(state)
    return state["last_scan"]


def _reconcile_opens_with_binance(opens: list[dict], chain_map: dict, *, dry: bool) -> tuple[list[dict], list[dict]]:
    """Yerel açıklar vs Binance: zincirde yoksa (manuel kapatma) state'ten düş.

    dry_run kayıtları / global dry modda dokunulmaz.
    """
    kept: list[dict] = []
    orphaned: list[dict] = []
    for p in opens:
        if dry or p.get("dry_run"):
            kept.append(p)
            continue
        sym = (p.get("symbol") or "").upper()
        if sym and sym in chain_map:
            kept.append(p)
        else:
            orphaned.append(p)
    return kept, orphaned


def _drop_orphaned_opens(orphaned: list[dict]) -> None:
    """Binance'te kapanmış pozisyonları history'e yaz + state güncelle."""
    if not orphaned:
        return
    now = datetime.now(_TZ_TR).isoformat()
    history = load_history()
    for p in orphaned:
        history.append({
            **p,
            "exit_price": p.get("exit_price"),
            "exit_time_tr": now,
            "pnl": p.get("pnl"),
            "close_note": "binance_external",
        })
        print(f"[{LABEL}] sync: {p.get('symbol')} Binance'te yok → state'ten düşüldü")
    save_history(history)
    state = load_state()
    drop = {(p.get("symbol") or "").upper() for p in orphaned}
    state["open_positions"] = [
        p for p in (state.get("open_positions") or [])
        if (p.get("symbol") or "").upper() not in drop
    ]
    state["updated_at_tr"] = now
    save_state(state)


def cr6_status_block(*, refresh: bool = True) -> dict:
    """Dashboard / status() için Supertrend Live bloğu."""
    cfg = load_config()
    dry = _is_dry(cfg)
    state = load_state()
    opens = list(state.get("open_positions") or [])
    chain_map = {}
    usdt = None
    try:
        c = _client(cfg)
        if c.configured():
            usdt = usdt_balance(c)
            for p in get_positions(c):
                chain_map[p["symbol"]] = p
            # Canlı: Binance'te kapanmışları state'ten temizle
            opens, orphaned = _reconcile_opens_with_binance(opens, chain_map, dry=dry)
            if orphaned:
                _drop_orphaned_opens(orphaned)
                state = load_state()
                opens = list(state.get("open_positions") or [])
    except Exception as e:
        open_syms = {p.get("symbol") for p in opens if p.get("symbol")}
        scan = state.get("last_scan") or []
        return {
            "enabled": _enabled(),
            "dry_run": dry,
            "error": str(e),
            "open_positions": opens,
            "cards": [],
            "last_scan": scan,
            "waiting": _waiting_list(scan, open_syms),
        }

    open_syms = {p.get("symbol") for p in opens if p.get("symbol")}
    try:
        fee_rate = get_taker_rate(c if c.configured() else None, "BTCUSDT", cfg=cfg)
    except Exception:
        fee_rate = float(cfg.get("taker_fee_rate") or 0.0004)
    cards = [
        _enrich_live(p, chain_map.get(p.get("symbol")), fee_rate=fee_rate)
        for p in opens
    ]
    total_upnl = round(sum(c.get("unrealized_pnl") or 0 for c in cards), 4)
    total_upnl_gross = round(sum(c.get("unrealized_pnl_gross") or 0 for c in cards), 4)
    total_commission_est = round(sum(c.get("commission_est") or 0 for c in cards), 4)
    scan = refresh_scan(force=False, ttl_sec=60) if refresh else list(state.get("last_scan") or [])
    waiting = _waiting_list(scan, open_syms)
    return {
        "enabled": _enabled(),
        "dry_run": dry,
        "live_env": os.getenv("CRYPTO_FUTURES_LIVE", "false"),
        "label": LABEL,
        "strategy": STRATEGY,
        "algo": ALGO_NAME,
        "margin_usd": MARGIN_USD,
        "leverage": LEVERAGE,
        "taker_fee_rate": fee_rate,
        "top_n": TOP_N,
        "symbols": _symbols(),
        "usdt": usdt,
        "open_count": len(cards),
        "total_unrealized_pnl": total_upnl,
        "total_unrealized_pnl_gross": total_upnl_gross,
        "total_commission_est": total_commission_est,
        "open_positions": opens,
        "cards": cards,
        "last_scan": scan,
        "last_scan_at_tr": load_state().get("last_scan_at_tr"),
        "waiting": waiting,
        "updated_at_tr": datetime.now(_TZ_TR).isoformat(),
    }


def run_status() -> dict:
    return cr6_status_block()


def main() -> None:
    p = argparse.ArgumentParser(description="Supertrend Live Binance Futures")
    p.add_argument("cmd", choices=["open", "close", "trail", "status", "preview"])
    args = p.parse_args()
    if args.cmd == "open":
        r = run_open()
    elif args.cmd == "close":
        r = run_close()
    elif args.cmd == "trail":
        r = run_trail()
    elif args.cmd == "preview":
        r = run_preview()
    else:
        r = run_status()
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
