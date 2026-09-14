"""REST /api/v1 — site + gelecek native. Yalnız approved public."""
from __future__ import annotations

import json
import os
from datetime import datetime

from flask import Blueprint, jsonify, request

from auth import admin_required, hash_password, load_user, login_required, login_user, make_token, rate_ok, verify_password
from bursaspor_pages import build_bursaspor_payload
from catalog import CAT_KEYS, CATEGORIES, MEKAN_TAXONOMY, parse_dt, place_mine, place_public, query_places, tags_dump, unique_slug
from discover import FALLBACK_LAT, FALLBACK_LNG, nearby, today_bursa, tonight, weekend, weekend_plan
from news_mobile import build_news_detail, build_news_hub
from models import Place, Review, SessionLocal, User, clamp_score, recompute_place_rating, review_dimension_avgs

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _mobile_data_json(filename: str) -> dict:
    path = os.path.join(_DATA_DIR, filename)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _err(msg: str, code: int = 400):
    return jsonify({"ok": False, "error": msg}), code


def _json():
    return request.get_json(silent=True) or {}


def _paging():
    try:
        limit = int(request.args.get("limit") or 24)
    except ValueError:
        limit = 24
    try:
        offset = int(request.args.get("offset") or 0)
    except ValueError:
        offset = 0
    return max(1, min(limit, 100)), max(0, offset)


@bp.route("/categories")
def categories():
    return jsonify({"ok": True, "categories": list(CATEGORIES), "taxonomy": MEKAN_TAXONOMY})


@bp.route("/places")
def places():
    limit, offset = _paging()
    db = SessionLocal()
    try:
        rows, total = query_places(
            db,
            category=request.args.get("category"),
            ilce=request.args.get("ilce"),
            price_band=request.args.get("spec") or request.args.get("price_band"),
            subcategory=request.args.get("sub") or request.args.get("subcategory"),
            q=request.args.get("q"),
            from_=request.args.get("from"),
            to=request.args.get("to"),
            status="approved",
            limit=limit,
            offset=offset,
        )
        cards = [place_public(p) for p in rows]
        from features import annotate_favorites

        annotate_favorites(db, load_user(), cards)
        return jsonify({"ok": True, "places": cards, "total": total, "limit": limit, "offset": offset})
    finally:
        db.close()


@bp.route("/places/<slug>")
def place_one(slug: str):
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == slug, Place.status == "approved").first()
        if p is None:
            return _err("bulunamadı", 404)
        d = place_public(p)
        d["dimensions"] = review_dimension_avgs(db, p.id)
        from features import annotate_favorites

        annotate_favorites(db, load_user(), [d])
        return jsonify({"ok": True, "place": d})
    finally:
        db.close()


@bp.route("/places/<slug>/favorite", methods=["POST"])
@login_required
def place_favorite_toggle(slug: str):
    from models import Favorite

    user = load_user()
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == slug, Place.status == "approved").first()
        if p is None:
            return _err("bulunamadı", 404)
        fav = db.query(Favorite).filter(Favorite.user_id == user.id, Favorite.place_id == p.id).first()
        if fav:
            db.delete(fav)
            p.fav_count = max(0, (p.fav_count or 0) - 1)
            is_fav = False
        else:
            db.add(Favorite(user_id=user.id, place_id=p.id))
            p.fav_count = (p.fav_count or 0) + 1
            is_fav = True
        db.commit()
        return jsonify({"ok": True, "is_fav": is_fav, "fav_count": int(p.fav_count or 0)})
    finally:
        db.close()


@bp.route("/places/<slug>/reviews")
def place_reviews(slug: str):
    limit, offset = _paging()
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == slug, Place.status == "approved").first()
        if p is None:
            return _err("bulunamadı", 404)
        qry = db.query(Review).filter(Review.place_id == p.id, Review.status == "approved").order_by(Review.updated_at.desc())
        total = qry.count()
        rows = qry.offset(offset).limit(limit).all()
        return jsonify({
            "ok": True,
            "reviews": [r.public() for r in rows],
            "dimensions": review_dimension_avgs(db, p.id),
            "rating_avg": p.rating_avg,
            "rating_count": p.rating_count,
            "total": total,
            "limit": limit,
            "offset": offset,
        })
    finally:
        db.close()


@bp.route("/places/<slug>/reviews", methods=["POST"])
@login_required
def place_review_post(slug: str):
    if not rate_ok("review", limit=20):
        return _err("çok sık deneme", 429)
    user = load_user()
    body = _json()
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == slug, Place.status == "approved").first()
        if p is None:
            return _err("bulunamadı", 404)
        rev = db.query(Review).filter(Review.place_id == p.id, Review.user_id == user.id).first()
        if rev is None:
            rev = Review(place_id=p.id, user_id=user.id)
            db.add(rev)
        rev.score_food = clamp_score(body.get("score_food"))
        rev.score_service = clamp_score(body.get("score_service"))
        rev.score_atmosphere = clamp_score(body.get("score_atmosphere"))
        rev.score_price = clamp_score(body.get("score_price"))
        rev.body = (body.get("body") or "").strip()[:2000]
        rev.status = "pending"
        from datetime import datetime as _dt
        rev.updated_at = _dt.utcnow()
        db.flush()
        recompute_place_rating(db, p)
        db.commit()
        return jsonify({"ok": True, "review": rev.public(), "pending": True, "message": "admin onayı bekleniyor"})
    finally:
        db.close()


@bp.route("/discover/today")
def discover_today():
    db = SessionLocal()
    try:
        return jsonify({"ok": True, **today_bursa(db)})
    finally:
        db.close()


@bp.route("/discover/tonight")
def discover_tonight():
    couple = (request.args.get("mode") or "") == "couple"
    db = SessionLocal()
    try:
        return jsonify({"ok": True, **tonight(db, couple=couple)})
    finally:
        db.close()


@bp.route("/discover/nearby")
def discover_nearby():
    db = SessionLocal()
    try:
        try:
            lat = float(request.args.get("lat"))
            lng = float(request.args.get("lng"))
        except (TypeError, ValueError):
            lat, lng = FALLBACK_LAT, FALLBACK_LNG
        try:
            radius = float(request.args.get("r") or 500)
        except (TypeError, ValueError):
            radius = 500
        return jsonify({"ok": True, **nearby(db, lat, lng, max(200, min(radius, 5000)))})
    finally:
        db.close()


@bp.route("/discover/weekend")
def discover_weekend():
    plan = (request.args.get("plan") or "") == "1"
    try:
        people = max(1, min(int(request.args.get("people") or 2), 8))
    except ValueError:
        people = 2
    db = SessionLocal()
    try:
        data = weekend(db)
        out = {"ok": True, **data}
        if plan:
            out["plan"] = weekend_plan(db, people=people)
        return jsonify(out)
    finally:
        db.close()


@bp.route("/events")
def events():
    limit, offset = _paging()
    db = SessionLocal()
    try:
        rows, total = query_places(
            db,
            category="event",
            from_=request.args.get("from"),
            to=request.args.get("to"),
            q=request.args.get("q"),
            status="approved",
            limit=limit,
            offset=offset,
        )
        return jsonify({"ok": True, "events": [place_public(p) for p in rows], "total": total, "limit": limit, "offset": offset})
    finally:
        db.close()


@bp.route("/auth/register", methods=["POST"])
def register():
    if not rate_ok("register"):
        return _err("çok sık deneme", 429)
    body = _json()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    name = (body.get("name") or "").strip()
    if "@" not in email or "." not in email:
        return _err("geçerli e-posta gir")
    if len(password) < 8:
        return _err("şifre en az 8 karakter")
    if len(name) < 2:
        return _err("ad en az 2 karakter")
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            return _err("bu e-posta kayıtlı")
        u = User(email=email, password_hash=hash_password(password), name=name, role="user", email_verified=False)
        from mail_verify import new_email_token, send_verify_email

        u.email_token = new_email_token()
        db.add(u)
        db.commit()
        db.refresh(u)
        try:
            send_verify_email(email=email, name=name, token=u.email_token)
        except Exception:
            pass
        try:
            from notify import notify_register

            notify_register(name=name, email=email, user_id=u.id, source="api")
        except Exception:
            pass
        login_user(u)
        return jsonify({"ok": True, "user": u.public(), "token": make_token(u), "email_verify_sent": True})
    finally:
        db.close()


@bp.route("/auth/login", methods=["POST"])
def login():
    if not rate_ok("login", limit=10):
        return _err("çok sık deneme", 429)
    body = _json()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        if u is None or not verify_password(password, u.password_hash):
            return _err("e-posta veya şifre yanlış", 401)
        if not bool(getattr(u, "is_active", True)):
            return _err("hesap pasif", 403)
        login_user(u)
        from models import log_activity

        log_activity(
            db,
            kind="login",
            title="Giriş yaptı (API)",
            detail=u.name or "",
            user_id=u.id,
            email=u.email,
            user_role=u.role,
        )
        db.commit()
        return jsonify({"ok": True, "user": u.public(), "token": make_token(u)})
    finally:
        db.close()


@bp.route("/auth/forgot-password", methods=["POST"])
def forgot_password():
    if not rate_ok("forgot_password", limit=3, window=900):
        return _err("çok sık deneme — 15 dk sonra tekrar dene", 429)
    body = _json()
    email = (body.get("email") or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return _err("geçerli e-posta gir")
    db = SessionLocal()
    try:
        from password_reset import send_new_password_email

        send_new_password_email(db, email)
        # E-posta kayıtlı olmasa da aynı yanıt (enumeration önleme)
        return jsonify({
            "ok": True,
            "message": "Kayıtlıysa yeni şifren e-posta adresine gönderildi. Gelen kutunu ve spam klasörünü kontrol et.",
        })
    finally:
        db.close()


def _fill_place(p: Place, body: dict, *, is_admin: bool, db) -> str | None:
    title = (body.get("title") or p.title or "").strip()
    if not title:
        return "başlık gerekli"
    cat = (body.get("category") or p.category or "").strip()
    if cat not in CAT_KEYS:
        return "kategori geçersiz"
    if cat == "event" and not parse_dt(body.get("starts_at") or (p.starts_at.isoformat() if p.starts_at else "")):
        if not p.starts_at:
            return "etkinlikte tarih zorunlu"
    p.title = title
    if not p.slug or body.get("title"):
        p.slug = unique_slug(db, title, exclude_id=p.id)
    p.category = cat
    p.ilce = (body.get("ilce") or p.ilce or "").strip()
    p.address = (body.get("address") or "").strip() if "address" in body else (p.address or "")
    for key in ("phone", "web", "hours_text", "price_band", "blurb", "body", "img_url", "venue_name", "subcategory"):
        if key in body:
            setattr(p, key, (body.get(key) or "").strip())
    if "lat" in body:
        try:
            p.lat = float(body["lat"]) if body["lat"] not in (None, "") else None
        except (TypeError, ValueError):
            p.lat = None
    if "lng" in body:
        try:
            p.lng = float(body["lng"]) if body["lng"] not in (None, "") else None
        except (TypeError, ValueError):
            p.lng = None
    if "tags" in body:
        p.tags = tags_dump(body.get("tags"))
    if "starts_at" in body:
        p.starts_at = parse_dt(body.get("starts_at"))
    if "ends_at" in body:
        p.ends_at = parse_dt(body.get("ends_at"))
    if is_admin:
        if "featured" in body:
            p.featured = bool(body.get("featured"))
        if "rating_admin" in body and body.get("rating_admin") not in (None, ""):
            try:
                p.rating_admin = float(body["rating_admin"])
            except (TypeError, ValueError):
                pass
        if body.get("status") in ("pending", "approved", "rejected"):
            p.status = body["status"]
    return None


@bp.route("/places", methods=["POST"])
@login_required
def create_place():
    if not rate_ok("submit"):
        return _err("çok sık deneme", 429)
    user = load_user()
    body = _json()
    db = SessionLocal()
    try:
        p = Place(status="pending", submitted_by_id=user.id, title="")
        err = _fill_place(p, body, is_admin=False, db=db)
        if err:
            return _err(err)
        db.add(p)
        db.commit()
        db.refresh(p)
        return jsonify({"ok": True, "place": place_mine(p)}), 201
    finally:
        db.close()


@bp.route("/me/places")
@login_required
def my_places():
    user = load_user()
    limit, offset = _paging()
    db = SessionLocal()
    try:
        qry = db.query(Place).filter(Place.submitted_by_id == user.id).order_by(Place.id.desc())
        total = qry.count()
        rows = qry.offset(offset).limit(limit).all()
        return jsonify({"ok": True, "places": [place_mine(p) for p in rows], "total": total, "limit": limit, "offset": offset})
    finally:
        db.close()


@bp.route("/admin/queue")
@admin_required
def admin_queue():
    status = (request.args.get("status") or "pending").strip()
    if status not in ("pending", "approved", "rejected", "all"):
        status = "pending"
    limit, offset = _paging()
    db = SessionLocal()
    try:
        qry = db.query(Place)
        if status != "all":
            qry = qry.filter(Place.status == status)
        qry = qry.order_by(Place.id.desc())
        total = qry.count()
        rows = qry.offset(offset).limit(limit).all()
        return jsonify({"ok": True, "places": [place_mine(p) for p in rows], "total": total, "limit": limit, "offset": offset})
    finally:
        db.close()


@bp.route("/admin/places/<int:pid>/approve", methods=["POST"])
@admin_required
def admin_approve(pid: int):
    user = load_user()
    db = SessionLocal()
    try:
        p = db.get(Place, pid)
        if p is None:
            return _err("bulunamadı", 404)
        p.status = "approved"
        p.reviewed_by_id = user.id
        p.reviewed_at = datetime.utcnow()
        p.reject_reason = ""
        db.commit()
        return jsonify({"ok": True, "place": place_public(p)})
    finally:
        db.close()


@bp.route("/admin/places/<int:pid>/reject", methods=["POST"])
@admin_required
def admin_reject(pid: int):
    user = load_user()
    body = _json()
    reason = (body.get("reason") or "").strip()
    db = SessionLocal()
    try:
        p = db.get(Place, pid)
        if p is None:
            return _err("bulunamadı", 404)
        p.status = "rejected"
        p.reject_reason = reason
        p.reviewed_by_id = user.id
        p.reviewed_at = datetime.utcnow()
        db.commit()
        return jsonify({"ok": True, "place": place_mine(p)})
    finally:
        db.close()


@bp.route("/admin/places/<int:pid>", methods=["PATCH"])
@admin_required
def admin_patch(pid: int):
    body = _json()
    db = SessionLocal()
    try:
        p = db.get(Place, pid)
        if p is None:
            return _err("bulunamadı", 404)
        err = _fill_place(p, body, is_admin=True, db=db)
        if err:
            return _err(err)
        db.commit()
        db.refresh(p)
        return jsonify({"ok": True, "place": place_mine(p)})
    finally:
        db.close()


def _events_notify_cards(db, rows) -> list[dict]:
    from feed_social import going_count

    now = datetime.utcnow()
    out = []
    for p in rows:
        d = place_public(p)
        when = ""
        if p.starts_at:
            delta = p.starts_at - now
            days = max(0, delta.days)
            if days == 0:
                hrs = max(1, delta.seconds // 3600)
                when = "bugün" if delta.seconds < 43200 else f"{hrs} saat sonra"
            elif days == 1:
                when = "yarın"
            else:
                when = f"{days} gün sonra"
            d["starts_at_iso"] = p.starts_at.isoformat() + "Z"
            d["starts_at_label"] = p.starts_at.strftime("%d.%m %H:%M")
        d["when_label"] = when
        d["going"] = going_count(db, p.id)
        out.append(d)
    return out


@bp.route("/feed")
def feed_api():
    from feed_social import FEED_PAGE_SIZE, build_feed, profile_feed, upcoming_events

    limit, offset = _paging()
    tab = (request.args.get("tab") or "recents").strip().lower()
    if tab not in ("recents", "friends", "popular"):
        tab = "recents"
    user = load_user()
    db = SessionLocal()
    try:
        if user:
            feed, has_more = profile_feed(db, user, tab, limit=limit, offset=offset)
        else:
            feed, has_more = build_feed(db, viewer=None, tab=tab, limit=limit, offset=offset)
        ev_rows = (
            db.query(Place)
            .filter(
                Place.status == "approved",
                Place.category.in_(("event", "concert", "theater", "cinema", "family")),
                Place.starts_at.isnot(None),
                Place.starts_at >= datetime.utcnow(),
            )
            .order_by(Place.starts_at.asc())
            .limit(12)
            .all()
        )
        events = _events_notify_cards(db, ev_rows)
        return jsonify(
            {
                "ok": True,
                "feed": feed,
                "events": events,
                "has_more": has_more,
                "tab": tab,
                "logged_in": bool(user),
            }
        )
    finally:
        db.close()


@bp.route("/events/upcoming")
def events_upcoming_api():
    db = SessionLocal()
    try:
        rows = (
            db.query(Place)
            .filter(
                Place.status == "approved",
                Place.category.in_(("event", "concert", "theater", "cinema", "family")),
                Place.starts_at.isnot(None),
                Place.starts_at >= datetime.utcnow(),
            )
            .order_by(Place.starts_at.asc())
            .limit(40)
            .all()
        )
        return jsonify({"ok": True, "events": _events_notify_cards(db, rows), "total": len(rows)})
    finally:
        db.close()


@bp.route("/me", methods=["GET", "PATCH"])
@login_required
def me_api():
    user = load_user()
    from feed_social import follow_counts

    db = SessionLocal()
    try:
        u = db.get(User, user.id)
        if not u:
            return _err("bulunamadı", 404)
        if request.method == "PATCH":
            body = _json()
            action = (body.get("action") or "profile").strip()
            if action == "profile":
                name = (body.get("name") or "").strip()
                if name:
                    if len(name) < 2:
                        return _err("ad en az 2 karakter", 400)
                    u.name = name
                if "show_full_name" in body:
                    u.show_full_name = bool(body.get("show_full_name"))
            elif action == "password":
                cur = body.get("current_password") or ""
                new = body.get("new_password") or ""
                new2 = body.get("new_password2") or ""
                if not verify_password(cur, u.password_hash):
                    return _err("mevcut şifre yanlış", 400)
                if len(new) < 8:
                    return _err("yeni şifre en az 8 karakter", 400)
                if new != new2:
                    return _err("yeni şifreler eşleşmiyor", 400)
                u.password_hash = hash_password(new)
            else:
                return _err("geçersiz işlem", 400)
            db.commit()
            db.refresh(u)
        data = u.public()
        data["counts"] = follow_counts(db, u.id)
        return jsonify({"ok": True, "user": data})
    finally:
        db.close()


@bp.route("/me/avatar", methods=["POST"])
@login_required
def me_avatar_api():
    from admin_forms import save_upload

    user = load_user()
    db = SessionLocal()
    try:
        u = db.get(User, user.id)
        if not u:
            return _err("bulunamadı", 404)
        f = request.files.get("avatar")
        path, err = save_upload(f, category="avatar")
        if err:
            return _err(err, 400)
        if not path:
            return _err("geçerli bir görsel seç", 400)
        u.avatar_url = path
        db.commit()
        db.refresh(u)
        return jsonify({"ok": True, "user": u.public()})
    finally:
        db.close()


@bp.route("/posts/<int:post_id>/like", methods=["POST"])
@login_required
def post_like_api(post_id: int):
    from models import PostLike, UserPost

    user = load_user()
    db = SessionLocal()
    try:
        post = db.get(UserPost, post_id)
        if not post or post.status != "approved":
            return _err("gönderi bulunamadı", 404)
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
        return jsonify({"ok": True, "liked": liked, "likes": int(post.likes_count or 0)})
    finally:
        db.close()


@bp.route("/mobile/menu")
def mobile_menu():
    groups = [
        {
            "title": "Topluluk",
            "icon": "community",
            "items": [
                {"label": "Arkadaş / partner ara", "path": "/arkadas-ara", "category": "buddy"},
                {"label": "Akış", "path": "/feed"},
            ],
        },
        {
            "title": "Sağlık",
            "icon": "health",
            "items": [
                {"label": "Hastaneler", "path": "/hastaneler", "category": "hospital"},
                {"label": "Doktorlar", "path": "/doktorlar", "category": "doctor"},
                {"label": "Diş hekimleri", "path": "/dis-hekimleri", "category": "dentist"},
                {"label": "Nöbetçi eczaneler", "path": "/nobetci-eczaneler", "category": "pharmacy"},
                {"label": "Veterinerler", "path": "/veterinerler", "category": "vet"},
            ],
        },
        {
            "title": "Gezi",
            "icon": "visit",
            "items": [
                {"label": "Gezilecek yerler", "path": "/gezilecek"},
            ],
        },
        {
            "title": "Konaklama & doğa",
            "icon": "nature",
            "items": [
                {"label": "Oteller", "path": "/oteller", "category": "hotel"},
                {"label": "Kamp alanları", "path": "/kamp", "category": "camp"},
                {"label": "Uludağ teleferik", "path": "/uludag-teleferik", "category": "visit"},
            ],
        },
        {
            "title": "Şehir",
            "icon": "city",
            "items": [
                {"label": "Bursa haberleri", "path": "/haberler"},
                {"label": "Bursaspor", "path": "/bursaspor"},
                {"label": "Faturalar & tarifeler", "path": "/faturalar"},
                {"label": "Hafta sonu planı", "path": "/hafta-sonu"},
                {"label": "Rota planlayıcı", "path": "/rota"},
            ],
        },
        {
            "title": "Etkinlik",
            "icon": "event",
            "items": [
                {"label": "Konserler", "path": "/konserler", "category": "concert"},
                {"label": "Tiyatro", "path": "/tiyatro", "category": "theater"},
                {"label": "Sinema", "path": "/sinema", "category": "cinema"},
                {"label": "Etkinlik takvimi", "path": "/etkinlikler", "category": "event"},
            ],
        },
    ]
    return jsonify({"ok": True, "groups": groups, "categories": list(CATEGORIES)})


@bp.route("/leaders/weekly")
def leaders_weekly():
    db = SessionLocal()
    try:
        rows = (
            db.query(User)
            .filter(User.is_active.is_(True), User.role == "user", ~User.email.like("%.sanal@bursaapp.com"))
            .order_by(User.loyalty_points.desc(), User.id.desc())
            .limit(10)
            .all()
        )
        leaders = []
        for i, u in enumerate(rows, start=1):
            leaders.append(
                {
                    "rank": i,
                    "user": {
                        "id": u.id,
                        "name": u.display_name(),
                        "avatar_url": u.avatar_url or "",
                        "points": int(u.loyalty_points or 0),
                    },
                }
            )
        return jsonify(
            {
                "ok": True,
                "week_label": datetime.utcnow().strftime("%d.%m.%Y"),
                "leaders": leaders,
                "note": "Haftalık lider — puan tablosu (loyalty_points)",
            }
        )
    finally:
        db.close()


@bp.route("/activities/types")
def activities_types():
    from activity_seek import ACTIVITY_TYPES, SKILL_LEVELS

    types = [
        {"key": k, "label": v["label"], "emoji": v["emoji"], "default_title": v["default_title"]}
        for k, v in ACTIVITY_TYPES.items()
    ]
    return jsonify({"ok": True, "types": types, "skill_levels": SKILL_LEVELS})


@bp.route("/activities/seeking")
def activities_seeking():
    from activity_seek import ACTIVITY_TYPES, list_open_seeks, seek_public

    activity_type = (request.args.get("type") or request.args.get("activity_type") or "").strip().lower()
    ilce = (request.args.get("ilce") or "").strip()
    if activity_type and activity_type not in ACTIVITY_TYPES:
        activity_type = ""
    viewer = load_user()
    db = SessionLocal()
    try:
        rows = list_open_seeks(db, activity_type=activity_type or None, ilce=ilce or None)
        return jsonify(
            {
                "ok": True,
                "seeking": [seek_public(db, s, viewer) for s in rows],
                "filter": {"type": activity_type or None, "ilce": ilce or None},
            }
        )
    finally:
        db.close()


@bp.route("/activities/seeking", methods=["POST"])
@login_required
def activities_seeking_create():
    from activity_seek import create_seek, seek_public

    if not rate_ok("activity_seek", limit=8):
        return _err("Çok hızlı — biraz bekle", 429)
    user = load_user()
    db = SessionLocal()
    try:
        seek, err = create_seek(db, user, _json())
        if err:
            return _err(err, 400)
        return jsonify({"ok": True, "seek": seek_public(db, seek, user)}), 201
    finally:
        db.close()


@bp.route("/activities/seeking/<int:seek_id>/join", methods=["POST"])
@login_required
def activities_seeking_join(seek_id: int):
    from activity_seek import join_seek, seek_public

    if not rate_ok("activity_join", limit=20):
        return _err("Çok hızlı — biraz bekle", 429)
    user = load_user()
    db = SessionLocal()
    try:
        seek, err = join_seek(db, user, seek_id)
        if err:
            return _err(err, 400)
        return jsonify(
            {
                "ok": True,
                "pending": True,
                "message": "Onay bekleniyor",
                "seek": seek_public(db, seek, user),
            }
        )
    finally:
        db.close()


@bp.route("/activities/seeking/<int:seek_id>/join/<int:join_user_id>/approve", methods=["POST"])
@login_required
def activities_seeking_approve(seek_id: int, join_user_id: int):
    from activity_seek import approve_join, seek_public

    user = load_user()
    db = SessionLocal()
    try:
        seek, err = approve_join(db, user, seek_id, join_user_id)
        if err:
            return _err(err, 400)
        return jsonify({"ok": True, "seek": seek_public(db, seek, user)})
    finally:
        db.close()


@bp.route("/activities/seeking/<int:seek_id>/join/<int:join_user_id>/reject", methods=["POST"])
@login_required
def activities_seeking_reject(seek_id: int, join_user_id: int):
    from activity_seek import reject_join, seek_public

    user = load_user()
    db = SessionLocal()
    try:
        seek, err = reject_join(db, user, seek_id, join_user_id)
        if err:
            return _err(err, 400)
        return jsonify({"ok": True, "seek": seek_public(db, seek, user)})
    finally:
        db.close()


@bp.route("/activities/seeking/<int:seek_id>/join", methods=["DELETE"])
@login_required
def activities_seeking_leave(seek_id: int):
    from activity_seek import leave_seek, seek_public

    user = load_user()
    db = SessionLocal()
    try:
        seek, err = leave_seek(db, user, seek_id)
        if err:
            return _err(err, 400)
        return jsonify({"ok": True, "seek": seek_public(db, seek, user)})
    finally:
        db.close()


@bp.route("/activities/seeking/<int:seek_id>", methods=["DELETE"])
@login_required
def activities_seeking_cancel(seek_id: int):
    from activity_seek import cancel_seek

    user = load_user()
    db = SessionLocal()
    try:
        err = cancel_seek(db, user, seek_id)
        if err:
            return _err(err, 400)
        return jsonify({"ok": True})
    finally:
        db.close()


@bp.route("/okey/seeking")
def okey_seeking():
    """Geriye uyumluluk — yalnız okey ilanları."""
    from activity_seek import list_open_seeks, seek_public

    viewer = load_user()
    db = SessionLocal()
    try:
        rows = list_open_seeks(db, activity_type="okey")
        seeking = [seek_public(db, s, viewer) for s in rows]
        # Eski mobil alan adları
        legacy = []
        for s in seeking:
            legacy.append(
                {
                    "id": s["id"],
                    "host": s["host"],
                    "ilce": s["ilce"],
                    "time_label": s["time_label"],
                    "note": s["note"],
                    "points_min": s["points_min"],
                    "activity_type": s["activity_type"],
                    "activity_label": s["activity_label"],
                    "emoji": s["emoji"],
                    "title": s["title"],
                    "slots_needed": s["slots_needed"],
                    "spots_left": s["spots_left"],
                    "joined": s["joined"],
                    "is_mine": s["is_mine"],
                }
            )
        return jsonify({"ok": True, "seeking": legacy})
    finally:
        db.close()


@bp.route("/mobile/nobetci-eczaneler")
def mobile_nobetci():
    from pharmacy_mobile import build_pharmacy_payload

    lat = lng = None
    try:
        if request.args.get("lat") not in (None, ""):
            lat = float(request.args.get("lat"))
        if request.args.get("lng") not in (None, ""):
            lng = float(request.args.get("lng"))
    except (TypeError, ValueError):
        lat = lng = None
    payload = build_pharmacy_payload(
        ilce=request.args.get("ilce") or "",
        lat=lat,
        lng=lng,
    )
    return jsonify(payload)


@bp.route("/mobile/nobetci-eczaneler/<slug>")
def mobile_nobetci_detail(slug):
    from pharmacy_mobile import build_pharmacy_detail

    return jsonify(build_pharmacy_detail(slug))


@bp.route("/mobile/news")
def mobile_news():
    topic = (request.args.get("konu") or request.args.get("topic") or "").strip()
    q = (request.args.get("q") or "").strip()
    try:
        page = max(1, int(request.args.get("page") or 1))
    except ValueError:
        page = 1
    try:
        per_page = max(1, min(int(request.args.get("limit") or 24), 48))
    except ValueError:
        per_page = 24
    payload = build_news_hub(topic=topic, q=q, page=page, per_page=per_page)
    return jsonify({"ok": True, **payload})


@bp.route("/mobile/news/<slug>")
def mobile_news_detail(slug: str):
    payload = build_news_detail(slug)
    if not payload:
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True, "article": payload})


@bp.route("/mobile/bursaspor")
def mobile_bursaspor():
    db = SessionLocal()
    try:
        payload = build_bursaspor_payload(db)
        return jsonify({"ok": True, **payload})
    finally:
        db.close()


@bp.route("/mobile/teleferik")
def mobile_teleferik():
    data = _mobile_data_json("teleferik.json")
    if not data:
        return jsonify({"ok": False})
    return jsonify({"ok": True, **data})


@bp.route("/mobile/utilities")
def mobile_utilities():
    data = _mobile_data_json("utilities.json")
    return jsonify({"ok": True, "utilities": data if data else {}})


@bp.route("/mobile/hotels")
def mobile_hotels():
    from hotels_mobile import build_hotels_payload

    db = SessionLocal()
    try:
        payload = build_hotels_payload(
            db,
            q=request.args.get("q") or "",
            ilce=request.args.get("ilce") or "",
            sub=request.args.get("sub") or "",
            band=request.args.get("band") or "",
            sort=request.args.get("sort") or "rating",
            price_filter=request.args.get("price") or "",
        )
        return jsonify({"ok": True, **payload})
    finally:
        db.close()


@bp.route("/mobile/visit")
def mobile_visit():
    from visit_mobile import build_visit_payload

    try:
        page = max(1, int(request.args.get("page") or 1))
    except ValueError:
        page = 1
    db = SessionLocal()
    try:
        payload = build_visit_payload(
            db,
            q=request.args.get("q") or "",
            ilce=request.args.get("ilce") or "",
            sub=request.args.get("sub") or "",
            sort=request.args.get("sort") or "featured",
            kinds=request.args.getlist("kind"),
            fees=request.args.getlist("fee"),
            tags=request.args.getlist("tag"),
            page=page,
        )
        return jsonify({"ok": True, **payload})
    finally:
        db.close()


@bp.route("/mobile/vets")
def mobile_vets():
    from vets_mobile import build_vets_payload

    tab = (request.args.get("tab") or "hepsi").strip().lower()
    lat = lng = None
    try:
        if request.args.get("lat") not in (None, ""):
            lat = float(request.args.get("lat"))
        if request.args.get("lng") not in (None, ""):
            lng = float(request.args.get("lng"))
    except (TypeError, ValueError):
        lat = lng = None
    db = SessionLocal()
    try:
        payload = build_vets_payload(
            db,
            tab=tab,
            ilce=request.args.get("ilce") or "",
            sub=request.args.get("sub") or "",
            lat=lat,
            lng=lng,
        )
        return jsonify({"ok": True, **payload})
    finally:
        db.close()


@bp.route("/mobile/dentists")
def mobile_dentists():
    from dentists_mobile import build_dentists_payload

    db = SessionLocal()
    try:
        payload = build_dentists_payload(
            db,
            ilce=request.args.get("ilce") or "",
            band=request.args.get("band") or "",
        )
        return jsonify({"ok": True, **payload})
    finally:
        db.close()


@bp.route("/mobile/doctors")
def mobile_doctors():
    from doctors_mobile import build_doctors_payload

    db = SessionLocal()
    try:
        payload = build_doctors_payload(
            db,
            ilce=request.args.get("ilce") or "",
            spec=request.args.get("spec") or "",
        )
        return jsonify({"ok": True, **payload})
    finally:
        db.close()


@bp.route("/mobile/hospitals")
def mobile_hospitals():
    from hospitals_mobile import build_hospitals_payload

    db = SessionLocal()
    try:
        payload = build_hospitals_payload(
            db,
            ilce=request.args.get("ilce") or "",
            band=request.args.get("band") or "",
        )
        return jsonify({"ok": True, **payload})
    finally:
        db.close()
