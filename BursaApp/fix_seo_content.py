#!/usr/bin/env python3
"""Yanlış kapak görselleri + SEO bulgularını düzelt (idempotent)."""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from hospital_covers import is_locked_path
from models import Place, SessionLocal, init_db

UA = "Mozilla/5.0 (compatible; BursaApp/1.0)"


def md5(path: str) -> str:
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def copy_img(src: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest)
    print("copy", src, "→", dest)


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
        print("fetch", dest, len(data))
        return True
    except Exception as e:
        print("fetch fail", dest, e)
        return False


def fix_wrong_images() -> None:
    """Yeşil Türbe / Yeşil Cami yanlışlıkla kopyalanmış kapaklar."""
    turbe = os.path.join(_DIR, "static/visit/yesil-turbe.jpg")
    cami = os.path.join(_DIR, "static/visit/yesil-cami.jpg")
    turbe_h = md5(turbe)
    cami_h = md5(cami)

    # göz klinik — tıbbi görsel
    eye = os.path.join(_DIR, "static/hospital/_eye_clinic.jpg")
    test = os.path.join(_DIR, "static/hospital/_test_eye.jpg")
    if os.path.isfile(test) and (not os.path.isfile(eye) or md5(eye) in (turbe_h, cami_h)):
        copy_img(test, eye)
    if not os.path.isfile(eye) or md5(eye) in (turbe_h, cami_h):
        if not fetch(
            "https://images.unsplash.com/photo-1551601651-2a8555f1a136?w=1200",
            eye,
        ):
            # ağ yoksa retina klinik kapağı (türbe değil)
            copy_img(os.path.join(_DIR, "static/hospital/bursa-retina-goz.jpg"), eye)

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
            print("skip locked hospital cover", dest_rel)
            continue
        dest = os.path.join(_DIR, dest_rel)
        src_path = src if os.path.isabs(src) else os.path.join(_DIR, src)
        if not os.path.isfile(src_path):
            print("skip missing src", src_path)
            continue
        if os.path.isfile(dest) and md5(dest) not in (turbe_h, cami_h):
            # zaten farklıysa ama göz merkezi eye ile aynı olmalı
            if "goz-merkezi" in dest_rel and md5(dest) != md5(src_path):
                copy_img(src_path, dest)
            continue
        copy_img(src_path, dest)


def ensure_shop_images(db) -> None:
    mapping = {
        "korupark-avm": ("static/shop/korupark-avm.jpg", "static/cinema/sinema-korupark.jpg"),
        "marka-outlet": ("static/shop/marka-outlet.jpg", "static/cinema/sinema-marka.jpg"),
        "kozahan-hediyelik": ("static/shop/kozahan-hediyelik.jpg", "static/visit/koza-han.jpg"),
        "cumalikizik-yerel": ("static/shop/cumalikizik-yerel.jpg", "static/visit/cumalikizik.jpg"),
        "antik-carsı-osmangazi": ("static/shop/antik-carsı-osmangazi.jpg", "static/visit/hanlar-kapalicarsi.jpg"),
    }
    # slug may use ascii
    alt = {"antik-carsı-osmangazi": "antik-carsı-osmangazi"}
    for slug, (dest_rel, src_rel) in mapping.items():
        p = db.query(Place).filter(Place.slug == slug).first()
        if not p:
            # try ascii variant
            p = db.query(Place).filter(Place.slug.like("antik-cars%")).first() if "antik" in slug else None
        if not p:
            print("no place", slug)
            continue
        dest = os.path.join(_DIR, dest_rel.replace("antik-carsı", "antik-carsi") if "cars" in dest_rel else dest_rel)
        # normalize dest without non-ascii
        dest = os.path.join(_DIR, "static/shop", f"{p.slug}.jpg")
        src = os.path.join(_DIR, src_rel)
        if os.path.isfile(src):
            copy_img(src, dest)
            p.img_url = f"/static/shop/{p.slug}.jpg"
            print("shop img", p.slug)
        else:
            print("no src for shop", src)

    # event missing img
    ev = db.query(Place).filter(Place.slug == "eve-caner-dagli-20260902").first()
    if ev and not (ev.img_url or "").strip():
        src = os.path.join(_DIR, "static/event/etkinlik-junioshow-2026.jpg")
        if not os.path.isfile(src):
            # any event
            ed = os.path.join(_DIR, "static/event")
            files = [f for f in os.listdir(ed) if f.endswith(".jpg")] if os.path.isdir(ed) else []
            src = os.path.join(ed, files[0]) if files else ""
        if src and os.path.isfile(src):
            dest = os.path.join(_DIR, "static/event", f"{ev.slug}.jpg")
            copy_img(src, dest)
            ev.img_url = f"/static/event/{ev.slug}.jpg"


BLURBS = {
    "bursa-goz-merkezi": "Yıldırım’da göz muayene, katarakt ve retina tedavisi sunan özel göz merkezi.",
    "marka-outlet": "Nilüfer Marka AVM / outlet — markalı alışveriş, yeme-içme ve sinema.",
    "oyun-iki-kisilik-20261022": "İki kişilik tiyatro oyunu — Bursa sahnesinde sınırlı gösterim.",
}


def fill_blurbs(db) -> int:
    n = 0
    for p in db.query(Place).filter(Place.status == "approved").all():
        b = (p.blurb or "").strip()
        if len(b) >= 20:
            continue
        if p.slug in BLURBS:
            p.blurb = BLURBS[p.slug]
            n += 1
            continue
        cat = p.category or ""
        ilce = (p.ilce or "Bursa").strip()
        title = p.title or "Mekan"
        templates = {
            "concert": f"{title} konseri — {ilce}’de canlı müzik etkinliği.",
            "cinema": f"{title} vizyonda — Bursa sinemalarında gösterimde.",
            "theater": f"{title} — Bursa tiyatro sahnesinde oyun.",
            "food": f"{title} — {ilce}’de yeme-içme noktası.",
            "market": f"{title} market — {ilce} alışveriş noktası.",
            "sport": f"{title} — {ilce} spor ve fitness.",
            "hospital": f"{title} — {ilce} sağlık kuruluşu, poliklinik ve branş hizmetleri.",
            "event": f"{title} — Bursa etkinlik takviminde.",
            "shop": f"{title} — {ilce} alışveriş noktası.",
        }
        p.blurb = templates.get(cat, f"{title} — BursaApp rehberinde {ilce} kaydı.")
        n += 1
    return n


def fill_doctor_ilce(db) -> int:
    n = 0
    hospitals = {
        h.slug: (h.ilce or "").strip()
        for h in db.query(Place).filter(Place.category == "hospital", Place.status == "approved").all()
    }
    for d in db.query(Place).filter(Place.category == "doctor", Place.status == "approved").all():
        if (d.ilce or "").strip():
            continue
        ilce = hospitals.get((d.venue_name or "").strip(), "")
        if not ilce:
            ilce = "Nilüfer" if (d.venue_name or "").startswith("aci") else "Osmangazi"
        d.ilce = ilce
        n += 1
    return n


def main() -> None:
    init_db()
    fix_wrong_images()
    db = SessionLocal()
    try:
        ensure_shop_images(db)
        nb = fill_blurbs(db)
        nd = fill_doctor_ilce(db)
        # goz blurb + ensure img_url
        g = db.query(Place).filter(Place.slug == "bursa-goz-merkezi").first()
        if g:
            g.img_url = "/static/hospital/bursa-goz-merkezi.jpg"
            if len((g.blurb or "").strip()) < 20:
                g.blurb = BLURBS["bursa-goz-merkezi"]
        db.commit()
        print(f"blurbs={nb} doctor_ilce={nd}")
    finally:
        db.close()
    # cleanup test file
    for junk in ("static/hospital/_test_eye.jpg",):
        p = os.path.join(_DIR, junk)
        if os.path.isfile(p):
            os.remove(p)


if __name__ == "__main__":
    main()
