"""B1#05 geçmişini A2#05 slotları üzerinden geriye doldurur.

A2#05'in kapanmış her işlemi bir slot (saat + sembol) sayılır. Her slotta B1#05'in
eşleme kararı **yalnızca o slotun girişinden önce kapanmış** işlemlerle verilir
(walk-forward) — yoksa sonucu bilerek en iyi motoru seçmiş olurdu.

Karar verildikten sonra yön / fiyat / sonuç, seçilen motorun o slottaki **gerçek
kaydından** alınır. Motor o slotta işlem açmamışsa slot atlanır: B1#05 de o an
sinyalsiz kalırdı.

Kayıtlar `backfill: true` ile işaretlenir, `algo_name` alanına hangi motorun
kullanıldığı yazılır (B1#05←A2#02 gibi) — böylece dashboard'daki algoritma isabet
dökümü motor bazlı çıkar.

Uyarı: havuzdaki MELEZ defterinin geçmişi de simülasyon (`backfilled`), yani
B1#05 MELEZ'i seçtiği slotlarda simülasyon üstüne simülasyon olur. Çıktıda kaç
slotta bu olduğu ayrıca raporlanır.

Kullanım:
    python3 b1_05_backfill.py            # önizleme (dosya yazmaz)
    python3 b1_05_backfill.py --write    # history + state yaz
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from b1_05_signal import (
    TARGET_SYMS, _MIN_TRADES, _load_history, book_label, source_keys,
)
from pm_trader_helpers import (
    SANAL_INITIAL_BALANCE, resolve_open_slot_gates, symbol_wr_amount_for_book,
)

_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_BOOK = "a2_05"
STATE_FILE = os.path.join(_DIR, "poly_trader_b1_05_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_b1_05_history.json")
BOOK_KEY = "b1_05"
# Simülasyon geçmişi olan defterler — raporda ayrıca sayılır
_SIMULATED = {"melez"}


def _slot(t: dict) -> tuple:
    """(saat öneki, sembol) — A2 defterleri :06, diğerleri :05 açtığı için saat bazlı."""
    return ((t.get("entry_time_tr") or "")[:13], t.get("symbol"))


def _best_for_symbol(prior: dict[str, list], sym: str,
                     min_trades: int = _MIN_TRADES) -> dict | None:
    """O ana kadarki geçmişe göre bu sembolde en yüksek WR'li defter."""
    best: dict | None = None
    for key, rows in prior.items():
        w = t = 0
        for r in rows:
            if (r.get("symbol") or "").replace("USDT", "") != sym:
                continue
            t += 1
            if r.get("win"):
                w += 1
        if t < min_trades:
            continue
        wr = round(w / t * 100, 1)
        if best is None or wr > best["wr"] or (wr == best["wr"] and t > best["t"]):
            best = {"book": key, "label": book_label(key), "wr": wr, "w": w, "t": t}
    return best


def build() -> tuple[list, dict[str, int]]:
    """(kayıtlar, atlama sebebi sayaçları)"""
    keys = source_keys()
    all_hist = {k: [t for t in _load_history(k) if t.get("win") is not None] for k in keys}

    # Slot -> defter -> kayıt
    slot_books: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for key, rows in all_hist.items():
        for t in rows:
            slot_books[_slot(t)][key] = t

    targets = [t for t in _load_history(SOURCE_BOOK) if t.get("win") is not None]
    targets.sort(key=lambda t: (t.get("entry_time_tr") or ""))

    records: list[dict] = []
    skips: dict[str, int] = defaultdict(int)
    engine_use: dict[str, int] = defaultdict(int)

    for src in targets:
        entry_ts = src.get("entry_time_tr") or ""
        sym_full = src.get("symbol") or ""
        sym = sym_full.replace("USDT", "")
        if sym not in TARGET_SYMS:
            skips["sembol kapsam dışı"] += 1
            continue

        # Walk-forward: bu slotun girişinden ÖNCE kapanmış işlemler
        prior = {
            k: [t for t in rows if (t.get("exit_time_tr") or "") < entry_ts]
            for k, rows in all_hist.items()
        }
        best = _best_for_symbol(prior, sym)
        if not best:
            skips[f"{sym}: yeterli geçmişi olan defter yok"] += 1
            continue

        rec = slot_books.get(_slot(src), {}).get(best["book"])
        if not rec:
            skips[f"{best['label']} bu slotta işlem açmamış"] += 1
            continue
        direction = rec.get("predicted_dir")
        price = rec.get("pm_entry_price")
        if direction not in ("UP", "DOWN") or not price:
            skips[f"{best['label']} yön/fiyat eksik"] += 1
            continue

        price = float(price)
        win = bool(rec.get("win"))

        # Tutar: B1#05'in o ana kadarki kendi backfill geçmişine göre
        hour_tr = src.get("entry_hour_tr")
        base = symbol_wr_amount_for_book(records, sym_full, BOOK_KEY)
        _skip, amount, hot, cold, _note = resolve_open_slot_gates(records, hour_tr, base)

        size = round(amount / price, 2) if price > 0 else 0.0
        pnl = round(size - amount, 2) if win else round(-amount, 2)
        engine_use[best["label"]] += 1

        records.append({
            "symbol":           sym_full,
            "predicted_dir":    direction,
            "actual_dir":       rec.get("actual_dir") or src.get("actual_dir"),
            "win":              win,
            "entry_price":      rec.get("entry_price") or src.get("entry_price"),
            "exit_price":       rec.get("exit_price") or src.get("exit_price"),
            "entry_time_tr":    entry_ts,
            "entry_hour_tr":    hour_tr,
            "entry_dow":        src.get("entry_dow"),
            "entry_is_weekend": src.get("entry_is_weekend"),
            "amount":           amount,
            "exit_time_tr":     src.get("exit_time_tr"),
            "pnl":              pnl,
            "algo_signal":      direction,
            "algo_name":        f"B1#05←{best['label']}",
            "algo_ok":          direction == (rec.get("actual_dir") or src.get("actual_dir")),
            "pm_spent":         amount,
            "pm_size":          size,
            "pm_entry_price":   price,
            "to_win":           size,
            "pm_slug":          rec.get("pm_slug") or src.get("pm_slug"),
            "hot_hour_boost":   hot,
            "cold_hour_cut":    cold,
            "b1_05_engine":     best["book"],
            "b1_05_engine_wr":  best["wr"],
            "b1_05_engine_n":   best["t"],
            "backfill":         True,
        })

    return records, dict(skips), dict(engine_use)


def _summary(records: list) -> None:
    n = len(records)
    if not n:
        return
    wins = sum(1 for r in records if r["win"])
    pnl = round(sum(r["pnl"] for r in records), 2)
    be = sum(r["pm_entry_price"] for r in records) / n
    print(f"\nB1#05 sonucu: {wins}/{n} kazanç (%{100*wins/n:.1f})"
          f" · başabaş %{100*be:.1f} · edge {100*wins/n - 100*be:+.1f} puan")
    print(f"PnL: {pnl:+.2f}$   Bakiye: ${SANAL_INITIAL_BALANCE:.0f} → "
          f"${SANAL_INITIAL_BALANCE + pnl:.2f}")

    print("\nMotor bazlı:")
    per: dict[str, list] = defaultdict(lambda: [0, 0, 0.0])
    for r in records:
        row = per[r["algo_name"]]
        row[1] += 1
        row[2] += r["pnl"]
        if r["win"]:
            row[0] += 1
    for name, (w, t, p) in sorted(per.items(), key=lambda kv: -kv[1][1]):
        sim = "  (simülasyon geçmişi)" if any(
            s in name.lower() for s in _SIMULATED) else ""
        print(f"  {name:22s} {w:3d}/{t:<3d} %{100*w/t:5.1f}  {p:+8.2f}${sim}")

    print("\nSembol bazlı:")
    per_sym: dict[str, list] = defaultdict(lambda: [0, 0, 0.0])
    for r in records:
        row = per_sym[r["symbol"].replace("USDT", "")]
        row[1] += 1
        row[2] += r["pnl"]
        if r["win"]:
            row[0] += 1
    for sym, (w, t, p) in per_sym.items():
        print(f"  {sym:5s} {w:3d}/{t:<3d} %{100*w/t:5.1f}  {p:+8.2f}$")


def main() -> int:
    records, skips, engines = build()
    write = "--write" in sys.argv

    n = len(records)
    pnl = round(sum(r["pnl"] for r in records), 2)
    balance = round(SANAL_INITIAL_BALANCE + pnl, 2)
    total_slots = n + sum(skips.values())

    print(f"Kaynak: {SOURCE_BOOK} geçmişi · {total_slots} slot")
    print(f"İşlem açılan: {n}  ·  atlanan: {sum(skips.values())}")
    if skips:
        print("\nAtlama sebepleri:")
        for reason, cnt in sorted(skips.items(), key=lambda kv: -kv[1]):
            print(f"  {cnt:4d}  {reason}")
    _summary(records)

    if write and records:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "balance": balance,
                "open_positions": [],
                "total_pnl": pnl,
                "backfilled_at": datetime.now().isoformat(),
                "backfill_from": records[0]["entry_time_tr"],
                "backfill_to": records[-1]["entry_time_tr"],
            }, f, indent=2, ensure_ascii=False)
        print(f"\nYazıldı: {os.path.basename(HISTORY_FILE)} ({n} kayıt), "
              f"{os.path.basename(STATE_FILE)} (bakiye ${balance:.2f})")
    elif not write:
        print("\n(önizleme — yazmak için --write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
