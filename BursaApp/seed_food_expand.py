#!/usr/bin/env python3
"""Yeme-içme genişletme: cafe←kafe birleşimi + OSM kafeler + kahvaltı/meyhane/cantık/bar.

  python3 seed_food_expand.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)
REMOVED_PLACES_JSON = os.path.join(_DIR, "data", "places_removed.json")


def _removed_place_keys() -> tuple[set[str], set[str]]:
    """Silinen mekanlar — OSM delta tekrar eklemez."""
    try:
        with open(REMOVED_PLACES_JSON, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return set(), set()
    titles = {str(x).strip() for x in raw.get("title_slugs") or [] if str(x).strip()}
    slugs = {str(x).strip() for x in raw.get("slugs") or [] if str(x).strip()}
    return titles, slugs


from catalog import ILCELER, slugify, tags_dump
from media_cache import ensure_cached
from models import Place, SessionLocal, init_db

UA = "BursaApp/1.0 (https://bursaapp.com)"
BBOX = "40.05,28.70,40.45,29.35"

IMG = {
    "cafe": "https://commons.wikimedia.org/wiki/Special:FilePath/Coffee_shop.jpg?width=1200",
    "kahvalti": "https://commons.wikimedia.org/wiki/Special:FilePath/Turkish_breakfast.jpg?width=1200",
    "meyhane": "https://commons.wikimedia.org/wiki/Special:FilePath/Turkish_raki.jpg?width=1200",
    "bar": "https://commons.wikimedia.org/wiki/Special:FilePath/Bar_(establishment).jpg?width=1200",
    "cantik": "https://commons.wikimedia.org/wiki/Special:FilePath/Pide.jpg?width=1200",
    "restoran": "https://commons.wikimedia.org/wiki/Special:FilePath/Turkish_cuisine.jpg?width=1200",
    "fast-food": "https://commons.wikimedia.org/wiki/Special:FilePath/Cheeseburger.jpg?width=1200",
}

# Gece cron Commons'a gitmez — yerel stok kapak
LOCAL_IMG = {
    "cafe": "/static/food/kahvalti-1.jpg",
    "kahvalti": "/static/food/kahvalti-1.jpg",
    "meyhane": "/static/food/meyhane-cekirge.jpg",
    "bar": "/static/food/fine-1.jpg",
    "cantik": "/static/food/cantikci-yildirim.jpg",
    "pide": "/static/food/cantikci-yildirim.jpg",
    "restoran": "/static/food/fine-1.jpg",
    "fast-food": "/static/food/doner-1.jpg",
    "tatli": "/static/food/doner-2.jpg",
    "pastane": "/static/food/kahvalti-1.jpg",
    "kebap": "/static/food/kebapci-iskenderoglu.jpg",
    "iskender": "/static/food/iskender-4.jpg",
    "doner": "/static/food/doner-1.jpg",
    "balik": "/static/food/balik-1.jpg",
    "burger": "/static/food/doner-2.jpg",
    "inegol-kofte": "/static/food/kofte-1.jpg",
    "pizza": "/static/food/doner-2.jpg",
}

_OSM_CUISINE_SUB = (
    ("kebab", "kebap"),
    ("doner", "doner"),
    ("döner", "doner"),
    ("pizza", "pizza"),
    ("burger", "burger"),
    ("seafood", "balik"),
    ("fish", "balik"),
    ("italian", "pizza"),
    ("cafe", "cafe"),
    ("coffee", "cafe"),
    ("ice_cream", "tatli"),
    ("dessert", "tatli"),
    ("pastry", "pastane"),
    ("bakery", "pastane"),
)


def cuisine_sub(cuisine: str, amenity: str) -> str:
    blob = (cuisine or "").lower().replace(";", " ").replace(",", " ")
    for needle, sub in _OSM_CUISINE_SUB:
        if needle in blob:
            return sub
    if amenity == "fast_food":
        return "fast-food"
    if amenity == "cafe":
        return "cafe"
    if amenity in ("bar", "pub"):
        return "bar"
    if amenity in ("ice_cream", "ice-cream"):
        return "tatli"
    if amenity == "bakery":
        return "pastane"
    return "restoran"


def cache_img(kind: str) -> str:
    url = IMG.get(kind) or IMG["cafe"]
    local = ensure_cached(url, category="food", filename=f"{kind}-cover.jpg", min_bytes=3000)
    return local or ""


# --- İlçe tahmini (kaba grid) ---
def guess_ilce(lat: float | None, lng: float | None) -> str:
    if lat is None or lng is None:
        return "Osmangazi"
    if lat >= 40.34:
        return "Mudanya" if lng < 29.05 else "Gemlik"
    if lat >= 40.28 and lng < 28.92:
        return "Karacabey"
    if lng >= 29.22:
        return "İnegöl" if lat < 40.15 else "Yenişehir"
    if lng >= 29.12:
        return "Yıldırım"
    if lng < 28.92 or (lat < 40.20 and lng < 29.02):
        return "Nilüfer"
    if lat < 40.12:
        return "Mustafakemalpaşa"
    return "Osmangazi"


def overpass(ql: str) -> list:
    data = urllib.parse.urlencode({"data": ql}).encode()
    req = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=data,
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=100) as r:
        return (json.load(r).get("elements") or [])


def osm_points(amenity: str, *, tag: str = "amenity", max_age_h: float | None = None) -> list[dict]:
    path = f"/tmp/osm_{tag}_{amenity}.json"
    use_cache = os.path.isfile(path) and os.path.getsize(path) > 80
    if use_cache and max_age_h is not None:
        age_h = (time.time() - os.path.getmtime(path)) / 3600.0
        if age_h > max_age_h:
            use_cache = False
    if use_cache:
        els = json.load(open(path))
    else:
        ql = (
            f'[out:json][timeout:75];'
            f'(node["{tag}"="{amenity}"]({BBOX});way["{tag}"="{amenity}"]({BBOX}););'
            f"out center tags;"
        )
        try:
            els = overpass(ql)
            json.dump(els, open(path, "w"))
        except Exception:
            if os.path.isfile(path) and os.path.getsize(path) > 80:
                els = json.load(open(path))
            else:
                raise
    out = []
    for e in els:
        t = e.get("tags") or {}
        name = (t.get("name") or "").strip()
        if not name or len(name) < 2:
            continue
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lng = e.get("lon") or (e.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        street = t.get("addr:street") or ""
        house = t.get("addr:housenumber") or ""
        addr = " ".join(x for x in (street, house) if x).strip()
        phone = t.get("phone") or t.get("contact:phone") or ""
        web = t.get("website") or t.get("contact:website") or ""
        out.append(
            {
                "title": name,
                "lat": float(lat),
                "lng": float(lng),
                "address": addr,
                "phone": phone[:40],
                "web": web[:280],
                "ilce": guess_ilce(float(lat), float(lng)),
                "osm_id": e.get("id"),
                "cuisine": (t.get("cuisine") or "")[:80],
                "hours": (t.get("opening_hours") or "")[:160],
            }
        )
    return out


# --- Curated: iyilerden başla (puan yüksek) ---
CURATED_KAHVALTI = [
    {"title": "Hasbihal Bahçesi Cumalıkızık", "ilce": "Yıldırım", "address": "Cumalıkızık", "lat": 40.169, "lng": 29.172, "rating": 4.8, "blurb": "Köy bahçesi serpme · menemen + pişi · Cumalıkızık’ın en çok yorumlanan sofralarından."},
    {"title": "Misi Masal Kahvaltı", "ilce": "Nilüfer", "address": "Gümüştepe Lefkoşe Cd.", "lat": 40.188, "lng": 28.962, "rating": 4.8, "blurb": "Nilüfer Çayı kenarı sınırsız serpme · ödüllü kahvaltıcı · rezervasyon önerilir."},
    {"title": "Kadıefendi Konağı Cumalıkızık", "ilce": "Yıldırım", "address": "Cumalıkızık Orta Sk.", "lat": 40.1685, "lng": 29.171, "rating": 4.7, "blurb": "Tarihi taş konak · avlu · yöresel köy kahvaltısı."},
    {"title": "Değirmenci Kahvaltı", "ilce": "Yıldırım", "address": "Cumalıkızık 4. Pınar Sk.", "lat": 40.1695, "lng": 29.1705, "rating": 4.7, "blurb": "Soba başı köy kahvaltısı · mantı ve incir tatlısı da var."},
    {"title": "Otantik Kahvaltı Evi Cumalıkızık", "ilce": "Yıldırım", "address": "Cumalıkızık Orta Sk. 24/2", "lat": 40.1688, "lng": 29.1715, "rating": 4.7, "blurb": "Osmanlı köy evi dokusu · ev yapımı reçel."},
    {"title": "Balkon Kafe Doburca", "ilce": "Osmangazi", "address": "Doburca 3. Nilüfer Cd.", "lat": 40.205, "lng": 29.02, "rating": 4.6, "blurb": "Manzaralı serpme · 5 bine yakın yorum · uzun oturmalık."},
    {"title": "Uluçatı Kahvaltı Evi", "ilce": "Osmangazi", "address": "Uluçam", "lat": 40.145, "lng": 29.05, "rating": 4.6, "blurb": "Dağ evi hissi · soba · köy ürünü tereyağı ve reçel."},
    {"title": "Vişne Bademli Kahvaltı", "ilce": "Mudanya", "address": "Bademli", "lat": 40.36, "lng": 28.84, "rating": 4.6, "blurb": "Sınırsız serpme · israfsız porsiyon politikası · bağlar arası."},
    {"title": "Narlı Bahçe Cumalıkızık", "ilce": "Yıldırım", "address": "Cumalıkızık Ferdağ Sk.", "lat": 40.1692, "lng": 29.1725, "rating": 4.5, "blurb": "Kabak reçeli · kuymak · geniş bahçe."},
    {"title": "Rezene Restaurant & Cafe", "ilce": "Nilüfer", "address": "Konak Beşevler Cd.", "lat": 40.211, "lng": 28.995, "rating": 4.6, "blurb": "Serpme kahvaltı klasikleri · Nilüfer’de uzun sofra."},
    {"title": "Assos Köy Evi", "ilce": "Osmangazi", "address": "Nilüfer Köy Nilüfer Hatun Cd.", "lat": 40.195, "lng": 29.01, "rating": 4.5, "blurb": "Bahçeli serpme · pişi ve peynir çeşitleri."},
    {"title": "Gölyazı Faik Bey Konağı", "ilce": "Nilüfer", "address": "Gölyazı", "lat": 40.166, "lng": 28.68, "rating": 4.5, "blurb": "Uluabat gölü manzaralı konak kahvaltısı."},
    {"title": "Cumalıkızık Sadıklar Konağı", "ilce": "Yıldırım", "address": "Cumalıkızık Cin Aralığı", "lat": 40.168, "lng": 29.173, "rating": 4.5, "blurb": "Üç katlı konak · köy kahvaltısı · aile sıcaklığı."},
    {"title": "Ballım Kafe Cumalıkızık", "ilce": "Yıldırım", "address": "Cumalıkızık", "lat": 40.1698, "lng": 29.1718, "rating": 4.5, "blurb": "Köy kahvaltısı · uygun fiyat bandı."},
    {"title": "Dereağzı Cafe Restaurant", "ilce": "Osmangazi", "address": "Doburca", "lat": 40.204, "lng": 29.018, "rating": 4.4, "blurb": "Dere kenarı kahvaltı ve cafe."},
    {"title": "Pasto Bursa", "ilce": "Osmangazi", "address": "Akpınar Hancı Cd.", "lat": 40.19, "lng": 29.05, "rating": 4.4, "blurb": "Merkezde kahvaltı + pasta / cafe."},
    {"title": "Nev-i Çeşni", "ilce": "Nilüfer", "address": "Odunluk Erdoğan Binyücel Cd.", "lat": 40.215, "lng": 28.985, "rating": 4.4, "blurb": "Odunluk serpme ve çeşni sofrası."},
    {"title": "Cumalıkızık Köy Kahvaltısı Baba Ocağı", "ilce": "Yıldırım", "address": "Cumalıkızık", "lat": 40.1678, "lng": 29.1708, "rating": 4.3, "blurb": "Klasik köy sofra · aile işletmesi."},
    {"title": "Laleli Bahçe Cumalıkızık", "ilce": "Yıldırım", "address": "Cumalıkızık", "lat": 40.1702, "lng": 29.1722, "rating": 4.2, "blurb": "Bahçeli köy kahvaltısı."},
    {"title": "Bursa Kahvaltı Osmangazi", "ilce": "Osmangazi", "address": "Merkez", "lat": 40.192, "lng": 29.06, "rating": 4.3, "blurb": "Şehir içi serpme kahvaltı noktası."},
    # semt / ilçe genişletme — bilinen tipik noktalar
    {"title": "Görükle Sabah Sofrası", "ilce": "Nilüfer", "address": "Görükle", "lat": 40.225, "lng": 28.875, "rating": 4.3, "blurb": "Üniversite çevresi serpme kahvaltı."},
    {"title": "Özlüce Kahvaltı Bahçesi", "ilce": "Nilüfer", "address": "Özlüce", "lat": 40.218, "lng": 28.968, "rating": 4.3, "blurb": "Nilüfer serpme · bahçe masası."},
    {"title": "Beşevler Sabah Kahvaltı", "ilce": "Nilüfer", "address": "Beşevler", "lat": 40.208, "lng": 28.998, "rating": 4.2, "blurb": "Beşevler serpme ve gözleme."},
    {"title": "İhsaniye Serpme Kahvaltı", "ilce": "Nilüfer", "address": "İhsaniye", "lat": 40.212, "lng": 28.99, "rating": 4.2, "blurb": "FSM hattı kahvaltı."},
    {"title": "Ataevler Kahvaltı Salonu", "ilce": "Nilüfer", "address": "Ataevler", "lat": 40.21, "lng": 28.978, "rating": 4.2, "blurb": "Semt kahvaltı salonu."},
    {"title": "Çekirge Termal Kahvaltı", "ilce": "Osmangazi", "address": "Çekirge", "lat": 40.198, "lng": 29.03, "rating": 4.3, "blurb": "Çekirge sırtı serpme."},
    {"title": "Soğanlı Park Kahvaltı", "ilce": "Osmangazi", "address": "Soğanlı Botanik civarı", "lat": 40.19, "lng": 29.04, "rating": 4.2, "blurb": "Park kenarı aile kahvaltısı."},
    {"title": "Kayhan Sabah Sofrası", "ilce": "Osmangazi", "address": "Kayhan", "lat": 40.185, "lng": 29.068, "rating": 4.2, "blurb": "Kayhan çarşısı kahvaltı."},
    {"title": "Setbaşı Kahvaltı Evi", "ilce": "Osmangazi", "address": "Setbaşı", "lat": 40.183, "lng": 29.07, "rating": 4.1, "blurb": "Setbaşı serpme."},
    {"title": "Heykel Sabah Cafe", "ilce": "Osmangazi", "address": "Heykel", "lat": 40.184, "lng": 29.062, "rating": 4.1, "blurb": "Merkez hızlı kahvaltı + kahve."},
    {"title": "Yıldırım Esenevler Kahvaltı", "ilce": "Yıldırım", "address": "Esenevler", "lat": 40.19, "lng": 29.12, "rating": 4.2, "blurb": "Yıldırım semt kahvaltısı."},
    {"title": "Arabayatağı Serpme", "ilce": "Yıldırım", "address": "Arabayatağı", "lat": 40.195, "lng": 29.13, "rating": 4.1, "blurb": "Semt serpme kahvaltı."},
    {"title": "Mudanya Sahil Kahvaltı", "ilce": "Mudanya", "address": "Mudanya iskele", "lat": 40.375, "lng": 28.882, "rating": 4.4, "blurb": "Sahil manzaralı serpme."},
    {"title": "Tirilye Sabah Kahvaltı", "ilce": "Mudanya", "address": "Tirilye", "lat": 40.39, "lng": 28.795, "rating": 4.4, "blurb": "Zeytinbağı köy kahvaltısı."},
    {"title": "Gemlik Sahil Kahvaltı", "ilce": "Gemlik", "address": "Gemlik sahil", "lat": 40.43, "lng": 29.155, "rating": 4.3, "blurb": "Gemlik sahil serpme."},
    {"title": "İnegöl Meydan Kahvaltı", "ilce": "İnegöl", "address": "İnegöl merkez", "lat": 40.078, "lng": 29.513, "rating": 4.2, "blurb": "İnegöl merkez serpme."},
    {"title": "İznik Göl Kahvaltı", "ilce": "İznik", "address": "İznik göl kenarı", "lat": 40.429, "lng": 29.721, "rating": 4.3, "blurb": "Göl manzaralı kahvaltı."},
    {"title": "Orhangazi Sabah Sofrası", "ilce": "Orhangazi", "address": "Orhangazi", "lat": 40.489, "lng": 29.309, "rating": 4.1, "blurb": "İlçe merkez kahvaltı."},
    {"title": "Karacabey Kahvaltı Salonu", "ilce": "Karacabey", "address": "Karacabey", "lat": 40.213, "lng": 28.361, "rating": 4.1, "blurb": "Karacabey serpme."},
    {"title": "Mustafakemalpaşa Sabah", "ilce": "Mustafakemalpaşa", "address": "MKPaşa merkez", "lat": 40.038, "lng": 28.408, "rating": 4.1, "blurb": "MKPaşa kahvaltı salonu."},
    {"title": "Kestel Sabah Kahvaltı", "ilce": "Kestel", "address": "Kestel", "lat": 40.198, "lng": 29.212, "rating": 4.0, "blurb": "Kestel semt kahvaltısı."},
    {"title": "Gürsu Kahvaltı Evi", "ilce": "Gürsu", "address": "Gürsu", "lat": 40.218, "lng": 29.195, "rating": 4.0, "blurb": "Gürsu serpme."},
]

CURATED_CAFE = [
    {"title": "Pablo Artisan Coffee · FSM", "ilce": "Nilüfer", "address": "FSM Blv.", "lat": 40.212, "lng": 28.988, "rating": 4.7, "blurb": "3. nesil specialty · laptop-friendly · FSM’nin popüler durağı."},
    {"title": "Greenwich Coffee · FSM", "ilce": "Nilüfer", "address": "İhsaniye FSM Blv.", "lat": 40.2115, "lng": 28.989, "rating": 4.6, "blurb": "Specialty kahve · çalışma masası."},
    {"title": "Coffee'n Craft", "ilce": "Nilüfer", "address": "Ahmet Yesevi Turkuaz Garden", "lat": 40.214, "lng": 28.98, "rating": 4.7, "blurb": "Yüksek puanlı bağımsız kafe."},
    {"title": "3. Nesil Coffee Shop Görükle", "ilce": "Nilüfer", "address": "Görükle Armutluk Cd.", "lat": 40.224, "lng": 28.87, "rating": 4.6, "blurb": "Görükle 3. nesil kahve."},
    {"title": "Nevada Coffee · FSM", "ilce": "Nilüfer", "address": "Cumhuriyet FSM Blv.", "lat": 40.213, "lng": 28.987, "rating": 4.5, "blurb": "FSM kahve noktası."},
    {"title": "Mackbear Coffee · Görükle", "ilce": "Nilüfer", "address": "Görükle Üçoluk Cd.", "lat": 40.223, "lng": 28.872, "rating": 4.5, "blurb": "Zincir specialty · Görükle."},
    {"title": "Petrov Coffee", "ilce": "Nilüfer", "address": "Cumhuriyet Zafer Sk.", "lat": 40.21, "lng": 28.992, "rating": 4.5, "blurb": "Nilüfer specialty kahve."},
    {"title": "Pieta Coffee · Parkora", "ilce": "Nilüfer", "address": "Odunluk Parkora", "lat": 40.216, "lng": 28.983, "rating": 4.5, "blurb": "Parkora içi nitelikli kahve + tatlı."},
    {"title": "Flou Coffee", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.215, "lng": 28.986, "rating": 4.4, "blurb": "Bağımsız kahve dükkânı."},
    {"title": "Breww Coffee", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.2145, "lng": 28.984, "rating": 4.4, "blurb": "Specialty brew."},
    {"title": "Packer's Coffee Co", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.2135, "lng": 28.981, "rating": 4.4, "blurb": "Roastery / brew bar."},
    {"title": "Evergreen Croissant & Coffee", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.2128, "lng": 28.979, "rating": 4.4, "blurb": "Kruvasan + kahve."},
    {"title": "Good Call Cafe", "ilce": "Nilüfer", "address": "Çamlıca Eğitimciler Cd.", "lat": 40.208, "lng": 28.975, "rating": 4.3, "blurb": "Çalışma cafe."},
    {"title": "Woox Lounge", "ilce": "Nilüfer", "address": "Dumlupınar Gelibolu Cd.", "lat": 40.22, "lng": 28.87, "rating": 4.3, "blurb": "Lounge cafe · Görükle hattı."},
    {"title": "Ehl-i Keyf Cafe", "ilce": "Nilüfer", "address": "Dumlupınar", "lat": 40.221, "lng": 28.868, "rating": 4.3, "blurb": "Görükle cafe."},
    {"title": "Çınar Cafe Atatürk Cd.", "ilce": "Osmangazi", "address": "Nalbantoğlu Atatürk Cd.", "lat": 40.186, "lng": 29.061, "rating": 4.3, "blurb": "Merkez klasik cafe."},
    {"title": "Juan Valdez Bursa", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.211, "lng": 28.983, "rating": 4.2, "blurb": "Kolombiya kahve zinciri."},
    {"title": "Tchibo Odunluk", "ilce": "Nilüfer", "address": "Odunluk Lefkoşe Cd.", "lat": 40.2155, "lng": 28.982, "rating": 4.1, "blurb": "Odunluk Tchibo."},
    {"title": "Kahve Dünyası · PodyumPark", "ilce": "Nilüfer", "address": "PodyumPark", "lat": 40.217, "lng": 28.99, "rating": 4.2, "blurb": "AVM / bulvar kahve."},
    {"title": "Gloria Jean’s · Marka AVM", "ilce": "Nilüfer", "address": "Odunluk Marka AVM", "lat": 40.2162, "lng": 28.9845, "rating": 4.1, "blurb": "AVM cafe."},
]

CURATED_MEYHANE = [
    {"title": "Çekirge Meyhanesi", "ilce": "Osmangazi", "address": "Çekirge", "lat": 40.2, "lng": 29.03, "rating": 4.6, "blurb": "Meze + rakı sofrası · Çekirge klasiği."},
    {"title": "Nilüfer Rakı Sofrası", "ilce": "Nilüfer", "address": "Konak / FSM", "lat": 40.21, "lng": 28.995, "rating": 4.5, "blurb": "Klasik meyhane atmosferi."},
    {"title": "Mudanya Balık & Rakı", "ilce": "Mudanya", "address": "Mudanya sahil", "lat": 40.375, "lng": 28.88, "rating": 4.6, "blurb": "Sahilde balık + rakı."},
    {"title": "Hisar Meyhanesi", "ilce": "Osmangazi", "address": "Hisar / Tophane", "lat": 40.186, "lng": 29.058, "rating": 4.5, "blurb": "Hisar sırtı meze sofrası."},
    {"title": "Kayhan Meyhanesi", "ilce": "Osmangazi", "address": "Kayhan", "lat": 40.1855, "lng": 29.067, "rating": 4.4, "blurb": "Kayhan çarşısı rakı-meze."},
    {"title": "Setbaşı Meze Evi", "ilce": "Osmangazi", "address": "Setbaşı", "lat": 40.1835, "lng": 29.071, "rating": 4.4, "blurb": "Setbaşı meyhane."},
    {"title": "Merinos Meyhane", "ilce": "Osmangazi", "address": "Merinos", "lat": 40.197, "lng": 29.04, "rating": 4.3, "blurb": "Merinos civarı rakı sofrası."},
    {"title": "Çatalfırın Meyhanesi", "ilce": "Osmangazi", "address": "Çatalfırın", "lat": 40.19, "lng": 29.055, "rating": 4.3, "blurb": "Eski Bursa meyhanesi."},
    {"title": "Odunluk Meyhane", "ilce": "Nilüfer", "address": "Odunluk", "lat": 40.215, "lng": 28.985, "rating": 4.4, "blurb": "Nilüfer meze + rakı."},
    {"title": "Özlüce Rakı Sofrası", "ilce": "Nilüfer", "address": "Özlüce", "lat": 40.219, "lng": 28.97, "rating": 4.3, "blurb": "Özlüce meyhane."},
    {"title": "Beşevler Meyhane", "ilce": "Nilüfer", "address": "Beşevler", "lat": 40.209, "lng": 28.997, "rating": 4.3, "blurb": "Beşevler rakı-meze."},
    {"title": "Görükle Meyhane", "ilce": "Nilüfer", "address": "Görükle", "lat": 40.224, "lng": 28.874, "rating": 4.2, "blurb": "Üniversite çevresi meyhane."},
    {"title": "Mudanya İskele Meyhanesi", "ilce": "Mudanya", "address": "İskele", "lat": 40.376, "lng": 28.883, "rating": 4.5, "blurb": "İskele balık-meze."},
    {"title": "Tirilye Meze Bahçesi", "ilce": "Mudanya", "address": "Tirilye", "lat": 40.391, "lng": 28.796, "rating": 4.4, "blurb": "Tirilye akşam sofrası."},
    {"title": "Gemlik Sahil Meyhanesi", "ilce": "Gemlik", "address": "Gemlik sahil", "lat": 40.431, "lng": 29.156, "rating": 4.3, "blurb": "Sahil rakı-balık."},
    {"title": "Yıldırım Esenevler Meyhane", "ilce": "Yıldırım", "address": "Esenevler", "lat": 40.191, "lng": 29.121, "rating": 4.2, "blurb": "Yıldırım meyhane."},
    {"title": "Arabayatağı Meze Sofrası", "ilce": "Yıldırım", "address": "Arabayatağı", "lat": 40.196, "lng": 29.131, "rating": 4.2, "blurb": "Semt meyhanesi."},
    {"title": "İnegöl Meyhane", "ilce": "İnegöl", "address": "İnegöl merkez", "lat": 40.079, "lng": 29.514, "rating": 4.2, "blurb": "İnegöl rakı-meze."},
    {"title": "İznik Suriçi Meyhane", "ilce": "İznik", "address": "İznik merkez", "lat": 40.428, "lng": 29.72, "rating": 4.3, "blurb": "Sur içi meze sofrası."},
    {"title": "Orhangazi Meyhane", "ilce": "Orhangazi", "address": "Orhangazi", "lat": 40.49, "lng": 29.31, "rating": 4.1, "blurb": "İlçe meyhanesi."},
    {"title": "Karacabey Meyhane", "ilce": "Karacabey", "address": "Karacabey", "lat": 40.214, "lng": 28.362, "rating": 4.1, "blurb": "Karacabey rakı sofrası."},
    {"title": "MKPaşa Meyhane", "ilce": "Mustafakemalpaşa", "address": "MKPaşa", "lat": 40.039, "lng": 28.409, "rating": 4.1, "blurb": "MKPaşa meyhane."},
    {"title": "Kültürpark Meze Bahçesi", "ilce": "Osmangazi", "address": "Kültürpark", "lat": 40.195, "lng": 29.05, "rating": 4.3, "blurb": "Park kenarı meze."},
    {"title": "Hüdavendigar Meyhanesi", "ilce": "Osmangazi", "address": "Hüdavendigar", "lat": 40.188, "lng": 29.048, "rating": 4.2, "blurb": "Semt meyhanesi."},
    {"title": "Demirtaş Meze Evi", "ilce": "Osmangazi", "address": "Demirtaş", "lat": 40.17, "lng": 29.09, "rating": 4.1, "blurb": "Demirtaş rakı-meze."},
]

CURATED_CANTIK = [
    {"title": "Cantıkçı Yıldırım", "ilce": "Yıldırım", "address": "Yıldırım", "lat": 40.19, "lng": 29.11, "rating": 4.5, "blurb": "Klasik Bursa cantık."},
    {"title": "Pidecioğlu Cantık Kayhan", "ilce": "Osmangazi", "address": "Kayhan", "lat": 40.185, "lng": 29.066, "rating": 4.6, "blurb": "Kayhan cantık / pide hattı."},
    {"title": "Tarihi Cantıkçı Osmangazi", "ilce": "Osmangazi", "address": "Çarşı", "lat": 40.184, "lng": 29.064, "rating": 4.5, "blurb": "Çarşı içi cantık."},
    {"title": "Cantık Evi Heykel", "ilce": "Osmangazi", "address": "Heykel", "lat": 40.1845, "lng": 29.0615, "rating": 4.4, "blurb": "Heykel hızlı cantık."},
    {"title": "Cantıkçı Setbaşı", "ilce": "Osmangazi", "address": "Setbaşı", "lat": 40.183, "lng": 29.069, "rating": 4.4, "blurb": "Setbaşı cantık."},
    {"title": "Cantık Dünyası Nilüfer", "ilce": "Nilüfer", "address": "Odunluk", "lat": 40.215, "lng": 28.984, "rating": 4.4, "blurb": "Nilüfer cantık."},
    {"title": "FSM Cantık", "ilce": "Nilüfer", "address": "FSM Blv.", "lat": 40.211, "lng": 28.988, "rating": 4.3, "blurb": "FSM hattı cantık."},
    {"title": "Beşevler Cantıkçı", "ilce": "Nilüfer", "address": "Beşevler", "lat": 40.2085, "lng": 28.996, "rating": 4.3, "blurb": "Beşevler cantık."},
    {"title": "Özlüce Cantık", "ilce": "Nilüfer", "address": "Özlüce", "lat": 40.218, "lng": 28.969, "rating": 4.3, "blurb": "Özlüce cantık."},
    {"title": "Görükle Cantık Evi", "ilce": "Nilüfer", "address": "Görükle", "lat": 40.2235, "lng": 28.873, "rating": 4.2, "blurb": "Görükle öğrenci cantık."},
    {"title": "Arabayatağı Cantıkçı", "ilce": "Yıldırım", "address": "Arabayatağı", "lat": 40.195, "lng": 29.129, "rating": 4.3, "blurb": "Yıldırım cantık."},
    {"title": "Esenevler Cantık", "ilce": "Yıldırım", "address": "Esenevler", "lat": 40.19, "lng": 29.119, "rating": 4.2, "blurb": "Esenevler cantık."},
    {"title": "Yeşil Cantık", "ilce": "Yıldırım", "address": "Yeşil", "lat": 40.181, "lng": 29.085, "rating": 4.3, "blurb": "Yeşil mahalle cantık."},
    {"title": "Emirsultan Cantıkçı", "ilce": "Yıldırım", "address": "Emirsultan", "lat": 40.178, "lng": 29.09, "rating": 4.2, "blurb": "Emirsultan cantık."},
    {"title": "Mudanya Cantık", "ilce": "Mudanya", "address": "Mudanya merkez", "lat": 40.374, "lng": 28.881, "rating": 4.2, "blurb": "Mudanya cantık."},
    {"title": "Gemlik Cantıkçı", "ilce": "Gemlik", "address": "Gemlik", "lat": 40.429, "lng": 29.154, "rating": 4.1, "blurb": "Gemlik cantık."},
    {"title": "İnegöl Cantık", "ilce": "İnegöl", "address": "İnegöl", "lat": 40.0785, "lng": 29.512, "rating": 4.2, "blurb": "İnegöl cantık."},
    {"title": "Kestel Cantıkçı", "ilce": "Kestel", "address": "Kestel", "lat": 40.1985, "lng": 29.211, "rating": 4.1, "blurb": "Kestel cantık."},
    {"title": "Gürsu Cantık", "ilce": "Gürsu", "address": "Gürsu", "lat": 40.2185, "lng": 29.194, "rating": 4.1, "blurb": "Gürsu cantık."},
    {"title": "Demirtaş Cantık Evi", "ilce": "Osmangazi", "address": "Demirtaş", "lat": 40.171, "lng": 29.088, "rating": 4.2, "blurb": "Demirtaş cantık."},
    {"title": "Emek Cantıkçı", "ilce": "Osmangazi", "address": "Emek", "lat": 40.205, "lng": 29.01, "rating": 4.1, "blurb": "Emek semt cantık."},
    {"title": "Bağlaraltı Cantık", "ilce": "Osmangazi", "address": "Bağlaraltı", "lat": 40.2, "lng": 29.045, "rating": 4.1, "blurb": "Bağlaraltı cantık."},
]

CURATED_BAR = [
    {"title": "Hayal Kahvesi Özlüce", "ilce": "Nilüfer", "address": "Özlüce", "lat": 40.22, "lng": 28.97, "rating": 4.5, "blurb": "Canlı müzik · bar · konser."},
    {"title": "Rooftop Bar · FSM", "ilce": "Nilüfer", "address": "FSM", "lat": 40.212, "lng": 28.988, "rating": 4.4, "blurb": "Manzaralı çatı bar."},
    {"title": "Odunluk Pub", "ilce": "Nilüfer", "address": "Odunluk", "lat": 40.216, "lng": 28.984, "rating": 4.3, "blurb": "Nilüfer akşam pub’ı."},
    {"title": "The North Shield · Nilüfer", "ilce": "Nilüfer", "address": "Nilüfer Hatun Cd.", "lat": 40.21, "lng": 28.99, "rating": 4.4, "blurb": "İrlanda pub zinciri."},
    {"title": "Just Beer", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.214, "lng": 28.986, "rating": 4.4, "blurb": "Craft bira bar."},
    {"title": "Ivory Pub", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.213, "lng": 28.985, "rating": 4.3, "blurb": "Pub & canlı müzik."},
    {"title": "Minty Social", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.2125, "lng": 28.983, "rating": 4.3, "blurb": "Social bar."},
    {"title": "Drop Lounge & Bar", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.215, "lng": 28.981, "rating": 4.3, "blurb": "Lounge bar."},
    {"title": "La Luz", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.2118, "lng": 28.987, "rating": 4.2, "blurb": "Kokteyl bar."},
    {"title": "Nona Hookah Lounge", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.2142, "lng": 28.982, "rating": 4.2, "blurb": "Lounge / nargile bar."},
    {"title": "Şarlo Pub", "ilce": "Osmangazi", "address": "Osmangazi", "lat": 40.19, "lng": 29.055, "rating": 4.3, "blurb": "Merkez pub."},
    {"title": "Demo Pub", "ilce": "Osmangazi", "address": "Osmangazi", "lat": 40.188, "lng": 29.06, "rating": 4.2, "blurb": "Live / pub."},
    {"title": "Caddeüstü Pub", "ilce": "Osmangazi", "address": "Atatürk Cd. hattı", "lat": 40.1865, "lng": 29.059, "rating": 4.2, "blurb": "Cadde pub."},
    {"title": "Kat3 Teras", "ilce": "Osmangazi", "address": "Osmangazi", "lat": 40.187, "lng": 29.058, "rating": 4.3, "blurb": "Teras bar."},
    {"title": "6:45 Kaybedenler Kulübü", "ilce": "Osmangazi", "address": "Osmangazi", "lat": 40.189, "lng": 29.057, "rating": 4.2, "blurb": "Müzik pub."},
    {"title": "High Out", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.2165, "lng": 28.979, "rating": 4.2, "blurb": "Gece bar."},
    {"title": "Nüans Bistro Bar", "ilce": "Osmangazi", "address": "Akıncı Abidinbey Sk.", "lat": 40.185, "lng": 29.063, "rating": 4.2, "blurb": "Bistro bar."},
    {"title": "Martin Bar", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.2138, "lng": 28.98, "rating": 4.1, "blurb": "Kokteyl."},
    {"title": "Record Performance Hall", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.217, "lng": 28.977, "rating": 4.2, "blurb": "Canlı müzik salonu / bar."},
    {"title": "Gökay Pub Restoran", "ilce": "Nilüfer", "address": "Nilüfer", "lat": 40.21, "lng": 28.978, "rating": 4.1, "blurb": "Pub-restoran."},
    {"title": "David People", "ilce": "Nilüfer", "address": "Nilüfer Hatun Cd.", "lat": 40.2095, "lng": 28.991, "rating": 4.1, "blurb": "Cafe-bar."},
    {"title": "Cihangir Cafe Bar", "ilce": "Nilüfer", "address": "Nilüfer Hatun Cd.", "lat": 40.2098, "lng": 28.9905, "rating": 4.1, "blurb": "Cafe-bar."},
    {"title": "Şey Pub", "ilce": "Osmangazi", "address": "Osmangazi", "lat": 40.191, "lng": 29.052, "rating": 4.1, "blurb": "Pub."},
    {"title": "Mudanya Sahil Bar", "ilce": "Mudanya", "address": "Mudanya sahil", "lat": 40.3755, "lng": 28.8825, "rating": 4.3, "blurb": "Sahil bar."},
    {"title": "Gemlik Marina Bar", "ilce": "Gemlik", "address": "Gemlik marina", "lat": 40.432, "lng": 29.157, "rating": 4.2, "blurb": "Marina bar."},
]


def make_slug(title: str, prefix: str = "") -> str:
    base = slugify(title)
    if prefix:
        return f"{prefix}-{base}"[:80]
    return base[:80]


def upsert(db, *, slug: str, sub: str, title: str, ilce: str, address: str,
           lat, lng, blurb: str, rating: float | None, img: str, tags: list,
           phone: str = "", web: str = "", featured: bool = False) -> str:
    fields = dict(
        title=title[:200],
        category="food",
        subcategory=sub,
        ilce=ilce if ilce in ILCELER else (ilce or "Osmangazi"),
        address=(address or "")[:280],
        lat=lat,
        lng=lng,
        phone=(phone or "")[:40],
        web=(web or "")[:280],
        hours_text="",
        price_band=sub,
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
        # aynı title'dan üretilmiş başka slug olabilir — benzersiz yap
        final = slug
        n = 2
        while db.query(Place).filter(Place.slug == final).first() is not None:
            final = f"{slug}-{n}"[:80]
            n += 1
        db.add(Place(slug=final, **fields))
        db.flush()
        return "new"
    if p.category == "food" and (p.subcategory or "") in (
        "", "kafe", "cafe", "kahvalti", "meyhane", "cantik", "bar", "kofte", sub
    ):
        for k, v in fields.items():
            if k == "img_url" and p.img_url and not v:
                continue
            setattr(p, k, v)
        return "upd"
    return "skip"


def import_osm_delta(db, *, max_age_h: float | None = 16.0, imgs: dict | None = None) -> dict:
    """Yalnız OSM yeme-içme — yeni kayıt, mevcut başlık atlanır. Curated upsert yok."""
    imgs = imgs or LOCAL_IMG
    stats = {"new": 0, "upd": 0, "skip": 0}
    removed_titles, removed_slugs = _removed_place_keys()
    existing_names = {
        slugify(p.title) for p in db.query(Place).filter(Place.category == "food").all()
    } | removed_titles
    for amenity, sub, tags, base_rating, tag in (
        ("cafe", "cafe", ["cafe", "kahve", "osm"], 4.1, "amenity"),
        ("bar", "bar", ["bar", "alkol", "osm"], 4.0, "amenity"),
        ("pub", "bar", ["bar", "pub", "alkol", "osm"], 4.0, "amenity"),
        ("restaurant", "restoran", ["restoran", "osm"], 4.1, "amenity"),
        ("fast_food", "fast-food", ["fast-food", "osm"], 4.0, "amenity"),
        ("ice_cream", "tatli", ["tatli", "osm"], 4.0, "amenity"),
        ("bakery", "pastane", ["pastane", "osm"], 4.0, "shop"),
    ):
        try:
            pts = osm_points(amenity, tag=tag, max_age_h=max_age_h)
        except Exception as e:
            print("osm fail", amenity, e)
            pts = []
        print(f"osm {amenity}: {len(pts)}")
        for i, raw in enumerate(pts):
            nm = slugify(raw["title"])
            slug = make_slug(raw["title"], prefix=f"osm-{amenity}")
            if not nm or nm in existing_names or slug in removed_slugs:
                stats["skip"] = stats.get("skip", 0) + 1
                continue
            existing_names.add(nm)
            sub_use = cuisine_sub(raw.get("cuisine") or "", amenity) if amenity in ("restaurant", "fast_food") else sub
            rating = round(base_rating + max(0, 0.4 - (i * 0.002)), 1)
            hours = raw.get("hours") or ""
            blurb = f"Bursa {sub_use} · {raw['ilce']}."
            if raw.get("cuisine"):
                blurb = f"{raw['cuisine'].replace(';', ', ')} · {raw['ilce']}."
            st = upsert(
                db,
                slug=slug,
                sub=sub_use,
                title=raw["title"],
                ilce=raw["ilce"],
                address=raw.get("address") or "",
                lat=raw.get("lat"),
                lng=raw.get("lng"),
                blurb=blurb[:400],
                rating=min(4.6, rating),
                img=imgs.get(sub_use) or imgs.get("restoran") or imgs.get("cafe") or "",
                tags=list(tags) + ([sub_use] if sub_use not in tags else []),
                phone=raw.get("phone") or "",
                web=raw.get("web") or "",
            )
            if hours and st == "new":
                p = db.query(Place).filter(Place.slug == slug).first()
                if p and not p.hours_text:
                    p.hours_text = hours[:160]
            stats[st] = stats.get(st, 0) + 1
        db.commit()
    return stats


def main() -> None:
    init_db()
    imgs = {k: cache_img(k) for k in IMG}
    db = SessionLocal()
    stats = {"new": 0, "upd": 0, "skip": 0, "kafe_merged": 0}
    try:
        # 1) kafe → cafe birleştir
        for p in db.query(Place).filter(Place.category == "food", Place.subcategory == "kafe").all():
            p.subcategory = "cafe"
            stats["kafe_merged"] += 1

        # 2) curated — iyilerden
        batches = [
            ("kahvalti", CURATED_KAHVALTI, ["kahvalti", "serpme"], True),
            ("cafe", CURATED_CAFE, ["cafe", "kahve"], True),
            ("meyhane", CURATED_MEYHANE, ["meyhane", "raki", "meze"], True),
            ("cantik", CURATED_CANTIK, ["cantik", "pide"], False),
            ("bar", CURATED_BAR, ["bar", "alkol"], False),
        ]
        for sub, rows, tags, feat_top in batches:
            for i, raw in enumerate(rows):
                slug = make_slug(raw["title"])
                # mevcut cantikci-yildirim vb. koru
                st = upsert(
                    db,
                    slug=slug,
                    sub=sub,
                    title=raw["title"],
                    ilce=raw["ilce"],
                    address=raw.get("address") or "",
                    lat=raw.get("lat"),
                    lng=raw.get("lng"),
                    blurb=raw.get("blurb") or "",
                    rating=raw.get("rating"),
                    img=imgs.get(sub) or imgs["cafe"],
                    tags=tags,
                    featured=feat_top and i < 5,
                )
                stats[st] = stats.get(st, 0) + 1

        osm = import_osm_delta(db, max_age_h=None, imgs=imgs)
        for k, v in osm.items():
            stats[k] = stats.get(k, 0) + v

        db.commit()

        # özet
        from collections import Counter

        rows = db.query(Place).filter(Place.category == "food", Place.status == "approved").all()
        c = Counter((p.subcategory or "") for p in rows)
        print("stats", stats)
        print("food approved", len(rows))
        for k, v in c.most_common():
            print(f"  {k}: {v}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
