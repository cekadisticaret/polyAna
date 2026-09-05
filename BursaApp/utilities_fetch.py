#!/usr/bin/env python3
"""Bursa su / elektrik / doğalgaz tarifeleri ve bölge ofisleri.

Kaynak: data/utilities_seed.json (resmi tarife tabloları + iletişim).
Cron ile generated_at damgası güncellenir; resmi siteler erişilebilirse not eklenir.

  python3 BursaApp/utilities_fetch.py

Cron (İST 06:00 ≈ UTC 03:00):
  0 3 * * * cd /root/aiProject && python3 BursaApp/utilities_fetch.py >> /tmp/utilities_fetch.log 2>&1
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(_DIR, "data", "utilities_seed.json")
OUT = os.path.join(_DIR, "data", "utilities.json")
UA = "BursaApp/1.0 (+https://bursaapp.com; utilities)"
IST = ZoneInfo("Europe/Istanbul")

PROBE_URLS = [
    ("buski", "https://www.buski.gov.tr/"),
    ("uedas", "https://www.uedas.com.tr/"),
    ("bursagaz", "https://www.bursagaz.com/"),
    ("aksa", "https://www.aksadogalgaz.com.tr/"),
]


def _get(url: str, timeout: int = 12) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, (resp.read(8000) or b"").decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = (e.read(4000) or b"").decode("utf-8", "replace")
        return e.code, body
    except Exception as e:
        return 0, str(e)


def _probe_sources() -> dict:
    out: dict = {}
    for key, url in PROBE_URLS:
        code, _ = _get(url)
        out[key] = {"url": url, "http": code, "ok": 200 <= code < 400}
    return out


def main() -> int:
    if not os.path.isfile(SEED):
        print("missing seed", SEED)
        return 1
    data = json.loads(open(SEED, encoding="utf-8").read())
    now = datetime.now(tz=IST)
    data["generated_at"] = now.isoformat()
    data["generated_label"] = now.strftime("%d.%m.%Y %H:%M İST")
    data["source_probe"] = _probe_sources()
    data["attribution"] = "BUSKİ · UEDAŞ · Bursagaz resmi tarifeler (özet)"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"wrote {OUT} · branches water={len(data['water']['branches'])} elec={len(data['electricity']['branches'])} gas={len(data['gas']['branches'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
