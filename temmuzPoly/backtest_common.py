"""Walk-forward backtest ortak motoru — canlı trader dosyalarına dokunulmaz."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

import poly_predictor_analysis as pa
from backtest_analiz2 import fetch_klines_history, _neutral_preloaded
from poly_a2_algo_trader_core import entry_zscore

_TZ_TR = ZoneInfo("Europe/Istanbul")
TOKEN_SIM = 0.50

ApplyPmFn = Callable[[dict, str, str, float, list, dict], bool] | None
ResolvePnlFn = Callable[[dict, bool], float] | None

SignalFn = Callable[..., dict | None] | Callable[..., Awaitable[dict | None]]


@dataclass
class Trade:
    entry_time: str
    exit_time: str
    symbol: str
    predicted_dir: str
    actual_dir: str
    win: bool
    entry_price: float
    exit_price: float
    amount: float
    pnl: float
    balance_after: float
    extra: dict | None = None


def apply_synthetic_pm(pos: dict, amount: float) -> None:
    pos["pm_spent"] = amount
    pos["pm_size"] = round(amount / TOKEN_SIM, 2)
    pos["pm_entry_price"] = TOKEN_SIM
    pos["to_win"] = pos["pm_size"]


def resolve_pnl(pos: dict, win: bool) -> float:
    spent = float(pos.get("pm_spent") or pos.get("amount") or 0)
    size = float(pos.get("pm_size") or 0)
    if size > 0 and spent > 0:
        return round(size - spent, 2) if win else round(-spent, 2)
    return round(-spent, 2) if not win else 0.0


def to_a4_klines(kslice: list[dict]) -> list[dict]:
    return [{
        "open": k["open"], "high": k["high"], "low": k["low"],
        "close": k["close"], "volume": k["volume"],
    } for k in kslice]


def to_algo21_klines(kslice: list[dict]) -> list[dict]:
    return [{
        "o": k["open"], "h": k["high"], "l": k["low"],
        "c": k["close"], "v": k["volume"],
    } for k in kslice]


NEUTRAL_OB = {
    "bids": [["50000.0", "100.0"], ["49999.0", "100.0"]],
    "asks": [["50001.0", "100.0"], ["50002.0", "100.0"]],
}


async def run_walk_forward(
    label: str,
    symbols: list[str],
    signal_fn: SignalFn,
    start_date: datetime,
    initial_balance: float = 1000.0,
    end_date: datetime | None = None,
    min_bars: int = 60,
    amount_fn: Callable[[list[Trade], str], float] | None = None,
    apply_pm_fn: ApplyPmFn = None,
    resolve_pnl_fn: ResolvePnlFn = None,
    min_entry_price: float | None = None,
    exclude_price_band: tuple[float, float] | None = None,
    z_gate: tuple[float, float] | None = None,
) -> dict:
    end = end_date or datetime.now(timezone.utc)
    fetch_start = start_date - timedelta(days=8)
    test_start_ms = int(start_date.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    warmup = min_bars

    bars_by_sym: dict[str, list[dict]] = {}
    for sym in symbols:
        print(f"[{label}] Veri: {sym} 1h...")
        bars = await fetch_klines_history(sym, "1h", int(fetch_start.timestamp() * 1000), end_ms)
        if len(bars) < min_bars + 10:
            raise RuntimeError(f"Yetersiz veri {sym}: {len(bars)}")
        bars_by_sym[sym] = bars

    min_len = min(len(b) for b in bars_by_sym.values())
    balance = initial_balance
    total_pnl = 0.0
    history: list[Trade] = []
    open_pos: dict[str, dict] = {}
    skipped = 0

    for i in range(warmup, min_len - 1):
        if bars_by_sym[symbols[0]][i]["open_time"] < test_start_ms and not open_pos:
            nxt = bars_by_sym[symbols[0]][i + 1]["open_time"]
            if nxt < test_start_ms:
                continue

        for sym in symbols:
            pos = open_pos.get(sym)
            if pos is None or pos["settle_idx"] != i:
                continue
            bar = bars_by_sym[sym][i]
            entry = pos["entry_price"]
            exit_p = bar["close"]
            pred = pos["predicted_dir"]
            actual = "UP" if exit_p >= entry else "DOWN"
            win = pred == actual
            pnl = resolve_pnl_fn(pos, win) if resolve_pnl_fn else resolve_pnl(pos, win)
            balance = round(balance + pnl, 2)
            total_pnl = round(total_pnl + pnl, 2)

            ts_open = datetime.fromtimestamp(pos["open_ms"] / 1000, tz=timezone.utc)
            ts_close = datetime.fromtimestamp(bar["open_time"] / 1000 + 3600, tz=timezone.utc)
            if ts_open.timestamp() >= start_date.timestamp():
                history.append(Trade(
                    entry_time=ts_open.astimezone(_TZ_TR).isoformat(),
                    exit_time=ts_close.astimezone(_TZ_TR).isoformat(),
                    symbol=sym,
                    predicted_dir=pred,
                    actual_dir=actual,
                    win=win,
                    entry_price=entry,
                    exit_price=exit_p,
                    amount=pos["amount"],
                    pnl=pnl,
                    balance_after=balance,
                    extra=pos.get("extra"),
                ))
            del open_pos[sym]

        if i + 1 >= min_len:
            continue
        if bars_by_sym[symbols[0]][i + 1]["open_time"] < test_start_ms:
            continue

        open_ms = bars_by_sym[symbols[0]][i + 1]["open_time"] + 5 * 60 * 1000

        for sym in symbols:
            if sym in open_pos:
                continue
            bars = bars_by_sym[sym]
            kslice = bars[max(0, i - 199): i + 1]
            if len(kslice) < min_bars:
                continue

            raw = signal_fn(sym, kslice, open_ms, history, amount_fn, bars[i + 1])
            sig = await raw if asyncio.iscoroutine(raw) else raw
            if sig is None:
                skipped += 1
                continue

            amount = sig.get("amount")
            if amount_fn and amount is None:
                amount = amount_fn(history, sym)
            if not amount or amount <= 0:
                skipped += 1
                continue

            pos = {
                "symbol": sym,
                "predicted_dir": sig["predicted_dir"],
                "entry_price": sig.get("entry_price", bars[i]["close"]),
                "amount": amount,
                "settle_idx": i + 1,
                "open_ms": open_ms,
                "extra": sig.get("extra"),
            }
            next_bar = bars[i + 1]
            if apply_pm_fn:
                if not apply_pm_fn(pos, sym, sig["predicted_dir"], amount, kslice, next_bar):
                    skipped += 1
                    continue
                ep = float(pos.get("pm_entry_price") or 0)
                if min_entry_price is not None and ep < min_entry_price:
                    skipped += 1
                    continue
                if exclude_price_band is not None:
                    _lo, _hi = exclude_price_band
                    if _lo <= ep < _hi:
                        skipped += 1
                        continue
            else:
                apply_synthetic_pm(pos, amount)
            if z_gate is not None:
                _z = entry_zscore(kslice)
                _zlo, _zhi = z_gate
                if _z is None or not (_zlo <= abs(_z) < _zhi):
                    skipped += 1
                    continue
            open_pos[sym] = pos

    pa._slot_utc_ms = None

    wins = sum(1 for t in history if t.win)
    total = len(history)
    monthly: dict[str, float] = {}
    sym_stats: dict[str, dict] = {}
    for t in history:
        mk = t.entry_time[:7]
        monthly[mk] = round(monthly.get(mk, 0) + t.pnl, 2)
        s = sym_stats.setdefault(t.symbol, {"w": 0, "n": 0, "pnl": 0.0})
        s["n"] += 1
        s["pnl"] = round(s["pnl"] + t.pnl, 2)
        if t.win:
            s["w"] += 1

    peak = initial_balance
    max_dd = 0.0
    for t in history:
        peak = max(peak, t.balance_after)
        dd = (peak - t.balance_after) / peak * 100 if peak else 0
        max_dd = max(max_dd, dd)

    first = history[0].entry_time[:10] if history else "—"
    last = history[-1].entry_time[:10] if history else "—"

    return {
        "label": label,
        "symbols": symbols,
        "period": f"{first} → {last}",
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "total_pnl": round(total_pnl, 2),
        "trades": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate_pct": round(wins / total * 100, 1) if total else 0.0,
        "max_drawdown_pct": round(max_dd, 1),
        "skipped_signals": skipped,
        "monthly_pnl": monthly,
        "by_symbol": {
            k: {
                "trades": v["n"],
                "wins": v["w"],
                "win_rate_pct": round(v["w"] / v["n"] * 100, 1) if v["n"] else 0,
                "pnl": v["pnl"],
            }
            for k, v in sym_stats.items()
        },
        "trade_list": [asdict(t) for t in history],
    }


def print_summary(r: dict) -> None:
    print("\n" + "=" * 52)
    print(f"  {r['label']} BACKTEST")
    print("=" * 52)
    print(f"  Dönem      : {r['period']}")
    print(f"  İşlem      : {r['trades']} ({r['wins']}W / {r['losses']}L)")
    print(f"  Win rate   : {r['win_rate_pct']}%")
    print(f"  P&L        : {'+' if r['total_pnl']>=0 else ''}${r['total_pnl']:.2f}")
    print(f"  Bakiye     : ${r['initial_balance']:.0f} → ${r['final_balance']:.2f}")
    print(f"  Max DD     : {r['max_drawdown_pct']}%")
    print(f"  Atlanan    : {r['skipped_signals']}")
    for sym, st in r["by_symbol"].items():
        name = sym.replace("USDT", "")
        print(f"  {name:4s}       : {st['trades']} işlem  WR {st['win_rate_pct']}%  "
              f"P&L {'+' if st['pnl']>=0 else ''}${st['pnl']:.0f}")
    print("\n  Aylık P&L:")
    for m, p in sorted(r["monthly_pnl"].items()):
        print(f"    {m}: {'+' if p>=0 else ''}${p:.2f}")
    print("=" * 52)
