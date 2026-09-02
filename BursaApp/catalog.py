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
    {"key": "market", "path": "/marketler", "label": "Marketler", "hint": "Migros, BİM, A101, Şok, semt pazarı"},
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
    {"key": "vet", "path": "/veterinerler", "label": "Veterinerler", "hint": "klinik, hayvan hastanesi"},
)
CAT_BY_KEY = {c["key"]: c for c in CATEGORIES}
CAT_BY_PATH = {c["path"]: c for c in CATEGORIES}
CAT_KEYS = tuple(c["key"] for c in CATEGORIES)

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
        ("bakkal", "Bakkal"),
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
GROUP_ILCE = frozenset(("food", "visit", "hotel", "camp", "vet", "hospital", "shop", "market", "sport", "family"))
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


def place_public(p) -> dict:
    from seo_urls import place_seo_path

    avg = getattr(p, "rating_avg", None)
    count = int(getattr(p, "rating_count", None) or 0)
    shown = display_rating(p)
    sub = (getattr(p, "subcategory", None) or "").strip()
    path = place_seo_path(p)
    return {
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
        "img_url": p.img_url,
        "img": p.img_url,
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
    else:
        qry = qry.order_by(Place.featured.desc(), Place.starts_at.asc().nulls_last(), Place.id.desc())
    total = qry.count()
    rows = qry.offset(max(0, offset)).limit(max(1, min(int(limit or 24), 800))).all()
    return rows, total
