#!/usr/bin/env python3
"""Sahipsiz defter taraması — hiçbir runner'ın dokunmadığı state dosyaları.

`Analizler/data/a4_state.json` 51 saattir 6 açık pozisyon tutuyordu: `a4`
kataloğdan (`ANALIZ_META`) kaldırılmış ama dosyası kalmıştı, dolayısıyla
`close`/`trail` turları o defteri hiç görmüyordu. Pozisyonlar ne kapanıyor
ne de zarar/kâr olarak sayılıyordu — sessiz muhasebe boşluğu.

    python3 AgustosKripto/orphan_scan.py            # rapor
    python3 AgustosKripto/orphan_scan.py --archive  # sahipsizleri arşive taşı
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

_DIR = os.path.dirname(os.path.abspath(__file__))
TR = timezone(timedelta(hours=3))


def _known_keys() -> dict[str, set[str]]:
    """Her grubun runner'ının gerçekten işlediği defter anahtarları."""
    out: dict[str, set[str]] = {}

    sys.path.insert(0, _DIR)

    def _load(sub: str, attr_path: str) -> set[str]:
        import importlib.util as ilu
        d = os.path.join(_DIR, sub)
        sys.path.insert(0, d)
        try:
            spec = ilu.spec_from_file_location(f"_scan_{sub}", os.path.join(d, "catalog.py"))
            if spec is None or spec.loader is None:
                return set()
            mod = ilu.module_from_spec(spec)
            spec.loader.exec_module(mod)
            books = getattr(mod, "ALL_BOOKS", [])
            return {b.get("book_key") or b.get("uid") for b in books}
        except Exception:
            return set()
        finally:
            sys.path.remove(d)

    out["Test"] = _load("Test", "ALL_BOOKS")
    out["Algoritmalar"] = _load("Algoritmalar", "ALL_BOOKS")

    # Analizler kataloğu signals.py içinde
    d = os.path.join(_DIR, "Analizler")
    sys.path.insert(0, d)
    try:
        import importlib.util as ilu
        spec = ilu.spec_from_file_location("_scan_analizler_sig", os.path.join(d, "signals.py"))
        mod = ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out["Analizler"] = {m["id"] for m in getattr(mod, "ANALIZ_META", [])}
    except Exception:
        out["Analizler"] = set()
    finally:
        sys.path.remove(d)
    return out


def scan() -> list[dict]:
    known = _known_keys()
    rows = []
    now = datetime.now(TR)
    for group, keys in known.items():
        ddir = os.path.join(_DIR, group, "data")
        if not keys or not os.path.isdir(ddir):
            continue
        for path in sorted(glob.glob(os.path.join(ddir, "*_state.json"))):
            key = os.path.basename(path).replace("_state.json", "")
            if key in keys:
                continue
            try:
                st = json.load(open(path))
            except Exception:
                continue
            opens = st.get("open_positions") or []
            ages = []
            for p in opens:
                try:
                    ages.append((now - datetime.fromisoformat(str(p["entry_time_tr"])))
                                .total_seconds() / 3600)
                except Exception:
                    pass
            rows.append({
                "grup": group, "defter": key, "yol": path,
                "acik": len(opens),
                "en_eski_saat": round(max(ages), 1) if ages else 0.0,
                "bakiye": st.get("balance"),
            })
    return rows


def main() -> None:
    rows = scan()
    if not rows:
        print("Sahipsiz defter yok.")
        return
    canli = [r for r in rows if r["acik"]]
    print(f"Sahipsiz state dosyası: {len(rows)} · açık pozisyon tutan: {len(canli)}\n")
    print(f"{'grup':14} {'defter':22} {'açık':>5} {'en eski':>9} {'bakiye':>10}")
    for r in sorted(rows, key=lambda x: -x["acik"]):
        print(f"{r['grup']:14} {r['defter']:22} {r['acik']:>5} "
              f"{r['en_eski_saat']:>8.1f}s {str(r['bakiye']):>10}")

    if "--archive" not in sys.argv:
        print("\n(--archive ile sahipsiz dosyalar _archive_orphan_<tarih>/ altına taşınır)")
        return

    dest = os.path.join(_DIR, f"_archive_orphan_{datetime.now(TR):%Y%m%d}")
    os.makedirs(dest, exist_ok=True)
    moved = 0
    for r in rows:
        for suffix in ("_state.json", "_history.json"):
            src = r["yol"].replace("_state.json", suffix)
            if os.path.exists(src):
                shutil.move(src, os.path.join(dest, f"{r['grup']}_{os.path.basename(src)}"))
                moved += 1
    print(f"\n{moved} dosya taşındı → {dest}")


if __name__ == "__main__":
    main()
