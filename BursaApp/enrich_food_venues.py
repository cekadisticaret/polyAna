#!/usr/bin/env python3
"""Yeme-içme: yüksek puanlı mekanlara gerçekçi kapak + menü.

Foto kaynağı: Wikimedia Commons (mekân adı / Bursa / yemek araması).
Menü: restaurants.json + alt tür şablonları (fiyatlar tahmini; mekan değişebilir).

  python3 enrich_food_venues.py --limit 80
  python3 enrich_food_venues.py --limit 20 --dry-run
  python3 enrich_food_venues.py --slug zennup-1844
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from media_cache import ensure_cached
from models import Place, SessionLocal, init_db, merge_place_extra

UA = {"User-Agent": "BursaApp/1.0 (https://bursaapp.com; food enrich)"}
STOCK_MARKERS = (
    "cafe-cover.jpg",
    "kahvalti-cover.jpg",
    "cantik-cover.jpg",
    "bar-cover.jpg",
    "meyhane-cover.jpg",
    "/static/food/iskender-",
    "/static/food/doner-",
    "/static/food/kofte-",
    "/static/food/ocakbasi-",
    "/static/food/pide-",
    "/static/food/lokanta-",
    "/static/food/fine-",
    "/static/food/anadolu-",
    "/static/food/konak-",
    "/static/food/ne-yenir-",
)

# Bilinen Commons dosyaları (mekâna yakın / yemek karesi)
CURATED: dict[str, list[str]] = {
    "kebapci-iskender-yilmaz": ["İskender Kebap.jpg", "Iskender Kebap Bursa Iskender.JPG"],
    "kebapci-iskender-mavi": ["Tarihi Mavi Dükkan İskender 04.jpg", "İskender Kebap.jpg"],
    "hacibey-iskender": ["Hacıbey fileto.jpg", "İskender Kebap.jpg"],
    "uludag-kebapcisi-cemal-cemil": ["İskender Kebap.jpg", "Iskender Kebap Bursa Iskender.JPG"],
    "kebapci-iskenderoglu": ["İskender Kebap.jpg"],
    "iskender-efendi-konagi": ["İskender Kebap.jpg"],
    "kebapci-huseyin-usta": ["İskender Kebap.jpg"],
    "kebapci-tamer": ["İskender Kebap.jpg"],
    "tarihi-bursa-carsi-kebapcisi": ["İskender Kebap.jpg", "Pideli kofte.jpg"],
    "cicek-izgara": ["Pideli kofte.jpg", "Pideli köfte - Istanbul.jpg"],
    "kebapci-idris": ["Pideli kofte.jpg"],
    "kayhan-koftecisi-eker": ["Pideli kofte.jpg"],
    "omur-koftecisi-1965": ["Pideli Köfte in Bursa.jpg", "Pideli kofte.jpg"],
    "pideli-kofte-osmangazi": ["Pideli kofte.jpg"],
    "inegol-restaurant": ["Pideli kofte.jpg"],
    "hasbihal-bahcesi-cumalikizik": ["Cumalıkızık 7112.jpg", "Turkey-1409 (2215838173) (2).jpg"],
    "kadiefendi-konagi-cumalikizik": ["Cumalıkızık Evleri.jpg", "Cumalıkızık.jpg"],
    "otantik-kahvalti-evi-cumalikizik": ["Cumalıkızık Taş Evleri.jpg"],
    "kahvalti-evi-cumalikizik": ["Cumalıkızık Sokakları.jpg"],
    "narli-bahce-cumalikizik": ["Cumalıkızık, Bursa 1.jpg"],
    "cumalikizik-sadiklar-konagi": ["Cumalıkızık Evleri.jpg"],
    "ballim-kafe-cumalikizik": ["Cumalıkızık.jpg"],
    "cumalikizik-doga-koy-kahvalti": ["Cumalıkızık, Bursa 6.jpg"],
    "cumalikizik-koy-kahvaltisi-baba-ocagi": ["Cumalıkızık, Bursa 7.jpg"],
    "misi-masal-kahvalti": ["TurkishBreakfastAtCesme.jpg"],
    "golyazi-faik-bey-konagi": ["Gölyazı.jpg", "Günbatımı, Gölyazı 2014-1.jpg"],
    "golyazi-balik": ["Gölyazı.jpg"],
    "balikci-golyazi": ["Gölyazı.jpg"],
    "pidecioglu-kayhan": ["Pide.jpg", "Turkish pide.jpg"],
    "pidecioglu-cantik-kayhan": ["Pide.jpg"],
    "zennup-1844": ["Turkish breakfast.jpg", "Meze.jpg"],
    "the-mantl-bursa": ["Grilled meat.jpg", "Turkish kebab.jpg"],
}

SUB_QUERIES = {
    "iskender": ["İskender Kebap Bursa", "İskender kebap plate"],
    "kebap": ["Bursa kebab", "Turkish kebab grill"],
    "inegol-kofte": ["Pideli köfte", "İnegöl köfte"],
    "pide": ["Turkish pide", "Pide fırın"],
    "cantik": ["Bursa cantık", "Turkish pide"],
    "balik": ["Turkish fish restaurant", "Grilled fish plate"],
    "kahvalti": ["Turkish breakfast serpme", "Cumalıkızık kahvaltı"],
    "restoran": ["Turkish restaurant interior", "Anatolian cuisine plate"],
    "meyhane": ["Turkish meze rakı", "Meze platter"],
    "cafe": ["Specialty coffee shop", "Coffee barista pour"],
    "bar": ["Cocktail bar interior", "Bar counter night"],
    "burger": ["Gourmet burger plate", "Cheeseburger close up"],
}

MENU_TMPL: dict[str, list[str]] = {
    "iskender": [
        "İskender (porsiyon) | 420–520 TL",
        "Pideli İskender | 450–560 TL",
        "Ayran | 40–55 TL",
        "Künefe / sütlü tatlı | 180–260 TL",
    ],
    "kebap": [
        "Bursa kebabı / döner porsiyon | 320–420 TL",
        "Dürüm | 220–300 TL",
        "İskender usulü | 400–500 TL",
        "Ayran / şalgam | 40–60 TL",
    ],
    "inegol-kofte": [
        "Pideli köfte | 360–450 TL",
        "Porsiyon köfte | 320–400 TL",
        "Ayran | 40–55 TL",
        "Salata | 80–120 TL",
    ],
    "pide": [
        "Kıymalı pide | 280–360 TL",
        "Kuşbaşılı pide | 320–400 TL",
        "Kaşarlı pide | 260–340 TL",
        "Ayran | 40–55 TL",
    ],
    "cantik": [
        "Cantık (kıymalı/kaşarlı) | 180–260 TL",
        "Karışık cantık | 220–300 TL",
        "Ayran | 40–55 TL",
    ],
    "balik": [
        "Günün balığı (porsiyon) | 550–900 TL",
        "Karides / kalamar | 420–650 TL",
        "Meze tabağı | 280–420 TL",
        "Salata | 120–180 TL",
    ],
    "kahvalti": [
        "Serpme kahvaltı (2 kişilik) | 700–1.100 TL",
        "Menemen / yumurta | 180–280 TL",
        "Pişi / gözleme | 120–200 TL",
        "Çay | 25–40 TL",
    ],
    "restoran": [
        "Günün menüsü | 450–750 TL",
        "Izgara / ana yemek | 480–850 TL",
        "Çorba | 120–180 TL",
        "Tatlı | 180–280 TL",
    ],
    "meyhane": [
        "Meze tabağı | 350–550 TL",
        "Balık / ızgara | 550–950 TL",
        "Rakı (kadeh) | şube fiyatı",
        "Salata | 120–180 TL",
    ],
    "cafe": [
        "Espresso / filtre | 90–150 TL",
        "Latte / cappuccino | 120–180 TL",
        "Cheesecake / tatlı | 180–280 TL",
        "Tost / sandwich | 200–320 TL",
    ],
    "bar": [
        "Kokteyl | 350–550 TL",
        "Bira | 180–280 TL",
        "Snack / tabak | 250–420 TL",
    ],
    "burger": [
        "Klasik burger | 220–320 TL",
        "Double / smash | 300–420 TL",
        "Patates | 100–160 TL",
        "İçecek | 40–90 TL",
    ],
}


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def is_stock(img: str) -> bool:
    s = (img or "").lower()
    if not s:
        return True
    return any(m in s for m in STOCK_MARKERS)


def commons_file_url(name: str, width: int = 1400) -> str:
    return (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        + urllib.parse.quote(name)
        + f"?width={width}"
    )


def commons_search(q: str, limit: int = 8) -> list[dict]:
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{q} filetype:bitmap",
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "iiurlwidth": 1400,
            "format": "json",
        }
    )
    data = json.loads(_get(url))
    ban = (
        "pdf",
        "svg",
        "map",
        "logo",
        "icon",
        "diagram",
        "chart",
        "flag",
        "coat of",
        "capsella",
        "plant",
        "flower",
        "herbarium",
        "botanic",
        "species",
        "insect",
        "coin",
        "stamp",
        "medal",
        "portrait of",
        "cemetery",
        "grave",
        "bursa-pastoris",
        "bursa pastoris",
    )
    out: list[dict] = []
    for p in (data.get("query") or {}).get("pages", {}).values():
        title = p.get("title") or ""
        low = title.lower()
        if any(b in low for b in ban):
            continue
        ii = (p.get("imageinfo") or [{}])[0]
        if not str(ii.get("mime") or "").startswith("image/"):
            continue
        u = ii.get("thumburl") or ii.get("url")
        if not u:
            continue
        out.append({"title": title, "url": u, "size": int(ii.get("size") or 0)})
    return out


def _tokens(s: str) -> list[str]:
    s = re.sub(r"[^0-9a-zA-ZçğıöşüÇĞİÖŞÜ\s]", " ", (s or "").lower())
    stop = {"bursa", "the", "ve", "cafe", "kafe", "restaurant", "restoran", "usta", "tarihi"}
    return [t for t in s.split() if len(t) > 2 and t not in stop]


def score_hit(place_title: str, file_title: str, sub: str) -> float:
    pt = _tokens(place_title)
    ft = _tokens(file_title.replace("File:", ""))
    if not ft:
        return 0.0
    fl = file_title.lower()
    if any(b in fl for b in ("capsella", "bursa-pastoris", "bursa pastoris", "herbarium")):
        return 0.0
    overlap = len(set(pt) & set(ft))
    ratio = SequenceMatcher(None, " ".join(pt), " ".join(ft)).ratio()
    bonus = 0.0
    if "bursa" in fl and "pastoris" not in fl:
        bonus += 0.15
    if sub == "iskender" and "iskender" in fl:
        bonus += 0.35
    if sub == "inegol-kofte" and ("köfte" in fl or "kofte" in fl or "pideli" in fl):
        bonus += 0.3
    if sub == "kahvalti" and (
        "kahvalt" in fl or "breakfast" in fl or "cumalıkızık" in fl or "cumalikizik" in fl
    ):
        bonus += 0.25
    if sub == "cantik" and "cantik" in fl:
        bonus += 0.3
    if sub in ("burger", "fast-food") and ("burger" in fl or "hamburger" in fl or "cheeseburger" in fl):
        bonus += 0.25
    # başlıkta mekân adı hiç yoksa ve sadece genel yemekse düşük tut
    score = overlap * 0.25 + ratio + bonus
    if overlap == 0 and bonus < 0.3:
        score *= 0.55
    return score


def pick_photo(p: Place) -> tuple[str | None, str]:
    """Dönüş: (cached public url, source note)."""
    slug = p.slug
    sub = (p.subcategory or "").strip() or "restoran"
    # 1) curated
    for name in CURATED.get(slug, []):
        url = commons_file_url(name)
        local = ensure_cached(url, category="food-venue", filename=f"{slug}.jpg", min_bytes=8000)
        if local:
            return local, f"commons:{name}"
        time.sleep(0.2)
    # 2) search by title
    queries = [f"{p.title} Bursa", p.title]
    queries += SUB_QUERIES.get(sub, ["Turkish food"])[:2]
    best_url = None
    best_score = 0.35
    best_note = ""
    for q in queries:
        time.sleep(0.35)
        try:
            hits = commons_search(q)
        except Exception:
            continue
        for h in hits:
            sc = score_hit(p.title, h["title"], sub)
            # subcategory dish fallback: lower bar
            if sc < best_score and q in SUB_QUERIES.get(sub, []):
                if h["size"] > 200_000 and sc >= 0.2:
                    sc = 0.36
            if sc > best_score:
                best_score = sc
                best_url = h["url"]
                best_note = f"search:{q}|{h['title']}"
        if best_score >= 0.7:
            break
    if best_url:
        local = ensure_cached(best_url, category="food-venue", filename=f"{slug}.jpg", min_bytes=8000)
        if local:
            return local, best_note
    return None, ""


def load_json_menus() -> dict[str, str]:
    path = os.path.join(_DIR, "data", "restaurants.json")
    out: dict[str, str] = {}
    try:
        rows = json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return out
    for raw in rows or []:
        slug = raw.get("slug")
        menu = raw.get("menu") or []
        if not slug or not menu:
            continue
        lines = []
        for i in menu:
            if isinstance(i, dict):
                lines.append(
                    f"{i.get('name','')} | {i.get('price','')} | {i.get('note','')}".strip(" |")
                )
            else:
                lines.append(str(i))
        out[slug] = "\n".join(lines)
    return out


def menu_for(p: Place, json_menus: dict[str, str]) -> tuple[str, str]:
    if (p.menu_text or "").strip():
        return p.menu_text.strip(), "keep"
    if p.slug in json_menus:
        return json_menus[p.slug], "restaurants.json"
    sub = (p.subcategory or "restoran").strip()
    lines = MENU_TMPL.get(sub) or MENU_TMPL["restoran"]
    note = "Not: fiyatlar yaklaşık (2026); güncel için mekânı ara."
    return "\n".join(lines + [note]), f"tmpl:{sub}"


def select_places(db, *, limit: int, slug: str | None) -> list[Place]:
    q = db.query(Place).filter(Place.category == "food", Place.status == "approved")
    if slug:
        p = q.filter(Place.slug == slug).first()
        return [p] if p else []
    rows = q.all()

    def score(p: Place) -> float:
        return float(p.rating_admin or p.rating_avg or 0)

    ranked = sorted(rows, key=score, reverse=True)
    out: list[Place] = []
    for p in ranked:
        sub = (p.subcategory or "").strip()
        if sub in (
            "restoran",
            "iskender",
            "kebap",
            "inegol-kofte",
            "balik",
            "pide",
            "cantik",
            "kahvalti",
            "meyhane",
            "burger",
        ) or (sub in ("cafe", "bar") and score(p) >= 4.55):
            out.append(p)
        if len(out) >= limit:
            break
    return out


def run(*, limit: int, slug: str | None, dry: bool, force_photo: bool) -> None:
    init_db()
    json_menus = load_json_menus()
    db = SessionLocal()
    try:
        places = select_places(db, limit=limit, slug=slug)
        print(f"aday={len(places)} dry={dry}")
        n_photo = n_menu = n_skip = 0
        for p in places:
            changed = False
            # photo
            need_photo = force_photo or is_stock(p.img_url or "")
            if need_photo:
                path, src = pick_photo(p)
                if path:
                    print(f"PHOTO {p.slug} <- {src}")
                    if not dry:
                        p.img_url = path
                        merge_place_extra(p, {"photo_source": src, "photo_enriched_at": time.strftime("%Y-%m-%d")})
                    n_photo += 1
                    changed = True
                else:
                    print(f"PHOTO miss {p.slug}")
            # menu
            text, msrc = menu_for(p, json_menus)
            if msrc != "keep":
                print(f"MENU  {p.slug} <- {msrc}")
                if not dry:
                    p.menu_text = text
                    merge_place_extra(p, {"menu_source": msrc})
                n_menu += 1
                changed = True
            if not changed:
                n_skip += 1
        if not dry:
            db.commit()
        print(f"done photo={n_photo} menu={n_menu} skip={n_skip}")
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--slug", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-photo", action="store_true")
    args = ap.parse_args()
    run(
        limit=max(1, args.limit),
        slug=(args.slug or "").strip() or None,
        dry=bool(args.dry_run),
        force_photo=bool(args.force_photo),
    )


if __name__ == "__main__":
    main()
