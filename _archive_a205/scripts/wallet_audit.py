#!/usr/bin/env python3
"""Cüzdandaki tüm PM pozisyonlarını botun defteriyle karşılaştırır.

Bot yalnızca live_state.json'daki pozisyonları kapatır/redeem eder. Emir
kaydedilmeden gerçekleştiyse veya kapanış başarısız olduysa pozisyon cüzdanda
öksüz kalır — para orada durur ama kimse dokunmaz. Bu script onları bulur.

Kullanım: scripts/wallet_audit.py
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

_HDR = {"User-Agent": "a205-audit", "Accept": "application/json"}


def api(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=_HDR), timeout=25) as r:
        return json.loads(r.read().decode())


def main() -> int:
    funder = os.getenv("POLY_FUNDER", "")
    if not funder:
        print("POLY_FUNDER yok")
        return 1

    rows = api(f"https://data-api.polymarket.com/positions?sizeThreshold=0.01&user={funder}")
    rows = [p for p in rows if isinstance(p, dict)]

    state = json.loads((DATA / "live_state.json").read_text(encoding="utf-8"))
    known = {str(p.get("pm_token_id")) for p in state.get("open_positions") or []}

    hist = json.loads((DATA / "live_history.json").read_text(encoding="utf-8"))
    closed_slugs = {t.get("pm_slug") for t in hist if t.get("pm_slug")}

    tracked_val = orphan_val = redeem_val = 0.0
    orphans = []

    print(f"{'MARKET':44s} {'YÖN':5s} {'HİSSE':>8s} {'DEĞER':>8s} {'DURUM':>8s}  DEFTER")
    print("-" * 90)
    for p in sorted(rows, key=lambda x: -float(x.get("currentValue") or 0)):
        val = float(p.get("currentValue") or 0)
        if val < 0.01:
            continue
        tok = str(p.get("asset") or "")
        slug = p.get("slug") or ""
        is_known = tok in known
        redeemable = bool(p.get("redeemable"))

        if is_known:
            tracked_val += val
            tag = "takipte"
        else:
            orphan_val += val
            tag = "kapanmis" if slug in closed_slugs else "ÖKSÜZ"
            orphans.append((slug, p.get("outcome", ""), val, redeemable, tag))
        if redeemable:
            redeem_val += val

        print(f"{slug[:44]:44s} {str(p.get('outcome'))[:5]:5s} "
              f"{float(p.get('size') or 0):8.1f} {val:8.2f} "
              f"{'REDEEM' if redeemable else 'açık':>8s}  {tag}")

    print("-" * 90)
    print(f"botun takip ettiği : ${tracked_val:.2f}")
    print(f"defter dışı        : ${orphan_val:.2f}")
    print(f"redeem edilebilir  : ${redeem_val:.2f}")
    print(f"toplam             : ${tracked_val + orphan_val:.2f}")

    hard = [o for o in orphans if o[4] == "ÖKSÜZ"]
    if hard:
        print(f"\nhiç kaydedilmemiş {len(hard)} pozisyon — "
              f"toplam ${sum(o[2] for o in hard):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
