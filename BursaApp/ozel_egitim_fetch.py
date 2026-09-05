#!/usr/bin/env python3
"""Bursa özel eğitim / rehabilitasyon — MEB resmi liste.

Kaynak: https://ookgm.meb.gov.tr/kurumlar.php?il=BURSA&tur=rehabilitasyon

  python3 BursaApp/ozel_egitim_fetch.py
  python3 BursaApp/ozel_egitim_fetch.py --merge   # schools.json ile birleştir
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "data")
OUT_PATH = os.path.join(DATA, "meb_ozel_egitim_bursa.json")
CURATED_PATH = os.path.join(DATA, "ozel_egitim_curated.json")
SCHOOLS_PATH = os.path.join(DATA, "schools.json")
MEB_URL = "https://ookgm.meb.gov.tr/kurumlar.php?il=BURSA&tur=rehabilitasyon"

ILCELER = (
    "Osmangazi", "Nilüfer", "Yıldırım", "Mudanya", "Gemlik", "İnegöl",
    "Mustafakemalpaşa", "İznik", "Kestel", "Gürsu", "Orhangazi", "Karacabey",
    "Yenişehir", "Orhaneli", "Büyükorhan", "Harmancık", "Keles",
)
ILCE_NORM = {x.upper().replace("İ", "I"): x for x in ILCELER}


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().translate(str.maketrans("çğıöşü", "cgiosu"))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:88] or "ozel-egitim"


def norm_ilce(raw: str) -> str:
    t = (raw or "").strip().upper().replace("İ", "I")
    return ILCE_NORM.get(t, raw.strip().title())


def norm_phone(raw: str) -> str:
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 10:
        return "0" + d
    if len(d) == 11 and d.startswith("0"):
        return d
    if len(d) >= 10:
        return "0" + d[-10:]
    return (raw or "").strip()[:40]


def display_title(meb_title: str) -> str:
    t = (meb_title or "").strip()
    if t.upper().startswith("ÖZEL "):
        t = t[5:].strip()
    return t.title() if t.isupper() else t


def parse_meb_html(html: str) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
        if len(cells) < 5:
            continue
        clean = lambda s: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()
        cells = [clean(c) for c in cells]
        if not cells[0].isdigit():
            continue
        _, ilce_raw, name, address, phone_raw = cells[:5]
        if "Kurum Adı" in name:
            continue
        slug = slugify(name)
        base = slug
        i = 2
        while slug in seen:
            slug = f"{base}-{i}"
            i += 1
        seen.add(slug)
        ilce = norm_ilce(ilce_raw)
        ph = norm_phone(phone_raw)
        nice = display_title(name)
        rows.append(
            {
                "slug": slug,
                "title": nice,
                "subcategory": "ozel-egitim",
                "price_band": "Özel",
                "ilce": ilce,
                "address": address.strip(),
                "phone": ph,
                "web": "",
                "hours_text": "08:30 – 17:30",
                "blurb": f"Özel eğitim ve rehabilitasyon · {ilce}",
                "tags": ["ozel-egitim", "rehabilitasyon", "meb"],
                "featured": False,
                "source": "meb",
                "extra": {"meb_title": name, "programs": ["Destek eğitim", "Rehabilitasyon"]},
            }
        )
    return rows


def fetch_meb() -> list[dict]:
    req = urllib.request.Request(
        MEB_URL,
        headers={"User-Agent": "BursaApp/1.0 (+https://bursaapp.com)"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    return parse_meb_html(html)


def load_curated_overrides() -> list[dict]:
    if os.path.isfile(CURATED_PATH):
        return json.loads(open(CURATED_PATH, encoding="utf-8").read())
    return []


def apply_overrides(rows: list[dict], overrides: list[dict]) -> list[dict]:
    by_slug = {r["slug"]: r for r in rows}
    by_title = {(r.get("title") or "").lower(): r for r in rows}
    for o in overrides:
        o = dict(o)
        slug = o.get("slug") or slugify(o["title"])
        o["slug"] = slug
        if slug in by_slug:
            base = by_slug[slug]
        elif (o.get("title") or "").lower() in by_title:
            base = by_title[(o["title"] or "").lower()]
        else:
            by_slug[slug] = o
            continue
        for k, v in o.items():
            if v not in (None, "", [], {}):
                base[k] = v
    return list(by_slug.values())


def merge_into_schools(extra_rows: list[dict]) -> int:
    if not os.path.isfile(SCHOOLS_PATH):
        return 0
    schools = json.loads(open(SCHOOLS_PATH, encoding="utf-8").read())
    by_slug = {r["slug"]: r for r in schools}
    added = 0
    for row in extra_rows:
        slug = row["slug"]
        if slug in by_slug:
            base = by_slug[slug]
            for k, v in row.items():
                if v not in (None, "", [], {}):
                    base[k] = v
            continue
        # OSM eşleşmesi — özel eğitim adı
        title_low = (row.get("title") or "").lower()
        matched = None
        for s in schools:
            st = (s.get("title") or "").lower()
            if "ozel egitim" in st or "özel eğitim" in st:
                if st[:20] == title_low[:20] or title_low[:16] in st or st[:16] in title_low:
                    matched = s
                    break
        if matched:
            for k, v in row.items():
                if k == "slug":
                    continue
                if v not in (None, "", [], {}):
                    matched[k] = v
            matched["subcategory"] = row.get("subcategory") or "ozel-egitim"
            continue
        by_slug[slug] = row
        added += 1
    merged = list(by_slug.values())
    with open(SCHOOLS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return added


def main() -> None:
    os.makedirs(DATA, exist_ok=True)
    print("MEB rehabilitasyon listesi çekiliyor…", flush=True)
    rows = fetch_meb()
    print(f"MEB: {len(rows)} özel eğitim merkezi", flush=True)
    rows = apply_overrides(rows, load_curated_overrides())
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"Yazıldı: {OUT_PATH} ({len(rows)} kayıt)", flush=True)
    if "--merge" in sys.argv:
        added = merge_into_schools(rows)
        print(f"schools.json birleşti · yeni {added} kayıt", flush=True)


if __name__ == "__main__":
    main()
