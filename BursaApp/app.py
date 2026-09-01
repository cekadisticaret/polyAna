#!/usr/bin/env python3
"""BursaApp — şehir rehberi. Üye ekler, admin onaylar. Port 5051, 127.0.0.1."""
from __future__ import annotations

import calendar
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, flash, jsonify, redirect, render_template, request

from admin import bp as admin_bp
from api_v1 import bp as api_v1_bp
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
    maps_url,
    parse_dt,
    place_public,
    query_places,
    tags_dump,
    unique_slug,
)
from models import Place, SessionLocal, User, init_db

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

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("BURSAAPP_SECRET_KEY") or os.environ.get("BURSAAPP_JWT_SECRET") or "bursaapp-dev"
app.config["SESSION_COOKIE_NAME"] = "bursaapp_session"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30
app.register_blueprint(api_v1_bp)
app.register_blueprint(admin_bp)

init_db()


@app.context_processor
def _inject():
    user = load_user()
    return {
        "nav_user": user,
        "categories": CATEGORIES,
        "ilceler": ILCELER,
    }


@app.after_request
def _no_store(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


def _weather() -> dict:
    return {"label": "Açık", "temp_c": 24, "hint": "Uludağ serin · merkez ılık"}


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
            Place.category.in_(("event", "theater", "concert", "cinema")),
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
        featured, _ = query_places(db, featured=True, q=q or None, limit=3)
        if len(featured) < 3:
            extra, _ = query_places(db, q=q or None, limit=6)
            seen = {p.id for p in featured}
            for p in extra:
                if p.id not in seen:
                    featured.append(p)
                if len(featured) >= 3:
                    break
        listed, _ = query_places(db, q=q or None, limit=8)
        listed = [p for p in listed if p.id not in {x.id for x in featured}][:5]
        cal = _cal(_month_shows(db))
        return render_template(
            "home.html",
            featured=[place_public(p) for p in featured],
            listed=[place_public(p) for p in listed],
            q=q,
            weather=_weather(),
            ilce_n=17,
            nav="kesfet",
            **cal,
        )
    finally:
        db.close()


@app.route("/yeme-icme")
@app.route("/gezilecek")
@app.route("/oteller")
@app.route("/kamp")
@app.route("/konserler")
@app.route("/tiyatro")
@app.route("/sinema")
@app.route("/eglence")
@app.route("/etkinlikler")
@app.route("/organizasyonlar")
@app.route("/hastaneler")
@app.route("/doktorlar")
@app.route("/veterinerler")
def category_list():
    cat = CAT_BY_PATH.get(request.path)
    if not cat:
        return redirect("/")
    q = (request.args.get("q") or "").strip()
    ilce = (request.args.get("ilce") or "").strip()
    spec = (request.args.get("spec") or "").strip()
    food = cat["key"] == "food"
    visit = cat["key"] == "visit"
    doctor = cat["key"] == "doctor"
    concert = cat["key"] == "concert"
    kinds = KIND_BY_CAT.get(cat["key"])
    grouped = cat["key"] in GROUP_ILCE or cat["key"] in GROUP_BAND
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
            order="rating" if food else ("date" if kinds else None),
            price_band=band or None,
            limit=200 if grouped else 60,
        )
        places = [place_public(p) for p in rows]
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
        chip_items = list(ILCELER)
        chip_param = "ilce"
        chip_on = ilce
        if doctor:
            chip_items = list(DOCTOR_SPECS)
            chip_param = "spec"
            chip_on = spec
        elif kinds:
            chip_items = list(kinds)
            chip_param = "spec"
            chip_on = spec
        if grouped:
            by = {}
            key_fn = (lambda p: p.get("price_band") or "Diğer") if cat["key"] in GROUP_BAND else (
                lambda p: p.get("ilce") or "Diğer"
            )
            for p in places:
                by.setdefault(key_fn(p), []).append(p)
            order = DOCTOR_SPECS if doctor else (kinds if kinds else ILCELER)
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
        return render_template(
            "list.html",
            cat=cat,
            places=places,
            groups=groups,
            total=total,
            q=q,
            ilce=ilce,
            chip_items=chip_items,
            chip_param=chip_param,
            chip_on=chip_on,
            cal=_cal(_month_shows(db)) if cat["key"] == "event" else None,
            nav=cat["key"],
        )
    finally:
        db.close()


@app.route("/yer/<slug>")
def detail(slug: str):
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == slug, Place.status == "approved").first()
        if p is None:
            return render_template("detail.html", place=None, similar=[], nav="kesfet"), 404
        similar, _ = query_places(db, category=p.category, limit=6)
        similar = [place_public(s) for s in similar if s.id != p.id][:3]
        d = place_public(p)
        d["maps"] = maps_url(p)
        staff, staff_groups, hospital, units = [], [], None, []
        if p.category == "hospital":
            docs, _ = query_places(db, category="doctor", venue_name=p.slug, limit=200)
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
        return render_template(
            "detail.html",
            place=d,
            similar=similar,
            staff=staff,
            staff_groups=staff_groups,
            hospital=hospital,
            units=units,
            nav=p.category,
        )
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
                        u = User(email=email, password_hash=hash_password(password), name=name, role="user")
                        db.add(u)
                        db.commit()
                        db.refresh(u)
                        login_user(u)
                        return redirect("/hesap")
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
        return render_template("account.html", places=rows, nav="hesap")
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
                    db.commit()
                    flash("Gönderildi. Onay bekliyor — sitede henüz görünmez.", "ok")
                    return redirect("/hesap")
                finally:
                    db.close()
    return render_template("submit.html", err=err, nav="ekle", preset=request.args.get("cat") or "")


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
