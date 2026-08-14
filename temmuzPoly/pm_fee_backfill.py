#!/usr/bin/env python3
"""PM taker ücretini geçmiş defterlere işler.

Polymarket bu piyasalarda `fee = C × 0.07 × p × (1−p)` taker ücreti alıyor
(Gamma: feeType=crypto_fees_v2). Defterler bugüne kadar ücreti hiç düşmedi,
dolayısıyla kayıtlı P&L olduğundan yüksek görünüyordu.

Betik her kapalı işlemin ücretini giriş kotasyonundan hesaplar, `pm_fee`
alanına yazar ve `pnl`'i o kadar düşürür. Bakiye sıfırdan kurulmaz —
yalnızca toplam ücret kadar azaltılır, böylece geçmiş reset'ler bozulmaz.

Giriş fiyatı geçmişte Gamma mid'inden alınmıştı; gerçek ask geriye dönük
bilinemeyeceği için kayıtlı fiyata dokunulmaz. Spread farkı yalnız bundan
sonraki işlemlerde giderilir (pm_sanal_quote artık CLOB ask kullanıyor).

Kullanım:
    python3 temmuzPoly/pm_fee_backfill.py            # kuru çalışma (rapor)
    python3 temmuzPoly/pm_fee_backfill.py --apply    # yaz
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pm_trader_helpers import pm_taker_fee  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Europe/Istanbul")
BACKUP_DIR = os.path.join(BASE, "_fee_backfill_backup")


def _fee_for(trade: dict) -> float:
    spent = float(trade.get("pm_spent") or 0)
    price = float(trade.get("pm_entry_price") or trade.get("token_price") or 0)
    size = float(trade.get("pm_size") or trade.get("to_win") or 0)
    if spent <= 0 or not (0.0 < price < 1.0):
        return 0.0
    if size <= 0:
        size = spent / price
    return pm_taker_fee(size, price)


def process_book(hist_path: str, apply: bool) -> dict | None:
    key = os.path.basename(hist_path).replace("_history.json", "")
    state_path = os.path.join(BASE, f"{key}_state.json")
    try:
        history = json.load(open(hist_path))
    except Exception as e:
        print(f"  ! {key}: geçmiş okunamadı ({e})", file=sys.stderr)
        return None
    if not isinstance(history, list) or not history:
        return None

    total_fee = 0.0
    touched = 0
    skipped = 0
    for t in history:
        if not isinstance(t, dict):
            continue
        if t.get("pm_fee") is not None:
            skipped += 1
            continue
        fee = _fee_for(t)
        if fee <= 0:
            continue
        t["pm_fee"] = fee
        t["pnl"] = round(float(t.get("pnl") or 0) - fee, 2)
        total_fee += fee
        touched += 1

    # Açık pozisyonlara da ücreti işaretle — kapanışta iki kez düşülmesin diye
    # sanal_pnl kayıtlı değeri kullanır.
    state = None
    open_marked = 0
    if os.path.exists(state_path):
        try:
            state = json.load(open(state_path))
        except Exception as e:
            print(f"  ! {key}: state okunamadı ({e})", file=sys.stderr)
            state = None
    if state is not None:
        for p in state.get("open_positions") or []:
            if isinstance(p, dict) and p.get("pm_fee") is None:
                fee = _fee_for(p)
                if fee > 0:
                    p["pm_fee"] = fee
                    open_marked += 1

    if touched == 0 and open_marked == 0:
        return None

    # balance == 0.0 olan defterler canlı aynalar: bakiye yer tutucu, gerçek para
    # PM cüzdanında. Onlarda yalnız total_pnl düzeltilir.
    placeholder = state is not None and float(state.get("balance") or 0) == 0.0

    row = {
        "key": key,
        "trades": len(history),
        "touched": touched,
        "skipped": skipped,
        "open_marked": open_marked,
        "fee": round(total_fee, 2),
        "bal_before": None,
        "bal_after": None,
        "placeholder": placeholder,
    }
    if state is not None:
        bal = float(state.get("balance") or 0)
        row["bal_before"] = round(bal, 2)
        row["bal_after"] = bal if placeholder else round(bal - total_fee, 2)

    if not apply:
        return row

    os.makedirs(BACKUP_DIR, exist_ok=True)
    shutil.copy2(hist_path, os.path.join(BACKUP_DIR, os.path.basename(hist_path)))
    with open(hist_path, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    if state is not None:
        shutil.copy2(state_path, os.path.join(BACKUP_DIR, os.path.basename(state_path)))
        if not placeholder:
            state["balance"] = round(float(state.get("balance") or 0) - total_fee, 2)
        state["total_pnl"] = round(float(state.get("total_pnl") or 0) - total_fee, 2)
        state["fee_backfill_at"] = datetime.now(TZ).isoformat()
        state["fee_backfill_total"] = round(total_fee, 2)
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="değişiklikleri yaz")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(BASE, "*_history.json")))
    rows = []
    for p in paths:
        r = process_book(p, args.apply)
        if r:
            rows.append(r)

    rows.sort(key=lambda r: -r["fee"])
    mode = "UYGULANDI" if args.apply else "KURU ÇALIŞMA (yazılmadı)"
    print(f"PM taker ücreti geri doldurma — {mode}\n")
    print(f"{'defter':24s} {'işlem':>6s} {'işlenen':>8s} {'ücret $':>9s} "
          f"{'bakiye önce':>12s} {'bakiye sonra':>13s}")
    print("-" * 78)
    for r in rows:
        b0 = f"{r['bal_before']:.2f}" if r["bal_before"] is not None else "-"
        b1 = f"{r['bal_after']:.2f}" if r["bal_after"] is not None else "-"
        print(f"{r['key'][:24]:24s} {r['trades']:>6d} {r['touched']:>8d} "
              f"{r['fee']:>9.2f} {b0:>12s} {b1:>13s}")
    print("-" * 78)
    print(f"{'TOPLAM':24s} {sum(r['trades'] for r in rows):>6d} "
          f"{sum(r['touched'] for r in rows):>8d} {sum(r['fee'] for r in rows):>9.2f}")
    marked = sum(r["open_marked"] for r in rows)
    if marked:
        print(f"\nAçık pozisyonlara ücret işaretlendi: {marked} adet")

    ph = [r for r in rows if r["placeholder"]]
    if ph:
        print(f"\nCanlı ayna ({len(ph)} defter) — bakiye yer tutucu, yalnız total_pnl "
              f"düzeltildi: {', '.join(r['key'].replace('poly_trader_', '') for r in ph)}")

    bust = [r for r in rows
            if r["bal_after"] is not None and r["bal_after"] < 0 and not r["placeholder"]]
    if bust:
        print("\nÜcret sonrası bakiyesi eksiye düşen defterler (sermaye tükendi):")
        for r in bust:
            print(f"  {r['key'].replace('poly_trader_', ''):22s} "
                  f"{r['bal_before']:>8.2f}$ -> {r['bal_after']:>8.2f}$")
        print("  Sıfırlamak için: python3 temmuzPoly/algo_islemler_fresh_start.py")
    if not args.apply:
        print("\nYazmak için: python3 temmuzPoly/pm_fee_backfill.py --apply")
    else:
        print(f"\nYedekler: {BACKUP_DIR}")


if __name__ == "__main__":
    main()
