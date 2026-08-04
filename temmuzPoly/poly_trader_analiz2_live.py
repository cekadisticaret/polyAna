"""
2. ANALİZ LIVE — SOL gerçek Polymarket ($6–8 WR'ye göre)

Algoritma: poly_trader_analiz2 ile aynı sinyal (predict, ALLOW_FALLBACK=False).
A1 Live'e dokunmaz; kendi state/history; bağımsız cron.

Gerçek PM: PM_ANALIZ2_REAL_ENABLED (varsayılan false)
Hafta sonu: dashboard anahtarı (Cum 22:00 otomatik kapanır · Pzt 12:00 açılır; manuel override mümkün)
Modlar: close (:02 PM sonuç) / open (:05)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from poly_predictor_analysis import _fetch_klines
from poly_trader_analiz2 import (
    ALLOW_FALLBACK,
    SYMBOLS,
    _resolve_signal,
    _us_market_open,
    get_stats,
    get_symbol_stats,
    _wr,
)
from pm_trader_helpers import (
    pm_fetch_resolution,
    pm_get_balance,
    pm_place_order,
    pm_find_market,
    pm_log_hata,
    pm_stake_fields,
    pm_realized_pnl,
    pm_tg_stake,
    resolve_open_slot_gates,
    slot_amount_log,
    tg_send_pm_live,
    skip_if_weekend_pause,
    pm_live_wr_amount,
    pm_live_amount_range_str,
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

_TZ_TR = ZoneInfo("Europe/Istanbul")
_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(_DIR, "poly_trader_analiz2_live_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_analiz2_live_history.json")
HATA_FILE = os.path.join(_DIR, "analiz2_live_polyhata.json")

LABEL = "2. ANALİZ LIVE"
TRADE_AMOUNT = 7.0
TRADE_AMOUNT_LOW = 6.0
TRADE_AMOUNT_HIGH = 8.0
ANALIZ2_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poly_trader_analiz2_history.json")
INITIAL_BALANCE = 300.0

_PM_LIVE = os.getenv("PM_ANALIZ2_REAL_ENABLED", "false").lower() in ("1", "true", "yes")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": INITIAL_BALANCE, "open_positions": [], "total_pnl": 0.0}


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


def _trade_amount(history: list, symbol: str) -> float:
    return pm_live_wr_amount("a2", history, symbol, get_symbol_stats)


def load_analiz2_signal_history() -> list:
    if not os.path.exists(ANALIZ2_HISTORY_FILE):
        return []
    try:
        with open(ANALIZ2_HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _try_pm_open(
    state: dict,
    *,
    sym: str,
    direction: str,
    entry_price: float,
    hour_tr: int,
    dow: int,
    is_weekend: bool,
    now_tr: datetime,
    now: datetime,
    extra: dict,
    amount: float = TRADE_AMOUNT,
) -> tuple[dict | None, str | None]:
    import pm_trader_helpers as pmh
    pmh.PM_DRY_RUN = not _PM_LIVE

    et_hour = (now - timedelta(hours=4)).hour
    pos = {
        "symbol": sym,
        "predicted_dir": direction,
        "entry_price": entry_price,
        "entry_time_tr": now_tr.isoformat(),
        "entry_hour_tr": hour_tr,
        "entry_dow": dow,
        "entry_is_weekend": is_weekend,
        "amount": amount,
        **extra,
    }
    pm = pm_find_market(sym, et_hour, now)
    if not pm or not pm.get("active") or pm.get("closed"):
        durum = "bulunamadı" if not pm else "kapalı"
        pm_log_hata(HATA_FILE, sym, "market_" + durum, f"et_hour={et_hour}")
        return None, "market"
    from pm_trader_helpers import pm_sanal_quote, pm_hourly_profit_entry_ok, HOURLY_MIN_NET_PROFIT_RATIO
    q = pm_sanal_quote(sym, direction, amount, now)
    if q:
        ok, skip_msg = pm_hourly_profit_entry_ok(q, HOURLY_MIN_NET_PROFIT_RATIO)
        if not ok:
            print(f"[{LABEL}] {sym} — {skip_msg}")
            pm_log_hata(HATA_FILE, sym, "profit_low", skip_msg)
            return None, "profit_low"
    token_id = pm["up_token"] if direction == "UP" else pm["down_token"]
    order = pm_place_order(
        token_id, amount, pm["tick_size"], pm["neg_risk"],
        label=LABEL, hata_file=HATA_FILE,
    )
    if not order:
        return None, "order"
    pos.update({
        "pm_slug": pm["slug"],
        "pm_title": pm.get("title", ""),
        "pm_token_id": token_id,
        "pm_token_dir": direction,
        "pm_size": order["size"],
        "pm_entry_price": order["price"],
        "pm_order_id": order["order_id"],
        "pm_spent": order["spent"],
        "pm_live": True,
    })
    print(
        f"[{LABEL}] PM order: {sym} {direction} "
        f"{order['size']} @ {order['price']} (${order['spent']:.2f})"
    )
    state["open_positions"].append(pos)
    return pos, None


async def run_close() -> None:
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")
    if skip_if_weekend_pause(LABEL, "close", now_tr):
        return

    state = load_state()
    history = load_history()

    if not state["open_positions"]:
        print(f"[{LABEL} close] {saat} İST — açık pozisyon yok")
        return

    lines = []
    toplam_pnl = 0.0
    failed_pos = []

    for pos in list(state["open_positions"]):
        sym = pos["symbol"]
        klines = await _fetch_klines(sym, "1h", 2)
        if not klines:
            failed_pos.append(pos)
            continue
        current_price = klines[-1]["close"]

        entry = pos["entry_price"]
        pred = pos["predicted_dir"]
        amount = pos.get("amount", TRADE_AMOUNT)
        binance_actual = "UP" if current_price >= entry else "DOWN"

        has_pm = bool(pos.get("pm_slug") and pos.get("pm_order_id"))
        pm_win = None
        pm_source = False
        if has_pm:
            res = pm_fetch_resolution(pos["pm_slug"])
            if res is None:
                print(
                    f"[{LABEL} close] {sym} PM sonucu bekleniyor ({pos.get('pm_slug')}) — ertelendi",
                    file=sys.stderr,
                )
                failed_pos.append(pos)
                continue
            token_dir = pos.get("pm_token_dir") or pred
            pm_win = (token_dir == "UP" and res["up_won"]) or (
                token_dir == "DOWN" and not res["up_won"]
            )
            actual = "UP" if res["up_won"] else "DOWN"
            win = bool(pm_win)
            pm_source = True
        else:
            actual = binance_actual
            win = pred == actual

        pm_spent = float(pos.get("pm_spent") or amount or 0)
        pm_size = float(pos.get("pm_size") or 0)
        if pm_source and pm_size > 0 and pm_spent > 0:
            pnl = pm_realized_pnl(pos, win)
        else:
            pnl = round(pm_size - pm_spent, 2) if win and pm_size else round(-pm_spent, 2)

        toplam_pnl += pnl
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

        history.append({
            "symbol": sym,
            "predicted_dir": pred,
            "actual_dir": actual,
            "binance_actual": binance_actual,
            "win": win,
            "pm_win": pm_win,
            "settle_source": "pm" if pm_source else "binance",
            "entry_price": entry,
            "exit_price": current_price,
            "entry_time_tr": pos["entry_time_tr"],
            "entry_hour_tr": pos.get("entry_hour_tr"),
            "entry_dow": pos.get("entry_dow"),
            "entry_is_weekend": pos.get("entry_is_weekend"),
            "amount": amount,
            "pm_spent": pos.get("pm_spent"),
            "pm_size": pos.get("pm_size"),
            "pm_entry_price": pos.get("pm_entry_price"),
            "pm_order_id": pos.get("pm_order_id"),
            "pm_slug": pos.get("pm_slug"),
            "pm_token_dir": pos.get("pm_token_dir"),
            "pm_spent_original": pos.get("pm_spent_original"),
            "pm_partial_received": pos.get("pm_partial_received"),
            "pm_partial_sold_size": pos.get("pm_partial_sold_size"),
            "pm_partial_tp_done": pos.get("pm_partial_tp_done"),
            "exit_time_tr": now_tr.isoformat(),
            "pnl": pnl,
            "pm_live": True,
            "ind_rsi_vote": pos.get("ind_rsi_vote"),
            "ind_macd_vote": pos.get("ind_macd_vote"),
            "ind_ema_vote": pos.get("ind_ema_vote"),
        })

        name = sym.replace("USDT", "")
        icon = "✅" if win else "❌"
        pct = (current_price - entry) / entry * 100 if entry else 0
        stake = pm_tg_stake(pos) or f"💵 ${amount:.0f}"
        src = "🎯PM" if pm_source else "BN"
        lines.append(
            f"{icon} {name}  {pred}  {entry:.2f}→{current_price:.2f} ({pct:+.2f}%)\n"
            f"   {stake}  net {'+' if pnl >= 0 else ''}{pnl:.2f}$  {src}"
        )

    state["open_positions"] = failed_pos
    save_state(state)
    save_history(history)

    if failed_pos:
        names = ", ".join(p["symbol"].replace("USDT", "") for p in failed_pos)
        print(f"[{LABEL} close] {saat} — ertelenen: {names}")

    if not lines:
        return

    closed_all = len(history)
    win_all = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    genel = f"%{win_all/closed_all*100:.0f}" if closed_all else "—"
    saat_round = f"{int(saat[:2]):02d}:00"
    sep = "━" * 26

    tg_send(
        f"{sep}\n"
        f"🏁 <b>{LABEL} — {saat_round} Sonuçlar</b>  🔴 GERÇEK PM\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+' if toplam_pnl >= 0 else ''}{toplam_pnl:.2f}$  |  {_pm_bal_line()}\n"
        f"{'🟢' if total_pnl >= 0 else '🔴'} Toplam P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all} işlem)\n"
        f"{sep}"
    )
    print(f"[{LABEL} close] {saat} İST — {len(lines)} pozisyon kapatıldı")


async def run_open() -> None:
    if not _PM_LIVE:
        print(f"[{LABEL} open] PM_ANALIZ2_REAL_ENABLED=false — atlandı")
        return

    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    history = load_history()
    if skip_if_weekend_pause(LABEL, "open", now_tr, history=history):
        return
    hour_tr = now_tr.hour
    dow = now_tr.weekday()
    is_weekend = dow >= 5
    saat = now_tr.strftime("%H:%M")

    state = load_state()

    if not can_open_trade(LABEL, tg_send):
        return

    cold_skip, _, _, _, cold_note = resolve_open_slot_gates(history, hour_tr, 0)
    if cold_skip:
        print(f"[{LABEL} open] {saat} — {cold_note} → işlem yok")
        return

    us_open = _us_market_open(now)
    opened = []

    for sym in SYMBOLS:
        pred_obj, sig_mode = await _resolve_signal(sym, us_open)
        if pred_obj is None:
            continue

        try:
            klines = await _fetch_klines(sym, "1h", 3)
            entry_price = klines[-2]["close"] if klines and len(klines) >= 2 else pred_obj.current_price
        except Exception:
            entry_price = pred_obj.current_price

        ind_ema_raw = pred_obj.trend.upper()
        extra = {
            "signal_mode": sig_mode,
            "us_market_open": us_open,
            "ind_rsi_vote": "UP" if pred_obj.rsi < 50 else "DOWN",
            "ind_rsi_val": round(pred_obj.rsi, 1),
            "ind_macd_vote": "UP" if pred_obj.macd_bull else "DOWN",
            "ind_ema_vote": (
                "UP" if "YUKARI" in ind_ema_raw
                else "DOWN" if "AŞAĞI" in ind_ema_raw
                else "NEUTRAL"
            ),
        }
        base_amount = _trade_amount(history, sym)
        _sk, amount, hot_boost, cold_cut, gate_note = resolve_open_slot_gates(
            history, hour_tr, base_amount
        )
        if gate_note:
            print(f"[{LABEL} open] {gate_note}")
        slot_amount_log(LABEL, hour_tr, base_amount, amount, hot_boost, cold_cut)
        pos, err = _try_pm_open(
            state,
            sym=sym,
            direction=pred_obj.predicted_dir,
            entry_price=entry_price,
            hour_tr=hour_tr,
            dow=dow,
            is_weekend=is_weekend,
            now_tr=now_tr,
            now=now,
            extra=extra,
            amount=amount,
        )
        if pos:
            opened.append({
                "sym": sym,
                "pred_obj": pred_obj,
                "entry_price": entry_price,
                "pos": pos,
                "sig_mode": sig_mode,
            })
        elif err:
            print(f"[{LABEL} open] {sym} — PM açılış hatası: {err}")

    save_state(state)

    if not opened:
        print(f"[{LABEL} open] {saat} İST — işlem yok")
        return

    next_h = f"{(hour_tr + 1) % 24:02d}:00"
    lines = []
    for c in opened:
        sym = c["sym"]
        pred_obj = c["pred_obj"]
        name = sym.replace("USDT", "")
        conf = max(pred_obj.prob_up, pred_obj.prob_down) * 100
        dir_icon = "📈" if pred_obj.predicted_dir == "UP" else "📉"
        dir_tr = "YÜKSELİR" if pred_obj.predicted_dir == "UP" else "DÜŞER"
        hour_wins, hour_total = get_stats(history, sym, hour_tr)
        sym_wins, sym_total = get_symbol_stats(history, sym)
        pos = c["pos"]
        mode_tag = "  🌙yedek" if c["sig_mode"] == "fallback" else ""
        pm_line = pm_tg_stake(pos)
        spent, size, _ = pm_stake_fields(pos)
        pm_detail = f"   {pm_line}" if pm_line else f"   💵 ${TRADE_AMOUNT:.0f}"
        if size > 0 and spent > 0:
            pm_detail += f"  (kazanırsa +${round(size - spent, 2):.2f})"
        lines.append(
            f"{dir_icon} <b>{name}</b>  {dir_tr}  konf:%{conf:.0f}  giriş:{c['entry_price']:.2f}{mode_tag}\n"
            f"{pm_detail}\n"
            f"   🕐 {hour_tr:02d}:00→{next_h} İST başarı: {_wr(hour_wins, hour_total)}"
            f"  |  genel: {_wr(sym_wins, sym_total)}"
        )

    sess_tag = "🇺🇸 ABD açık" if us_open else (
        "🌙 ABD kapalı (yedek)" if ALLOW_FALLBACK else "🌙 ABD kapalı (standard)"
    )
    at_risk = sum(p.get("pm_spent") or p.get("amount", TRADE_AMOUNT) for p in state["open_positions"])
    sep = "━" * 26
    tg_send(
        f"{sep}\n"
        f"🆕 <b>{LABEL} — {saat} - {next_h}</b>  🔴 GERÇEK PM  {pm_live_amount_range_str('a2')}/işlem  {sess_tag}\n"
        + "\n".join(lines)
        + f"\n{sep}\n"
        f"{_pm_bal_line()}  |  📂 ${at_risk:.0f} riskte\n"
        f"{sep}"
    )
    print(f"[{LABEL} open] {saat} İST — {len(opened)} açıldı")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        asyncio.run(run_close())
    else:
        asyncio.run(run_open())
