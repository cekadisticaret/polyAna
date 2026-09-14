#!/usr/bin/env python3
"""Live defteri onarımı.

İki bozulmayı düzeltir:
  1. P&L şişmesi — pm_chain_settlement market bazlı toplam döndürdüğü için
     aynı markete birden fazla giriş yapıldığında her kayda tam toplam yazılmış.
     Doğrusu pozisyonun kendi pm_spent/pm_size değerinden hesaplanır.
  2. Mükerrer açık pozisyon — mirror tüm paper defterini tek seferde yansıtınca
     aynı market+token'a birden çok giriş oluşmuş. Bunlar tek pozisyonda
     birleştirilir (zincirdeki gerçek durum bu).

Kullanım: scripts/repair_state.py [--apply]
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TZ_TR = ZoneInfo("Europe/Istanbul")

_SLUG_HOUR = re.compile(r"-(\d{1,2})(am|pm)-et$")


def slot_hour_tr(slug: str) -> int | None:
    """Market slug'ından TR slot saati. ET = UTC-4, TR = UTC+3 → +7 saat."""
    m = _SLUG_HOUR.search(slug or "")
    if not m:
        return None
    hour, half = int(m.group(1)), m.group(2)
    if half == "am":
        et = 0 if hour == 12 else hour
    else:
        et = 12 if hour == 12 else hour + 12
    return (et + 7) % 24


def true_pnl(rec: dict) -> float:
    spent = float(rec.get("pm_spent") or rec.get("amount") or 0)
    size = float(rec.get("pm_size") or 0)
    return round(size - spent, 2) if rec.get("win") else round(-spent, 2)


def repair_history(path: Path) -> tuple[list, int, float, float]:
    history = json.loads(path.read_text(encoding="utf-8"))
    fixed = 0
    before = sum(float(t.get("pnl") or 0) for t in history)
    for rec in history:
        real = true_pnl(rec)
        if abs(real - float(rec.get("pnl") or 0)) > 0.01:
            rec["pnl_before_repair"] = rec.get("pnl")
            rec["pnl"] = real
            fixed += 1
    after = sum(float(t.get("pnl") or 0) for t in history)
    return history, fixed, before, after


def merge_positions(positions: list) -> list:
    """Aynı market+token'daki girişleri tek pozisyona indir."""
    merged: dict[tuple, dict] = {}
    order: list[tuple] = []
    for pos in positions:
        key = (pos.get("pm_slug"), pos.get("pm_token_id"))
        if key not in merged:
            base = dict(pos)
            base["pm_order_ids"] = [pos.get("pm_order_id")] if pos.get("pm_order_id") else []
            base["merged_count"] = 1
            merged[key] = base
            order.append(key)
            continue

        acc = merged[key]
        acc_spent = float(acc.get("pm_spent") or 0)
        acc_size = float(acc.get("pm_size") or 0)
        add_spent = float(pos.get("pm_spent") or 0)
        add_size = float(pos.get("pm_size") or 0)

        acc["pm_spent"] = round(acc_spent + add_spent, 2)
        acc["pm_size"] = round(acc_size + add_size, 2)
        acc["amount"] = round(float(acc.get("amount") or 0) + float(pos.get("amount") or 0), 2)
        if acc["pm_size"]:
            acc["pm_entry_price"] = round(acc["pm_spent"] / acc["pm_size"], 4)
        if pos.get("pm_order_id"):
            acc["pm_order_ids"].append(pos["pm_order_id"])
        acc["merged_count"] += 1

    out = []
    for key in order:
        pos = merged[key]
        hour = slot_hour_tr(pos.get("pm_slug") or "")
        if hour is not None and pos.get("entry_hour_tr") != hour:
            pos["entry_hour_tr_before_repair"] = pos.get("entry_hour_tr")
            pos["entry_hour_tr"] = hour
            now_tr = datetime.now(timezone.utc).astimezone(TZ_TR)
            slot = now_tr.replace(minute=0, second=0, microsecond=0)
            if slot.hour != hour:
                slot = slot.replace(hour=hour)
                if slot > now_tr:
                    slot -= timedelta(days=1)
            pos["entry_time_tr"] = slot.isoformat()
            pos["entry_dow"] = slot.weekday()
            pos["entry_is_weekend"] = slot.weekday() >= 5
        out.append(pos)
    return out


def clean_paper(positions: list, hour_tr: int) -> list:
    """Paper defteri: geçmiş slotları at, aynı sembol+saatten tek kayıt bırak."""
    seen: set[tuple] = set()
    out = []
    for pos in positions:
        if int(pos.get("entry_hour_tr", -1)) != hour_tr:
            continue
        key = (pos.get("symbol"), pos.get("entry_hour_tr"))
        if key in seen:
            continue
        seen.add(key)
        out.append(pos)
    return out


def main() -> int:
    apply = "--apply" in sys.argv
    state_path = DATA / "live_state.json"
    hist_path = DATA / "live_history.json"
    paper_path = DATA / "paper_state.json"

    history, fixed, before, after = repair_history(hist_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    open_before = state.get("open_positions") or []
    open_after = merge_positions(open_before)

    print(f"GEÇMİŞ  : {fixed}/{len(history)} kayıt düzeltildi")
    print(f"          toplam P&L {before:+.2f}$ → {after:+.2f}$")
    print(f"AÇIK POZ: {len(open_before)} kayıt → {len(open_after)} gerçek pozisyon")
    for p in open_after:
        print(
            f"          {p['symbol']:8s} {p.get('pm_token_dir'):4s} "
            f"slot {p.get('entry_hour_tr'):02d}:00  "
            f"risk ${float(p.get('pm_spent') or 0):.2f}  "
            f"kazanırsa ${float(p.get('pm_size') or 0):.2f}"
            + (f"  ({p['merged_count']} giriş birleşti)" if p.get("merged_count", 1) > 1 else "")
        )
    risk = sum(float(p.get("pm_spent") or 0) for p in open_after)
    print(f"          toplam risk ${risk:.2f}")

    hour_tr = datetime.now(timezone.utc).astimezone(TZ_TR).hour
    paper = json.loads(paper_path.read_text(encoding="utf-8"))
    paper_before = paper.get("open_positions") or []
    paper_after = clean_paper(paper_before, hour_tr)
    print(f"PAPER   : {len(paper_before)} kayıt → {len(paper_after)} (sadece {hour_tr:02d}:00 slotu)")

    if not apply:
        print("\n(kuru çalışma — yazmak için --apply)")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for src in (state_path, hist_path, paper_path):
        shutil.copy2(src, src.with_suffix(f".json.bak_{stamp}"))

    state["open_positions"] = open_after
    state["total_pnl"] = round(after, 2)
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    hist_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

    paper["open_positions"] = paper_after
    paper_path.write_text(json.dumps(paper, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nyazıldı — yedek: *.json.bak_{stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
