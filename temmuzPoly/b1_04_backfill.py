"""B1#04 geçmişini A2#05 slotları üzerinden geriye doldurur.

A2#05'in belirtilen tarihten sonra girdiği her slotta (saat + sembol) B1#04'ün
karar mantığını çalıştırır. Karar her slotta **yalnızca o slottan önce kapanmış**
işlemlerle verilir (walk-forward) — aksi halde sonucu bilerek karar vermiş olurdu.

Yön, fiyat ve kazanç/kayıp gerçek defter kayıtlarından alınır; tutar ve PnL
gerçek trader'ın kullandığı fonksiyonlarla hesaplanır. Kayıtlar `backfill: true`
ile işaretlenir.

Kullanım:
    python3 b1_04_backfill.py            # önizleme (dosya yazmaz)
    python3 b1_04_backfill.py --write    # history + state yaz
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import b1_04_signal as S
from pm_trader_helpers import (
    SANAL_INITIAL_BALANCE, resolve_open_slot_gates, symbol_wr_amount_for_book,
)

_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_BOOK = "a2_05"
# Ekranda 08-10 02:02 kapanışı görünen işlemler dahil (giriş bir saat önce)
FROM_EXIT = "2026-08-10T02:00"
STATE_FILE = os.path.join(_DIR, "poly_trader_b1_04_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_b1_04_history.json")
ALGO_NAME = "Edge-ağırlıklı küme konsensüsü"


def _load(key: str) -> list:
    path = os.path.join(_DIR, f"poly_trader_{key}_history.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _slot(t: dict) -> tuple:
    return ((t.get("entry_time_tr") or "")[:13], t.get("symbol"))


def build() -> tuple[list, list]:
    """(kayıtlar, atlanan slot notları)"""
    voters = S.voter_keys()
    all_hist = {k: _load(k) for k in voters}

    # Slot -> defter -> kayıt (yön/fiyat/sonuç aramak için)
    slot_books: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for key, rows in all_hist.items():
        for t in rows:
            if t.get("win") is None:
                continue
            slot_books[_slot(t)][key] = t

    # Hedef slotlar: A2#05'in FROM_EXIT sonrası kapanan işlemleri
    targets = [
        t for t in _load(SOURCE_BOOK)
        if t.get("win") is not None and (t.get("exit_time_tr") or "") >= FROM_EXIT
    ]
    targets.sort(key=lambda t: (t.get("entry_time_tr") or ""))

    records: list[dict] = []
    skipped: list[str] = []

    for src in targets:
        entry_ts = src.get("entry_time_tr") or ""
        sym = src.get("symbol")
        slot = _slot(src)

        # ---- Walk-forward: yalnızca bu slotun girişinden ÖNCE kapanmış işlemler
        prior = {
            k: [t for t in rows if (t.get("exit_time_tr") or "") < entry_ts]
            for k, rows in all_hist.items()
        }
        edges = _edges_from(prior)
        clusters = _clusters_from(prior)

        # ---- Oylar: bu slotta defterlerin fiilen kaydettiği yönler
        votes = []
        for key, rec in slot_books.get(slot, {}).items():
            d = rec.get("predicted_dir")
            if d in ("UP", "DOWN"):
                votes.append({"key": key, "label": S.book_label(key), "dir": d,
                              "price": rec.get("pm_entry_price"), "algo": key})
        if not votes:
            skipped.append(f"{entry_ts[:16]} {sym}: oy yok")
            continue

        score = S.score_votes(votes, edges, clusters)
        if not score["passes"]:
            skipped.append(
                f"{entry_ts[:16]} {sym}: eşik altı (net {score['net']:+.3f})"
            )
            continue

        direction = score["direction"]

        # ---- Gerçek fiyat + sonuç: o yönde işlem açmış bir defterden
        price = win = None
        for key, rec in slot_books.get(slot, {}).items():
            if rec.get("predicted_dir") == direction and rec.get("pm_entry_price"):
                price, win = float(rec["pm_entry_price"]), bool(rec["win"])
                break
        if price is None:
            # O yönde defter yok → karşı yönün simetriği
            if not src.get("pm_entry_price"):
                skipped.append(f"{entry_ts[:16]} {sym}: fiyat yok")
                continue
            price = round(1.0 - float(src["pm_entry_price"]), 3)
            win = not bool(src["win"])

        # ---- Tutar: B1#04'ün o ana kadarki kendi geçmişine göre
        hour_tr = src.get("entry_hour_tr")
        base = symbol_wr_amount_for_book(records, sym, "b1_04")
        _skip, amount, hot, cold, _n = resolve_open_slot_gates(records, hour_tr, base)

        size = round(amount / price, 2) if price > 0 else 0.0
        pnl = round(size - amount, 2) if win else round(-amount, 2)

        records.append({
            "symbol":           sym,
            "predicted_dir":    direction,
            "actual_dir":       src.get("actual_dir"),
            "win":              bool(win),
            "entry_price":      src.get("entry_price"),
            "exit_price":       src.get("exit_price"),
            "entry_time_tr":    entry_ts,
            "entry_hour_tr":    hour_tr,
            "entry_dow":        src.get("entry_dow"),
            "entry_is_weekend": src.get("entry_is_weekend"),
            "amount":           amount,
            "exit_time_tr":     src.get("exit_time_tr"),
            "pnl":              pnl,
            "algo_signal":      direction,
            "algo_name":        ALGO_NAME,
            "algo_ok":          direction == src.get("actual_dir"),
            "pm_spent":         amount,
            "pm_size":          size,
            "pm_entry_price":   price,
            "to_win":           size,
            "pm_slug":          src.get("pm_slug"),
            "hot_hour_boost":   hot,
            "cold_hour_cut":    cold,
            "consensus_net":    score["net"],
            "backfill":         True,
        })

    return records, skipped


def _edges_from(prior: dict[str, list]) -> dict[str, dict]:
    out = {}
    for key, rows in prior.items():
        rows = [t for t in rows if t.get("pm_entry_price")]
        if len(rows) < S._MIN_TRADES:
            continue
        rows = sorted(rows, key=lambda t: t.get("entry_time_tr") or "")[-S._EDGE_WINDOW:]
        n = len(rows)
        wins = sum(1 for t in rows if t.get("win"))
        be = sum(float(t["pm_entry_price"]) for t in rows) / n
        edge = S._shrunk_rate(wins, n, be) - be
        out[key] = {"label": S.book_label(key), "n": n, "edge": round(edge, 4),
                    "weight": round(max(0.0, edge), 4)}
    return out


def _clusters_from(prior: dict[str, list]) -> dict[str, str]:
    slots: dict[tuple, dict[str, str]] = defaultdict(dict)
    for key, rows in prior.items():
        for t in rows:
            d = t.get("predicted_dir")
            if d in ("UP", "DOWN"):
                slots[_slot(t)][key] = d
    agree: dict[tuple, list] = defaultdict(lambda: [0, 0])
    for books in slots.values():
        ks = sorted(books)
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                a, b = ks[i], ks[j]
                agree[(a, b)][0] += 1
                if books[a] == books[b]:
                    agree[(a, b)][1] += 1
    parent = {k: k for k in prior}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b), (n, same) in agree.items():
        if n < S._CLUSTER_MIN_OVERLAP or same / n < S._AGREE_CLUSTER:
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return {k: find(k) for k in parent}


def main() -> int:
    records, skipped = build()
    write = "--write" in sys.argv

    n = len(records)
    wins = sum(1 for r in records if r["win"])
    pnl = round(sum(r["pnl"] for r in records), 2)
    balance = round(SANAL_INITIAL_BALANCE + pnl, 2)

    print(f"Kaynak: {SOURCE_BOOK} · {FROM_EXIT} sonrası")
    print(f"Değerlendirilen slot: {n + len(skipped)}  →  işlem açılan: {n}, atlanan: {len(skipped)}")
    if n:
        be = sum(r["pm_entry_price"] for r in records) / n
        print(f"\nB1#04 sonucu: {wins}/{n} kazanç (%{100*wins/n:.1f})"
              f" · başabaş %{100*be:.1f} · edge {100*wins/n - 100*be:+.1f} puan")
        print(f"PnL: {pnl:+.2f}$   Bakiye: ${SANAL_INITIAL_BALANCE:.0f} → ${balance:.2f}")

    if write and records:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        last = records[-1]
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "balance": balance,
                "open_positions": [],
                "total_pnl": pnl,
                "backfilled_at": datetime.now().isoformat(),
                "backfill_from": last["entry_time_tr"],
            }, f, indent=2, ensure_ascii=False)
        print(f"\nYazıldı: {os.path.basename(HISTORY_FILE)} ({n} kayıt), "
              f"{os.path.basename(STATE_FILE)} (bakiye ${balance:.2f})")
    elif not write:
        print("\n(önizleme — yazmak için --write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
