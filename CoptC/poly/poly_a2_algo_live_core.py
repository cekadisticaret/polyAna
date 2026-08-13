#!/usr/bin/env python3
"""A2 Top-17 — Live (gerçek PM) çekirdeği.

Sanal A2 açılışları kaynak; live sanal defterle birebir senkron (309 mirror gibi).
Cron open :07 — sanal batch (:06) bittikten sonra eksikleri tamamlar.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from poly_live_hourly_common import tg_send, try_pm_open
from poly_predictor_analysis import _fetch_klines
from poly_a2_algo_trader_core import _sym_short
from pm_trader_helpers import (
    HOURLY_MIN_NET_PROFIT_RATIO,
    pm_fetch_resolution,
    pm_get_balance,
    pm_live_amount_range_str,
    pm_live_wr_amount,
    pm_realized_pnl,
    pm_sanal_slot_candle,
    pm_tg_stake,
    resolve_slot_trade_amount,
    skip_if_weekend_pause,
    slot_amount_log,
)
from pm_balance_guard import can_open_trade, is_dashboard_live_open

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


@dataclass(frozen=True)
class A2LiveSpec:
    algo_num: int
    algo_name: str
    label: str
    amount_system: str  # analiz5_settings anahtarı (örn. a2_02)
    env_flag: str       # PM_A2_02_LIVE_ENABLED
    default_amount: float = 5.0
    # A2 dışı defterler için (B1#05 gibi). Boş bırakılırsa algo_num'dan türetilir,
    # yani mevcut A2 spec'lerinin davranışı değişmez.
    book_tag: str | None = None      # dosya öneki: poly_trader_<book_tag>_*.json
    sanal_book: str | None = None    # aynalanan sanal defter anahtarı
    sanal_label: str | None = None   # TG metninde görünen sanal defter adı
    # PM kotasyonu kapısı. `None` = kapı yok → sanal ne açtıysa aynen aynalanır.
    # Sanal defterlerde bu kapı yok; açık bırakılırsa live sanaldan sapıyor
    # (2026-08-12: sanal BTC'ye 0.725'ten girdi, live 0.77'de "profit_low" deyip
    # atladı → aynı saatte sanal 2, live 1 pozisyon). Varsayılan eski davranış.
    min_profit_ratio: float | None = HOURLY_MIN_NET_PROFIT_RATIO


def book_tag(spec: A2LiveSpec) -> str:
    return spec.book_tag or f"a2_{spec.algo_num:02d}_live"


def sanal_book(spec: A2LiveSpec) -> str:
    return spec.sanal_book or f"a2_{spec.algo_num:02d}"


def sanal_label(spec: A2LiveSpec) -> str:
    return spec.sanal_label or f"A2#{spec.algo_num:02d}"


def _paths(spec: A2LiveSpec) -> tuple[str, str, str]:
    tag = book_tag(spec)
    return (
        os.path.join(_DIR, f"poly_trader_{tag}_state.json"),
        os.path.join(_DIR, f"poly_trader_{tag}_history.json"),
        os.path.join(_DIR, f"{tag}_polyhata.json"),
    )


_LIVE_MODULE_BY_NUM: dict[int, str] = {
    2: "poly_trader_a2_02_live",
    3: "poly_trader_a2_03_live",
    4: "poly_trader_a2_04_live",
    5: "poly_trader_a2_05_live",
    6: "poly_trader_a2_06_live",
    7: "poly_trader_a2_07_live",
    8: "poly_trader_a2_08_live",
    16: "poly_trader_a2_16_live",
}


def get_live_spec(algo_num: int) -> A2LiveSpec | None:
    mod_name = _LIVE_MODULE_BY_NUM.get(algo_num)
    if not mod_name:
        return None
    import importlib
    mod = importlib.import_module(mod_name)
    return getattr(mod, "SPEC", None)


def _pm_enabled(spec: A2LiveSpec) -> bool:
    """Dashboard Live anahtarı tek otorite; .env bayrağı yedek (geriye uyumluluk)."""
    if is_dashboard_live_open(spec.label):
        return True
    return os.getenv(spec.env_flag, "false").lower() in ("1", "true", "yes")


def is_live_active(spec: A2LiveSpec) -> bool:
    if not _pm_enabled(spec):
        return False
    return can_open_trade(spec.label, lambda t: tg_send(spec.label, t))


def _sanal_state_path(spec_or_num: "A2LiveSpec | int") -> str:
    key = (sanal_book(spec_or_num) if isinstance(spec_or_num, A2LiveSpec)
           else f"a2_{int(spec_or_num):02d}")
    return os.path.join(_DIR, f"poly_trader_{key}_state.json")


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


def _resolve_pm(pos: dict, *, now_hour: int):
    """PM sonuç — slot bitmişse gevşek eşik, o da yoksa Binance mum yedeği.

    Gamma bazen saat bitince uzun süre mid-price (örn. 0.75) tutuyor;
    closed=False iken 0.99 eşiği hiç geçmiyor. Slot bitmişse:
      1) 0.90 eşiği
      2) Binance 1h slot mumu (sanal settle ile aynı) — defteri kilitlemez
    """
    slug = pos.get("pm_slug")
    if not slug:
        return None
    res = pm_fetch_resolution(slug)
    if res is not None:
        return res
    entry_h = pos.get("entry_hour_tr")
    slot_ended = entry_h is not None and int(entry_h) != int(now_hour)
    if not slot_ended:
        return None
    res = pm_fetch_resolution(slug, min_decisive=0.90)
    if res is not None:
        return res
    candle = pm_sanal_slot_candle(pos.get("symbol") or "", pos.get("entry_time_tr") or "")
    if not candle:
        return None
    hour_open, hour_close = candle
    up_won = hour_close >= hour_open
    print(
        f"[A2 live] {pos.get('symbol')} PM kesin değil → Binance yedek "
        f"{'UP' if up_won else 'DOWN'} ({hour_open:.2f}→{hour_close:.2f})"
    )
    return {
        "up_won": up_won,
        "closed": False,
        "up_price": 1.0 if up_won else 0.0,
        "down_price": 0.0 if up_won else 1.0,
        "title": "binance_fallback",
        "source": "binance_slot",
    }


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
    pending = []
    tur_pnl = 0.0
    failed = []
    for pos in list(state["open_positions"]):
        sym = pos["symbol"]
        klines = await _fetch_klines(sym, "1h", 2)
        if not klines:
            failed.append(pos)
            pending.append(f"{_sym_short(sym)} (kline yok)")
            continue
        current_price = klines[-1]["close"]
        entry = pos["entry_price"]
        pred = pos["predicted_dir"]
        amount = pos.get("amount", spec.default_amount)
        has_pm = bool(pos.get("pm_slug") and pos.get("pm_order_id"))
        if has_pm:
            res = _resolve_pm(pos, now_hour=now_tr.hour)
            if res is None:
                failed.append(pos)
                pending.append(
                    f"{_sym_short(sym)} h={pos.get('entry_hour_tr')} "
                    f"(PM sonuç henüz kesin değil)"
                )
                continue
            token_dir = pos.get("pm_token_dir") or pred
            win = (token_dir == "UP" and res["up_won"]) or (token_dir == "DOWN" and not res["up_won"])
            actual = "UP" if res["up_won"] else "DOWN"
            pnl = pm_realized_pnl(pos, win)
            settle_src = res.get("source") or "pm"
        else:
            actual = "UP" if current_price >= entry else "DOWN"
            win = pred == actual
            pm_spent = float(pos.get("pm_spent") or amount)
            pm_size = float(pos.get("pm_size") or 0)
            pnl = round(pm_size - pm_spent, 2) if win and pm_size else round(-pm_spent, 2)
            settle_src = "no_pm"
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
            "pm_slug": pos.get("pm_slug"),
            "algo_name": pos.get("algo_name", spec.algo_name),
            "algo_num": spec.algo_num,
            "settle_source": settle_src if has_pm else "no_pm",
        })
        name = _sym_short(sym)
        lines.append(f"{'✅' if win else '❌'} {name}  {pred}  net {'+' if pnl >= 0 else ''}{pnl:.2f}$")

    state["open_positions"] = failed
    save_state(spec, state)
    save_history(spec, history)
    if pending:
        print(f"[{spec.label} close] {len(pending)} pozisyon bekliyor: {', '.join(pending)}")
    if not lines:
        return
    print(f"[{spec.label} close] {len(lines)} pozisyon kapatıldı")
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
        min_profit_ratio=spec.min_profit_ratio,
    )
    if pos:
        save_state(spec, state)
        name = _sym_short(sym)
        print(
            f"[{spec.label} mirror] {name} {direction} ${amount:.2f} "
            f"(sanal {sanal_label(spec)})"
        )
    return pos, err


async def sync_open_from_sanal_state(spec: A2LiveSpec) -> list[tuple[str, str, float, dict]]:
    """Sanal defterdeki tüm açık pozisyonları live'a yansıt."""
    if not is_live_active(spec):
        print(f"[{spec.label} sync] live kapalı — atlandı")
        return []

    spath = _sanal_state_path(spec)
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
    """Live open — sanal defterle senkron (bağımsız sinyal yok)."""
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    if skip_if_weekend_pause(spec.label, "open", now_tr):
        return
    if not _pm_enabled(spec):
        print(f"[{spec.label} open] dashboard kapalı ({spec.amount_system}) — atlandı")
        return

    saat = now_tr.strftime("%H:%M")
    hour_tr = now_tr.hour
    history = load_history(spec)
    opened = await sync_open_from_sanal_state(spec)

    if not opened:
        sanal_n = 0
        spath = _sanal_state_path(spec)
        if os.path.exists(spath):
            try:
                with open(spath, encoding="utf-8") as f:
                    sanal_n = len(json.load(f).get("open_positions") or [])
            except Exception:
                pass
        print(
            f"[{spec.label} open] {saat} — live açılan yok"
            + (f" (sanal {sanal_n} açık)" if sanal_n else "")
        )
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
        + f"\n(sanal {sanal_label(spec)} ile aynı)\n"
        + f"{sep}\n{_pm_bal_line()}\n{sep}",
    )
    print(f"[{spec.label} open] {len(opened)} açıldı (sanal sync)")


def main(spec: A2LiveSpec) -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    asyncio.run(run_close(spec) if mode == "close" else run_open(spec))
