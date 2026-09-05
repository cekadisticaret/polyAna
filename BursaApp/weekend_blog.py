"""Hafta sonu rota blog yazıları — gerçek mekanlarla otomatik üretim."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from catalog import place_public, tags_load
from discover import _next_weekend
from itinerary import _nature_route, build_day_route
from models import Place

_DIR = os.path.dirname(os.path.abspath(__file__))
GENERATED_DIR = os.path.join(_DIR, "data", "blog_generated")
IST = ZoneInfo("Europe/Istanbul")

VISIT_FALLBACK: dict[str, str] = {
    "ulu-cami": "/static/visit/ulu-cami.jpg",
    "koza-han": "/static/visit/koza-han.jpg",
    "cumalikizik": "/static/visit/cumalikizik.jpg",
    "golyazi": "/static/visit/golyazi.jpg",
    "misi": "/static/visit/misi.jpg",
    "mudanya": "/static/visit/mudanya-mutareke-evi.jpg",
    "tirilye": "/static/visit/tirilye.jpg",
    "uludag": "/static/visit/uludag.jpg",
    "teleferik": "/static/visit/teleferik.jpg",
    "tophane": "/static/visit/tophane.jpg",
    "iznik": "/static/visit/iznik-surlar.jpg",
    "muradiye": "/static/visit/muradiye.jpg",
}


def _pick_by_slug(db, *slugs: str) -> Place | None:
    for s in slugs:
        p = db.query(Place).filter(Place.slug == s, Place.status == "approved").first()
        if p:
            return p
    return None


def _rating(p: Place) -> float:
    if p.rating_avg is not None:
        return float(p.rating_avg)
    if p.rating_admin is not None:
        return float(p.rating_admin)
    return 0.0


def _pick_food(db, *, sub: str | None = None, tag: str | None = None, exclude: set[int] | None = None) -> Place | None:
    exclude = exclude or set()
    q = db.query(Place).filter(Place.status == "approved", Place.category == "food")
    rows = [p for p in q.all() if p.id not in exclude]
    if sub:
        rows = [p for p in rows if (p.subcategory or "") == sub] or rows
    if tag:
        t = tag.lower()
        rows = [p for p in rows if t in {x.lower() for x in tags_load(p.tags)}] or rows
    rows.sort(key=_rating, reverse=True)
    return rows[0] if rows else None


def _visit_img(slug: str, img_url: str | None) -> str:
    if img_url and str(img_url).startswith("/static/"):
        return str(img_url)
    for key, path in VISIT_FALLBACK.items():
        if key in (slug or ""):
            return path
    return "/static/visit/hanlar-kapalicarsi.jpg"


def _place_link(slot: dict) -> str:
    return slot.get("path") or f"/yer/{slot.get('slug', '')}"


def _slot_line(slot: dict) -> str:
    t = slot.get("slot_time") or ""
    lab = slot.get("slot_label") or "Durak"
    title = slot.get("title") or "Mekan"
    path = _place_link(slot)
    ilce = slot.get("ilce") or ""
    blurb = (slot.get("blurb") or "").strip()
    cost = int(slot.get("slot_cost_tl") or 0)
    bits = [f"<strong>{t}</strong> — {lab}: <a href=\"{path}\">{title}</a>"]
    if ilce:
        bits.append(f"({ilce})")
    if blurb:
        bits.append(blurb[:200] + ("…" if len(blurb) > 200 else ""))
    if cost:
        bits.append(f"≈ {cost} TL")
    transit = slot.get("transit_from_prev") or ""
    if transit:
        bits.append(f"Ulaşım: {transit}")
    return " ".join(bits)


def _day_section(
    *,
    h2: str,
    slots: list[dict],
    tips: list[str],
    image: str,
) -> dict[str, Any]:
    paras = [_slot_line(s) for s in slots if s.get("title")]
    if tips:
        paras.append(" ".join(tips))
    paras.append(
        'Detay ve alternatifler: <a href="/rota">rota planlayıcı</a> · '
        '<a href="/hafta-sonu">hafta sonu fikirleri</a>.'
    )
    return {"h2": h2, "image": image, "paras": paras}


def _route_slots(route: dict) -> list[dict]:
    return list(route.get("slots") or [])


def _hero_from_slots(slots: list[dict]) -> str:
    for s in slots:
        if s.get("img_url"):
            return _visit_img(s.get("slug") or "", s.get("img_url"))
    return "/static/visit/hanlar-kapalicarsi.jpg"


def _build_sahil_day(db, *, transport: str = "car") -> dict:
    used: set[int] = set()
    mudanya = _pick_by_slug(db, "mudanya-mutareke-evi", "mudanya") or db.query(Place).filter(
        Place.status == "approved", Place.category == "visit"
    ).filter(Place.title.ilike("%mudanya%")).first()
    tirilye = _pick_by_slug(db, "tirilye-zeytinbagi", "tirilye") or db.query(Place).filter(
        Place.status == "approved", Place.category == "visit"
    ).filter(Place.title.ilike("%tirilye%")).first()
    balik = _pick_food(db, sub="balik", exclude=used) or _pick_food(db, tag="balik", exclude=used)
    cafe = _pick_food(db, sub="cafe", exclude=used)
    slots_raw = []
    if mudanya:
        used.add(mudanya.id)
        slots_raw.append(("10:30", "Sahil yürüyüşü", mudanya, 0))
    if balik:
        used.add(balik.id)
        slots_raw.append(("13:00", "Balık öğle", balik, 450))
    if tirilye:
        used.add(tirilye.id)
        slots_raw.append(("16:00", "Köy turu", tirilye, 0))
    if cafe:
        used.add(cafe.id)
        slots_raw.append(("18:30", "Gün batımı molası", cafe, 180))
    from itinerary import _pack_slots

    slots, total = _pack_slots(slots_raw, transport=transport)
    return {
        "title": "Mudanya · Tirilye sahil rotası",
        "slots": slots,
        "est_total_tl": total,
        "transport": transport,
        "tips": [
            "Cumartesi trafik yoğun — sabah erken çık.",
            "Tirilye için Mudanya üzerinden 20 dk sahil yolu.",
        ],
    }


def _build_koy_day(db, *, transport: str = "car") -> dict:
    return build_day_route(
        db,
        budget_tl=0,
        people=2,
        transport=transport,
        family=False,
        romantic=False,
    )


def _build_doga_day(db, *, transport: str = "car") -> dict:
    return _nature_route(db, people=2, budget=0, transport=transport)


def _build_otobus_day(db) -> dict:
    return build_day_route(db, budget_tl=1200, people=2, transport="bus", cheap=True)


def _build_termal_day(db) -> dict:
    used: set[int] = set()
    hotels = db.query(Place).filter(Place.status == "approved", Place.category == "hotel").all()
    termal = [
        p
        for p in hotels
        if (p.subcategory or "") in ("termal", "spa")
        or "termal" in {t.lower() for t in tags_load(p.tags)}
    ]
    termal.sort(key=_rating, reverse=True)
    hotel = termal[0] if termal else _pick_by_slug(db, "celik-palace-otel", "almira")
    kaplica = _pick_by_slug(db, "eski-kaplica", "yeni-kaplica") or _pick_by_slug(db, "muradiye")
    yemek = _pick_food(db, sub="iskender", exclude=used) or _pick_food(db, exclude=used)
    slots = []
    if hotel:
        d = place_public(hotel)
        d.update({"slot_time": "11:00", "slot_label": "Termal / konak", "slot_cost_tl": 0})
        slots.append(d)
    if kaplica:
        d = place_public(kaplica)
        d.update({"slot_time": "14:00", "slot_label": "Kaplıca molası", "slot_cost_tl": 200})
        slots.append(d)
    if yemek:
        d = place_public(yemek)
        d.update({"slot_time": "19:30", "slot_label": "Akşam", "slot_cost_tl": 400})
        slots.append(d)
    return {
        "title": "Çekirge termal günü",
        "slots": slots,
        "tips": ["Rezervasyon otelden; BursaApp oda satmaz."],
    }


ThemeFn = Callable[..., dict]

THEMES: list[dict[str, Any]] = [
    {
        "id": "tarihi-koy",
        "title": "Tarihi merkez + köy",
        "lead": "Cumartesi hanlar ve Ulu Cami; Pazar köy kahvaltısı ve taş sokaklar.",
        "sat": lambda db: build_day_route(db, transport="car"),
        "sun": lambda db: _build_doga_day(db, transport="car"),
    },
    {
        "id": "sahil-mudanya",
        "title": "Mudanya · Tirilye sahil",
        "lead": "Cumartesi sahil ve balık; Pazar Tirilye taş evleri.",
        "sat": lambda db: _build_sahil_day(db),
        "sun": lambda db: _build_sahil_day(db),
    },
    {
        "id": "doga-golyazi",
        "title": "Göl ve köy",
        "lead": "Gölyazı, Misi veya Botanik — sakin tempo.",
        "sat": lambda db: _build_doga_day(db, transport="car"),
        "sun": lambda db: _build_doga_day(db, transport="car"),
    },
    {
        "id": "otobus-ekonomik",
        "title": "Otobüsle ekonomik",
        "lead": "Arabasız; Burulaş ile merkez rotası.",
        "sat": lambda db: _build_otobus_day(db),
        "sun": lambda db: _build_otobus_day(db),
    },
    {
        "id": "termal-cekirge",
        "title": "Termal + Çekirge",
        "lead": "Kaplıca molası ve Çekirge yeme-içme.",
        "sat": lambda db: _build_termal_day(db),
        "sun": lambda db: build_day_route(db, transport="car", romantic=True),
    },
    {
        "id": "aile-uludag",
        "title": "Aile · Uludağ hattı",
        "lead": "Teleferik veya doğa; çocuklu tempo.",
        "sat": lambda db: build_day_route(db, transport="car", family=True),
        "sun": lambda db: _build_doga_day(db, transport="car"),
    },
]


def _slugify(text: str) -> str:
    t = text.lower().replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c")
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:48] or "rota"


def build_weekend_post(db, theme: dict, *, sat: datetime, sun: datetime, pub_date: str) -> dict[str, Any]:
    sat_route = theme["sat"](db)
    sun_route = theme["sun"](db)
    sat_slots = _route_slots(sat_route)
    sun_slots = _route_slots(sun_route)
    sat_label = f"Cumartesi · {sat.day}.{sat.month:02d}"
    sun_label = f"Pazar · {sun.day}.{sun.month:02d}"
    theme_id = theme["id"]
    slug = f"hafta-sonu-{theme_id}-{sat.strftime('%Y%m%d')}"
    h1 = f"Hafta sonu rotası: {theme['title']} ({sat.day}–{sun.day} {sat.strftime('%B')})"
    # Turkish month in title - use numeric for simplicity
    aylar = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
    h1 = f"Hafta sonu rotası: {theme['title']} · {sat.day}–{sun.day} {aylar[sat.month - 1]}"
    sections = [
        _day_section(
            h2=f"1. gün — {sat_label}",
            slots=sat_slots,
            tips=list(sat_route.get("tips") or [])[:2],
            image=_hero_from_slots(sat_slots),
        ),
        _day_section(
            h2=f"2. gün — {sun_label}",
            slots=sun_slots,
            tips=list(sun_route.get("tips") or [])[:2],
            image=_hero_from_slots(sun_slots) if sun_slots else _hero_from_slots(sat_slots),
        ),
        {
            "h2": "Bütçe ve pratik",
            "image": "/static/visit/koza-han.jpg",
            "paras": [
                f"Tahmini harcama (2 kişi): Cumartesi ≈ {sat_route.get('est_total_tl') or '—'} TL · "
                f"Pazar ≈ {sun_route.get('est_total_tl') or '—'} TL — yemek dahil, konaklama hariç.",
                "Bilet ve oda rezervasyonu işletme/otel üzerinden; BursaApp satış yapmaz.",
                '<a href="/hafta-sonu">Hafta sonu planlayıcı</a> ile kişi sayısını değiştir.',
            ],
        },
    ]
    est = (sat_route.get("est_total_tl") or 0) + (sun_route.get("est_total_tl") or 0)
    return {
        "slug": slug,
        "title": h1,
        "h1": h1,
        "desc": f"{theme['lead']} Gerçek mekanlarla 2 günlük alternatif rota — {sat_label} / {sun_label}.",
        "date": pub_date,
        "image": _hero_from_slots(sat_slots),
        "cta_path": "/hafta-sonu",
        "cta_label": "Hafta sonu planla",
        "kind": "plan",
        "generated": True,
        "theme_id": theme_id,
        "weekend_sat": sat.strftime("%Y-%m-%d"),
        "weekend_sun": sun.strftime("%Y-%m-%d"),
        "sections": sections,
        "related": [
            ("bursa-hafta-sonu-2-gun", "Genel 2 gün planı"),
            ("bursa-1-gunluk-gezi-plani", "1 günde Bursa"),
        ],
        "est_total_tl": est,
    }


def load_generated_posts() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not os.path.isdir(GENERATED_DIR):
        return out
    for name in os.listdir(GENERATED_DIR):
        if not name.endswith(".json"):
            continue
        path = os.path.join(GENERATED_DIR, name)
        try:
            row = json.loads(open(path, encoding="utf-8").read())
        except Exception:
            continue
        slug = row.get("slug") or name.replace(".json", "")
        if slug:
            out[slug] = row
    return out


def save_generated_post(post: dict[str, Any]) -> str:
    os.makedirs(GENERATED_DIR, exist_ok=True)
    slug = post["slug"]
    path = os.path.join(GENERATED_DIR, f"{slug}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=2)
    return path


def pick_themes_for_week(*, week_num: int, count: int = 2) -> list[dict]:
    n = len(THEMES)
    start = week_num % n
    picked = [THEMES[(start + i) % n] for i in range(min(count, n))]
    return picked


def generate_weekend_blogs(db, *, count: int = 2, pub_date: str | None = None) -> list[dict]:
    """Önümüzdeki hafta sonu için 1–2 blog yazısı üret."""
    now = datetime.now(IST)
    pub = pub_date or now.strftime("%Y-%m-%d")
    sat, sun = _next_weekend()
    week_num = now.isocalendar()[1]
    n = max(1, min(2, count))
    themes = pick_themes_for_week(week_num=week_num, count=n)
    written: list[dict] = []
    for theme in themes:
        post = build_weekend_post(db, theme, sat=sat, sun=sun, pub_date=pub)
        if os.path.isfile(os.path.join(GENERATED_DIR, f"{post['slug']}.json")):
            continue
        save_generated_post(post)
        written.append(post)
    return written
