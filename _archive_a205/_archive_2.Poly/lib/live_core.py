#!/usr/bin/env python3
"""2.Poly A2#05 Live PM core (standalone).

Sanal defter kaynak; cron open :05:00 TR (+ :05:10 retry).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from poly_live_hourly_common import tg_send, try_pm_open
from klines import _fetch_klines
from sanal_core import _sym_short
from pm_trader_helpers import (
    HOURLY_MIN_NET_PROFIT_RATIO,
    pm_fetch_resolution,
    pm_get_balance,
    pm_live_amount_range_str,
    pm_live_wr_amount,
    pm_chain_settlement,
    pm_realized_pnl,
    pm_tg_stake,
    resolve_slot_trade_amount,
    skip_if_weekend_pause,
    slot_amount_log,
)
from pm_balance_guard import can_open_trade, is_dashboard_live_open

_TZ_TR = ZoneInfo("Europe/Istanbul")
_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


@dataclass(frozen=True)
class A2LiveSpec:
    algo_num: int
    algo_name: str
    label: str
    amount_system: str  # analiz5_settings anahtarı (örn. a2_02)
    env_flag: str       # PM_A2_02_LIVE_ENABLED
    default_amount: float = 5.0


def _paths(spec: A2LiveSpec) -> tuple[str, str, str]:
    tag = f"a2_{spec.algo_num:02d}_live"
    return (
        os.path.join(_DIR, f"poly_trader_{tag}_state.json"),
        os.path.join(_DIR, f"poly_trader_{tag}_history.json"),
        os.path.join(_DIR, f"{tag}_polyhata.json"),
    )


def get_live_spec(algo_num: int) -> A2LiveSpec | None:
    if algo_num != 5:
        return None
    return A2LiveSpec(
        algo_num=5,
        algo_name="Mean Reversion (Z-Score)",
        label="A2#05 Mean Rev Live",
        amount_system="a2_05",
        env_flag="PM_A2_05_LIVE_ENABLED",
        default_amount=5.0,
    )



def _pm_enabled(spec: A2LiveSpec) -> bool:
    """Dashboard Live anahtarı tek otorite; .env bayrağı yedek (geriye uyumluluk)."""
    if is_dashboard_live_open(spec.label):
        return True
    return os.getenv(spec.env_flag, "false").lower() in ("1", "true", "yes")


def is_live_active(spec: A2LiveSpec) -> bool:
    if not _pm_enabled(spec):
        return False
    return can_open_trade(spec.label, lambda t: tg_send(spec.label, t))


def _sanal_state_path(algo_num: int) -> str:
    return os.path.join(_DIR, f"poly_trader_a2_{algo_num:02d}_state.json")


def _live_has_sanal_pos(live_state: dict, sanal_pos: dict) -> bool:
    sym = sanal_pos.get("symbol")
    slug = sanal_pos.get("pm_slug")
    hour = sanal_pos.get("entry_hour_tr")
    for p in live_state.get("open_positions") or []:
        if p.get("symbol") != sym:
            continue
        if slug and p.get("pm_slug") == slug:
            return True
        if hour is not None and p.get("entry_hour_tr") == hour:
            return True
    return False


def load_state(spec: A2LiveSpec) -> dict:
    sp, _, _ = _paths(spec)
    if os.path.exists(sp):
        try:
            with open(sp) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": 0.0, "open_positions": [], "total_pnl": 0.0}


def save_state(spec: A2LiveSpec, state: dict) -> None:
    sp, _, _ = _paths(spec)
    with open(sp, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_history(spec: A2LiveSpec) -> list:
    _, hp, _ = _paths(spec)
    if os.path.exists(hp):
        try:
            with open(hp) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_history(spec: A2LiveSpec, history: list) -> None:
    _, hp, _ = _paths(spec)
    with open(hp, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _wr(wins: int, total: int) -> str:
    return f"%{wins / total * 100:.0f} ({wins}/{total})" if total else "veri yok"


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t.get("symbol") == symbol]
    return sum(1 for t in trades if t.get("win")), len(trades)


def get_stats(history: list, symbol: str, hour_tr: int) -> tuple[int, int]:
    trades = [
        t for t in history
        if t.get("symbol") == symbol and t.get("entry_hour_tr") == hour_tr
    ]
    return sum(1 for t in trades if t.get("win")), len(trades)


def _trade_amount(spec: A2LiveSpec, history: list, symbol: str) -> float:
    return pm_live_wr_amount(spec.amount_system, history, symbol, get_symbol_stats)


def _pm_bal_line() -> str:
    bal = pm_get_balance()
    return f"💰 PM Bakiye: ${bal:.2f}" if bal >= 0 else "💰 PM Bakiye: ?"


def _slot_ended(pos: dict, now_tr: datetime) -> bool:
    """Pozisyonun saat slotu kapandı mı (giriş saati + 1sa geçti mi)."""
    raw = pos.get("entry_time_tr")
    if not raw:
        return False
    try:
        entry = datetime.fromisoformat(raw)
    except ValueError:
        return False
    slot_end = entry.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return now_tr >= slot_end


async def run_close(spec: A2LiveSpec) -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    if skip_if_weekend_pause(spec.label, "close", now_tr):
        return
    state = load_state(spec)
    history = load_history(spec)
    if not state["open_positions"]:
        print(f"[{spec.label} close] açık pozisyon yok")
        return

    lines = []
    tur_pnl = 0.0
    failed = []
    for pos in list(state["open_positions"]):
        sym = pos["symbol"]
        klines = await _fetch_klines(sym, "1h", 2)
        if not klines:
            failed.append(pos)
            continue
        current_price = klines[-1]["close"]
        entry = pos["entry_price"]
        pred = pos["predicted_dir"]
        amount = pos.get("amount", spec.default_amount)
        has_pm = bool(pos.get("pm_slug") and pos.get("pm_order_id"))
        if has_pm:
            # Saat slotu bittiyse eşiği gevşet: mum kapandığı için 0.95 kesin sayılır
            res = pm_fetch_resolution(
                pos["pm_slug"],
                0.95 if _slot_ended(pos, now_tr) else 0.99,
            )
            if res is None:
                failed.append(pos)
                continue
            token_dir = pos.get("pm_token_dir") or pred
            win = (token_dir == "UP" and res["up_won"]) or (token_dir == "DOWN" and not res["up_won"])
            actual = "UP" if res["up_won"] else "DOWN"
            pnl = pm_realized_pnl(pos, win)
            chain = pm_chain_settlement(pos.get("pm_slug", ""), pos.get("pm_token_id", ""))
            if chain:
                # Kalan hisse kazanınca $1'e eşit; elde hisse yoksa gelen para neyse odur
                payout = chain["shares"] if win else 0.0
                pnl = round(chain["proceeds"] + payout - chain["spent"], 2)
                if win and chain["shares"] < 0.5:
                    pos["pm_exited_early"] = True
                    print(
                        f"[A2#05 Mean Rev Live close] {sym} — pozisyon zaten kapatılmış, "
                        f"gerçek sonuç {pnl:+.2f}$ (beklenen ödeme gelmedi)"
                    )
        else:
            actual = "UP" if current_price >= entry else "DOWN"
            win = pred == actual
            pm_spent = float(pos.get("pm_spent") or amount)
            pm_size = float(pos.get("pm_size") or 0)
            pnl = round(pm_size - pm_spent, 2) if win and pm_size else round(-pm_spent, 2)
        tur_pnl += pnl
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)
        history.append({
            "symbol": sym,
            "predicted_dir": pred,
            "actual_dir": actual,
            "win": win,
            "entry_price": entry,
            "exit_price": current_price,
            "entry_time_tr": pos["entry_time_tr"],
            "entry_hour_tr": pos.get("entry_hour_tr"),
            "entry_dow": pos.get("entry_dow"),
            "amount": amount,
            "pnl": pnl,
            "pm_live": True,
            "exit_time_tr": now_tr.isoformat(),
            "pm_spent": pos.get("pm_spent"),
            "pm_size": pos.get("pm_size"),
            "pm_exited_early": pos.get("pm_exited_early", False),
            "pm_slug": pos.get("pm_slug"),
            "algo_name": pos.get("algo_name", spec.algo_name),
            "algo_num": spec.algo_num,
        })
        name = _sym_short(sym)
        lines.append(f"{'✅' if win else '❌'} {name}  {pred}  net {'+' if pnl >= 0 else ''}{pnl:.2f}$")

    state["open_positions"] = failed
    save_state(spec, state)
    save_history(spec, history)
    if not lines:
        return
    closed = len(history)
    wins = sum(1 for t in history if t["win"])
    genel = f"%{wins / closed * 100:.0f}" if closed else "—"
    sep = "━" * 26
    tg_send(
        spec.label,
        f"{sep}\n🏁 <b>{spec.label} — Sonuçlar</b>  🔴 GERÇEK PM\n"
        + "\n".join(lines)
        + f"\nBu tur: {'+' if tur_pnl >= 0 else ''}{tur_pnl:.2f}$  |  {_pm_bal_line()}\n"
        f"Genel: {genel} ({closed} işlem)\n{sep}",
    )


async def mirror_open_from_sanal(
    spec: A2LiveSpec,
    sanal_pos: dict,
    *,
    entry_price: float,
    now_tr: datetime | None = None,
) -> tuple[dict | None, str | None]:
    """Sanal pozisyon → gerçek PM (aynı sembol, yön, slot)."""
    if not is_live_active(spec):
        return None, "inactive"

    sym = sanal_pos.get("symbol") or ""
    direction = (sanal_pos.get("predicted_dir") or sanal_pos.get("pm_token_dir") or "").upper()
    if not sym or direction not in ("UP", "DOWN"):
        return None, "bad_pos"
    if entry_price <= 0:
        return None, "bad_entry"

    if now_tr is None:
        now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    now = datetime.now(timezone.utc)

    state = load_state(spec)
    if _live_has_sanal_pos(state, sanal_pos):
        return None, "exists"

    history = load_history(spec)
    hour_tr = int(sanal_pos.get("entry_hour_tr", now_tr.hour))
    dow = int(sanal_pos.get("entry_dow", now_tr.weekday()))
    is_weekend = bool(sanal_pos.get("entry_is_weekend", dow >= 5))

    base = _trade_amount(spec, history, sym)
    amount, hot_boost, cold_cut = resolve_slot_trade_amount(base, hour_tr, history)
    slot_amount_log(spec.label, hour_tr, base, amount, hot_boost, cold_cut)
    _, _, hata = _paths(spec)

    pos, err = try_pm_open(
        state,
        label=spec.label,
        hata_file=hata,
        sym=sym,
        direction=direction,
        entry_price=entry_price,
        hour_tr=hour_tr,
        dow=dow,
        is_weekend=is_weekend,
        now_tr=now_tr,
        now=now,
        extra={
            "algo_name": spec.algo_name,
            "algo_num": spec.algo_num,
            "algo_signal": direction,
            "hot_hour_boost": hot_boost,
            "cold_hour_cut": cold_cut,
            "mirrored_from_sanal": True,
            "sanal_pm_slug": sanal_pos.get("pm_slug"),
        },
        amount=amount,
        pm_live=True,
        min_profit_ratio=HOURLY_MIN_NET_PROFIT_RATIO,
    )
    if pos:
        save_state(spec, state)
        name = _sym_short(sym)
        print(
            f"[{spec.label} mirror] {name} {direction} ${amount:.2f} "
            f"(sanal A2#{spec.algo_num:02d})"
        )
    return pos, err


async def sync_open_from_sanal_state(spec: A2LiveSpec) -> list[tuple[str, str, float, dict]]:
    """Sanal defterdeki tüm açık pozisyonları live'a yansıt."""
    if not is_live_active(spec):
        print(f"[{spec.label} sync] live kapalı — atlandı")
        return []

    spath = _sanal_state_path(spec.algo_num)
    if not os.path.exists(spath):
        return []
    try:
        with open(spath, encoding="utf-8") as f:
            sanal_state = json.load(f)
    except Exception:
        return []

    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    opened: list[tuple[str, str, float, dict]] = []
    for sanal_pos in sanal_state.get("open_positions") or []:
        entry_price = float(sanal_pos.get("entry_price") or 0)
        if entry_price <= 0:
            continue
        pos, err = await mirror_open_from_sanal(
            spec, sanal_pos, entry_price=entry_price, now_tr=now_tr,
        )
        if pos:
            sym = sanal_pos["symbol"]
            direction = (sanal_pos.get("predicted_dir") or "").upper()
            opened.append((sym, direction, entry_price, pos))
        elif err and err not in ("exists", "inactive"):
            print(f"[{spec.label} sync] {sanal_pos.get('symbol')} — {err}")
    return opened


async def run_open(spec: A2LiveSpec) -> None:
    """Live open — sinyal dosyasından doğrudan gerçek PM (sanal yok)."""
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    if skip_if_weekend_pause(spec.label, "open", now_tr):
        return
    if not _pm_enabled(spec):
        print(f"[{spec.label} open] dashboard kapalı ({spec.amount_system}) — atlandı")
        return
    if not is_live_active(spec):
        print(f"[{spec.label} open] live inactive — atlandı")
        return

    saat = now_tr.strftime("%H:%M")
    hour_tr = now_tr.hour
    dow = now_tr.weekday()
    is_weekend = dow >= 5
    now = datetime.now(timezone.utc)
    history = load_history(spec)
    state = load_state(spec)
    _, _, hata = _paths(spec)

    sig_path = os.path.join(_DIR, "algo_signals_v2.json")
    sig_entry = None
    if os.path.exists(sig_path):
        try:
            with open(sig_path, encoding="utf-8") as f:
                data = json.load(f)
            sig_entry = (data.get("signals") or {}).get(str(spec.algo_num))
        except Exception as e:
            print(f"[{spec.label} open] sinyal okuma: {e}")
    if not sig_entry:
        print(f"[{spec.label} open] {saat} — sinyal yok")
        return

    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    opened: list[tuple[str, str, float, dict]] = []

    for sym in symbols:
        short = _sym_short(sym)
        direction = (sig_entry.get(short) or "").upper()
        if direction not in ("UP", "DOWN"):
            print(f"[{spec.label} open] {sym} — NEUTRAL, işlem yok")
            continue
        # aynı saat/sembol zaten açıksa atla
        already = False
        for p in state.get("open_positions") or []:
            if p.get("symbol") == sym and p.get("entry_hour_tr") == hour_tr:
                already = True
                break
        if already:
            print(f"[{spec.label} open] {sym} — zaten açık")
            continue
        try:
            klines = await _fetch_klines(sym, "1h", 3)
            entry_price = klines[-2]["close"] if klines and len(klines) >= 2 else None
        except Exception:
            entry_price = None
        if not entry_price:
            print(f"[{spec.label} open] {sym} — fiyat yok")
            continue

        base = _trade_amount(spec, history, sym)
        amount, hot_boost, cold_cut = resolve_slot_trade_amount(base, hour_tr, history)
        slot_amount_log(spec.label, hour_tr, base, amount, hot_boost, cold_cut)

        pos, err = try_pm_open(
            state,
            label=spec.label,
            hata_file=hata,
            sym=sym,
            direction=direction,
            entry_price=float(entry_price),
            hour_tr=hour_tr,
            dow=dow,
            is_weekend=is_weekend,
            now_tr=now_tr,
            now=now,
            extra={
                "algo_name": spec.algo_name,
                "algo_num": spec.algo_num,
                "algo_signal": direction,
                "hot_hour_boost": hot_boost,
                "cold_hour_cut": cold_cut,
            },
            amount=amount,
            pm_live=True,
            min_profit_ratio=HOURLY_MIN_NET_PROFIT_RATIO,
        )
        if pos:
            save_state(spec, state)
            opened.append((sym, direction, float(entry_price), pos))
            print(f"[{spec.label} open] {short} {direction} ${amount:.2f}")
        elif err:
            print(f"[{spec.label} open] {sym} — {err}")

    if not opened:
        print(f"[{spec.label} open] {saat} — live açılan yok")
        return

    next_h = f"{(hour_tr + 1) % 24:02d}:00"
    lines = []
    for sym, direction, entry_price, pos in opened:
        name = _sym_short(sym)
        dir_icon = "📈" if direction == "UP" else "📉"
        hw, ht = get_stats(history, sym, hour_tr)
        sw, st = get_symbol_stats(history, sym)
        pm_line = pm_tg_stake(pos) or f"💵 ${pos.get('amount', spec.default_amount):.0f}"
        lines.append(
            f"{dir_icon} <b>{name}</b>  {direction}  📊 {spec.algo_name}  giriş:{entry_price:.2f}\n"
            f"   {pm_line}\n   🕐 {_wr(hw, ht)}  |  genel: {_wr(sw, st)}"
        )
    sep = "━" * 26
    tg_send(
        spec.label,
        f"{sep}\n🆕 <b>{spec.label} — {saat}-{next_h}</b>  🔴 GERÇEK PM  "
        f"{pm_live_amount_range_str(spec.amount_system)}\n"
        + "\n".join(lines)
        + f"\n{sep}\n{_pm_bal_line()}\n{sep}",
    )
    print(f"[{spec.label} open] {len(opened)} gerçek PM açıldı")


def main(spec: A2LiveSpec) -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    asyncio.run(run_close(spec) if mode == "close" else run_open(spec))
