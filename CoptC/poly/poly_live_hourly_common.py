"""Saatlik gerçek PM trader ortak yardımcıları."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pm_trader_helpers import (
    pm_fetch_resolution,
    pm_find_market,
    pm_log_hata,
    pm_place_order,
    pm_realized_pnl,
    pm_sanal_quote,
    pm_hourly_profit_entry_ok,
    pm_stake_fields,
    pm_tg_stake,
    tg_send_pm_live,
)


def tg_send(label: str, text: str) -> None:
    tg_send_pm_live(text, label=label)


def try_pm_open(
    state: dict,
    *,
    label: str,
    hata_file: str,
    sym: str,
    direction: str,
    entry_price: float,
    hour_tr: int,
    dow: int,
    is_weekend: bool,
    now_tr: datetime,
    now: datetime,
    extra: dict,
    amount: float,
    pm_live: bool,
    min_profit_ratio: float | None = None,
) -> tuple[dict | None, str | None]:
    import pm_trader_helpers as pmh
    pmh.PM_DRY_RUN = not pm_live

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
        pm_log_hata(hata_file, sym, "market_" + durum, f"et_hour={et_hour}")
        return None, "market"
    if min_profit_ratio is not None:
        q = pm_sanal_quote(sym, direction, amount, now)
        if q:
            ok, skip_msg = pm_hourly_profit_entry_ok(q, min_profit_ratio)
            if not ok:
                print(f"[{label}] {sym} — {skip_msg}")
                pm_log_hata(hata_file, sym, "profit_low", skip_msg)
                return None, "profit_low"
    token_id = pm["up_token"] if direction == "UP" else pm["down_token"]
    order = pm_place_order(
        token_id, amount, pm["tick_size"], pm["neg_risk"],
        label=label, hata_file=hata_file,
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
    state["open_positions"].append(pos)
    return pos, None


def close_pm_positions(
    state: dict,
    history: list,
    *,
    label: str,
    fetch_klines,
    default_amount: float,
    extra_rec_fn=None,
) -> tuple[list[str], float, list[dict]]:
    """Açık pozisyonları kapat. (tg_lines, tur_pnl, failed_pos) döner."""
    lines: list[str] = []
    tur_pnl = 0.0
    failed: list[dict] = []

    for pos in list(state["open_positions"]):
        sym = pos["symbol"]
        klines = fetch_klines(sym, "1h", 2)
        if hasattr(klines, "__await__"):
            raise TypeError("fetch_klines must be sync here")
        if not klines:
            failed.append(pos)
            continue
        current_price = klines[-1]["close"] if isinstance(klines[-1], dict) else klines[-1].get("close")
        entry = pos["entry_price"]
        pred = pos["predicted_dir"]
        amount = pos.get("amount", default_amount)
        binance_actual = "UP" if current_price >= entry else "DOWN"

        has_pm = bool(pos.get("pm_slug") and pos.get("pm_order_id"))
        pm_win = None
        pm_source = False
        if has_pm:
            res = pm_fetch_resolution(pos["pm_slug"])
            if res is None:
                failed.append(pos)
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

        tur_pnl += pnl
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

        rec = {
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
            "exit_time_tr": datetime.now(timezone.utc).astimezone().isoformat(),
            "pnl": pnl,
            "pm_live": True,
        }
        if extra_rec_fn:
            rec.update(extra_rec_fn(pos, win))
        history.append(rec)

        name = sym.replace("USDT", "")
        icon = "✅" if win else "❌"
        pct = (current_price - entry) / entry * 100 if entry else 0
        stake = pm_tg_stake(pos) or f"💵 ${amount:.0f}"
        src = "🎯PM" if pm_source else "BN"
        lines.append(
            f"{icon} {name}  {pred}  {entry:.2f}→{current_price:.2f} ({pct:+.2f}%)\n"
            f"   {stake}  net {'+' if pnl >= 0 else ''}{pnl:.2f}$  {src}"
        )

    return lines, tur_pnl, failed
