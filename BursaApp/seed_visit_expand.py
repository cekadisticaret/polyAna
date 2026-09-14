#!/usr/bin/env python3
"""Gezilecek genişletme: OSM turizm/tarih/doğa + meşhur noktalar.

  python3 seed_visit_expand.py
"""
from __future__ import annotations

import json
import os
import sys
import time

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import ILCELER, slugify, tags_dump
from models import Place, SessionLocal, init_db
from seed_food_expand import overpass

UA = "BursaApp/1.0 (https://bursaapp.com)"
# İl sınırına yakın kutu — İznik / Karacabey / MKPaşa dahil
BBOX = "39.90,28.10,40.55,29.90"

SUB_IMG = {
    "cami": "/static/visit/ulu-cami.jpg",
    "kilise": "/static/visit/tirilye.jpg",
    "kulliye": "/static/visit/muradiye.jpg",
    "turbe": "/static/visit/yesil-turbe.jpg",
    "han": "/static/visit/koza-han.jpg",
    "hisar": "/static/visit/tophane.jpg",
    "antik": "/static/visit/iznik-surlar.jpg",
    "anit": "/static/visit/inkaya-cinari.jpg",
    "muze": "/static/visit/panorama-1326.jpg",
    "park": "/static/visit/soganli-botanik.jpg",
    "doga": "/static/visit/suuctu.jpg",
    "selale": "/static/visit/suuctu.jpg",
    "dag": "/static/visit/uludag.jpg",
    "gol": "/static/visit/golyazi.jpg",
    "koy": "/static/visit/cumalikizik.jpg",
    "kaplica": "/static/visit/eski-kaplica.jpg",
    "magara": "/static/visit/oylat.jpg",
    "manzara": "/static/visit/tophane.jpg",
    "hat": "/static/visit/teleferik.jpg",
}

EXISTING_SUB = {
    "ulu-cami": "cami",
    "koza-han": "han",
    "hanlar-kapalicarsi": "han",
    "tophane": "hisar",
    "kale-sokak": "hisar",
    "muradiye": "kulliye",
    "eski-kaplica": "kaplica",
    "inkaya-cinari": "doga",
    "panorama-1326": "muze",
    "uludag": "dag",
    "teleferik": "hat",
    "yesil-turbe": "turbe",
    "yesil-cami": "cami",
    "emir-sultan": "kulliye",
    "irgandi": "han",
    "cumalikizik": "koy",
    "golyazi": "koy",
    "misi": "koy",
    "soganli-botanik": "park",
    "tirilye": "koy",
    "oylat": "magara",
    "suuctu": "selale",
    "iznik-surlar": "antik",
}

CURATED = [
    {"title": "Karagöz Müzesi", "ilce": "Osmangazi", "address": "Çekirge Cad., Osmangazi", "lat": 40.203, "lng": 29.038, "sub": "muze", "rating": 4.4, "featured": False, "blurb": "Karagöz-Hacivat gölge oyunu koleksiyonu. Çekirge hattında kısa durak."},
    {"title": "Tofaş Anadolu Arabaları Müzesi", "ilce": "Yıldırım", "address": "Umurbey, Yıldırım", "lat": 40.1832, "lng": 29.0755, "sub": "muze", "rating": 4.6, "featured": True, "blurb": "Restöre ipek fabrikası. Fayton, kağnı, klasik otomobil. Irgandı yanında.", "img": "/static/visit/tofas-anadolu-arabalari-muzesi.jpg"},
    {"title": "Bursa Kent Müzesi", "ilce": "Osmangazi", "address": "Heykel, Atatürk Cad., Osmangazi", "lat": 40.1836, "lng": 29.0612, "sub": "muze", "rating": 4.5, "featured": False, "blurb": "Şehir tarihi, Hanlar bölgesi. Ulu Cami–Heykel aksında."},
    {"title": "Hüsnü Züber Evi", "ilce": "Osmangazi", "address": "Hisar, Osmangazi", "lat": 40.1862, "lng": 29.0574, "sub": "muze", "rating": 4.5, "featured": False, "blurb": "Osmanlı evi müze. Tophane–Kale Sokak yürüyüşünde."},
    {"title": "Atatürk Evi Müzesi", "ilce": "Osmangazi", "address": "Çekirge, Osmangazi", "lat": 40.2014, "lng": 29.0332, "sub": "muze", "rating": 4.3, "featured": False, "blurb": "Atatürk’ün Bursa konaklaması. Çekirge kaplıca hattı."},
    {"title": "Türk İslam Eserleri Müzesi", "ilce": "Yıldırım", "address": "Yeşil Medrese, Yıldırım", "lat": 40.1814, "lng": 29.0748, "sub": "muze", "rating": 4.5, "featured": False, "blurb": "Yeşil Medrese. Çini, hat, vakıf eserleri. Yeşil Türbe yanı."},
    {"title": "Uluumay Osmanlı Halk Kıyafetleri Müzesi", "ilce": "Osmangazi", "address": "Muradiye, Osmangazi", "lat": 40.1912, "lng": 29.0458, "sub": "muze", "rating": 4.4, "featured": False, "blurb": "Kaftan ve yöresel giysi. Muradiye külliyesi bahçesinde."},
    {"title": "Mudanya Mütareke Evi", "ilce": "Mudanya", "address": "Mütareke, 12 Eylül Cd. No:8, Mudanya", "lat": 40.3764, "lng": 28.8832, "sub": "muze", "rating": 4.5, "featured": True, "blurb": "1922 ateşkes evi. Sahil yürüyüşüyle birlikte.", "img": "/static/visit/mudanya-mutareke-evi.jpg"},
    {"title": "Merinos Parkı", "ilce": "Osmangazi", "address": "Merinos / Atatürk Kongre Kültür Merkezi", "lat": 40.1955, "lng": 29.0554, "sub": "park", "rating": 4.5, "featured": False, "blurb": "Eski merinos fabrikası parkı + AKKM. Şehir içi yeşil."},
    {"title": "Kültürpark", "ilce": "Osmangazi", "address": "Çekirge Cad. / Kültürpark, Osmangazi", "lat": 40.1988, "lng": 29.0485, "sub": "park", "rating": 4.3, "featured": False, "blurb": "Fuar alanı, gölet, yürüyüş. Çekirge altı."},
    {"title": "Hüdavendigar Camii", "ilce": "Osmangazi", "address": "Çekirge, Osmangazi", "lat": 40.2018, "lng": 29.0314, "sub": "cami", "rating": 4.6, "featured": False, "blurb": "I. Murad külliyesi. Çekirge sırtı, erken Osmanlı.", "img": "/static/visit/hudavendigar-camii.jpg"},
    {"title": "Yıldırım Bayezid Camii", "ilce": "Yıldırım", "address": "Yıldırım, Yıldırım Bayezid Cad.", "lat": 40.1874, "lng": 29.0862, "sub": "cami", "rating": 4.5, "featured": False, "blurb": "Yıldırım külliyesi. Şehir doğusu, Yeşil’den ayrı durak."},
    {"title": "Orhan Camii", "ilce": "Osmangazi", "address": "Hanlar bölgesi, Osmangazi", "lat": 40.1839, "lng": 29.0626, "sub": "cami", "rating": 4.6, "featured": False, "blurb": "Orhan Gazi camisi. Koza Han–Ulu Cami üçgeni."},
    {"title": "Osman Gazi Türbesi", "ilce": "Osmangazi", "address": "Tophane Parkı, Osmangazi", "lat": 40.1867, "lng": 29.0601, "sub": "turbe", "rating": 4.7, "featured": True, "blurb": "Osman Gazi. Saat kulesi yanı, Hisar sırtı."},
    {"title": "Orhan Gazi Türbesi", "ilce": "Osmangazi", "address": "Tophane Parkı, Osmangazi", "lat": 40.1865, "lng": 29.0604, "sub": "turbe", "rating": 4.7, "featured": False, "blurb": "Orhan Gazi. Osman Gazi türbesinin yanı başında."},
    {"title": "Saltanat Kapısı", "ilce": "Osmangazi", "address": "Hisar / Kale, Osmangazi", "lat": 40.1852, "lng": 29.0564, "sub": "hisar", "rating": 4.4, "featured": False, "blurb": "Bursa kalesi kapısı. Kale Sokak yürüyüşü."},
    {"title": "Saitabat Şelalesi", "ilce": "Kestel", "address": "Saitabat, Kestel", "lat": 40.155, "lng": 29.248, "sub": "selale", "rating": 4.5, "featured": True, "blurb": "Kestel dağında şelale ve mesire. Hafta sonu piknik."},
    {"title": "Hamamlıkızık", "ilce": "Yıldırım", "address": "Hamamlıkızık Köyü, Yıldırım", "lat": 40.164, "lng": 29.186, "sub": "koy", "rating": 4.3, "featured": False, "blurb": "Cumalıkızık’ın komşu Osmanlı köyü. Daha sakin sokak."},
    {"title": "İznik Ayasofya", "ilce": "İznik", "address": "İznik merkez", "lat": 40.4291, "lng": 29.7214, "sub": "antik", "rating": 4.6, "featured": True, "blurb": "Nikaia Ayasofyası. Konsil tarihi, cami olarak da ziyaret."},
    {"title": "İznik Lefke Kapısı", "ilce": "İznik", "address": "Lefke Kapı, İznik", "lat": 40.4308, "lng": 29.7315, "sub": "antik", "rating": 4.5, "featured": False, "blurb": "Doğu sur kapısı. İznik sur turunun duraklarından."},
    {"title": "İznik Yeşil Cami", "ilce": "İznik", "address": "Yeşil Cami, İznik", "lat": 40.4302, "lng": 29.7206, "sub": "cami", "rating": 4.6, "featured": False, "blurb": "Erken Osmanlı, minare çinisi. İznik merkez."},
    {"title": "Karacabey Longozu", "ilce": "Karacabey", "address": "Yeniköy / Karadağ, Karacabey", "lat": 40.268, "lng": 28.452, "sub": "doga", "rating": 4.5, "featured": True, "blurb": "Kuş cenneti, su basar orman. Kuş gözlem ve yürüyüş.", "img": "/static/visit/karacabey-longozu.jpg"},
    {"title": "Güzelyalı", "ilce": "Mudanya", "address": "Güzelyalı sahil, Mudanya", "lat": 40.358, "lng": 28.918, "sub": "koy", "rating": 4.4, "featured": False, "blurb": "Mudanya–Bursa sahil beldesi. Yürüyüş + deniz."},
    {"title": "İznik Gölü", "ilce": "İznik", "address": "İznik göl kıyısı", "lat": 40.426, "lng": 29.708, "sub": "gol", "rating": 4.6, "featured": False, "blurb": "Göl kenarı, gün batımı. Sur ve çini ile aynı gün."},
]


def guess_ilce(lat: float | None, lng: float | None) -> str:
    if lat is None or lng is None:
        return "Osmangazi"
    if lng >= 29.50:
        return "İznik" if lat >= 40.28 else "Yenişehir"
    if lat >= 40.40:
        if lng < 29.08:
            return "Mudanya"
        if lng < 29.28:
            return "Gemlik"
        return "Orhangazi"
    if lat >= 40.32:
        return "Mudanya" if lng < 29.06 else "Gemlik"
    if lng < 28.55:
        return "Karacabey"
    if lat < 40.08 and lng < 28.75:
        return "Mustafakemalpaşa"
    if lat < 40.02:
        if lng < 29.05:
            return "Orhaneli"
        if lng < 29.25:
            return "Keles"
        return "Harmancık"
    if lng >= 29.28:
        return "İnegöl" if lat < 40.20 else "Yenişehir"
    if lng >= 29.18:
        return "Kestel" if lat < 40.23 else "Gürsu"
    if lng >= 29.10:
        return "Yıldırım"
    if lng < 28.95 or (lat < 40.21 and lng < 29.02):
        return "Nilüfer"
    return "Osmangazi"


def visit_sub(tags: dict, title: str) -> str:
    t = {str(k): str(v or "").lower() for k, v in (tags or {}).items()}
    name = (title or "").lower()
    tourism = t.get("tourism", "")
    historic = t.get("historic", "")
    leisure = t.get("leisure", "")
    natural = t.get("natural", "")
    amenity = t.get("amenity", "")
    religion = t.get("religion", "")
    building = t.get("building", "")
    if tourism == "museum" or "müze" in name or "muze" in name:
        return "muze"
    if tourism == "viewpoint" or "seyir" in name or "manzara" in name:
        return "manzara"
    if tourism in ("zoo", "theme_park", "aquarium"):
        return "park"
    if natural == "waterfall" or "şelale" in name or "selale" in name:
        return "selale"
    if natural == "cave" or "mağara" in name or "magara" in name:
        return "magara"
    if leisure == "nature_reserve" or "tabiat" in name:
        return "doga"
    if leisure == "park" or "botanik" in name:
        return "park"
    if amenity == "place_of_worship" or building in ("mosque", "church"):
        notable = bool(t.get("wikipedia") or t.get("wikidata"))
        tourist = any(
            x in name
            for x in (
                "ulu", "yeşil", "yesil", "orhan", "osman", "murad", "emir",
                "hüda", "huda", "yıldırım", "yildirim", "fatih", "ayasofya",
                "kilise", "külliye", "kulliye", "selatin", "grand",
            )
        )
        if religion in ("christian", "orthodox") or building == "church" or "kilise" in name:
            return "kilise"
        if "türbe" in name or "turbe" in name:
            return "turbe" if (notable or tourist) else "skip"
        if "külliye" in name or "kulliye" in name:
            return "kulliye"
        if notable or tourist:
            return "cami"
        return "skip"
    if historic in ("castle", "city_gate", "citywalls", "fort", "tower"):
        return "hisar"
    if historic in ("tomb", "memorial") or "türbe" in name:
        return "turbe"
    if historic in ("ruins", "archaeological_site"):
        return "antik"
    if historic == "caravanserai" or " han" in f" {name}" or name.endswith("han"):
        return "han"
    if "kaplıca" in name or "kaplica" in name or "hamam" in name:
        return "kaplica"
    if "köy" in name or "kasaba" in name:
        return "koy"
    if historic == "monument":
        return "anit"
    if tourism == "attraction":
        if "cami" in name:
            return "cami"
        if "müze" in name or "muze" in name:
            return "muze"
        return "anit"
    if natural in ("peak", "ridge"):
        if "uludağ" in name or "uludag" in name:
            return "dag"
        return "skip"
    return "anit"


def osm_fetch(cache: str, ql: str, *, max_age_h: float | None = None) -> list:
    path = f"/tmp/{cache}.json"
    use_cache = os.path.isfile(path) and os.path.getsize(path) > 80
    if use_cache and max_age_h is not None:
        age_h = (time.time() - os.path.getmtime(path)) / 3600.0
        if age_h > max_age_h:
            use_cache = False
    if use_cache:
        return json.load(open(path))
    try:
        els = overpass(ql)
        json.dump(els, open(path, "w"))
        return els
    except Exception:
        if os.path.isfile(path) and os.path.getsize(path) > 80:
            return json.load(open(path))
        raise


def parse_els(els: list) -> list[dict]:
    skip_tourism = {"hotel", "hostel", "motel", "guest_house", "apartment", "information", "picnic_site"}
    skip_names = {"cami", "camii", "mescit", "mescid", "park", "wc", "tuvalet"}
    out = []
    for e in els:
        t = e.get("tags") or {}
        name = (t.get("name") or t.get("name:tr") or "").strip()
        if not name or len(name) < 3:
            continue
        if name.lower() in skip_names:
            continue
        if (t.get("tourism") or "") in skip_tourism:
            continue
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lng = e.get("lon") or (e.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        leisure = t.get("leisure") or ""
        if leisure == "park":
            nm = name.lower()
            notable = t.get("wikipedia") or t.get("wikidata") or t.get("tourism")
            if not notable and not any(x in nm for x in ("botanik", "tabiat", "milli", "kent", "hayvanat", "merinos", "kültür")):
                if len(name) < 14:
                    continue
        sub = visit_sub(t, name)
        if sub == "skip":
            continue
        street = t.get("addr:street") or ""
        house = t.get("addr:housenumber") or ""
        addr = " ".join(x for x in (street, house) if x).strip()
        out.append(
            {
                "title": name,
                "lat": float(lat),
                "lng": float(lng),
                "address": addr,
                "phone": (t.get("phone") or t.get("contact:phone") or "")[:40],
                "web": (t.get("website") or t.get("contact:website") or "")[:280],
                "ilce": guess_ilce(float(lat), float(lng)),
                "hours": (t.get("opening_hours") or "")[:160],
                "sub": visit_sub(t, name),
                "tags": t,
            }
        )
    return out


def make_slug(title: str, prefix: str = "osm-visit") -> str:
    return f"{prefix}-{slugify(title)}"[:80]


def upsert(db, *, slug: str, sub: str, title: str, ilce: str, address: str,
           lat, lng, blurb: str, rating: float | None, img: str, tags: list,
           phone: str = "", web: str = "", featured: bool = False,
           hours: str = "", price_band: str = "") -> str:
    fields = dict(
        title=title[:200],
        category="visit",
        subcategory=sub,
        ilce=ilce if ilce in ILCELER else (ilce or "Osmangazi"),
        address=(address or "")[:280],
        lat=lat,
        lng=lng,
        phone=(phone or "")[:40],
        web=(web or "")[:280],
        hours_text=(hours or "")[:160],
        price_band=(price_band or sub)[:40],
        blurb=(blurb or "")[:400],
        body=(blurb or "")[:2000],
        img_url=img or "",
        tags=tags_dump(tags),
        rating_admin=float(rating) if rating else None,
        featured=featured,
        status="approved",
    )
    p = db.query(Place).filter(Place.slug == slug).first()
    if p is None:
        final = slug
        n = 2
        while db.query(Place).filter(Place.slug == final).first() is not None:
            final = f"{slug}-{n}"[:80]
            n += 1
        db.add(Place(slug=final, **fields))
        db.flush()
        return "new"
    if p.category == "visit":
        for k, v in fields.items():
            if k == "img_url" and p.img_url and not v:
                continue
            if k == "featured" and p.featured:
                continue
            if k in ("blurb", "body") and (p.blurb or "") and len(p.blurb or "") > len(v or ""):
                continue
            setattr(p, k, v)
        return "upd"
    return "skip"


OSM_QUERIES = [
    (
        "osm_visit_tourism",
        f'[out:json][timeout:90];(node["tourism"~"^(attraction|museum|viewpoint|gallery|artwork|zoo|theme_park|aquarium)$"]({BBOX});way["tourism"~"^(attraction|museum|viewpoint|gallery|artwork|zoo|theme_park|aquarium)$"]({BBOX}););out center tags;',
    ),
    (
        "osm_visit_historic",
        f'[out:json][timeout:90];(node["historic"~"^(castle|monument|memorial|ruins|archaeological_site|tomb|mosque|church|city_gate|citywalls|manor|caravanserai|tower)$"]({BBOX});way["historic"~"^(castle|monument|memorial|ruins|archaeological_site|tomb|mosque|church|city_gate|citywalls|manor|caravanserai|tower)$"]({BBOX}););out center tags;',
    ),
    (
        "osm_visit_worship",
        f'[out:json][timeout:90];(node["amenity"="place_of_worship"]["name"]({BBOX});way["amenity"="place_of_worship"]["name"]({BBOX}););out center tags;',
    ),
    (
        "osm_visit_nature",
        f'[out:json][timeout:90];(node["natural"~"^(waterfall|cave|peak)$"]({BBOX});way["natural"~"^(waterfall|cave)$"]({BBOX});node["leisure"="nature_reserve"]({BBOX});way["leisure"="nature_reserve"]({BBOX});way["leisure"="park"]["wikipedia"]({BBOX});node["leisure"="park"]["wikipedia"]({BBOX});way["leisure"="park"]["wikidata"]({BBOX}););out center tags;',
    ),
    (
        "osm_visit_park",
        f'[out:json][timeout:90];(node["leisure"="park"]["name"]["access"!="private"]({BBOX});way["leisure"="park"]["name"]["access"!="private"]({BBOX}););out center tags;',
    ),
]


def import_osm_delta(db, *, max_age_h: float | None = 16.0) -> dict:
    """Yalnız OSM gezilecek — yeni kayıt, mevcut başlık atlanır. Curated overwrite yok."""
    stats = {"new": 0, "upd": 0, "skip": 0}
    existing_names = {slugify(p.title) for p in db.query(Place).filter(Place.category == "visit").all()}
    for cache, ql in OSM_QUERIES:
        try:
            els = osm_fetch(cache, ql, max_age_h=max_age_h)
        except Exception as e:
            print("osm fail", cache, e)
            els = []
        pts = parse_els(els)
        print(f"{cache}: els={len(els)} named={len(pts)}")
        for i, raw in enumerate(pts):
            nm = slugify(raw["title"])
            if not nm or nm in existing_names:
                stats["skip"] += 1
                continue
            existing_names.add(nm)
            sub = raw["sub"]
            rating = round(4.05 + max(0, 0.35 - i * 0.001), 1)
            blurb = f"Bursa {sub} · {raw['ilce']}."
            st = upsert(
                db,
                slug=make_slug(raw["title"]),
                sub=sub,
                title=raw["title"],
                ilce=raw["ilce"],
                address=raw.get("address") or "",
                lat=raw.get("lat"),
                lng=raw.get("lng"),
                blurb=blurb,
                rating=min(4.5, rating),
                img=SUB_IMG.get(sub) or SUB_IMG["anit"],
                tags=[sub, "osm", "gezilecek"],
                phone=raw.get("phone") or "",
                web=raw.get("web") or "",
                hours=raw.get("hours") or "",
                price_band=sub,
            )
            stats[st] = stats.get(st, 0) + 1
        db.commit()
        print("after", cache, stats)
    return stats


def main() -> None:
    init_db()
    db = SessionLocal()
    stats = {"new": 0, "upd": 0, "skip": 0}
    try:
        for p in db.query(Place).filter(Place.category == "visit").all():
            sub = EXISTING_SUB.get(p.slug)
            if sub and not (p.subcategory or "").strip():
                p.subcategory = sub
                if not (p.price_band or "").strip():
                    p.price_band = sub
                stats["upd"] += 1
        db.commit()

        existing_names = {slugify(p.title) for p in db.query(Place).filter(Place.category == "visit").all()}
        for i, raw in enumerate(CURATED):
            nm = slugify(raw["title"])
            if not nm:
                continue
            existing_names.add(nm)
            st = upsert(
                db,
                slug=slugify(raw["title"])[:80],
                sub=raw["sub"],
                title=raw["title"],
                ilce=raw["ilce"],
                address=raw.get("address") or "",
                lat=raw.get("lat"),
                lng=raw.get("lng"),
                blurb=raw.get("blurb") or "",
                rating=raw.get("rating"),
                img=raw.get("img") or SUB_IMG.get(raw["sub"]) or SUB_IMG["anit"],
                tags=[raw["sub"], "gezilecek"],
                featured=bool(raw.get("featured")),
                hours="1–2 saat",
                price_band=raw["sub"],
            )
            stats[st] = stats.get(st, 0) + 1
        db.commit()

        osm = import_osm_delta(db, max_age_h=None)
        for k, v in osm.items():
            stats[k] = stats.get(k, 0) + v

        from collections import Counter
        rows = db.query(Place).filter(Place.category == "visit", Place.status == "approved").all()
        print("stats", stats)
        print("visit approved", len(rows))
        for k, v in Counter((p.subcategory or "") for p in rows).most_common():
            print(f"  {k}: {v}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
