#!/usr/bin/env python3
"""BursaApp — şehir rehberi. Üye ekler, admin onaylar. Port 5051, 127.0.0.1."""
from __future__ import annotations

import calendar
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, Response

from admin import bp as admin_bp
from api_v1 import bp as api_v1_bp
from features import bp as features_bp
from features import hub_context, _active_campaigns
from auth import (
    hash_password,
    load_user,
    login_required,
    login_user,
    logout_user,
    rate_ok,
    verify_password,
)
from catalog import (
    CAT_BY_KEY,
    CAT_BY_PATH,
    CATEGORIES,
    CONCERT_KINDS,
    DOCTOR_SPECS,
    GROUP_BAND,
    GROUP_ILCE,
    ILCELER,
    KIND_BY_CAT,
    MEKAN_TAXONOMY,
    maps_url,
    parse_dt,
    place_public,
    query_places,
    subcategories_for,
    tags_dump,
    unique_slug,
)
from discover import (
    FALLBACK_LAT,
    FALLBACK_LNG,
    nearby,
    today_bursa,
    tonight,
    weekend,
    weekend_plan,
)
from models import (
    Place,
    Review,
    SessionLocal,
    SportMatch,
    User,
    clamp_score,
    init_db,
    recompute_place_rating,
    review_dimension_avgs,
)

_DIR = os.path.dirname(os.path.abspath(__file__))
_TZ = ZoneInfo("Europe/Istanbul")
_ROOT_ENV = os.path.join(os.path.dirname(_DIR), ".env")


def _load_env(path: str) -> None:
    if not os.path.isfile(path):
        return
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


_load_env(_ROOT_ENV)
_load_env(os.path.join(_DIR, ".env"))

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("BURSAAPP_SECRET_KEY") or os.environ.get("BURSAAPP_JWT_SECRET") or "bursaapp-dev"
app.config["SESSION_COOKIE_NAME"] = "bursaapp_session"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30
app.register_blueprint(api_v1_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(features_bp)

init_db()


@app.context_processor
def _inject():
    from seo import resolve_seo, site_base
    from seo_status import ga_measurement_id, google_verification_token
    from mail_verify import VERIFY_DAYS, can_review, verify_banner

    user = load_user()
    return {
        "nav_user": user,
        "can_review": can_review(user),
        "email_verify_banner": verify_banner(user),
        "verify_days": VERIFY_DAYS,
        "categories": CATEGORIES,
        "ilceler": ILCELER,
        "mekan_taxonomy": MEKAN_TAXONOMY,
        "google_site_verification": google_verification_token(),
        "ga_measurement_id": ga_measurement_id(),
        "site_url": site_base(),
        "seo": resolve_seo(),
    }


@app.after_request
def _cache_headers(resp):
    path = request.path or ""
    # Güvenlik başlıkları
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
    if path.startswith("/static/"):
        # Görseller uzun cache — sayfa yenilemede sürekli indirilmesin
        if any(path.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".woff2", ".css", ".js")):
            resp.headers["Cache-Control"] = "public, max-age=604800, immutable"
        else:
            resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
    if path.startswith("/sitemap") or path in ("/favicon.ico", "/robots.txt"):
        resp.headers["Cache-Control"] = "public, max-age=3600"
        return resp
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    # Ziyaretçi / sayfa görüntüleme
    try:
        from analytics import track_response

        track_response(request, resp)
    except Exception:
        pass
    return resp


def _weather() -> dict:
    return {"label": "Açık", "temp_c": 24, "hint": "Uludağ serin · merkez ılık"}


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/x-icon",
    )


@app.route("/robots.txt")
def robots_txt():
    from seo import site_base

    base = site_base()
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /hesap\n"
        "Disallow: /giris\n"
        "Disallow: /kayit\n"
        "Disallow: /isletme\n"
        "Disallow: /api/\n"
        "Disallow: /*?*lat=\n"
        "Disallow: /*?*lng=\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return Response(body, mimetype="text/plain; charset=utf-8")


@app.route("/sitemap.xml")
def sitemap_xml():
    """Sitemap index — Search Console'a bu URL verilir."""
    from seo import render_sitemap_index

    return Response(
        render_sitemap_index(
            [
                "/sitemap-pages.xml",
                "/sitemap-places.xml",
                "/sitemap-images.xml",
            ]
        ),
        mimetype="application/xml; charset=utf-8",
    )


@app.route("/sitemap-pages.xml")
def sitemap_pages():
    from seo import abs_url, render_urlset, sitemap_static_urls
    from models import Editorial

    entries = sitemap_static_urls()
    db = SessionLocal()
    try:
        for ed in db.query(Editorial).filter(Editorial.status == "approved").all():
            entries.append(
                {
                    "loc": abs_url(f"/oneriyor/{ed.slug}"),
                    "changefreq": "weekly",
                    "priority": "0.65",
                    "lastmod": ed.created_at,
                }
            )
    finally:
        db.close()

    seen: set[str] = set()
    uniq = []
    for e in entries:
        loc = e.get("loc")
        if not loc or loc in seen:
            continue
        seen.add(loc)
        uniq.append(e)
    return Response(render_urlset(uniq), mimetype="application/xml; charset=utf-8")


@app.route("/sitemap-places.xml")
def sitemap_places():
    from seo import abs_url, render_urlset

    db = SessionLocal()
    try:
        rows = (
            db.query(Place)
            .filter(Place.status == "approved")
            .order_by(Place.id.desc())
            .limit(10000)
            .all()
        )
        entries = []
        for p in rows:
            entries.append(
                {
                    "loc": abs_url(f"/yer/{p.slug}"),
                    "changefreq": "weekly",
                    "priority": "0.7",
                    "lastmod": p.created_at,
                }
            )
    finally:
        db.close()
    return Response(render_urlset(entries), mimetype="application/xml; charset=utf-8")


@app.route("/sitemap-images.xml")
def sitemap_images():
    from seo import abs_url, render_urlset

    db = SessionLocal()
    try:
        rows = (
            db.query(Place)
            .filter(
                Place.status == "approved",
                Place.img_url.isnot(None),
                Place.img_url != "",
            )
            .order_by(Place.id.desc())
            .limit(5000)
            .all()
        )
        entries = []
        for p in rows:
            entries.append(
                {
                    "loc": abs_url(f"/yer/{p.slug}"),
                    "changefreq": "weekly",
                    "priority": "0.6",
                    "lastmod": p.created_at,
                    "image": p.img_url,
                    "image_title": p.title,
                }
            )
    finally:
        db.close()
    return Response(
        render_urlset(entries, with_images=True),
        mimetype="application/xml; charset=utf-8",
    )


def _month_shows(db):
    now = datetime.now(_TZ).replace(tzinfo=None)
    start = datetime(now.year, now.month, 1)
    end = datetime(now.year + (1 if now.month == 12 else 0), 1 if now.month == 12 else now.month + 1, 1)
    return (
        db.query(Place)
        .filter(
            Place.status == "approved",
            Place.starts_at.isnot(None),
            Place.starts_at >= start,
            Place.starts_at < end,
            Place.category.in_(("event", "theater", "concert", "cinema", "family")),
        )
        .order_by(Place.starts_at.asc())
        .all()
    )


def _cal(events: list):
    now = datetime.now(_TZ)
    ay = (
        "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
        "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
    )
    ev_days = set()
    ev_map = {}
    ev_slug = {}
    for e in events:
        if e.starts_at:
            if e.starts_at.year == now.year and e.starts_at.month == now.month:
                ev_days.add(e.starts_at.day)
                ev_map[e.starts_at.day] = e.title
                ev_slug[e.starts_at.day] = e.slug
    _first_wd, n_days = calendar.monthrange(now.year, now.month)
    pad = datetime(now.year, now.month, 1).weekday()
    return {
        "year": now.year,
        "month": now.month,
        "month_label": f"{ay[now.month - 1]} {now.year}",
        "today": now.day,
        "cal_cells": [None] * pad + list(range(1, n_days + 1)),
        "ev_days": ev_days,
        "ev_map": ev_map,
        "ev_slug": ev_slug,
        "events": events,
    }


@app.route("/")
@app.route("/kesfet")
def home():
    q = (request.args.get("q") or "").strip()
    db = SessionLocal()
    try:
        hub = hub_context(db)
        featured, _ = query_places(db, featured=True, q=q or None, limit=8)
        if len(featured) < 8:
            extra, _ = query_places(db, q=q or None, limit=16)
            seen = {p.id for p in featured}
            for p in extra:
                if p.id not in seen:
                    featured.append(p)
                if len(featured) >= 8:
                    break
        place_count = db.query(Place).filter(Place.status == "approved").count()
        cal = _cal(_month_shows(db))
        from seo import for_home

        return render_template(
            "home.html",
            featured=[place_public(p) for p in featured],
            q=q,
            weather=_weather(),
            ilce_n=len(ILCELER),
            place_count=place_count,
            nav="kesfet",
            seo=for_home(),
            **hub,
            **cal,
        )
    finally:
        db.close()


@app.route("/bugun")
def bugun():
    db = SessionLocal()
    try:
        data = today_bursa(db)
        return render_template("today.html", today=data, nav="bugun", weather=_weather())
    finally:
        db.close()


@app.route("/bu-aksam")
def bu_aksam():
    couple = (request.args.get("mode") or "").strip() == "couple"
    db = SessionLocal()
    try:
        data = tonight(db, couple=couple)
        return render_template("tonight.html", data=data, couple=couple, nav="aksam", weather=_weather())
    finally:
        db.close()


@app.route("/yakinimda")
def yakinimda():
    db = SessionLocal()
    try:
        used_fallback = False
        try:
            lat = float(request.args.get("lat"))
            lng = float(request.args.get("lng"))
        except (TypeError, ValueError):
            lat, lng = FALLBACK_LAT, FALLBACK_LNG
            used_fallback = True
        try:
            radius = float(request.args.get("r") or 500)
        except (TypeError, ValueError):
            radius = 500
        radius = max(200, min(radius, 5000))
        data = nearby(db, lat, lng, radius)
        return render_template(
            "nearby.html",
            data=data,
            used_fallback=used_fallback,
            nav="yakin",
            weather=_weather(),
        )
    finally:
        db.close()


@app.route("/hafta-sonu")
def hafta_sonu():
    plan_mode = (request.args.get("plan") or "").strip() == "1"
    people = 2
    try:
        people = max(1, min(int(request.args.get("people") or 2), 8))
    except ValueError:
        people = 2
    db = SessionLocal()
    try:
        data = weekend(db)
        plan = weekend_plan(db, people=people) if plan_mode else None
        return render_template(
            "weekend.html",
            data=data,
            plan=plan,
            people=people,
            nav="haftasonu",
            weather=_weather(),
        )
    finally:
        db.close()


@app.route("/marketler")
def marketler():
    """Market listesi · yakınımda · kampanyalı."""
    from seo import for_category

    tab = (request.args.get("tab") or "hepsi").strip().lower()
    if tab not in ("hepsi", "yakin", "kampanya"):
        tab = "hepsi"
    cat = CAT_BY_KEY["market"]
    sub = (request.args.get("sub") or "").strip()
    ilce = (request.args.get("ilce") or "").strip()
    used_fallback = False
    try:
        lat = float(request.args.get("lat"))
        lng = float(request.args.get("lng"))
    except (TypeError, ValueError):
        lat, lng = FALLBACK_LAT, FALLBACK_LNG
        used_fallback = True
    try:
        radius = float(request.args.get("r") or 1500)
    except (TypeError, ValueError):
        radius = 1500
    radius = max(400, min(radius, 8000))

    db = SessionLocal()
    try:
        campaigns = _active_campaigns(db, 40, category="market")
        camp_by_place = {it["place"]["id"]: it["campaign"] for it in campaigns}
        places = []
        if tab == "yakin":
            data = nearby(db, lat, lng, radius, category="market")
            places = data["places"]
            for p in places:
                c = camp_by_place.get(p["id"])
                if c:
                    p["campaign_badge"] = c.badge or c.title
        elif tab == "kampanya":
            places = []
        else:
            rows, _ = query_places(
                db,
                category="market",
                ilce=ilce or None,
                subcategory=sub or None,
                order="rating",
                limit=120,
            )
            places = [place_public(p) for p in rows]
            for p in places:
                c = camp_by_place.get(p["id"])
                if c:
                    p["campaign_badge"] = c.badge or c.title

        return render_template(
            "markets.html",
            cat=cat,
            tab=tab,
            places=places,
            campaigns=campaigns,
            sub=sub,
            ilce=ilce,
            sub_chips=subcategories_for("market"),
            ilceler=list(ILCELER),
            lat=lat,
            lng=lng,
            radius=int(radius),
            used_fallback=used_fallback,
            nav="market",
            seo=for_category(cat),
        )
    finally:
        db.close()


@app.route("/veterinerler")
def veterinerler():
    """Veteriner listesi — yakındakileri mesafeye göre sırala."""
    from seo import for_category

    cat = CAT_BY_KEY["vet"]
    tab = (request.args.get("tab") or "hepsi").strip().lower()
    if tab not in ("hepsi", "yakin"):
        tab = "hepsi"
    ilce = (request.args.get("ilce") or "").strip()
    sub = (request.args.get("sub") or "").strip()
    used_fallback = False
    try:
        lat = float(request.args.get("lat"))
        lng = float(request.args.get("lng"))
    except (TypeError, ValueError):
        lat, lng = FALLBACK_LAT, FALLBACK_LNG
        used_fallback = True

    db = SessionLocal()
    try:
        if tab == "yakin":
            data = nearby(db, lat, lng, category="vet", unlimited=True)
            places = data["places"]
            total = len(places)
            groups = []
        else:
            rows, total = query_places(
                db,
                category="vet",
                ilce=ilce or None,
                subcategory=sub or None,
                order="rating",
                limit=120,
            )
            places = [place_public(p) for p in rows]
            groups = []
            by = {}
            for p in places:
                by.setdefault(p.get("ilce") or "Diğer", []).append(p)
            for ad in ILCELER:
                if ad in by:
                    groups.append({"label": ad, "places": by.pop(ad)})
            for ad, plist in by.items():
                groups.append({"label": ad, "places": plist})

        return render_template(
            "vets.html",
            cat=cat,
            tab=tab,
            places=places,
            groups=groups,
            total=total,
            ilce=ilce,
            sub=sub,
            sub_chips=subcategories_for("vet"),
            ilceler=list(ILCELER),
            lat=lat,
            lng=lng,
            used_fallback=used_fallback,
            nav="vet",
            seo=for_category(cat, ilce=ilce, sub=sub, total=total, places=places),
        )
    finally:
        db.close()


def _load_nobetci_feed() -> dict:
    import json as _json

    path = os.path.join(_DIR, "data", "nobetci_eczaneler.json")
    if not os.path.isfile(path):
        return {"ok": False, "pharmacies": [], "total": 0, "duty_date": "", "attribution": ""}
    try:
        return _json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return {"ok": False, "pharmacies": [], "total": 0, "duty_date": "", "attribution": ""}


@app.route("/nobetci-eczaneler")
def nobetci_eczaneler():
    from seo import page as seo_page

    ilce = (request.args.get("ilce") or "").strip()
    feed = _load_nobetci_feed()
    items = list(feed.get("pharmacies") or [])
    if ilce:
        items = [p for p in items if (p.get("district") or "") == ilce]
    districts = sorted({p.get("district") for p in (feed.get("pharmacies") or []) if p.get("district")})
    by = {}
    for p in items:
        by.setdefault(p.get("district") or "Diğer", []).append(p)
    groups = []
    for ad in list(ILCELER) + [k for k in by if k not in ILCELER]:
        if ad in by:
            groups.append({"label": ad, "places": by.pop(ad)})
    for ad, plist in by.items():
        groups.append({"label": ad, "places": plist})
    return render_template(
        "nobetci_eczaneler.html",
        feed=feed,
        groups=groups,
        places=items,
        ilce=ilce,
        districts=districts,
        nav="pharmacy",
        seo=seo_page(
            title="Bursa nöbetçi eczaneler",
            description="Bugün Bursa nöbetçi eczaneleri — ilçe, telefon, Google Maps konum.",
            path="/nobetci-eczaneler",
        ),
    )


@app.route("/nobetci-eczaneler/<slug>")
def nobetci_eczane_detail(slug: str):
    from seo import page as seo_page

    feed = _load_nobetci_feed()
    place = next((p for p in (feed.get("pharmacies") or []) if p.get("slug") == slug), None)
    return render_template(
        "nobetci_eczane_detail.html",
        place=place,
        feed=feed,
        nav="pharmacy",
        seo=seo_page(
            title=(place["name"] if place else "Nöbetçi eczane") + " · Bursa",
            description=(place.get("address") if place else "Bursa nöbetçi eczane") or "",
            path=f"/nobetci-eczaneler/{slug}",
        ),
    )


@app.route("/kamp")
def kamp_list():
    from seo import page as seo_page

    vibe = (request.args.get("vibe") or "").strip().lower()
    db = SessionLocal()
    try:
        rows, _ = query_places(db, category="camp", order="rating", limit=200)
        places = [place_public(p) for p in rows]

        def match(p):
            ex = p.get("extra") or {}
            tags = [t.lower() for t in (p.get("tags") or [])]
            v = (ex.get("vibe") or "").lower()
            sub = (p.get("subcategory") or "").lower()
            band = (p.get("price_band") or "").lower()
            city = (ex.get("city") or "").lower()
            if not vibe:
                return True
            if vibe == "instagram":
                return v == "instagram" or "instagram" in tags or bool(p.get("featured"))
            if vibe == "uludag":
                return sub == "uludag" or "uludag" in tags
            if vibe == "deniz":
                return sub == "deniz" or "deniz" in tags or v == "deniz"
            if vibe == "gol":
                return sub in ("gol",) or "gol" in tags or "golet" in tags or v == "gol"
            if vibe == "yayla":
                return sub in ("yayla", "orman") or "yayla" in tags or "orman" in tags
            if vibe == "kanyon":
                return sub in ("kanyon", "selale") or "kanyon" in tags or "selale" in tags
            if vibe == "ucretsiz":
                return "ucretsiz" in band or "ücretsiz" in band or "ucretsiz" in tags or v == "ucretsiz"
            if vibe == "balikesir":
                return "balikesir" in tags or "balıkesir" in city or city == "balıkesir"
            return True

        places = [p for p in places if match(p)]
        places.sort(
            key=lambda p: (
                -(float(p["rating"]) if p.get("rating") is not None else -1.0),
                0 if p.get("featured") else 1,
                (p.get("title") or ""),
            )
        )
        featured = [p for p in places if p.get("featured")][:8]
        return render_template(
            "camps.html",
            places=places,
            featured=featured,
            groups=[],
            vibe=vibe,
            nav="camp",
            seo=seo_page(
                title="Bursa kamp yerleri",
                description="Çobankaya, Kapanca, Gölyazı, Longoz, Saitabat ve Balıkesir kaçışları — BursaApp kamp rehberi.",
                path="/kamp",
                breadcrumbs=[("Keşfet", "/"), ("Kamp", "/kamp")],
                keywords="bursa kamp, çobankaya, kapanca, gölyazı kamp, uludağ kamp, karacabey longoz",
            ),
        )
    finally:
        db.close()


@app.route("/oteller")
def hotels_list():
    from seo import page as seo_page
    from catalog import subcategories_for, ILCELER

    q = (request.args.get("q") or "").strip()
    ilce = (request.args.get("ilce") or "").strip()
    sub = (request.args.get("sub") or "").strip()
    band = (request.args.get("band") or "").strip().lower()
    db = SessionLocal()
    try:
        rows, _ = query_places(
            db,
            category="hotel",
            ilce=ilce or None,
            q=q or None,
            subcategory=sub or None,
            order="rating",
            limit=300,
        )
        places = [place_public(p) for p in rows]
        if band:
            places = [p for p in places if (p.get("price_band") or "").lower() == band]
        places.sort(
            key=lambda p: (
                -(float(p["rating"]) if p.get("rating") is not None else -1.0),
                (p.get("title") or ""),
            )
        )
        featured = [p for p in places if p.get("featured")][:8]
        if len(featured) < 4:
            featured = places[:8]
        featured_slugs = {p.get("slug") for p in featured}
        districts = sorted({p.get("ilce") for p in places if p.get("ilce")}) or list(ILCELER)
        return render_template(
            "hotels.html",
            places=places,
            featured=featured,
            featured_slugs=featured_slugs,
            q=q,
            ilce=ilce,
            sub=sub,
            band=band,
            subs=subcategories_for("hotel"),
            districts=districts,
            nav="hotel",
            seo=seo_page(
                title="Bursa Oteller",
                description="Termal Çekirge, şehir otelleri ve Uludağ konaklama — BursaApp otel rehberi. Rezervasyon siteden yapılmaz.",
                path="/oteller",
                breadcrumbs=[("Keşfet", "/"), ("Oteller", "/oteller")],
                keywords="bursa otel, çekirge termal, uludağ otel, bursa konaklama",
            ),
        )
    finally:
        db.close()


@app.route("/yeme-icme")
@app.route("/gezilecek")
@app.route("/alisveris")
@app.route("/spor")
@app.route("/aile")
@app.route("/konserler")
@app.route("/tiyatro")
@app.route("/sinema")
@app.route("/eglence")
@app.route("/etkinlikler")
@app.route("/organizasyonlar")
@app.route("/hastaneler")
@app.route("/doktorlar")
def category_list():
    cat = CAT_BY_PATH.get(request.path)
    if not cat:
        return redirect("/")
    q = (request.args.get("q") or "").strip()
    ilce = (request.args.get("ilce") or "").strip()
    spec = (request.args.get("spec") or "").strip()
    sub = (request.args.get("sub") or "").strip()
    food = cat["key"] == "food"
    visit = cat["key"] == "visit"
    doctor = cat["key"] == "doctor"
    hospital = cat["key"] == "hospital"
    tax_subs = subcategories_for(cat["key"])
    kinds = None if tax_subs else KIND_BY_CAT.get(cat["key"])
    # Hastane: ilçe grupları yok — tek liste, puana göre
    grouped = (not hospital) and (
        cat["key"] in GROUP_ILCE or cat["key"] in GROUP_BAND or bool(tax_subs)
    )
    band = spec if (doctor or kinds) else None
    db = SessionLocal()
    try:
        rows, total = query_places(
            db,
            category=cat["key"],
            ilce=ilce or None,
            q=q or None,
            from_=request.args.get("from"),
            to=request.args.get("to"),
            order="rating" if (food or hospital) else ("date" if kinds else None),
            price_band=band or None,
            subcategory=sub or None,
            limit=500 if food else (200 if grouped or hospital else 60),
        )
        places = [place_public(p) for p in rows]
        if hospital:
            band_f = (request.args.get("band") or "").strip()
            if band_f:
                places = [p for p in places if (p.get("price_band") or "") == band_f]
                total = len(places)
            # Öne çıkan + yüksek puan önce (özel kaybolmasın)
            places.sort(
                key=lambda p: (
                    0 if p.get("featured") else 1,
                    -(float(p["rating"]) if p.get("rating") is not None else -1.0),
                    (p.get("title") or ""),
                )
            )
        if visit:
            _order = {s: i for i, s in enumerate((
                "ulu-cami", "koza-han", "hanlar-kapalicarsi", "tophane", "kale-sokak",
                "muradiye", "eski-kaplica", "inkaya-cinari", "panorama-1326", "uludag",
                "teleferik", "yesil-turbe", "yesil-cami", "emir-sultan", "irgandi",
                "cumalikizik", "golyazi", "misi", "soganli-botanik", "tirilye",
                "oylat", "suuctu", "iznik-surlar",
            ))}
            places.sort(key=lambda p: _order.get(p.get("slug") or "", 99))
        groups = []
        sub_chips = tax_subs if tax_subs and not doctor and not kinds else []
        chip_items = list(ILCELER)
        chip_param = "ilce"
        chip_on = ilce
        if doctor:
            chip_items = list(DOCTOR_SPECS)
            chip_param = "spec"
            chip_on = spec
            sub_chips = []
        elif kinds:
            chip_items = list(kinds)
            chip_param = "spec"
            chip_on = spec
            sub_chips = []
        if grouped:
            by = {}
            if cat["key"] in GROUP_BAND:
                key_fn = lambda p: p.get("price_band") or "Diğer"
                order = DOCTOR_SPECS if doctor else (kinds if kinds else [])
            elif sub_chips and not ilce:
                key_fn = lambda p: p.get("subcategory_label") or "Diğer"
                order = [lab for _, lab in sub_chips]
            else:
                key_fn = lambda p: p.get("ilce") or "Diğer"
                order = list(ILCELER)
            for p in places:
                by.setdefault(key_fn(p), []).append(p)
            for ad in order:
                if ad in by:
                    groups.append({"label": ad, "places": by.pop(ad)})
            for ad, plist in by.items():
                groups.append({"label": ad, "places": plist})
        if doctor:
            slugs = {p.get("hospital_slug") or p.get("venue_name") for p in places}
            slugs.discard("")
            slugs.discard(None)
            if slugs:
                hs = {h.slug: h for h in db.query(Place).filter(Place.slug.in_(slugs)).all()}
                for p in places:
                    h = hs.get(p.get("hospital_slug") or p.get("venue_name") or "")
                    if h:
                        p["hospital_title"] = h.title
                        p["hospital_slug"] = h.slug
        from seo import for_category

        hosp_band = (request.args.get("band") or "").strip() if hospital else ""
        hospital_bands = ("Özel", "Devlet", "Üniversite", "Kampüs", "Göz", "Diş") if hospital else ()

        return render_template(
            "list.html",
            cat=cat,
            places=places,
            groups=groups,
            total=total,
            q=q,
            ilce=ilce,
            sub=sub,
            chip_items=chip_items,
            chip_param=chip_param,
            chip_on=chip_on,
            sub_chips=sub_chips,
            hosp_band=hosp_band,
            hospital_bands=hospital_bands,
            cal=_cal(_month_shows(db)) if cat["key"] == "event" else None,
            nav=cat["key"],
            seo=for_category(
                cat,
                ilce=ilce,
                sub=sub or (chip_on if chip_param == "spec" else ""),
                total=total,
                places=places,
            ),
        )
    finally:
        db.close()


@app.route("/album")
def album_page():
    import json as _json

    items = []
    ap = os.path.join(_DIR, "data", "album.json")
    if os.path.isfile(ap):
        try:
            items = _json.loads(open(ap, encoding="utf-8").read())
        except Exception:
            items = []
    from seo import page as seo_page

    return render_template(
        "album.html",
        items=items,
        nav="album",
        seo=seo_page(
            title="Bursa albüm",
            description="Bursa’dan seçilmiş görseller — Wikimedia Commons.",
            path="/album",
        ),
    )


@app.route("/bursaspor")
def bursaspor_page():
    db = SessionLocal()
    try:
        rows = (
            db.query(SportMatch)
            .filter(SportMatch.club == "bursaspor", SportMatch.season == "2026-27")
            .order_by(SportMatch.week.asc().nullslast(), SportMatch.kickoff_at.asc().nullslast())
            .all()
        )
        matches = []
        for m in rows:
            matches.append(
                {
                    "id": m.id,
                    "week": m.week,
                    "competition": m.competition,
                    "kickoff_at": m.kickoff_at.strftime("%d.%m.%Y %H:%M") if m.kickoff_at else "",
                    "kickoff_raw": m.kickoff_at,
                    "home_team": m.home_team,
                    "away_team": m.away_team,
                    "home_score": m.home_score,
                    "away_score": m.away_score,
                    "venue": m.venue,
                    "is_home": m.is_home,
                    "ticket_price": m.ticket_price,
                    "ticket_url": m.ticket_url,
                    "status": m.status,
                    "note": m.note,
                    "played": m.home_score is not None and m.away_score is not None,
                }
            )
        from seo import page as seo_page
        import json as _json
        import os as _os

        standings = []
        sp = _os.path.join(_DIR, "data", "bursaspor_standings.json")
        if _os.path.isfile(sp):
            try:
                standings = _json.loads(open(sp, encoding="utf-8").read())
            except Exception:
                standings = []

        feed = {"news": [], "desk": {}, "generated_at": "", "disclaimer": ""}
        fp = _os.path.join(_DIR, "data", "bursaspor_feed.json")
        if _os.path.isfile(fp):
            try:
                feed = _json.loads(open(fp, encoding="utf-8").read())
            except Exception:
                pass

        return render_template(
            "bursaspor.html",
            matches=matches,
            standings=standings,
            feed=feed,
            nav="bursaspor",
            seo=seo_page(
                title="Bursaspor haber · maç masası · fikstür 2026-27",
                description="Bursaspor haber özetleri, maç analizi, Trendyol 1. Lig puan durumu ve fikstür.",
                path="/bursaspor",
            ),
        )
    finally:
        db.close()


@app.route("/yer/<slug>")
def detail(slug: str):
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == slug, Place.status == "approved").first()
        if p is None:
            from seo import page as seo_page

            return (
                render_template(
                    "detail.html",
                    place=None,
                    similar=[],
                    reviews=[],
                    dims=None,
                    my_review=None,
                    is_fav=False,
                    nav="kesfet",
                    seo=seo_page(
                        title="Kayıt bulunamadı",
                        description="Bu kayıt yayınlı değil veya kaldırılmış.",
                        path=f"/yer/{slug}",
                        noindex=True,
                    ),
                ),
                404,
            )        # view counter
        p.views = int(p.views or 0) + 1
        db.commit()
        similar, _ = query_places(db, category=p.category, limit=6)
        similar = [place_public(s) for s in similar if s.id != p.id][:3]
        d = place_public(p)
        d["maps"] = maps_url(p)
        venue_events = []
        if p.category in ("event", "concert", "theater") and (p.venue_name or p.address):
            vn = (p.venue_name or "").strip()
            addr = (p.address or "").strip()
            q = (
                db.query(Place)
                .filter(
                    Place.status == "approved",
                    Place.category.in_(("event", "concert", "theater")),
                    Place.id != p.id,
                )
            )
            if vn:
                q = q.filter((Place.venue_name == vn) | (Place.address == vn))
            elif addr:
                q = q.filter(Place.address == addr)
            rows = q.order_by(Place.starts_at.asc().nulls_last()).limit(8).all()
            venue_events = [place_public(x) for x in rows]
        staff, staff_groups, hospital, units = [], [], None, []
        if p.category == "hospital":
            docs, _ = query_places(db, category="doctor", venue_name=p.slug, limit=500)
            staff = [place_public(x) for x in docs]
            by = {}
            for s in staff:
                by.setdefault(s.get("price_band") or "Diğer", []).append(s)
            for ad in DOCTOR_SPECS:
                if ad in by:
                    staff_groups.append({"label": ad, "places": by.pop(ad)})
            for ad, plist in by.items():
                staff_groups.append({"label": ad, "places": plist})
            unit_rows, _ = query_places(db, category="hospital", venue_name=p.slug, limit=20)
            units = [place_public(u) for u in unit_rows if u.id != p.id]
        elif p.category == "doctor" and p.venue_name:
            h = db.query(Place).filter(Place.slug == p.venue_name, Place.status == "approved").first()
            if h:
                hospital = place_public(h)
                hospital["maps"] = maps_url(h)
        reviews = (
            db.query(Review)
            .filter(Review.place_id == p.id, Review.status == "approved")
            .order_by(Review.updated_at.desc())
            .limit(50)
            .all()
        )
        user = load_user()
        my_review = None
        is_fav = False
        is_going = False
        going_count = 0
        if user:
            my_review = db.query(Review).filter(Review.place_id == p.id, Review.user_id == user.id).first()
            from models import Favorite
            is_fav = (
                db.query(Favorite).filter(Favorite.user_id == user.id, Favorite.place_id == p.id).first()
                is not None
            )
        from feed_social import going_count as _going_count, user_is_going

        going_count = _going_count(db, p.id)
        if user:
            is_going = user_is_going(db, user.id, p.id)
        dims = review_dimension_avgs(db, p.id)
        from seo import for_place
        from models import PlacePhoto

        user_photos = [
            {"img_url": x.img_url, "caption": x.caption}
            for x in db.query(PlacePhoto)
            .filter(PlacePhoto.place_id == p.id, PlacePhoto.status == "approved")
            .order_by(PlacePhoto.id.desc())
            .limit(40)
            .all()
        ]

        if p.category == "food":
            tmpl = "restaurant_detail.html"
        elif p.category == "hospital":
            tmpl = "hospital_detail.html"
        elif p.category == "doctor":
            tmpl = "doctor_detail.html"
        elif p.category in ("event", "concert", "theater") and not (p.slug or "").startswith("film-"):
            tmpl = "event_detail.html"
        else:
            tmpl = "detail.html"
        return render_template(
            tmpl,
            place=d,
            similar=similar,
            venue_events=venue_events,
            staff=staff,
            staff_groups=staff_groups,
            hospital=hospital,
            units=units,
            reviews=[r.public() for r in reviews],
            dims=dims,
            my_review=my_review.public() if my_review else None,
            is_fav=is_fav,
            is_going=is_going,
            going_count=going_count,
            user_photos=user_photos,
            nav=p.category,
            seo=for_place(d),
        )
    finally:
        db.close()


@app.route("/yer/<slug>/yorum", methods=["POST"])
def yer_yorum(slug: str):
    from mail_verify import can_review
    from seo_urls import place_seo_path

    user = load_user()
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == slug, Place.status == "approved").first()
        if p is None:
            flash("Kayıt yok", "err")
            return redirect("/")
        dest = f"{place_seo_path(p)}#yorumlar"
        if user is None:
            flash("Yorum yapmak için üye olman gerekir.", "err")
            return redirect(f"/kayit?next={dest}")
        if not can_review(user):
            flash("Yorum için önce e-posta onayını tamamla — mailindeki linke bas.", "err")
            return redirect("/hesap/ayarlar")
        if not rate_ok("review", limit=20):
            flash("Çok sık deneme. Bir dakika bekle.", "err")
            return redirect(dest)
        if p.category == "doctor":
            flash("Doktor kayıtlarında değerlendirme kapalı.", "err")
            return redirect(place_seo_path(p))
        food = clamp_score(request.form.get("score_food"))
        service = clamp_score(request.form.get("score_service"))
        atmosphere = clamp_score(request.form.get("score_atmosphere"))
        price = clamp_score(request.form.get("score_price"))
        body = (request.form.get("body") or "").strip()[:2000]
        rev = db.query(Review).filter(Review.place_id == p.id, Review.user_id == user.id).first()
        if rev is None:
            rev = Review(place_id=p.id, user_id=user.id)
            db.add(rev)
        rev.score_food = food
        rev.score_service = service
        rev.score_atmosphere = atmosphere
        rev.score_price = price
        rev.body = body
        rev.status = "pending"  # admin onayı
        rev.updated_at = datetime.utcnow()
        f = request.files.get("photo")
        if f and f.filename:
            from admin_forms import save_upload

            url = save_upload(f, category="review")
            if url:
                rev.img_url = url
        db.flush()
        # puan yalnız onaylı yorumlardan — pending skoru etkilemez
        recompute_place_rating(db, p)
        db.commit()
        flash("Yorumun alındı — admin onayından sonra yayınlanır.", "ok")
        return redirect(dest)
    finally:
        db.close()


@app.route("/yer/<slug>/foto", methods=["POST"])
@login_required
def yer_foto(slug: str):
    """Kamp vb. yerlere üye fotoğrafı — admin onayı gerekir."""
    from admin_forms import save_upload
    from models import PlacePhoto

    user = load_user()
    if not rate_ok("place_photo", limit=15):
        flash("Çok sık deneme.", "err")
        return redirect(f"/yer/{slug}")
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == slug, Place.status == "approved").first()
        if not p:
            flash("Kayıt yok", "err")
            return redirect("/")
        if (p.slug or "").startswith("film-"):
            flash("Film sayfalarında üye fotoğrafı kapalı.", "err")
            from seo_urls import place_seo_path

            return redirect(place_seo_path(p))
        f = request.files.get("photo")
        caption = (request.form.get("caption") or "").strip()[:280]
        url = save_upload(f, category="place_photo") if f and f.filename else ""
        if not url:
            flash("Geçerli bir foto seç.", "err")
            return redirect(f"/yer/{slug}")
        db.add(PlacePhoto(place_id=p.id, user_id=user.id, img_url=url, caption=caption, status="pending"))
        db.commit()
        from seo_urls import place_seo_path

        flash("Fotoğraf alındı — onaydan sonra galeride görünür.", "ok")
        return redirect(place_seo_path(p) + "#galeri")
    finally:
        db.close()


@app.route("/giris", methods=["GET", "POST"])
def giris():
    if load_user():
        return redirect(request.args.get("next") or "/")
    err = ""
    if request.method == "POST":
        if not rate_ok("login", limit=10):
            err = "Çok sık deneme. Bir dakika bekle."
        else:
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            db = SessionLocal()
            try:
                u = db.query(User).filter(User.email == email).first()
                if u is None or not verify_password(password, u.password_hash):
                    err = "E-posta veya şifre yanlış."
                else:
                    login_user(u)
                    from models import log_activity

                    log_activity(
                        db,
                        kind="login",
                        title="Giriş yaptı",
                        detail=u.name or "",
                        user_id=u.id,
                        email=u.email,
                    )
                    db.commit()
                    return redirect(request.args.get("next") or request.form.get("next") or "/")
            finally:
                db.close()
    return render_template("auth.html", mode="giris", err=err, next=request.args.get("next") or "", nav="auth")


@app.route("/kayit", methods=["GET", "POST"])
def kayit():
    if load_user():
        return redirect("/")
    err = ""
    if request.method == "POST":
        if not rate_ok("register"):
            err = "Çok sık deneme. Bir dakika bekle."
        else:
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            name = (request.form.get("name") or "").strip()
            if "@" not in email or "." not in email:
                err = "Geçerli bir e-posta gir."
            elif len(password) < 8:
                err = "Şifre en az 8 karakter."
            elif len(name) < 2:
                err = "Ad en az 2 karakter."
            else:
                db = SessionLocal()
                try:
                    if db.query(User).filter(User.email == email).first():
                        err = "Bu e-posta zaten kayıtlı."
                    else:
                        u = User(
                            email=email,
                            password_hash=hash_password(password),
                            name=name,
                            role="user",
                            email_verified=False,
                            email_token="",
                        )
                        from mail_verify import VERIFY_DAYS, new_email_token, send_verify_email

                        u.email_token = new_email_token()
                        db.add(u)
                        db.flush()
                        from models import log_activity

                        log_activity(
                            db,
                            kind="register",
                            title="Yeni üye kaydı",
                            detail=name,
                            user_id=u.id,
                            email=email,
                        )
                        db.commit()
                        db.refresh(u)
                        try:
                            result = send_verify_email(email=email, name=name, token=u.email_token)
                        except Exception:
                            result = {"ok": False, "link": ""}
                        try:
                            from notify import notify_register

                            notify_register(name=name, email=email, user_id=u.id, source="web")
                        except Exception:
                            pass
                        login_user(u)
                        if result.get("ok"):
                            flash(
                                f"Kayıt tamam — e-postandaki onay linkine bas. "
                                f"{VERIFY_DAYS} gün içinde onaylamazsan üyelik iptal edilir.",
                                "ok",
                            )
                        else:
                            flash(
                                "Kayıt tamam ama onay maili gönderilemedi. "
                                "Biraz sonra Ayarlar’dan tekrar dene; spam klasörünü de kontrol et.",
                                "err",
                            )
                        return redirect("/hesap/profil")
                finally:
                    db.close()
    return render_template("auth.html", mode="kayit", err=err, next="", nav="auth")


@app.route("/cikis")
def cikis():
    logout_user()
    return redirect("/")


@app.route("/hesap")
@login_required
def hesap():
    user = load_user()
    db = SessionLocal()
    try:
        rows = db.query(Place).filter(Place.submitted_by_id == user.id).order_by(Place.id.desc()).all()
        u = db.get(User, user.id)
        return render_template("account.html", places=rows, points=u.loyalty_points if u else 0, nav="hesap")
    finally:
        db.close()


@app.route("/hesap/profil")
@login_required
def hesap_profil():
    from feed_social import (
        album_photos,
        build_feed,
        going_count,
        suggest_places,
        upcoming_events,
        _place_card,
        _ago,
    )
    from models import EventGoing, UserVisit

    user = load_user()
    tab = (request.args.get("tab") or "recents").strip().lower()
    if tab not in ("recents", "mine", "popular", "media", "visits", "reviews", "going"):
        tab = "recents"
    db = SessionLocal()
    try:
        u = db.get(User, user.id)
        if not u:
            flash("Oturum geçersiz", "err")
            return redirect("/giris")
        owner = u.id if tab in ("mine", "media", "visits", "reviews", "going") else None
        feed_tab = "mine" if tab == "mine" else ("popular" if tab == "popular" else "recents")
        feed = build_feed(db, viewer=u, owner_id=owner if tab == "mine" else (u.id if tab == "reviews" else None), tab=feed_tab)
        if tab == "recents":
            # kendi + public karışık: kendi id filtre yok
            feed = build_feed(db, viewer=u, owner_id=None, tab="recents")
        album = album_photos(db, u.id) if tab == "media" else []
        visits = []
        if tab == "visits":
            for v in db.query(UserVisit).filter(UserVisit.user_id == u.id).order_by(UserVisit.id.desc()).limit(80).all():
                p = db.get(Place, v.place_id)
                visits.append({"note": v.note, "ago": _ago(v.created_at), "place": _place_card(p)})
        goings = []
        going_n = db.query(EventGoing).filter(EventGoing.user_id == u.id).count()
        if tab == "going":
            for g in db.query(EventGoing).filter(EventGoing.user_id == u.id).order_by(EventGoing.id.desc()).all():
                p = db.get(Place, g.place_id)
                card = _place_card(p)
                goings.append(
                    {
                        "place": card,
                        "going": going_count(db, g.place_id),
                        "starts_at": p.starts_at.strftime("%d.%m.%Y %H:%M") if p and p.starts_at else "",
                    }
                )
        visit_places = []
        for v in db.query(UserVisit).filter(UserVisit.user_id == u.id).order_by(UserVisit.id.desc()).limit(30).all():
            p = db.get(Place, v.place_id)
            if p:
                visit_places.append(_place_card(p))
        return render_template(
            "profile_feed.html",
            u=u,
            tab=tab,
            feed=feed,
            album=album,
            visits=visits,
            goings=goings,
            going_n=going_n,
            suggest=suggest_places(db, 6),
            events=upcoming_events(db, 8),
            visit_places=visit_places,
            nav="hesap",
        )
    finally:
        db.close()


@app.route("/hesap/ayarlar", methods=["GET", "POST"])
@login_required
def hesap_ayarlar():
    from admin_forms import save_upload

    user = load_user()
    db = SessionLocal()
    try:
        u = db.get(User, user.id)
        if not u:
            flash("Oturum geçersiz", "err")
            return redirect("/giris")
        if request.method == "POST":
            action = (request.form.get("action") or "").strip()
            if action == "avatar":
                f = request.files.get("avatar")
                path = save_upload(f, category="avatar") if f and f.filename else ""
                if not path:
                    flash("Geçerli bir görsel seç.", "err")
                else:
                    u.avatar_url = path
                    db.commit()
                    flash("Profil fotoğrafı güncellendi.", "ok")
            elif action == "display_name":
                u.show_full_name = request.form.get("show_full_name") == "1"
                db.commit()
                flash("İsim görünümü kaydedildi.", "ok")
            elif action == "password":
                cur = request.form.get("current_password") or ""
                new = request.form.get("new_password") or ""
                new2 = request.form.get("new_password2") or ""
                if not verify_password(cur, u.password_hash):
                    flash("Mevcut şifre yanlış.", "err")
                elif len(new) < 8:
                    flash("Yeni şifre en az 8 karakter.", "err")
                elif new != new2:
                    flash("Yeni şifreler eşleşmiyor.", "err")
                else:
                    u.password_hash = hash_password(new)
                    db.commit()
                    flash("Şifre güncellendi.", "ok")
            elif action == "resend_verify":
                from mail_verify import new_email_token, send_verify_email

                if u.email_verified:
                    flash("E-posta zaten onaylı.", "ok")
                else:
                    u.email_token = new_email_token()
                    db.commit()
                    result = send_verify_email(email=u.email, name=u.name, token=u.email_token)
                    if result.get("ok"):
                        flash("Onay maili gönderildi. Gelen kutusu ve spam klasörünü kontrol et.", "ok")
                    else:
                        flash(
                            "Onay maili gönderilemedi. Biraz sonra tekrar dene; sorun sürerse destekten yaz.",
                            "err",
                        )
            return redirect("/hesap/ayarlar")
        return render_template("profile_settings.html", u=u, nav="hesap")
    finally:
        db.close()


@app.route("/hesap/profil/post", methods=["POST"])
@login_required
def hesap_profil_post():
    from admin_forms import save_upload
    from feed_social import set_post_images
    from models import PlacePhoto, UserPost, UserVisit

    user = load_user()
    if not rate_ok("feed_post", limit=20):
        flash("Çok sık post.", "err")
        return redirect("/hesap/profil")
    body = (request.form.get("body") or "").strip()[:2000]
    privacy = (request.form.get("privacy") or "public").strip()
    if privacy not in ("public", "private"):
        privacy = "public"
    place_slug = (request.form.get("place_slug") or "").strip()
    also_visit = request.form.get("also_visit") == "1"
    db = SessionLocal()
    try:
        place = None
        if place_slug:
            place = db.query(Place).filter(Place.slug == place_slug, Place.status == "approved").first()
        urls = []
        files = request.files.getlist("photos") or []
        for f in files[:6]:
            if f and f.filename:
                url = save_upload(f, category="feed")
                if url:
                    urls.append(url)
                    if place:
                        db.add(
                            PlacePhoto(
                                place_id=place.id,
                                user_id=user.id,
                                img_url=url,
                                caption=(body[:280] if body else ""),
                                status="pending",
                            )
                        )
        if not body and not urls:
            flash("Metin veya foto ekle.", "err")
            return redirect("/hesap/profil")
        post = UserPost(user_id=user.id, place_id=place.id if place else None, body=body, privacy=privacy)
        set_post_images(post, urls)
        db.add(post)
        if also_visit and place:
            vis = db.query(UserVisit).filter(UserVisit.user_id == user.id, UserVisit.place_id == place.id).first()
            if not vis:
                db.add(UserVisit(user_id=user.id, place_id=place.id, note=body[:280]))
            else:
                if body:
                    vis.note = body[:280]
        db.commit()
        flash("Gönderi paylaşıldı." + (" Fotoğraflar yer galerisi için onaya düştü." if urls and place else ""), "ok")
        return redirect("/hesap/profil?tab=mine")
    finally:
        db.close()


@app.route("/hesap/profil/ziyaret", methods=["POST"])
@login_required
def hesap_profil_ziyaret():
    from models import UserVisit

    user = load_user()
    q = (request.form.get("place_q") or "").strip()
    note = (request.form.get("note") or "").strip()[:280]
    db = SessionLocal()
    try:
        place = db.query(Place).filter(Place.slug == q, Place.status == "approved").first()
        if not place and q:
            like = f"%{q}%"
            place = (
                db.query(Place)
                .filter(Place.status == "approved", Place.title.ilike(like))
                .order_by(Place.id.desc())
                .first()
            )
        if not place:
            flash("Yer bulunamadı — slug veya başlık yaz.", "err")
            return redirect("/hesap/profil?tab=visits")
        vis = db.query(UserVisit).filter(UserVisit.user_id == user.id, UserVisit.place_id == place.id).first()
        if vis:
            if note:
                vis.note = note
            flash("Zaten listende — not güncellendi." if note else "Zaten gittiğin yerlerde.", "ok")
        else:
            db.add(UserVisit(user_id=user.id, place_id=place.id, note=note))
            flash(f"{place.title} eklendi.", "ok")
        db.commit()
        return redirect("/hesap/profil?tab=visits")
    finally:
        db.close()


@app.route("/hesap/profil/like/<int:post_id>", methods=["POST"])
@login_required
def hesap_profil_like(post_id: int):
    from models import PostLike, UserPost

    user = load_user()
    db = SessionLocal()
    try:
        post = db.get(UserPost, post_id)
        if not post:
            flash("Gönderi yok", "err")
            return redirect("/hesap/profil")
        like = db.query(PostLike).filter(PostLike.user_id == user.id, PostLike.post_id == post_id).first()
        if like:
            db.delete(like)
            post.likes_count = max(0, int(post.likes_count or 0) - 1)
        else:
            db.add(PostLike(user_id=user.id, post_id=post_id))
            post.likes_count = int(post.likes_count or 0) + 1
        db.commit()
        return redirect(request.referrer or "/hesap/profil")
    finally:
        db.close()


@app.route("/yer/<slug>/gidecegim", methods=["POST"])
@login_required
def yer_gidecegim(slug: str):
    from feed_social import EVENT_CATS, going_count
    from models import EventGoing
    from seo_urls import place_seo_path

    user = load_user()
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == slug, Place.status == "approved").first()
        if not p:
            flash("Kayıt yok", "err")
            return redirect("/")
        if p.category not in EVENT_CATS and p.category not in ("camp", "fun"):
            # etkinlik + kamp/eğlence de olsun
            pass
        row = db.query(EventGoing).filter(EventGoing.user_id == user.id, EventGoing.place_id == p.id).first()
        if row:
            db.delete(row)
            db.commit()
            flash(f"Listeden çıktın. Gidecek: {going_count(db, p.id)}", "ok")
        else:
            db.add(EventGoing(user_id=user.id, place_id=p.id))
            db.commit()
            flash(f"Gideceğim kaydedildi. Toplam gidecek: {going_count(db, p.id)}", "ok")
        return redirect(place_seo_path(p))
    finally:
        db.close()


@app.route("/hesap/email-onay")
def hesap_email_onay():
    token = (request.args.get("token") or "").strip()
    if not token:
        flash("Geçersiz onay linki.", "err")
        return redirect("/giris")
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email_token == token).first()
        if not u:
            flash("Link geçersiz veya kullanılmış.", "err")
            return redirect("/giris")
        u.email_verified = True
        u.email_token = ""
        db.commit()
        login_user(u)
        flash("E-posta onaylandı. Teşekkürler!", "ok")
        return redirect("/hesap")
    finally:
        db.close()


@app.route("/hesap/favoriler")
@login_required
def hesap_favoriler():
    user = load_user()
    db = SessionLocal()
    try:
        from models import Favorite
        favs = db.query(Favorite).filter(Favorite.user_id == user.id).order_by(Favorite.id.desc()).all()
        places = []
        for f in favs:
            p = db.get(Place, f.place_id)
            if p and p.status == "approved":
                places.append(place_public(p))
        return render_template("favorites.html", places=places, nav="hesap")
    finally:
        db.close()


@app.route("/hesap/rotalar")
@login_required
def hesap_rotalar():
    user = load_user()
    db = SessionLocal()
    try:
        from models import SavedRoute
        import json as _json
        rows = db.query(SavedRoute).filter(SavedRoute.user_id == user.id).order_by(SavedRoute.id.desc()).all()
        items = []
        for r in rows:
            try:
                slots = _json.loads(r.slots_json or "[]")
            except Exception:
                slots = []
            items.append({"route": r, "slots": slots})
        return render_template("saved_routes.html", items=items, nav="hesap")
    finally:
        db.close()


@app.route("/hesap/ekle", methods=["GET", "POST"])
@login_required
def ekle():
    user = load_user()
    err = ""
    if request.method == "POST":
        if not rate_ok("submit"):
            err = "Çok sık deneme. Bir dakika bekle."
        else:
            title = (request.form.get("title") or "").strip()
            cat = (request.form.get("category") or "").strip()
            starts = parse_dt(request.form.get("starts_at"))
            if not title:
                err = "Başlık gerekli."
            elif cat not in CAT_BY_KEY:
                err = "Kategori seç."
            elif cat == "event" and not starts:
                err = "Etkinlikte tarih zorunlu."
            else:
                db = SessionLocal()
                try:
                    p = Place(
                        title=title,
                        slug=unique_slug(db, title),
                        category=cat,
                        subcategory=(request.form.get("subcategory") or "").strip(),
                        ilce=(request.form.get("ilce") or "").strip(),
                        address=(request.form.get("address") or "").strip(),
                        phone=(request.form.get("phone") or "").strip(),
                        web=(request.form.get("web") or "").strip(),
                        hours_text=(request.form.get("hours_text") or "").strip(),
                        price_band=(request.form.get("price_band") or "").strip(),
                        blurb=(request.form.get("blurb") or "").strip(),
                        body=(request.form.get("body") or "").strip(),
                        img_url=(request.form.get("img_url") or "").strip(),
                        venue_name=(request.form.get("venue_name") or "").strip(),
                        tags=tags_dump(request.form.get("tags") or ""),
                        starts_at=starts,
                        ends_at=parse_dt(request.form.get("ends_at")),
                        status="pending",
                        submitted_by_id=user.id,
                    )
                    db.add(p)
                    db.flush()
                    from models import log_activity

                    log_activity(
                        db,
                        kind="place_submit",
                        title=f"Yeni yer: {title}",
                        detail=f"{cat} · {p.slug}",
                        user_id=user.id,
                        email=getattr(user, "email", "") or "",
                        meta={"place_id": p.id, "category": cat},
                    )
                    db.commit()
                    flash("Gönderildi. Onay bekliyor — sitede henüz görünmez.", "ok")
                    return redirect("/hesap")
                finally:
                    db.close()
    return render_template("submit.html", err=err, nav="ekle", preset=request.args.get("cat") or "")


@app.route("/categories")
def legacy_categories():
    return redirect("/", 301)


@app.route("/events")
def legacy_events():
    return redirect("/etkinlikler", 301)


@app.route("/places")
def legacy_places():
    return redirect("/gezilecek", 301)


@app.route("/api/places")
@app.route("/api/bursa/places")
def api_places_legacy():
    q = request.args.get("q")
    tab = (request.args.get("tab") or "").strip()
    cat = "food" if tab == "yemek" else None
    db = SessionLocal()
    try:
        rows, _ = query_places(db, category=cat, q=q, limit=60)
        return jsonify({"ok": True, "places": [place_public(p) for p in rows]})
    finally:
        db.close()


def main() -> None:
    host = os.environ.get("BURSAAPP_HOST", "127.0.0.1")
    port = int(os.environ.get("BURSAAPP_PORT", "5051"))
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
