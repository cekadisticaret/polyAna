#!/usr/bin/env python3
"""Gezilecek yerler — canlı kapak + detay galerisi (Wikimedia Commons).

Instagram giriş duvarı yüzünden scrape edilemiyor; Commons’taki güncel
renkli fotoğraflar (2024 dış, iç, detay) yerel cache’e alınır.

  python3 enrich_visit_gallery.py
  python3 enrich_visit_gallery.py --slug ulu-cami
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
import urllib.request
import json

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from media_cache import ensure_cached
from models import Place, SessionLocal, init_db, merge_place_extra

UA = "BursaApp/1.0 (https://bursaapp.com; media enrich)"


def filepath(name: str, width: int = 1400) -> str:
    return (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        + urllib.parse.quote(name)
        + f"?width={width}"
    )


# Kapak + galeri dosya adları (Commons File:…) — Instagram tarzı canlı kareler
VISIT_GALLERY: dict[str, list[str]] = {
    "ulu-cami": [
        "Bursa Ulu Cami 2024.jpg",
        "BURSA ULUCAMİ.jpg",
        "BURSA ULUCAMİ KARLI VAKİTLER.jpg",
        "Bursa Ulu Cami Kaleden Görünümü.jpg",
        "Bursa - Bursa Grand Mosque - 20230709201719.jpg",
        "BURSA ULUCAMİ,KÜNDEKARİ,KAPI - panoramio.jpg",
        "BURSA,ULUCAMİ,KAPI,KÜNDEKARİ,OYMACILIK - panoramio.jpg",
        "BURSA,ULUCAMİ,MİMARİSİ - panoramio.jpg",
        "Bursa Ulu Camii - Kabe kapı örtüsü.jpg",
        "BURSA,ULUCAMİ,KÜNDEKARİ,KAPI,OYMACILIK - panoramio.jpg",
    ],
    "cumalikizik": [
        "Cumalıkızık.jpg",
        "Cumalıkızık Sokakları.jpg",
        "Cumalıkızık Evleri.jpg",
        "Cumalıkızık Taş Evleri.jpg",
        "Cumalıkızık, Bursa 1.jpg",
        "Cumalıkızık, Bursa 6.jpg",
        "Cumalıkızık, Bursa 7.jpg",
        "Cumalıkızık 7121.jpg",
    ],
    "uludag": [
        "Uludağ Teleferik @ Kurbağakaya (Oteller Bölgesi), January 2026 (1).jpg",
        "Uludağ Teleferik @ Kurbağakaya (Oteller Bölgesi), January 2026 (2).jpg",
        "Uludağ Teleferik - Kurbağakaya (Oteller Bölgesi) station building, January 2026 (1).jpg",
        "Bursa Uludağ in the snow winter wonderland 2004 0185a.jpg",
        "Uludağ Kayak Merkezi- Uludag Ski Center.jpg",
        "Bursa Uludağ Ski-related activities and slopes 2004 0138.jpg",
        "Bursa Uludağ Ski-related activities and slopes 2004 0134.jpg",
        "View of Uludağ from Sarıalan.JPG",
    ],
    "yesil-turbe": [
        "Yeşil Türbe.jpg",
        "Yesil Turbe Bursa.jpg",
        "Green Tomb Bursa.jpg",
        "Yeşil Türbe exterior.jpg",
    ],
    "yesil-cami": [
        "Yeşil Cami.jpg",
        "Green Mosque Bursa.jpg",
        "Yesil Camii Bursa.jpg",
    ],
    "hudavendigar-camii": [
        "Bursa, Hüdavendigar Camii, main facade from north.jpg",
        "Hüdavendigar (1).jpg",
        "Hüdavendigar (2).jpg",
        "Çekirge cami.jpg",
        "Bursa, Hüdavendigar Camii, ground floor, entrance porch towards west.jpg",
        "Bursa, Hüdavendigar Camii, main facade, ground floor, middle arches, from north.jpg",
    ],
    "koza-han": [
        "Koza Han, Bursa.jpg",
        "Koza Han, Bursa1.jpg",
        "Koza Han Bursa (2130792748).jpg",
        "Bursa Koza Han in 2003 0861.jpg",
        "Bursa Koza Han in 2003 0862.jpg",
        "Bursa Koza Han in 1993 031.jpg",
    ],
    "tophane": [
        "Tophane Bursa.jpg",
        "Tophane Clock Tower Bursa.jpg",
        "Osman Gazi Tomb Bursa.jpg",
    ],
    "muradiye": [
        "Muradiye Complex.jpg",
        "Muradiye Mosque Bursa.jpg",
        "Muradiye Külliyesi.jpg",
    ],
    "golyazi": [
        "Gölyazı.jpg",
        "Günbatımı, Gölyazı 2014-1.jpg",
        "Günbatımı, Gölyazı 2014-4.jpg",
        "Günbatımı, Gölyazı 2014-2.jpg",
        "Günbatımı, Gölyazı 2014-9.jpg",
        "Günbatımı, Gölyazı 2014-3.jpg",
        "Günbatımı, Gölyazı 2014-6.jpg",
    ],
    "suuctu": [
        "Suuçtu Waterfall.jpg",
        "Suuctu Selalesi.jpg",
        "Suuçtu Şelalesi.jpg",
    ],
    "teleferik": [
        "Bursa Teleferik.jpg",
        "Bursa cable car.jpg",
        "Teleferik Bursa Uludag.jpg",
    ],
    "hanlar-kapalicarsi": [
        "Bursa, Kapalı Çarşı.jpg",
        "Bursa Kapalı Çarşı.jpg",
        "Bursa Uzun Çarşı 2006 0041.jpg",
        "Bursa Uzun Çarşı 2007 0039.jpg",
        "Bursa Uzun Çarşı 2006 0042.jpg",
        "Bursa Tarihi Semtleri Kapalı Çarşı (1) - panoramio.jpg",
        "Bursa, bazaar, 03.jpg",
        "Koza Han, Bursa.jpg",
    ],
    "kale-sokak": [
        "Hisar Bursa.jpg",
        "Bursa castle walls.jpg",
        "Tophane Hisar Bursa.jpg",
    ],
    "eski-kaplica": [
        "Bursa, Eski Kaplıca from southwest.jpg",
        "Bursa, Eski Kaplıca from northwest.jpg",
        "Bursa, Eski Kaplıca, entrance from southeast.jpg",
        "Bursa, Eski Kaplıca, domes from south.jpg",
        "Bursa, Eski Kaplıca from west.jpg",
        "Bursa, Eski Kaplıca, general view from south.jpg",
    ],
    "inkaya-cinari": [
        "İnkaya Çınarı.jpg",
        "Inkaya Plane Tree.jpg",
        "Inkaya cinari Bursa.jpg",
    ],
    "panorama-1326": [
        "Panorama 1326 Bursa.jpg",
        "Bursa 1326 panorama museum.jpg",
    ],
    "mudanya-mutareke-evi": [
        "Mudanya ateşkes anlaşmasının yapıldığı tarihi bina.JPG",
        "MUDANYA MUTAKERE EVİ.JPG",
        "MudanyaMütareke2016.jpg",
        "Mutareke binası-Mudanya-Bursa - panoramio.jpg",
        "Mudanya 02.jpg",
    ],
    "tofas-anadolu-arabalari-muzesi": [
        "Tofaş Bursa Anadolu Arabaları Müzesi.jpg",
        "Tofaş Anadolu Arabaları Müzesi.jpg",
        "Tofaş Anadolu Arabaları Müzesi 2.jpg",
        "Tofaş Anadolu Arabaları Müzesi 3.jpg",
        "Tofaş Anadolu Arabaları Müzesi 4.jpg",
        "Tofaş Bursa Anadolu Arabaları Müzesi 2.jpg",
    ],
    "emir-sultan": [
        "Emir Sultan Camii 7067.jpg",
        "Emir Sultan Camii - Bursa 2017 (4).jpg",
        "Emir Sultan Camii - Bursa 2017 (14).jpg",
        "Emir Sultan Camii - Bursa 2017 (2).jpg",
        "Emir Sultan Camii - Bursa 2017 (1).jpg",
        "Bursa Emir Sultan Camii 7109.jpg",
    ],
    "irgandi": [
        "Irgandı Bridge.jpg",
        "Irgandi Köprüsü.jpg",
        "Irgandi Bridge Bursa.jpg",
    ],
    "misi": [
        "Misi köyü-gümüştepe - panoramio.jpg",
        "Gumustepe Mahallesi (Misi Koyu) 2016.jpg",
        "View from Dagyenice.jpg",
    ],
    "soganli-botanik": [
        "Soğanlı Botanik Parkı, Bursa.jpg",
        "Bursa Botanik Parkı2.JPG",
        "Botanic park-Bursa - panoramio.jpg",
        "Botanic park-Bursa 2011 Autumn - panoramio.jpg",
        "Bursa botanik park.jpg",
    ],
    "tirilye": [
        "Tirilye mudanya bursa 2015 - panoramio (6).jpg",
        "Tirilye houses.jpg",
        "Tirilye liman.jpg",
        "Tirilye Fatih cami.jpg",
        "Tirilye'de gün batımı - panoramio.jpg",
        "Tirilye sahil1.jpg",
        "Tirilye Eski Evleri 2014.jpg",
        "Trilye bursa türkiye - panoramio.jpg",
    ],
    "oylat": [
        "Oylat mağarası - panoramio.jpg",
        "Bursa, Oylat dağı.jpg",
    ],
    "iznik-surlar": [
        "Nicaea's Byzantine fortifications, Iznik, Turkey (37799829874).jpg",
        "Nicaea's Byzantine fortifications, Iznik, Turkey (37799849454).jpg",
        "Nicaea's Byzantine fortifications, Iznik, Turkey (38459515486).jpg",
        "Secondary gate (Tali Kapı) in the walls of Nicaea, İznik, Bursa Province, Turkey 01.jpg",
        "Aerial view of Lake İznik from north-east (IMG 2266).jpg",
        "Iznik gölü M.ACAR.jpg",
        "Sahildeniznik.jpg",
        "İznik Gölünün manzarası.jpg",
    ],
    "karacabey-longozu": [
        "Karacabey Longozu - Bahar.jpg",
        "Eskikaraağaç Leylek Köyü.jpg",
        "BURSA-KARACABEY - panoramio - HALUK COMERTEL (3).jpg",
        "BURSA-KARACABEY - panoramio - HALUK COMERTEL (5).jpg",
        "BURSA-KARACABEY - panoramio.jpg",
    ],
}


def commons_search(query: str, limit: int = 8) -> list[str]:
    """Dosya adı listesi — arama yedek."""
    q = urllib.parse.urlencode(
        {
            "action": "query",
            "list": "search",
            "srsearch": f"filetype:bitmap {query}",
            "srnamespace": "6",
            "srlimit": str(limit),
            "format": "json",
        }
    )
    url = f"https://commons.wikimedia.org/w/api.php?{q}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.load(r)
    except Exception:
        return []
    out = []
    for hit in data.get("query", {}).get("search", []):
        title = (hit.get("title") or "").replace("File:", "")
        if title:
            out.append(title)
    return out


def download_gallery(slug: str, files: list[str], *, cover: bool = True) -> tuple[str | None, list[str]]:
    import time

    urls: list[str] = []
    seen = set()
    for i, name in enumerate(files):
        src = filepath(name, 1400)
        local = ensure_cached(
            src,
            category="visit",
            filename=f"{slug}-g{i:02d}.jpg",
            min_bytes=4000,
        )
        if not local:
            time.sleep(0.4)
            continue
        if local in seen:
            continue
        seen.add(local)
        urls.append(local)
        time.sleep(0.25)
    cover_url = None
    if cover and urls:
        # kapak: ilk başarılıyı ayrıca static/visit/{slug}.jpg olarak kopyala
        cover_url = urls[0]
        try:
            import shutil

            src_path = os.path.join(_DIR, cover_url.lstrip("/"))
            dest = os.path.join(_DIR, "static", "visit", f"{slug}.jpg")
            if os.path.isfile(src_path):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src_path, dest)
                cover_url = f"/static/visit/{slug}.jpg"
        except Exception:
            pass
    return cover_url, urls


def enrich_one(db, p: Place) -> dict:
    files = list(VISIT_GALLERY.get(p.slug) or [])
    cover, gallery = download_gallery(p.slug, files[:12])
    if len(gallery) < 3:
        import time

        time.sleep(1.0)
        for name in commons_search(p.title.replace("·", " ").strip(), 10):
            if name not in files:
                files.append(name)
        cover, gallery = download_gallery(p.slug, files[:12])
    changed = {"slug": p.slug, "gallery": len(gallery), "cover": bool(cover)}
    if cover:
        p.img_url = cover
    if gallery:
        merge_place_extra(p, {"gallery": gallery})
    return changed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="", help="yalnız bir yer")
    args = ap.parse_args()
    init_db()
    db = SessionLocal()
    try:
        q = db.query(Place).filter(Place.category == "visit", Place.status == "approved")
        if args.slug:
            q = q.filter(Place.slug == args.slug)
        rows = q.order_by(Place.id).all()
        print(f"visit places: {len(rows)}")
        for p in rows:
            info = enrich_one(db, p)
            print(f"  {info['slug']}: gallery={info['gallery']} cover={info['cover']}")
        db.commit()
        print("ok")
    finally:
        db.close()


if __name__ == "__main__":
    main()
