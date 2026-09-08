"""REST /api/v1 — site + gelecek native. Yalnız approved public."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from auth import admin_required, hash_password, load_user, login_required, login_user, make_token, rate_ok, verify_password
from catalog import CAT_KEYS, CATEGORIES, MEKAN_TAXONOMY, parse_dt, place_mine, place_public, query_places, tags_dump, unique_slug
from discover import FALLBACK_LAT, FALLBACK_LNG, nearby, today_bursa, tonight, weekend, weekend_plan
from models import Place, Review, SessionLocal, User, clamp_score, recompute_place_rating, review_dimension_avgs

bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


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
        return jsonify({"ok": True, "places": [place_public(p) for p in rows], "total": total, "limit": limit, "offset": offset})
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
        return jsonify({"ok": True, "place": d})
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


@bp.route("/me")
@login_required
def me_api():
    user = load_user()
    from feed_social import follow_counts

    db = SessionLocal()
    try:
        u = db.get(User, user.id)
        if not u:
            return _err("bulunamadı", 404)
        data = u.public()
        data["counts"] = follow_counts(db, u.id)
        return jsonify({"ok": True, "user": data})
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


@bp.route("/okey/seeking")
def okey_seeking():
    """Okey 4. oyuncu — şimdilik örnek + boş slot; ileride gerçek eşleşme."""
    return jsonify(
        {
            "ok": True,
            "seeking": [
                {
                    "id": 1,
                    "host": "Ayşe K.",
                    "ilce": "Nilüfer",
                    "time_label": "Bu akşam 21:00",
                    "note": "3 kişiyiz, 1 kişi arıyoruz",
                    "points_min": 120,
                },
                {
                    "id": 2,
                    "host": "Mehmet T.",
                    "ilce": "Osmangazi",
                    "time_label": "Yarın 20:30",
                    "note": "Kısa oyun, acele etmeyin :)",
                    "points_min": 80,
                },
            ],
        }
    )
