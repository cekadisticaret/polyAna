#!/usr/bin/env python3
"""BursaApp içerik zenginleştirme — menü/ücret/kadro/bilet + Bursaspor + Uzi düzeltmesi."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import infer_food_subcategory, tags_dump, unique_slug
from models import Place, SessionLocal, SportMatch, init_db, merge_place_extra, place_extra, set_place_extra

# ---------- Restoran ekleri (araştırma / popüler mekanlar) ----------
NEW_RESTAURANTS = [
    {
        "slug": "kebapci-iskender-yilmaz",
        "title": "Kebapçı İskender · Yılmaz Usta",
        "ilce": "Osmangazi",
        "address": "Ünlü Cad. No:7, Heykel, Osmangazi",
        "phone": "0224 221 0650",
        "web": "https://www.kebapciiskender.com.tr/",
        "hours_text": "11:00–21:00",
        "price_band": "iskender",
        "rating": 4.5,
        "photo": "iskender-4.jpg",
        "tags": ["iskender", "klasik"],
        "blurb": "1883’ten beri İskender markası. Heykel şubesi.",
        "est_meal_tl": 450,
        "menu": [
            {"name": "İskender porsiyon", "price": "420–480 TL", "note": "pide üstü döner"},
            {"name": "Pideli köfte", "price": "380–420 TL", "note": ""},
            {"name": "Yarım porsiyon İskender", "price": "280–320 TL", "note": ""},
            {"name": "Ayran", "price": "40 TL", "note": ""},
        ],
        "gallery": ["/static/food/iskender-4.jpg", "/static/food/iskender-5.jpg"],
    },
    {
        "slug": "hacibey-iskender",
        "title": "Hacıbey İskender",
        "ilce": "Osmangazi",
        "address": "Atatürk Cad. / Heykel civarı, Osmangazi",
        "phone": "",
        "hours_text": "öğün",
        "price_band": "iskender",
        "rating": 4.4,
        "photo": "iskender-5.jpg",
        "tags": ["iskender"],
        "blurb": "Merkezde klasik İskender.",
        "est_meal_tl": 400,
        "menu": [
            {"name": "İskender", "price": "390–450 TL", "note": ""},
            {"name": "Çocuk porsiyon", "price": "250 TL", "note": ""},
        ],
    },
    {
        "slug": "cicek-izgara",
        "title": "Çiçek Izgara",
        "ilce": "Osmangazi",
        "address": "Ünlü Cad., Osmangazi",
        "hours_text": "11:00–22:00",
        "price_band": "köfte",
        "rating": 4.6,
        "photo": "kofte-1.jpg",
        "tags": ["kofte", "izgara"],
        "blurb": "Bursa’nın efsane köftecilerinden. Porsiyon + ayran klasik.",
        "est_meal_tl": 350,
        "menu": [
            {"name": "Köfte porsiyon", "price": "320–380 TL", "note": "pilav/salata"},
            {"name": "Pideli köfte", "price": "360 TL", "note": ""},
            {"name": "Izgara karışık", "price": "450 TL", "note": ""},
        ],
        "gallery": ["/static/food/kofte-1.jpg", "/static/food/kofte-2.jpg"],
    },
    {
        "slug": "kent-lokantasi",
        "title": "Kent Lokantası",
        "ilce": "Osmangazi",
        "address": "Heykel / Çarşı, Osmangazi",
        "hours_text": "11:00–21:00",
        "price_band": "lokanta",
        "rating": 4.3,
        "photo": "lokanta-1.jpg",
        "tags": ["ev-yemegi", "lokanta"],
        "blurb": "Günlük ev yemekleri, çorba + ana yemek menüsü.",
        "est_meal_tl": 280,
        "menu": [
            {"name": "Günün menüsü", "price": "250–320 TL", "note": "çorba+ana+salata"},
            {"name": "Çorba", "price": "80 TL", "note": ""},
        ],
    },
    {
        "slug": "mura-kebap",
        "title": "Mura Kebap",
        "ilce": "Nilüfer",
        "address": "Özlüce / Nilüfer",
        "hours_text": "12:00–23:00",
        "price_band": "kebap",
        "rating": 4.5,
        "photo": "ocakbasi-2.jpg",
        "tags": ["kebap", "ocakbasi"],
        "blurb": "Nilüfer tarafında ocakbaşı ve kebap.",
        "est_meal_tl": 500,
        "menu": [
            {"name": "Adana / Urfa", "price": "380 TL", "note": ""},
            {"name": "Karışık ızgara", "price": "650 TL", "note": "2 kişilik"},
            {"name": "İskender usulü", "price": "420 TL", "note": ""},
        ],
    },
    {
        "slug": "pide-sarayi-bursa",
        "title": "Pide Sarayı",
        "ilce": "Yıldırım",
        "address": "Yıldırım, Bursa",
        "hours_text": "10:00–22:00",
        "price_band": "pide",
        "rating": 4.4,
        "photo": "pide-1.jpg",
        "tags": ["pide", "lahmacun"],
        "blurb": "Kıymalı, kuşbaşılı, kaşarlı pide.",
        "est_meal_tl": 250,
        "menu": [
            {"name": "Kıymalı pide", "price": "220 TL", "note": ""},
            {"name": "Kuşbaşılı", "price": "260 TL", "note": ""},
            {"name": "Lahmacun", "price": "90 TL", "note": ""},
        ],
    },
    {
        "slug": "balikci-yunus",
        "title": "Balıkçı Yunus",
        "ilce": "Mudanya",
        "address": "Mudanya sahil",
        "hours_text": "12:00–23:00",
        "price_band": "balık",
        "rating": 4.5,
        "photo": "balik-1.jpg",
        "tags": ["balik", "deniz"],
        "blurb": "Mudanya’da taze balık ve mezeler.",
        "est_meal_tl": 700,
        "menu": [
            {"name": "Günün balığı", "price": "piyasa", "note": "ızgara/tava"},
            {"name": "Karışık meze", "price": "450 TL", "note": ""},
            {"name": "Kalamar", "price": "380 TL", "note": ""},
        ],
        "gallery": ["/static/food/balik-1.jpg", "/static/food/deniz-1.jpg"],
    },
    {
        "slug": "golyazi-balik",
        "title": "Gölyazı Balık Restaurant",
        "ilce": "Nilüfer",
        "address": "Gölyazı, Nilüfer",
        "hours_text": "11:00–22:00",
        "price_band": "balık",
        "rating": 4.4,
        "photo": "deniz-2.jpg",
        "tags": ["balik", "golyazi"],
        "blurb": "Göl manzaralı balık ve meze.",
        "est_meal_tl": 650,
        "menu": [
            {"name": "Levrek / Çipura", "price": "piyasa", "note": ""},
            {"name": "Meze tabağı", "price": "400 TL", "note": ""},
        ],
    },
    {
        "slug": "villa-mangia",
        "title": "Villa Mangia",
        "ilce": "Nilüfer",
        "address": "Nilüfer, Bursa",
        "hours_text": "12:00–23:00",
        "price_band": "fine-dining",
        "rating": 4.6,
        "photo": "fine-1.jpg",
        "tags": ["italyan", "fine"],
        "blurb": "İtalyan mutfağı, pizza ve pasta.",
        "est_meal_tl": 800,
        "menu": [
            {"name": "Pizza margherita", "price": "380 TL", "note": ""},
            {"name": "Pasta carbonara", "price": "420 TL", "note": ""},
            {"name": "Risotto", "price": "450 TL", "note": ""},
        ],
    },
    {
        "slug": "kahvalti-evi-cumalikizik",
        "title": "Cumalıkızık Kahvaltı Evleri",
        "ilce": "Yıldırım",
        "address": "Cumalıkızık köyü",
        "hours_text": "08:00–17:00",
        "price_band": "kahvaltı",
        "rating": 4.5,
        "photo": "kahvalti-1.jpg",
        "tags": ["kahvalti", "koy"],
        "blurb": "Köy kahvaltısı, reçel, gözleme, menemen.",
        "est_meal_tl": 450,
        "menu": [
            {"name": "Serpme kahvaltı (kişi)", "price": "400–500 TL", "note": ""},
            {"name": "Gözleme", "price": "120 TL", "note": ""},
            {"name": "Menemen", "price": "150 TL", "note": ""},
        ],
    },
    {
        "slug": "manti-evi-bursa",
        "title": "Mantı Evi Bursa",
        "ilce": "Nilüfer",
        "address": "Nilüfer, Bursa",
        "hours_text": "11:00–21:00",
        "price_band": "mantı",
        "rating": 4.4,
        "photo": "manti-1.jpg",
        "tags": ["manti"],
        "blurb": "Kayseri usulü ve Bursa usulü mantı.",
        "est_meal_tl": 300,
        "menu": [
            {"name": "Kayseri mantı", "price": "280 TL", "note": ""},
            {"name": "Fırın mantı", "price": "300 TL", "note": ""},
        ],
    },
    {
        "slug": "anadolu-sofrasi",
        "title": "Anadolu Sofrası",
        "ilce": "Osmangazi",
        "address": "Osmangazi, Bursa",
        "hours_text": "11:00–22:00",
        "price_band": "lokanta",
        "rating": 4.3,
        "photo": "anadolu-1.jpg",
        "tags": ["anadolu", "kebap"],
        "blurb": "Anadolu mutfağı, güveç ve kebaplar.",
        "est_meal_tl": 400,
        "menu": [
            {"name": "Güveç", "price": "380 TL", "note": ""},
            {"name": "Ali nazik", "price": "420 TL", "note": ""},
        ],
    },
    {
        "slug": "bahce-cafe-kulturpark",
        "title": "Kültürpark Bahçe Cafe",
        "ilce": "Osmangazi",
        "address": "Kültürpark, Osmangazi",
        "hours_text": "10:00–23:00",
        "price_band": "cafe",
        "rating": 4.2,
        "photo": "bahce-1.jpg",
        "tags": ["cafe", "bahce"],
        "blurb": "Park içi kahve, tost, tatlı.",
        "est_meal_tl": 250,
        "menu": [
            {"name": "Filtre kahve", "price": "120 TL", "note": ""},
            {"name": "Tost menü", "price": "220 TL", "note": ""},
        ],
    },
    {
        "slug": "kavurma-evi",
        "title": "Kavurma Evi",
        "ilce": "Osmangazi",
        "address": "Osmangazi, Bursa",
        "hours_text": "öğün",
        "price_band": "kavurma",
        "rating": 4.4,
        "photo": "kavurma-1.jpg",
        "tags": ["kavurma", "et"],
        "blurb": "Tereyağlı kavurma ve pilav.",
        "est_meal_tl": 380,
        "menu": [
            {"name": "Kavurma porsiyon", "price": "360 TL", "note": ""},
            {"name": "Kavurmalı yumurta", "price": "280 TL", "note": ""},
        ],
    },
    {
        "slug": "konak-alti-restoran",
        "title": "Konak Altı Restoran",
        "ilce": "Osmangazi",
        "address": "Tophane / Hisar, Osmangazi",
        "hours_text": "11:00–23:00",
        "price_band": "kebap",
        "rating": 4.5,
        "photo": "konak-1.jpg",
        "tags": ["manzara", "kebap"],
        "blurb": "Hisar manzaralı kebap ve meze.",
        "est_meal_tl": 550,
        "menu": [
            {"name": "Karışık ızgara", "price": "600 TL", "note": ""},
            {"name": "İskender", "price": "420 TL", "note": ""},
        ],
        "gallery": ["/static/food/konak-1.jpg", "/static/food/fine-2.jpg"],
    },
]

# Mevcut restoranlara menü yaması (slug → menu)
MENU_PATCH = {
    "tarihi-bursa-carsi-kebapcisi": [
        {"name": "İskender", "price": "400–460 TL", "note": "çarşı klasik"},
        {"name": "Pideli köfte", "price": "360 TL", "note": ""},
        {"name": "Ayran", "price": "40 TL", "note": ""},
    ],
    "kuskular-doner-kanalboyu": [
        {"name": "Döner porsiyon", "price": "320–380 TL", "note": ""},
        {"name": "Dürüm", "price": "220 TL", "note": ""},
        {"name": "İskender usulü", "price": "400 TL", "note": ""},
    ],
    "tarihi-konak-kebap": [
        {"name": "İskender", "price": "420 TL", "note": ""},
        {"name": "Pideli köfte", "price": "380 TL", "note": ""},
    ],
    "donerci-adnan-usta": [
        {"name": "Döner porsiyon", "price": "340 TL", "note": ""},
        {"name": "İskender", "price": "400 TL", "note": ""},
    ],
    "kebapci-huseyin-usta": [
        {"name": "Tereyağlı İskender", "price": "430 TL", "note": "Tuzpazarı"},
        {"name": "Yarım porsiyon", "price": "280 TL", "note": ""},
    ],
    "uludag-kebapcisi-cemal-cemil": [
        {"name": "İskender", "price": "420 TL", "note": "Eski Garaj"},
        {"name": "Köfte", "price": "360 TL", "note": ""},
    ],
}

HOSPITAL_EXTRA = {
    "bursa-sehir-hastanesi": {
        "services": [
            "Acil servis 7/24",
            "Genel cerrahi",
            "Kardiyoloji / KVC",
            "Onkoloji",
            "Kadın doğum",
            "Çocuk / yenidoğan",
            "MR · BT · röntgen",
            "Yoğun bakım",
        ],
        "fees": [
            {"name": "Muayene (SGK)", "price": "katkı payı", "note": "MHRS / 182"},
            {"name": "Özel / ücretli", "price": "kuruma göre", "note": "vezne"},
        ],
        "fee_note": "Devlet hastanesi — randevu MHRS (182). Ücretler SGK kapsamına göre değişir.",
        "staff": [],
    },
    "acibadem-bursa": {
        "services": [
            "Check-up",
            "Kardiyoloji",
            "Ortopedi",
            "Kadın doğum",
            "Göz",
            "Kulak burun boğaz",
            "Acil",
            "Görüntüleme (MR/BT)",
        ],
        "fees": [
            {"name": "Uzman muayene", "price": "2.500–4.500 TL", "note": "branşa göre (tahmini 2026)"},
            {"name": "Profesör muayene", "price": "4.000–7.000 TL", "note": "tahmini"},
            {"name": "Kontrol", "price": "muayene × ~0.5", "note": "10–15 gün"},
        ],
        "fee_note": "Özel hastane — güncel fiyat için 444 55 44 / acibadem.com.tr. Fiyatlar bilgilendirme amaçlıdır.",
    },
    "medical-park-bursa": {
        "services": ["Acil", "Cerrahi", "Dahiliye", "Kardiyoloji", "Doğum", "Check-up"],
        "fees": [
            {"name": "Uzman muayene", "price": "2.000–4.000 TL", "note": "tahmini"},
            {"name": "Check-up paketleri", "price": "değişken", "note": "web"},
        ],
        "fee_note": "Medical Park Bursa — randevu ve fiyat için hastane çağrı merkezi.",
    },
    "medicana-bursa": {
        "services": ["Acil", "Kardiyoloji", "Ortopedi", "Nöroloji", "Check-up"],
        "fees": [
            {"name": "Uzman muayene", "price": "2.000–3.800 TL", "note": "tahmini"},
        ],
        "fee_note": "Medicana Bursa — güncel ücretler için 444 22 00.",
    },
}

VET_EXTRA = {
    "buu-hayvan-hastanesi": {
        "services": ["Dahiliye", "Cerrahi", "Görüntüleme", "Doğum", "Acil (mesai)"],
        "fees": [
            {"name": "Muayene", "price": "800–1.500 TL", "note": "tahmini · türe göre"},
            {"name": "Aşı", "price": "değişken", "note": ""},
        ],
        "fee_note": "Üniversite hayvan hastanesi — güncel tarife için 0224 294 08 01.",
        "staff": [
            {"name": "Fakülte klinik kadrosu", "role": "öğretim üyesi + asistan"},
        ],
    },
    "akademi-hayvan-hastanesi": {
        "services": ["Muayene", "Cerrahi", "Laboratuvar", "Pet hotel (ilan)"],
        "fees": [
            {"name": "Muayene", "price": "1.000–1.800 TL", "note": "tahmini"},
            {"name": "Kontrol", "price": "600–1.000 TL", "note": ""},
        ],
        "staff": [
            {"name": "Klinik hekim kadrosu", "role": "BVHO kayıtlı"},
        ],
        "fee_note": "Odunluk — randevu için klinik telefonunu arayın.",
    },
    "pakvet": {
        "services": ["Kedi-köpek", "Egzotik", "Diş", "7/24 acil (ilan)"],
        "fees": [
            {"name": "Muayene", "price": "1.200–2.000 TL", "note": "tahmini"},
        ],
        "staff": [
            {"name": "Hüseyin Alper Pakyürek", "role": "Veteriner hekim"},
        ],
    },
    "petclass": {
        "services": ["Muayene", "Aşı", "Tüy bakımı yönlendirme"],
        "fees": [{"name": "Muayene", "price": "1.000–1.600 TL", "note": "tahmini"}],
        "staff": [{"name": "Klinik hekim", "role": "Veteriner hekim"}],
    },
    "nilufer-veteriner-poliklinik": {
        "services": ["Muayene", "Aşı", "Cerrahi yönlendirme"],
        "fees": [{"name": "Muayene", "price": "1.000–1.700 TL", "note": "tahmini"}],
        "staff": [{"name": "Poliklinik hekimleri", "role": "Veteriner hekim"}],
    },
}

# Bursaspor 2026-27 (Wikipedia / TFF özeti)
MATCHES = [
    {"week": 0, "kickoff": "2026-07-09T17:00", "home": "Bursaspor", "away": "Batman Petrolspor", "venue": "Bolu · hazırlık", "is_home": True, "hs": 1, "as": 1, "comp": "Hazırlık"},
    {"week": 0, "kickoff": "2026-07-26T19:00", "home": "Bursaspor", "away": "Shakhtar Donetsk", "venue": "Atatürk Spor Kompleksi", "is_home": True, "hs": 0, "as": 0, "comp": "Hazırlık"},
    {"week": 1, "kickoff": "2026-08-09T21:30", "home": "Bodrum FK", "away": "Bursaspor", "venue": "Bodrum İlçe Stadyumu", "is_home": False, "hs": 0, "as": 2, "comp": "1. Lig"},
    {"week": 2, "kickoff": "2026-08-15T21:30", "home": "Bursaspor", "away": "Iğdır FK", "venue": "Bursa Büyükşehir Belediye Stadyumu", "is_home": True, "hs": 1, "as": 0, "comp": "1. Lig", "ticket_price": "Kombine / Passolig", "ticket_url": "https://www.bursaspor.org.tr/"},
    {"week": 3, "kickoff": "2026-08-21T21:30", "home": "Fatih Karagümrük", "away": "Bursaspor", "venue": "Yusuf Ziya Öniş", "is_home": False, "hs": 2, "as": 1, "comp": "1. Lig"},
    {"week": 4, "kickoff": "2026-08-29T19:00", "home": "Kayserispor", "away": "Bursaspor", "venue": "Kadir Has", "is_home": False, "comp": "1. Lig"},
    {"week": 5, "kickoff": "2026-09-03T20:00", "home": "Bursaspor", "away": "İstanbulspor", "venue": "Bursa Büyükşehir Belediye Stadyumu", "is_home": True, "comp": "1. Lig", "ticket_price": "Passolig", "ticket_url": "https://www.bursaspor.org.tr/"},
    {"week": 6, "kickoff": "2026-09-07T20:00", "home": "Manisa FK", "away": "Bursaspor", "venue": "19 Mayıs Stadyumu", "is_home": False, "comp": "1. Lig"},
    {"week": 7, "kickoff": "2026-09-13T20:00", "home": "Bursaspor", "away": "Esenler Erokspor", "venue": "Bursa Büyükşehir Belediye Stadyumu", "is_home": True, "comp": "1. Lig", "ticket_url": "https://www.bursaspor.org.tr/"},
    {"week": 8, "kickoff": "2026-09-19T20:00", "home": "Batman Petrolspor", "away": "Bursaspor", "venue": "Batman", "is_home": False, "comp": "1. Lig"},
    {"week": 9, "kickoff": "2026-10-11T20:00", "home": "Bursaspor", "away": "Mardin 1969", "venue": "Bursa Büyükşehir Belediye Stadyumu", "is_home": True, "comp": "1. Lig", "ticket_url": "https://www.bursaspor.org.tr/"},
    {"week": 10, "kickoff": "2026-10-14T20:00", "home": "Muğlaspor", "away": "Bursaspor", "venue": "Muğla", "is_home": False, "comp": "1. Lig"},
    {"week": 11, "kickoff": "2026-10-18T20:00", "home": "Bursaspor", "away": "Pendikspor", "venue": "Bursa Büyükşehir Belediye Stadyumu", "is_home": True, "comp": "1. Lig", "ticket_url": "https://www.bursaspor.org.tr/"},
    {"week": 12, "kickoff": "2026-10-25T20:00", "home": "Keçiörengücü", "away": "Bursaspor", "venue": "Aktepe", "is_home": False, "comp": "1. Lig"},
    {"week": 13, "kickoff": "2026-11-01T20:00", "home": "Bursaspor", "away": "Bandırmaspor", "venue": "Bursa Büyükşehir Belediye Stadyumu", "is_home": True, "comp": "1. Lig", "ticket_url": "https://www.bursaspor.org.tr/"},
    {"week": 14, "kickoff": "2026-11-08T20:00", "home": "Antalyaspor", "away": "Bursaspor", "venue": "Antalya Stadyumu", "is_home": False, "comp": "1. Lig"},
    {"week": 15, "kickoff": "2026-11-22T20:00", "home": "Bursaspor", "away": "Sivasspor", "venue": "Bursa Büyükşehir Belediye Stadyumu", "is_home": True, "comp": "1. Lig", "ticket_url": "https://www.bursaspor.org.tr/"},
    {"week": 16, "kickoff": "2026-11-29T20:00", "home": "Vanspor", "away": "Bursaspor", "venue": "Van", "is_home": False, "comp": "1. Lig"},
    {"week": 17, "kickoff": "2026-12-06T20:00", "home": "Bursaspor", "away": "Boluspor", "venue": "Bursa Büyükşehir Belediye Stadyumu", "is_home": True, "comp": "1. Lig", "ticket_url": "https://www.bursaspor.org.tr/"},
    {"week": 18, "kickoff": "2026-12-13T20:00", "home": "Sarıyer", "away": "Bursaspor", "venue": "İstanbul", "is_home": False, "comp": "1. Lig"},
    {"week": 19, "kickoff": "2026-12-20T20:00", "home": "Bursaspor", "away": "Ümraniyespor", "venue": "Bursa Büyükşehir Belediye Stadyumu", "is_home": True, "comp": "1. Lig", "ticket_url": "https://www.bursaspor.org.tr/"},
]


def _upsert_restaurant(db, raw: dict) -> str:
    slug = raw["slug"]
    img = raw.get("photo") or ""
    img_url = f"/static/food/{img}" if img and not str(img).startswith("/") else (img or "")
    tags = list(raw.get("tags") or []) + ["restoran"]
    sub = (raw.get("subcategory") or "").strip() or infer_food_subcategory(raw.get("price_band") or "", tags)
    p = db.query(Place).filter(Place.slug == slug).first()
    fields = dict(
        title=raw["title"],
        category="food",
        subcategory=sub,
        ilce=raw.get("ilce") or "",
        address=raw.get("address") or "",
        phone=raw.get("phone") or "",
        web=raw.get("web") or "",
        hours_text=raw.get("hours_text") or "",
        price_band=raw.get("price_band") or "",
        blurb=raw.get("blurb") or "",
        body=raw.get("body") or raw.get("blurb") or "",
        img_url=img_url,
        tags=tags_dump(tags),
        rating_admin=float(raw.get("rating") or 0) or None,
        featured=bool(raw.get("featured")),
        status="approved",
        est_meal_tl=int(raw.get("est_meal_tl") or 0),
    )
    if p is None:
        p = Place(slug=slug, **fields)
        db.add(p)
        db.flush()
        action = "new"
    else:
        for k, v in fields.items():
            setattr(p, k, v)
        action = "upd"
    ex = place_extra(p)
    if raw.get("menu"):
        ex["menu"] = raw["menu"]
        p.menu_text = "\n".join(
            f"{i['name']} | {i.get('price','')} | {i.get('note','')}".strip(" |") for i in raw["menu"]
        )
    if raw.get("gallery"):
        ex["gallery"] = raw["gallery"]
    set_place_extra(p, ex)
    return action


def fix_uzi(db) -> None:
    p = db.query(Place).filter(Place.slug == "konser-uzi-20260920").first()
    if not p:
        return
    p.title = "Uzi"
    p.img_url = "/static/concert/konser-uzi-20260920.jpg"
    p.venue_name = "Hayal Kahvesi Bursa"
    p.ilce = "Nilüfer"
    p.address = "29 Ekim Mah. Ahmet Taner Kışlalı Bulv., Özlüce, Nilüfer"
    p.starts_at = datetime(2026, 9, 20, 20, 30)
    p.ticket_price = "900–1.000 TL"
    p.ticket_url = "https://www.etkinlinkler.com/etkinlik/uzi-2026-09-20-203000-868798/4297"
    p.web = "https://eventpal.co/bursa"
    p.blurb = "Türkçe rap · 20 Eylül 2026 20:30 · Hayal Kahvesi Bursa. Bilet: Biletix / Bubilet (EventPal karşılaştırma)."
    p.body = (
        "Uzi (Utku Cihan Yalçınkaya) 20 Eylül 2026’da Hayal Kahvesi Bursa’da sahne alıyor. "
        "Bilet fiyatları yaklaşık 900–1.000 TL. Satış: Biletix ve Bubilet. "
        "6 yaş sınırı vardır. BursaApp üzerinden bilet satışı yoktur."
    )
    p.price_band = "Konser"
    # seed JSON kopyası da güncellensin diye not


def seed_matches(db) -> int:
    # wipe season then insert
    db.query(SportMatch).filter(SportMatch.club == "bursaspor", SportMatch.season == "2026-27").delete()
    n = 0
    for row in MATCHES:
        ko = datetime.strptime(row["kickoff"], "%Y-%m-%dT%H:%M") if row.get("kickoff") else None
        db.add(
            SportMatch(
                club="bursaspor",
                season="2026-27",
                week=row.get("week"),
                competition=row.get("comp") or "1. Lig",
                kickoff_at=ko,
                home_team=row["home"],
                away_team=row["away"],
                home_score=row.get("hs"),
                away_score=row.get("as"),
                venue=row.get("venue") or "",
                is_home=bool(row.get("is_home")),
                ticket_price=row.get("ticket_price") or "",
                ticket_url=row.get("ticket_url") or "",
                status="played" if row.get("hs") is not None else "scheduled",
            )
        )
        n += 1
    return n


def enrich_existing(db) -> dict:
    stats = {"menu": 0, "hospital": 0, "vet": 0, "doctor": 0, "ticket": 0}
    for slug, menu in MENU_PATCH.items():
        p = db.query(Place).filter(Place.slug == slug).first()
        if not p:
            continue
        merge_place_extra(p, {"menu": menu, "gallery": [p.img_url] if p.img_url else []})
        p.menu_text = "\n".join(f"{i['name']} | {i.get('price','')}" for i in menu)
        if not p.est_meal_tl:
            p.est_meal_tl = 400
        stats["menu"] += 1

    for slug, ex in HOSPITAL_EXTRA.items():
        p = db.query(Place).filter(Place.slug == slug).first()
        if not p:
            continue
        merge_place_extra(p, ex)
        # link doctors as staff names from DB
        docs = (
            db.query(Place)
            .filter(Place.category == "doctor", Place.venue_name == slug, Place.status == "approved")
            .limit(40)
            .all()
        )
        if docs:
            staff = [{"name": d.title, "role": d.price_band or "Hekim"} for d in docs[:25]]
            merge_place_extra(p, {"staff": staff})
        stats["hospital"] += 1

    for slug, ex in VET_EXTRA.items():
        p = db.query(Place).filter(Place.slug == slug).first()
        if not p:
            continue
        merge_place_extra(p, ex)
        stats["vet"] += 1

    # doktor specialty_detail
    for d in db.query(Place).filter(Place.category == "doctor", Place.status == "approved").limit(200):
        branch = d.price_band or ""
        if branch and not place_extra(d).get("specialty_detail"):
            hosp = d.venue_name or ""
            merge_place_extra(
                d,
                {
                    "specialty_detail": f"{branch} uzmanı."
                    + (f" Bağlı kurum: {hosp}." if hosp else ""),
                },
            )
            stats["doctor"] += 1

    # konser/etkinlik boş bilet → genel yönlendirme
    for p in db.query(Place).filter(
        Place.category.in_(("concert", "event", "theater")),
        Place.status == "approved",
    ):
        if p.ticket_price and p.ticket_url:
            continue
        if not p.ticket_url and p.web:
            p.ticket_url = p.web
        if not p.ticket_price:
            p.ticket_price = "Platformdan kontrol edin"
        stats["ticket"] += 1
    return stats


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        fix_uzi(db)
        n_match = seed_matches(db)
        n_new = n_upd = 0
        for raw in NEW_RESTAURANTS:
            a = _upsert_restaurant(db, raw)
            if a == "new":
                n_new += 1
            else:
                n_upd += 1
        stats = enrich_existing(db)
        # shows_concert.json Uzi patch on disk
        shows_path = os.path.join(_DIR, "data", "shows_concert.json")
        try:
            shows = json.loads(open(shows_path, encoding="utf-8").read())
            for s in shows:
                if s.get("slug") == "konser-uzi-20260920":
                    s["venue_name"] = "Hayal Kahvesi Bursa"
                    s["ilce"] = "Nilüfer"
                    s["starts"] = "2026-09-20T20:30:00"
                    s["blurb"] = "20 Eylül 20:30 · Hayal Kahvesi · bilet ~900–1000 TL (Biletix/Bubilet)."
                    s["price_band"] = "Konser"
            open(shows_path, "w", encoding="utf-8").write(json.dumps(shows, ensure_ascii=False, indent=2) + "\n")
        except Exception as e:
            print("shows json skip", e)
        db.commit()
        print(
            f"uzi=ok matches={n_match} restaurants new={n_new} upd={n_upd} "
            f"enrich={stats}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
