#!/usr/bin/env python3
"""Bursa nöbetçi eczaneler — günlük çekim.

Asıl kaynak: Bursa Eczacı Odası (https://www.beo.org.tr/nobetci-eczaneler)
Nöbet genelde akşam ~18:30 → ertesi 08:30. eczaneadresi.com API bazen bir gün geride kalır.

  python3 BursaApp/nobetci_eczane_fetch.py

Cron (İST 07:00 / 12:00 / 15:00 / 18:45 / 19:00 ≈ UTC 04:00 / 09:00 / 12:00 / 15:45 / 16:00):
  0 4,9,12,16 * * * cd /root/aiProject && python3 BursaApp/nobetci_eczane_fetch.py >> /tmp/nobetci_eczane.log 2>&1
  45 15 * * * cd /root/aiProject && python3 BursaApp/nobetci_eczane_fetch.py >> /tmp/nobetci_eczane.log 2>&1
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from html import unescape
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_DIR, "data", "nobetci_eczaneler.json")
BEO_URL = "https://www.beo.org.tr/nobetci-eczaneler"
API = "https://eczaneadresi.com/api/public/widget/duty"
UA = {"User-Agent": "BursaApp/1.0 (+https://bursaapp.com; nobetci eczane)"}
IST = ZoneInfo("Europe/Istanbul")

_TR_MONTH = {
    "ocak": 1, "subat": 2, "şubat": 2, "mart": 3, "nisan": 4, "mayis": 5, "mayıs": 5,
    "haziran": 6, "temmuz": 7, "agustos": 8, "ağustos": 8, "eylul": 9, "eylül": 9,
    "ekim": 10, "kasim": 11, "kasım": 11, "aralik": 12, "aralık": 12,
}


def _slug(name: str, district: str, key: str) -> str:
    s = f"{name}-{district}-{key}".lower()
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = s.translate(tr)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or f"eczane-{key}"


def _tr_title(s: str) -> str:
    s = unescape(s or "").strip()
    s = s.translate(str.maketrans("Iİ", "ıi")).lower()
    parts = []
    for w in s.split():
        if not w:
            continue
        if w[0] == "i":
            parts.append("İ" + w[1:])
        elif w[0] == "ı":
            parts.append("I" + w[1:])
        else:
            parts.append(w[0].upper() + w[1:])
    return " ".join(parts)


def _norm_ilce(raw: str) -> str:
    blob = _tr_title((raw or "").split("-")[0].strip())
    aliases = {
        "Mustafakemalpasa": "Mustafakemalpaşa",
        "Mustafakemalpaşa": "Mustafakemalpaşa",
        "İnegöl": "İnegöl",
        "Inegol": "İnegöl",
        "Inegöl": "İnegöl",
        "İznik": "İznik",
        "Iznik": "İznik",
        "Nilüfer": "Nilüfer",
        "Yıldırım": "Yıldırım",
        "Gürsu": "Gürsu",
        "Büyükorhan": "Büyükorhan",
        "Harmancık": "Harmancık",
        "Osmangazi": "Osmangazi",
        "Mudanya": "Mudanya",
        "Gemlik": "Gemlik",
        "Kestel": "Kestel",
        "Karacabey": "Karacabey",
        "Yenişehir": "Yenişehir",
        "Orhangazi": "Orhangazi",
        "Orhaneli": "Orhaneli",
        "Keles": "Keles",
    }
    return aliases.get(blob, blob)


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def _parse_beo_date(html: str) -> str:
    m = re.search(
        r"(\d{1,2})\s+(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|Temmuz|"
        r"Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|Aralık|Aralik)\s+(\d{4})\s+Bugün",
        html,
        re.I,
    )
    if not m:
        return datetime.now(IST).strftime("%Y-%m-%d")
    day, mon, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    mi = _TR_MONTH.get(mon) or datetime.now(IST).month
    return f"{year:04d}-{mi:02d}-{day:02d}"


def fetch_beo() -> dict:
    html = _get(BEO_URL)
    duty_date = _parse_beo_date(html)
    items = []
    for m in re.finditer(
        r"<h4 class=\"red\"><strong>([^<]+)</strong>\s*-\s*([^<]+)</h4>(.*?)</p>",
        html,
        re.S | re.I,
    ):
        name = _tr_title(m.group(1))
        district = _norm_ilce(unescape(m.group(2)))
        body = m.group(3)
        addr_m = re.search(r"fa-home[^>]*>\s*</i>\s*(.*?)<br", body, re.S | re.I)
        extra_m = re.search(r"<br>\s*(\([^<]+\))", body)
        address = re.sub(r"\s+", " ", unescape(addr_m.group(1) if addr_m else "")).strip()
        if extra_m:
            extra = re.sub(r"\s+", " ", unescape(extra_m.group(1))).strip()
            if extra and extra not in address:
                address = f"{address} {extra}".strip()
        phones = [p.strip() for p in re.findall(r'href="tel:([^"]+)"', body)]
        phone = phones[0] if phones else ""
        geo = re.search(r"maps\?q=(-?\d+\.?\d*),(-?\d+\.?\d*)", body)
        lat_f = lng_f = None
        maps = ""
        if geo:
            lat_f, lng_f = float(geo.group(1)), float(geo.group(2))
            maps = f"https://www.google.com/maps/dir/?api=1&destination={lat_f},{lng_f}"
        hours_m = re.search(
            r"(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}\s*/\s*\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})",
            unescape(body),
        )
        hours = ""
        if hours_m:
            hours = re.sub(r"\s+", " ", hours_m.group(1)).strip()
        key = re.sub(r"[^0-9]", "", f"{lat_f or ''}{lng_f or ''}")[-8:] or str(len(items) + 1)
        items.append(
            {
                "id": int(key) if key.isdigit() else len(items) + 1,
                "slug": _slug(name, district, key),
                "name": name,
                "district": district,
                "address": address[:280],
                "phone": phone[:40],
                "lat": lat_f,
                "lng": lng_f,
                "maps": maps,
                "hours_text": hours,
                "source_url": BEO_URL,
            }
        )
    # aynı isim+ilçe tek
    seen = set()
    uniq = []
    for p in items:
        k = (p["name"].lower(), p["district"].lower())
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    uniq.sort(key=lambda x: (x.get("district") or "ZZZ", x.get("name") or ""))
    if len(uniq) < 8:
        raise RuntimeError(f"BEO parse zayıf: {len(uniq)} eczane")
    return {
        "ok": True,
        "fetched_at": datetime.now(IST).isoformat(timespec="minutes"),
        "duty_date": duty_date,
        "city": "Bursa",
        "total": len(uniq),
        "attribution": "Bursa Eczacı Odası",
        "source": BEO_URL,
        "pharmacies": uniq,
    }


def fetch_api_fallback() -> dict:
    qs = urllib.parse.urlencode({"scope": "city", "city": "bursa", "limit": 200})
    data = json.loads(_get(f"{API}?{qs}"))
    if not data.get("ok"):
        raise RuntimeError(f"API ok=false: {data!r}"[:300])
    items = []
    for p in data.get("pharmacies") or []:
        lat, lng = p.get("lat"), p.get("lng")
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
                "slug": _slug(name, district, str(pid)),
                "name": name,
                "district": district,
                "address": (p.get("address") or "").strip(),
                "phone": (p.get("phone") or "").strip(),
                "lat": lat_f,
                "lng": lng_f,
                "maps": maps,
                "hours_text": "",
                "source_url": (p.get("detail_url") or "").strip(),
            }
        )
    items.sort(key=lambda x: (x.get("district") or "ZZZ", x.get("name") or ""))
    return {
        "ok": True,
        "fetched_at": datetime.now(IST).isoformat(timespec="minutes"),
        "duty_date": data.get("tarih") or "",
        "city": data.get("city") or "Bursa",
        "total": len(items),
        "attribution": "eczaneadresi.com (yedek)",
        "source": API,
        "pharmacies": items,
    }


def fetch() -> dict:
    try:
        return fetch_beo()
    except Exception as e:
        print("BEO fail, API yedek:", e, file=sys.stderr)
        return fetch_api_fallback()


def main() -> None:
    payload = fetch()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(
        f"wrote {OUT} total={payload['total']} duty_date={payload.get('duty_date')} "
        f"src={payload.get('attribution')}"
    )


if __name__ == "__main__":
    main()
