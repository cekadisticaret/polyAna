#!/usr/bin/env python3
"""Uludağ / Bursa Teleferik bilet, saat, indirim ve ulaşım bilgisi.

  python3 BursaApp/teleferik_fetch.py

Cron (İST 06:15 ≈ UTC 03:15):
  15 3 * * * cd /root/aiProject && python3 BursaApp/teleferik_fetch.py >> /tmp/teleferik_fetch.log 2>&1
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
SEED = os.path.join(_DIR, "data", "teleferik_seed.json")
OUT = os.path.join(_DIR, "data", "teleferik.json")
UA = "BursaApp/1.0 (+https://bursaapp.com; teleferik)"
IST = ZoneInfo("Europe/Istanbul")
OFFICIAL = "https://uludag.uludagbel.com.tr/teleferik"


def _get(url: str, timeout: int = 15) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, (resp.read(120000) or b"").decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, (e.read(8000) or b"").decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def _parse_prices(html: str) -> list[dict]:
    """Resmi sayfadan TL rakamları yakala — seed'i ezmez, yalnızca not."""
    found = []
    for m in re.finditer(r"(\d{2,4})\s*TL", html, re.I):
        val = int(m.group(1))
        if 50 <= val <= 5000:
            found.append(val)
    uniq = sorted(set(found))
    return [{"amount_tl": v, "from_page": True} for v in uniq[:8]]


def main() -> int:
    if not os.path.isfile(SEED):
        print("missing seed", SEED)
        return 1
    data = json.loads(open(SEED, encoding="utf-8").read())
    now = datetime.now(tz=IST)
    data["generated_at"] = now.isoformat()
    data["generated_label"] = now.strftime("%d.%m.%Y %H:%M İST")

    code, html = _get(OFFICIAL)
    data["official_probe"] = {"url": OFFICIAL, "http": code, "ok": 200 <= code < 400}
    if data["official_probe"]["ok"] and html:
        scraped = _parse_prices(html)
        if scraped:
            data["scraped_prices_hint"] = scraped
            data["scrape_note"] = "Sayfadan yakalanan TL değerleri — gişe tarifesi ile teyit edin."

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"wrote {OUT} · prices={len(data.get('prices') or [])} probe={data['official_probe']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
