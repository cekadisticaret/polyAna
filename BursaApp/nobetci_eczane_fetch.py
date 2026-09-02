#!/usr/bin/env python3
"""Bursa nöbetçi eczaneler — günlük çekim (ücretsiz public API).

Kaynak: https://eczaneadresi.com/api/public/widget/duty?scope=city&city=bursa

  python3 BursaApp/nobetci_eczane_fetch.py

Cron (İST 07:00 / 19:00 ≈ UTC 04:00 / 16:00):
  0 4,16 * * * cd /root/aiProject && python3 BursaApp/nobetci_eczane_fetch.py >> /tmp/nobetci_eczane.log 2>&1
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_DIR, "data", "nobetci_eczaneler.json")
API = "https://eczaneadresi.com/api/public/widget/duty"
UA = {"User-Agent": "BursaApp/1.0 (+https://bursaapp.com; nobetci eczane)"}
IST = ZoneInfo("Europe/Istanbul")


def _slug(name: str, district: str, pid: int) -> str:
    s = f"{name}-{district}-{pid}".lower()
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = s.translate(tr)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or f"eczane-{pid}"


def fetch() -> dict:
    qs = urllib.parse.urlencode({"scope": "city", "city": "bursa", "limit": 200})
    url = f"{API}?{qs}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    if not data.get("ok"):
        raise RuntimeError(f"API ok=false: {data!r}"[:300])
    items = []
    for p in data.get("pharmacies") or []:
        lat = p.get("lat")
        lng = p.get("lng")
        try:
            lat_f = float(lat) if lat is not None else None
            lng_f = float(lng) if lng is not None else None
        except (TypeError, ValueError):
            lat_f = lng_f = None
        pid = int(p.get("id") or 0)
        name = (p.get("name") or "Eczane").strip()
        district = (p.get("district") or "").strip()
        maps = (p.get("maps") or "").strip()
        if not maps and lat_f is not None and lng_f is not None:
            maps = f"https://www.google.com/maps/dir/?api=1&destination={lat_f},{lng_f}"
        items.append(
            {
                "id": pid,
                "slug": _slug(name, district, pid),
                "name": name,
                "district": district,
                "address": (p.get("address") or "").strip(),
                "phone": (p.get("phone") or "").strip(),
                "lat": lat_f,
                "lng": lng_f,
                "maps": maps,
                "source_url": (p.get("detail_url") or "").strip(),
            }
        )
    # ilçe + ad
    items.sort(key=lambda x: (x.get("district") or "ZZZ", x.get("name") or ""))
    return {
        "ok": True,
        "fetched_at": datetime.now(IST).isoformat(timespec="minutes"),
        "duty_date": data.get("tarih") or "",
        "city": data.get("city") or "Bursa",
        "total": len(items),
        "attribution": "",
        "pharmacies": items,
    }


def main() -> None:
    payload = fetch()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"wrote {OUT} total={payload['total']} duty_date={payload.get('duty_date')}")


if __name__ == "__main__":
    main()
