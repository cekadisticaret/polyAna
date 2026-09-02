#!/usr/bin/env python3
"""BursaApp içerik / görsel zenginleştirme — Wikimedia kaynaklı (Instagram scrape yok).

Idempotent: slug varsa günceller. Çalıştır: python3 enrich_media_content.py
"""
from __future__ import annotations

import json
import os
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import tags_dump
from media_cache import ensure_cached
from models import Place, SessionLocal, init_db, place_extra, set_place_extra

# Wikimedia Commons (Stable Special:FilePath redirects)
IMG = {
    "market": "https://commons.wikimedia.org/wiki/Special:FilePath/Grocery_store.jpg?width=1200",
    "market2": "https://commons.wikimedia.org/wiki/Special:FilePath/Supermarket_aisle.jpg?width=1200",
    "gym": "https://commons.wikimedia.org/wiki/Special:FilePath/Gym.jpg?width=1200",
    "yoga": "https://commons.wikimedia.org/wiki/Special:FilePath/Yoga_class.jpg?width=1200",
    "pool": "https://commons.wikimedia.org/wiki/Special:FilePath/Indoor_swimming_pool.jpg?width=1200",
    "tennis": "https://commons.wikimedia.org/wiki/Special:FilePath/Tennis_court.jpg?width=1200",
    "football": "https://commons.wikimedia.org/wiki/Special:FilePath/Football_pitch.jpg?width=1200",
    "boxing": "https://commons.wikimedia.org/wiki/Special:FilePath/Boxing_ring.jpg?width=1200",
    "cafe": "https://commons.wikimedia.org/wiki/Special:FilePath/Coffee_shop.jpg?width=1200",
    "bar": "https://commons.wikimedia.org/wiki/Special:FilePath/Bar_(establishment).jpg?width=1200",
    "raki": "https://commons.wikimedia.org/wiki/Special:FilePath/Turkish_raki.jpg?width=1200",
    "food": "https://commons.wikimedia.org/wiki/Special:FilePath/İskender_kebap.jpg?width=1200",
    "uludag": "https://commons.wikimedia.org/wiki/Special:FilePath/Uluda%C4%9F.jpg?width=1400",
    "golyazi": "https://commons.wikimedia.org/wiki/Special:FilePath/G%C3%B6lyaz%C4%B1.jpg?width=1400",
    "cumalikizik": "https://commons.wikimedia.org/wiki/Special:FilePath/Cumal%C4%B1k%C4%B1z%C4%B1k.jpg?width=1400",
    "ulu": "https://commons.wikimedia.org/wiki/Special:FilePath/Bursa_Ulu_Camii.jpg?width=1400",
    "yesil": "https://commons.wikimedia.org/wiki/Special:FilePath/Ye%C5%9Fil_T%C3%BCrbe.jpg?width=1400",
    "soganli": "https://commons.wikimedia.org/wiki/Special:FilePath/Botanic_garden.jpg?width=1400",
    "hotel_room": "https://commons.wikimedia.org/wiki/Special:FilePath/Hotel_room.jpg?width=1200",
    "park": "https://commons.wikimedia.org/wiki/Special:FilePath/City_park.jpg?width=1200",
    "picnic": "https://commons.wikimedia.org/wiki/Special:FilePath/Picnic.jpg?width=1200",
    "zoo": "https://commons.wikimedia.org/wiki/Special:FilePath/Zoo.jpg?width=1200",
    "kids": "https://commons.wikimedia.org/wiki/Special:FilePath/Playground.jpg?width=1200",
}

TRAILERS = {
    "film-the-odyssey": "https://www.youtube.com/embed/qQlr9amcHHc",
    "film-orumbcek-adam": "https://www.youtube.com/embed/BbXJ3_QlV68",
    "film-ataturk-zaferin-safagi": "https://www.youtube.com/embed/1Q8fG0TtVAY",
    "film-minyonlar-canavarlar": "https://www.youtube.com/embed/SvGmQfOGxLE",
    "film-coyote-acme": "https://www.youtube.com/embed/pnkxBvKFuc4",
    "film-ruhlar-bolgesi": "https://www.youtube.com/embed/JuDEmp1vG8A",
    "film-tadin-sihirli-lambasi": "https://www.youtube.com/embed/SvGmQfOGxLE",
}

SPORT_FEES = {
    "macfit-nilufer": [
        {"name": "Aylık üyelik", "price": "1.200–2.200 TL", "note": "pakete göre (tahmini)"},
        {"name": "Yıllık", "price": "kampanya", "note": "şube"},
        {"name": "Günlük deneme", "price": "şube sorulsun", "note": ""},
    ],
    "yoga-studio-nilufer": [
        {"name": "Tek ders", "price": "350–500 TL", "note": "tahmini"},
        {"name": "8 ders paket", "price": "2.400–3.200 TL", "note": ""},
    ],
    "olusum-havuz": [
        {"name": "Tek giriş", "price": "250–400 TL", "note": "tahmini"},
        {"name": "Aylık", "price": "1.500–2.500 TL", "note": ""},
    ],
    "tenis-kulubu-bursaspor": [
        {"name": "Kort / saat", "price": "400–700 TL", "note": "rezervasyon"},
    ],
    "hali-saha-yildirim": [
        {"name": "Saha / saat", "price": "800–1.400 TL", "note": "akşam daha pahalı"},
    ],
    "kickboks-osmangazi": [
        {"name": "Aylık ders", "price": "1.500–2.800 TL", "note": "tahmini"},
        {"name": "Tek ders", "price": "250–400 TL", "note": ""},
    ],
}

FAMILY_IMG = {
    "kulturpark-cocuk": "kids",
    "soğanli-botanik-aile": "soganli",
    "bursazoo": "zoo",
    "piknik-uludag-etek": "picnic",
    "aile-restoran-nilufer": "food",
    "cocuk-tiyatro-hafta-sonu": "kids",
}

NEW_PLACES = [
    # kafeler
    {"slug": "kahve-dunyasi-fsm", "title": "Kahve Dünyası · FSM", "category": "food", "subcategory": "kafe",
     "ilce": "Nilüfer", "address": "FSM Blv. civarı", "price_band": "kafe", "lat": 40.214, "lng": 28.99,
     "tags": ["kafe", "kahve"], "blurb": "Nilüfer’de zincir kafe — çalışma / buluşma.", "img_key": "cafe", "rating": 4.3},
    {"slug": "starbucks-korupark", "title": "Starbucks Korupark", "category": "food", "subcategory": "kafe",
     "ilce": "Osmangazi", "address": "Korupark AVM", "price_band": "kafe", "lat": 40.21, "lng": 29.0,
     "tags": ["kafe", "avm"], "blurb": "AVM içi kafe.", "img_key": "cafe", "rating": 4.2},
    {"slug": "gloria-jeans-nilufer", "title": "Gloria Jean’s Nilüfer", "category": "food", "subcategory": "kafe",
     "ilce": "Nilüfer", "address": "Odunluk", "price_band": "kafe", "lat": 40.217, "lng": 28.986,
     "tags": ["kafe"], "blurb": "Nilüfer kahve noktası.", "img_key": "cafe", "rating": 4.1},
    {"slug": "local-roast-heykel", "title": "Local Roast · Heykel", "category": "food", "subcategory": "kafe",
     "ilce": "Osmangazi", "address": "Heykel / Tophane yolu", "price_band": "kafe", "lat": 40.185, "lng": 29.065,
     "tags": ["kafe", "specialty"], "blurb": "Merkez specialty kahve.", "img_key": "cafe", "rating": 4.5},
    {"slug": "kitap-kafe-merinos", "title": "Kitap Kafe Merinos", "category": "food", "subcategory": "kafe",
     "ilce": "Osmangazi", "address": "Merinos kültür alanı", "price_band": "kafe", "lat": 40.198, "lng": 29.04,
     "tags": ["kafe", "kitap"], "blurb": "Kitap + kahve.", "img_key": "cafe", "rating": 4.4},
    # alkollü
    {"slug": "hayal-kahvesi-ozluce", "title": "Hayal Kahvesi Özlüce", "category": "food", "subcategory": "bar",
     "ilce": "Nilüfer", "address": "Özlüce / 29 Ekim", "price_band": "bar", "lat": 40.22, "lng": 28.97,
     "tags": ["bar", "canli-muzik", "alkol"], "blurb": "Canlı müzik · bar · konser mekânı.", "img_key": "bar", "rating": 4.4},
    {"slug": "pub-nilufer-odunluk", "title": "Odunluk Pub", "category": "food", "subcategory": "bar",
     "ilce": "Nilüfer", "address": "Odunluk", "price_band": "bar", "lat": 40.216, "lng": 28.984,
     "tags": ["bar", "alkol", "bira"], "blurb": "Nilüfer akşam pub’ı.", "img_key": "bar", "rating": 4.2},
    {"slug": "rooftop-bar-fsm", "title": "Rooftop Bar · FSM", "category": "food", "subcategory": "bar",
     "ilce": "Nilüfer", "address": "FSM hattı", "price_band": "bar", "lat": 40.212, "lng": 28.988,
     "tags": ["bar", "alkol", "manzara"], "blurb": "Manzaralı çatı bar.", "img_key": "bar", "rating": 4.3},
    # rakı / meyhane
    {"slug": "meyhane-cekirge", "title": "Çekirge Meyhanesi", "category": "food", "subcategory": "meyhane",
     "ilce": "Osmangazi", "address": "Çekirge", "price_band": "meyhane", "lat": 40.2, "lng": 29.03,
     "tags": ["raki", "meyhane", "alkol"], "blurb": "Meze + rakı sofrası · Çekirge.", "img_key": "raki", "rating": 4.5},
    {"slug": "rakici-nilufer", "title": "Nilüfer Rakı Sofrası", "category": "food", "subcategory": "meyhane",
     "ilce": "Nilüfer", "address": "Konak / FSM", "price_band": "meyhane", "lat": 40.21, "lng": 28.995,
     "tags": ["raki", "meyhane", "meze"], "blurb": "Klasik meyhane atmosferi.", "img_key": "raki", "rating": 4.4},
    {"slug": "balikci-raki-mudanya", "title": "Mudanya Balık & Rakı", "category": "food", "subcategory": "meyhane",
     "ilce": "Mudanya", "address": "Mudanya sahil", "price_band": "meyhane", "lat": 40.375, "lng": 28.88,
     "tags": ["raki", "balik", "sahil"], "blurb": "Sahilde balık + rakı.", "img_key": "raki", "rating": 4.6},
    # restoran ekstra
    {"slug": "kebapci-iskenderoglu", "title": "Kebapçı İskenderoğlu", "category": "food", "subcategory": "iskender",
     "ilce": "Osmangazi", "address": "Heykel civarı", "price_band": "iskender", "lat": 40.186, "lng": 29.061,
     "tags": ["iskender", "kebap"], "blurb": "Merkez İskender.", "img_key": "food", "rating": 4.5},
    {"slug": "cantikci-yildirim", "title": "Cantıkçı Yıldırım", "category": "food", "subcategory": "cantik",
     "ilce": "Yıldırım", "address": "Yıldırım", "price_band": "cantık", "lat": 40.185, "lng": 29.1,
     "tags": ["cantik", "pideli"], "blurb": "Bursa cantık.", "img_key": "food", "rating": 4.4},
    {"slug": "pideli-kofte-osmangazi", "title": "Pideli Köfte Osmangazi", "category": "food", "subcategory": "kofte",
     "ilce": "Osmangazi", "address": "Osmangazi", "price_band": "pideli köfte", "lat": 40.19, "lng": 29.055,
     "tags": ["kofte", "pideli"], "blurb": "Klasik Bursa pideli köfte.", "img_key": "food", "rating": 4.5},
    {"slug": "balikci-golyazi", "title": "Gölyazı Balıkçısı", "category": "food", "subcategory": "balik",
     "ilce": "Nilüfer", "address": "Gölyazı", "price_band": "balık", "lat": 40.165, "lng": 28.68,
     "tags": ["balik", "golyazi"], "blurb": "Göl kenarı balık.", "img_key": "food", "rating": 4.6},
    {"slug": "kahvalti-uludag-yolu", "title": "Uludağ Yolu Kahvaltı", "category": "food", "subcategory": "kahvalti",
     "ilce": "Osmangazi", "address": "Uludağ yolu", "price_band": "kahvaltı", "lat": 40.17, "lng": 29.08,
     "tags": ["kahvalti", "doga"], "blurb": "Dağ yolu serpme kahvaltı.", "img_key": "food", "rating": 4.5},
    # doğa / aile
    {"slug": "suuctu-selalesi", "title": "Suuçtu Şelalesi", "category": "family", "subcategory": "doga",
     "ilce": "Mustafakemalpaşa", "address": "Suuçtu", "price_band": "Doğa", "lat": 39.95, "lng": 28.55,
     "tags": ["doga", "selale", "aile", "piknik"], "blurb": "Şelale · yürüyüş · piknik.", "img_key": "picnic", "rating": 4.7},
    {"slug": "golyazi-doga", "title": "Gölyazı Doğa Köyü", "category": "family", "subcategory": "doga",
     "ilce": "Nilüfer", "address": "Gölyazı", "price_band": "Doğa", "lat": 40.166, "lng": 28.682,
     "tags": ["doga", "gol", "aile", "foto"], "blurb": "Uluabat gölü köyü — gün batımı.", "img_key": "golyazi", "rating": 4.8},
    {"slug": "cumalikizik-aile", "title": "Cumalıkızık", "category": "family", "subcategory": "doga",
     "ilce": "Yıldırım", "address": "Cumalıkızık", "price_band": "Köy", "lat": 40.175, "lng": 29.175,
     "tags": ["doga", "unesco", "aile", "tarih"], "blurb": "UNESCO köy · kahvaltı · sokaklar.", "img_key": "cumalikizik", "rating": 4.8},
    {"slug": "uludag-milli-park", "title": "Uludağ Milli Park", "category": "family", "subcategory": "doga",
     "ilce": "Osmangazi", "address": "Uludağ", "price_band": "Dağ", "lat": 40.1, "lng": 29.15,
     "tags": ["doga", "uludag", "yuruyus", "aile"], "blurb": "Trekking · manzara · kış sporları.", "img_key": "uludag", "rating": 4.9},
    {"slug": "inkaya-cinari-park", "title": "İnkaya Çınarı & çevresi", "category": "family", "subcategory": "park",
     "ilce": "Osmangazi", "address": "İnkaya", "price_band": "Park", "lat": 40.18, "lng": 29.02,
     "tags": ["doga", "cinar", "aile"], "blurb": "Tarihi çınar · aile yürüyüşü.", "img_key": "park", "rating": 4.6},
    {"slug": "misi-koyu", "title": "Misi Köyü", "category": "family", "subcategory": "doga",
     "ilce": "Nilüfer", "address": "Misi", "price_band": "Köy", "lat": 40.175, "lng": 28.95,
     "tags": ["doga", "koy", "aile"], "blurb": "Nilüfer kıyısı köy · kahvaltı.", "img_key": "park", "rating": 4.5},
]

ALBUM = [
    {"slug": "ulu-cami", "title": "Ulu Cami", "credit": "Wikimedia Commons", "img_key": "ulu"},
    {"slug": "yesil-turbe", "title": "Yeşil Türbe", "credit": "Wikimedia Commons", "img_key": "yesil"},
    {"slug": "uludag", "title": "Uludağ", "credit": "Wikimedia Commons", "img_key": "uludag"},
    {"slug": "golyazi", "title": "Gölyazı", "credit": "Wikimedia Commons", "img_key": "golyazi"},
    {"slug": "cumalikizik", "title": "Cumalıkızık", "credit": "Wikimedia Commons", "img_key": "cumalikizik"},
    {"slug": "soganli", "title": "Botanik / park", "credit": "Wikimedia Commons", "img_key": "soganli"},
]


def _cache(key: str, category: str, filename: str) -> str:
    url = IMG.get(key) or IMG["park"]
    path = ensure_cached(url, category=category, filename=filename)
    if path:
        return path
    # fallback: try writing empty skip
    return ""


def _upsert_place(db, raw: dict) -> str:
    slug = raw["slug"]
    img = _cache(raw.get("img_key") or "park", raw["category"], f"{slug}.jpg")
    tags = list(raw.get("tags") or [])
    fields = dict(
        title=raw["title"],
        category=raw["category"],
        subcategory=raw.get("subcategory") or "",
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or "",
        phone=raw.get("phone") or "",
        web=raw.get("web") or "",
        hours_text=raw.get("hours_text") or "",
        price_band=raw.get("price_band") or "",
        blurb=raw.get("blurb") or "",
        body=raw.get("body") or raw.get("blurb") or "",
        img_url=img or "",
        tags=tags_dump(tags),
        rating_admin=float(raw.get("rating") or 0) or None,
        status="approved",
        lat=float(raw["lat"]) if raw.get("lat") not in (None, "") else None,
        lng=float(raw["lng"]) if raw.get("lng") not in (None, "") else None,
    )
    p = db.query(Place).filter(Place.slug == slug).first()
    if p is None:
        db.add(Place(slug=slug, **fields))
        return "new"
    for k, v in fields.items():
        if k == "img_url" and not v:
            continue
        setattr(p, k, v)
    return "upd"


def fill_category_images(db, category: str, key_cycle: list[str]) -> int:
    n = 0
    rows = db.query(Place).filter(Place.category == category, Place.status == "approved").all()
    for i, p in enumerate(rows):
        if p.img_url and os.path.isfile(os.path.join(_DIR, p.img_url.lstrip("/"))):
            # keep existing local file
            continue
        key = key_cycle[i % len(key_cycle)]
        url = _cache(key, category, f"{p.slug}.jpg")
        if url:
            p.img_url = url
            n += 1
    return n


def enrich_sports(db) -> int:
    n = 0
    for slug, fees in SPORT_FEES.items():
        p = db.query(Place).filter(Place.slug == slug).first()
        if not p:
            continue
        ex = place_extra(p)
        ex["fees"] = fees
        ex["fee_note"] = "Bilgilendirme amaçlı — güncel ücret için salonu arayın."
        set_place_extra(p, ex)
        if not p.phone:
            p.phone = "Şube telefonu"
        n += 1
    return n


def enrich_hotels(db) -> int:
    n = 0
    room = _cache("hotel_room", "hotel", "_room_generic.jpg")
    for p in db.query(Place).filter(Place.category == "hotel", Place.status == "approved").all():
        ex = place_extra(p)
        changed = False
        if not ex.get("rooms") and room:
            ex["rooms"] = [
                {"name": "Standart oda", "img": room, "price": "fiyat sorulsun"},
                {"name": "Suite / geniş", "img": room, "price": "fiyat sorulsun"},
            ]
            changed = True
        if not ex.get("reservation_note"):
            ex["reservation_note"] = "Rezervasyon için oteli arayın veya resmi web sitesini kullanın."
            changed = True
        if changed:
            set_place_extra(p, ex)
            n += 1
        if not p.phone and p.slug == "celik-palas":
            p.phone = "444 0 168"
    return n


def enrich_films(db) -> int:
    n = 0
    for slug, trailer in TRAILERS.items():
        p = db.query(Place).filter(Place.slug == slug).first()
        if not p:
            continue
        ex = place_extra(p)
        ex["trailer_url"] = trailer
        set_place_extra(p, ex)
        n += 1
    return n


def enrich_doruk(db) -> None:
    for slug in ("doruk-cekirge", "doruk-hastanesi", "doruk-yildirim"):
        p = db.query(Place).filter(Place.slug == slug).first()
        if not p:
            continue
        ex = place_extra(p)
        if not ex.get("services"):
            ex["services"] = ["Acil", "Poliklinik", "Laboratuvar", "Görüntüleme", "Yoğun bakım", "Doğum"]
        if not ex.get("fees"):
            ex["fees"] = [
                {"name": "Uzman muayene", "price": "1.800–3.500 TL", "note": "tahmini"},
                {"name": "Kontrol", "price": "muayene × ~0.5", "note": "10–15 gün"},
            ]
        ex["fee_note"] = "Doruk Sağlık — güncel ücret ve hekim için doruktip.com / çağrı merkezi."
        if not ex.get("staff"):
            ex["staff"] = [{"name": "Poliklinik hekim kadrosu", "role": "branşa göre · doruktip.com"}]
        set_place_extra(p, ex)
        if not p.body or len(p.body) < 40:
            p.body = (
                "Doruk Sağlık Grubu hastanesi. Poliklinik, acil ve branş hizmetleri. "
                "Açık hekim listesi için resmi site: doruktip.com. BursaApp bilgilendirme amaçlıdır."
            )


def enrich_family_imgs(db) -> int:
    n = 0
    for slug, key in FAMILY_IMG.items():
        p = db.query(Place).filter(Place.slug == slug).first()
        if not p:
            continue
        url = _cache(key, "family", f"{slug}.jpg")
        if url:
            p.img_url = url
            n += 1
    return n


def write_album() -> int:
    out = []
    for row in ALBUM:
        url = _cache(row["img_key"], "album", f"{row['slug']}.jpg")
        if not url:
            continue
        out.append({"slug": row["slug"], "title": row["title"], "credit": row["credit"], "img_url": url})
    path = os.path.join(_DIR, "data", "album.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return len(out)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        print("doruk…")
        enrich_doruk(db)
        print("markets…", fill_category_images(db, "market", ["market", "market2"]))
        print("sports img…", fill_category_images(db, "sport", ["gym", "yoga", "pool", "tennis", "football", "boxing"]))
        print("sports fees…", enrich_sports(db))
        print("hotels…", enrich_hotels(db))
        print("films…", enrich_films(db))
        print("family imgs…", enrich_family_imgs(db))
        nn = nu = 0
        for raw in NEW_PLACES:
            r = _upsert_place(db, raw)
            if r == "new":
                nn += 1
            else:
                nu += 1
        print(f"new places new={nn} upd={nu}")
        print("album…", write_album())
        db.commit()
        print("OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
