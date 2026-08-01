#!/usr/bin/env python3
"""15M 309 LIVE — Squeeze Mom gerçek Polymarket ($3 sabit).

Sanal 15M 309 ile aynı mantık / aynı anda:
  - Sinyal ve açılış kararı sanal run_open'dan gelir (mirror).
  - Live kendi başına ayrı sinyal üretmez.
  - Close: sanal close ile birlikte (PM settle).

Env: PM_15M_309_REAL_ENABLED=true
Cron: poly_trader_15m_a2.py open → sanal 309 open içinde mirror.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import poly_trader_5m_common as _pm_common
from poly_15m_a2_algo_trader_core import (
    CONFIG_BY_NUM,
    _PERIOD_MIN,
    _current_period_ts,
    _fetch_klines_15m,
    _resolve_period_candle,
    _sym_short,
    _wr,
)
from pm_trader_helpers import (
    pm_5m_history_extras,
    pm_fetch_resolution,
    pm_get_balance,
    pm_realized_pnl,
    pm_tg_stake,
    tg_send_pm_live,
)
from pm_balance_guard import can_open_trade

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

_DIR = os.path.dirname(os.path.abspath(__file__))
_TZ_TR = ZoneInfo("Europe/Istanbul")
STATE_FILE = os.path.join(_DIR, "poly_trader_15m_309_live_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_15m_309_live_history.json")

LABEL = "15M 309 LIVE"
CFG = CONFIG_BY_NUM[309]
TRADE_AMOUNT = 3.0
_PM_LIVE = os.getenv("PM_15M_309_REAL_ENABLED", "false").lower() in ("1", "true", "yes")
_PM_SANITY_MIN = 0.05
_PM_SANITY_MAX = 0.95
# Emir deneme süresi — sanal gibi pencere yok; makul kısa retry
_ORDER_TRY_SEC = 60


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": 0.0, "open_positions": [], "total_pnl": 0.0}


def save_state(state: dict) -> None:
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


def tg_send(text: str) -> None:
    tg_send_pm_live(text, label=LABEL)


def _pm_bal_line() -> str:
    bal = pm_get_balance()
    return f"💰 PM Bakiye: ${bal:.2f}" if bal >= 0 else "💰 PM Bakiye: ?"


def _resolve_market(symbol: str, ts_period: int, direction: str):
    """Sanal ile aynı yön — sadece market/token; 0.35–0.65 bandı yok."""
    pm = None
    for attempt in range(3):
        pm = _pm_common._pm_find_15m_market(ts_period, symbol)
        if pm and not pm.get("closed") and pm.get("up_token") and pm.get("down_token"):
            break
        if attempt < 2:
            time.sleep(1)
            pm = None
    if not pm or pm.get("closed"):
        return None, "PM market yok"
    tp = pm["up_price"] if direction == "UP" else pm["down_price"]
    if not (_PM_SANITY_MIN <= tp <= _PM_SANITY_MAX):
        return None, f"token @{tp:.2f} sanity dışı"
    pm["token_price"] = tp
    return pm, ""


def _fetch_resolution_retry(slug: str, *, period_ended: bool) -> dict | None:
    """15m marketler hemen 0.99 olmuyor — kademeli eşik + kısa retry."""
    thresholds = (0.99, 0.95, 0.90, 0.80) if period_ended else (0.99, 0.95)
    for thr in thresholds:
        for _ in range(3):
            res = pm_fetch_resolution(slug, min_decisive=thr)
            if res is not None:
                return res
            time.sleep(2)
    return None


def run_close(*, wait: bool = True) -> None:
    """Önceki tur live pozisyonlarını PM settle ile kapat."""
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    now_ts = time.time()
    state = load_state()
    history = load_history()
    if not state["open_positions"]:
        print(f"[{LABEL} close] açık pozisyon yok")
        return

    if wait:
        time.sleep(2)
    lines: list[str] = []
    tur_pnl = 0.0
    kept: list[dict] = []

    for pos in list(state["open_positions"]):
        sym = pos["symbol"]
        pos_ts = int(pos.get("ts_period") or 0)
        # Bu slotun 15dk'sı bitti mi? (yeni slot açılışında önceki kapanır)
        period_ended = bool(pos_ts) and now_ts >= pos_ts + 900
        # Henüz bitmemiş (aynı slot) pozisyonu kapatma
        if pos_ts and not period_ended:
            kept.append(pos)
            print(f"[{LABEL} close] {_sym_short(sym)} slot devam — bekleniyor")
            continue

        candle = _resolve_period_candle(sym, pos_ts) if pos_ts else None
        if candle is None:
            try:
                candle = _fetch_klines_15m(sym, 10)[-2]
            except Exception as e:
                print(f"[{LABEL} close] {sym}: {e}", file=sys.stderr)
                kept.append(pos)
                continue

        ref_open = float(candle["open"])
        prev_close = float(candle["close"])
        pred = pos["predicted_dir"]
        binance_actual = "UP" if prev_close >= ref_open else "DOWN"
        amount = float(pos.get("amount") or TRADE_AMOUNT)

        has_pm = bool(pos.get("pm_slug") and pos.get("pm_order_id"))
        pm_source = False
        if has_pm:
            res = _fetch_resolution_retry(pos["pm_slug"], period_ended=period_ended)
            if res is None:
                # Slot bitti ama PM gecikti → Binance ile kapat (bildirim kaçmasın)
                print(
                    f"[{LABEL} close] {_sym_short(sym)} PM sonuç yok — Binance fallback",
                    file=sys.stderr,
                )
                win = pred == binance_actual
                actual = binance_actual
                pnl = pm_realized_pnl(pos, win)
            else:
                token_dir = pos.get("pm_token_dir") or pred
                win = (token_dir == "UP" and res["up_won"]) or (
                    token_dir == "DOWN" and not res["up_won"]
                )
                actual = "UP" if res["up_won"] else "DOWN"
                pnl = pm_realized_pnl(pos, win)
                pm_source = True
        else:
            win = pred == binance_actual
            actual = binance_actual
            pnl = pm_realized_pnl(pos, win)

        tur_pnl += pnl
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)
        history.append({
            "symbol": sym,
            "predicted_dir": pred,
            "actual_dir": actual,
            "binance_actual": binance_actual,
            "win": win,
            "entry_price": ref_open,
            "exit_price": prev_close,
            "amount": amount,
            "pnl": pnl,
            "entry_time_tr": pos.get("entry_time_tr"),
            "entry_period_min": pos.get("entry_period_min"),
            "entry_dow": pos.get("entry_dow"),
            "entry_hour_tr": pos.get("entry_hour_tr"),
            "exit_time_tr": now_tr.isoformat(),
            "algo_name": CFG.algo_name,
            "algo_num": 309,
            "pm_live": True,
            "settle_source": "pm" if pm_source else "binance",
            "ts_period": pos.get("ts_period"),
            **pm_5m_history_extras(pos),
        })
        name = _sym_short(sym)
        icon = "✅" if win else "❌"
        src = "PM" if pm_source else "BN"
        lines.append(
            f"{icon} {name}  {pred}  net {'+' if pnl >= 0 else ''}{pnl:.2f}$  <i>({src})</i>"
        )

    state["open_positions"] = kept
    save_state(state)
    save_history(history)
    if not lines:
        if kept:
            print(f"[{LABEL} close] sonuç yok — {len(kept)} pozisyon bekliyor")
        else:
            print(f"[{LABEL} close] kapatılacak yok")
        return
    wins = sum(1 for t in history if t.get("win"))
    closed = len(history)
    genel = f"%{wins / closed * 100:.0f}" if closed else "—"
    sep = "━" * 26
    tg_send(
        f"{sep}\n🏁 <b>{LABEL} — Sonuçlar</b>  🔴 GERÇEK PM  $3\n"
        + "\n".join(lines)
        + f"\nBu tur: {'+' if tur_pnl >= 0 else ''}{tur_pnl:.2f}$  |  {_pm_bal_line()}\n"
        f"Genel: {genel} ({closed} işlem)\n{sep}"
    )
    print(f"[{LABEL} close] {len(lines)} pozisyon kapatıldı, {len(kept)} açık kaldı")


def mirror_open_from_sanal(
    *,
    symbol: str,
    direction: str,
    entry_price: float,
    ts_period: int,
    period_min: int,
    dow: int,
    hour_tr: int,
    now_tr: datetime | None = None,
) -> str | None:
    """Sanal 309 aynı sembol/yön açarken çağrılır — $3 gerçek PM.

    Returns: TG satırı veya None (atlandı).
    """
    if not _PM_LIVE:
        return None
    if now_tr is None:
        now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    if not can_open_trade(LABEL, tg_send):
        return None

    name = _sym_short(symbol)
    # Aynı ts_period için çift açma
    state = load_state()
    for p in state.get("open_positions") or []:
        if p.get("symbol") == symbol and p.get("ts_period") == ts_period:
            print(f"[{LABEL} mirror] {name} zaten açık bu slot")
            return None

    pm_info, pm_skip = _resolve_market(symbol, ts_period, direction)
    if not pm_info:
        print(f"[{LABEL} mirror] {name} — {pm_skip}")
        return None

    token_price = pm_info["token_price"]
    token_id = pm_info["up_token"] if direction == "UP" else pm_info["down_token"]
    if time.time() < ts_period + 3:
        _pm_common._pm_period_warmup(ts_period)

    # Sanal gibi sabit +45s penceresi yok — emir denemesi şimdiden kısa süre
    deadline = time.time() + _ORDER_TRY_SEC
    _pm_common._PM_DRY_RUN = False
    _pm_common.LABEL = LABEL
    order = _pm_common._pm_place_order(
        token_id, TRADE_AMOUNT, pm_info.get("tick_size", "0.01"),
        pm_info.get("neg_risk", False), deadline=deadline,
        min_shares=1.0,
        max_spent=TRADE_AMOUNT,
    )
    if not order or order.get("_skip"):
        print(f"[{LABEL} mirror] {name} — emir başarısız")
        return None

    spent = float(order["spent"])
    size = float(order["size"])
    price = float(order.get("price") or token_price)
    pos = {
        "symbol": symbol,
        "predicted_dir": direction,
        "entry_price": entry_price,
        "entry_time_tr": now_tr.isoformat(),
        "entry_period_min": period_min,
        "entry_dow": dow,
        "entry_hour_tr": hour_tr,
        "ts_period": ts_period,
        "amount": spent,
        "pm_spent": spent,
        "pm_size": size,
        "to_win": size,
        "pm_entry_price": price,
        "token_price": price,
        "pm_slug": pm_info["slug"],
        "pm_token_id": token_id,
        "pm_token_dir": direction,
        "pm_order_id": order.get("order_id", ""),
        "algo_name": CFG.algo_name,
        "algo_num": 309,
        "pm_live": True,
        "mirrored_from_sanal": True,
    }
    state["open_positions"].append(pos)
    save_state(state)

    dir_icon = "📈" if direction == "UP" else "📉"
    dir_tr = "YÜKSELİR" if direction == "UP" else "DÜŞER"
    stake = pm_tg_stake(pos) or f"💵 ${spent:.2f}"
    line = (
        f"{dir_icon} <b>{name}</b>  {dir_tr}  giriş:{entry_price:.2f}  {stake}  🔴 GERÇEK\n"
        f"   @{price:.2f} → 🏆 ${size:.2f}"
    )
    print(f"[{LABEL} mirror] {name} {dir_tr} ${spent:.2f}→${size:.2f} (sanal ile)")

    history = load_history()
    wins = sum(1 for t in history if t.get("win"))
    total = len(history)
    saat = f"{period_min // 60:02d}:{period_min % 60:02d}"
    next_min = period_min + _PERIOD_MIN
    next_saat = f"{(next_min % (24 * 60)) // 60:02d}:{next_min % 60:02d}"
    sep = "━" * 26
    tg_send(
        f"{sep}\n🆕 <b>{LABEL} — {saat} → {next_saat}</b>  🔴 GERÇEK PM  $3\n"
        f"{line}\n{_pm_bal_line()}  |  📂 {len(state['open_positions'])} açık"
        f"  |  {_wr(wins, total)}\n"
        f"(sanal 309 ile aynı karar)\n{sep}"
    )
    return line


def run() -> None:
    """Manuel: close + sanal 309 turu (live mirror dahil)."""
    from poly_15m_a2_algo_trader_core import run_close as sanal_close, run_open as sanal_open, _tg_round

    cfg = CFG
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    period_min = (now_tr.hour * 60 + now_tr.minute) // _PERIOD_MIN * _PERIOD_MIN
    saat = f"{period_min // 60:02d}:{period_min % 60:02d}"
    next_min = period_min + _PERIOD_MIN
    next_saat = f"{(next_min % (24 * 60)) // 60:02d}:{next_min % 60:02d}"

    closed, tur_pnl = sanal_close(cfg)
    run_close(wait=False)
    opened = sanal_open(cfg)
    _tg_round(cfg, saat, next_saat, closed, opened, tur_pnl)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode in ("open", "run"):
        run()
    elif mode == "close":
        run_close()
    else:
        print(f"Bilinmeyen mod: {mode}")
        sys.exit(1)
