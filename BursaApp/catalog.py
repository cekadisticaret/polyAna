"""Kategori / ilçe sabitleri, mekan taksonomisi ve Place sorguları."""
from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy import or_

CATEGORIES = (
    {"key": "food", "path": "/yeme-icme", "label": "Yeme-içme", "hint": "restoran, cafe, İskender, tatlı, pub"},
    {"key": "visit", "path": "/gezilecek", "label": "Gezilecek", "hint": "cami, han, köy, doğa, Uludağ"},
    {"key": "hotel", "path": "/oteller", "label": "Oteller", "hint": "termal, şehir, Uludağ kayak"},
    {"key": "camp", "path": "/kamp", "label": "Kamp", "hint": "milli park, göl, karavan"},
    {"key": "shop", "path": "/alisveris", "label": "Alışveriş", "hint": "AVM, mağaza, outlet, hediyelik"},
    {"key": "market", "path": "/marketler", "label": "Marketler", "hint": "BİM, Özhan, File, Migros — zincir başına bir kayıt"},
    {"key": "sport", "path": "/spor", "label": "Spor", "hint": "fitness, pilates, yüzme, halı saha"},
    {"key": "family", "path": "/aile", "label": "Aile", "hint": "park, piknik, çocuk aktivitesi"},
    {"key": "concert", "path": "/konserler", "label": "Konserler", "hint": "salon, açıkhava, stadyum"},
    {"key": "theater", "path": "/tiyatro", "label": "Tiyatro", "hint": "sahneler ve oyunlar"},
    {"key": "cinema", "path": "/sinema", "label": "Sinema", "hint": "salonlar ve vizyon"},
    {"key": "fun", "path": "/eglence", "label": "Eğlence", "hint": "canlı müzik, bar, bowling, escape"},
    {"key": "event", "path": "/etkinlikler", "label": "Etkinlikler", "hint": "tarihli takvim"},
    {"key": "org", "path": "/organizasyonlar", "label": "Organizasyonlar", "hint": "festival, dernek, ajans"},
    {"key": "hospital", "path": "/hastaneler", "label": "Hastaneler", "hint": "devlet, özel, üniversite"},
    {"key": "doctor", "path": "/doktorlar", "label": "Doktorlar", "hint": "branş + bağlı olduğu hastane"},
    {"key": "dentist", "path": "/dis-hekimleri", "label": "Diş hekimleri", "hint": "ADSM, özel klinik, Dt."},
    {"key": "vet", "path": "/veterinerler", "label": "Veterinerler", "hint": "klinik, hayvan hastanesi"},
    {"key": "school", "path": "/okullar", "label": "Okullar", "hint": "devlet, özel, dershane, özel eğitim, lise"},
)
CAT_BY_KEY = {c["key"]: c for c in CATEGORIES}
CAT_BY_PATH = {c["path"]: c for c in CATEGORIES}
CAT_KEYS = tuple(c["key"] for c in CATEGORIES)

CAT_ICONS = {
    "food": "🍽",
    "visit": "🌿",
    "hotel": "🏨",
    "camp": "⛺",
    "shop": "🛍",
    "market": "🛒",
    "sport": "💪",
    "family": "👨‍👩‍👧",
    "concert": "🎵",
    "theater": "🎭",
    "cinema": "🎬",
    "fun": "🎳",
    "event": "📅",
    "org": "🏛",
    "hospital": "🏥",
    "doctor": "🩺",
    "dentist": "🦷",
    "vet": "🐾",
    "school": "🎓",
    "pharmacy": "💊",
}

# Mobil kategoriler — promosyon kartı stili (ton, vurgu, görsel)
CAT_PROMO_META = {
    "visit": {
        "tone": "pink",
        "pill_tone": "blue",
        "before": "Keşfet ",
        "pill": "cami & köy",
        "after": " rotaları!",
        "cta": "Listeyi aç",
        "img": "visit/cumalikizik.jpg",
    },
    "food": {
        "tone": "yellow",
        "pill_tone": "orange",
        "before": "Lezzet turu: ",
        "pill": "İskender",
        "after": " & kahvaltı",
        "cta": "Mekanları gör",
        "img": "visit/koza-han.jpg",
    },
    "hotel": {
        "tone": "peach",
        "pill_tone": "blue",
        "before": "Konaklama: ",
        "pill": "termal",
        "after": " & şehir otelleri",
        "cta": "Otellere bak",
        "img": "visit/ulu-cami.jpg",
    },
    "camp": {
        "tone": "mint",
        "pill_tone": "blue",
        "before": "Doğada ",
        "pill": "kamp",
        "after": " & karavan",
        "cta": "Alanları keşfet",
        "img": "visit/suuctu.jpg",
    },
    "shop": {
        "tone": "sky",
        "pill_tone": "orange",
        "before": "Alışveriş: ",
        "pill": "AVM",
        "after": " & yerel dükkan",
        "cta": "Mağazalara git",
        "img": "visit/koza-han.jpg",
    },
    "market": {
        "tone": "lemon",
        "pill_tone": "orange",
        "before": "Yakın ",
        "pill": "market",
        "after": " listesi",
        "cta": "Marketleri gör",
        "img": "visit/kale-sokak.jpg",
    },
    "sport": {
        "tone": "lilac",
        "pill_tone": "blue",
        "before": "Aktif yaşam: ",
        "pill": "fitness",
        "after": " & spor salonu",
        "cta": "Salonları bul",
        "img": "visit/panorama-1326.jpg",
    },
    "family": {
        "tone": "rose",
        "pill_tone": "orange",
        "before": "Aile için ",
        "pill": "park",
        "after": " & piknik",
        "cta": "Planla",
        "img": "visit/golyazi.jpg",
    },
    "concert": {
        "tone": "blue",
        "pill_tone": "orange",
        "before": "Bu hafta ",
        "pill": "konser",
        "after": " & sahne",
        "cta": "Bilet değil, rehber",
        "img": "visit/panorama-1326.jpg",
    },
    "theater": {
        "tone": "lavender",
        "pill_tone": "blue",
        "before": "Sahne: ",
        "pill": "tiyatro",
        "after": " oyunları",
        "cta": "Oyunlara bak",
        "img": "visit/muradiye.jpg",
    },
    "cinema": {
        "tone": "indigo",
        "pill_tone": "orange",
        "before": "Vizyonda ",
        "pill": "film",
        "after": " & salonlar",
        "cta": "Vizyona git",
        "img": "visit/tophane.jpg",
    },
    "fun": {
        "tone": "sand",
        "pill_tone": "blue",
        "before": "Gece & ",
        "pill": "eğlence",
        "after": " mekanları",
        "cta": "Keşfet",
        "img": "visit/kale-sokak.jpg",
    },
    "event": {
        "tone": "aqua",
        "pill_tone": "orange",
        "before": "Takvimde ",
        "pill": "etkinlik",
        "after": " seç",
        "cta": "Takvimi aç",
        "img": "visit/yesil-turbe.jpg",
    },
    "org": {
        "tone": "stone",
        "pill_tone": "blue",
        "before": "Festival & ",
        "pill": "organizasyon",
        "after": "",
        "cta": "Listele",
        "img": "visit/inkaya-cinari.jpg",
    },
    "hospital": {
        "tone": "blush",
        "pill_tone": "blue",
        "before": "Sağlık: ",
        "pill": "hastane",
        "after": " rehberi",
        "cta": "Hastaneler",
        "img": "visit/muradiye.jpg",
    },
    "doctor": {
        "tone": "blush",
        "pill_tone": "orange",
        "before": "Branşa göre ",
        "pill": "doktor",
        "after": " listesi",
        "cta": "Doktorlar",
        "img": "visit/ulu-cami.jpg",
    },
    "dentist": {
        "tone": "ice",
        "pill_tone": "blue",
        "before": "Diş kliniği & ",
        "pill": "ADSM",
        "after": "",
        "cta": "Klinikleri gör",
        "img": "visit/yesil-turbe.jpg",
    },
    "vet": {
        "tone": "mint",
        "pill_tone": "orange",
        "before": "Evcil dostlar: ",
        "pill": "veteriner",
        "after": "",
        "cta": "Klinikler",
        "img": "visit/golyazi.jpg",
    },
    "school": {
        "tone": "butter",
        "pill_tone": "blue",
        "before": "Eğitim: ",
        "pill": "okul",
        "after": " rehberi",
        "cta": "Okullar",
        "img": "visit/tirilye.jpg",
    },
}

PHARMACY_PROMO = {
    "key": "pharmacy",
    "path": "/nobetci-eczaneler",
    "label": "Nöbetçi eczaneler",
    "hint": "Bugünkü liste",
    "tone": "ice",
    "pill_tone": "orange",
    "before": "Bugün ",
    "pill": "nöbetçi",
    "after": " eczane",
    "cta": "Listeyi aç",
    "img": "visit/koza-han.jpg",
}

TELEFERIK_PROMO = {
    "key": "teleferik",
    "path": "/uludag-teleferik",
    "label": "Uludağ Teleferik",
    "hint": "Bilet · saat · otobüs",
    "tone": "mint",
    "pill_tone": "orange",
    "before": "Uludağ'a ",
    "pill": "teleferik",
    "after": " — bilet & saat",
    "cta": "Rehberi aç",
    "img": "visit/teleferik.jpg",
}


def category_promo_cards():
    """Mobil /kategoriler promosyon kartları (sıralı)."""
    order = (
        "visit",
        "food",
        "hotel",
        "camp",
        "concert",
        "market",
        "hospital",
        "shop",
        "sport",
        "family",
        "theater",
        "cinema",
        "fun",
        "event",
        "org",
        "doctor",
        "dentist",
        "vet",
        "school",
    )
    by_key = CAT_BY_KEY
    cards = []
    for key in order:
        base = by_key.get(key)
        if not base:
            continue
        meta = CAT_PROMO_META.get(key, {})
        cards.append(
            {
                **base,
                "icon": CAT_ICONS.get(key, "•"),
                "title": base["label"].upper(),
                "tone": meta.get("tone", "stone"),
                "pill_tone": meta.get("pill_tone", "blue"),
                "before": meta.get("before", ""),
                "pill": meta.get("pill", base["label"].lower()),
                "after": meta.get("after", ""),
                "cta": meta.get("cta", "Listeyi aç"),
                "img": meta.get("img", "visit/ulu-cami.jpg"),
            }
        )
        if key == "visit":
            cards.append(
                {
                    **TELEFERIK_PROMO,
                    "icon": "🚡",
                    "title": TELEFERIK_PROMO["label"].upper(),
                }
            )
    cards.append(
        {
            **PHARMACY_PROMO,
            "icon": CAT_ICONS["pharmacy"],
            "title": PHARMACY_PROMO["label"].upper(),
        }
    )
    return cards


# Ana grup → (category, alt tür slug → etiket)
MEKAN_TAXONOMY = {
    "food": (
        ("restoran", "Restoran"),
        ("iskender", "İskender"),
        ("kebap", "Kebap"),
        ("doner", "Döner"),
        ("inegol-kofte", "İnegöl köfte"),
        ("pide", "Pide"),
        ("cantik", "Cantık"),
        ("balik", "Balık"),
        ("burger", "Burger"),
        ("pizza", "Pizza"),
        ("fast-food", "Fast food"),
        ("kahvalti", "Kahvaltı"),
        ("tatli", "Tatlı"),
        ("pastane", "Pastane"),
        ("vegan", "Vegan"),
        ("vejetaryen", "Vejetaryen"),
        ("cafe", "Cafe"),
        ("meyhane", "Meyhane"),
        ("bar", "Bar"),
    ),
    "fun": (
        ("pub", "Pub"),
        ("bar", "Bar"),
        ("gece-kulubu", "Gece kulübü"),
        ("bowling", "Bowling"),
        ("bilardo", "Bilardo"),
        ("karaoke", "Karaoke"),
        ("oyun-salonu", "Oyun salonu"),
        ("vr", "VR"),
        ("sinema-salon", "Sinema"),
        ("canli-muzik", "Canlı müzik"),
        ("escape", "Escape"),
    ),
    "family": (
        ("cocuk-oyun", "Çocuk oyun alanı"),
        ("park", "Park"),
        ("piknik", "Piknik alanı"),
        ("hayvanat", "Hayvanat bahçesi"),
        ("aile-restoran", "Aile restoranı"),
        ("cocuk-etkinlik", "Çocuk etkinlikleri"),
    ),
    "hotel": (
        ("otel", "Otel"),
        ("butik", "Butik otel"),
        ("bungalov", "Bungalov"),
        ("dag-evi", "Dağ evi"),
        ("termal", "Termal otel"),
        ("pansiyon", "Pansiyon"),
    ),
    "shop": (
        ("avm", "AVM"),
        ("magaza", "Mağaza"),
        ("outlet", "Outlet"),
        ("antika", "Antika"),
        ("hediyelik", "Hediyelik eşya"),
        ("yerel", "Yerel ürünler"),
    ),
    "market": (
        ("hipermarket", "Hipermarket"),
        ("supermarket", "Süpermarket"),
        ("indirim", "İndirim marketi"),
        ("gourmet", "Gourmet"),
        ("toptan", "Toptan"),
        ("semt-pazari", "Semt pazarı"),
        ("organik", "Organik / yerel"),
        ("kozmetik", "Kozmetik market"),
    ),
    "sport": (
        ("fitness", "Fitness"),
        ("pilates", "Pilates"),
        ("yoga", "Yoga"),
        ("yuzme", "Yüzme"),
        ("tenis", "Tenis"),
        ("hali-saha", "Halı saha"),
        ("dovus", "Dövüş sporları"),
    ),
    "camp": (
        ("uludag", "Uludağ"),
        ("deniz", "Deniz kenarı"),
        ("gol", "Göl / gölet"),
        ("yayla", "Yayla"),
        ("kanyon", "Kanyon"),
        ("selale", "Şelale"),
        ("karavan", "Karavan"),
        ("orman", "Orman"),
    ),
    "visit": (
        ("cami", "Cami"),
        ("kilise", "Kilise"),
        ("kulliye", "Külliye"),
        ("turbe", "Türbe"),
        ("han", "Han / çarşı"),
        ("hisar", "Hisar / kale"),
        ("antik", "Antik / sur"),
        ("anit", "Anıt"),
        ("muze", "Müze"),
        ("park", "Park"),
        ("doga", "Doğa"),
        ("selale", "Şelale"),
        ("dag", "Dağ"),
        ("gol", "Göl"),
        ("koy", "Köy / kasaba"),
        ("kaplica", "Kaplıca"),
        ("magara", "Mağara"),
        ("manzara", "Manzara"),
        ("hat", "Teleferik"),
    ),
    "school": (
        ("anaokul", "Anaokulu"),
        ("ilkokul", "İlkokul"),
        ("ortaokul", "Ortaokul"),
        ("lise", "Lise"),
        ("kolej", "Kolej"),
        ("universite", "Üniversite"),
        ("dershane", "Dershane"),
        ("ozel-egitim", "Özel eğitim"),
    ),
}

CAFE_FEATURE_TAGS = (
    ("kahve", "Kahve"),
    ("tatli", "Tatlı"),
    ("kahvalti", "Kahvaltı"),
    ("manzarali", "Manzaralı"),
    ("calisma", "Çalışmaya uygun"),
    ("laptop-friendly", "Laptop-friendly"),
    ("sessiz", "Sessiz"),
    ("7-24", "7/24 açık"),
    ("nargile", "Nargile"),
    ("kitap-cafe", "Kitap cafe"),
)

SUBCAT_LABEL = {}
for _cat, _pairs in MEKAN_TAXONOMY.items():
    for _k, _lab in _pairs:
        SUBCAT_LABEL[_k] = _lab

DOCTOR_SPECS = (
    "Kadın doğum", "Çocuk", "Kalp", "Onkoloji", "Göz", "Diş",
    "Ortopedi", "KBB", "Cildiye", "Genel cerrahi", "Üroloji",
    "Beyin cerrahisi", "Nöroloji", "Dahiliye", "Göğüs",
    "Gastroenteroloji", "Psikiyatri", "Hematoloji", "Endokrin",
    "FTR", "Plastik", "Enfeksiyon", "Nakil", "Genetik",
)
CONCERT_KINDS = ("Yaklaşan", "Salon", "Açıkhava", "Stadyum", "Live")
THEATER_KINDS = ("Yaklaşan", "Salon")
CINEMA_KINDS = ("Vizyonda", "Salon")
EVENT_KINDS = ("Festival", "Fuar", "Sahne", "Kent")
FUN_KINDS = ("Canlı müzik", "Bar", "Bowling", "Escape", "AVM")
ORG_KINDS = ("Belediye", "Dernek", "Ajans", "Fuar")
GROUP_ILCE = frozenset(("food", "visit", "hotel", "camp", "vet", "hospital", "dentist", "shop", "market", "sport", "family", "school"))
GROUP_BAND = frozenset(("doctor", "concert", "theater", "cinema", "event", "fun", "org"))
KIND_BY_CAT = {
    "concert": CONCERT_KINDS,
    "theater": THEATER_KINDS,
    "cinema": CINEMA_KINDS,
    "event": EVENT_KINDS,
    "fun": FUN_KINDS,
    "org": ORG_KINDS,
}

ILCELER = (
    "Osmangazi",
    "Nilüfer",
    "Yıldırım",
    "Mudanya",
    "Gemlik",
    "İnegöl",
    "Mustafakemalpaşa",
    "İznik",
    "Kestel",
    "Gürsu",
    "Orhangazi",
    "Karacabey",
    "Yenişehir",
    "Orhaneli",
    "Büyükorhan",
    "Harmancık",
    "Keles",
)

_TR = str.maketrans("çğıöşüÇĞİÖŞÜâîûÂÎÛ", "cgiosuCGIOSUaiuAIU")

# food price_band / tag → subcategory
_FOOD_SUB_MAP = {
    "kebap": "kebap",
    "iskender": "iskender",
    "doner": "doner",
    "döner": "doner",
    "kofte": "inegol-kofte",
    "köfte": "inegol-kofte",
    "inegol": "inegol-kofte",
    "pide": "pide",
    "balik": "balik",
    "balık": "balik",
    "burger": "burger",
    "pizza": "pizza",
    "fast": "fast-food",
    "kahvalti": "kahvalti",
    "kahvaltı": "kahvalti",
    "tatli": "tatli",
    "tatlı": "tatli",
    "pastane": "pastane",
    "cafe": "cafe",
    "kafe": "cafe",
    "kahve": "cafe",
    "meyhane": "meyhane",
    "raki": "meyhane",
    "rakı": "meyhane",
    "cantik": "cantik",
    "cantık": "cantik",
    "bar": "bar",
    "pub": "bar",
    "vegan": "vegan",
    "vejetaryen": "vejetaryen",
    "restoran": "restoran",
}


def infer_food_subcategory(price_band: str = "", tags=None) -> str:
    tags = tags or []
    blob = " ".join([price_band or ""] + [str(t) for t in tags]).lower().translate(_TR)
    for needle, sub in _FOOD_SUB_MAP.items():
        if needle.translate(_TR) in blob:
            return sub
    return "restoran"


def subcategories_for(category: str) -> list[tuple[str, str]]:
    return list(MEKAN_TAXONOMY.get(category) or ())


def subcategory_label(key: str) -> str:
    k = (key or "").strip()
    if k == "kafe":
        k = "cafe"
    return SUBCAT_LABEL.get(k) or k


# Yeme-içme kenar filtresi (TripAdvisor benzeri gruplar)
FOOD_KIND = (
    ("restoran", "Restoranlar", frozenset({
        "restoran", "iskender", "kebap", "doner", "inegol-kofte", "pide",
        "cantik", "balik", "burger", "pizza", "fast-food", "vegan", "vejetaryen",
    })),
    ("cafe", "Kahve ve çay", frozenset({"cafe"})),
    ("kahvalti", "Kahvaltı", frozenset({"kahvalti"})),
    ("tatli", "Tatlı", frozenset({"tatli"})),
    ("pastane", "Unlu mamuller", frozenset({"pastane"})),
    ("meyhane", "Meyhane", frozenset({"meyhane"})),
    ("bar", "Bar", frozenset({"bar"})),
)
FOOD_KIND_SUBS = {k: subs for k, _lab, subs in FOOD_KIND}
FOOD_MEAL = (("kahvalti", "Kahvaltı"), ("ogle", "Öğle yemeği"), ("aksam", "Akşam yemeği"))
FOOD_CUISINE = (("turk", "Türk"), ("pizza", "Pizza"), ("fast-food", "Fast food"), ("italyan", "İtalyan"))
FOOD_DISH = (
    ("burger", "Burger"),
    ("kebap", "Karışık kebap"),
    ("balik", "Balık"),
    ("iskender", "İskender"),
    ("inegol-kofte", "Köfte"),
    ("cantik", "Cantık"),
    ("pizza", "Pizza"),
    ("doner", "Döner"),
)
FOOD_PRICE = (("ucuz", "Ucuz"), ("orta", "Ortalama"), ("kaliteli", "Kaliteli yemek"))

# Yeme-içme küratör kartları (görselli hızlı filtre)
FOOD_CURATED = (
    {
        "key": "iskender",
        "tag": "Bursa klasiği",
        "title": "Asıl İskender nerede?",
        "img": "/static/food/ne-yenir-iskender.jpg",
        "tone": "gold",
        "filter": {"dish": "iskender"},
    },
    {
        "key": "burger",
        "tag": "Fast food",
        "title": "Şehrin en iyi hamburgeri",
        "img": "/static/food/doner-2.jpg",
        "tone": "sun",
        "filter": {"dish": "burger"},
    },
    {
        "key": "kahvalti",
        "tag": "Sabah sofrası",
        "title": "Serpme kahvaltı rotası",
        "img": "/static/food/kahvalti-uludag-yolu.jpg",
        "tone": "mint",
        "filter": {"kind": "kahvalti"},
    },
    {
        "key": "cantik",
        "tag": "Kayhan",
        "title": "Cantık & pideli lezzet",
        "img": "/static/food/cantikci-yildirim.jpg",
        "tone": "rose",
        "filter": {"dish": "cantik"},
    },
    {
        "key": "balik",
        "tag": "Sahil",
        "title": "Balık & rakı sofrası",
        "img": "/static/food/balikci-raki-mudanya.jpg",
        "tone": "sea",
        "filter": {"dish": "balik"},
    },
    {
        "key": "kofte",
        "tag": "1965'ten beri",
        "title": "İnegöl köfte durakları",
        "img": "/static/food/ne-yenir-inegol-kofte.jpg",
        "tone": "ember",
        "filter": {"dish": "inegol-kofte"},
    },
    {
        "key": "cafe",
        "tag": "3. nesil",
        "title": "Specialty kahve",
        "img": "/static/food/gloria-jeans-nilufer.jpg",
        "tone": "violet",
        "filter": {"kind": "cafe"},
    },
    {
        "key": "meyhane",
        "tag": "Meze",
        "title": "Meyhane gecesi",
        "img": "/static/food/meyhane-cekirge.jpg",
        "tone": "wine",
        "filter": {"kind": "meyhane"},
    },
)

# Gezilecek kenar filtresi (TripAdvisor tür grupları)
VISIT_KIND = (
    ("anit", "Anıtlar ve turistik yerler", frozenset({
        "anit", "hisar", "antik", "hat",
    })),
    ("dini", "Dini yerler", frozenset({"cami", "kilise", "kulliye", "turbe"})),
    ("muze", "Müzeler", frozenset({"muze"})),
    ("doga", "Doğa ve parklar", frozenset({
        "doga", "park", "selale", "dag", "gol", "magara",
    })),
    ("koy", "Köyler ve kasabalar", frozenset({"koy"})),
    ("carsi", "Çarşı ve hanlar", frozenset({"han"})),
    ("kaplica", "Kaplıca ve spa", frozenset({"kaplica"})),
    ("manzara", "Manzara noktaları", frozenset({"manzara"})),
)
VISIT_KIND_SUBS = {k: subs for k, _lab, subs in VISIT_KIND}
VISIT_FEE = (("ucretsiz", "Ücretsiz"), ("ucretli", "Ücretli"))
VISIT_TAG = (("unesco", "UNESCO"), ("instagram", "Fotoğraf noktası"))
_VISIT_PAID_SUBS = frozenset({"muze", "hat", "kaplica", "magara"})
_VISIT_PAID_BANDS = frozenset({"müze", "muze", "hat", "kaplıca", "kaplica", "magara", "park"})


def visit_fee_tier(p: dict) -> str:
    sub = (p.get("subcategory") or "").strip()
    band = (p.get("price_band") or "").lower()
    if sub in _VISIT_PAID_SUBS or band in _VISIT_PAID_BANDS:
        return "ucretli"
    return "ucretsiz"


def visit_matches(
    p: dict,
    *,
    kinds: list[str] | None = None,
    fees: list[str] | None = None,
    tags: list[str] | None = None,
) -> bool:
    sub = (p.get("subcategory") or "").strip()
    blob = " ".join(
        [str(t).lower() for t in (p.get("tags") or [])]
        + [sub, p.get("price_band") or "", p.get("title") or ""]
    ).lower()
    if kinds:
        ok = False
        for k in kinds:
            if sub in (VISIT_KIND_SUBS.get(k) or frozenset()):
                ok = True
                break
        if not ok:
            return False
    if fees and visit_fee_tier(p) not in fees:
        return False
    if tags:
        if not any(t in blob for t in tags):
            return False
    return True


_TURK_SUBS = frozenset({
    "restoran", "iskender", "kebap", "doner", "inegol-kofte", "pide",
    "cantik", "kahvalti", "meyhane", "balik",
})


def food_price_tier(p: dict) -> str:
    band = (p.get("price_band") or "").lower()
    if "fine" in band:
        return "kaliteli"
    n = int(p.get("est_meal_tl") or 0)
    if n <= 0:
        return "orta"
    if n < 280:
        return "ucuz"
    if n >= 700:
        return "kaliteli"
    return "orta"


def food_price_marks(p: dict) -> str:
    t = food_price_tier(p)
    return {"ucuz": "$", "orta": "$$", "kaliteli": "$$$"}.get(t, "$$")


def food_matches(
    p: dict,
    *,
    kinds: list[str] | None = None,
    meals: list[str] | None = None,
    cuisines: list[str] | None = None,
    dishes: list[str] | None = None,
    prices: list[str] | None = None,
) -> bool:
    sub = (p.get("subcategory") or "").strip()
    tags = [str(t).lower() for t in (p.get("tags") or [])]
    hours = (p.get("hours_text") or "").lower()
    blob = " ".join(tags + [sub, p.get("price_band") or "", p.get("title") or ""]).lower()
    if kinds:
        ok = False
        for k in kinds:
            if sub in (FOOD_KIND_SUBS.get(k) or frozenset()):
                ok = True
                break
        if not ok:
            return False
    if dishes:
        if sub not in dishes and not any(d.replace("-", " ") in blob or d in blob for d in dishes):
            return False
    if cuisines:
        ok = False
        for c in cuisines:
            if c == "turk" and (sub in _TURK_SUBS or "turk" in blob or "anadolu" in blob):
                ok = True
            elif c == "pizza" and (sub == "pizza" or "pizza" in blob):
                ok = True
            elif c == "fast-food" and (sub in ("fast-food", "burger") or "fast" in blob):
                ok = True
            elif c == "italyan" and ("italyan" in blob or sub == "pizza"):
                ok = True
        if not ok:
            return False
    if meals:
        ok = False
        for m in meals:
            if m == "kahvalti" and (sub == "kahvalti" or "kahvalti" in blob):
                ok = True
            elif m == "ogle" and sub not in ("bar",):
                ok = True
            elif m == "aksam" and (
                sub in ("meyhane", "bar", "restoran", "kebap", "balik")
                or "akşam" in hours or "aksam" in hours
            ):
                ok = True
        if not ok:
            return False
    if prices and food_price_tier(p) not in prices:
        return False
    return True


def slugify(text: str) -> str:
    s = (text or "").translate(_TR).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or "yer"


def unique_slug(db, title: str, exclude_id: int | None = None) -> str:
    from models import Place

    base = slugify(title)
    slug, n = base, 2
    while True:
        q = db.query(Place).filter(Place.slug == slug)
        if exclude_id:
            q = q.filter(Place.id != exclude_id)
        if q.first() is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


def tags_load(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    return [p.strip() for p in str(raw).split(",") if p.strip()]


def tags_dump(val) -> str:
    return json.dumps(tags_load(val), ensure_ascii=False)


def display_rating(p) -> float | None:
    """BursaApp puanı varsa onu, yoksa admin/Google puanını göster."""
    avg = getattr(p, "rating_avg", None)
    if avg is not None and float(avg) > 0:
        return float(avg)
    admin = getattr(p, "rating_admin", None)
    if admin is not None and float(admin) > 0:
        return float(admin)
    return None


def _listing_img(url: str | None) -> str:
    """Liste kartları için thumb varsa onu kullan (hız); yoksa orijinal."""
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("/static/cache/thumbs/"):
        return u
    if u.startswith("/static/"):
        try:
            from optimize_images import public_thumb_url

            thumb = public_thumb_url(u)
            if thumb:
                return thumb
        except Exception:
            pass
    return u


def hospital_staff_groups(staff: list[dict]) -> list[dict]:
    """Hastane detay — branş grupları; en çok hekimli branş önce."""
    by: dict[str, list] = {}
    for s in staff:
        by.setdefault(s.get("price_band") or "Diğer", []).append(s)
    return sorted(
        [{"label": ad, "places": plist} for ad, plist in by.items()],
        key=lambda g: (-len(g["places"]), g["label"].casefold()),
    )


def place_public(p) -> dict:
    from seo_urls import place_seo_path

    avg = getattr(p, "rating_avg", None)
    count = int(getattr(p, "rating_count", None) or 0)
    shown = display_rating(p)
    sub = (getattr(p, "subcategory", None) or "").strip()
    path = place_seo_path(p)
    d = {
        "id": p.id,
        "slug": p.slug,
        "path": path,
        "title": p.title,
        "category": p.category,
        "category_label": (CAT_BY_KEY.get(p.category) or {}).get("label") or p.category,
        "subcategory": sub,
        "subcategory_label": subcategory_label(sub) if sub else "",
        "ilce": p.ilce,
        "address": p.address,
        "lat": p.lat,
        "lng": p.lng,
        "phone": p.phone,
        "web": p.web,
        "hours_text": p.hours_text,
        "price_band": p.price_band,
        "blurb": p.blurb,
        "body": p.body,
        "img_url": _listing_img(p.img_url),
        "img": _listing_img(p.img_url),
        "img_full": p.img_url or "",
        "tags": tags_load(p.tags),
        "rating_admin": p.rating_admin,
        "rating_avg": float(avg) if avg is not None else None,
        "rating_count": count,
        "rating": shown,
        "featured": bool(p.featured),
        "starts_at": p.starts_at.isoformat() if p.starts_at else None,
        "when": p.starts_at.strftime("%d.%m %H:%M") if p.starts_at else None,
        "when_long": (
            p.starts_at.strftime("%d %B %Y · %H:%M")
            .replace("January", "Ocak")
            .replace("February", "Şubat")
            .replace("March", "Mart")
            .replace("April", "Nisan")
            .replace("May", "Mayıs")
            .replace("June", "Haziran")
            .replace("July", "Temmuz")
            .replace("August", "Ağustos")
            .replace("September", "Eylül")
            .replace("October", "Ekim")
            .replace("November", "Kasım")
            .replace("December", "Aralık")
            if p.starts_at
            else None
        ),
        "starts_ts": int(p.starts_at.timestamp()) if p.starts_at else None,
        "ends_at": p.ends_at.isoformat() if p.ends_at else None,
        "venue_name": p.venue_name,
        "hospital_slug": p.venue_name if p.category == "doctor" else "",
        "status": p.status,
        "maps": maps_url(p),
        "plan_tier": getattr(p, "plan_tier", None) or "free",
        "claim_status": getattr(p, "claim_status", None) or "",
        "instagram": getattr(p, "instagram", None) or "",
        "whatsapp": getattr(p, "whatsapp", None) or "",
        "ticket_price": getattr(p, "ticket_price", None) or "",
        "ticket_url": getattr(p, "ticket_url", None) or "",
        "boost_active": bool(getattr(p, "boost_until", None) and p.boost_until > datetime.utcnow())
        if getattr(p, "boost_until", None)
        else False,
        "est_meal_tl": int(getattr(p, "est_meal_tl", None) or 0),
        "views": int(getattr(p, "views", None) or 0),
        "fav_count": int(getattr(p, "fav_count", None) or 0),
        "menu_text": getattr(p, "menu_text", None) or "",
        "extra": _place_extra_public(p),
    }
    if d.get("category") == "dentist" and (
        d.get("price_band") == "Devlet" or "mhrs" in (d.get("tags") or [])
    ):
        ex = d.get("extra") or {}
        if not ex.get("mhrs_url"):
            ex = dict(ex)
            ex["mhrs_url"] = "https://mhrs.gov.tr/vatandas/#/Randevu"
            d["extra"] = ex
    return d


def _place_extra_public(p) -> dict:
    from models import place_extra

    ex = place_extra(p)
    menu = ex.get("menu") or []
    gallery = ex.get("gallery") or []
    services = ex.get("services") or []
    fees = ex.get("fees") or []
    staff = ex.get("staff") or []
    rooms = ex.get("rooms") or []
    platforms = ex.get("platforms") or []
    rules = ex.get("rules") or []
    facilities = ex.get("facilities") or []
    return {
        "menu": menu if isinstance(menu, list) else [],
        "gallery": gallery if isinstance(gallery, list) else [],
        "services": services if isinstance(services, list) else [],
        "services_lead": (ex.get("services_lead") or "") if isinstance(ex.get("services_lead") or "", str) else "",
        "fees": fees if isinstance(fees, list) else [],
        "staff": staff if isinstance(staff, list) else [],
        "rooms": rooms if isinstance(rooms, list) else [],
        "platforms": platforms if isinstance(platforms, list) else [],
        "rules": rules if isinstance(rules, list) else [],
        "about": (ex.get("about") or "") if isinstance(ex.get("about"), str) else "",
        "price_min": (ex.get("price_min") or "") if isinstance(ex.get("price_min") or "", str) else "",
        "price_max": (ex.get("price_max") or "") if isinstance(ex.get("price_max") or "", str) else "",
        "source_url": (ex.get("source_url") or "") if isinstance(ex.get("source_url") or "", str) else "",
        "facilities": facilities if isinstance(facilities, list) else [],
        "tips": (ex.get("tips") or "") if isinstance(ex.get("tips") or "", str) else "",
        "vibe": (ex.get("vibe") or "") if isinstance(ex.get("vibe") or "", str) else "",
        "city": (ex.get("city") or "") if isinstance(ex.get("city") or "", str) else "",
        "specialty_detail": (ex.get("specialty_detail") or "") if isinstance(ex.get("specialty_detail"), str) else "",
        "fee_note": (ex.get("fee_note") or "") if isinstance(ex.get("fee_note"), str) else "",
        "menu_url": (ex.get("menu_url") or "") if isinstance(ex.get("menu_url") or "", str) else "",
        "trailer_url": (ex.get("trailer_url") or "") if isinstance(ex.get("trailer_url") or "", str) else "",
        "reservation_note": (ex.get("reservation_note") or "")
        if isinstance(ex.get("reservation_note") or "", str)
        else "",
        "experience_years": str(ex.get("experience_years") or ""),
        "profile_url": (ex.get("profile_url") or "") if isinstance(ex.get("profile_url") or "", str) else "",
        "linkedin_url": (ex.get("linkedin_url") or "") if isinstance(ex.get("linkedin_url") or "", str) else "",
        "catalog_url": (ex.get("catalog_url") or "") if isinstance(ex.get("catalog_url") or "", str) else "",
        "logo_bg": (ex.get("logo_bg") or "") if isinstance(ex.get("logo_bg") or "", str) else "",
        "branch_note": (ex.get("branch_note") or "") if isinstance(ex.get("branch_note") or "", str) else "",
        "mhrs_url": (ex.get("mhrs_url") or "") if isinstance(ex.get("mhrs_url") or "", str) else "",
    }


def place_mine(p) -> dict:
    d = place_public(p)
    d["reject_reason"] = p.reject_reason
    d["created_at"] = p.created_at.isoformat() if p.created_at else None
    return d


def maps_url(p) -> str:
    if p.lat is not None and p.lng is not None:
        return f"https://www.google.com/maps/search/?api=1&query={p.lat},{p.lng}"
    q = " ".join(x for x in (p.title, p.address, p.ilce, "Bursa") if x)
    from urllib.parse import quote_plus
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(q)}"


def parse_dt(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def query_places(
    db,
    *,
    category: str | None = None,
    ilce: str | None = None,
    q: str | None = None,
    from_=None,
    to=None,
    status: str = "approved",
    featured: bool | None = None,
    submitted_by_id: int | None = None,
    order: str | None = None,
    price_band: str | None = None,
    subcategory: str | None = None,
    venue_name: str | None = None,
    categories: tuple | list | None = None,
    limit: int = 24,
    offset: int = 0,
):
    from models import Place

    qry = db.query(Place)
    if status:
        qry = qry.filter(Place.status == status)
    if category and category in CAT_KEYS:
        qry = qry.filter(Place.category == category)
    if categories:
        qry = qry.filter(Place.category.in_(tuple(categories)))
    if ilce:
        qry = qry.filter(Place.ilce == ilce)
    if price_band:
        qry = qry.filter(Place.price_band == price_band)
    if subcategory:
        qry = qry.filter(Place.subcategory == subcategory)
    if venue_name:
        qry = qry.filter(Place.venue_name == venue_name)
    if submitted_by_id:
        qry = qry.filter(Place.submitted_by_id == submitted_by_id)
    if featured is True:
        qry = qry.filter(Place.featured.is_(True))
    if from_:
        dt = parse_dt(from_)
        if dt:
            qry = qry.filter(Place.starts_at.isnot(None), Place.starts_at >= dt)
    if to:
        dt = parse_dt(to)
        if dt:
            qry = qry.filter(or_(Place.ends_at.is_(None), Place.ends_at <= dt), Place.starts_at.isnot(None))
    if q:
        like = f"%{q.strip()}%"
        qry = qry.filter(
            or_(
                Place.title.ilike(like),
                Place.blurb.ilike(like),
                Place.body.ilike(like),
                Place.ilce.ilike(like),
                Place.address.ilike(like),
                Place.venue_name.ilike(like),
                Place.tags.ilike(like),
                Place.subcategory.ilike(like),
            )
        )
    if order == "rating":
        qry = qry.order_by(
            Place.rating_avg.desc().nulls_last(),
            Place.rating_admin.desc().nulls_last(),
            Place.title.asc(),
        )
    elif order == "date":
        qry = qry.order_by(Place.starts_at.asc().nulls_last(), Place.featured.desc(), Place.id.desc())
    elif order == "title":
        qry = qry.order_by(Place.title.asc(), Place.id.asc())
    else:
        qry = qry.order_by(Place.featured.desc(), Place.starts_at.asc().nulls_last(), Place.id.desc())
    total = qry.count()
    rows = qry.offset(max(0, offset)).limit(max(1, min(int(limit or 24), 2500))).all()
    return rows, total
