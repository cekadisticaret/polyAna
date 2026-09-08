#!/usr/bin/env python3
"""Kamp yerlerini camps.json'dan zenginleştir + Wikimedia foto."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import tags_dump
from models import Place, SessionLocal, init_db, merge_place_extra

UA = {"User-Agent": "BursaApp/1.0 (https://bursaapp.com; city guide)"}
CAMP_DIR = os.path.join(_DIR, "static", "camp")
VISIT_DIR = os.path.join(_DIR, "static", "visit")
MIN_KEEP = 40000

# Slug başına Commons arama — genel "Bursa" yerine özel sorgular
CAMP_QUERIES: dict[str, list[str]] = {
    "cobankaya-kamp": ["Çobankaya Uludağ", "Uludağ National Park camping", "Çobankaya plateau"],
    "sarialan-kamp": ["Sarıalan Uludağ", "Uludağ Sarıalan plateau", "Uludağ cable car"],
    "golyazi-kamp": ["Gölyazı Uluabat Lake", "Golyazi peninsula sunset"],
    "kapanca-korsan-limani": ["Kapanca Mudanya", "Korsan Limanı Mudanya", "Mudanya coast Turkey"],
    "eskel-kamp": ["Eşkel Mudanya beach", "Esence Mudanya coast", "Mudanya camping"],
    "iznik-golu-kamp": ["Lake Iznik Turkey", "İznik Gölü", "Iznik lake camping"],
    "dagyenice-kamp": ["Dağyenice Göleti", "Dagyenice pond Bursa"],
    "suuctu-kamp": ["Suuçtu waterfall", "Suuctu waterfall Mustafakemalpaşa"],
    "kocayayla-kamp": ["Kocayayla Keles", "Kocayayla plateau Bursa"],
    "ericek-goleti-kamp": ["Ericek Göleti Gürsu", "Ericek pond Bursa"],
    "sadagi-kamp": ["Sadağı Canyon Orhaneli", "Sadagi canyon Bursa"],
    "oylat-kamp": ["Oylat cave Inegol", "Oylat thermal forest"],
    "misi-kamp": ["Misi village Bursa", "Gumushtepe Misi Nilufer"],
    "karabelen-kamp": ["Karabelen Uludağ", "Uludağ national park entrance"],
    "kirazliyayla-kamp": ["Kirazlıyayla Uludağ", "Uludağ Kirazlı plateau"],
    "kayapa-kamp": ["Kayapa Göleti Bursa", "Kayapa pond Nilufer"],
    "barakli-goleti-kamp": ["Baraklı Göleti Keles", "Barakli pond Bursa"],
    "softabogan-kamp": ["Softaboğan waterfall Uludağ", "Softabogan waterfall Bursa"],
    "karacabey-longoz-kamp": ["Karacabey Longoz", "Karacabey floodplain forest"],
    "saitabat-kamp": ["Saitabat waterfall Kestel", "Saitabat waterfall Bursa"],
    "sansarak-kanyon-kamp": ["Sansarak canyon Iznik", "Sansarak kanyonu"],
    "gokoz-kamp": ["Gököz Natural Park Keles", "Gokoz Keles Bursa"],
    "ketenlik-yayla-kamp": ["Ketenlik Yaylası Uludağ", "Uludağ plateau camping"],
    "dalyan-golu-kamp": ["Dalyan Lake Karacabey", "Karacabey Dalyan longoz"],
    "caylak-selalesi-kamp": ["Çaylak Şelalesi Susurluk", "Caylak waterfall Balikesir"],
    "seytan-sofrasi-kamp": ["Şeytan Sofrası Ayvalık", "Devil's Table Ayvalik sunset"],
    "ortunc-koyu-kamp": ["Ortunç Bay Cunda", "Ortunc koyu Ayvalik"],
    "kucukova-koyu-kamp": ["Küçükova bay Erdek", "Kapıdağ peninsula beach"],
    "hasan-boguldu-kamp": ["Hasan Boğuldu Edremit", "Hasanboguldu pond Kazdagi"],
    "kapidag-camping": ["Kapıdağ Erdek camping", "Kapidag peninsula Erdek"],
    "kazdagi-kamp": ["Kazdağı National Park", "Mount Ida forest camping Turkey"],
    "sarimsakli-kamp": ["Sarımsaklı beach Ayvalık", "Sarimsakli Ayvalik"],
    "cataldag-goleti-kamp": ["Çataldağ Göleti Susurluk", "Cataldag pond Balikesir"],
    "yalintas-kamp": ["Yalıntaş Uludağ camping", "Uludağ Yalıntaş campsite"],
    "yalintas-goleti-kamp": ["Yalıntaş Göleti Uludağ", "Yalintas pond Uludag"],
    "kilimli-golu-kamp": ["Kilimli Gölü Uludağ", "Kilimli lake Uludag"],
    "alacam-yayla-kamp": ["Alaçam Yaylası Uludağ", "Alacam plateau Uludag"],
    "sudusen-selalesi-kamp": ["Sudüşen Şelalesi Uludağ", "Sudusen waterfall Uludag"],
    "karacabey-yenikoy-kamp": ["Karacabey Yeniköy camping", "Karacabey forest camping"],
    "golkuk-uludag-kamp": ["Gölcük lake Uludağ", "Uludağ Gölcük pond"],
    "trilye-sahil-kamp": ["Trilye Mudanya", "Tirilye fishing village Turkey"],
    "alic-yayla-kamp": ["Alıç Yaylası Keles", "Alic plateau Bursa"],
}

# Commons başarısız olursa — her slug farklı visit görseli
CAMP_COPY: dict[str, str] = {
    "eskel-kamp": "tirilye",
    "kapanca-korsan-limani": "mudanya-mutareke-evi",
    "kayapa-kamp": "soganli-botanik",
    "kocayayla-kamp": "cumalikizik",
    "kirazliyayla-kamp": "panorama-1326",
    "gokoz-kamp": "oylat",
    "ketenlik-yayla-kamp": "inkaya-cinari",
    "kazdagi-kamp": "karacabey-longozu",
    "dalyan-golu-kamp": "karacabey-longozu",
    "saitabat-kamp": "suuctu",
    "softabogan-kamp": "teleferik",
    "barakli-goleti-kamp": "uludag",
    "ericek-goleti-kamp": "soganli-botanik",
    "iznik-golu-kamp": "iznik-surlar",
    "trilye-sahil-kamp": "tirilye",
    "alic-yayla-kamp": "cumalikizik",
    "yalintas-kamp": "uludag",
    "yalintas-goleti-kamp": "teleferik",
    "kilimli-golu-kamp": "uludag",
    "alacam-yayla-kamp": "panorama-1326",
    "sudusen-selalesi-kamp": "suuctu",
    "karacabey-yenikoy-kamp": "karacabey-longozu",
    "kayapa-kamp": "soganli-botanik",
    "barakli-goleti-kamp": "muradiye",
    "saitabat-kamp": "suuctu",
    "sansarak-kanyon-kamp": "iznik-surlar",
    "caylak-selalesi-kamp": "suuctu",
    "ortunc-koyu-kamp": "tirilye",
    "kapidag-camping": "tirilye",
    "cataldag-goleti-kamp": "golyazi",
}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def commons_search(q: str) -> str | None:
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": q,
            "gsrnamespace": 6,
            "gsrlimit": 12,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "iiurlwidth": 1400,
            "format": "json",
        }
    )
    data = json.loads(_get(url))
    ban = ("bursaray", "siemens", "metro", ".pdf", ".svg", "logo", "map", "flag", "coat")
    best = None
    best_size = 0
    for p in (data.get("query") or {}).get("pages", {}).values():
        title = (p.get("title") or "").lower()
        if any(b in title for b in ban):
            continue
        ii = (p.get("imageinfo") or [{}])[0]
        if not str(ii.get("mime") or "").startswith("image/"):
            continue
        sz = int(ii.get("size") or 0)
        u = ii.get("thumburl") or ii.get("url")
        if u and sz >= best_size:
            best, best_size = u, sz
    return best


def file_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_index(exclude_slug: str | None = None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not os.path.isdir(CAMP_DIR):
        return out
    for fn in os.listdir(CAMP_DIR):
        if not fn.endswith(".jpg"):
            continue
        slug = fn[:-4]
        if slug == exclude_slug:
            continue
        path = os.path.join(CAMP_DIR, fn)
        if os.path.getsize(path) > 8000:
            out[file_md5(path)] = slug
    return out


def is_dup(path: str, slug: str, idx: dict[str, str]) -> bool:
    if not os.path.isfile(path):
        return False
    owner = idx.get(file_md5(path))
    return bool(owner and owner != slug)


def save_img(slug: str, url: str, idx: dict[str, str]) -> str:
    dest = os.path.join(CAMP_DIR, f"{slug}.jpg")
    raw = _get(url)
    if len(raw) < 8000:
        return ""
    os.makedirs(CAMP_DIR, exist_ok=True)
    open(dest, "wb").write(raw)
    if is_dup(dest, slug, idx):
        os.remove(dest)
        return ""
    return f"/static/camp/{slug}.jpg"


def copy_visit(slug: str, base: str, idx: dict[str, str], allow_dup: bool = False) -> str:
    src = os.path.join(VISIT_DIR, f"{base}.jpg")
    dest = os.path.join(CAMP_DIR, f"{slug}.jpg")
    if not os.path.isfile(src):
        return ""
    os.makedirs(CAMP_DIR, exist_ok=True)
    shutil.copy(src, dest)
    if not allow_dup and is_dup(dest, slug, idx):
        os.remove(dest)
        return ""
    print("copy", slug, "<-", base)
    return f"/static/camp/{slug}.jpg"


def build_queries(raw: dict) -> list[str]:
    slug = raw["slug"]
    seen: set[str] = set()
    out: list[str] = []
    for q in (
        *(raw.get("search_queries") or []),
        raw.get("search"),
        raw.get("wiki"),
        *(CAMP_QUERIES.get(slug) or []),
        f"{raw.get('title')} camping Turkey",
        f"{raw.get('title')} Bursa",
    ):
        q = (q or "").strip()
        if not q or q.lower() in seen:
            continue
        seen.add(q.lower())
        out.append(q)
    return out


def photo_for(raw: dict, force: bool = False, fix_dupes: bool = False) -> str:
    slug = raw["slug"]
    dest = os.path.join(CAMP_DIR, f"{slug}.jpg")
    idx = hash_index(exclude_slug=slug)

    if os.path.isfile(dest) and os.path.getsize(dest) > MIN_KEEP:
        if not force and not fix_dupes:
            return f"/static/camp/{slug}.jpg"
        if not force and fix_dupes and not is_dup(dest, slug, idx):
            return f"/static/camp/{slug}.jpg"

    if os.path.isfile(dest) and (force or fix_dupes):
        bak = dest + ".bak"
        try:
            shutil.copy2(dest, bak)
        except OSError:
            bak = ""

    for q in build_queries(raw):
        time.sleep(0.35)
        try:
            url = commons_search(q)
        except Exception as e:
            print("search", slug, q[:40], e)
            continue
        if not url:
            continue
        try:
            path = save_img(slug, url, idx)
            if path:
                print("dl", slug, "<-", q[:50])
                return path
        except Exception as e:
            print("dl fail", slug, e)

    copy = raw.get("copy") or CAMP_COPY.get(slug)
    if copy:
        path = copy_visit(slug, copy, idx)
        if path:
            if os.path.isfile(dest + ".bak"):
                os.remove(dest + ".bak")
            return path
        path = copy_visit(slug, copy, idx, allow_dup=True)
        if path:
            if os.path.isfile(dest + ".bak"):
                os.remove(dest + ".bak")
            return path

    bak = dest + ".bak"
    if os.path.isfile(bak):
        shutil.move(bak, dest)
        print("restore", slug)
        return f"/static/camp/{slug}.jpg"

    if os.path.isfile(dest) and os.path.getsize(dest) > 8000:
        return f"/static/camp/{slug}.jpg"
    print("NO PHOTO", slug)
    return ""


def upsert(db, raw: dict, img: str) -> None:
    body = (raw.get("body") or raw.get("blurb") or "")[:8000]
    fields = dict(
        title=raw["title"][:200],
        category="camp",
        subcategory=(raw.get("subcategory") or "")[:48],
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or "",
        phone=raw.get("phone") or "",
        web=raw.get("web") or "",
        hours_text=raw.get("hours_text") or "",
        price_band=raw.get("price_band") or "",
        blurb=(raw.get("blurb") or "")[:400],
        body=body,
        img_url=img or "",
        tags=tags_dump(raw.get("tags") or []),
        featured=bool(raw.get("featured")),
        status="approved",
        lat=raw.get("lat"),
        lng=raw.get("lng"),
        rating_admin=raw.get("rating_admin"),
    )
    p = db.query(Place).filter(Place.slug == raw["slug"]).first()
    if p is None:
        p = Place(slug=raw["slug"], **fields)
        db.add(p)
        db.flush()
    else:
        for k, v in fields.items():
            if k in ("lat", "lng") and v is None:
                continue
            if k == "rating_admin" and v is None:
                continue
            setattr(p, k, v)
    city = raw.get("city") or ""
    merge_place_extra(
        p,
        {
            "facilities": raw.get("facilities") or [],
            "tips": raw.get("tips") or "",
            "vibe": raw.get("vibe") or "",
            "source": "camp_research_2026",
            "city": city,
        },
    )


def main() -> None:
    force = "--force-photos" in sys.argv
    fix_dupes = "--fix-dupes" in sys.argv or force
    init_db()
    rows = json.loads(open(os.path.join(_DIR, "data", "camps.json"), encoding="utf-8").read())
    db = SessionLocal()
    try:
        keep = {r["slug"] for r in rows}
        for raw in rows:
            img = photo_for(raw, force=force, fix_dupes=fix_dupes)
            upsert(db, raw, img)
        orphans = [
            p.slug
            for p in db.query(Place).filter(Place.category == "camp", Place.status == "approved")
            if p.slug not in keep
        ]
        if orphans:
            print("orphan camps (kept):", orphans)
        db.commit()
        print("camp n", len(rows))
    finally:
        db.close()


if __name__ == "__main__":
    main()
