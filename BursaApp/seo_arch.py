#!/usr/bin/env python3
"""QR Düğün Foto SEO mimarisinin BursaApp karşılığı — hub / dikey / blog / trust."""
from __future__ import annotations

from typing import Any

# Tek iletişim (WhatsApp destek)
PHONE_E164 = "+905535469948"
PHONE_DISPLAY = "+90 553 546 99 48"
WHATSAPP_URL = "https://wa.me/905535469948"
OG_IMAGE = "/static/og-bursa.jpg"
OG_IMAGE_W = 1200
OG_IMAGE_H = 630
INDEX_ROBOTS = "index, follow, max-snippet:-1, max-image-preview:large"

# Görünür SSS — FAQPage ile birebir aynı sorular
HOME_FAQ = (
    (
        "BursaApp ücretli mi?",
        "Hayır. Şehir rehberi ücretsizdir; restoran, gezilecek yer ve otel listelerine üye olmadan bakılır. İşletme paketleri ayrıdır, zorunlu değildir.",
    ),
    (
        "Kayıtlar nasıl güncelleniyor?",
        "Üyeler taslak ekler, admin onaylar. Yayınlanan yerler yönetici onayından geçmiş kayıtlardır. Nöbetçi eczane listesi her akşam yenilenir.",
    ),
    (
        "Nasıl 1 günlük rota çıkarırım?",
        "Keşfet’te planını yap (yeme-içme, gezilecek, otel), ilçe veya filtreyle daralt, yer detayından rotaya ekle — veya /rota sayfasından bütçeli plan iste.",
    ),
    (
        "Rezervasyon veya sipariş verebilir miyim?",
        "Hayır. BursaApp yalnızca rehberdir; masa rezervasyonu, yemek siparişi veya bilet satışı yapmaz. İşletme telefonu ve harita linki yer detayında.",
    ),
    (
        "İşletmemi nasıl ekler veya güncellerim?",
        "Üye olup taslak yer ekleyebilir veya mevcut kaydı sahiplenme talebiyle güncelleyebilirsin. Yayın admin onayından sonra; sahte veya eksik kayıtlar reddedilir.",
    ),
)

HOME_HOWTO = (
    ("Planını yap", "Yeme-içme, gezilecek yerler veya oteller — aynı rehber, farklı plan."),
    ("İlçe ve filtreyle daralt", "Osmangazi, Nilüfer, Yıldırım… mutfak, tür veya giriş ücreti ile listeyi kıs."),
    ("Detay ve rota", "Saat, harita, puan. Beğendiğini 1 günlük rotaya ekle; rezervasyon veya bahis emri yok."),
)

# Dikey landing — aynı ürün, farklı H1 / title / Service.name
VERTICALS = {
    "/yeme-icme": {
        "nav": "Yeme-içme",
        "h1": "Bursa’da nerede yenir? Restoran ve cafe rehberi",
        "lead": "İskender, kahvaltı, kebap, cafe — ilçe ve mutfak filtresiyle Bursa sofra haritası. Ücretsiz rehber; rezervasyon siteden yapılmaz.",
        "title": "Bursa Restoran Rehberi",
        "desc": "Bursa’da nerede yenir? 700+ restoran ve cafe — İskender, kahvaltı, ilçe filtresi. Ücretsiz rehber.",
        "keywords": "bursa restoran, bursa'da ne yenir, bursa kahvaltı, iskender, bursa cafe",
        "service_name": "Bursa restoran ve yeme-içme rehberi",
        "why_title": "Neden BursaApp yeme-içme?",
        "why": (
            "İlçe ilçe restoran, cafe, kahvaltı ve pub tek listede.",
            "Mutfak ve yemek filtresi (İskender, köfte, balık).",
            "Puan ve öne çıkanlar; OSM kopyaları elenir.",
            "Ücretsiz; sipariş veya bahis emri yok.",
        ),
        "how_title": "Nasıl işler?",
        "cta_label": "Restoranları gör",
        "cta_href": "#liste",
        "cross": (("/gezilecek", "Gezilecek"), ("/oteller", "Oteller"), ("/blog", "Blog")),
    },
    "/gezilecek": {
        "nav": "Gezilecek",
        "h1": "Bursa gezilecek yerler: Ulu Cami’den Uludağ’a",
        "lead": "Hanlar, köyler, müze, şelale ve Uludağ. UNESCO ve ücretsiz duraklar aynı haritada. Kısa rota için blog yazısına bak.",
        "title": "Bursa Gezilecek Yerler",
        "desc": "Ulu Cami, Cumalıkızık, Gölyazı, Uludağ — Bursa gezilecek yerler, harita ve 1 günlük rota. Ücretsiz rehber.",
        "keywords": "bursa gezilecek yerler, ulu cami, cumalıkızık, uludağ, gölyazı",
        "service_name": "Bursa gezilecek yerler rehberi",
        "why_title": "Neden bu liste?",
        "why": (
            "Tarihi merkez + köy + doğa tek kategoride.",
            "Mahalle camisi ve rastgele zirve yok; öne çıkanlar üstte.",
            "Giriş ücreti ve UNESCO çipi.",
            "Yeme-içme ve otelle çapraz link.",
        ),
        "how_title": "Nasıl işler?",
        "cta_label": "Yerleri gör",
        "cta_href": "#liste",
        "cross": (("/yeme-icme", "Yeme-içme"), ("/oteller", "Oteller"), ("/blog", "Blog")),
    },
    "/oteller": {
        "nav": "Oteller",
        "h1": "Bursa otelleri: termal, şehir ve Uludağ konaklama",
        "lead": "Çekirge termal, şehir oteli ve Uludağ. Örnek gecelik tutar fikir verir — kart çekilmez, rezervasyon otelden.",
        "title": "Bursa Otelleri",
        "desc": "Bursa otelleri: Çekirge termal, şehir ve Uludağ. Örnek fiyat, ilçe filtresi — rezervasyon siteden yapılmaz.",
        "keywords": "bursa otel, çekirge termal, uludağ otel, bursa konaklama",
        "service_name": "Bursa otel ve konaklama rehberi",
        "why_title": "Neden BursaApp oteller?",
        "why": (
            "Termal, şehir ve dağ aynı listede.",
            "Gerçek kapak fotoğrafı ve ilçe.",
            "Rezervasyon ve kart yok.",
            "Yanına gezi ve yemek rotası eklenir.",
        ),
        "how_title": "Nasıl işler?",
        "cta_label": "Otelleri gör",
        "cta_href": "#liste",
        "cross": (("/yeme-icme", "Yeme-içme"), ("/gezilecek", "Gezilecek"), ("/blog", "Blog")),
    },
    "/dugun-salonlari": {
        "nav": "Düğün salonları",
        "h1": "Bursa düğün salonları: adres, fiyat ve foto",
        "lead": "Kapalı salon, bahçe ve davet mekânları. Paket aralığı bilgilendirme amaçlı — teklif için salonu arayın.",
        "title": "Bursa Düğün Salonları",
        "desc": "Bursa düğün salonları listesi: adres, telefon, paket fiyat aralığı ve salon fotoları. Rezervasyon siteden yapılmaz.",
        "keywords": "bursa düğün salonu, düğün salonları bursa, düğün paketi bursa, nikah salonu bursa",
        "service_name": "Bursa düğün salonu rehberi",
        "why_title": "Neden BursaApp düğün salonları?",
        "why": (
            "İlçe ve tür filtresi.",
            "Salon fotoları ve özellikler.",
            "Paket fiyat aralığı (teyit için arayın).",
            "Rezervasyon ve komisyon yok.",
        ),
        "how_title": "Nasıl işler?",
        "cta_label": "Salonları gör",
        "cta_href": "#liste",
        "cross": (("/oteller", "Oteller"), ("/yeme-icme", "Yeme-içme"), ("/etkinlikler", "Etkinlikler")),
    },
    "/gece-hayati": {
        "nav": "Gece hayatı",
        "h1": "Bursa gece hayatı: bar, pub ve gece kulüpleri",
        "lead": "Nilüfer, Osmangazi ve Mudanya hattında bar, meyhane, canlı müzik ve gece kulüpleri. Rezervasyon siteden yapılmaz.",
        "title": "Bursa Gece Hayatı",
        "desc": "Bursa bar, pub, gece kulübü ve meyhane listesi — ilçe filtresi, telefon ve harita. Ücretsiz rehber.",
        "keywords": "bursa gece hayatı, bursa bar, bursa gece kulübü, bursa meyhane, arap şükrü",
        "service_name": "Bursa gece hayatı rehberi",
        "why_title": "Neden BursaApp gece hayatı?",
        "why": (
            "Bar, pub, kulüp ve meyhane tek kategoride.",
            "İlçe ve tür filtresi.",
            "Telefon ve harita linki.",
            "Rezervasyon ve bilet satışı yok.",
        ),
        "how_title": "Nasıl işler?",
        "cta_label": "Mekanları gör",
        "cta_href": "#liste",
        "cross": (("/eglence", "Eğlence"), ("/konserler", "Konserler"), ("/yeme-icme", "Yeme-içme")),
    },
}

from blog_posts import BLOG_KINDS, all_blog_posts, blog_posts_sorted


def offer_ld(url: str) -> dict[str, Any]:
    return {
        "@type": "Offer",
        "url": url,
        "price": "0",
        "priceCurrency": "TRY",
        "availability": "https://schema.org/InStock",
        "description": "BursaApp şehir rehberi ücretsizdir.",
    }


def service_ld(*, name: str, path: str, desc: str) -> dict[str, Any]:
    from seo import abs_url, site_base

    url = abs_url(path)
    return {
        "@type": "Service",
        "name": name,
        "serviceType": "Şehir rehberi",
        "url": url,
        "description": desc,
        "provider": {"@type": "Organization", "name": "BursaApp", "url": site_base() + "/"},
        "areaServed": {"@type": "City", "name": "Bursa", "addressCountry": "TR"},
        "offers": offer_ld(url),
    }


def organization_full() -> dict[str, Any]:
    from seo import abs_url, site_base, DEFAULT_DESC

    return {
        "@type": "Organization",
        "@id": site_base() + "/#org",
        "name": "BursaApp",
        "url": site_base() + "/",
        "logo": abs_url("/static/logo-512.png"),
        "description": DEFAULT_DESC,
        "telephone": PHONE_E164,
        "areaServed": {"@type": "City", "name": "Bursa", "addressCountry": "TR"},
        "contactPoint": {
            "@type": "ContactPoint",
            "contactType": "customer support",
            "telephone": PHONE_E164,
            "availableLanguage": "Turkish",
        },
        "sameAs": [WHATSAPP_URL],
    }


def website_full() -> dict[str, Any]:
    from seo import site_base

    return {
        "@type": "WebSite",
        "@id": site_base() + "/#website",
        "name": "BursaApp",
        "url": site_base() + "/",
        "inLanguage": "tr-TR",
        "publisher": {"@id": site_base() + "/#org"},
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": site_base() + "/yeme-icme?q={search_term_string}",
            },
            "query-input": "required name=search_term_string",
        },
    }


def howto_ld() -> dict[str, Any]:
    from seo import abs_url, site_base

    steps = []
    for i, (name, text) in enumerate(HOME_HOWTO, 1):
        steps.append(
            {
                "@type": "HowToStep",
                "position": i,
                "name": name,
                "text": text,
                "url": site_base() + "/#nasil",
            }
        )
    return {
        "@type": "HowTo",
        "name": "BursaApp ile Bursa’da ne yapılacağını bulmak",
        "description": "Üç adım: plan, filtre, rota.",
        "url": abs_url("/"),
        "step": steps,
    }


def faq_ld() -> dict[str, Any]:
    from seo import site_base

    ents = []
    for q, a in HOME_FAQ:
        ents.append(
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
        )
    return {
        "@type": "FAQPage",
        "url": site_base() + "/#sss",
        "mainEntity": ents,
    }


def home_graph() -> list[dict[str, Any]]:
    from seo import abs_url, DEFAULT_DESC, site_base

    org = organization_full()
    web = website_full()
    page = {
        "@type": "WebPage",
        "@id": site_base() + "/#webpage",
        "url": abs_url("/"),
        "name": "Bursa QR kodsuz şehir rehberi — restoran, gezi, otel",
        "description": DEFAULT_DESC,
        "inLanguage": "tr-TR",
        "isPartOf": {"@id": site_base() + "/#website"},
        "about": {"@id": site_base() + "/#org"},
        "primaryImageOfPage": abs_url(OG_IMAGE),
    }
    svc = service_ld(
        name="Bursa şehir rehberi",
        path="/",
        desc=DEFAULT_DESC,
    )
    svc["@id"] = site_base() + "/#service"
    return [org, web, page, svc, howto_ld(), faq_ld()]


def article_full(*, title: str, description: str, path: str, image: str, date: str) -> dict[str, Any]:
    from seo import abs_url, clip, site_base

    url = abs_url(path)
    return {
        "@type": "Article",
        "headline": title,
        "description": clip(description, 200),
        "url": url,
        "image": abs_url(image),
        "datePublished": date,
        "dateModified": date,
        "inLanguage": "tr-TR",
        "author": {"@id": site_base() + "/#org"},
        "publisher": {
            "@type": "Organization",
            "name": "BursaApp",
            "logo": {"@type": "ImageObject", "url": abs_url("/static/logo-512.png")},
        },
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
    }


def llms_txt(db=None) -> str:
    from ai_seo import llms_txt as _gen

    return _gen(db)

