"""SEO landing tanımları + ilçe slug."""
from __future__ import annotations

from catalog import ILCELER, slugify

# path → meta
SEO_LANDINGS = {
    "bursa-restoranlari": {
        "title": "Bursa Restoranları",
        "h1": "Bursa'da Restoranlar",
        "desc": "Bursa'nın en iyi restoranları: İskender, kebap, balık ve aile mekanları — ilçe ilçe BursaApp rehberi.",
        "category": "food",
        "subcategory": None,
        "exclude_sub": ("cafe",),
    },
    "bursa-cafeler": {
        "title": "Bursa Cafeler",
        "h1": "Bursa'da Cafeler",
        "desc": "Bursa'da çalışmaya uygun, manzaralı ve popüler cafeler — Nilüfer, Osmangazi, Yıldırım.",
        "category": "food",
        "subcategory": "cafe",
    },
    "bursa-kahvalti": {
        "title": "Bursa Kahvaltı",
        "h1": "Bursa'da Kahvaltı Nerede Yapılır?",
        "desc": "Bursa kahvaltı mekanları: serpme, köy kahvaltısı ve merkez adresleri.",
        "category": "food",
        "subcategory": "kahvalti",
    },
    "bursa-kahvalti-mekanlari": {
        "title": "Bursa Kahvaltı Mekanları",
        "h1": "Bursa Kahvaltı Mekanları",
        "desc": "Kahvaltı için önerilen Bursa adresleri — puanlı liste.",
        "category": "food",
        "subcategory": "kahvalti",
    },
    "bursa-konserleri": {
        "title": "Bursa Konserleri",
        "h1": "Bursa'da Konserler",
        "desc": "Bursa yaklaşan konserler: Kültürpark, Merinos, açıkhava — tarih ve bilet bilgisi.",
        "category": "concert",
    },
    "bursa-tiyatro": {
        "title": "Bursa Tiyatro",
        "h1": "Bursa'da Tiyatro",
        "desc": "Bursa tiyatro oyunları ve sahneler — takvim ve salonlar.",
        "category": "theater",
    },
    "bursa-gezilecek-yerler": {
        "title": "Bursa Gezilecek Yerler",
        "h1": "Bursa'da Gezilecek Yerler",
        "desc": "Ulu Cami, Cumalıkızık, Uludağ, Gölyazı ve tarihi hanlar — Bursa gezi rehberi.",
        "category": "visit",
    },
}

ILCE_SLUGS = {slugify(ad): ad for ad in ILCELER}
# bilinen varyantlar
ILCE_SLUGS.update({
    "nilufer": "Nilüfer",
    "osmangazi": "Osmangazi",
    "yildirim": "Yıldırım",
    "inegol": "İnegöl",
    "iznik": "İznik",
    "mustafakemalpasa": "Mustafakemalpaşa",
    "kestel": "Kestel",
    "gursu": "Gürsu",
    "orhangazi": "Orhangazi",
    "karacabey": "Karacabey",
    "yenisehir": "Yenişehir",
    "orhaneli": "Orhaneli",
    "buyukorhan": "Büyükorhan",
    "harmancik": "Harmancık",
    "keles": "Keles",
})

DISTRICT_SECTIONS = (
    ("event", "Etkinlikler", "event"),
    ("food", "Restoranlar", "food"),
    ("cafe", "Cafeler", "food"),
    ("cinema", "Sinemalar", "cinema"),
    ("sport", "Spor", "sport"),
    ("shop", "Alışveriş", "shop"),
    ("market", "Marketler", "market"),
    ("visit", "Gezilecek", "visit"),
    ("hotel", "Oteller", "hotel"),
    ("fun", "Eğlence", "fun"),
)
