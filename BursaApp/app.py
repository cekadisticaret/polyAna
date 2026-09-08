#!/usr/bin/env python3
"""BursaApp — şehir rehberi. Üye ekler, admin onaylar. Port 5051, 127.0.0.1."""
from __future__ import annotations

import calendar
import os
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, Response

from admin import bp as admin_bp
from api_v1 import bp as api_v1_bp
from features import bp as features_bp
from features import hub_context, _active_campaigns, active_campaign_for_place
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
    FOOD_CUISINE,
    FOOD_CURATED,
    FOOD_DISH,
    FOOD_KIND,
    FOOD_MEAL,
    FOOD_PRICE,
    GROUP_BAND,
    GROUP_ILCE,
    ILCELER,
    KIND_BY_CAT,
    MEKAN_TAXONOMY,
    VISIT_FEE,
    VISIT_KIND,
    VISIT_TAG,
    food_matches,
    food_price_marks,
    visit_fee_tier,
    visit_matches,
    hospital_staff_groups,
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


def _static_asset_v() -> str:
    """CSS/JS cache-bust — dosya mtime değişince tarayıcı yeni sürümü çeker."""
    mt = 0
    for name in ("app.css", "seo-pages.css", "utilities-pages.css", "nearby-explore.css", "nearby-explore.js"):
        try:
            mt = max(mt, int(os.path.getmtime(os.path.join(_DIR, "static", name))))
        except OSError:
            pass
    return str(mt or 1)
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
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.register_blueprint(api_v1_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(features_bp)

init_db()


def _mobile_tab() -> str:
    """Alt sekme çubuğu — keşif odaklı mobil rotalar."""
    path = request.path or ""
    if path in ("/", "/etrafimda") or path.startswith("/harita"):
        return "home"
    if path.startswith("/feed"):
        return "feed"
    if path.startswith("/rota"):
        return "route"
    if path.startswith("/kategoriler") or path.startswith("/gezilecek") or path.startswith("/yeme-icme"):
        return "explore"
    if path.startswith("/hesap") or path.startswith("/giris") or path.startswith("/kayit"):
        return "profile"
    return ""


def _wants_json() -> bool:
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json"


@app.errorhandler(413)
def _upload_too_large(_e):
    flash("Dosya çok büyük (en fazla 12 MB). Daha küçük bir fotoğraf dene.", "err")
    return redirect(request.referrer or "/hesap/ayarlar")


@app.errorhandler(404)
def _not_found(_e):
    from seo import page as seo_page

    path = request.path or "/404"
    seo = seo_page(
        title="Sayfa bulunamadı",
        description="Aradığınız sayfa BursaApp rehberinde yok. Ana sayfa veya kategorilerden devam edin.",
        path=path,
        noindex=True,
        breadcrumbs=[("Ana Sayfa", "/"), ("Sayfa bulunamadı", path)],
    )
    return render_template("404.html", nav="", seo=seo), 404


_TESSEKKUR = {
    "email": {
        "title": "E-posta onaylandı",
        "subtitle": "Hesabın aktif",
        "body": "Teşekkürler — artık yorum yazabilir, favorilerini kaydedebilir ve profilini düzenleyebilirsin.",
        "next": "/hesap/profil",
        "next_label": "Profilim",
        "hint": "",
    },
    "kayit": {
        "title": "Kayıt tamam",
        "subtitle": "Hoş geldin",
        "body": "Üyeliğin oluşturuldu. E-postandaki onay linkine bas; onayladıktan sonra yorum yazabilirsin.",
        "next": "/hesap/ayarlar",
        "next_label": "E-posta ayarları",
        "hint": "Mail gelmediyse spam klasörünü kontrol et veya ayarlardan tekrar gönder.",
    },
    "sahiplen": {
        "title": "Talebin alındı",
        "subtitle": "İnceleniyor",
        "body": "Sahiplenme belgelerin admin ekibine iletildi. Sonuç e-posta veya bildirimle paylaşılacak.",
        "next": "",
        "next_label": "Devam et",
        "hint": "",
    },
    "yorum": {
        "title": "Yorum gönderildi",
        "subtitle": "Onay bekliyor",
        "body": "Değerlendirmen alındı. Admin onayından sonra yer sayfasında yayınlanacak.",
        "next": "",
        "next_label": "Yer sayfasına dön",
        "hint": "",
    },
    "default": {
        "title": "Teşekkürler",
        "subtitle": "İşlem tamam",
        "body": "Talebin kaydedildi. BursaApp rehberinde keşfe devam edebilirsin.",
        "next": "/",
        "next_label": "Ana sayfa",
        "hint": "",
    },
}


@app.route("/tesekkur")
def tesekkur_page():
    from seo import for_tesekkur

    kind = (request.args.get("from") or "default").strip().lower()
    row = _TESSEKKUR.get(kind) or _TESSEKKUR["default"]
    nxt = _safe_next(request.args.get("next"), row.get("next") or "")
    if not nxt and row.get("next"):
        nxt = row["next"]
    next_label = (request.args.get("label") or row.get("next_label") or "Devam et").strip()[:40]
    return render_template(
        "tesekkur.html",
        nav="",
        seo=for_tesekkur(),
        tks_title=row["title"],
        tks_subtitle=row["subtitle"],
        tks_body=row["body"],
        tks_next=nxt,
        tks_next_label=next_label,
        tks_hint=row.get("hint") or "",
    )


@app.context_processor
def _inject():
    from seo import resolve_seo, site_base
    from seo_arch import HOME_FAQ, HOME_HOWTO, PHONE_DISPLAY, PHONE_E164, VERTICALS, WHATSAPP_URL
    from seo_status import ga_measurement_id, google_ads_id, google_verification_token
    from mail_verify import VERIFY_DAYS, can_review, verify_banner
    from admin_permissions import can_access_panel

    user = load_user()
    path = request.path or "/"
    return {
        "nav_user": user,
        "can_admin_panel": can_access_panel(user),
        "can_review": can_review(user),
        "email_verify_banner": verify_banner(user),
        "verify_days": VERIFY_DAYS,
        "categories": CATEGORIES,
        "ilceler": ILCELER,
        "mekan_taxonomy": MEKAN_TAXONOMY,
        "google_site_verification": google_verification_token(),
        "ga_measurement_id": ga_measurement_id(),
        "google_ads_id": google_ads_id(),
        "site_url": site_base(),
        "seo": resolve_seo(),
        "home_faq": HOME_FAQ,
        "home_howto": HOME_HOWTO,
        "seo_vertical": VERTICALS.get(path),
        "wa_phone": PHONE_DISPLAY,
        "wa_url": WHATSAPP_URL,
        "phone_e164": PHONE_E164,
        "static_v": _static_asset_v(),
        "mobile_tab": _mobile_tab(),
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
    if path.startswith("/sitemap") or path in (
        "/favicon.ico",
        "/robots.txt",
        "/llms.txt",
        "/llms-full.txt",
    ) or path.startswith("/.well-known/"):
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
    from ai_seo import robots_txt_body

    return Response(robots_txt_body(), mimetype="text/plain; charset=utf-8")


@app.route("/llms.txt")
@app.route("/.well-known/llms.txt")
def llms_txt():
    from models import SessionLocal

    from ai_seo import llms_txt as _llms

    db = SessionLocal()
    try:
        body = _llms(db)
    finally:
        db.close()
    return Response(body, mimetype="text/plain; charset=utf-8")


@app.route("/llms-full.txt")
def llms_full_txt():
    from models import SessionLocal

    from ai_seo import llms_full_txt as _full

    db = SessionLocal()
    try:
        body = _full(db)
    finally:
        db.close()
    return Response(body, mimetype="text/plain; charset=utf-8")


@app.route("/sitemap.xml")
def sitemap_xml():
    """Sitemap index — Search Console'a bu URL verilir."""
    from seo import render_sitemap_index

    return Response(
        render_sitemap_index(
            [
                "/sitemap-pages.xml",
                "/sitemap-news.xml",
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


@app.route("/sitemap-news.xml")
def sitemap_news():
    from news_pages import load_news_feed, decorate_article
    from seo import abs_url, render_urlset

    feed = load_news_feed()
    entries = [
        {
            "loc": abs_url("/haberler"),
            "changefreq": "hourly",
            "priority": "0.95",
            "lastmod": feed.get("generated_at"),
        }
    ]
    for raw in feed.get("articles") or []:
        art = decorate_article(raw)
        entries.append(
            {
                "loc": abs_url(art["path"]),
                "changefreq": "daily",
                "priority": "0.82",
                "lastmod": raw.get("published_at") or feed.get("generated_at"),
            }
        )
    return Response(render_urlset(entries), mimetype="application/xml; charset=utf-8")


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
def home():
    q = (request.args.get("q") or "").strip()
    db = SessionLocal()
    try:
        hub = hub_context(db)
        from blog_posts import all_blog_posts, blog_posts_sorted

        featured, _ = query_places(db, category="visit", featured=True, q=q or None, limit=8)
        if len(featured) < 8:
            extra, _ = query_places(db, category="visit", q=q or None, order="rating", limit=16)
            seen = {p.id for p in featured}
            for p in extra:
                if p.id not in seen:
                    featured.append(p)
                if len(featured) >= 8:
                    break
        place_count = db.query(Place).filter(Place.status == "approved").count()
        cal = _cal(_month_shows(db))
        from seo import for_home
        from blog_posts import all_blog_posts, blog_posts_sorted
        from news_pages import headline_articles

        return render_template(
            "home.html",
            featured=[place_public(p) for p in featured],
            news_headlines=headline_articles(limit=4),
            q=q,
            weather=_weather(),
            ilce_n=len(ILCELER),
            place_count=place_count,
            nav="kesfet",
            seo=for_home(),
            blog_teasers=blog_posts_sorted()[:4],
            blog_total=len(all_blog_posts()),
            **hub,
            **cal,
        )
    finally:
        db.close()


@app.route("/kesfet")
def kesfet_redirect():
    return redirect("/", 301)


@app.route("/kategoriler")
def kategoriler_page():
    from catalog import CAT_ICONS, category_promo_cards

    return render_template(
        "mobile_categories.html",
        cat_ico=CAT_ICONS,
        promo_cards=category_promo_cards(),
        nav="categories",
    )


@app.route("/feed")
def feed_page():
    from feed_social import (
        FEED_PAGE_SIZE,
        build_feed,
        feed_picker_places,
        follow_counts,
        profile_feed,
        suggest_follow_users,
        upcoming_events,
    )

    user = load_user()
    tab = (request.args.get("tab") or "recents").strip().lower()
    if tab not in ("recents", "friends", "popular"):
        tab = "recents"
    if tab == "friends" and not user:
        tab = "recents"
    db = SessionLocal()
    try:
        if user:
            u = db.get(User, user.id)
            if not u:
                return redirect("/giris?next=/feed")
            feed, feed_has_more = profile_feed(db, u, tab, limit=FEED_PAGE_SIZE, offset=0)
            picker_places = feed_picker_places(db, u.id, limit=20)
            follow_suggestions = suggest_follow_users(db, u.id, limit=5)
            social_counts = follow_counts(db, u.id)
        else:
            u = None
            feed, feed_has_more = build_feed(db, viewer=None, tab=tab, limit=FEED_PAGE_SIZE, offset=0)
            picker_places = []
            follow_suggestions = []
            social_counts = {"following": 0, "followers": 0}
        events = upcoming_events(db, 6)
        resp = app.make_response(
            render_template(
                "mobile_feed.html",
                u=u,
                tab=tab,
                feed=feed,
                feed_has_more=feed_has_more,
                picker_places=picker_places,
                follow_suggestions=follow_suggestions,
                social_counts=social_counts,
                events=events,
                nav="feed",
            )
        )
        resp.headers["Cache-Control"] = "private, no-store"
        return resp
    finally:
        db.close()


@app.route("/blog")
def blog_hub():
    from seo import for_blog_hub
    from blog_posts import BLOG_KINDS, all_blog_posts, blog_posts_sorted

    kind = (request.args.get("kind") or "").strip()
    if kind and kind not in BLOG_KINDS:
        kind = ""
    all_posts = all_blog_posts()
    kind_counts: dict[str, int] = {}
    for p in all_posts.values():
        k = p.get("kind") or ""
        if k:
            kind_counts[k] = kind_counts.get(k, 0) + 1
    posts = blog_posts_sorted(kind=kind or None)
    return render_template(
        "blog/index.html",
        posts=posts,
        total_all=len(all_posts),
        kind_filter=kind,
        kind_counts=kind_counts,
        blog_kinds=BLOG_KINDS,
        nav="blog",
        seo=for_blog_hub(),
    )


@app.route("/blog/<slug>")
def blog_post(slug: str):
    from seo import for_blog_post
    from blog_posts import BLOG_KINDS, all_blog_posts

    post = all_blog_posts().get(slug)
    seo = for_blog_post(slug)
    if not post or not seo:
        return redirect("/blog")
    return render_template(
        "blog/post.html",
        slug=slug,
        post=post,
        blog_kinds=BLOG_KINDS,
        nav="blog",
        seo=seo,
    )


@app.route("/haberler")
def news_index():
    from news_pages import NEWS_TOPICS, list_articles, load_bursaspor_sidebar, load_videos
    from seo import for_news_hub

    topic = (request.args.get("konu") or "").strip()
    q = (request.args.get("q") or "").strip()
    page = max(1, int(request.args.get("page") or 1))
    articles, total, meta = list_articles(topic=topic, q=q, page=page, per_page=24)
    videos = load_videos()
    return render_template(
        "news_index.html",
        articles=articles,
        total=total,
        meta=meta,
        topic=topic if topic in NEWS_TOPICS else "",
        topics=NEWS_TOPICS,
        q=q,
        bursaspor=load_bursaspor_sidebar(),
        videos=videos,
        featured_video=videos[0] if videos else None,
        nav="news",
        seo=for_news_hub(total=total, topic=topic, articles=articles),
    )


@app.route("/haber/<slug>")
def news_detail(slug: str):
    from news_pages import (
        NEWS_TOPICS,
        get_article,
        headline_articles,
        load_bursaspor_sidebar,
        load_videos,
        match_video,
        reading_minutes,
        related_articles,
        videos_for_topic,
    )
    from seo import for_news_article

    article = get_article(slug)
    if not article:
        return redirect("/haberler")
    videos = load_videos()
    video = match_video(article, videos)
    topic_videos = videos_for_topic(
        article.get("topic") or "genel",
        limit=4,
        exclude_id=(video or {}).get("id") or "",
    )
    related = related_articles(article, limit=6)
    latest = [a for a in headline_articles(limit=10) if a.get("id") != article.get("id")][:7]
    bursaspor = load_bursaspor_sidebar()
    seo = for_news_article(article, video=video)
    if not seo:
        return redirect("/haberler")
    return render_template(
        "news_detail.html",
        article=article,
        video=video,
        topic_videos=topic_videos,
        related=related,
        latest=latest,
        topics=NEWS_TOPICS,
        bursaspor=bursaspor,
        read_mins=reading_minutes(article),
        nav="news",
        seo=seo,
    )


@app.route("/kvkk")
def kvkk_page():
    from seo import for_kvkk

    return render_template("kvkk.html", nav="kvkk", seo=for_kvkk())


@app.route("/iletisim")
def iletisim_page():
    from seo import for_iletisim

    return render_template("iletisim.html", nav="iletisim", seo=for_iletisim())


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
    ilce = ""
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
    """Veteriner listesi — eczane tarzı hero + ince liste."""
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
            places = [_decorate_health_row(p) for p in data["places"]]
            total = len(places)
            groups = [{"label": "Yakınında", "places": places}] if places else []
            page_sub = (
                f"Konumuna göre · {lat:.4f}, {lng:.4f}"
                if not used_fallback
                else "Konum alınamadı — Osmangazi merkez"
            )
        else:
            rows, total = query_places(
                db,
                category="vet",
                ilce=ilce or None,
                subcategory=sub or None,
                order="rating",
                limit=500,
            )
            places = [place_public(p) for p in rows]
            groups = _health_ilce_groups(places)
            page_sub = "Oda kayıtlı klinik ve hayvan hastanesi — randevu siteden yok"

        ozel_n = sum(1 for g in groups for p in g["places"] if (p.get("price_band") or "") == "Hastane")
        return _render_health_page(
            nav="vet",
            page_title="Veterinerler",
            page_sub=page_sub,
            hero_theme="vet",
            hero_art="health/vet.svg",
            hero_kicker="Evcil hayvan sağlığı",
            hero_headline="Bursa veteriner klinikleri",
            hero_desc=f"{total} kayıtlı klinik · ilçene göre filtrele, ara veya yol tarifi al.",
            stat1_label="klinik",
            stat2_value=len(groups),
            stat2_label="bölüm",
            stat3_value=ozel_n or "7/24",
            stat3_label="hastane" if ozel_n else "acil (ilan)",
            row_kind="vet",
            row_unit="klinik",
            total=total,
            groups=groups,
            base_path="/veterinerler",
            ilce=ilce,
            sub=sub,
            filter_items=list(ILCELER) if tab == "hepsi" else None,
            filter_param="ilce",
            filter_label="Bölge",
            filter_on=ilce,
            show_geo_bar=tab == "hepsi",
            geo_script=True,
            geo_near_url="/veterinerler?tab=yakin",
            hero_note="Kaynak Bursa Veteriner Hekimler Odası kayıtlı işletmeler",
            empty_text="Bu filtrede veteriner yok.",
            seo=for_category(cat, ilce=ilce, sub=sub, total=total, places=[p for g in groups for p in g["places"]]),
        )
    finally:
        db.close()


@app.route("/dis-hekimleri")
def dis_hekimleri():
    """Diş hekimleri — ADSM, klinik ve Dt. kadrosu."""
    from seo import for_category

    cat = CAT_BY_KEY["dentist"]
    ilce = (request.args.get("ilce") or "").strip()
    band = (request.args.get("band") or "").strip()
    db = SessionLocal()
    try:
        clinics, _ = query_places(db, category="dentist", ilce=ilce or None, order="rating", limit=500)
        docs_dis, _ = query_places(db, category="doctor", price_band="Diş", ilce=ilce or None, limit=200)
        docs_dh, _ = query_places(
            db, category="doctor", price_band="Diş hekimi", ilce=ilce or None, limit=200
        )
        seen_doc: set[int] = set()
        docs = []
        for p in docs_dis + docs_dh:
            if p.id in seen_doc:
                continue
            seen_doc.add(p.id)
            docs.append(p)
        places = [place_public(p) for p in clinics] + [place_public(p) for p in docs]
        if band:
            places = [p for p in places if (p.get("price_band") or "") == band]
        places.sort(
            key=lambda p: (
                0 if p.get("featured") else 1,
                0 if (p.get("price_band") or "") == "Devlet" else 1,
                -(float(p["rating"]) if p.get("rating") is not None else -1.0),
                p.get("title") or "",
            )
        )
        total = len(places)
        _attach_hospital_titles(db, places)
        groups = _health_ilce_groups(places)
        devlet_n = sum(1 for p in places if (p.get("price_band") or "") == "Devlet")
        return _render_health_page(
            nav="dentist",
            page_title="Diş hekimleri",
            page_sub="ADSM, özel klinik ve hastane diş hekimleri · MHRS / randevu",
            hero_theme="dentist",
            hero_art="health/dentist.svg",
            hero_kicker="Ağız ve diş sağlığı",
            hero_headline="Bursa diş hekimleri",
            hero_desc=f"{total} hekim ve klinik · devlet ADSM veya özel poliklinik.",
            stat1_label="kayıt",
            stat2_value=len(groups),
            stat2_label="ilçe",
            stat3_value=devlet_n or "MHRS",
            stat3_label="ADSM" if devlet_n else "randevu",
            row_kind="dentist",
            row_unit="kayıt",
            total=total,
            groups=groups,
            base_path="/dis-hekimleri",
            ilce=ilce,
            band_on=band,
            band_chips=_DENTIST_BANDS,
            filter_items=list(ILCELER),
            filter_param="ilce",
            filter_label="Bölge",
            filter_on=ilce,
            hero_note="Devlet ADSM · MHRS / 182 · Özel klinikler randevu ile",
            empty_text="Bu filtrede diş hekimi / klinik yok.",
            seo=for_category(cat, ilce=ilce, sub=band, total=total, places=places),
        )
    finally:
        db.close()


@app.route("/okullar")
def okullar():
    """Okullar — devlet / özel / üniversite + kademe filtresi."""
    from catalog import subcategories_for
    from seo import for_category

    cat = CAT_BY_KEY["school"]
    ilce = (request.args.get("ilce") or "").strip()
    band = (request.args.get("band") or "").strip()
    sub = (request.args.get("sub") or "").strip()
    db = SessionLocal()
    try:
        rows, _ = query_places(
            db,
            category="school",
            ilce=ilce or None,
            price_band=band or None,
            subcategory=sub or None,
            order="title",
            limit=600,
        )
        places = [_decorate_health_row(place_public(p)) for p in rows]
        total = len(places)
        groups = _health_ilce_groups(places)
        devlet_n = sum(1 for p in places if (p.get("price_band") or "") == "Devlet")
        ozel_n = sum(1 for p in places if (p.get("price_band") or "") == "Özel")
        sub_chips = subcategories_for("school")
        return _render_health_page(
            nav="school",
            page_title="Okullar",
            page_sub="Okul, dershane, özel eğitim · kayıt, etkinlik ve iletişim",
            hero_theme="school",
            hero_art="health/school.svg",
            hero_kicker="Eğitim rehberi",
            hero_headline="Bursa okulları",
            hero_desc=f"{total} kurum · okul, dershane, özel eğitim, kolej ve üniversite.",
            stat1_label="okul",
            stat2_value=len(groups),
            stat2_label="ilçe",
            stat3_value=ozel_n,
            stat3_label="özel",
            row_kind="school",
            row_unit="okul",
            total=total,
            groups=groups,
            base_path="/okullar",
            ilce=ilce,
            band_on=band,
            band_chips=_SCHOOL_BANDS,
            sub=sub,
            sub_chips=sub_chips,
            filter_items=list(ILCELER),
            filter_param="ilce",
            filter_label="İlçe",
            filter_on=ilce,
            hero_note=f"Devlet {devlet_n} · Özel {ozel_n} · OSM + resmi kaynak birleşimi",
            empty_text="Bu filtrede okul yok.",
            seo=for_category(cat, ilce=ilce, sub=sub or band, total=total, places=places),
        )
    finally:
        db.close()


_RX_MONTHS = (
    "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split()
)


def _rx_hours_short(text: str) -> str:
    import re as _re

    times = _re.findall(r"(\d{1,2}:\d{2})", text or "")
    if len(times) >= 2:
        return f"{times[0]} – {times[-1]}"
    return (text or "").strip()


def _rx_duty_label(feed: dict) -> str:
    raw = (feed.get("duty_date") or "").strip()[:10]
    if not raw:
        return ""
    try:
        from datetime import datetime as _dt

        d = _dt.strptime(raw, "%Y-%m-%d")
        return f"{d.day} {_RX_MONTHS[d.month - 1]} {d.year}"
    except Exception:
        return raw


def _decorate_rx(p: dict) -> dict:
    out = dict(p)
    name = (out.get("name") or "Eczane").strip()
    out["hours_short"] = _rx_hours_short(out.get("hours_text") or "")
    out["initial"] = name[0].upper()
    return out


def _rx_with_distance(items: list[dict], lat: float, lng: float) -> list[dict]:
    from discover import haversine_m

    out: list[dict] = []
    for p in items:
        d = dict(p)
        plat, plng = d.get("lat"), d.get("lng")
        if plat is None or plng is None:
            d["distance_m"] = None
        else:
            dm = int(round(haversine_m(lat, lng, float(plat), float(plng))))
            d["distance_m"] = dm
            d["walk_min"] = max(1, int(round(dm / 80)))
        out.append(d)
    out.sort(key=lambda x: (x.get("distance_m") is None, x.get("distance_m") or 10**9))
    return out


def _rx_distance_label(distance_m: int | None) -> str:
    if distance_m is None:
        return ""
    if distance_m < 1000:
        return f"{distance_m} m"
    return f"{distance_m / 1000:.1f} km"


def _health_initial(title: str) -> str:
    for ch in (title or "").strip():
        if ch.isalpha():
            return ch.upper()
    return "?"


def _decorate_health_row(p: dict) -> dict:
    out = dict(p)
    out["initial"] = _health_initial(out.get("title") or out.get("name"))
    out["hours_short"] = _rx_hours_short(out.get("hours_text") or "")
    return out


def _health_card_groups(places: list[dict], *, by: str = "ilce") -> list[dict]:
    """Kart listesi grupları — hastane: ilçe · doktor: branş."""
    by_map: dict[str, list] = {}
    if by == "spec":
        for p in places:
            by_map.setdefault(p.get("price_band") or "Diğer", []).append(p)
        order = list(DOCTOR_SPECS)
    else:
        for p in places:
            by_map.setdefault(p.get("ilce") or "Diğer", []).append(p)
        order = list(ILCELER)
    groups = []
    for ad in order:
        if ad in by_map:
            groups.append({"label": ad, "places": by_map.pop(ad)})
    for ad, plist in by_map.items():
        groups.append({"label": ad, "places": plist})
    return groups


def _health_ilce_groups(places: list[dict]) -> list[dict]:
    by: dict[str, list] = {}
    for p in places:
        by.setdefault(p.get("ilce") or "Diğer", []).append(_decorate_health_row(p))
    groups = []
    for ad in ILCELER:
        if ad in by:
            groups.append({"label": ad, "places": by.pop(ad)})
    for ad, plist in by.items():
        groups.append({"label": ad, "places": plist})
    return groups


def _attach_hospital_titles(db, places: list[dict]) -> None:
    slugs = {p.get("hospital_slug") or p.get("venue_name") for p in places}
    slugs.discard("")
    slugs.discard(None)
    if not slugs:
        return
    hs = {h.slug: h for h in db.query(Place).filter(Place.slug.in_(slugs)).all()}
    for p in places:
        h = hs.get(p.get("hospital_slug") or p.get("venue_name") or "")
        if h:
            p["hospital_title"] = h.title
            p["hospital_slug"] = h.slug


def _health_qs(*, ilce: str = "", spec: str = "", band: str = "", sub: str = "") -> str:
    from urllib.parse import quote

    parts = []
    if ilce:
        parts.append(f"ilce={quote(ilce)}")
    if spec:
        parts.append(f"spec={quote(spec)}")
    if band:
        parts.append(f"band={quote(band)}")
    if sub:
        parts.append(f"sub={quote(sub)}")
    return ("?" + "&".join(parts)) if parts else ""


def _render_health_page(**ctx):
    base = ctx.get("base_path") or "/"
    ilce = ctx.get("ilce") or ""
    spec = ctx.get("spec") or ""
    band = ctx.get("band_on") or ""
    sub = ctx.get("sub") or ""
    tail = _health_qs(spec=spec, band=band, sub=sub)
    ctx.setdefault("filter_all_url", base + tail)
    ctx.setdefault("filter_base", base)
    ctx.setdefault(
        "filter_extra",
        ("&" + tail[1:]) if tail else "",
    )
    if ctx.get("filter_items") is not None and "filter_on" not in ctx:
        ctx["filter_on"] = ilce or spec or ""
    return render_template("health_list.html", **ctx)


_HOSPITAL_BANDS = ("Özel", "Devlet", "Üniversite", "Kampüs", "Göz", "Diş")
_DENTIST_BANDS = ("Devlet", "Özel", "Klinik")
_SCHOOL_BANDS = ("Devlet", "Özel", "Üniversite")
_SCHOOL_SUBS = ("anaokul", "ilkokul", "ortaokul", "lise", "kolej", "universite", "dershane", "ozel-egitim")


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
    has_geo = False
    try:
        lat = float(request.args.get("lat"))
        lng = float(request.args.get("lng"))
        has_geo = True
    except (TypeError, ValueError):
        lat = lng = None
    feed = _load_nobetci_feed()
    items = [_decorate_rx(p) for p in (feed.get("pharmacies") or [])]
    if ilce:
        items = [p for p in items if (p.get("district") or "") == ilce]
    if has_geo:
        items = _rx_with_distance(items, lat, lng)
        for p in items:
            p["distance_label"] = _rx_distance_label(p.get("distance_m"))
    districts = sorted({p.get("district") for p in (feed.get("pharmacies") or []) if p.get("district")})
    if has_geo:
        groups = [{"label": "Sana en yakın", "places": items}] if items else []
    else:
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
        duty_label=_rx_duty_label(feed),
        nav="pharmacy",
        has_geo=has_geo,
        lat=lat,
        lng=lng,
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
    if place:
        place = _decorate_rx(place)
    osm = ""
    if place and place.get("lat") is not None and place.get("lng") is not None:
        lat = float(place["lat"])
        lng = float(place["lng"])
        osm = (
            "https://www.openstreetmap.org/export/embed.html"
            f"?bbox={lng - 0.012:.6f},{lat - 0.008:.6f},{lng + 0.012:.6f},{lat + 0.008:.6f}"
            f"&layer=mapnik&marker={lat},{lng}"
        )
    return render_template(
        "nobetci_eczane_detail.html",
        place=place,
        feed=feed,
        duty_label=_rx_duty_label(feed),
        osm_embed=osm,
        nav="pharmacy",
        seo=seo_page(
            title=(place["name"] if place else "Nöbetçi eczane") + " · Bursa",
            description=(place.get("address") if place else "Bursa nöbetçi eczane") or "",
            path=f"/nobetci-eczaneler/{slug}",
        ),
    )


def _utilities_ctx(kind: str):
    from utilities_pages import branches_by_ilce, fmt_tl, load_teleferik, load_utilities

    feed = load_utilities()
    key = {"su": "water", "elec": "electricity", "gas": "gas"}[kind]
    section = feed.get(key) or {}
    aksa = section.get("aksa") or {}
    return dict(
        feed=feed,
        section=section,
        kind=kind,
        branch_groups=branches_by_ilce(section.get("branches")),
        aksa_branch_groups=branches_by_ilce(aksa.get("branches")),
        fmt_tl=fmt_tl,
        teleferik=load_teleferik(),
    )


@app.route("/faturalar")
def utilities_hub():
    from seo import page as seo_page
    from utilities_pages import load_teleferik, load_utilities

    feed = load_utilities()
    return render_template(
        "utilities_hub.html",
        feed=feed,
        teleferik=load_teleferik(),
        nav_util="hub",
        nav="faturalar",
        seo=seo_page(
            title="Bursa su, elektrik ve doğalgaz fiyatları 2026",
            description="BUSKİ su tarifesi (m³/ton), UEDAŞ elektrik kWh fiyatı, Bursagaz doğalgaz birim bedeli — ilçe ilçe abone merkezleri. Güncel özet.",
            path="/faturalar",
            keywords="bursa su fiyatı, buski tarife, uedaş elektrik fiyatı, bursagaz doğalgaz fiyatı, bursa fatura",
        ),
    )


@app.route("/buski-su-fiyatlari")
def utilities_water():
    from seo import page as seo_page

    ctx = _utilities_ctx("su")
    return render_template(
        "utilities_kind.html",
        page_h1="BUSKİ su fiyatları 2026 — ton / m³ tarife",
        nav_util="su",
        nav="faturalar",
        seo=seo_page(
            title="BUSKİ su fiyatları 2026 — Bursa m³ ve ton tarifesi",
            description="Bursa BUSKİ güncel su fiyatları: kademeli m³ tarifesi, atıksu bedeli, 17 ilçe abone merkezi telefon ve adres. 1 m³ = 1 ton.",
            path="/buski-su-fiyatlari",
            keywords="buski su fiyatı, bursa su fiyatı 2026, buski tarife, ton su fiyatı bursa, buski abone",
        ),
        **ctx,
    )


@app.route("/bursa-elektrik-fiyatlari")
def utilities_electric():
    from seo import page as seo_page

    ctx = _utilities_ctx("elec")
    return render_template(
        "utilities_kind.html",
        page_h1="Bursa elektrik fiyatları 2026 — UEDAŞ tarife",
        nav_util="elec",
        nav="faturalar",
        seo=seo_page(
            title="Bursa elektrik fiyatları 2026 — UEDAŞ kWh tarifesi",
            description="UEDAŞ Bursa mesken elektrik birim fiyatları, kademe dilimleri ve ilçe bölge müdürlükleri. Arıza: 186.",
            path="/bursa-elektrik-fiyatlari",
            keywords="bursa elektrik fiyatı, uedaş tarife, bursa kwh fiyatı 2026, elektrik birim fiyat bursa",
        ),
        **ctx,
    )


@app.route("/bursa-dogalgaz-fiyatlari")
def utilities_gas():
    from seo import page as seo_page

    ctx = _utilities_ctx("gas")
    return render_template(
        "utilities_kind.html",
        page_h1="Bursa doğalgaz fiyatları 2026 — Aksa · Bursagaz tarife",
        nav_util="gas",
        nav="faturalar",
        seo=seo_page(
            title="Bursa doğalgaz fiyatları 2026 — Aksa Doğalgaz · Bursagaz sm³",
            description="Aksa Doğalgaz Bursa ve Bursagaz güncel konut doğalgaz tarifesi, 444 11 33 / 444 4 827 çağrı merkezleri ve ilçe müşteri merkezleri. Acil: 187.",
            path="/bursa-dogalgaz-fiyatlari",
            keywords="aksa doğalgaz bursa, bursagaz tarife, bursa doğalgaz fiyatı 2026, aksa bursa gaz fiyatı, sm3 doğalgaz bursa",
        ),
        **ctx,
    )


@app.route("/uludag-teleferik")
def teleferik_guide():
    from datetime import datetime
    from flask import url_for
    from seo import abs_url, page as seo_page
    from utilities_pages import load_teleferik

    data = load_teleferik()
    year = datetime.now(tz=_TZ).year
    hero_img = url_for("static", filename="visit/teleferik.jpg")
    gallery_uludag = url_for("static", filename="visit/uludag.jpg")

    return render_template(
        "teleferik_guide.html",
        data=data,
        year=year,
        hero_img=hero_img,
        gallery_uludag=gallery_uludag,
        nav_util="teleferik",
        nav="teleferik",
        seo=seo_page(
            title=f"Uludağ teleferik bilet fiyatları {year} — saatler, halk günü, otobüs",
            description="Bursa Teleferik güncel bilet fiyatı, cuma halk günü indirimi, açılış-kapanış saatleri, Teferrüç'e giden otobüs ve Bursaray bilgisi.",
            path="/uludag-teleferik",
            image=abs_url("/static/visit/teleferik.jpg"),
            keywords="uludağ teleferik fiyat, bursa teleferik bilet, teleferik halk günü, teferrüç otobüs, teleferik saatleri",
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
                description="42 kamp noktası: Çobankaya, Yalıntaş, Kilimli, Kapanca, Trilye, Longoz, Gölyazı ve Balıkesir kaçışları — BursaApp rehberi.",
                path="/kamp",
                breadcrumbs=[("Keşfet", "/"), ("Kamp", "/kamp")],
                keywords="bursa kamp, çobankaya, kapanca, gölyazı kamp, uludağ kamp, karacabey longoz",
            ),
        )
    finally:
        db.close()


def _hotel_price_tl(place: dict) -> int | None:
    """Örnek gecelik fiyat — extra.price_min metninden TL tamsayı."""
    import re

    raw = ""
    extra = place.get("extra") or {}
    if isinstance(extra, dict):
        raw = (extra.get("price_min") or extra.get("price_max") or "").strip()
    if not raw:
        est = int(place.get("est_meal_tl") or 0)
        return est if est > 0 else None
    digits = re.sub(r"[^\d]", "", raw.split(",")[0])
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _hotel_link(**overrides) -> str:
    from urllib.parse import urlencode

    params: dict[str, str] = {}
    for key in ("q", "ilce", "sub", "band", "sort", "price"):
        val = overrides[key] if key in overrides else (request.args.get(key) or "").strip()
        if val:
            params[key] = val
    qs = urlencode(params)
    return "/oteller" + (f"?{qs}" if qs else "")


@app.route("/oteller")
def hotels_list():
    from seo import for_vertical
    from catalog import subcategories_for, ILCELER

    q = (request.args.get("q") or "").strip()
    ilce = (request.args.get("ilce") or "").strip()
    sub = (request.args.get("sub") or "").strip()
    band = (request.args.get("band") or "").strip().lower()
    sort = (request.args.get("sort") or "rating").strip().lower()
    if sort not in ("rating", "price_asc", "price_desc"):
        sort = "rating"
    price_filter = (request.args.get("price") or "").strip().lower()
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
        for p in places:
            p["price_tl"] = _hotel_price_tl(p)
        if band and not ilce:
            places = [p for p in places if (p.get("price_band") or "").lower() == band]
        if price_filter == "lt10":
            places = [p for p in places if (p.get("price_tl") or 10**9) < 10000]
        elif price_filter == "10-18":
            places = [p for p in places if p.get("price_tl") is not None and 10000 <= p["price_tl"] < 18000]
        elif price_filter == "18plus":
            places = [p for p in places if (p.get("price_tl") or 0) >= 18000]
        if sort == "price_asc":
            places.sort(
                key=lambda p: (
                    p.get("price_tl") is None,
                    p.get("price_tl") or 10**9,
                    (p.get("title") or ""),
                )
            )
        elif sort == "price_desc":
            places.sort(
                key=lambda p: (
                    p.get("price_tl") is None,
                    -(p.get("price_tl") or 0),
                    (p.get("title") or ""),
                )
            )
        else:
            places.sort(
                key=lambda p: (
                    -(float(p["rating"]) if p.get("rating") is not None else -1.0),
                    (p.get("title") or ""),
                )
            )
        if sort.startswith("price"):
            featured = places[:8]
        else:
            featured = [p for p in places if p.get("featured")][:8]
            if len(featured) < 4:
                featured = places[:8]
        featured_slugs = {p.get("slug") for p in featured}
        districts = list(ILCELER)
        return render_template(
            "hotels.html",
            places=places,
            featured=featured,
            featured_slugs=featured_slugs,
            q=q,
            ilce=ilce,
            sub=sub,
            band=band,
            sort=sort,
            price_filter=price_filter,
            hotel_link=_hotel_link,
            subs=subcategories_for("hotel"),
            districts=districts,
            nav="hotel",
            seo=for_vertical("/oteller", total=len(places), places=places),
        )
    finally:
        db.close()


def _food_href(**upd) -> str:
    """Yeme-içme filtre URL. toggle=('kind','cafe') ekler/çıkarır."""
    from urllib.parse import urlencode

    multi = ("kind", "meal", "cuisine", "dish", "price")
    single = ("q", "ilce", "sort", "page")
    args = {k: list(request.args.getlist(k)) for k in multi}
    out: list[tuple[str, str]] = []
    did_toggle = False
    tog = upd.pop("toggle", None)
    if tog:
        did_toggle = True
        key, val = tog
        cur = list(args.get(key) or [])
        if val in cur:
            cur = [x for x in cur if x != val]
        else:
            cur.append(val)
        args[key] = cur
    for k in multi:
        vals = upd[k] if k in upd else args.get(k) or []
        if isinstance(vals, str):
            vals = [vals] if vals else []
        for v in vals:
            if v:
                out.append((k, v))
    for k in single:
        if k in upd:
            v = upd[k]
        elif k == "page" and did_toggle:
            v = ""
        else:
            v = (request.args.get(k) or "").strip()
        if k == "page" and str(v) in ("", "1"):
            continue
        if v:
            out.append((k, str(v)))
    qs = urlencode(out, doseq=True)
    return "/yeme-icme" + (("?" + qs) if qs else "")


def _visit_href(**upd) -> str:
    """Gezilecek filtre URL. toggle=('kind','muze') ekler/çıkarır."""
    from urllib.parse import urlencode

    multi = ("kind", "fee", "tag")
    single = ("q", "ilce", "sort", "page", "sub")
    args = {k: list(request.args.getlist(k)) for k in multi}
    out: list[tuple[str, str]] = []
    did_toggle = False
    tog = upd.pop("toggle", None)
    if tog:
        did_toggle = True
        key, val = tog
        cur = list(args.get(key) or [])
        if val in cur:
            cur = [x for x in cur if x != val]
        else:
            cur.append(val)
        args[key] = cur
    for k in multi:
        vals = upd[k] if k in upd else args.get(k) or []
        if isinstance(vals, str):
            vals = [vals] if vals else []
        for v in vals:
            if v:
                out.append((k, v))
    for k in single:
        if k in upd:
            v = upd[k]
        elif k == "page" and did_toggle:
            v = ""
        else:
            v = (request.args.get(k) or "").strip()
        if k == "page" and str(v) in ("", "1"):
            continue
        if v:
            out.append((k, str(v)))
    qs = urlencode(out, doseq=True)
    return "/gezilecek" + (("?" + qs) if qs else "")


@app.route("/gezilecek-yerler")
def gezilecek_yerler_redirect():
    return redirect("/gezilecek", 301)


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
            order="rating" if (food or visit or hospital) else ("date" if kinds else None),
            price_band=band or None,
            subcategory=sub or None,
            limit=2500 if (food or visit) else (200 if grouped or hospital else 60),
        )
        places = [place_public(p) for p in rows]
        if food:
            kinds = [x for x in request.args.getlist("kind") if x]
            meals = [x for x in request.args.getlist("meal") if x]
            cuisines = [x for x in request.args.getlist("cuisine") if x]
            dishes = [x for x in request.args.getlist("dish") if x]
            prices = [x for x in request.args.getlist("price") if x]
            if sub and sub not in dishes:
                dishes = dishes + [sub]
            filtered = [
                p for p in places
                if food_matches(p, kinds=kinds or None, meals=meals or None, cuisines=cuisines or None, dishes=dishes or None, prices=prices or None)
            ]
            sort = (request.args.get("sort") or "featured").strip()
            if sort == "name":
                filtered.sort(key=lambda p: (p.get("title") or "").lower())
            elif sort == "rating":
                filtered.sort(key=lambda p: (-(float(p["rating"]) if p.get("rating") is not None else -1), p.get("title") or ""))
            else:
                filtered.sort(
                    key=lambda p: (
                        0 if p.get("featured") else 1,
                        -(float(p["rating"]) if p.get("rating") is not None else -1),
                        p.get("title") or "",
                    )
                )
            total_f = len(filtered)
            per = 40
            try:
                page_n = max(1, int(request.args.get("page") or 1))
            except ValueError:
                page_n = 1
            pages = max(1, (total_f + per - 1) // per)
            if page_n > pages:
                page_n = pages
            start = (page_n - 1) * per
            page_rows = filtered[start:start + per]
            for i, p in enumerate(page_rows, start=start + 1):
                p["rank"] = i
                p["price_marks"] = food_price_marks(p)
                ex = p.get("extra") or {}
                p["has_menu"] = bool(ex.get("menu") or p.get("menu_text") or p.get("web"))
                gals = ex.get("gallery") if isinstance(ex.get("gallery"), list) else []
                p["gallery"] = [p["img_url"]] + [g for g in gals if g and g != p.get("img_url")]
                p["gallery"] = [g for g in p["gallery"] if g][:6]
            food_hero = []
            if page_n == 1 and not q:
                for p in filtered[:3]:
                    if p.get("img_url"):
                        food_hero.append(p)
            food_curated_rows = []
            for c in FOOD_CURATED:
                kw: dict = {"page": ""}
                kw.update(c.get("filter") or {})
                active = False
                fd = c.get("filter") or {}
                if fd.get("dish") and fd["dish"] in dishes:
                    active = True
                if fd.get("kind") and fd["kind"] in kinds:
                    active = True
                if fd.get("meal") and fd["meal"] in meals:
                    active = True
                food_curated_rows.append({**c, "href": _food_href(**kw), "active": active})
            from seo import for_category

            return render_template(
                "foods_list.html",
                cat=cat,
                places=page_rows,
                total=total_f,
                q=q,
                ilce=ilce,
                sub=sub,
                sort=sort,
                page=page_n,
                pages=pages,
                kinds_on=kinds,
                meals_on=meals,
                cuisines_on=cuisines,
                dishes_on=dishes,
                prices_on=prices,
                food_kind=FOOD_KIND,
                food_meal=FOOD_MEAL,
                food_cuisine=FOOD_CUISINE,
                food_dish=FOOD_DISH,
                food_price=FOOD_PRICE,
                food_curated=food_curated_rows,
                food_hero=food_hero,
                food_href=_food_href,
                nav="food",
                seo=for_category(cat, ilce=ilce, sub=sub, total=total_f, places=page_rows),
            )
        if visit:
            kinds = [x for x in request.args.getlist("kind") if x]
            fees = [x for x in request.args.getlist("fee") if x]
            vtags = [x for x in request.args.getlist("tag") if x]
            if sub:
                places = [p for p in places if (p.get("subcategory") or "") == sub]
            filtered = [
                p for p in places
                if visit_matches(p, kinds=kinds or None, fees=fees or None, tags=vtags or None)
            ]
            sort = (request.args.get("sort") or "featured").strip()
            if sort == "name":
                filtered.sort(key=lambda p: (p.get("title") or "").lower())
            elif sort == "rating":
                filtered.sort(key=lambda p: (-(float(p["rating"]) if p.get("rating") is not None else -1), p.get("title") or ""))
            else:
                filtered.sort(
                    key=lambda p: (
                        0 if p.get("featured") else 1,
                        0 if not str(p.get("slug") or "").startswith("osm-visit-") else 1,
                        -(float(p["rating"]) if p.get("rating") is not None else -1),
                        p.get("title") or "",
                    )
                )
            total_f = len(filtered)
            per = 40
            try:
                page_n = max(1, int(request.args.get("page") or 1))
            except ValueError:
                page_n = 1
            pages = max(1, (total_f + per - 1) // per)
            if page_n > pages:
                page_n = pages
            start = (page_n - 1) * per
            page_rows = filtered[start:start + per]
            for i, p in enumerate(page_rows, start=start + 1):
                p["rank"] = i
                p["fee_label"] = "Ücretli" if visit_fee_tier(p) == "ucretli" else "Ücretsiz"
                ex = p.get("extra") or {}
                gals = ex.get("gallery") if isinstance(ex.get("gallery"), list) else []
                p["gallery"] = [p.get("img_url")] + [g for g in gals if g and g != p.get("img_url")]
                p["gallery"] = [g for g in p["gallery"] if g][:6]
            from seo import for_category

            return render_template(
                "visits_list.html",
                cat=cat,
                places=page_rows,
                total=total_f,
                q=q,
                ilce=ilce,
                sub=sub,
                sort=sort,
                page=page_n,
                pages=pages,
                kinds_on=kinds,
                fees_on=fees,
                tags_on=vtags,
                visit_kind=VISIT_KIND,
                visit_fee=VISIT_FEE,
                visit_tag=VISIT_TAG,
                visit_href=_visit_href,
                nav="visit",
                seo=for_category(cat, ilce=ilce, sub=sub, total=total_f, places=page_rows),
            )
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

        if hospital:
            groups = _health_card_groups(places, by="ilce")
            ozel_n = sum(1 for p in places if (p.get("price_band") or "") == "Özel")
            return _render_health_page(
                nav="hospital",
                page_title="Hastaneler",
                page_sub="Devlet, özel, üniversite — karttaki hekimler o hastaneye bağlı",
                hero_theme="hospital",
                hero_art="health/hospital.svg",
                hero_kicker="Bursa sağlık",
                hero_headline="Hastaneler ve merkezler",
                hero_desc=f"{total} hastane · ilçene göre filtrele, puan ve tür.",
                stat1_label="hastane",
                stat2_value=len(groups),
                stat2_label="ilçe",
                stat3_value=ozel_n or "MHRS",
                stat3_label="özel" if ozel_n else "randevu",
                row_kind="hospital",
                row_unit="hastane",
                total=total,
                groups=groups,
                list_style="cards",
                card_kind="hospital",
                base_path="/hastaneler",
                ilce=ilce,
                band_on=hosp_band,
                band_chips=_HOSPITAL_BANDS,
                filter_items=list(ILCELER),
                filter_param="ilce",
                filter_label="Bölge",
                filter_on=ilce,
                hero_note="Randevu MHRS / 182 · Acil 112",
                empty_text="Bu filtrede hastane yok.",
                seo=for_category(cat, ilce=ilce, sub=hosp_band, total=total, places=places),
            )

        if doctor:
            groups = _health_card_groups(places, by="spec")
            brans_n = len({p.get("price_band") for p in places if p.get("price_band")})
            return _render_health_page(
                nav="doctor",
                page_title="Doktorlar",
                page_sub="Branşa göre hekim — hastane sayfasına bağlı · randevu / tıbbi tavsiye yok",
                hero_theme="doctor",
                hero_art="health/doctor.svg",
                hero_kicker="Branş ve hekim",
                hero_headline="Bursa doktorları",
                hero_desc=f"{total} hekim · branş ve ilçeye göre filtrele.",
                stat1_label="hekim",
                stat2_value=brans_n or len(groups),
                stat2_label="branş" if brans_n else "ilçe",
                stat3_value="MHRS",
                stat3_label="randevu",
                row_kind="doctor",
                row_unit="hekim",
                total=total,
                groups=groups,
                list_style="cards",
                card_kind="doctor",
                base_path="/doktorlar",
                ilce=ilce,
                spec=spec,
                filter_items=list(DOCTOR_SPECS),
                filter_param="spec",
                filter_label="Branş",
                filter_on=spec,
                hero_note="Resmi kadro bağlantıları · MHRS / 182",
                empty_text="Bu filtrede hekim yok.",
                seo=for_category(cat, ilce=ilce, sub=spec, total=total, places=places),
            )

        hospital_bands = _HOSPITAL_BANDS if hospital else ()

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
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from news_pages import load_bursaspor_videos

        rows = (
            db.query(SportMatch)
            .filter(SportMatch.club == "bursaspor", SportMatch.season == "2026-27")
            .order_by(SportMatch.week.asc().nullslast(), SportMatch.kickoff_at.asc().nullslast())
            .all()
        )
        now = datetime.now(ZoneInfo("Europe/Istanbul"))
        matches = []
        next_match = None
        last_match = None
        upcoming = []
        played_items = []
        for m in rows:
            played = m.home_score is not None and m.away_score is not None
            item = {
                "id": m.id,
                "week": m.week,
                "competition": m.competition,
                "kickoff_at": m.kickoff_at.strftime("%d.%m.%Y %H:%M") if m.kickoff_at else "",
                "kickoff_date": m.kickoff_at.strftime("%d.%m.%Y") if m.kickoff_at else "",
                "kickoff_time": m.kickoff_at.strftime("%H:%M") if m.kickoff_at else "",
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
                "played": played,
            }
            matches.append(item)
            if played:
                last_match = item
                played_items.append(item)
            elif m.kickoff_at:
                kickoff = m.kickoff_at
                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=ZoneInfo("Europe/Istanbul"))
                if next_match is None and kickoff >= now:
                    next_match = item
                if len(upcoming) < 8 and kickoff >= now:
                    upcoming.append(item)
        recent = list(reversed(played_items[-3:]))
        from seo import page as seo_page
        import json as _json
        import os as _os

        standings = []
        bs_row = None
        sp = _os.path.join(_DIR, "data", "bursaspor_standings.json")
        if _os.path.isfile(sp):
            try:
                standings = _json.loads(open(sp, encoding="utf-8").read())
                for r in standings:
                    if "Bursaspor" in (r.get("team") or ""):
                        bs_row = r
                        break
            except Exception:
                standings = []

        feed = {"news": [], "desk": {}, "generated_at": "", "disclaimer": ""}
        fp = _os.path.join(_DIR, "data", "bursaspor_feed.json")
        if _os.path.isfile(fp):
            try:
                feed = _json.loads(open(fp, encoding="utf-8").read())
            except Exception:
                pass

        desk = feed.get("desk") or {}
        if not next_match and desk.get("next_match"):
            nm = desk["next_match"]
            next_match = {
                "home_team": nm.get("home") or "",
                "away_team": nm.get("away") or "",
                "kickoff_at": nm.get("kickoff") or "",
                "kickoff_date": (nm.get("kickoff") or "").split(" ")[0],
                "kickoff_time": (nm.get("kickoff") or "").split(" ")[-1] if nm.get("kickoff") else "",
                "venue": nm.get("venue") or "",
                "is_home": nm.get("is_home"),
                "ticket_url": "https://www.bursaspor.org.tr/",
                "played": False,
            }

        hero_bg = "/static/cache/bursaspor/cover-1.jpg"
        mf = _os.path.join(_DIR, "static", "cache", "bursaspor", "manifest.json")
        if _os.path.isfile(mf):
            try:
                pool = _json.loads(open(mf, encoding="utf-8").read())
                if isinstance(pool, list) and pool:
                    hero_bg = pool[0]
            except Exception:
                pass

        videos = load_bursaspor_videos(limit=6)
        featured_video = videos[0] if videos else None

        return render_template(
            "bursaspor.html",
            matches=matches,
            upcoming=upcoming,
            recent=recent,
            next_match=next_match,
            last_match=last_match,
            standings=standings,
            bs_row=bs_row,
            feed=feed,
            desk=desk,
            videos=videos,
            featured_video=featured_video,
            hero_bg=hero_bg,
            nav="bursaspor",
            seo=seo_page(
                title="Bursaspor haber · maç · video · fikstür 2026-27",
                description=(
                    "Bursaspor maç önizlemesi, video, gündem özeti, Trendyol 1. Lig puan durumu "
                    "ve fikstür — BursaApp'te izle, oku, siteden çıkma."
                ),
                path="/bursaspor",
                keywords="bursaspor, bursaspor haber, bursaspor maç, bursaspor fikstür, yeşil beyaz, timsah",
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
        # detayda tam çözünürlük; listelerde thumb (place_public)
        if d.get("img_full"):
            d["img_url"] = d["img_full"]
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
        school_events = []
        if p.category == "school":
            ev_rows = (
                db.query(Place)
                .filter(
                    Place.status == "approved",
                    Place.category == "event",
                    Place.venue_name == p.slug,
                )
                .order_by(Place.starts_at.desc().nulls_last())
                .limit(24)
                .all()
            )
            school_events = [place_public(x) for x in ev_rows]
        staff, staff_groups, hospital, units = [], [], None, []
        if p.category == "hospital":
            docs, _ = query_places(db, category="doctor", venue_name=p.slug, limit=500)
            staff = [place_public(x) for x in docs]
            staff_groups = hospital_staff_groups(staff)
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
        elif p.category in ("doctor", "dentist"):
            tmpl = "doctor_detail.html"
        elif p.category == "school":
            tmpl = "school_detail.html"
        elif p.category in ("event", "concert", "theater") and not (p.slug or "").startswith("film-"):
            tmpl = "event_detail.html"
        else:
            tmpl = "detail.html"
        return render_template(
            tmpl,
            place=d,
            similar=similar,
            venue_events=venue_events,
            school_events=school_events,
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
            market_campaign=active_campaign_for_place(db, p.id) if p.category == "market" else None,
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

            url, _err = save_upload(f, category="review")
            if url:
                rev.img_url = url
        db.flush()
        # puan yalnız onaylı yorumlardan — pending skoru etkilemez
        recompute_place_rating(db, p)
        db.commit()
        return redirect("/tesekkur?from=yorum&next=" + quote(dest, safe="") + "&label=" + quote("Yer sayfasına dön", safe=""))
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
        url, err = save_upload(f, category="place_photo")
        if not url:
            flash(err or "Geçerli bir foto seç.", "err")
            return redirect(f"/yer/{slug}")
        db.add(PlacePhoto(place_id=p.id, user_id=user.id, img_url=url, caption=caption, status="pending"))
        db.commit()
        from seo_urls import place_seo_path

        flash("Fotoğraf alındı — onaydan sonra galeride görünür.", "ok")
        return redirect(place_seo_path(p) + "#galeri")
    finally:
        db.close()


def _safe_next(val: str | None, default: str = "/") -> str:
    s = (val or "").strip()
    if s.startswith("/") and not s.startswith("//") and "://" not in s:
        return s
    return default


@app.route("/giris", methods=["GET", "POST"])
def giris():
    from admin_permissions import can_access_panel, first_panel_url, has_perm

    nxt = _safe_next(request.args.get("next") or request.form.get("next"), "/")
    user = load_user()
    wants_admin = nxt.startswith("/admin")
    err = ""
    if user and wants_admin and not can_access_panel(user):
        err = f"Şu an {user.email} ile girişlisin — bu hesabın panel yetkisi yok."
    elif user and request.method == "GET":
        if wants_admin and can_access_panel(user):
            dest = nxt
            if nxt.startswith("/admin/dashboard") and not has_perm(user, "dashboard"):
                dest = first_panel_url(user)
            return redirect(dest)
        return redirect(nxt if nxt not in ("/", "") else "/")
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
                elif not bool(getattr(u, "is_active", True)):
                    err = "Hesabın pasif durumda. Yönetici ile iletişime geç."
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
                        user_role=u.role,
                    )
                    db.commit()
                    dest = nxt
                    if wants_admin:
                        if nxt.startswith("/admin/dashboard") and not has_perm(u, "dashboard"):
                            dest = first_panel_url(u)
                        elif nxt == "/admin" or nxt.startswith("/admin?"):
                            if not has_perm(u, "queue"):
                                dest = first_panel_url(u)
                    return redirect(_safe_next(dest, "/"))
            finally:
                db.close()
    return render_template("auth.html", mode="giris", err=err, next=nxt if nxt != "/" else "", nav="auth")


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
                            return redirect("/tesekkur?from=kayit")
                        flash(
                                "Kayıt tamam ama onay maili gönderilemedi. "
                                "Biraz sonra Ayarlar’dan tekrar dene; spam klasörünü de kontrol et.",
                                "err",
                            )
                        return redirect("/tesekkur?from=kayit")
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
    from feed_social import album_photos, post_images
    from models import EventGoing, Favorite, PlacePhoto, UserPost, UserVisit

    user = load_user()
    tab = (request.args.get("tab") or "media").strip().lower()
    if tab not in ("about", "posts", "media"):
        tab = "media"
    db = SessionLocal()
    try:
        rows = db.query(Place).filter(Place.submitted_by_id == user.id).order_by(Place.id.desc()).all()
        u = db.get(User, user.id)
        if not u:
            flash("Oturum geçersiz", "err")
            return redirect("/giris")
        posts_n = (
            db.query(UserPost)
            .filter(UserPost.user_id == u.id, UserPost.status == "approved")
            .count()
        )
        favs_n = db.query(Favorite).filter(Favorite.user_id == u.id).count()
        visits_n = db.query(UserVisit).filter(UserVisit.user_id == u.id).count()
        going_n = db.query(EventGoing).filter(EventGoing.user_id == u.id).count()
        likes_total = sum(
            int(p.likes_count or 0)
            for p in db.query(UserPost).filter(UserPost.user_id == u.id).all()
        )
        album = album_photos(db, u.id, limit=36)
        user_posts = []
        for post in (
            db.query(UserPost)
            .filter(UserPost.user_id == u.id)
            .order_by(UserPost.id.desc())
            .limit(24)
            .all()
        ):
            imgs = post_images(post)
            user_posts.append(
                {
                    "id": post.id,
                    "body": (post.body or "")[:120],
                    "images": imgs,
                    "thumb": imgs[0] if imgs else "",
                    "likes": int(post.likes_count or 0),
                    "status": post.status,
                    "created": post.created_at,
                }
            )
        return render_template(
            "account.html",
            u=u,
            tab=tab,
            places=rows,
            points=int(u.loyalty_points or 0),
            posts_n=posts_n,
            favs_n=favs_n,
            visits_n=visits_n,
            going_n=going_n,
            likes_total=likes_total,
            album=album,
            user_posts=user_posts,
            nav="hesap",
        )
    finally:
        db.close()


def _profile_follow_suggestions(db, user_id: int, *, limit: int = 3) -> list[dict]:
    from feed_social import suggest_follow_users

    return suggest_follow_users(db, user_id, limit=limit)


@app.route("/hesap/profil")
@login_required
def hesap_profil():
    from feed_social import (
        album_photos,
        build_feed,
        profile_feed,
        FEED_PAGE_SIZE,
        follow_counts,
        going_count,
        suggest_places,
        suggest_top_restaurants,
        feed_picker_places,
        upcoming_events,
        _place_card,
        _ago,
    )
    from models import EventGoing, UserVisit

    user = load_user()
    tab = (request.args.get("tab") or "recents").strip().lower()
    if tab not in ("recents", "mine", "popular", "friends", "media", "visits", "reviews", "going"):
        tab = "recents"
    db = SessionLocal()
    try:
        u = db.get(User, user.id)
        if not u:
            flash("Oturum geçersiz", "err")
            return redirect("/giris")
        feed_has_more = False
        if tab in ("recents", "friends", "popular", "mine"):
            feed, feed_has_more = profile_feed(db, u, tab, limit=FEED_PAGE_SIZE, offset=0)
        elif tab == "reviews":
            feed_all, _ = build_feed(db, viewer=u, owner_id=u.id, tab="recents", limit=80, offset=0)
            feed = [x for x in feed_all if x.get("kind") == "review"]
        else:
            feed = []
        album = album_photos(db, u.id) if tab == "media" else []
        visits = []
        if tab == "visits":
            for v in db.query(UserVisit).filter(UserVisit.user_id == u.id).order_by(UserVisit.id.desc()).limit(80).all():
                p = db.get(Place, v.place_id)
                visits.append(
                    {
                        "note": v.note,
                        "ago": _ago(v.created_at),
                        "place": _place_card(p),
                        "status": v.status,
                    }
                )
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
            if p and p.category in ("visit", "camp"):
                visit_places.append(_place_card(p))
        picker_places = feed_picker_places(db, u.id, limit=20)
        follow_suggestions = _profile_follow_suggestions(db, u.id, limit=3)
        social_counts = follow_counts(db, u.id)
        resp = app.make_response(
            render_template(
            "profile_feed.html",
            u=u,
            tab=tab,
            feed=feed,
            feed_has_more=feed_has_more,
            album=album,
            visits=visits,
            goings=goings,
            going_n=going_n,
            suggest=suggest_places(db, 8),
            restaurant_suggest=suggest_top_restaurants(db, 6),
            follow_suggestions=follow_suggestions,
            social_counts=social_counts,
            picker_places=picker_places,
            events=upcoming_events(db, 8),
            visit_places=visit_places,
            nav="hesap",
            )
        )
        resp.headers["Cache-Control"] = "private, no-store"
        return resp
    finally:
        db.close()


@app.route("/hesap/profil/feed")
def hesap_profil_feed():
    from feed_social import FEED_PAGE_SIZE, profile_feed, PROFILE_FEED_TABS, build_feed

    tab = (request.args.get("tab") or "recents").strip().lower()
    if tab not in PROFILE_FEED_TABS:
        return {"html": "", "has_more": False, "next_offset": 0}, 400
    offset = max(0, int(request.args.get("offset") or 0))
    limit = min(20, max(1, int(request.args.get("limit") or FEED_PAGE_SIZE)))
    db = SessionLocal()
    try:
        user = load_user()
        if user:
            u = db.get(User, user.id)
            if not u:
                return {"html": "", "has_more": False, "next_offset": 0}, 401
            feed, has_more = profile_feed(db, u, tab, limit=limit, offset=offset)
        else:
            if tab not in ("recents", "popular"):
                return {"html": "", "has_more": False, "next_offset": 0}, 401
            feed, has_more = build_feed(db, viewer=None, tab=tab, limit=limit, offset=offset)
        html = render_template("_feed_items.html", feed=feed, tone_offset=offset, show_empty=offset == 0)
        return {
            "html": html,
            "has_more": has_more,
            "next_offset": offset + len(feed),
        }
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
                path, err = save_upload(f, category="avatar")
                if err:
                    flash(err, "err")
                elif path:
                    u.avatar_url = path
                    db.commit()
                    flash("Profil fotoğrafı güncellendi.", "ok")
                    return redirect("/hesap/ayarlar?foto=1")
                else:
                    flash("Geçerli bir görsel seç.", "err")
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
            if f:
                url, _err = save_upload(f, category="feed")
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
        post_status = "approved" if privacy == "private" else "pending"
        post = UserPost(
            user_id=user.id,
            place_id=place.id if place else None,
            body=body,
            privacy=privacy,
            status=post_status,
        )
        set_post_images(post, urls)
        db.add(post)
        if also_visit and place:
            vis = db.query(UserVisit).filter(UserVisit.user_id == user.id, UserVisit.place_id == place.id).first()
            visit_note = body[:280] if body else ""
            visit_status = "pending" if visit_note.strip() else "approved"
            if not vis:
                db.add(
                    UserVisit(
                        user_id=user.id,
                        place_id=place.id,
                        note=visit_note,
                        status=visit_status,
                    )
                )
            else:
                if body:
                    vis.note = visit_note
                    vis.status = visit_status
        db.commit()
        if post_status == "pending":
            flash(
                "Gönderin alındı — admin onayından sonra herkese görünür."
                + (" Fotoğraflar yer galerisi için de onaya düştü." if urls and place else ""),
                "ok",
            )
        else:
            flash("Gönderi kaydedildi (sadece sen görürsün)." + (" Fotoğraflar onaya düştü." if urls and place else ""), "ok")
        return redirect("/hesap/profil?tab=mine")
    finally:
        db.close()


@app.route("/hesap/profil/ziyaret", methods=["POST"])
@login_required
def hesap_profil_ziyaret():
    from feed_social import ensure_visit_feed_post
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
        visit_status = "pending" if note.strip() else "approved"
        if vis:
            if note:
                vis.note = note
                vis.status = visit_status
            flash("Zaten listende — not güncellendi." + (" Onaydan sonra yayınlanır." if visit_status == "pending" else ""), "ok")
        else:
            db.add(UserVisit(user_id=user.id, place_id=place.id, note=note, status=visit_status))
            flash(
                f"{place.title} eklendi." + (" Notun onay bekliyor." if visit_status == "pending" else ""),
                "ok",
            )
        db.flush()
        vis = db.query(UserVisit).filter(UserVisit.user_id == user.id, UserVisit.place_id == place.id).first()
        if vis and vis.status == "approved":
            ensure_visit_feed_post(db, vis)
        db.commit()
        return redirect("/hesap/profil?tab=visits")
    finally:
        db.close()


@app.route("/hesap/profil/takip/<int:target_id>", methods=["POST"])
@login_required
def hesap_profil_takip(target_id: int):
    from feed_social import follow_toggle

    user = load_user()
    if target_id == user.id:
        if _wants_json():
            return {"ok": False, "error": "Kendini takip edemezsin."}, 400
        flash("Kendini takip edemezsin.", "err")
        return redirect(request.referrer or "/hesap/profil")
    db = SessionLocal()
    try:
        try:
            following = follow_toggle(db, user.id, target_id)
        except LookupError:
            if _wants_json():
                return {"ok": False, "error": "Kullanıcı bulunamadı."}, 404
            flash("Kullanıcı bulunamadı.", "err")
            return redirect(request.referrer or "/hesap/profil")
        db.commit()
        if _wants_json():
            return {"ok": True, "following": following, "user_id": target_id}
        flash("Takip edildi." if following else "Takip bırakıldı.", "ok")
        return redirect(request.referrer or "/hesap/profil?tab=friends")
    finally:
        db.close()


@app.route("/hesap/profil/takip")
@login_required
def hesap_profil_takip_liste():
    from feed_social import follow_counts, follow_network

    user = load_user()
    list_tab = (request.args.get("list") or "following").strip().lower()
    if list_tab not in ("following", "followers"):
        list_tab = "following"
    offset = max(0, int(request.args.get("offset") or 0))
    db = SessionLocal()
    try:
        u = db.get(User, user.id)
        if not u:
            return redirect("/giris?next=/hesap/profil/takip")
        network, has_more = follow_network(
            db,
            u.id,
            list_kind=list_tab,
            viewer_id=u.id,
            limit=40,
            offset=offset,
        )
        counts = follow_counts(db, u.id)
        return render_template(
            "profile_follow.html",
            u=u,
            list_tab=list_tab,
            network=network,
            network_has_more=has_more,
            next_offset=offset + len(network),
            counts=counts,
            nav="feed",
        )
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
        if not post or post.status != "approved":
            if _wants_json():
                return {"ok": False, "error": "Gönderi bulunamadı."}, 404
            flash("Gönderi bulunamadı veya henüz onaylanmadı.", "err")
            return redirect("/hesap/profil")
        like = db.query(PostLike).filter(PostLike.user_id == user.id, PostLike.post_id == post_id).first()
        liked = False
        if like:
            db.delete(like)
            post.likes_count = max(0, int(post.likes_count or 0) - 1)
        else:
            db.add(PostLike(user_id=user.id, post_id=post_id))
            post.likes_count = int(post.likes_count or 0) + 1
            liked = True
        db.commit()
        if _wants_json():
            return {"ok": True, "liked": liked, "likes": int(post.likes_count or 0)}
        return redirect(request.referrer or "/hesap/profil")
    finally:
        db.close()


@app.route("/hesap/profil/comment/<int:post_id>", methods=["POST"])
@login_required
def hesap_profil_comment(post_id: int):
    from content_filter import filter_profanity, profanity_ok
    from models import PostComment, UserPost

    user = load_user()
    raw = (request.form.get("body") or "").strip()[:500]
    if not raw:
        if _wants_json():
            return {"ok": False, "error": "Yorum boş olamaz."}, 400
        flash("Yorum boş olamaz.", "err")
        return redirect(request.referrer or "/feed")
    if not rate_ok("feed_comment", limit=30):
        if _wants_json():
            return {"ok": False, "error": "Çok sık deneme. Biraz bekle."}, 429
        flash("Çok sık deneme. Biraz bekle.", "err")
        return redirect(request.referrer or "/feed")

    body = filter_profanity(raw)
    if not profanity_ok(body):
        if _wants_json():
            return {"ok": False, "error": "Yorum uygun değil."}, 400
        flash("Yorum uygun değil.", "err")
        return redirect(request.referrer or "/feed")

    db = SessionLocal()
    try:
        post = db.get(UserPost, post_id)
        if not post or post.status != "approved":
            if _wants_json():
                return {"ok": False, "error": "Gönderi bulunamadı."}, 404
            flash("Gönderi bulunamadı.", "err")
            return redirect(request.referrer or "/feed")
        comment = PostComment(post_id=post_id, user_id=user.id, body=body, status="approved")
        db.add(comment)
        post.comments_count = int(post.comments_count or 0) + 1
        db.commit()
        db.refresh(comment)
        u = db.get(User, user.id)
        payload = {
            "ok": True,
            "comment": {
                "id": comment.id,
                "user_name": u.display_name() if u else (user.name or "Üye"),
                "body": body,
                "ago": "az önce",
            },
            "comments": int(post.comments_count or 0),
        }
        if _wants_json():
            return payload
        flash("Yorumun yayınlandı.", "ok")
        return redirect(request.referrer or "/feed")
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
        return redirect("/tesekkur?from=email")
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


@app.route("/api/analytics/beacon", methods=["POST"])
def api_analytics_beacon():
    """İstemci tıklama + sayfa süresi olayları (sendBeacon)."""
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False}), 400
    from analytics import ingest_beacon

    db = SessionLocal()
    try:
        ok = ingest_beacon(db, request=request, payload=payload)
        if ok:
            db.commit()
        return ("", 204) if ok else (jsonify({"ok": False}), 200)
    except Exception:
        db.rollback()
        return jsonify({"ok": False}), 500
    finally:
        db.close()


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
