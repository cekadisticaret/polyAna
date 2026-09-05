#!/usr/bin/env python3
"""Diş + doktor kadrosu — otomatik teyit ve DB senkronu (cron).

  python3 BursaApp/health_refresh.py

Sıra: Doruk kadro → MHRS/resmi diş + seed_health → doktor zenginleştirme.
"""
from __future__ import annotations

import os
import subprocess
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def _run(label: str, script: str, *args: str, required: bool = True) -> bool:
    path = os.path.join(_DIR, script)
    cmd = [PY, path, *args]
    print(f"=== {label} ===", flush=True)
    r = subprocess.run(cmd, cwd=os.path.dirname(_DIR))
    if r.returncode != 0:
        msg = f"{label} çıkış kodu {r.returncode}"
        if required:
            print(f"HATA: {msg}", flush=True)
            return False
        print(f"UYARI: {msg} (atlandı)", flush=True)
    return True


def main() -> int:
    ok = True
    ok = _run("Doruk hekim kadrosu", "doruk_doctors_fetch.py", required=False) and ok
    ok = (
        _run(
            "Diş hekimleri (MHRS/resmi + seed)",
            "dentists_fetch.py",
            "--no-photon",
            "--no-skrs",
            "--seed",
        )
        and ok
    )
    _run("Doktor zenginleştirme", "enrich_doctors.py", required=False)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
