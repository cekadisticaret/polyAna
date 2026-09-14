"""Admin HTML — Ventic UI · kapsamlı yönetim paneli."""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request

from admin_forms import (
    build_extra_from_form,
    format_list_text,
    format_menu_text,
    format_staff_text,
    save_upload,
)
from auth import admin_required, hash_password, load_user
from catalog import CATEGORIES, ILCELER, parse_dt, tags_dump, tags_load, unique_slug
from models import (
    ActivityLog,
    Campaign,
    ClaimRequest,
    Favorite,
    Place,
    PlacePhoto,
    Review,
    SeoAudit,
    SessionLocal,
    SportMatch,
    User,
    UserPost,
    UserVisit,
    member_login_query,
    place_extra,
    set_place_extra,
)

bp = Blueprint("admin_pages", __name__)


@bp.context_processor
def _inject_admin_sidebar():
    """Tüm admin şablonlarında yetki değişkenleri (view unutsa bile)."""
    from admin_permissions import is_super_admin, panel_perms

    user = load_user()
    return {
        "admin_perms": panel_perms(user) if user else set(),
        "is_super_admin": is_super_admin(user) if user else False,
    }


# Admin → Kategoriler menüsünde yönetilen içerik türleri
ADMIN_CATEGORY_GROUPS = (
    {
        "label": "Sağlık",
        "keys": ("hospital", "doctor", "dentist", "vet"),
    },
    {
        "label": "Eğitim",
        "keys": ("school",),
    },
    {
        "label": "Rehber",
        "keys": ("food", "visit", "hotel", "camp", "shop", "market", "sport", "family"),
    },
    {
        "label": "Etkinlik",
        "keys": ("concert", "theater", "cinema", "fun", "event", "org"),
    },
)
ADMIN_CATEGORY_KEYS = tuple(k for g in ADMIN_CATEGORY_GROUPS for k in g["keys"])


def _category_meta(key: str) -> dict:
    from catalog import CAT_BY_KEY

    c = CAT_BY_KEY.get(key) or {}
    return {
        "key": key,
        "label": c.get("label") or key,
        "path": c.get("path") or "/",
        "hint": c.get("hint") or "",
    }


def _category_counts(db) -> dict[str, int]:
    from sqlalchemy import func

    rows = (
        db.query(Place.category, func.count(Place.id))
        .filter(Place.status == "approved", Place.category.in_(ADMIN_CATEGORY_KEYS))
        .group_by(Place.category)
        .all()
    )
    return {k: n for k, n in rows}


def _badge_counts(db) -> dict:
    pending_reviews = db.query(Review).filter(Review.status == "pending").count()
    pending_posts = db.query(UserPost).filter(UserPost.status == "pending", UserPost.privacy == "public").count()
    pending_visit_notes = (
        db.query(UserVisit)
        .filter(UserVisit.status == "pending", UserVisit.note != "")
        .count()
    )
    pending_photos = db.query(PlacePhoto).filter(PlacePhoto.status == "pending").count()
    return {
        "pending_places": db.query(Place).filter(Place.status == "pending").count(),
        "pending_claims": db.query(ClaimRequest).filter(ClaimRequest.status == "pending").count(),
        "pending_photos": pending_photos,
        "pending_reviews": pending_reviews,
        "pending_posts": pending_posts,
        "pending_visit_notes": pending_visit_notes,
        "pending_moderation": pending_reviews + pending_posts + pending_visit_notes,
    }


def _admin_ctx(db, admin_nav: str) -> dict:
    from admin_permissions import is_super_admin, panel_perms

    user = load_user()
    perms = panel_perms(user) if user else set()
    return {
        "admin_nav": admin_nav,
        "nav": "admin",
        "admin_perms": perms,
        "is_super_admin": is_super_admin(user) if user else False,
        **_badge_counts(db),
    }


def _apply_place_form(p: Place, form, files=None) -> None:
    p.title = (form.get("title") or p.title or "").strip()
    new_slug = (form.get("slug") or p.slug or "").strip()
    if new_slug:
        p.slug = new_slug
    p.category = (form.get("category") or p.category or "visit").strip()
    p.subcategory = (form.get("subcategory") or "").strip()
    p.ilce = (form.get("ilce") or "").strip()
    p.address = (form.get("address") or "").strip()
    p.phone = (form.get("phone") or "").strip()
    p.web = (form.get("web") or "").strip()
    p.hours_text = (form.get("hours_text") or "").strip()
    p.price_band = (form.get("price_band") or "").strip()
    p.blurb = (form.get("blurb") or "").strip()
    p.body = (form.get("body") or "").strip()
    p.venue_name = (form.get("venue_name") or "").strip()
    p.tags = tags_dump(form.get("tags") or "")
    p.featured = form.get("featured") == "1"
    p.starts_at = parse_dt(form.get("starts_at"))
    p.ends_at = parse_dt(form.get("ends_at"))
    p.instagram = (form.get("instagram") or "").strip()
    p.whatsapp = (form.get("whatsapp") or "").strip()
    p.ticket_price = (form.get("ticket_price") or "").strip()
    p.ticket_url = (form.get("ticket_url") or "").strip()
    p.menu_text = (form.get("menu_text") or "").strip()
    p.plan_tier = (form.get("plan_tier") or p.plan_tier or "free").strip() or "free"
    status = (form.get("status") or "").strip()
    if status in ("pending", "approved", "rejected"):
        p.status = status
    try:
        p.lat = float(form.get("lat")) if form.get("lat") else None
        p.lng = float(form.get("lng")) if form.get("lng") else None
    except ValueError:
        pass
    try:
        p.rating_admin = float(form.get("rating_admin")) if form.get("rating_admin") else None
    except ValueError:
        pass
    try:
        p.est_meal_tl = int(form.get("est_meal_tl") or 0)
    except ValueError:
        p.est_meal_tl = 0

    img_url = (form.get("img_url") or "").strip()
    uploaded = None
    cur_ex = place_extra(p)
    if files:
        uploaded, _err = save_upload(files.get("img_file"), category=p.category or "misc")
        gal_file = files.get("gallery_file")
        if gal_file:
            gurl, _gerr = save_upload(gal_file, category=p.category or "misc")
            if gurl:
                gal = list(cur_ex.get("gallery") or [])
                gal.append(gurl)
                cur_ex["gallery"] = gal
    if uploaded:
        p.img_url = uploaded
    elif img_url:
        p.img_url = img_url

    built = build_extra_from_form(form, cur_ex)
    # uploaded gallery image already in cur_ex — keep if form emptied accidentally
    if cur_ex.get("gallery") and not built.get("gallery"):
        built["gallery"] = cur_ex["gallery"]
    set_place_extra(p, built)
    if not p.menu_text and built.get("menu"):
        p.menu_text = format_menu_text(built["menu"])


def _apply_match_form(m: SportMatch, form) -> None:
    m.season = (form.get("season") or m.season or "2026-27").strip()
    m.competition = (form.get("competition") or "1. Lig").strip()
    m.home_team = (form.get("home_team") or "").strip()
    m.away_team = (form.get("away_team") or "").strip()
    m.venue = (form.get("venue") or "").strip()
    m.ticket_price = (form.get("ticket_price") or "").strip()
    m.ticket_url = (form.get("ticket_url") or "").strip()
    m.note = (form.get("note") or "").strip()
    m.status = (form.get("status") or "scheduled").strip() or "scheduled"
    m.is_home = form.get("is_home") == "1"
    m.kickoff_at = parse_dt(form.get("kickoff_at"))
    try:
        m.week = int(form.get("week")) if form.get("week") else None
    except ValueError:
        m.week = None
    try:
        hs = form.get("home_score")
        as_ = form.get("away_score")
        m.home_score = int(hs) if hs not in (None, "") else None
        m.away_score = int(as_) if as_ not in (None, "") else None
    except ValueError:
        pass
    if m.home_score is not None and m.away_score is not None:
        m.status = "played"


@bp.route("/admin")
@admin_required
def queue():
    status = (request.args.get("status") or "pending").strip()
    if status not in ("pending", "approved", "rejected"):
        status = "pending"
    cat = (request.args.get("cat") or "").strip()
    q = (request.args.get("q") or "").strip()
    db = SessionLocal()
    try:
        query = db.query(Place).filter(Place.status == status)
        if cat:
            query = query.filter(Place.category == cat)
        if q:
            like = f"%{q}%"
            query = query.filter(
                (Place.title.ilike(like)) | (Place.slug.ilike(like)) | (Place.address.ilike(like))
            )
        rows = query.order_by(Place.id.desc()).limit(300).all()
        counts = {
            "pending": db.query(Place).filter(Place.status == "pending").count(),
            "approved": db.query(Place).filter(Place.status == "approved").count(),
            "rejected": db.query(Place).filter(Place.status == "rejected").count(),
        }
        items = []
        for p in rows:
            submitter = db.get(User, p.submitted_by_id) if p.submitted_by_id else None
            items.append({"place": p, "submitter": submitter})
        return render_template(
            "admin/queue.html",
            items=items,
            status=status,
            counts=counts,
            categories=CATEGORIES,
            cat=cat,
            q=q,
            **_admin_ctx(db, "queue"),
        )
    finally:
        db.close()


@bp.route("/admin/dashboard")
@admin_required
def dashboard():
    from sqlalchemy import func

    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=7)
        kpi = {
            "places": db.query(Place).filter(Place.status == "approved").count(),
            "events": db.query(Place).filter(
                Place.status == "approved",
                Place.category.in_(("event", "concert", "theater", "cinema")),
            ).count(),
            "users": db.query(User).count(),
            "reviews": db.query(Review).count(),
            "favorites": db.query(Favorite).count(),
            "pending_places": db.query(Place).filter(Place.status == "pending").count(),
            "pending_claims": db.query(ClaimRequest).filter(ClaimRequest.status == "pending").count(),
            "pending_campaigns": db.query(Campaign).filter(Campaign.status == "pending").count(),
            "pending_photos": db.query(PlacePhoto).filter(PlacePhoto.status == "pending").count(),
            "restaurants": db.query(Place)
            .filter(Place.status == "approved", Place.category == "food")
            .count(),
            "markets": db.query(Place)
            .filter(Place.status == "approved", Place.category == "market")
            .count(),
            "hospitals": db.query(Place)
            .filter(Place.status == "approved", Place.category == "hospital")
            .count(),
            "doctors": db.query(Place)
            .filter(Place.status == "approved", Place.category == "doctor")
            .count(),
            "dentists": db.query(Place)
            .filter(Place.status == "approved", Place.category == "dentist")
            .count(),
            "vets": db.query(Place)
            .filter(Place.status == "approved", Place.category == "vet")
            .count(),
            "hotels": db.query(Place)
            .filter(Place.status == "approved", Place.category == "hotel")
            .count(),
            "weddings": db.query(Place)
            .filter(Place.status == "approved", Place.category == "wedding")
            .count(),
            "nightlife": db.query(Place)
            .filter(Place.status == "approved", Place.category == "nightlife")
            .count(),
            "matches": db.query(SportMatch).filter(SportMatch.club == "bursaspor").count(),
            "logins_7d": member_login_query(db)
            .filter(ActivityLog.created_at >= since)
            .count(),
            "registers_7d": db.query(ActivityLog).filter(
                ActivityLog.kind == "register", ActivityLog.created_at >= since
            ).count(),
            "submits_7d": db.query(ActivityLog).filter(
                ActivityLog.kind == "place_submit", ActivityLog.created_at >= since
            ).count(),
        }
        try:
            import json as _json

            _neo = os.path.join(os.path.dirname(__file__), "data", "nobetci_eczaneler.json")
            with open(_neo, encoding="utf-8") as _f:
                _feed = _json.load(_f)
            kpi["pharmacies"] = int(_feed.get("total") or len(_feed.get("pharmacies") or []))
        except Exception:
            kpi["pharmacies"] = 0
        try:
            from news_pages import load_news_feed

            kpi["news"] = len(load_news_feed().get("articles") or [])
        except Exception:
            kpi["news"] = 0
        from analytics import (
            engagement_summary as traffic_engagement,
            summary as traffic_summary,
            top_clicks as traffic_top_clicks,
            top_pages as traffic_top_pages,
            top_place_clicks,
        )

        traffic = traffic_summary(db, days=14)
        page_traffic = traffic_top_pages(db, days=7, limit=30)
        engagement = traffic_engagement(db, days=7)
        click_stats = traffic_top_clicks(db, days=7, limit=15)
        place_clicks = top_place_clicks(db, limit=8)
        kpi["today_visitors"] = traffic["today_visitors"]
        kpi["today_pageviews"] = traffic["today_pageviews"]
        kpi["d7_visitors"] = traffic["d7_visitors"]
        kpi["d7_pageviews"] = traffic["d7_pageviews"]
        kpi["total_visitors"] = traffic["total_visitors"]
        kpi["total_pageviews"] = traffic["total_pageviews"]
        from seo_status import collect as seo_collect
        from flask import current_app

        seo_status = seo_collect(app=current_app._get_current_object(), db=db)
        kpi["seo_grade"] = seo_status["grade"]
        kpi["seo_ok"] = seo_status["ok_n"]
        kpi["seo_total"] = seo_status["total"]
        kpi["seo_gsc"] = seo_status.get("google_connected") or seo_status.get("google_token_set")
        by_cat = (
            db.query(Place.category, func.count(Place.id))
            .filter(Place.status == "approved")
            .group_by(Place.category)
            .all()
        )
        recent_users = db.query(User).order_by(User.id.desc()).limit(8).all()
        recent_activity = db.query(ActivityLog).order_by(ActivityLog.id.desc()).limit(12).all()
        pending = (
            db.query(Place)
            .filter(Place.status == "pending")
            .order_by(Place.id.desc())
            .limit(8)
            .all()
        )
        badges = _badge_counts(db)
        badges["pending_campaigns"] = kpi["pending_campaigns"]
        from admin_dashboard_charts import build_dashboard_charts

        chart_data = build_dashboard_charts(
            db,
            traffic=traffic,
            page_traffic=page_traffic,
            engagement=engagement,
            click_stats=click_stats,
            by_cat=by_cat,
            badges=badges,
        )
        login_stats = chart_data.get("logins") or {}
        kpi["logins_today"] = int(login_stats.get("today") or 0)
        kpi["logins_yesterday"] = int(login_stats.get("yesterday") or 0)
        kpi["logins_14d"] = int(login_stats.get("total") or 0)
        return render_template(
            "admin/dashboard.html",
            kpi=kpi,
            traffic=traffic,
            page_traffic=page_traffic,
            engagement=engagement,
            click_stats=click_stats,
            place_clicks=place_clicks,
            seo_status=seo_status,
            by_cat=by_cat,
            chart_data=chart_data,
            recent_users=recent_users,
            recent_activity=recent_activity,
            pending=pending,
            **_admin_ctx(db, "dashboard"),
        )
    finally:
        db.close()


@bp.route("/admin/photos")
@admin_required
def photos():
    st = (request.args.get("status") or "pending").strip()
    db = SessionLocal()
    try:
        q = db.query(PlacePhoto).order_by(PlacePhoto.id.desc())
        if st in ("pending", "approved", "rejected"):
            q = q.filter(PlacePhoto.status == st)
        rows = q.limit(200).all()
        enriched = []
        for ph in rows:
            place = db.get(Place, ph.place_id)
            user = db.get(User, ph.user_id)
            enriched.append({"photo": ph, "place": place, "user": user})
        return render_template(
            "admin/photos.html",
            rows=enriched,
            status=st,
            **_admin_ctx(db, "photos"),
        )
    finally:
        db.close()


@bp.route("/admin/photos/<int:pid>/<action>", methods=["POST"])
@admin_required
def photo_action(pid: int, action: str):
    db = SessionLocal()
    try:
        ph = db.get(PlacePhoto, pid)
        if ph and action in ("approve", "reject"):
            ph.status = "approved" if action == "approve" else "rejected"
            db.commit()
            flash("Fotoğraf güncellendi.", "ok")
        return redirect(request.referrer or "/admin/photos")
    finally:
        db.close()


@bp.route("/admin/seo")
@admin_required
def seo_panel():
    from seo_status import collect as seo_collect, google_verification_token
    from flask import current_app

    db = SessionLocal()
    try:
        rows = db.query(SeoAudit).order_by(SeoAudit.id.desc()).limit(20).all()
        latest = rows[0] if rows else None
        issues = []
        if latest:
            try:
                import json

                issues = json.loads(latest.issues_json or "[]")
            except Exception:
                issues = []
        seo_status = seo_collect(app=current_app._get_current_object(), db=db)
        return render_template(
            "admin/seo.html",
            rows=rows,
            latest=latest,
            issues=issues[:200],
            seo_status=seo_status,
            gsc_token=google_verification_token(),
            **_admin_ctx(db, "seo"),
        )
    finally:
        db.close()


@bp.route("/admin/seo/run", methods=["POST"])
@admin_required
def seo_run():
    import seo_nightly

    seo_nightly.main()
    flash("SEO denetimi çalıştırıldı.", "ok")
    return redirect("/admin/seo")


@bp.route("/admin/seo/gsc", methods=["POST"])
@admin_required
def seo_gsc_save():
    from seo_status import save_cfg
    from datetime import date

    token = (request.form.get("google_site_verification") or "").strip()
    # sadece içerik kısmı — kullanıcı bazen tüm meta'yı yapıştırır
    m = re.search(r'content=["\']([^"\']+)["\']', token, re.I)
    if m:
        token = m.group(1).strip()
    if token and not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", token):
        flash("Geçersiz doğrulama kodu.", "err")
        return redirect("/admin/seo")
    connected = request.form.get("gsc_connected") == "1"
    patch = {
        "google_site_verification": token,
        "gsc_connected": connected or bool(token),
        "gsc_property": (request.form.get("gsc_property") or "bursaapp.com").strip() or "bursaapp.com",
    }
    if patch["gsc_connected"] and not _load_connected_at():
        patch["gsc_connected_at"] = date.today().isoformat()
        patch["gsc_note"] = (
            "Domain mülk Search Console’da açık. Performans/dizin Google’da işleniyor; "
            "Site Haritaları’na sitemap.xml ekleyin."
        )
    save_cfg(patch)
    flash("Google / SEO ayarları kaydedildi.", "ok")
    return redirect("/admin/seo")


def _load_connected_at() -> str:
    try:
        from seo_status import _load_cfg

        return str(_load_cfg().get("gsc_connected_at") or "")
    except Exception:
        return ""
@bp.route("/admin/users")
@admin_required
def users():
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "all").strip()
    if status not in ("all", "active", "inactive"):
        status = "all"
    db = SessionLocal()
    try:
        query = db.query(User).order_by(User.id.desc())
        if status == "active":
            query = query.filter(User.is_active.is_(True))
        elif status == "inactive":
            query = query.filter(User.is_active.is_(False))
        if q:
            like = f"%{q}%"
            query = query.filter((User.email.ilike(like)) | (User.name.ilike(like)))
        rows = query.limit(300).all()
        counts = {
            "all": db.query(User).count(),
            "active": db.query(User).filter(User.is_active.is_(True)).count(),
            "inactive": db.query(User).filter(User.is_active.is_(False)).count(),
        }
        return render_template(
            "admin/users.html",
            rows=rows,
            q=q,
            status=status,
            counts=counts,
            **_admin_ctx(db, "users"),
        )
    finally:
        db.close()


@bp.route("/admin/users/<int:uid>/toggle", methods=["POST"])
@admin_required
def user_toggle_active(uid: int):
    cur = load_user()
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        if not u:
            flash("Üye bulunamadı.", "err")
            return redirect(request.referrer or "/admin/users")
        if cur and u.id == cur.id:
            flash("Kendi hesabınızı pasif yapamazsınız.", "err")
            return redirect(request.referrer or "/admin/users")
        new_active = not bool(u.is_active)
        if not new_active and u.role == "admin":
            admins = db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()
            if admins <= 1:
                flash("Son aktif admin pasif yapılamaz.", "err")
                return redirect(request.referrer or "/admin/users")
        u.is_active = new_active
        db.commit()
        flash(f"{u.name or u.email} {'aktif edildi' if new_active else 'pasif yapıldı'}.", "ok")
        return redirect(request.referrer or "/admin/users")
    finally:
        db.close()


@bp.route("/admin/activity")
@admin_required
def activity():
    kind = (request.args.get("kind") or "").strip()
    db = SessionLocal()
    try:
        query = db.query(ActivityLog).order_by(ActivityLog.id.desc())
        if kind:
            query = query.filter(ActivityLog.kind == kind)
        rows = query.limit(400).all()
        kinds = [
            r[0]
            for r in db.query(ActivityLog.kind).distinct().order_by(ActivityLog.kind).all()
        ]
        return render_template(
            "admin/activity.html",
            rows=rows,
            kind=kind,
            kinds=kinds,
            **_admin_ctx(db, "activity"),
        )
    finally:
        db.close()


@bp.route("/admin/reviews")
@admin_required
def reviews():
    status = (request.args.get("status") or "pending").strip()
    if status not in ("pending", "approved", "rejected", "all"):
        status = "pending"
    db = SessionLocal()
    try:
        query = db.query(Review).order_by(Review.id.desc())
        if status != "all":
            query = query.filter(Review.status == status)
        rows = query.limit(200).all()
        items = []
        for r in rows:
            items.append(
                {
                    "review": r,
                    "place": db.get(Place, r.place_id),
                    "user": db.get(User, r.user_id),
                }
            )
        counts = {
            "pending": db.query(Review).filter(Review.status == "pending").count(),
            "approved": db.query(Review).filter(Review.status == "approved").count(),
            "rejected": db.query(Review).filter(Review.status == "rejected").count(),
        }
        return render_template(
            "admin/reviews.html",
            items=items,
            status=status,
            counts=counts,
            **_admin_ctx(db, "reviews"),
        )
    finally:
        db.close()


@bp.route("/admin/reviews/<int:rid>/approve", methods=["POST"])
@admin_required
def review_approve(rid: int):
    db = SessionLocal()
    try:
        r = db.get(Review, rid)
        if r:
            r.status = "approved"
            r.updated_at = datetime.utcnow()
            p = db.get(Place, r.place_id)
            if p:
                from models import recompute_place_rating

                recompute_place_rating(db, p)
            u = db.get(User, r.user_id)
            if u:
                from user_points import award_review_approved

                award_review_approved(db, u.id, r.id)
            db.commit()
            flash("Yorum onaylandı.", "ok")
        return redirect(request.referrer or "/admin/reviews?status=pending")
    finally:
        db.close()


@bp.route("/admin/reviews/<int:rid>/reject", methods=["POST"])
@admin_required
def review_reject(rid: int):
    db = SessionLocal()
    try:
        r = db.get(Review, rid)
        if r:
            r.status = "rejected"
            r.updated_at = datetime.utcnow()
            p = db.get(Place, r.place_id)
            if p:
                from models import recompute_place_rating

                recompute_place_rating(db, p)
            db.commit()
            flash("Yorum reddedildi.", "ok")
        return redirect(request.referrer or "/admin/reviews?status=pending")
    finally:
        db.close()


@bp.route("/admin/posts")
@admin_required
def posts():
    status = (request.args.get("status") or "pending").strip()
    if status not in ("pending", "approved", "rejected", "all"):
        status = "pending"
    db = SessionLocal()
    try:
        query = db.query(UserPost).order_by(UserPost.id.desc())
        if status != "all":
            query = query.filter(UserPost.status == status)
        rows = query.limit(200).all()
        items = []
        for post in rows:
            items.append(
                {
                    "post": post,
                    "user": db.get(User, post.user_id),
                    "place": db.get(Place, post.place_id) if post.place_id else None,
                }
            )
        counts = {
            "pending": db.query(UserPost).filter(UserPost.status == "pending").count(),
            "approved": db.query(UserPost).filter(UserPost.status == "approved").count(),
            "rejected": db.query(UserPost).filter(UserPost.status == "rejected").count(),
        }
        return render_template(
            "admin/posts.html",
            items=items,
            status=status,
            counts=counts,
            **_admin_ctx(db, "posts"),
        )
    finally:
        db.close()


@bp.route("/admin/posts/<int:pid>/approve", methods=["POST"])
@admin_required
def post_approve(pid: int):
    db = SessionLocal()
    try:
        post = db.get(UserPost, pid)
        if post:
            post.status = "approved"
            db.commit()
            flash("Gönderi onaylandı.", "ok")
        return redirect(request.referrer or "/admin/posts?status=pending")
    finally:
        db.close()


@bp.route("/admin/posts/<int:pid>/reject", methods=["POST"])
@admin_required
def post_reject(pid: int):
    db = SessionLocal()
    try:
        post = db.get(UserPost, pid)
        if post:
            post.status = "rejected"
            db.commit()
            flash("Gönderi reddedildi.", "ok")
        return redirect(request.referrer or "/admin/posts?status=pending")
    finally:
        db.close()


@bp.route("/admin/visit-notes")
@admin_required
def visit_notes():
    status = (request.args.get("status") or "pending").strip()
    if status not in ("pending", "approved", "rejected", "all"):
        status = "pending"
    db = SessionLocal()
    try:
        query = db.query(UserVisit).filter(UserVisit.note != "").order_by(UserVisit.id.desc())
        if status != "all":
            query = query.filter(UserVisit.status == status)
        rows = query.limit(200).all()
        items = []
        for v in rows:
            items.append(
                {
                    "visit": v,
                    "user": db.get(User, v.user_id),
                    "place": db.get(Place, v.place_id),
                }
            )
        counts = {
            "pending": db.query(UserVisit).filter(UserVisit.status == "pending", UserVisit.note != "").count(),
            "approved": db.query(UserVisit).filter(UserVisit.status == "approved", UserVisit.note != "").count(),
            "rejected": db.query(UserVisit).filter(UserVisit.status == "rejected", UserVisit.note != "").count(),
        }
        return render_template(
            "admin/visit_notes.html",
            items=items,
            status=status,
            counts=counts,
            **_admin_ctx(db, "visit_notes"),
        )
    finally:
        db.close()


@bp.route("/admin/visit-notes/<int:vid>/approve", methods=["POST"])
@admin_required
def visit_note_approve(vid: int):
    db = SessionLocal()
    try:
        v = db.get(UserVisit, vid)
        if v:
            v.status = "approved"
            from feed_social import ensure_visit_feed_post

            ensure_visit_feed_post(db, v)
            db.commit()
            flash("Ziyaret notu onaylandı.", "ok")
        return redirect(request.referrer or "/admin/visit-notes?status=pending")
    finally:
        db.close()


@bp.route("/admin/visit-notes/<int:vid>/reject", methods=["POST"])
@admin_required
def visit_note_reject(vid: int):
    db = SessionLocal()
    try:
        v = db.get(UserVisit, vid)
        if v:
            v.status = "rejected"
            db.commit()
            flash("Ziyaret notu reddedildi.", "ok")
        return redirect(request.referrer or "/admin/visit-notes?status=pending")
    finally:
        db.close()


@bp.route("/admin/campaigns")
@admin_required
def campaigns():
    db = SessionLocal()
    try:
        rows = db.query(Campaign).order_by(Campaign.id.desc()).limit(100).all()
        items = []
        for c in rows:
            items.append({"campaign": c, "place": db.get(Place, c.place_id)})
        return render_template(
            "admin/campaigns.html",
            items=items,
            **_admin_ctx(db, "campaigns"),
        )
    finally:
        db.close()


@bp.route("/admin/claims")
@admin_required
def claims():
    db = SessionLocal()
    try:
        rows = (
            db.query(ClaimRequest)
            .filter(ClaimRequest.status == "pending")
            .order_by(ClaimRequest.id.desc())
            .all()
        )
        items = []
        for c in rows:
            p = db.get(Place, c.place_id)
            u = db.get(User, c.user_id)
            items.append({"claim": c, "place": p, "user": u})
        return render_template("admin/claims.html", items=items, **_admin_ctx(db, "claims"))
    finally:
        db.close()


@bp.route("/admin/claims/<int:cid>/approve", methods=["POST"])
@admin_required
def claim_approve(cid: int):
    db = SessionLocal()
    try:
        c = db.get(ClaimRequest, cid)
        if c:
            c.status = "approved"
            c.reviewed_at = datetime.utcnow()
            p = db.get(Place, c.place_id)
            if p:
                p.owner_user_id = c.user_id
                p.claim_status = "approved"
            db.commit()
            flash("Sahiplenme onaylandı.", "ok")
        return redirect("/admin/claims")
    finally:
        db.close()


@bp.route("/admin/claims/<int:cid>/reject", methods=["POST"])
@admin_required
def claim_reject(cid: int):
    db = SessionLocal()
    try:
        c = db.get(ClaimRequest, cid)
        if c:
            c.status = "rejected"
            c.reviewed_at = datetime.utcnow()
            p = db.get(Place, c.place_id)
            if p:
                p.claim_status = "rejected"
            db.commit()
            flash("Sahiplenme reddedildi.", "ok")
        return redirect("/admin/claims")
    finally:
        db.close()


@bp.route("/admin/<int:pid>/approve", methods=["POST"])
@admin_required
def approve(pid: int):
    user = load_user()
    db = SessionLocal()
    try:
        p = db.get(Place, pid)
        if p:
            was_pending = p.status == "pending"
            p.status = "approved"
            p.reviewed_by_id = user.id if user else None
            p.reviewed_at = datetime.utcnow()
            p.reject_reason = ""
            db.commit()
            if was_pending:
                try:
                    from notify import notify_place_approved

                    notify_place_approved(db, p)
                except Exception:
                    pass
            flash("Onaylandı.", "ok")
        return redirect(request.referrer or "/admin?status=pending")
    finally:
        db.close()


@bp.route("/admin/<int:pid>/reject", methods=["POST"])
@admin_required
def reject(pid: int):
    user = load_user()
    reason = (request.form.get("reason") or "").strip()
    db = SessionLocal()
    try:
        p = db.get(Place, pid)
        if p:
            p.status = "rejected"
            p.reviewed_by_id = user.id if user else None
            p.reviewed_at = datetime.utcnow()
            p.reject_reason = reason
            db.commit()
            flash("Reddedildi.", "ok")
        return redirect(request.referrer or "/admin?status=pending")
    finally:
        db.close()


@bp.route("/admin/<int:pid>/delete", methods=["POST"])
@admin_required
def delete_place(pid: int):
    db = SessionLocal()
    try:
        p = db.get(Place, pid)
        if p:
            db.delete(p)
            db.commit()
            flash("Silindi.", "ok")
        return redirect("/admin?status=approved")
    finally:
        db.close()


@bp.route("/admin/new", methods=["GET", "POST"])
@admin_required
def new_place():
    db = SessionLocal()
    try:
        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            if not title:
                flash("Başlık zorunlu.", "err")
                return redirect("/admin/new")
            slug_in = (request.form.get("slug") or title).strip()
            slug = unique_slug(db, slug_in)
            p = Place(title=title, slug=slug, category="visit", status="approved", extra_json="{}")
            _apply_place_form(p, request.form, request.files)
            p.slug = unique_slug(db, p.slug or slug)
            if not p.category:
                p.category = "visit"
            db.add(p)
            db.commit()
            flash("Yeni kayıt eklendi.", "ok")
            return redirect(f"/admin/{p.id}/edit")
        blank = Place(title="", slug="", category="food", status="approved", extra_json="{}")
        return render_template(
            "admin/edit.html",
            place=blank,
            is_new=True,
            categories=CATEGORIES,
            ilceler=ILCELER,
            tags=[],
            extra={},
            menu_lines="",
            fee_lines="",
            services_text="",
            staff_lines="",
            gallery_urls="",
            **_admin_ctx(db, "queue"),
        )
    finally:
        db.close()


@bp.route("/admin/<int:pid>/edit", methods=["GET", "POST"])
@admin_required
def edit(pid: int):
    db = SessionLocal()
    try:
        p = db.get(Place, pid)
        if not p:
            flash("Yok", "err")
            return redirect("/admin")
        if request.method == "POST":
            old_slug = p.slug
            _apply_place_form(p, request.form, request.files)
            if p.slug != old_slug:
                p.slug = unique_slug(db, p.slug, exclude_id=p.id)
            db.commit()
            flash("Kaydedildi.", "ok")
            return redirect(f"/admin/{pid}/edit")
        ex = place_extra(p)
        return render_template(
            "admin/edit.html",
            place=p,
            is_new=False,
            categories=CATEGORIES,
            ilceler=ILCELER,
            tags=tags_load(p.tags),
            extra=ex,
            menu_lines=format_menu_text(ex.get("menu") or []),
            fee_lines=format_list_text(ex.get("fees") or []),
            services_text="\n".join(ex.get("services") or []),
            staff_lines=format_staff_text(ex.get("staff") or []),
            gallery_urls="\n".join(ex.get("gallery") or []),
            **_admin_ctx(db, "queue"),
        )
    finally:
        db.close()


@bp.route("/admin/matches")
@admin_required
def matches():
    db = SessionLocal()
    try:
        rows = (
            db.query(SportMatch)
            .filter(SportMatch.club == "bursaspor")
            .order_by(SportMatch.week.asc().nullslast(), SportMatch.kickoff_at.asc().nullslast())
            .all()
        )
        return render_template(
            "admin/matches.html",
            rows=rows,
            **_admin_ctx(db, "matches"),
        )
    finally:
        db.close()


@bp.route("/admin/matches/new", methods=["POST"])
@admin_required
def match_new():
    db = SessionLocal()
    try:
        m = SportMatch(club="bursaspor")
        _apply_match_form(m, request.form)
        db.add(m)
        db.commit()
        flash("Maç eklendi.", "ok")
        return redirect("/admin/matches")
    finally:
        db.close()


@bp.route("/admin/matches/<int:mid>/edit", methods=["POST"])
@admin_required
def match_edit(mid: int):
    db = SessionLocal()
    try:
        m = db.get(SportMatch, mid)
        if m:
            _apply_match_form(m, request.form)
            db.commit()
            flash("Maç güncellendi.", "ok")
        return redirect("/admin/matches")
    finally:
        db.close()


@bp.route("/admin/matches/<int:mid>/delete", methods=["POST"])
@admin_required
def match_delete(mid: int):
    db = SessionLocal()
    try:
        m = db.get(SportMatch, mid)
        if m:
            db.delete(m)
            db.commit()
            flash("Maç silindi.", "ok")
        return redirect("/admin/matches")
    finally:
        db.close()


@bp.route("/admin/categories")
@admin_required
def categories_index():
    db = SessionLocal()
    try:
        counts = _category_counts(db)
        groups = []
        for g in ADMIN_CATEGORY_GROUPS:
            items = []
            for key in g["keys"]:
                meta = _category_meta(key)
                items.append({**meta, "count": counts.get(key, 0)})
            groups.append({"label": g["label"], "items": items})
        return render_template(
            "admin/categories_index.html",
            groups=groups,
            **_admin_ctx(db, "categories"),
        )
    finally:
        db.close()


@bp.route("/admin/categories/<cat_key>")
@admin_required
def category_list(cat_key: str):
    if cat_key not in ADMIN_CATEGORY_KEYS:
        flash("Geçersiz kategori.", "err")
        return redirect("/admin/categories")
    q = (request.args.get("q") or "").strip()
    ilce = (request.args.get("ilce") or "").strip()
    db = SessionLocal()
    try:
        query = db.query(Place).filter(Place.category == cat_key, Place.status == "approved")
        if ilce:
            query = query.filter(Place.ilce == ilce)
        if q:
            like = f"%{q}%"
            query = query.filter(
                (Place.title.ilike(like)) | (Place.slug.ilike(like)) | (Place.address.ilike(like))
            )
        rows = query.order_by(Place.title.asc()).limit(500).all()
        meta = _category_meta(cat_key)
        return render_template(
            "admin/category_list.html",
            cat=meta,
            rows=rows,
            q=q,
            ilce=ilce,
            ilceler=ILCELER,
            **_admin_ctx(db, "categories"),
        )
    finally:
        db.close()


@bp.route("/admin/categories/<cat_key>/new", methods=["GET", "POST"])
@admin_required
def category_new(cat_key: str):
    if cat_key not in ADMIN_CATEGORY_KEYS:
        flash("Geçersiz kategori.", "err")
        return redirect("/admin/categories")
    db = SessionLocal()
    try:
        meta = _category_meta(cat_key)
        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            if not title:
                flash("Başlık zorunlu.", "err")
                return redirect(f"/admin/categories/{cat_key}/new")
            slug_in = (request.form.get("slug") or title).strip()
            p = Place(
                title=title,
                slug=unique_slug(db, slug_in),
                category=cat_key,
                status="approved",
                extra_json="{}",
            )
            _apply_place_form(p, request.form, request.files)
            p.category = cat_key
            p.slug = unique_slug(db, p.slug or slug_in)
            db.add(p)
            db.commit()
            flash("Kayıt eklendi.", "ok")
            return redirect(f"/admin/categories/{cat_key}/{p.id}/edit")
        blank = Place(title="", slug="", category=cat_key, status="approved", extra_json="{}")
        return render_template(
            "admin/category_edit.html",
            place=blank,
            cat=meta,
            is_new=True,
            ilceler=ILCELER,
            tags=[],
            extra={},
            menu_lines="",
            fee_lines="",
            services_text="",
            staff_lines="",
            gallery_urls="",
            **_admin_ctx(db, "categories"),
        )
    finally:
        db.close()


@bp.route("/admin/categories/<cat_key>/<int:pid>/edit", methods=["GET", "POST"])
@admin_required
def category_edit(cat_key: str, pid: int):
    if cat_key not in ADMIN_CATEGORY_KEYS:
        flash("Geçersiz kategori.", "err")
        return redirect("/admin/categories")
    db = SessionLocal()
    try:
        p = db.get(Place, pid)
        meta = _category_meta(cat_key)
        if not p or p.category != cat_key:
            flash("Kayıt bulunamadı.", "err")
            return redirect(f"/admin/categories/{cat_key}")
        if request.method == "POST":
            old_slug = p.slug
            _apply_place_form(p, request.form, request.files)
            p.category = cat_key
            if p.slug != old_slug:
                p.slug = unique_slug(db, p.slug, exclude_id=p.id)
            db.commit()
            flash("Kaydedildi.", "ok")
            return redirect(f"/admin/categories/{cat_key}/{pid}/edit")
        ex = place_extra(p)
        return render_template(
            "admin/category_edit.html",
            place=p,
            cat=meta,
            is_new=False,
            ilceler=ILCELER,
            tags=tags_load(p.tags),
            extra=ex,
            menu_lines=format_menu_text(ex.get("menu") or []),
            fee_lines=format_list_text(ex.get("fees") or []),
            services_text="\n".join(ex.get("services") or []),
            staff_lines=format_staff_text(ex.get("staff") or []),
            gallery_urls="\n".join(ex.get("gallery") or []),
            **_admin_ctx(db, "categories"),
        )
    finally:
        db.close()


@bp.route("/admin/categories/<cat_key>/<int:pid>/delete", methods=["POST"])
@admin_required
def category_delete(cat_key: str, pid: int):
    if cat_key not in ADMIN_CATEGORY_KEYS:
        return redirect("/admin/categories")
    db = SessionLocal()
    try:
        p = db.get(Place, pid)
        if p and p.category == cat_key:
            db.delete(p)
            db.commit()
            flash("Silindi.", "ok")
        return redirect(f"/admin/categories/{cat_key}")
    finally:
        db.close()


@bp.route("/admin/staff")
@admin_required
def staff_list():
    db = SessionLocal()
    try:
        rows = (
            db.query(User)
            .filter(User.role.in_(("admin", "editor")))
            .order_by(User.role.asc(), User.id.asc())
            .all()
        )
        from admin_permissions import parse_permissions, role_label

        items = []
        for u in rows:
            items.append(
                {
                    "user": u,
                    "role_label": role_label(u.role),
                    "perms": sorted(parse_permissions(u.permissions_json)) if u.role == "editor" else [],
                }
            )
        return render_template(
            "admin/staff_list.html",
            items=items,
            perm_groups=__import__("admin_permissions").permission_groups(),
            **_admin_ctx(db, "staff"),
        )
    finally:
        db.close()


def _staff_from_form(form, *, existing: User | None = None) -> tuple[dict, str | None]:
    from admin_permissions import ALL_PERM_KEYS, dump_permissions, is_super_admin

    email = (form.get("email") or "").strip().lower()
    name = (form.get("name") or "").strip()
    role = (form.get("role") or "editor").strip()
    password = form.get("password") or ""
    if role not in ("admin", "editor"):
        role = "editor"
    perms = [p for p in form.getlist("perms") if p in ALL_PERM_KEYS]
    if not email:
        return {}, "E-posta zorunlu."
    if not name:
        return {}, "Ad zorunlu."
    if existing is None and len(password) < 8:
        return {}, "Yeni hesap için en az 8 karakter şifre gir."
    if role == "editor" and not perms:
        return {}, "Editör için en az bir yetki seç."
    cur = load_user()
    if existing and cur and existing.id == cur.id and role != "admin" and is_super_admin(existing):
        return {}, "Kendi tam yetkili admin hesabınızı düşüremezsiniz."
    data = {
        "email": email,
        "name": name,
        "role": role,
        "permissions_json": dump_permissions(perms) if role == "editor" else "[]",
    }
    if password:
        if len(password) < 8:
            return {}, "Şifre en az 8 karakter olmalı."
        data["password_hash"] = hash_password(password)
    return data, None


@bp.route("/admin/staff/new", methods=["GET", "POST"])
@admin_required
def staff_new():
    db = SessionLocal()
    try:
        from admin_permissions import permission_groups

        if request.method == "POST":
            data, err = _staff_from_form(request.form)
            if err:
                flash(err, "err")
                return redirect("/admin/staff/new")
            if db.query(User).filter(User.email == data["email"]).first():
                flash("Bu e-posta zaten kayıtlı.", "err")
                return redirect("/admin/staff/new")
            u = User(
                email=data["email"],
                name=data["name"],
                role=data["role"],
                permissions_json=data["permissions_json"],
                password_hash=data["password_hash"],
                email_verified=True,
            )
            db.add(u)
            db.commit()
            flash("Ekip üyesi eklendi.", "ok")
            return redirect("/admin/staff")
        blank = User(email="", name="", role="editor", permissions_json="[]")
        return render_template(
            "admin/staff_edit.html",
            staff=blank,
            is_new=True,
            perm_groups=permission_groups(),
            selected_perms=set(),
            **_admin_ctx(db, "staff"),
        )
    finally:
        db.close()


@bp.route("/admin/staff/<int:uid>/edit", methods=["GET", "POST"])
@admin_required
def staff_edit(uid: int):
    db = SessionLocal()
    try:
        from admin_permissions import parse_permissions, permission_groups

        u = db.get(User, uid)
        if not u or u.role not in ("admin", "editor"):
            flash("Kayıt bulunamadı.", "err")
            return redirect("/admin/staff")
        if request.method == "POST":
            data, err = _staff_from_form(request.form, existing=u)
            if err:
                flash(err, "err")
                return redirect(f"/admin/staff/{uid}/edit")
            other = db.query(User).filter(User.email == data["email"], User.id != uid).first()
            if other:
                flash("Bu e-posta başka hesapta kullanılıyor.", "err")
                return redirect(f"/admin/staff/{uid}/edit")
            u.email = data["email"]
            u.name = data["name"]
            u.role = data["role"]
            u.permissions_json = data["permissions_json"]
            u.email_verified = True
            if data.get("password_hash"):
                u.password_hash = data["password_hash"]
            db.commit()
            flash("Güncellendi.", "ok")
            return redirect("/admin/staff")
        return render_template(
            "admin/staff_edit.html",
            staff=u,
            is_new=False,
            perm_groups=permission_groups(),
            selected_perms=parse_permissions(u.permissions_json),
            **_admin_ctx(db, "staff"),
        )
    finally:
        db.close()


@bp.route("/admin/staff/<int:uid>/demote", methods=["POST"])
@admin_required
def staff_demote(uid: int):
    cur = load_user()
    db = SessionLocal()
    try:
        u = db.get(User, uid)
        if not u or u.role not in ("admin", "editor"):
            return redirect("/admin/staff")
        if cur and u.id == cur.id:
            flash("Kendi hesabınızı kaldıramazsınız.", "err")
            return redirect("/admin/staff")
        if u.role == "admin":
            admins = db.query(User).filter(User.role == "admin").count()
            if admins <= 1:
                flash("Son tam yetkili admin kaldırılamaz.", "err")
                return redirect("/admin/staff")
        u.role = "user"
        u.permissions_json = "[]"
        db.commit()
        flash("Panel erişimi kaldırıldı — normal üye oldu.", "ok")
        return redirect("/admin/staff")
    finally:
        db.close()
