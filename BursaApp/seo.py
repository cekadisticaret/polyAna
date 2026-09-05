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
DEFAULT_IMAGE = "/static/og-bursa.jpg"
LOCALE = "tr_TR"

# private / noindex path prefixes
NOINDEX_PREFIXES = (
    "/admin",
    "/hesap",
    "/giris",
    "/kayit",
    "/cikis",
    "/isletme",
    "/tesekkur",
    "/premium/checkout",
    "/favori/",
    "/api/",
    "/uploads/",
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
    robots: str = "index, follow, max-snippet:-1, max-image-preview:large"
    breadcrumbs: list[tuple[str, str]] = field(default_factory=list)
    json_ld: list[dict[str, Any]] = field(default_factory=list)
    keywords: str = ""
    graph: list[dict[str, Any]] | None = None
    schema_breadcrumbs: bool = False
    image_w: int = 1200
    image_h: int = 630
    hreflang: str | None = None

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
        if self.graph:
            payload = {"@context": "https://schema.org", "@graph": self.graph}
            return [json.dumps(payload, ensure_ascii=False, separators=(",", ":"))]
        blocks = [organization_ld(), website_ld()]
        if self.schema_breadcrumbs and self.breadcrumbs:
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
    graph: list[dict[str, Any]] | None = None,
    schema_breadcrumbs: bool = False,
    hreflang: str | None = None,
) -> PageSEO:
    from flask import request
    from seo_arch import INDEX_ROBOTS, OG_IMAGE

    p = path if path is not None else (request.path if request else "/")
    rob = robots or ("noindex, nofollow" if noindex else INDEX_ROBOTS)
    return PageSEO(
        title=title,
        description=description or DEFAULT_DESC,
        path=p,
        image=image or OG_IMAGE,
        og_type=og_type,
        robots=rob,
        breadcrumbs=breadcrumbs or [("Keşfet", "/")],
        json_ld=json_ld or [],
        keywords=keywords,
        graph=graph,
        schema_breadcrumbs=schema_breadcrumbs,
        hreflang=hreflang,
    )


def organization_ld() -> dict[str, Any]:
    from seo_arch import PHONE_E164, WHATSAPP_URL

    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": SITE_NAME,
        "url": site_base() + "/",
        "logo": abs_url("/static/logo-512.png"),
        "telephone": PHONE_E164,
        "sameAs": [WHATSAPP_URL],
        "description": DEFAULT_DESC,
        "areaServed": {"@type": "City", "name": "Bursa", "addressCountry": "TR"},
        "contactPoint": {
            "@type": "ContactPoint",
            "contactType": "customer support",
            "telephone": PHONE_E164,
            "availableLanguage": "Turkish",
        },
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
        "dentist": "Dentist",
        "vet": "VeterinaryCare",
        "school": "School",
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


def article_ld(*, title: str, description: str, path: str, image: str | None = None, date: str = "") -> dict[str, Any]:
    from seo_arch import article_full, OG_IMAGE

    return {
        "@context": "https://schema.org",
        **article_full(
            title=title,
            description=description,
            path=path,
            image=image or OG_IMAGE,
            date=date or datetime.utcnow().strftime("%Y-%m-%d"),
        ),
    }


def for_home() -> PageSEO:
    from seo_arch import home_graph, OG_IMAGE

    return page(
        title="Bursa Şehir Rehberi — restoran, gezi, otel",
        description=DEFAULT_DESC,
        path="/",
        image=OG_IMAGE,
        breadcrumbs=[("Ana Sayfa", "/")],
        keywords="bursa rehber, bursa restoran, bursa gezilecek yerler, bursa otel, bursa etkinlik",
        graph=home_graph(),
        hreflang="tr",
    )


def for_vertical(path: str, *, total: int = 0, places: list | None = None) -> PageSEO:
    from seo_arch import OG_IMAGE, VERTICALS, service_ld

    spec = VERTICALS[path]
    crumbs = [("Ana Sayfa", "/"), (spec["nav"], path)]
    ld = [
        {
            "@context": "https://schema.org",
            **service_ld(name=spec["service_name"], path=path, desc=spec["desc"]),
        }
    ]
    if places:
        ld.append(item_list_ld(spec["title"], path, places))
    desc = spec["desc"]
    if total:
        desc = clip(f"{desc} {total} kayıt.", 160)
    return page(
        title=spec["title"],
        description=desc,
        path=path,
        image=OG_IMAGE,
        breadcrumbs=crumbs,
        keywords=spec["keywords"],
        json_ld=ld,
        schema_breadcrumbs=False,
    )


def for_category(cat: dict[str, Any], *, ilce: str = "", sub: str = "", total: int = 0, places: list | None = None) -> PageSEO:
    from seo_arch import VERTICALS

    path = cat.get("path") or "/"
    if path in VERTICALS and not ilce and not sub:
        return for_vertical(path, total=total, places=places)
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
        schema_breadcrumbs=True,
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


def for_blog_hub() -> PageSEO:
    from blog_posts import all_blog_posts, blog_posts_sorted
    from seo_arch import OG_IMAGE

    all_p = all_blog_posts()
    n = len(all_p)
    desc = (
        f"Bursa gezi, kahvaltı, İskender, Uludağ, İznik, termal otel ve hafta sonu planları — "
        f"{n} how-to yazı; restoran ve gezilecek listelerine köprü."
    )
    elements = []
    for i, (slug, p) in enumerate(blog_posts_sorted(), 1):
        elements.append(
            {
                "@type": "ListItem",
                "position": i,
                "url": abs_url(f"/blog/{slug}"),
                "name": p["h1"],
            }
        )
    json_ld = [
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": "BursaApp Blog",
            "url": abs_url("/blog"),
            "description": clip(desc, 200),
            "mainEntity": {
                "@type": "ItemList",
                "numberOfItems": len(elements),
                "itemListElement": elements,
            },
        }
    ]
    return page(
        title="BursaApp Blog — gezi, yemek ve rota rehberi",
        description=desc,
        path="/blog",
        image=OG_IMAGE,
        breadcrumbs=[("Ana Sayfa", "/"), ("Blog", "/blog")],
        keywords="bursa blog, bursa gezi planı, bursa kahvaltı, bursa iskender, cumalıkızık, uludağ, iznik",
        og_type="website",
        json_ld=json_ld,
    )


def for_blog_post(slug: str) -> PageSEO | None:
    from blog_posts import all_blog_posts
    from seo_arch import OG_IMAGE

    post = all_blog_posts().get(slug)
    if not post:
        return None
    path = f"/blog/{slug}"
    return page(
        title=post["title"],
        description=post["desc"],
        path=path,
        image=post.get("image") or OG_IMAGE,
        og_type="article",
        breadcrumbs=[("Ana Sayfa", "/"), ("Blog", "/blog"), (post["h1"], path)],
        keywords=post["title"],
        json_ld=[
            article_ld(
                title=post["title"],
                description=post["desc"],
                path=path,
                image=post.get("image"),
                date=post.get("date") or "",
            )
        ],
    )


def for_kvkk() -> PageSEO:
    from seo_arch import OG_IMAGE

    return page(
        title="KVKK ve gizlilik",
        description="BursaApp gizlilik ve KVKK metni — hangi veri, neden, ne kadar.",
        path="/kvkk",
        image=OG_IMAGE,
        breadcrumbs=[("Ana Sayfa", "/"), ("KVKK", "/kvkk")],
        keywords="kvkk, gizlilik, bursaapp",
    )


def for_iletisim() -> PageSEO:
    from seo_arch import OG_IMAGE

    return page(
        title="İletişim",
        description="BursaApp destek — telefon ve WhatsApp ile ulaşın.",
        path="/iletisim",
        image=OG_IMAGE,
        breadcrumbs=[("Ana Sayfa", "/"), ("İletişim", "/iletisim")],
        keywords="bursaapp iletişim, destek, whatsapp",
    )


def for_tesekkur() -> PageSEO:
    from seo_arch import OG_IMAGE

    return page(
        title="Teşekkürler",
        description="İşleminiz tamamlandı — BursaApp.",
        path="/tesekkur",
        image=OG_IMAGE,
        noindex=True,
        breadcrumbs=[("Ana Sayfa", "/"), ("Teşekkürler", "/tesekkur")],
    )


def for_news_hub(*, total: int = 0, topic: str = "", articles: list | None = None) -> PageSEO:
    from news_pages import NEWS_TOPICS
    from seo_arch import OG_IMAGE

    topic_lab = NEWS_TOPICS.get(topic, "")
    title = f"Bursa haberleri — güncel gündem{f' · {topic_lab}' if topic_lab else ''}"
    desc = (
        "Bursa haberleri ve şehir gündemi: trafik, belediye, ekonomi, kültür, sağlık, spor. "
        "Video özeti + detaylı haber sayfaları — BursaApp'te kal, keşfet."
    )
    if total:
        desc = clip(f"{desc} {total} haber.", 165)
    json_ld = [
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": title,
            "url": abs_url("/haberler"),
            "description": clip(desc, 200),
        }
    ]
    if articles:
        elements = []
        for i, a in enumerate(articles[:20], 1):
            elements.append(
                {
                    "@type": "ListItem",
                    "position": i,
                    "url": abs_url(a.get("path") or f"/haber/{a.get('slug')}"),
                    "name": a.get("title"),
                }
            )
        json_ld.append(
            {
                "@context": "https://schema.org",
                "@type": "ItemList",
                "itemListElement": elements,
            }
        )
    return page(
        title=title,
        description=desc,
        path="/haberler" + (f"?konu={topic}" if topic else ""),
        image=OG_IMAGE,
        breadcrumbs=[("Ana Sayfa", "/"), ("Bursa Haberleri", "/haberler")],
        keywords="bursa haber, bursa haberleri, bursa gündem, bursa son dakika, bursa trafik, bursaspor haber",
        og_type="website",
        json_ld=json_ld,
        schema_breadcrumbs=True,
    )


def for_news_article(article: dict, *, video: dict | None = None) -> PageSEO | None:
    from seo_arch import OG_IMAGE

    if not article:
        return None
    path = f"/haber/{article.get('slug') or article.get('id')}"
    desc = clip(article.get("body_plain") or article.get("blurb") or article.get("title") or "", 165)
    img = article.get("img_url") or OG_IMAGE
    pub = article.get("published_at") or ""
    news_ld: dict = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": clip(article.get("title") or "", 110),
        "description": desc,
        "datePublished": pub,
        "dateModified": article.get("generated_at") or pub,
        "author": {"@type": "Organization", "name": article.get("source") or "BursaApp"},
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "logo": {"@type": "ImageObject", "url": abs_url("/static/logo-192.png")},
        },
        "mainEntityOfPage": abs_url(path),
        "image": [abs_url(img)],
        "articleSection": article.get("topic_label") or "Gündem",
        "inLanguage": "tr-TR",
    }
    json_ld = [news_ld]
    if video and video.get("id"):
        json_ld.append(
            {
                "@context": "https://schema.org",
                "@type": "VideoObject",
                "name": video.get("title"),
                "description": clip(video.get("title"), 160),
                "thumbnailUrl": video.get("thumb"),
                "uploadDate": video.get("published_at") or pub,
                "embedUrl": video.get("embed_url"),
            }
        )
    return page(
        title=f"{clip(article.get('title') or 'Bursa haberi', 58)} — Bursa haberleri",
        description=desc,
        path=path,
        image=img,
        breadcrumbs=[
            ("Ana Sayfa", "/"),
            ("Bursa Haberleri", "/haberler"),
            (clip(article.get("title") or "Haber", 48), path),
        ],
        keywords=f"bursa haber, bursa haberleri, {article.get('topic_label', '')}, {article.get('source', '')}",
        og_type="article",
        json_ld=json_ld,
        schema_breadcrumbs=True,
    )


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
                breadcrumbs=[("Ana Sayfa", "/")],
            )

    if path in ("/", "/kesfet"):
        return for_home()

    if path == "/blog":
        return for_blog_hub()
    mblog = re.match(r"^/blog/([^/]+)$", path)
    if mblog:
        post_seo = for_blog_post(mblog.group(1))
        if post_seo:
            return post_seo
    if path == "/kvkk":
        return for_kvkk()
    if path == "/tesekkur":
        return for_tesekkur()
    if path == "/oteller":
        return for_vertical("/oteller")

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
        breadcrumbs=[("Ana Sayfa", "/")],
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
    add("/yeme-icme", "daily", "0.9")
    add("/gezilecek", "daily", "0.8")
    add("/oteller", "daily", "0.8")
    add("/blog", "weekly", "0.7")
    from blog_posts import all_blog_posts

    for slug in all_blog_posts():
        add(f"/blog/{slug}", "weekly", "0.65")
    add("/kvkk", "yearly", "0.3")
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

    skip_cat = {"/yeme-icme", "/gezilecek", "/oteller"}
    for c in CATEGORIES:
        if c["path"] not in skip_cat:
            add(c["path"], "daily", "0.85")

    # kategori dışı kamuya açık sayfalar
    add("/bursaspor", "daily", "0.85")
    add("/haberler", "hourly", "0.95")
    add("/nobetci-eczaneler", "hourly", "0.9")
    add("/faturalar", "daily", "0.88")
    add("/buski-su-fiyatlari", "daily", "0.9")
    add("/bursa-elektrik-fiyatlari", "daily", "0.9")
    add("/bursa-dogalgaz-fiyatlari", "daily", "0.9")
    add("/uludag-teleferik", "daily", "0.9")
    add("/album", "weekly", "0.6")

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
