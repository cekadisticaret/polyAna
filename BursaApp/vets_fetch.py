#!/usr/bin/env python3
"""Bursa veterinerleri — BVHO + OSM + el seçimi.

  python3 BursaApp/vets_fetch.py           # BVHO + OSM → data/vets.json
  python3 BursaApp/vets_fetch.py --seed    # fetch + seed_health (DB)
  python3 BursaApp/vets_fetch.py --geocode   # eksik koordinatları Nominatim ile doldur (yavaş)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "data")
VETS_PATH = os.path.join(DATA, "vets.json")
CURATED_PATH = os.path.join(DATA, "vets_curated.json")
GEOCODE_CACHE = os.path.join(DATA, "vet_geocode.json")
BVHO_URL = "https://bursavho.org/muayenehaneler/"

ILCELER = (
    "Osmangazi", "Nilüfer", "Yıldırım", "Mudanya", "Gemlik", "İnegöl",
    "Mustafakemalpaşa", "İznik", "Kestel", "Gürsu", "Orhangazi", "Karacabey",
    "Yenişehir", "Orhaneli", "Büyükorhan", "Harmancık", "Keles",
)
ILCE_NORM = {x.lower().replace("i", "ı"): x for x in ILCELER}

DISTRICT_MAP = {
    "BÜYÜKORHAN": "Büyükorhan",
    "GEMLİK": "Gemlik",
    "GÜRSU": "Gürsu",
    "HARMANCIK": "Harmancık",
    "İNEGÖL": "İnegöl",
    "İZNİK": "İznik",
    "KARACABEY": "Karacabey",
    "KELES": "Keles",
    "KESTEL": "Kestel",
    "M.K.PAŞA": "Mustafakemalpaşa",
    "MUDANYA": "Mudanya",
    "NİLÜFER": "Nilüfer",
    "ORHANELİ": "Orhaneli",
    "ORHANGAZİ": "Orhangazi",
    "OSMANGAZİ": "Osmangazi",
    "YENİŞEHİR": "Yenişehir",
    "YILDIRIM": "Yıldırım",
}

OVERPASS = "https://overpass-api.de/api/interpreter"
NOMINATIM = "https://nominatim.openstreetmap.org/search"


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().translate(str.maketrans("çğıöşü", "cgiosu"))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or "veteriner"


def norm_ilce(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return ""
    up = t.upper()
    if up in DISTRICT_MAP:
        return DISTRICT_MAP[up]
    low = t.lower().replace("i", "ı")
    for k, val in ILCE_NORM.items():
        if k in low or low in k:
            return val
    for il in ILCELER:
        if il.lower() in t.lower():
            return il
    return t[:48]


def _title_key(title: str) -> str:
    s = unicodedata.normalize("NFKD", title or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    s = re.sub(r"\s+VETER(I|İ)NER\s+(MUAYENEHANES(I|İ)|POL(I|İ)KL(I|İ)N(I|İ)(G|Ğ)I|KLINIK|KLİNİK)", " ", s)
    s = re.sub(r"\s+VET\s+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def infer_band(title: str) -> tuple[str, str]:
    n = (title or "").upper()
    if any(x in n for x in ("HAYVAN HASTANES", " AT HASTANES", "FAKÜLTE", "FAKULTE")):
        return "Hastane", "hastane"
    if "POLİKLİN" in n or "POLIKLIN" in n:
        return "Poliklinik", "poliklinik"
    return "Klinik", "klinik"


def _clean_cell(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", t).strip()


def fetch_bvho() -> list[dict]:
    req = urllib.request.Request(
        BVHO_URL,
        headers={"User-Agent": "BursaApp/1.0 (+https://bursaapp.com; veteriner listesi)"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    panels = re.split(r'<div class="vc_tta-panel"', html)[1:]
    clinics: dict[tuple[str, str], dict] = {}
    seen_slugs: set[str] = set()

    for panel in panels:
        mt = re.search(r'vc_tta-title-text">([^<]+)', panel)
        if not mt:
            continue
        ilce = norm_ilce(mt.group(1).strip())
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", panel, re.S | re.I):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)
            if len(cells) < 2:
                continue
            vet_name = _clean_cell(cells[0])
            clinic = _clean_cell(cells[1])
            addr = _clean_cell(cells[2]) if len(cells) > 2 else ""
            if not clinic or len(clinic) < 4:
                continue
            if vet_name in ("---", ""):
                continue
            ck = (_title_key(clinic), re.sub(r"\s+", " ", addr.upper())[:100])
            if ck in clinics:
                ent = clinics[ck]
                vets = ent.setdefault("extra", {}).setdefault("vets", [])
                if vet_name and vet_name not in vets and len(vets) < 8:
                    vets.append(vet_name)
                continue
            band, sub = infer_band(clinic)
            title = clinic.title() if clinic.isupper() else clinic
            slug = slugify(title)
            base = slug
            i = 2
            while slug in seen_slugs:
                slug = f"{base}-{i}"
                i += 1
            seen_slugs.add(slug)
            blurb = f"BVHO kayıtlı · {addr}" if addr else f"BVHO kayıtlı · {ilce}"
            if len(blurb) > 160:
                blurb = blurb[:157] + "…"
            clinics[ck] = {
                "slug": slug,
                "title": title,
                "subcategory": sub,
                "price_band": band,
                "ilce": ilce,
                "address": addr[:280],
                "phone": "",
                "web": "",
                "hours_text": "Klinik mesai",
                "blurb": blurb,
                "tags": [sub, "bvho", "veteriner"],
                "featured": band == "Hastane",
                "source": "bvho",
                "extra": {"vets": [vet_name] if vet_name else []},
            }

    rows = list(clinics.values())
    rows.sort(
        key=lambda r: (
            0 if r.get("featured") else 1,
            0 if r.get("price_band") == "Hastane" else 1,
            r.get("ilce") or "",
            r.get("title") or "",
        )
    )
    return rows


def fetch_osm() -> list[dict]:
    q = """
    [out:json][timeout:120];
    area["name"="Bursa"]["admin_level"="4"]->.searchArea;
    (
      node["amenity"="veterinary"](area.searchArea);
      way["amenity"="veterinary"](area.searchArea);
      relation["amenity"="veterinary"](area.searchArea);
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
    for el in data.get("elements") or []:
        tags = el.get("tags") or {}
        name = (tags.get("name") or tags.get("name:tr") or "").strip()
        if not name:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        band, sub = infer_band(name)
        out.append(
            {
                "title": name,
                "title_key": _title_key(name),
                "lat": lat,
                "lng": lng,
                "phone": (tags.get("phone") or tags.get("contact:phone") or "")[:40],
                "web": (tags.get("website") or tags.get("contact:website") or "")[:280],
                "hours_text": (tags.get("opening_hours") or "")[:80],
                "subcategory": sub,
                "price_band": band,
                "source": "osm",
            }
        )
    return out


def load_curated() -> list[dict]:
    if os.path.isfile(CURATED_PATH):
        return json.loads(open(CURATED_PATH, encoding="utf-8").read())
    return []


def merge_all(bvho: list[dict], osm: list[dict], curated: list[dict]) -> list[dict]:
    by_slug = {r["slug"]: dict(r) for r in bvho}
    by_title = {_title_key(r["title"]): r["slug"] for r in bvho}

    for o in osm:
        tk = o.get("title_key") or _title_key(o["title"])
        slug = by_title.get(tk)
        if slug:
            base = by_slug[slug]
            base["lat"] = o["lat"]
            base["lng"] = o["lng"]
            if o.get("phone") and not base.get("phone"):
                base["phone"] = o["phone"]
            if o.get("web") and not base.get("web"):
                base["web"] = o["web"]
            if o.get("hours_text") and not base.get("hours_text"):
                base["hours_text"] = o["hours_text"]
            tags = list(base.get("tags") or [])
            if "osm" not in tags:
                tags.append("osm")
            base["tags"] = tags
        else:
            slug = slugify(o["title"])
            base_slug = slug
            i = 2
            while slug in by_slug:
                slug = f"{base_slug}-{i}"
                i += 1
            by_slug[slug] = {
                "slug": slug,
                "title": o["title"],
                "subcategory": o.get("subcategory") or "klinik",
                "price_band": o.get("price_band") or "Klinik",
                "ilce": norm_ilce(o.get("ilce") or "") or "Osmangazi",
                "address": "",
                "phone": o.get("phone") or "",
                "web": o.get("web") or "",
                "hours_text": o.get("hours_text") or "",
                "lat": o["lat"],
                "lng": o["lng"],
                "blurb": f"OpenStreetMap · {o['title']}",
                "tags": ["osm", "veteriner"],
                "featured": False,
                "source": "osm",
            }
            by_title[tk] = slug

    for c in curated:
        c = dict(c)
        slug = c.get("slug") or slugify(c["title"])
        c["slug"] = slug
        tk = _title_key(c["title"])
        if slug in by_slug:
            base = by_slug[slug]
        elif tk in by_title:
            base = by_slug[by_title[tk]]
            slug = base["slug"]
            c["slug"] = slug
        else:
            by_slug[slug] = c
            by_title[tk] = slug
            continue
        for k, v in c.items():
            if k in ("source", "extra") and k == "source":
                continue
            if k == "extra" and isinstance(v, dict):
                ex = dict(base.get("extra") or {})
                ex.update(v)
                base["extra"] = ex
                continue
            if v not in (None, "", [], {}):
                base[k] = v
        if c.get("lat") not in (None, "") and base.get("lat") in (None, ""):
            base["lat"] = c["lat"]
        if c.get("lng") not in (None, "") and base.get("lng") in (None, ""):
            base["lng"] = c["lng"]
        base["featured"] = bool(c.get("featured") or base.get("featured"))
        tags = list(base.get("tags") or [])
        for t in c.get("tags") or []:
            if t not in tags:
                tags.append(t)
        base["tags"] = tags

    rows = list(by_slug.values())
    rows.sort(
        key=lambda r: (
            0 if r.get("featured") else 1,
            0 if r.get("price_band") == "Hastane" else 1,
            0 if r.get("price_band") == "Poliklinik" else 2,
            r.get("ilce") or "",
            r.get("title") or "",
        )
    )
    return rows


def load_geocode_cache() -> dict:
    if os.path.isfile(GEOCODE_CACHE):
        return json.loads(open(GEOCODE_CACHE, encoding="utf-8").read())
    return {}


def save_geocode_cache(cache: dict) -> None:
    os.makedirs(DATA, exist_ok=True)
    with open(GEOCODE_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def geocode_rows(rows: list[dict], *, limit: int = 400) -> int:
    cache = load_geocode_cache()
    filled = 0
    for r in rows:
        if r.get("lat") not in (None, "") and r.get("lng") not in (None, ""):
            continue
        if filled >= limit:
            break
        addr = (r.get("address") or "").strip()
        if not addr:
            continue
        q = f"{addr}, {r.get('ilce') or 'Bursa'}, Bursa, Türkiye"
        if q in cache:
            hit = cache[q]
        else:
            url = NOMINATIM + "?" + urllib.parse.urlencode(
                {"q": q, "format": "json", "limit": 1, "countrycodes": "tr"}
            )
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BursaApp/1.0 (+https://bursaapp.com)"},
            )
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode())
                hit = data[0] if data else None
            except Exception:
                hit = None
            cache[q] = hit
            save_geocode_cache(cache)
            time.sleep(1.05)
        if hit:
            r["lat"] = float(hit["lat"])
            r["lng"] = float(hit["lon"])
            filled += 1
    return filled


def save_curated_snapshot(curated: list[dict]) -> None:
    if not curated:
        return
    os.makedirs(DATA, exist_ok=True)
    with open(CURATED_PATH, "w", encoding="utf-8") as f:
        json.dump(curated, f, ensure_ascii=False, indent=2)


def main() -> None:
    do_seed = "--seed" in sys.argv
    do_geocode = "--geocode" in sys.argv

    print("BVHO muayenehaneler çekiliyor…", flush=True)
    try:
        bvho = fetch_bvho()
        print(f"BVHO: {len(bvho)} klinik (tekilleştirilmiş)", flush=True)
    except Exception as exc:
        print(f"BVHO hata: {exc}", flush=True)
        sys.exit(1)

    print("OSM koordinat eşlemesi…", flush=True)
    try:
        osm = fetch_osm()
        print(f"OSM: {len(osm)} nokta", flush=True)
    except Exception as exc:
        print(f"OSM uyarı ({exc}) — BVHO yalnız", flush=True)
        osm = []

    curated = load_curated()
    if not os.path.isfile(CURATED_PATH) and os.path.isfile(VETS_PATH):
        old = json.loads(open(VETS_PATH, encoding="utf-8").read())
        curated = [r for r in old if r.get("copy") or r.get("featured")]
        if curated:
            save_curated_snapshot(curated)
            print(f"Curated yedek: {CURATED_PATH} ({len(curated)} kayıt)", flush=True)

    merged = merge_all(bvho, osm, curated)

    if do_geocode:
        need = sum(1 for r in merged if r.get("lat") in (None, "") and r.get("address"))
        print(f"Geocode: {need} adres bekliyor…", flush=True)
        n = geocode_rows(merged)
        print(f"Geocode: {n} koordinat eklendi", flush=True)

    os.makedirs(DATA, exist_ok=True)
    with open(VETS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    with_coords = sum(1 for r in merged if r.get("lat") not in (None, ""))
    print(f"Yazıldı: {VETS_PATH} ({len(merged)} veteriner · {with_coords} koordinatlı)", flush=True)
    ilce_counts: dict[str, int] = {}
    for r in merged:
        il = r.get("ilce") or "?"
        ilce_counts[il] = ilce_counts.get(il, 0) + 1
    for il in sorted(ilce_counts, key=lambda x: (-ilce_counts[x], x)):
        print(f"  {il}: {ilce_counts[il]}", flush=True)

    if do_seed:
        seed = os.path.join(_DIR, "seed_health.py")
        print("DB seed…", flush=True)
        subprocess.run([sys.executable, seed], check=True, cwd=os.path.dirname(_DIR))


if __name__ == "__main__":
    main()
