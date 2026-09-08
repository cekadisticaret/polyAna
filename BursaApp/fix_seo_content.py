#!/usr/bin/env python3
"""SEO içerik bulgularını düzelt: kapak, blurb, ilçe (idempotent)."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import ILCELER, subcategory_label
from hospital_covers import is_locked_path
from models import Place, SessionLocal, init_db

UA = "Mozilla/5.0 (compatible; BursaApp/1.0)"
MIN_BLURB = 20

DEFAULT_SOURCES = {
    "school": "static/visit/panorama-1326.jpg",
    "vet": "static/vet/pakvet.jpg",
    "dentist": "static/hospital/osmangazi-adsm.jpg",
    "doctor": "static/hospital/acibadem-bursa.jpg",
    "hospital": "static/hospital/bursa-sehir-hastanesi.jpg",
    "market": "static/visit/kale-sokak.jpg",
    "shop": "static/visit/koza-han.jpg",
    "sport": "static/visit/suuctu.jpg",
    "family": "static/visit/golyazi.jpg",
    "event": "static/event/etkinlik-junioshow-2026.jpg",
    "concert": "static/concert/konser-askin-nur-yengi-20260908.jpg",
    "theater": "static/theater/oyun-sen-istanbul-20260909.jpg",
    "cinema": "static/cinema/film-ruhlar-bolgesi.jpg",
    "fun": "static/visit/koza-han.jpg",
    "org": "static/visit/hanlar-kapalicarsi.jpg",
    "camp": "static/visit/uludag.jpg",
    "hotel": "static/visit/ulu-cami.jpg",
    "visit": "static/visit/ulu-cami.jpg",
    "food": "static/visit/koza-han.jpg",
}

CATEGORY_DEFAULT_URL: dict[str, str] = {}


def md5(path: str) -> str:
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def copy_img(src: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest)


def fetch(url: str, dest: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read()
        if len(data) < 8000:
            return False
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print("fetch fail", dest, e)
        return False


def ensure_default_images() -> None:
    ddir = os.path.join(_DIR, "static", "defaults")
    os.makedirs(ddir, exist_ok=True)
    for cat, src_rel in DEFAULT_SOURCES.items():
        src = os.path.join(_DIR, src_rel)
        dest = os.path.join(ddir, f"{cat}.jpg")
        if os.path.isfile(src) and (not os.path.isfile(dest) or os.path.getsize(dest) < 8000):
            copy_img(src, dest)
            print("default", cat)
        if os.path.isfile(dest):
            CATEGORY_DEFAULT_URL[cat] = f"/static/defaults/{cat}.jpg"


def infer_ilce_from_text(*parts: str) -> str:
    blob = " ".join(p for p in parts if p).lower()
    blob = blob.replace("i̇", "i")
    for ad in ILCELER:
        if ad.lower() in blob:
            return ad
    return ""


def _img_ok(img: str) -> bool:
    img = (img or "").strip()
    if not img:
        return False
    if img.startswith("/static/"):
        return os.path.isfile(os.path.join(_DIR, img.lstrip("/")))
    return img.startswith("http")


def _slug_image_paths(p: Place) -> list[str]:
    cat = (p.category or "").strip()
    slug = (p.slug or "").strip()
    if not cat or not slug:
        return []
    out = []
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        out.append(f"/static/{cat}/{slug}{ext}")
    if cat == "event" and not slug.startswith("eve-"):
        out.insert(0, f"/static/event/eve-{slug}.jpg")
    return out


def assign_images(db) -> int:
    n = 0
    for p in db.query(Place).filter(Place.status == "approved").all():
        if _img_ok(p.img_url or ""):
            continue
        assigned = False
        for rel in _slug_image_paths(p):
            if os.path.isfile(os.path.join(_DIR, rel.lstrip("/"))):
                if is_locked_path(rel):
                    p.img_url = rel
                    assigned = True
                    break
                p.img_url = rel
                assigned = True
                break
        if not assigned:
            default = CATEGORY_DEFAULT_URL.get(p.category or "")
            if default and _img_ok(default):
                p.img_url = default
                assigned = True
        if assigned:
            n += 1
    return n


def blurb_for(p: Place, hospitals: dict[str, str]) -> str:
    title = (p.title or "Mekan").strip()
    ilce = (p.ilce or "Bursa").strip()
    cat = p.category or ""
    sub = subcategory_label(p.subcategory) if p.subcategory else ""
    venue = hospitals.get((p.venue_name or "").strip(), "")

    custom = {
        "bursa-goz-merkezi": "Yıldırım'da göz muayenesi, katarakt ve retina tedavisi sunan özel göz merkezi.",
        "marka-outlet": "Nilüfer Marka AVM / outlet — markalı alışveriş, yeme-içme ve sinema.",
    }
    if p.slug in custom:
        return custom[p.slug]

    if cat == "school":
        kind = sub or (p.price_band or "Okul")
        return f"{title} — {ilce} {kind}. Bursa okul ve eğitim rehberi."

    if cat == "doctor":
        hosp = venue or (p.venue_name or "hastane").replace("-", " ").title()
        band = (p.price_band or "Uzman").strip()
        return f"{title} — {hosp} ({ilce}) {band} hekimi."

    if cat == "dentist":
        return f"{title} — {ilce} diş hekimi / ADSM kaydı."

    if cat == "vet":
        return f"{title} — {ilce} veteriner klinik ve hayvan sağlığı hizmeti."

    if cat == "market":
        if "genelinde" in (p.address or "").lower():
            return f"{title} — Bursa genelinde market zinciri; şube ve kampanya rehberi."
        return f"{title} — {ilce} market ve günlük alışveriş noktası."

    if cat == "hospital":
        return f"{title} — {ilce} sağlık kuruluşu; poliklinik ve branş hizmetleri."

    templates = {
        "concert": f"{title} konseri — {ilce}'de canlı müzik etkinliği.",
        "cinema": f"{title} vizyonda — Bursa sinemalarında gösterimde.",
        "theater": f"{title} — Bursa tiyatro sahnesinde oyun.",
        "food": f"{title} — {ilce}'de yeme-içme noktası.",
        "sport": f"{title} — {ilce} spor ve fitness merkezi.",
        "event": f"{title} — Bursa etkinlik takviminde {ilce}.",
        "shop": f"{title} — {ilce} alışveriş noktası.",
        "family": f"{title} — {ilce} aile ve çocuk aktivitesi.",
        "camp": f"{title} — Bursa kamp ve doğa alanı rehberi.",
        "hotel": f"{title} — {ilce} konaklama seçeneği.",
        "fun": f"{title} — {ilce} eğlence ve sosyal mekân.",
        "org": f"{title} — Bursa organizasyon ve etkinlik kaydı.",
        "visit": f"{title} — {ilce} gezilecek durak; Bursa rehberi.",
    }
    text = templates.get(cat, f"{title} — BursaApp rehberinde {ilce} kaydı.")
    if len(text.strip()) < MIN_BLURB:
        text = f"{text} Detaylar ve konum bilgisi."
    return text


def fill_blurbs(db) -> int:
    hospitals = {
        h.slug: (h.title or h.slug).replace("-", " ").title()
        for h in db.query(Place).filter(Place.category == "hospital", Place.status == "approved").all()
    }
    n = 0
    for p in db.query(Place).filter(Place.status == "approved").all():
        if len((p.blurb or "").strip()) >= MIN_BLURB:
            continue
        p.blurb = blurb_for(p, hospitals)
        n += 1
    return n


def fill_ilce(db) -> int:
    hospital_ilce = {
        h.slug: (h.ilce or "").strip()
        for h in db.query(Place).filter(Place.category == "hospital", Place.status == "approved").all()
    }
    n = 0
    for p in db.query(Place).filter(Place.status == "approved").all():
        if (p.ilce or "").strip():
            continue
        ilce = ""
        if p.category in ("doctor", "dentist"):
            ilce = hospital_ilce.get((p.venue_name or "").strip(), "")
        if not ilce:
            ilce = infer_ilce_from_text(p.address, p.title, p.blurb, p.body)
        if not ilce and p.category == "market":
            ilce = "Osmangazi"
        if not ilce and p.category == "event":
            ilce = infer_ilce_from_text(p.venue_name) or "Osmangazi"
        if not ilce and p.category == "doctor":
            ilce = "Nilüfer" if (p.venue_name or "").startswith("aci") else "Osmangazi"
        if ilce:
            p.ilce = ilce
            n += 1
    return n


def fix_wrong_images() -> None:
    """Yeşil Türbe / Yeşil Cami yanlışlıkla kopyalanmış kapaklar."""
    turbe = os.path.join(_DIR, "static/visit/yesil-turbe.jpg")
    cami = os.path.join(_DIR, "static/visit/yesil-cami.jpg")
    if not os.path.isfile(turbe) or not os.path.isfile(cami):
        return
    turbe_h = md5(turbe)
    cami_h = md5(cami)

    eye = os.path.join(_DIR, "static/hospital/_eye_clinic.jpg")
    if not os.path.isfile(eye) or md5(eye) in (turbe_h, cami_h):
        if not fetch(
            "https://images.unsplash.com/photo-1551601651-2a8555f1a136?w=1200",
            eye,
        ):
            retina = os.path.join(_DIR, "static/hospital/bursa-retina-goz.jpg")
            if os.path.isfile(retina):
                copy_img(retina, eye)

    replacements = {
        "static/hospital/bursa-goz-merkezi.jpg": eye,
        "static/doctor/bursa-goz-merkezi.jpg": eye,
        "static/hospital/nilufer-goz-merkezi.jpg": eye,
        "static/hospital/ali-osman-sonmez-onkoloji.jpg": "static/hospital/sehir-onkoloji.jpg",
        "static/doctor/ali-osman-sonmez-onkoloji.jpg": "static/hospital/sehir-onkoloji.jpg",
        "static/hospital/yildirim-adsm.jpg": "static/hospital/osmangazi-adsm.jpg",
        "static/doctor/yildirim-adsm.jpg": "static/hospital/osmangazi-adsm.jpg",
        "static/vet/millet-veteriner.jpg": "static/vet/pakvet.jpg",
        "static/cinema/film-sadece-bir-gece.jpg": "static/cinema/film-ruhlar-bolgesi.jpg",
        "static/family/suuctu-selalesi.jpg": "static/visit/suuctu.jpg",
    }
    for dest_rel, src in replacements.items():
        if is_locked_path(dest_rel):
            continue
        dest = os.path.join(_DIR, dest_rel)
        src_path = src if os.path.isabs(src) else os.path.join(_DIR, src)
        if not os.path.isfile(src_path):
            continue
        if os.path.isfile(dest) and md5(dest) not in (turbe_h, cami_h):
            if "goz-merkezi" in dest_rel and md5(dest) != md5(src_path):
                copy_img(src_path, dest)
            continue
        copy_img(src_path, dest)


def ensure_shop_images(db) -> int:
    n = 0
    mapping = {
        "korupark-avm": "static/cinema/sinema-korupark.jpg",
        "marka-outlet": "static/cinema/sinema-marka.jpg",
        "kozahan-hediyelik": "static/visit/koza-han.jpg",
        "cumalikizik-yerel": "static/visit/cumalikizik.jpg",
    }
    for slug, src_rel in mapping.items():
        p = db.query(Place).filter(Place.slug == slug).first()
        if not p:
            continue
        dest = os.path.join(_DIR, "static/shop", f"{p.slug}.jpg")
        src = os.path.join(_DIR, src_rel)
        if os.path.isfile(src):
            copy_img(src, dest)
            p.img_url = f"/static/shop/{p.slug}.jpg"
            n += 1
    return n


def main() -> None:
    init_db()
    ensure_default_images()
    fix_wrong_images()
    db = SessionLocal()
    try:
        ns = ensure_shop_images(db)
        ni = assign_images(db)
        nb = fill_blurbs(db)
        nd = fill_ilce(db)
        g = db.query(Place).filter(Place.slug == "bursa-goz-merkezi").first()
        if g:
            if not _img_ok(g.img_url or ""):
                g.img_url = "/static/hospital/bursa-goz-merkezi.jpg"
            if len((g.blurb or "").strip()) < MIN_BLURB:
                g.blurb = blurb_for(g, {})
        db.commit()
        print(f"shop={ns} images={ni} blurbs={nb} ilce={nd}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
