#!/usr/bin/env python3
"""Bursa okulları — OSM + el seçimi birleşik JSON.

  python3 BursaApp/schools_fetch.py          # OSM + curated → data/schools.json
  python3 BursaApp/schools_fetch.py --events # okul etkinliklerini de üret
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "data")
SCHOOLS_PATH = os.path.join(DATA, "schools.json")
EVENTS_PATH = os.path.join(DATA, "school_events.json")
CURATED_PATH = os.path.join(DATA, "schools_curated.json")
DERSHANE_PATH = os.path.join(DATA, "meb_dershaneler_bursa.json")
OZEL_EGITIM_PATH = os.path.join(DATA, "meb_ozel_egitim_bursa.json")

ILCELER = (
    "Osmangazi", "Nilüfer", "Yıldırım", "Mudanya", "Gemlik", "İnegöl",
    "Mustafakemalpaşa", "İznik", "Kestel", "Gürsu", "Orhangazi", "Karacabey",
    "Yenişehir", "Orhaneli", "Büyükorhan", "Harmancık", "Keles",
)
ILCE_NORM = {x.lower().replace("i", "ı"): x for x in ILCELER}

OVERPASS = "https://overpass-api.de/api/interpreter"

# El seçimi — zengin detay (OSM kaydı yoksa veya üstüne yazar)
CURATED: list[dict] = []


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().translate(str.maketrans("çğıöşü", "cgiosu"))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:88] or "okul"


def norm_ilce(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return ""
    low = t.lower().replace("i", "ı")
    for key, val in ILCE_NORM.items():
        if key in low or low in key:
            return val
    for il in ILCELER:
        if il.lower() in t.lower():
            return il
    return t[:48]


def infer_subcategory(name: str, tags: dict) -> str:
    n = (name or "").lower()
    isced = (tags.get("isced:level") or tags.get("school:levels") or "").lower()
    if "dershane" in n or "dershanecilik" in n:
        return "dershane"
    if any(
        x in n
        for x in (
            "özel eğitim",
            "ozel egitim",
            "rehabilitasyon",
            "uygulama okulu",
            "otizm",
            "disleksi",
        )
    ):
        return "ozel-egitim"
    if any(x in n for x in ("anaokul", "ana okul", "kreş", "kres", "kindergarten")):
        return "anaokul"
    if "üniversite" in n or "universite" in n or tags.get("amenity") == "university":
        return "universite"
    if any(x in n for x in ("ilkokul", "primary", "ilk okul")) or "1" in isced:
        return "ilkokul"
    if any(x in n for x in ("ortaokul", "orta okul", "middle")) or "2" in isced:
        return "ortaokul"
    if any(x in n for x in ("lise", "anadolu", "fen lisesi", "imam hatip", "high school")):
        return "lise"
    if any(x in n for x in ("kolej", "college", "amerikan", "ted ", "final", "bahçeşehir", "mev ")):
        return "kolej"
    if tags.get("amenity") == "kindergarten":
        return "anaokul"
    if tags.get("amenity") == "college":
        return "kolej"
    return "lise"


def infer_band(name: str, tags: dict) -> str:
    n = (name or "").lower()
    op = (tags.get("operator") or tags.get("operator:type") or "").lower()
    if tags.get("operator:type") in ("government", "public"):
        return "Devlet"
    if "devlet" in n or "imam hatip" in n and "özel" not in n:
        return "Devlet"
    if any(x in n for x in ("özel", "ozel", "kolej", "college", "amerikan", "ted ", "final", "bahçeşehir", "mev ", "doğa", "doga")):
        return "Özel"
    if "universite" in n or tags.get("amenity") == "university":
        return "Üniversite"
    if op in ("private", "religious"):
        return "Özel"
    if op in ("public", "government"):
        return "Devlet"
    return "Devlet"


def addr_from_tags(tags: dict) -> str:
    parts = []
    for k in ("addr:street", "addr:housenumber", "addr:neighbourhood", "addr:suburb"):
        v = (tags.get(k) or "").strip()
        if v:
            parts.append(v)
    city = (tags.get("addr:city") or tags.get("addr:province") or "").strip()
    if parts:
        line = " ".join(parts)
        if city and city.lower() not in line.lower():
            line += f", {city}"
        return line[:280]
    return (tags.get("addr:full") or "")[:280]


def fetch_osm() -> list[dict]:
    q = """
    [out:json][timeout:120];
    area["name"="Bursa"]["admin_level"="4"]->.bursa;
    (
      node["amenity"~"school|kindergarten|college|university"](area.bursa);
      way["amenity"~"school|kindergarten|college|university"](area.bursa);
      relation["amenity"~"school|kindergarten|college|university"](area.bursa);
    );
    out center tags;
    """
    req = urllib.request.Request(
        OVERPASS,
        data=f"data={urllib.parse.quote(q)}".encode(),
        headers={"User-Agent": "BursaApp/1.0 (+https://bursaapp.com)"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=130) as resp:
        data = json.loads(resp.read().decode())
    out: list[dict] = []
    seen: set[str] = set()
    for el in data.get("elements") or []:
        tags = el.get("tags") or {}
        name = (tags.get("name") or tags.get("name:tr") or "").strip()
        if not name or len(name) < 4:
            continue
        if any(x in name.lower() for x in ("atölye", "yurt", "pansiyon", "yemekhane")):
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        slug = slugify(name)
        base = slug
        i = 2
        while slug in seen:
            slug = f"{base}-{i}"
            i += 1
        seen.add(slug)
        ilce = norm_ilce(tags.get("addr:suburb") or tags.get("addr:district") or tags.get("addr:city") or "")
        sub = infer_subcategory(name, tags)
        band = infer_band(name, tags)
        phone = (tags.get("phone") or tags.get("contact:phone") or "")[:40]
        web = (tags.get("website") or tags.get("contact:website") or "")[:280]
        out.append(
            {
                "slug": slug,
                "title": name,
                "subcategory": sub,
                "price_band": band,
                "ilce": ilce or "Osmangazi",
                "address": addr_from_tags(tags),
                "phone": phone,
                "web": web,
                "hours_text": "08:00 – 16:00" if sub != "universite" else "",
                "lat": lat,
                "lng": lng,
                "blurb": f"{band} {sub.replace('kolej', 'kolej').title()} · {ilce or 'Bursa'}",
                "tags": [sub, band.lower()],
                "featured": band == "Özel" and sub in ("kolej", "lise"),
                "source": "osm",
            }
        )
    return out


def load_curated_file() -> list[dict]:
    if os.path.isfile(CURATED_PATH):
        return json.loads(open(CURATED_PATH, encoding="utf-8").read())
    return CURATED


def load_extra_json(path: str) -> list[dict]:
    if os.path.isfile(path):
        return json.loads(open(path, encoding="utf-8").read())
    return []


def merge_schools(osm_rows: list[dict], *extra_lists: list[dict]) -> list[dict]:
    by_slug = {r["slug"]: r for r in osm_rows}
    by_title = {r["title"].lower(): r for r in osm_rows}
    by_phone: dict[str, dict] = {}
    for r in osm_rows:
        ph = re.sub(r"\D", "", r.get("phone") or "")
        if len(ph) >= 10:
            by_phone[ph[-10:]] = r
    all_curated: list[dict] = []
    for lst in extra_lists:
        all_curated.extend(lst or [])
    for c in all_curated:
        slug = c.get("slug") or slugify(c["title"])
        c = dict(c)
        c["slug"] = slug
        if slug in by_slug:
            base = by_slug[slug]
            for k, v in c.items():
                if v not in (None, "", [], {}):
                    base[k] = v
            base["featured"] = bool(c.get("featured") or base.get("featured"))
        elif c["title"].lower() in by_title:
            base = by_title[c["title"].lower()]
            for k, v in c.items():
                if v not in (None, "", [], {}):
                    base[k] = v
        else:
            ph = re.sub(r"\D", "", c.get("phone") or "")
            if len(ph) >= 10 and ph[-10:] in by_phone and c.get("phone"):
                base = by_phone[ph[-10:]]
                for k, v in c.items():
                    if k == "slug":
                        continue
                    if v not in (None, "", [], {}):
                        base[k] = v
            else:
                by_slug[slug] = c
    rows = list(by_slug.values())
    rows.sort(
        key=lambda r: (
            0 if r.get("featured") else 1,
            0 if r.get("price_band") == "Özel" else 1 if r.get("price_band") == "Devlet" else 2,
            r.get("title") or "",
        )
    )
    return rows


def build_events(schools: list[dict]) -> list[dict]:
    """Okul etkinlikleri — curated extra.events + otomatik tanıtım günü şablonları."""
    events: list[dict] = []
    now = datetime.utcnow()
    types = [
        ("tanitim-gunu", "Tanitim Gunu", "Tanitim", "Okul tanitim ve kayit gunu — veli bilgilendirme."),
        ("bilim-senligi", "Bilim Senligi", "Etkinlik", "Proje sergisi ve atolye calismalari."),
        ("spor-gunu", "Spor Gunu", "Spor", "Okul ici spor musabakalari ve turnuva."),
        ("mezuniyet", "Mezuniyet Toreni", "Toreni", "Mezuniyet ve yil sonu gosterisi."),
    ]
    for s in schools:
        extra = s.get("extra") or {}
        for ev in extra.get("events") or []:
            ev = dict(ev)
            ev.setdefault("school_slug", s["slug"])
            events.append(ev)
        if s.get("price_band") != "Özel" and not s.get("featured"):
            continue
        for i, (code, label, band, blurb) in enumerate(types[:2]):
            start = now + timedelta(days=14 + i * 21 + hash(s["slug"]) % 10)
            events.append(
                {
                    "slug": f"okul-{s['slug']}-{code}-2026",
                    "title": f"{s['title']} · {label}",
                    "school_slug": s["slug"],
                    "starts": start.replace(hour=10, minute=0, second=0).isoformat(),
                    "ends": (start + timedelta(hours=6)).isoformat(),
                    "price_band": band,
                    "blurb": blurb,
                    "web": s.get("web") or "",
                    "ilce": s.get("ilce") or "",
                    "address": s.get("address") or s.get("title"),
                }
            )
    return events


def main() -> None:
    do_events = "--events" in sys.argv
    print("OSM okullar çekiliyor…", flush=True)
    try:
        osm = fetch_osm()
        print(f"OSM: {len(osm)} kayıt", flush=True)
    except Exception as exc:
        print(f"OSM hata ({exc}) — yalnız curated kullanılacak", flush=True)
        osm = []
    curated = load_curated_file()
    dershaneler = load_extra_json(DERSHANE_PATH)
    ozel_egitim = load_extra_json(OZEL_EGITIM_PATH)
    if not dershaneler and os.path.isfile(os.path.join(_DIR, "dershane_fetch.py")):
        print("meb_dershaneler_bursa.json yok — dershane_fetch çalıştırılıyor…", flush=True)
        import subprocess

        subprocess.run([sys.executable, os.path.join(_DIR, "dershane_fetch.py")], check=False)
        dershaneler = load_extra_json(DERSHANE_PATH)
    if not ozel_egitim and os.path.isfile(os.path.join(_DIR, "ozel_egitim_fetch.py")):
        print("meb_ozel_egitim_bursa.json yok — ozel_egitim_fetch çalıştırılıyor…", flush=True)
        import subprocess

        subprocess.run([sys.executable, os.path.join(_DIR, "ozel_egitim_fetch.py")], check=False)
        ozel_egitim = load_extra_json(OZEL_EGITIM_PATH)
    merged = merge_schools(osm, curated, dershaneler, ozel_egitim)
    os.makedirs(DATA, exist_ok=True)
    with open(SCHOOLS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"Yazıldı: {SCHOOLS_PATH} ({len(merged)} okul)", flush=True)
    if do_events or not os.path.isfile(EVENTS_PATH):
        evs = build_events(merged)
        with open(EVENTS_PATH, "w", encoding="utf-8") as f:
            json.dump(evs, f, ensure_ascii=False, indent=2)
        print(f"Yazıldı: {EVENTS_PATH} ({len(evs)} etkinlik)", flush=True)


if __name__ == "__main__":
    main()
