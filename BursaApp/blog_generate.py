"""Günlük + haftalık blog üretimi — gerçek mekan kayıtlarından."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from catalog import ILCELER, place_public, subcategories_for
from models import Place

from weekend_blog import (
    GENERATED_DIR,
    generate_weekend_blogs,
    load_generated_posts,
    save_generated_post,
)

_DIR = os.path.dirname(os.path.abspath(__file__))
META_PATH = os.path.join(_DIR, "data", "blog_meta.json")
IST = ZoneInfo("Europe/Istanbul")

FOOD_THEMES: list[tuple[str, str, str, str]] = [
    ("kahvalti", "kahvaltı", "Kahvaltı", "/yeme-icme?kind=kahvalti"),
    ("iskender", "iskender", "İskender", "/yeme-icme?dish=iskender"),
    ("cafe", "cafe", "Cafe", "/yeme-icme?kind=cafe"),
    ("balik", "balık", "Balık", "/yeme-icme?kind=balik"),
    ("meyhane", "meyhane", "Meyhane", "/yeme-icme?kind=meyhane"),
]

VISIT_TAGS: list[tuple[str, str, str]] = [
    ("unesco", "UNESCO", "/gezilecek?tag=unesco"),
    ("dogal", "Doğa", "/gezilecek?tag=dogal"),
    ("müze", "Müze", "/gezilecek?q=müze"),
    ("cami", "Cami & türbe", "/gezilecek?q=cami"),
    ("koy", "Köy", "/gezilecek?kind=koy"),
]


def _slugify(text: str) -> str:
    t = (
        (text or "")
        .lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:56] or "blog"


def _rating(p: Place) -> float:
    if p.rating_avg is not None:
        return float(p.rating_avg)
    if p.rating_admin is not None:
        return float(p.rating_admin)
    return 0.0


def _img(p: Place) -> str:
    if p.img_url and str(p.img_url).startswith("/"):
        return str(p.img_url)
    return "/static/visit/hanlar-kapalicarsi.jpg"


def _load_meta() -> dict:
    if not os.path.isfile(META_PATH):
        return {}
    try:
        return json.loads(open(META_PATH, encoding="utf-8").read())
    except Exception:
        return {}


def _save_meta(meta: dict) -> None:
    os.makedirs(os.path.dirname(META_PATH), exist_ok=True)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _already(slug: str) -> bool:
    return os.path.isfile(os.path.join(GENERATED_DIR, f"{slug}.json"))


def _place_line(p: Place) -> str:
    d = place_public(p)
    path = d.get("path") or f"/yer/{p.slug}"
    bits = [f'<a href="{path}">{p.title}</a>']
    if p.ilce:
        bits.append(f"({p.ilce})")
    if d.get("rating") is not None:
        bits.append(f"★ {float(d['rating']):.1f}")
    blurb = (p.blurb or "").strip()
    if blurb:
        bits.append(blurb[:160] + ("…" if len(blurb) > 160 else ""))
    return " — ".join(bits)


def _top_places(db, *, category: str, limit: int = 5, **filters) -> list[Place]:
    q = db.query(Place).filter(Place.status == "approved", Place.category == category)
    if filters.get("ilce"):
        q = q.filter(Place.ilce == filters["ilce"])
    if filters.get("sub"):
        q = q.filter(Place.subcategory == filters["sub"])
    if filters.get("q"):
        t = f"%{filters['q']}%"
        q = q.filter(Place.title.ilike(t) | Place.blurb.ilike(t))
    rows = list(q.all())
    rows.sort(key=_rating, reverse=True)
    return rows[:limit]


def build_food_list_post(db, theme: tuple[str, str, str, str], pub_date: str) -> dict[str, Any] | None:
    key, q, label, cta = theme
    slug = f"liste-{key}-{pub_date.replace('-', '')}"
    if _already(slug):
        return None
    rows = _top_places(db, category="food", limit=5, sub=key if key in dict(subcategories_for("food")) else None)
    if len(rows) < 3:
        rows = _top_places(db, category="food", limit=5, q=q)
    if len(rows) < 3:
        return None
    paras = [_place_line(p) for p in rows]
    paras.append(f'Tüm liste: <a href="{cta}">Bursa {label} mekanları</a>.')
    return {
        "slug": slug,
        "title": f"Bursa {label}: öne çıkan {len(rows)} mekan",
        "h1": f"Bursa {label} listesi — güncel seçim",
        "desc": f"Puan ve kayıt kalitesine göre {label} önerileri. Rezervasyon BursaApp’ten yapılmaz.",
        "date": pub_date,
        "image": _img(rows[0]),
        "cta_path": cta,
        "cta_label": f"{label} listesi",
        "kind": "yeme",
        "generated": True,
        "sections": [
            {"h2": f"Öne çıkan {label} mekanları", "paras": paras},
            {
                "h2": "Nasıl kullanılır?",
                "paras": [
                    "Detay sayfasında adres, saat ve harita linki var.",
                    '<a href="/rota">Rota planlayıcı</a> ile aynı güne ekleyebilirsin.',
                ],
            },
        ],
        "related": [
            ("bursa-da-kahvalti-nerede", "Kahvaltı rehberi"),
            ("bursa-iskender-nerede-yenir", "İskender rehberi"),
        ],
    }


def build_ilce_post(db, ilce: str, pub_date: str) -> dict[str, Any] | None:
    slug = f"ilce-{_slugify(ilce)}-{pub_date.replace('-', '')}"
    if _already(slug):
        return None
    visits = _top_places(db, category="visit", ilce=ilce, limit=4)
    foods = _top_places(db, category="food", ilce=ilce, limit=3)
    if len(visits) + len(foods) < 4:
        return None
    hero = _img(visits[0] if visits else foods[0])
    sections: list[dict] = []
    if visits:
        sections.append(
            {
                "h2": f"{ilce} — gezilecek",
                "image": hero,
                "paras": [_place_line(p) for p in visits]
                + [f'<a href="/gezilecek?ilce={ilce}">Tüm {ilce} gezilecek</a>'],
            }
        )
    if foods:
        sections.append(
            {
                "h2": f"{ilce} — yeme-içme",
                "paras": [_place_line(p) for p in foods]
                + [f'<a href="/yeme-icme?ilce={ilce}">Tüm {ilce} restoranlar</a>'],
            }
        )
    return {
        "slug": slug,
        "title": f"{ilce} gezi rehberi — kısa liste",
        "h1": f"{ilce}: gezilecek ve yeme-içme",
        "desc": f"{ilce} ilçesinde öne çıkan duraklar — BursaApp onaylı kayıtlardan.",
        "date": pub_date,
        "image": hero,
        "cta_path": f"/gezilecek?ilce={ilce}",
        "cta_label": f"{ilce} gezilecek",
        "kind": "gezi",
        "generated": True,
        "sections": sections,
        "related": [("bursa-1-gunluk-gezi-plani", "1 günde Bursa")],
    }


def build_spotlight_post(db, pub_date: str, offset: int = 0) -> dict[str, Any] | None:
    rows = db.query(Place).filter(Place.status == "approved", Place.category == "visit").all()
    rows = [p for p in rows if p.featured or _rating(p) >= 4.0]
    rows.sort(key=_rating, reverse=True)
    if not rows:
        rows = _top_places(db, category="visit", limit=20)
    if not rows:
        return None
    idx = (datetime.now(IST).timetuple().tm_yday + offset) % len(rows)
    p = rows[idx]
    slug = f"one-cikan-{_slugify(p.slug)}-{pub_date.replace('-', '')}"
    if _already(slug):
        return None
    d = place_public(p)
    path = d.get("path") or f"/yer/{p.slug}"
    return {
        "slug": slug,
        "title": f"Öne çıkan: {p.title}",
        "h1": f"Gezilecek: {p.title}",
        "desc": (p.blurb or f"{p.title} — BursaApp gezilecek kaydı.")[:200],
        "date": pub_date,
        "image": _img(p),
        "cta_path": path,
        "cta_label": "Detay sayfası",
        "kind": "gezi",
        "generated": True,
        "sections": [
            {
                "h2": "Neden listede?",
                "paras": [
                    _place_line(p),
                    f'Adres ve harita: <a href="{path}">{p.title} detay</a>.',
                ],
            },
            {
                "h2": "Rotaya ekle",
                "paras": [
                    "Yer detayından rotaya ekleyebilir veya "
                    '<a href="/rota">/rota</a> planlayıcı ile birleştirebilirsin.',
                ],
            },
        ],
        "related": [("bursa-1-gunluk-gezi-plani", "1 günlük rota")],
    }


def build_events_post(db, pub_date: str) -> dict[str, Any] | None:
    slug = f"etkinlik-haftasi-{pub_date.replace('-', '')}"
    if _already(slug):
        return None
    now = datetime.now(IST)
    end = now + timedelta(days=10)
    cats = ("event", "concert", "theater", "cinema", "fun")
    rows = (
        db.query(Place)
        .filter(
            Place.status == "approved",
            Place.category.in_(cats),
            Place.starts_at.isnot(None),
            Place.starts_at >= now.replace(tzinfo=None),
            Place.starts_at < end.replace(tzinfo=None),
        )
        .order_by(Place.starts_at.asc())
        .limit(8)
        .all()
    )
    if len(rows) < 2:
        return None
    paras = []
    for p in rows:
        d = place_public(p)
        path = d.get("path") or f"/yer/{p.slug}"
        when = ""
        if p.starts_at:
            when = p.starts_at.strftime("%d.%m %H:%M") + " · "
        paras.append(f"{when}<a href=\"{path}\">{p.title}</a> ({p.ilce or 'Bursa'})")
    return {
        "slug": slug,
        "title": "Bu hafta Bursa etkinlikleri",
        "h1": "Önümüzdeki günler: konser, tiyatro, etkinlik",
        "desc": "Onaylı etkinlik kayıtları — bilet satışı BursaApp’ten yapılmaz.",
        "date": pub_date,
        "image": _img(rows[0]),
        "cta_path": "/etkinlikler",
        "cta_label": "Tüm etkinlikler",
        "kind": "plan",
        "generated": True,
        "sections": [
            {"h2": "Takvim", "paras": paras + ['<a href="/etkinlikler">Etkinlik listesi</a>']},
        ],
        "related": [("bursa-hafta-sonu-2-gun", "Hafta sonu planı")],
    }


def build_visit_theme_post(db, tag: tuple[str, str, str], pub_date: str) -> dict[str, Any] | None:
    key, label, cta = tag
    slug = f"gezilecek-{key}-{pub_date.replace('-', '')}"
    if _already(slug):
        return None
    rows = _top_places(db, category="visit", limit=5, q=key if key != "unesco" else "unesco")
    if len(rows) < 3:
        return None
    return {
        "slug": slug,
        "title": f"Bursa {label}: 5 durak",
        "h1": f"{label} rotası — kısa liste",
        "desc": f"{label} odaklı gezilecek duraklar; detaylar BursaApp kayıtlarından.",
        "date": pub_date,
        "image": _img(rows[0]),
        "cta_path": cta,
        "cta_label": f"{label} listesi",
        "kind": "gezi",
        "generated": True,
        "sections": [
            {"h2": "Duraklar", "paras": [_place_line(p) for p in rows] + [f'<a href="{cta}">Filtreli liste</a>']},
        ],
        "related": [("bursa-1-gunluk-gezi-plani", "1 günde Bursa")],
    }


def generate_daily_blog(db, pub_date: str | None = None) -> dict[str, Any] | None:
    """Günde bir otomatik yazı — tür rotasyonu."""
    pub = pub_date or datetime.now(IST).strftime("%Y-%m-%d")
    day = datetime.now(IST).timetuple().tm_yday
    builders = [
        lambda: build_spotlight_post(db, pub),
        lambda: build_food_list_post(db, FOOD_THEMES[day % len(FOOD_THEMES)], pub),
        lambda: build_ilce_post(db, ILCELER[day % len(ILCELER)], pub),
        lambda: build_events_post(db, pub),
        lambda: build_visit_theme_post(db, VISIT_TAGS[day % len(VISIT_TAGS)], pub),
        lambda: build_food_list_post(db, FOOD_THEMES[(day + 2) % len(FOOD_THEMES)], pub),
        lambda: build_ilce_post(db, ILCELER[(day + 5) % len(ILCELER)], pub),
    ]
    start = day % len(builders)
    for i in range(len(builders)):
        post = builders[(start + i) % len(builders)]()
        if post:
            save_generated_post(post)
            return post
    return None


def ensure_weekend_blogs(db, *, count: int = 2) -> list[dict]:
    """Önümüzdeki hafta sonu yazıları yoksa üret."""
    return generate_weekend_blogs(db, count=count)


def run_blog_cron(db, *, weekend: bool = True, daily: bool = True) -> dict[str, Any]:
    """Cron giriş noktası."""
    pub = datetime.now(IST).strftime("%Y-%m-%d")
    out: dict[str, Any] = {"date": pub, "weekend": [], "daily": None}
    if weekend:
        for p in ensure_weekend_blogs(db, count=2):
            out["weekend"].append(p["slug"])
    if daily:
        p = generate_daily_blog(db, pub)
        if p:
            out["daily"] = p["slug"]
    meta = _load_meta()
    meta["last_run"] = datetime.now(IST).isoformat(timespec="seconds")
    meta["total_generated"] = len(load_generated_posts())
    _save_meta(meta)
    return out
