"""A2#05 X A6V3 MELEZ geçmişini mevcut defterlerin gerçek kararlarından yeniden kur.

Melezin motorları zaten canlı defterlerde çalışıyor:
  BTC  → A6V3 defterindeki BTC işlemleri  (MACD Div #26)
  ETH  → A2#05 defterindeki ETH işlemleri (Mean Reversion)
  SOL  → A2#05 defterindeki SOL işlemleri (Mean Reversion)

Yön/sonuç kayıtları oradan alınır; tutar ve P&L A6V4'ün kendi WR kademesiyle
kronolojik (walk-forward) yeniden hesaplanır — geleceğe bakma yok.

Kullanım: python3 temmuzPoly/analiz6_v4_backfill.py [--write]
"""
from __future__ import annotations

import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from pm_trader_helpers import (  # noqa: E402
    SANAL_INITIAL_BALANCE,
    pm_hourly_profit_entry_ok,
    resolve_open_slot_gates,
    symbol_wr_amount_for_book,
)

BOOK_KEY = "melez"
ALGO_NAME = "BTC→MACD Div · ETH/SOL→Mean Rev"
STATE_FILE = os.path.join(_DIR, "poly_trader_analiz6_v4_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_analiz6_v4_history.json")

# sembol → (kaynak defter, motor adı)
SOURCES = {
    "BTCUSDT": ("poly_trader_analiz6_v3_history.json", "MACD Hist. Div"),
    "ETHUSDT": ("poly_trader_a2_05_history.json", "Mean Reversion Z"),
    "SOLUSDT": ("poly_trader_a2_05_history.json", "Mean Reversion Z"),
}


def _load(name: str) -> list:
    path = os.path.join(_DIR, name)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def collect() -> list[dict]:
    """Kaynak defterlerden A6V4'ün göreceği kararları topla."""
    out = []
    for sym, (fname, engine) in SOURCES.items():
        for t in _load(fname):
            if t.get("symbol") != sym:
                continue
            if t.get("predicted_dir") not in ("UP", "DOWN"):
                continue
            if t.get("actual_dir") not in ("UP", "DOWN"):
                continue
            out.append({**t, "_engine": engine})
    out.sort(key=lambda t: t.get("entry_time_tr") or "")
    return out


def rebuild(candidates: list[dict]) -> tuple[list[dict], dict]:
    history: list[dict] = []
    balance = float(SANAL_INITIAL_BALANCE)
    total_pnl = 0.0
    skipped = 0

    for src in candidates:
        sym = src["symbol"]
        hour_tr = src.get("entry_hour_tr")
        if hour_tr is None:
            skipped += 1
            continue

        base_amt = symbol_wr_amount_for_book(history, sym, BOOK_KEY)
        _, amount, hot_boost, cold_cut, _ = resolve_open_slot_gates(history, hour_tr, base_amt)

        token_price = float(src.get("pm_entry_price") or 0)
        if token_price <= 0:
            skipped += 1
            continue
        spent = round(amount, 2)
        size = round(spent / token_price, 2)
        probe = {
            "pm_spent": spent,
            "pm_size": size,
            "pm_entry_price": token_price,
            "pm_slug": src.get("pm_slug") or "backfill",
        }
        ok, _msg = pm_hourly_profit_entry_ok(probe)
        if not ok:
            skipped += 1
            continue

        win = bool(src.get("win"))
        pnl = round(size - spent, 2) if win else round(-spent, 2)
        balance = round(balance - spent + (size if win else 0.0), 2)
        total_pnl = round(total_pnl + pnl, 2)

        history.append({
            "symbol": sym,
            "predicted_dir": src["predicted_dir"],
            "actual_dir": src["actual_dir"],
            "win": win,
            "entry_price": src.get("entry_price"),
            "exit_price": src.get("exit_price"),
            "entry_time_tr": src.get("entry_time_tr"),
            "entry_hour_tr": hour_tr,
            "entry_dow": src.get("entry_dow"),
            "entry_is_weekend": src.get("entry_is_weekend"),
            "amount": spent,
            "exit_time_tr": src.get("exit_time_tr"),
            "pnl": pnl,
            "algo_signal": src["predicted_dir"],
            "algo_name": src["_engine"],
            "algo_ok": src["predicted_dir"] == src["actual_dir"],
            "hot_hour_boost": hot_boost,
            "cold_hour_cut": cold_cut,
            "pm_spent": spent,
            "pm_size": size,
            "pm_entry_price": token_price,
            "to_win": size,
            "pm_slug": src.get("pm_slug"),
            "backfilled": True,
        })

    state = {
        "balance": balance,
        "open_positions": [],
        "total_pnl": total_pnl,
    }
    if skipped:
        print(f"  atlanan (kotasyon yok / kâr eşiği): {skipped}")
    return history, state


def report(history: list[dict], state: dict) -> None:
    n = len(history)
    if not n:
        print("kayıt yok")
        return
    wins = sum(1 for t in history if t["win"])
    risk = sum(t["pm_spent"] for t in history)
    print(f"\n=== A2#05 X A6V3 MELEZ backfill — {n} işlem ===")
    print(f"  WR       : %{100*wins/n:.1f} ({wins}/{n})")
    print(f"  P&L      : {state['total_pnl']:+.2f}$   ROI: {100*state['total_pnl']/risk:+.2f}%")
    print(f"  Bakiye   : ${state['balance']:.2f}  (başlangıç ${SANAL_INITIAL_BALANCE})")
    print(f"  Dönem    : {history[0]['entry_time_tr'][:16]} → {history[-1]['entry_time_tr'][:16]}")
    for sym in SOURCES:
        g = [t for t in history if t["symbol"] == sym]
        if not g:
            continue
        w = sum(1 for t in g if t["win"])
        p = sum(t["pnl"] for t in g)
        up = [t for t in g if t["predicted_dir"] == "UP"]
        dn = [t for t in g if t["predicted_dir"] == "DOWN"]
        bal = ""
        if up and dn:
            b = (100 * sum(1 for t in up if t["win"]) / len(up)
                 + 100 * sum(1 for t in dn if t["win"]) / len(dn)) / 2
            bal = f" dengeli=%{b:.1f}"
        print(f"    {sym:9} n={len(g):4} WR=%{100*w/len(g):5.1f}{bal}  pnl={p:+8.2f}")


if __name__ == "__main__":
    cands = collect()
    print(f"kaynak kararlar: {len(cands)}")
    hist, st = rebuild(cands)
    report(hist, st)
    if "--write" in sys.argv:
        with open(HISTORY_FILE, "w") as f:
            json.dump(hist, f, indent=2, ensure_ascii=False)
        with open(STATE_FILE, "w") as f:
            json.dump(st, f, indent=2, ensure_ascii=False)
        print(f"\nyazıldı → {os.path.basename(HISTORY_FILE)} · {os.path.basename(STATE_FILE)}")
    else:
        print("\n(kuru çalışma — yazmak için --write)")
