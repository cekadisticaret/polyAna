"""REST /api/v1 — site + gelecek native. Yalnız approved public."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from auth import admin_required, hash_password, load_user, login_required, login_user, make_token, rate_ok, verify_password
from catalog import CAT_KEYS, CATEGORIES, parse_dt, place_mine, place_public, query_places, tags_dump, unique_slug
from models import Place, SessionLocal, User

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
    return jsonify({"ok": True, "categories": list(CATEGORIES)})


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
        return jsonify({"ok": True, "place": place_public(p)})
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
        u = User(email=email, password_hash=hash_password(password), name=name, role="user")
        db.add(u)
        db.commit()
        db.refresh(u)
        login_user(u)
        return jsonify({"ok": True, "user": u.public(), "token": make_token(u)})
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
        login_user(u)
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
    for key in ("phone", "web", "hours_text", "price_band", "blurb", "body", "img_url", "venue_name"):
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
