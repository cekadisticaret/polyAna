#!/usr/bin/env python3
"""BursaApp SEO altyapısı — meta, canonical, Open Graph, JSON-LD, sitemap yardımcıları."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from catalog import CAT_BY_KEY, CAT_BY_PATH, CATEGORIES

SITE_NAME = "BursaApp"
DEFAULT_DESC = (
    "Bursa'da bugün ne var? Restoran, konser, tiyatro, gezilecek yerler, "
    "oteller ve etkinlikler — BursaApp şehir rehberi."
)
DEFAULT_IMAGE = "/static/logo-512.png"
LOCALE = "tr_TR"

# private / noindex path prefixes
NOINDEX_PREFIXES = (
    "/admin",
    "/hesap",
    "/giris",
    "/kayit",
    "/isletme",
    "/premium/checkout",
    "/favori/",
    "/api/",
)

# query keys that create duplicate URLs → strip from canonical
CANONICAL_DROP_ARGS = frozenset({"q", "from", "to", "lat", "lng", "r", "mode", "next"})


@dataclass
class PageSEO:
    title: str
    description: str
    path: str = "/"
    image: str | None = None
    og_type: str = "website"
    robots: str = "index,follow"
    breadcrumbs: list[tuple[str, str]] = field(default_factory=list)
    json_ld: list[dict[str, Any]] = field(default_factory=list)
    keywords: str = ""

    @property
    def canonical(self) -> str:
        return abs_url(self.path)

    @property
    def image_abs(self) -> str:
        return abs_url(self.image or DEFAULT_IMAGE)

    @property
    def title_full(self) -> str:
        t = (self.title or SITE_NAME).strip()
        if SITE_NAME.lower() in t.lower():
            return t[:70]
        return f"{t} · {SITE_NAME}"[:70]

    @property
    def description_clean(self) -> str:
        return clip(self.description or DEFAULT_DESC, 160)

    def to_json_ld_scripts(self) -> list[str]:
        blocks = [organization_ld(), website_ld()]
        if self.breadcrumbs:
            blocks.append(breadcrumb_ld(self.breadcrumbs))
        blocks.extend(self.json_ld or [])
        out = []
        for b in blocks:
            if not b:
                continue
            out.append(json.dumps(b, ensure_ascii=False, separators=(",", ":")))
        return out


def site_base() -> str:
    return (os.environ.get("BURSAAPP_PUBLIC_URL") or "https://bursaapp.com").rstrip("/")


def abs_url(path_or_url: str | None) -> str:
    if not path_or_url:
        return site_base() + "/"
    s = str(path_or_url).strip()
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if not s.startswith("/"):
        s = "/" + s
    return site_base() + s


def clip(text: str | None, n: int = 160) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    if len(s) <= n:
        return s
    cut = s[: n - 1].rsplit(" ", 1)[0]
    return (cut or s[: n - 1]).rstrip(".,;:") + "…"


def page(
    *,
    title: str,
    description: str | None = None,
    path: str | None = None,
    image: str | None = None,
    og_type: str = "website",
    robots: str | None = None,
    breadcrumbs: list[tuple[str, str]] | None = None,
    json_ld: list[dict[str, Any]] | None = None,
    keywords: str = "",
    noindex: bool = False,
) -> PageSEO:
    from flask import request

    p = path if path is not None else (request.path if request else "/")
    rob = robots or ("noindex,nofollow" if noindex else "index,follow")
    return PageSEO(
        title=title,
        description=description or DEFAULT_DESC,
        path=p,
        image=image,
        og_type=og_type,
        robots=rob,
        breadcrumbs=breadcrumbs or [("Keşfet", "/")],
        json_ld=json_ld or [],
        keywords=keywords,
    )


def organization_ld() -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": SITE_NAME,
        "url": site_base() + "/",
        "logo": abs_url("/static/logo-512.png"),
        "sameAs": [],
        "description": DEFAULT_DESC,
        "areaServed": {"@type": "City", "name": "Bursa", "addressCountry": "TR"},
    }


def website_ld() -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": site_base() + "/",
        "inLanguage": "tr-TR",
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": site_base() + "/yeme-icme?q={search_term_string}",
            },
            "query-input": "required name=search_term_string",
        },
    }


def breadcrumb_ld(crumbs: list[tuple[str, str]]) -> dict[str, Any]:
    items = []
    for i, (name, path) in enumerate(crumbs, 1):
        items.append(
            {
                "@type": "ListItem",
                "position": i,
                "name": name,
                "item": abs_url(path),
            }
        )
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": items,
    }


def _postal_address(place: dict[str, Any]) -> dict[str, Any] | None:
    if not (place.get("address") or place.get("ilce")):
        return None
    return {
        "@type": "PostalAddress",
        "streetAddress": place.get("address") or "",
        "addressLocality": place.get("ilce") or "Bursa",
        "addressRegion": "Bursa",
        "addressCountry": "TR",
    }


def _geo(place: dict[str, Any]) -> dict[str, Any] | None:
    if place.get("lat") is None or place.get("lng") is None:
        return None
    return {
        "@type": "GeoCoordinates",
        "latitude": place["lat"],
        "longitude": place["lng"],
    }


def place_json_ld(place: dict[str, Any]) -> dict[str, Any]:
    """LocalBusiness / TouristAttraction / Event — kategoriye göre."""
    cat = place.get("category") or ""
    url = abs_url(f"/yer/{place.get('slug')}")
    img = place.get("img_url") or place.get("img")
    base: dict[str, Any] = {
        "@context": "https://schema.org",
        "name": place.get("title") or "",
        "description": clip(place.get("blurb") or place.get("body") or "", 300),
        "url": url,
        "image": abs_url(img) if img else abs_url(DEFAULT_IMAGE),
    }
    addr = _postal_address(place)
    if addr:
        base["address"] = addr
    geo = _geo(place)
    if geo:
        base["geo"] = geo
    if place.get("phone"):
        base["telephone"] = place["phone"]
    if place.get("web"):
        base["sameAs"] = [place["web"]]
    if place.get("rating") and place.get("rating_count"):
        base["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": round(float(place["rating"]), 1),
            "reviewCount": int(place["rating_count"]),
            "bestRating": 5,
            "worstRating": 1,
        }

    if cat in ("concert", "theater", "cinema", "event") and place.get("starts_at"):
        base["@type"] = "Event"
        base["startDate"] = place["starts_at"]
        if place.get("ends_at"):
            base["endDate"] = place["ends_at"]
        base["eventAttendanceMode"] = "https://schema.org/OfflineEventAttendanceMode"
        base["eventStatus"] = "https://schema.org/EventScheduled"
        loc: dict[str, Any] = {
            "@type": "Place",
            "name": place.get("venue_name") or place.get("title") or "Bursa",
        }
        if addr:
            loc["address"] = addr
        if geo:
            loc["geo"] = geo
        base["location"] = loc
        if place.get("ticket_url") or place.get("web"):
            base["offers"] = {
                "@type": "Offer",
                "url": place.get("ticket_url") or place.get("web") or url,
                "priceCurrency": "TRY",
                "availability": "https://schema.org/InStock",
            }
            if place.get("ticket_price"):
                base["offers"]["price"] = re.sub(r"[^\d.]", "", place["ticket_price"]) or "0"
        return base

    type_map = {
        "food": "Restaurant",
        "hotel": "Hotel",
        "camp": "Campground",
        "visit": "TouristAttraction",
        "hospital": "Hospital",
        "doctor": "Physician",
        "vet": "VeterinaryCare",
        "shop": "Store",
        "sport": "SportsActivityLocation",
        "fun": "EntertainmentBusiness",
        "cinema": "MovieTheater",
        "concert": "MusicVenue",
        "theater": "PerformingArtsTheater",
    }
    base["@type"] = type_map.get(cat, "LocalBusiness")
    if place.get("hours_text"):
        base["openingHours"] = place["hours_text"]
    if cat == "food" and place.get("est_meal_tl"):
        base["priceRange"] = f"≈{place['est_meal_tl']} TL"
    elif place.get("price_band"):
        base["priceRange"] = place["price_band"]
    return base


def item_list_ld(name: str, path: str, places: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    elements = []
    for i, p in enumerate(places[:limit], 1):
        elements.append(
            {
                "@type": "ListItem",
                "position": i,
                "url": abs_url(f"/yer/{p.get('slug')}"),
                "name": p.get("title") or "",
            }
        )
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": name,
        "url": abs_url(path),
        "numberOfItems": len(places),
        "itemListElement": elements,
    }


def article_ld(*, title: str, description: str, path: str, image: str | None = None) -> dict[str, Any]:
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": clip(description, 200),
        "url": abs_url(path),
        "image": abs_url(image or DEFAULT_IMAGE),
        "inLanguage": "tr-TR",
        "author": {"@type": "Organization", "name": SITE_NAME},
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "logo": {"@type": "ImageObject", "url": abs_url("/static/logo-512.png")},
        },
    }


def for_home() -> PageSEO:
    return page(
        title="Bursa'da Ne Yapalım?",
        description=DEFAULT_DESC,
        path="/",
        breadcrumbs=[("Keşfet", "/")],
        keywords="bursa, bursa rehber, bursa konser, bursa restoran, bursa etkinlik",
        json_ld=[
            {
                "@context": "https://schema.org",
                "@type": "WebPage",
                "name": "Bursa'da Ne Yapalım?",
                "description": DEFAULT_DESC,
                "url": abs_url("/"),
                "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": site_base() + "/"},
            }
        ],
    )


def for_category(cat: dict[str, Any], *, ilce: str = "", sub: str = "", total: int = 0, places: list | None = None) -> PageSEO:
    label = cat.get("label") or cat.get("key") or "Liste"
    hint = cat.get("hint") or ""
    path = cat.get("path") or "/"
    parts = [f"Bursa {label}"]
    if sub:
        parts.append(sub)
    if ilce:
        parts.append(ilce)
    title = " · ".join(parts)
    desc = f"Bursa {label.lower()} rehberi"
    if ilce:
        desc += f" — {ilce}"
    if sub:
        desc += f" · {sub}"
    if hint:
        desc += f". {hint.capitalize()}."
    if total:
        desc += f" {total} kayıt."
    crumbs = [("Keşfet", "/"), (label, path)]
    if ilce:
        crumbs.append((ilce, f"{path}?ilce={ilce}"))
    # canonical: strip filter noise → category root (SEO best practice for facet pages)
    canon = path
    if ilce and not sub:
        # keep ilce as useful landing
        from urllib.parse import quote

        canon = f"{path}?ilce={quote(ilce)}"
    ld = []
    if places:
        ld.append(item_list_ld(title, path, places))
    return page(
        title=title,
        description=desc,
        path=canon,
        breadcrumbs=crumbs,
        keywords=f"bursa {label.lower()}, {hint}",
        json_ld=ld,
    )


def for_place(place: dict[str, Any]) -> PageSEO:
    cat = CAT_BY_KEY.get(place.get("category") or "") or {}
    cat_label = cat.get("label") or place.get("category_label") or "Yer"
    cat_path = cat.get("path") or "/"
    title_bits = [place.get("title") or "Yer"]
    if place.get("ilce"):
        title_bits.append(place["ilce"])
    title = " · ".join(title_bits)
    desc = place.get("blurb") or place.get("body") or f"{place.get('title')} — Bursa {cat_label}"
    if place.get("address"):
        desc = clip(f"{desc} Adres: {place['address']}", 160)
    place_path = place.get("path") or f"/yer/{place.get('slug')}"
    crumbs = [("Keşfet", "/"), (cat_label, cat_path), (place.get("title") or "Detay", place_path)]
    return page(
        title=title,
        description=desc,
        path=place_path,
        image=place.get("img_url") or place.get("img"),
        og_type="article" if place.get("starts_at") else "website",
        breadcrumbs=crumbs,
        keywords=", ".join(
            x
            for x in (
                place.get("title"),
                place.get("ilce"),
                cat_label,
                place.get("subcategory_label"),
                "Bursa",
            )
            if x
        ),
        json_ld=[place_json_ld(place)],
    )


def for_seo_landing(meta: dict[str, Any], path: str, places: list | None = None) -> PageSEO:
    title = meta.get("title") or "Bursa"
    desc = meta.get("desc") or meta.get("h1") or DEFAULT_DESC
    ld = [article_ld(title=title, description=desc, path=path)]
    if places:
        ld.append(item_list_ld(title, path, places))
    return page(
        title=title,
        description=desc,
        path=path,
        breadcrumbs=[("Keşfet", "/"), (title, path)],
        keywords=f"{title}, bursa rehber",
        json_ld=ld,
    )


def for_food(food: dict[str, Any]) -> PageSEO:
    path = f"/{food['slug']}"
    title = food.get("seo_title") or f"{food.get('title')} | BursaApp"
    # seo_title already may include | BursaApp — PageSEO.title_full handles dup
    if " · " in title or "|" in title:
        # use as full-ish title without double brand in title_full
        t = title.replace(" | BursaApp", "").replace(" · BursaApp", "").strip()
    else:
        t = food.get("title") or title
    desc = food.get("seo_desc") or food.get("history") or DEFAULT_DESC
    return page(
        title=t,
        description=desc,
        path=path,
        breadcrumbs=[
            ("Keşfet", "/"),
            ("Ne yenir?", "/bursa-da-ne-yenir"),
            (food.get("title") or t, path),
        ],
        keywords=f"bursa {food.get('title', '')}, nerede yenir",
        json_ld=[
            article_ld(title=t, description=desc, path=path),
            {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": f"Bursa'da {food.get('title')} nerede yenir?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": clip(food.get("where") or desc, 300),
                        },
                    },
                    {
                        "@type": "Question",
                        "name": f"{food.get('title')} nedir?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": clip(food.get("history") or desc, 300),
                        },
                    },
                ],
            },
        ],
    )


def for_district(ilce: str, slug: str) -> PageSEO:
    path = f"/ilce/{slug}"
    title = f"{ilce} Rehberi"
    desc = (
        f"{ilce} ilçesinde restoran, cafe, etkinlik, gezilecek yerler ve daha fazlası. "
        f"BursaApp {ilce} mini portal."
    )
    return page(
        title=title,
        description=desc,
        path=path,
        breadcrumbs=[("Keşfet", "/"), ("İlçeler", "/ilce"), (ilce, path)],
        keywords=f"{ilce}, bursa {ilce.lower()}, {ilce} restoran",
    )


DISCOVER_META = {
    "/bugun": (
        "Bugün Bursa'da Ne Var?",
        "Bugünün konser, tiyatro, etkinlik ve önerilen mekanları — BursaApp günlük keşif.",
    ),
    "/bu-aksam": (
        "Bu Akşam Bursa",
        "Bu akşam Bursa'da konser, sahne, yeme-içme ve gece planı önerileri.",
    ),
    "/yakinimda": (
        "Yakınımdaki Yerler · Bursa",
        "Konumuna yakın restoran, cafe ve gezilecek yerler.",
    ),
    "/hafta-sonu": (
        "Hafta Sonu Bursa Planı",
        "Cumartesi–Pazar için Bursa rota, etkinlik ve mekan önerileri.",
    ),
    "/rota": (
        "Bursa Rota Oluşturucu",
        "Bütçene göre 1 günlük Bursa rotası — mekan, yemek ve gezilecek yerler.",
    ),
    "/ai": (
        "Bursa AI Asistan",
        "Ne yapmak istediğini yaz, BursaApp gerçek mekanlarla plan önersin.",
    ),
    "/harita": (
        "Bursa Haritası",
        "Restoran, cafe, etkinlik ve gezilecek yerler haritada — BursaApp.",
    ),
    "/ilce": (
        "Bursa İlçeleri",
        "17 Bursa ilçesi mini portal — restoran, cafe, etkinlik.",
    ),
    "/bursa-da-ne-yenir": (
        "Bursa'da Ne Yenir?",
        "İskender, İnegöl köfte, Kemalpaşa ve Bursa'nın meşhur lezzetleri.",
    ),
    "/kampanyalar": (
        "Bursa Kampanyaları",
        "İşletme kampanyaları ve fırsatlar — BursaApp.",
    ),
    "/oneriyor": (
        "BursaApp Öneriyor",
        "Editoryal seçkiler: restoran, gezi ve etkinlik listeleri.",
    ),
    "/kuponlar": (
        "BursaApp Kuponları",
        "Sadakat puanı ve indirim kuponları.",
    ),
    "/premium": (
        "İşletme Paketleri · BursaApp",
        "Free, PRO ve Premium işletme paketleri.",
    ),
}


def resolve_seo(req=None) -> PageSEO:
    """Context processor varsayılanı — rota özel seo geçmezse kullanılır."""
    from flask import request as flask_request

    req = req or flask_request
    path = req.path or "/"
    for pref in NOINDEX_PREFIXES:
        if path == pref or path.startswith(pref.rstrip("/") + "/") or path.startswith(pref):
            return page(
                title="BursaApp",
                description=DEFAULT_DESC,
                path=path,
                noindex=True,
                breadcrumbs=[("Keşfet", "/")],
            )

    if path in ("/", "/kesfet"):
        return for_home()

    cat = CAT_BY_PATH.get(path)
    if cat:
        return for_category(cat)

    if path in DISCOVER_META:
        title, desc = DISCOVER_META[path]
        return page(
            title=title,
            description=desc,
            path=path,
            breadcrumbs=[("Keşfet", "/"), (title.split("·")[0].strip(), path)],
        )

    # /yer/<slug> without override — thin fallback
    m = re.match(r"^/yer/([^/]+)$", path)
    if m:
        return page(
            title=m.group(1).replace("-", " ").title(),
            description=DEFAULT_DESC,
            path=path,
            breadcrumbs=[("Keşfet", "/"), ("Yer", path)],
        )

    return page(
        title=SITE_NAME,
        description=DEFAULT_DESC,
        path=path,
        breadcrumbs=[("Keşfet", "/")],
    )


def sitemap_static_urls() -> list[dict[str, Any]]:
    """Sitemap için sabit kamuya açık URL'ler."""
    from foods import FAMOUS_FOODS
    from seo_pages import ILCE_SLUGS, SEO_LANDINGS
    from catalog import ILCELER, slugify as _sl

    rows: list[dict[str, Any]] = []

    def add(path: str, freq: str = "weekly", priority: str = "0.7", lastmod: datetime | None = None):
        rows.append(
            {
                "loc": abs_url(path),
                "changefreq": freq,
                "priority": priority,
                "lastmod": lastmod,
            }
        )

    add("/", "daily", "1.0")
    for p, freq, pri in (
        ("/bugun", "hourly", "0.9"),
        ("/bu-aksam", "hourly", "0.9"),
        ("/yakinimda", "daily", "0.8"),
        ("/hafta-sonu", "daily", "0.8"),
        ("/rota", "weekly", "0.7"),
        ("/ai", "weekly", "0.6"),
        ("/harita", "daily", "0.8"),
        ("/ilce", "weekly", "0.8"),
        ("/bursa-da-ne-yenir", "weekly", "0.9"),
        ("/kampanyalar", "daily", "0.6"),
        ("/oneriyor", "weekly", "0.7"),
    ):
        add(p, freq, pri)

    for c in CATEGORIES:
        add(c["path"], "daily", "0.85")

    for slug in SEO_LANDINGS:
        add(f"/{slug}", "weekly", "0.9")

    for f in FAMOUS_FOODS:
        add(f"/{f['slug']}", "weekly", "0.85")

    for ad in ILCELER:
        s = _sl(ad)
        add(f"/ilce/{s}", "weekly", "0.75")
        add(f"/{s}-restoranlari", "weekly", "0.8")
        add(f"/{s}-cafeler", "weekly", "0.75")

    # bilinen slug varyantları (nilufer vs nilüfer)
    for s in ("nilufer", "osmangazi", "yildirim", "inegol", "iznik"):
        if s in ILCE_SLUGS:
            add(f"/{s}-restoranlari", "weekly", "0.8")
            add(f"/{s}-cafeler", "weekly", "0.75")

    return rows


def xml_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_urlset(entries: list[dict[str, Any]], *, with_images: bool = False) -> str:
    ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
    if with_images:
        ns += ' xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"'
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f"<urlset {ns}>",
    ]
    for e in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(e['loc'])}</loc>")
        lm = e.get("lastmod")
        if isinstance(lm, datetime):
            lines.append(f"    <lastmod>{lm.strftime('%Y-%m-%d')}</lastmod>")
        elif isinstance(lm, str) and lm:
            lines.append(f"    <lastmod>{xml_escape(lm[:10])}</lastmod>")
        if e.get("changefreq"):
            lines.append(f"    <changefreq>{e['changefreq']}</changefreq>")
        if e.get("priority"):
            lines.append(f"    <priority>{e['priority']}</priority>")
        img = e.get("image")
        if with_images and img:
            lines.append("    <image:image>")
            lines.append(f"      <image:loc>{xml_escape(abs_url(img))}</image:loc>")
            if e.get("image_title"):
                lines.append(
                    f"      <image:title>{xml_escape(e['image_title'])}</image:title>"
                )
            lines.append("    </image:image>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def render_sitemap_index(sitemaps: list[str]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    today = datetime.utcnow().strftime("%Y-%m-%d")
    for path in sitemaps:
        lines.append("  <sitemap>")
        lines.append(f"    <loc>{xml_escape(abs_url(path))}</loc>")
        lines.append(f"    <lastmod>{today}</lastmod>")
        lines.append("  </sitemap>")
    lines.append("</sitemapindex>")
    return "\n".join(lines) + "\n"
