#!/usr/bin/env python3
"""Defterdeki açık pozisyonları zincirdeki gerçek durumla karşılaştırır.

Bot'un live_state.json kaydı "emir gönderdim" demektir; emrin gerçekten
dolup dolmadığı ancak Polymarket'in pozisyon/aktivite verisinden anlaşılır.
Bu script ikisini yan yana koyar.

Kullanım: scripts/verify_positions.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bootstrap import DATA, init  # noqa: E402

init()

_HDR = {"User-Agent": "a205-verify", "Accept": "application/json"}


def api(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=_HDR), timeout=20) as r:
        return json.loads(r.read().decode())


def main() -> int:
    funder = os.getenv("POLY_FUNDER", "")
    if not funder:
        print("POLY_FUNDER yok — zincir sorgulanamaz")
        return 1

    state = json.loads((DATA / "live_state.json").read_text(encoding="utf-8"))
    book = state.get("open_positions") or []
    if not book:
        print("defterde açık pozisyon yok")
        return 0

    chain_pos = api(f"https://data-api.polymarket.com/positions?sizeThreshold=0.01&user={funder}")
    by_token = {str(p.get("asset")): p for p in chain_pos if isinstance(p, dict)}

    activity = api(f"https://data-api.polymarket.com/activity?user={funder}&limit=500")
    fills: dict[str, dict] = {}
    for a in activity if isinstance(activity, list) else []:
        if a.get("type") != "TRADE" or a.get("side") == "SELL":
            continue
        tok = str(a.get("asset") or "")
        acc = fills.setdefault(tok, {"usdc": 0.0, "shares": 0.0, "n": 0})
        acc["usdc"] += float(a.get("usdcSize") or 0)
        acc["shares"] += float(a.get("size") or 0)
        acc["n"] += 1

    print(f"cüzdanda toplam {len(by_token)} açık token pozisyonu var\n")
    print(f"{'SEMBOL':7s} {'YÖN':5s} {'DEFTER $':>9s} {'ZİNCİR $':>9s} {'FARK $':>8s} "
          f"{'KAYIT':>6s} {'DOLUM':>6s}  DURUM")
    print("-" * 78)

    ok = mismatch = missing = 0
    for pos in book:
        tok = str(pos.get("pm_token_id") or "")
        sym = pos.get("symbol", "")[:3]
        side = pos.get("pm_token_dir", "")
        b_spent = float(pos.get("pm_spent") or 0)
        b_size = float(pos.get("pm_size") or 0)

        held = by_token.get(tok)
        fill = fills.get(tok)

        n_book = int(pos.get("merged_count") or 1)
        n_fill = int(fill["n"]) if fill else 0

        if not held and not fill:
            status = "ZİNCİRDE YOK"
            missing += 1
            c_spent = 0.0
        else:
            c_spent = float(fill["usdc"]) if fill else 0.0
            c_size = float(held.get("size") or 0) if held else (fill["shares"] if fill else 0.0)
            # %2 tolerans — taker ücreti ve yuvarlama
            close_spent = abs(c_spent - b_spent) <= max(0.25, b_spent * 0.02)
            close_size = abs(c_size - b_size) <= max(0.5, b_size * 0.02)
            if close_spent and close_size:
                status = "eslesiyor"
                ok += 1
            else:
                status = "KAYIT DISI ALIM"
                mismatch += 1

        print(f"{sym:7s} {side:5s} {b_spent:9.2f} {c_spent:9.2f} {c_spent - b_spent:8.2f} "
              f"{n_book:6d} {n_fill:6d}  {status}")

    print("-" * 78)
    print(f"eşleşen {ok} · farklı {mismatch} · zincirde yok {missing}")

    b_total = sum(float(p.get("pm_spent") or 0) for p in book)
    c_total = sum(fills.get(str(p.get("pm_token_id")), {}).get("usdc", 0.0) for p in book)
    print(f"\ndefter toplam risk : ${b_total:.2f}")
    print(f"zincir toplam alım : ${c_total:.2f}")

    val = sum(float(by_token.get(str(p.get('pm_token_id')), {}).get("currentValue") or 0) for p in book)
    print(f"pozisyonların şu anki değeri: ${val:.2f}")

    if "--reconcile" in sys.argv and mismatch:
        import shutil
        from datetime import datetime

        sp = DATA / "live_state.json"
        shutil.copy2(sp, sp.with_suffix(f".json.bak_{datetime.now():%Y%m%d_%H%M%S}"))
        for pos in book:
            tok = str(pos.get("pm_token_id") or "")
            fill, held = fills.get(tok), by_token.get(tok)
            if not fill:
                continue
            pos["pm_spent_book"] = pos.get("pm_spent")
            pos["pm_size_book"] = pos.get("pm_size")
            pos["pm_spent"] = round(fill["usdc"], 2)
            pos["pm_size"] = round(float(held.get("size") or 0) if held else fill["shares"], 2)
            pos["amount"] = pos["pm_spent"]
            if pos["pm_size"]:
                pos["pm_entry_price"] = round(pos["pm_spent"] / pos["pm_size"], 4)
            pos["chain_fills"] = fill["n"]
            pos["reconciled_from_chain"] = True
        state["open_positions"] = book
        sp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\ndefter zincire eşitlendi — risk ${b_total:.2f} → ${c_total:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
