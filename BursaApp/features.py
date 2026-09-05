"""Rota, yemek SEO, ilçe, harita, AI, favori, kampanya, işletme, SEO landing."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from urllib.parse import urlencode

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from auth import admin_required, load_user, login_required, rate_ok
from catalog import CAT_BY_KEY, ILCELER, hospital_staff_groups, maps_url, parse_dt, place_public, query_places, slugify, tags_dump, unique_slug
from discover import FALLBACK_LAT, FALLBACK_LNG, haversine_m, nearby, today_bursa, tonight, weekend
from foods import FAMOUS_FOODS, FOOD_BY_SLUG
from itinerary import ai_suggest, build_day_route
from models import (
    PLAN_TIERS,
    Campaign,
    ClaimRequest,
    Coupon,
    Editorial,
    Favorite,
    Place,
    Review,
    SavedRoute,
    SessionLocal,
    User,
)
from seo_pages import DISTRICT_SECTIONS, ILCE_SLUGS, SEO_LANDINGS
from seo import article_ld, for_district, for_food, for_seo_landing, page as seo_page

bp = Blueprint("features", __name__)

MAP_CATEGORIES = (
    ("", "Tümü"),
    ("food", "Restoran"),
    ("cafe", "Cafe"),
    ("visit", "Gezilecek"),
    ("hotel", "Otel"),
    ("camp", "Kamp"),
    ("event", "Etkinlik"),
    ("concert", "Konser"),
    ("market", "Market"),
    ("shop", "Alışveriş"),
    ("vet", "Veteriner"),
    ("hospital", "Hastane"),
    ("school", "Okul"),
)

MAP_RADIUS_OPTIONS = (
    (500, "500 m"),
    (1000, "1 km"),
    (2000, "2 km"),
    (5000, "5 km"),
    (0, "Sınırsız"),
)


def _map_query(
    *,
    cat: str = "",
    lat: float | None = None,
    lng: float | None = None,
    near: bool = False,
    radius_m: int = 2000,
    q: str = "",
) -> str:
    params: dict[str, str] = {}
    if near:
        params["near"] = "1"
    if cat:
        params["cat"] = cat
    if radius_m:
        params["r"] = str(radius_m)
    if lat is not None and lng is not None:
        params["lat"] = f"{lat:.5f}"
        params["lng"] = f"{lng:.5f}"
    q = (q or "").strip()
    if q:
        params["q"] = q
    return "/harita?" + urlencode(params) if params else "/harita"


def _near_search_match(p: Place, query: str) -> bool:
    query = (query or "").strip().lower()
    if not query:
        return True
    blob = " ".join(
        [
            p.title or "",
            p.ilce or "",
            p.address or "",
            p.category or "",
            p.subcategory or "",
            p.blurb or "",
        ]
    ).lower()
    return all(tok in blob for tok in query.split() if tok)


def _active_campaigns(db, limit=12, category: str | None = None):
    now = datetime.utcnow()
    rows = (
        db.query(Campaign)
        .filter(Campaign.status == "approved")
        .order_by(Campaign.id.desc())
        .limit(80)
        .all()
    )
    out = []
    for c in rows:
        if c.ends_at and c.ends_at < now:
            continue
        if c.starts_at and c.starts_at > now:
            continue
        p = db.get(Place, c.place_id)
        if not p or p.status != "approved":
            continue
        if category and p.category != category:
            continue
        out.append({"campaign": c, "place": place_public(p)})
        if len(out) >= limit:
            break
    return out


def active_campaign_for_place(db, place_id: int):
    """Tek market/yer için güncel onaylı kampanya (aktüel)."""
    now = datetime.utcnow()
    rows = (
        db.query(Campaign)
        .filter(Campaign.place_id == place_id, Campaign.status == "approved")
        .order_by(Campaign.id.desc())
        .limit(5)
        .all()
    )
    for c in rows:
        if c.ends_at and c.ends_at < now:
            continue
        if c.starts_at and c.starts_at > now:
            continue
        return c
    return None


# ---------- home extras helpers used by app ----------
def hub_context(db):
    today = today_bursa(db)
    pop_food, _ = query_places(db, category="food", order="rating", limit=6)
    cafes = [p for p in pop_food if (p.subcategory or "") == "cafe"]
    if len(cafes) < 3:
        more, _ = query_places(db, category="food", subcategory="cafe", order="rating", limit=6)
        cafes = more
    visits, _ = query_places(db, category="visit", limit=6)
    eds = db.query(Editorial).filter(Editorial.status == "approved").order_by(Editorial.id.desc()).limit(4).all()
    return {
        "today_data": today,
        "tonight_preview": tonight(db),
        "weekend_preview": weekend(db),
        "popular_food": [place_public(p) for p in pop_food[:6]],
        "popular_cafes": [place_public(p) for p in cafes[:6]],
        "popular_visit": [place_public(p) for p in visits[:6]],
        "campaigns": _active_campaigns(db, 4),
        "editorials": eds,
    }


@bp.route("/rota", methods=["GET", "POST"])
def rota():
    budget = 0
    people = 2
    transport = "bus"
    if request.method == "POST":
        try:
            budget = int(request.form.get("budget_tl") or 0)
        except ValueError:
            budget = 0
        try:
            people = max(1, min(int(request.form.get("people") or 2), 8))
        except ValueError:
            people = 2
        transport = (request.form.get("transport") or "bus").strip()
        if transport not in ("car", "bus", "walk"):
            transport = "bus"
    else:
        try:
            budget = int(request.args.get("budget") or 0)
        except ValueError:
            budget = 0
        transport = (request.args.get("transport") or "bus").strip()
        if transport not in ("car", "bus", "walk"):
            transport = "bus"
    db = SessionLocal()
    try:
        route = build_day_route(db, budget_tl=budget, people=people, transport=transport)
        if request.method == "POST" and load_user() and request.form.get("save") == "1":
            u = load_user()
            db.add(
                SavedRoute(
                    user_id=u.id,
                    title=route["title"],
                    budget_tl=budget,
                    slots_json=json.dumps(route["slots"], ensure_ascii=False),
                )
            )
            db.commit()
            flash("Rota kaydedildi.", "ok")
        return render_template(
            "rota.html",
            route=route,
            budget=budget,
            people=people,
            transport=transport,
            nav="rota",
        )
    finally:
        db.close()


@bp.route("/ai", methods=["GET", "POST"])
def ai_page():
    prompt = ""
    result = None
    chips = [
        "2 kişiyiz, araba yok, 2000 TL, tarihî yerler",
        "Ailece 4 kişi, otobüsle, ucuz yemek",
        "Sakin doğa, arabamız var, Gölyazı",
        "Yağmurlu gün, kapalı mekan",
        "Bu akşam konser / etkinlik ne var?",
        "Romantik akşam, Nilüfer cafe",
    ]
    if request.method == "POST":
        prompt = (request.form.get("prompt") or "").strip()
        if prompt and rate_ok("ai", limit=15):
            db = SessionLocal()
            try:
                result = ai_suggest(db, prompt)
            finally:
                db.close()
        elif not prompt:
            flash("Bir şey yaz — örneklerden birine tıkla.", "err")
    return render_template("ai.html", prompt=prompt, result=result, chips=chips, nav="ai")


@bp.route("/bursa-da-ne-yenir")
def ne_yenir():
    return render_template(
        "foods_index.html",
        foods=FAMOUS_FOODS,
        nav="yemek",
        seo=seo_page(
            title="Bursa'da Ne Yenir?",
            description="İskender, İnegöl köfte, Kemalpaşa ve Bursa'nın meşhur lezzetleri — nerede yenir rehberi.",
            path="/bursa-da-ne-yenir",
            breadcrumbs=[("Keşfet", "/"), ("Ne yenir?", "/bursa-da-ne-yenir")],
            keywords="bursa ne yenir, bursa iskender, bursa lezzet",
        ),
    )


@bp.route("/bursa-iskender")
@bp.route("/bursa-inegol-kofte")
@bp.route("/bursa-kemalpasa")
@bp.route("/bursa-pideli-kofte")
@bp.route("/bursa-kestane-sekeri")
@bp.route("/bursa-sut-helvasi")
def food_page():
    slug = request.path.strip("/")
    food = FOOD_BY_SLUG.get(slug)
    if not food:
        return redirect("/bursa-da-ne-yenir")
    db = SessionLocal()
    try:
        rows, _ = query_places(db, category="food", subcategory=food.get("subcategory"), order="rating", limit=12)
        if not rows:
            rows, _ = query_places(db, category="food", q=food["title"], order="rating", limit=12)
        reviews = []
        if rows:
            reviews = (
                db.query(Review)
                .filter(Review.place_id.in_([p.id for p in rows[:5]]), Review.status == "approved")
                .order_by(Review.updated_at.desc())
                .limit(8)
                .all()
            )
        return render_template(
            "food_detail.html",
            food=food,
            places=[place_public(p) for p in rows],
            reviews=[r.public() for r in reviews],
            nav="yemek",
            seo=for_food(food),
        )
    finally:
        db.close()


@bp.route("/ilce")
def ilce_index():
    from catalog import slugify as _sl
    pairs = [(_sl(ad), ad) for ad in ILCELER]
    return render_template("district_index.html", pairs=pairs, nav="ilce")


@bp.route("/ilce/<slug>")
def ilce_page(slug: str):
    name = ILCE_SLUGS.get(slug) or ILCE_SLUGS.get(slugify(slug))
    if not name:
        # try match
        for ad in ILCELER:
            if slugify(ad) == slug:
                name = ad
                break
    if not name:
        flash("İlçe bulunamadı", "err")
        return redirect("/ilce")
    db = SessionLocal()
    try:
        sections = []
        for key, label, cat in DISTRICT_SECTIONS:
            if key == "cafe":
                rows, _ = query_places(db, category="food", ilce=name, subcategory="cafe", order="rating", limit=8)
            elif cat == "event":
                rows, _ = query_places(db, category="event", ilce=name, order="date", limit=8)
                # also dated shows in ilce
                extra = (
                    db.query(Place)
                    .filter(
                        Place.status == "approved",
                        Place.ilce == name,
                        Place.category.in_(("concert", "theater", "cinema", "event")),
                    )
                    .order_by(Place.starts_at.asc().nulls_last())
                    .limit(8)
                    .all()
                )
                if extra:
                    rows = extra
            else:
                rows, _ = query_places(db, category=cat, ilce=name, order="rating" if cat == "food" else None, limit=8)
            sections.append({"key": key, "label": label, "places": [place_public(p) for p in rows]})
        return render_template(
            "district.html",
            ilce=name,
            ilce_slug=slugify(name),
            sections=sections,
            nav="ilce",
            seo=for_district(name, slugify(name)),
        )
    finally:
        db.close()


@bp.route("/etrafimda")
def etrafimda():
    args = request.args.to_dict()
    args["near"] = "1"
    if "r" not in args:
        args["r"] = "2000"
    return redirect("/harita?" + urlencode(args))


def _map_pin_gallery(d: dict, user_photo_urls: list | None = None) -> list[str]:
    """Kapak + extra galeri + onaylı kullanıcı fotoğrafları."""
    gallery: list[str] = []
    img = (d.get("img_url") or "").strip()
    if img:
        gallery.append(img)
    ex = d.get("extra") or {}
    gals = ex.get("gallery") if isinstance(ex.get("gallery"), list) else []
    for g in gals:
        u = (g or "").strip()
        if u and u not in gallery:
            gallery.append(u)
    for u in user_photo_urls or []:
        s = (u or "").strip()
        if s and s not in gallery:
            gallery.append(s)
    return gallery[:8]


def _map_pin_detail(d: dict, user_photo_urls: list | None = None) -> dict:
    blurb = (d.get("blurb") or "").strip()
    if len(blurb) > 320:
        blurb = blurb[:317].rstrip() + "…"
    return {
        "slug": d.get("slug"),
        "path": d.get("path"),
        "title": d.get("title"),
        "lat": d.get("lat"),
        "lng": d.get("lng"),
        "category": d.get("category"),
        "subcategory": d.get("subcategory"),
        "category_label": d.get("category_label"),
        "subcategory_label": d.get("subcategory_label") or "",
        "distance_m": d.get("distance_m"),
        "rating": d.get("rating"),
        "img_url": d.get("img_url"),
        "gallery": _map_pin_gallery(d, user_photo_urls),
        "blurb": blurb,
        "address": (d.get("address") or "").strip(),
        "ilce": (d.get("ilce") or "").strip(),
        "phone": (d.get("phone") or "").strip(),
        "web": (d.get("web") or "").strip(),
        "hours_text": (d.get("hours_text") or "").strip(),
        "price_band": (d.get("price_band") or "").strip(),
    }


@bp.route("/harita")
def harita():
    db = SessionLocal()
    try:
        near_mode = (request.args.get("near") or "").strip().lower() in ("1", "true", "yes")
        has_user_coords = request.args.get("lat") and request.args.get("lng")
        try:
            lat = float(request.args.get("lat") or FALLBACK_LAT)
            lng = float(request.args.get("lng") or FALLBACK_LNG)
        except ValueError:
            lat, lng = FALLBACK_LAT, FALLBACK_LNG
            has_user_coords = False
        used_fallback = not has_user_coords
        cat = (request.args.get("cat") or "").strip()
        q = (request.args.get("q") or "").strip()
        try:
            radius_m = int(request.args.get("r") or (2000 if near_mode else 0))
        except ValueError:
            radius_m = 2000 if near_mode else 0
        if radius_m not in (0, 500, 1000, 2000, 5000):
            radius_m = 2000 if near_mode else 0
        rows = (
            db.query(Place)
            .filter(Place.status == "approved", Place.lat.isnot(None), Place.lng.isnot(None))
            .all()
        )
        pins = []
        for p in rows:
            if cat == "cafe":
                if (p.subcategory or "") != "cafe":
                    continue
            elif cat and p.category != cat:
                continue
            if not _near_search_match(p, q):
                continue
            d = place_public(p)
            dist = int(haversine_m(lat, lng, float(p.lat), float(p.lng)))
            if radius_m and dist > radius_m:
                continue
            d["distance_m"] = dist
            pins.append(d)
        pins.sort(key=lambda x: x.get("distance_m") or 0)
        slim = []
        for d in pins[:200]:
            slim.append(
                {
                    "slug": d.get("slug"),
                    "path": d.get("path"),
                    "title": d.get("title"),
                    "lat": d.get("lat"),
                    "lng": d.get("lng"),
                    "category": d.get("category"),
                    "subcategory": d.get("subcategory"),
                    "category_label": d.get("category_label"),
                    "distance_m": d.get("distance_m"),
                    "rating": d.get("rating"),
                    "img_url": d.get("img_url"),
                }
            )
        seo = seo_page(
            title="Etrafımda ne var" if near_mode else "Harita",
            description=(
                "Konumuna göre en yakın restoran, gezilecek yer, market ve daha fazlası — Bursa haritası."
                if near_mode
                else "Bursa mekanları harita üzerinde; kategori filtreli keşif."
            ),
            path="/etrafimda" if near_mode else "/harita",
            breadcrumbs=[
                ("Ana Sayfa", "/"),
                ("Etrafımda ne var" if near_mode else "Harita", "/etrafimda" if near_mode else "/harita"),
            ],
        )
        near_pins = pins[:24]
        from models import PlacePhoto

        photo_map: dict[int, list[str]] = {}
        near_ids = [d.get("id") for d in near_pins if d.get("id")]
        if near_ids:
            for ph in (
                db.query(PlacePhoto)
                .filter(PlacePhoto.place_id.in_(near_ids), PlacePhoto.status == "approved")
                .order_by(PlacePhoto.id.desc())
                .all()
            ):
                photo_map.setdefault(ph.place_id, []).append(ph.img_url)
        near_slim = [
            _map_pin_detail(d, photo_map.get(d.get("id") or 0))
            for d in near_pins
        ]
        from map_tiles import leaflet_tile_layers

        tpl = "nearby_explore.html" if near_mode else "map.html"
        payload = dict(
            pins=near_pins if near_mode else pins[:200],
            pins_json=json.dumps(near_slim if near_mode else slim, ensure_ascii=False),
            total=len(pins),
            lat=lat,
            lng=lng,
            cat=cat,
            q=q,
            near_mode=near_mode,
            used_fallback=used_fallback,
            radius_m=radius_m,
            map_categories=MAP_CATEGORIES,
            map_radius_options=MAP_RADIUS_OPTIONS,
            map_query=_map_query,
            map_tiles=leaflet_tile_layers(),
            nav="harita",
            seo=seo,
        )
        return render_template(tpl, **payload)
    finally:
        db.close()


@bp.route("/kampanyalar")
def kampanyalar():
    db = SessionLocal()
    try:
        return render_template("campaigns.html", items=_active_campaigns(db, 30), nav="kampanya")
    finally:
        db.close()


@bp.route("/kuponlar", methods=["GET", "POST"])
def kuponlar():
    LOYALTY_COST = 100
    LOYALTY_PCT = 10
    user = load_user()
    db = SessionLocal()
    try:
        if request.method == "POST":
            if not user:
                flash("Kupon çevirmek için giriş yapın.", "err")
                return redirect("/giris?next=/kuponlar")
            u = db.get(User, user.id)
            if not u:
                flash("Oturum geçersiz.", "err")
                return redirect("/kuponlar")
            pts = int(u.loyalty_points or 0)
            if pts < LOYALTY_COST:
                flash(f"Yetersiz puan ({pts}/{LOYALTY_COST}). Yorum yazarak puan kazan.", "err")
                return redirect("/kuponlar")
            import secrets

            code = f"BA{u.id}{secrets.token_hex(3).upper()}"
            while db.query(Coupon).filter(Coupon.code == code).first():
                code = f"BA{u.id}{secrets.token_hex(3).upper()}"
            u.loyalty_points = pts - LOYALTY_COST
            db.add(
                Coupon(
                    code=code,
                    owner_user_id=u.id,
                    title=f"Sadakat kuponu · %{LOYALTY_PCT} (üyeye özel)",
                    discount_pct=LOYALTY_PCT,
                    max_uses=1,
                    status="active",
                    expires_at=datetime.utcnow() + timedelta(days=60),
                )
            )
            db.commit()
            flash(f"Kupon hazır: {code} · kalan puan {u.loyalty_points}", "ok")
            return redirect("/kuponlar")

        q = db.query(Coupon).filter(Coupon.status == "active")
        if user:
            q = q.filter(
                (Coupon.owner_user_id.is_(None)) | (Coupon.owner_user_id == user.id)
            )
        else:
            q = q.filter(Coupon.owner_user_id.is_(None))
        rows = q.order_by(Coupon.id.desc()).all()
        items = []
        for c in rows:
            place = db.get(Place, c.place_id) if c.place_id else None
            items.append({"coupon": c, "place": place_public(place) if place else None})
        points = 0
        if user:
            u = db.get(User, user.id)
            points = int(u.loyalty_points or 0) if u else 0
        return render_template(
            "coupons.html",
            items=items,
            points=points,
            cost=LOYALTY_COST,
            pct=LOYALTY_PCT,
            nav="kupon",
        )
    finally:
        db.close()


@bp.route("/oneriyor")
def oneriyor():
    db = SessionLocal()
    try:
        eds = db.query(Editorial).filter(Editorial.status == "approved").order_by(Editorial.id.desc()).all()
        return render_template("editorials.html", editorials=eds, nav="oneriyor")
    finally:
        db.close()


@bp.route("/oneriyor/<slug>")
def oneriyor_detail(slug: str):
    db = SessionLocal()
    try:
        ed = db.query(Editorial).filter(Editorial.slug == slug, Editorial.status == "approved").first()
        if not ed:
            return redirect("/oneriyor")
        try:
            slugs = json.loads(ed.place_slugs or "[]")
        except Exception:
            slugs = []
        places = []
        for s in slugs:
            p = db.query(Place).filter(Place.slug == s, Place.status == "approved").first()
            if p:
                places.append(place_public(p))
        return render_template(
            "editorial_detail.html",
            ed=ed,
            places=places,
            nav="oneriyor",
            seo=seo_page(
                title=ed.title,
                description=ed.blurb or ed.title,
                path=f"/oneriyor/{ed.slug}",
                breadcrumbs=[
                    ("Keşfet", "/"),
                    ("Öneriyor", "/oneriyor"),
                    (ed.title, f"/oneriyor/{ed.slug}"),
                ],
                json_ld=[
                    article_ld(
                        title=ed.title,
                        description=ed.blurb or ed.title,
                        path=f"/oneriyor/{ed.slug}",
                    )
                ],
            ),
        )
    finally:
        db.close()


@bp.route("/favori/<slug>", methods=["POST"])
@login_required
def favori_toggle(slug: str):
    user = load_user()
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == slug, Place.status == "approved").first()
        if not p:
            flash("Kayıt yok", "err")
            return redirect("/")
        fav = db.query(Favorite).filter(Favorite.user_id == user.id, Favorite.place_id == p.id).first()
        if fav:
            db.delete(fav)
            p.fav_count = max(0, (p.fav_count or 0) - 1)
            flash("Favoriden çıkarıldı", "ok")
        else:
            db.add(Favorite(user_id=user.id, place_id=p.id))
            p.fav_count = (p.fav_count or 0) + 1
            flash("Favorilere eklendi", "ok")
        db.commit()
        return redirect(request.referrer or f"/yer/{slug}")
    finally:
        db.close()


@bp.route("/yer/<slug>/sahiplen", methods=["GET", "POST"])
@login_required
def sahiplen(slug: str):
    user = load_user()
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == slug, Place.status == "approved").first()
        if not p:
            flash("Kayıt yok", "err")
            return redirect("/")
        if request.method == "POST":
            if p.owner_user_id and p.claim_status == "approved":
                flash("Bu işletme zaten sahiplenilmiş.", "err")
            else:
                existing = (
                    db.query(ClaimRequest)
                    .filter(ClaimRequest.place_id == p.id, ClaimRequest.user_id == user.id, ClaimRequest.status == "pending")
                    .first()
                )
                if existing:
                    flash("Talebin zaten bekliyor.", "ok")
                else:
                    from admin_forms import save_upload

                    note = (request.form.get("note") or "").strip()[:400]
                    tax_f = request.files.get("tax_doc")
                    id_f = request.files.get("id_doc")
                    if not tax_f or not getattr(tax_f, "filename", ""):
                        flash("Vergi levhası fotoğrafı gerekli.", "err")
                        return redirect(f"/yer/{slug}/sahiplen")
                    if not id_f or not getattr(id_f, "filename", ""):
                        flash("Yetkili kimlik fotoğrafı gerekli.", "err")
                        return redirect(f"/yer/{slug}/sahiplen")
                    tax_url, tax_err = save_upload(tax_f, category="claim")
                    if tax_err:
                        flash(f"Vergi levhası: {tax_err}", "err")
                        return redirect(f"/yer/{slug}/sahiplen")
                    id_url, id_err = save_upload(id_f, category="claim")
                    if id_err:
                        flash(f"Kimlik: {id_err}", "err")
                        return redirect(f"/yer/{slug}/sahiplen")
                    db.add(
                        ClaimRequest(
                            place_id=p.id,
                            user_id=user.id,
                            note=note,
                            tax_doc_url=tax_url or "",
                            id_doc_url=id_url or "",
                            status="pending",
                        )
                    )
                    p.claim_status = "pending"
                    db.commit()
                    return redirect(
                        "/tesekkur?from=sahiplen&next="
                        + quote(f"/yer/{slug}", safe="")
                        + "&label="
                        + quote("Yer sayfasına dön", safe="")
                    )
                return redirect(f"/yer/{slug}")
        return render_template("claim.html", place=place_public(p), nav="hesap")
    finally:
        db.close()


@bp.route("/isletme")
@login_required
def isletme_panel():
    user = load_user()
    db = SessionLocal()
    try:
        owned = db.query(Place).filter(Place.owner_user_id == user.id, Place.claim_status == "approved").all()
        return render_template("business.html", places=[place_public(p) for p in owned], tiers=PLAN_TIERS, nav="isletme")
    finally:
        db.close()


@bp.route("/isletme/<slug>", methods=["GET", "POST"])
@login_required
def isletme_edit(slug: str):
    user = load_user()
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == slug, Place.owner_user_id == user.id).first()
        if not p:
            flash("İşletme yok veya senin değil", "err")
            return redirect("/isletme")
        if request.method == "POST":
            p.blurb = (request.form.get("blurb") or "").strip()
            p.body = (request.form.get("body") or "").strip()
            p.phone = (request.form.get("phone") or "").strip()
            p.web = (request.form.get("web") or "").strip()
            p.hours_text = (request.form.get("hours_text") or "").strip()
            p.instagram = (request.form.get("instagram") or "").strip()
            p.whatsapp = (request.form.get("whatsapp") or "").strip()
            if (p.plan_tier or "free") in ("pro", "premium"):
                p.menu_text = (request.form.get("menu_text") or "").strip()
            # kampanya oluştur
            ctitle = (request.form.get("campaign_title") or "").strip()
            if ctitle and (p.plan_tier or "free") in ("pro", "premium"):
                db.add(
                    Campaign(
                        place_id=p.id,
                        title=ctitle,
                        body=(request.form.get("campaign_body") or "").strip(),
                        badge=(request.form.get("campaign_badge") or "").strip(),
                        status="pending",
                        starts_at=datetime.utcnow(),
                        ends_at=datetime.utcnow() + timedelta(days=30),
                    )
                )
                flash("Kampanya onaya gönderildi", "ok")
            # plan yükselt (ödeme stub)
            tier = (request.form.get("plan_tier") or "").strip()
            if tier in PLAN_TIERS and tier != (p.plan_tier or "free"):
                p.plan_tier = tier
                p.plan_until = datetime.utcnow() + timedelta(days=30)
                flash(f"{PLAN_TIERS[tier]['label']} planı işaretlendi (ödeme entegrasyonu yakında · {PLAN_TIERS[tier]['price_tl']} TL/ay).", "ok")
            db.commit()
            flash("Kaydedildi", "ok")
            return redirect(f"/isletme/{slug}")
        camps = db.query(Campaign).filter(Campaign.place_id == p.id).order_by(Campaign.id.desc()).limit(10).all()
        return render_template(
            "business_edit.html",
            place=p,
            camps=camps,
            tiers=PLAN_TIERS,
            nav="isletme",
        )
    finally:
        db.close()


@bp.route("/etkinlik/ekle", methods=["GET", "POST"])
@login_required
def etkinlik_ekle():
    user = load_user()
    err = ""
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        date_s = (request.form.get("event_date") or "").strip()
        time_s = (request.form.get("event_time") or "").strip() or "20:00"
        starts = None
        if date_s:
            starts = parse_dt(f"{date_s}T{time_s}")
        if not starts:
            starts = parse_dt(request.form.get("starts_at"))
        if not title or not starts:
            err = "Etkinlik adı ve tarih zorunlu."
        else:
            db = SessionLocal()
            try:
                cat = (request.form.get("category") or "event").strip()
                if cat not in ("event", "concert", "theater", "cinema", "family"):
                    cat = "event"
                img_url = (request.form.get("img_url") or "").strip()
                try:
                    from admin_forms import save_upload

                    up, _err = save_upload(request.files.get("cover_file"), category="event")
                    if up:
                        img_url = up
                except Exception:
                    pass
                p = Place(
                    title=title,
                    slug=unique_slug(db, title),
                    category=cat,
                    ilce=(request.form.get("ilce") or "").strip(),
                    address=(request.form.get("address") or "").strip(),
                    venue_name=(request.form.get("venue_name") or "").strip(),
                    blurb=(request.form.get("blurb") or request.form.get("description") or "").strip(),
                    body=(request.form.get("body") or request.form.get("description") or "").strip(),
                    img_url=img_url,
                    ticket_price=(request.form.get("ticket_price") or "").strip(),
                    ticket_url=(request.form.get("ticket_url") or "").strip(),
                    instagram=(request.form.get("instagram") or "").strip(),
                    web=(request.form.get("web") or "").strip(),
                    starts_at=starts,
                    ends_at=parse_dt(request.form.get("ends_at")),
                    status="pending",
                    submitted_by_id=user.id,
                    tags=tags_dump(["etkinlik"]),
                )
                db.add(p)
                db.commit()
                flash("Etkinlik gönderildi — admin onayından sonra yayınlanır.", "ok")
                return redirect("/hesap")
            finally:
                db.close()
    return render_template("event_submit.html", err=err, ilceler=ILCELER, nav="ekle")


@bp.route("/yer/<slug>/one-cikar", methods=["POST"])
@login_required
def one_cikar(slug: str):
    user = load_user()
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == slug).first()
        if not p:
            flash("Yok", "err")
            return redirect("/")
        if p.submitted_by_id != user.id and p.owner_user_id != user.id and user.role != "admin":
            flash("Yetki yok", "err")
            return redirect(f"/yer/{slug}")
        days = 7
        try:
            days = int(request.form.get("days") or 7)
        except ValueError:
            days = 7
        p.boost_until = datetime.utcnow() + timedelta(days=max(1, min(days, 30)))
        p.featured = True
        db.commit()
        flash(f"{days} gün öne çıkarma işaretlendi (ödeme stub · 99 TL/7 gün).", "ok")
        return redirect(f"/yer/{slug}")
    finally:
        db.close()


@bp.route("/hesap/bildirimler", methods=["GET", "POST"])
@login_required
def bildirimler():
    user = load_user()
    db = SessionLocal()
    try:
        u = db.get(User, user.id)
        if request.method == "POST":
            u.notify_concert = request.form.get("notify_concert") == "1"
            u.notify_theater = request.form.get("notify_theater") == "1"
            u.notify_festival = request.form.get("notify_festival") == "1"
            u.notify_campaign = request.form.get("notify_campaign") == "1"
            u.notify_new_place = request.form.get("notify_new_place") == "1"
            db.commit()
            db.refresh(u)
            flash("Bildirim tercihleri kaydedildi.", "ok")
            return redirect("/hesap/bildirimler?saved=1")
        db.refresh(u)
        return render_template("notify.html", u=u, nav="hesap")
    finally:
        db.close()


@bp.route("/premium")
def premium_page():
    return render_template("premium.html", tiers=PLAN_TIERS, nav="premium")


@bp.route("/premium/checkout", methods=["POST"])
@login_required
def premium_checkout():
    """Sandbox ödeme — gerçek PSP yok; planı işletme kaydına işler."""
    user = load_user()
    tier = (request.form.get("tier") or "").strip()
    slug = (request.form.get("slug") or "").strip()
    if tier not in PLAN_TIERS or tier == "free":
        flash("Geçersiz paket.", "err")
        return redirect("/premium")
    db = SessionLocal()
    try:
        p = None
        if slug:
            p = db.query(Place).filter(Place.slug == slug).first()
        if p is None:
            owned = (
                db.query(Place)
                .filter(Place.owner_user_id == user.id, Place.claim_status == "approved")
                .order_by(Place.id.desc())
                .first()
            )
            p = owned
        if p is None:
            flash("Önce bir işletmeyi sahiplenin / onaylatın.", "err")
            return redirect("/isletme")
        if p.owner_user_id not in (None, user.id) and user.role != "admin":
            flash("Bu işletme size ait değil.", "err")
            return redirect("/premium")
        if p.owner_user_id is None:
            p.owner_user_id = user.id
            p.claim_status = "approved"
        p.plan_tier = tier
        p.plan_until = datetime.utcnow() + timedelta(days=30)
        db.commit()
        price = PLAN_TIERS[tier]["price_tl"]
        flash(
            f"Sandbox ödeme OK · {PLAN_TIERS[tier]['label']} ({price} TL/ay) · "
            f"{p.title} · bitiş {p.plan_until.strftime('%d.%m.%Y')}",
            "ok",
        )
        return redirect("/isletme")
    finally:
        db.close()


# SEO landings + /bursa-{slug} yer sayfaları (örn. /bursa-ulu-cami)
@bp.route("/bursa-restoranlari")
@bp.route("/bursa-cafeler")
@bp.route("/bursa-kahvalti")
@bp.route("/bursa-kahvalti-mekanlari")
@bp.route("/bursa-konserleri")
@bp.route("/bursa-tiyatro")
@bp.route("/bursa-gezilecek-yerler")
def seo_landing():
    return _render_seo_landing(request.path.strip("/"))


@bp.route("/bursa-<slug>")
def bursa_slug_page(slug: str):
    """SEO yer detayı — /bursa-ulu-cami · landing değilse Place."""
    from seo_urls import RESERVED_BURSA_PATHS, path_to_place_slug

    key = f"bursa-{slug}"
    if key in SEO_LANDINGS:
        return _render_seo_landing(key)
    if key in FOOD_BY_SLUG or key in RESERVED_BURSA_PATHS:
        # meşhur yemek / rezerve — mevcut exact route yoksa gezilecek
        if key in FOOD_BY_SLUG:
            return redirect(f"/{key}")
        return redirect("/")
    place_slug = path_to_place_slug(key)
    db = SessionLocal()
    try:
        p = db.query(Place).filter(Place.slug == place_slug, Place.status == "approved").first()
        if p is None:
            p = db.query(Place).filter(Place.slug == key, Place.status == "approved").first()
        if p is None:
            return redirect("/gezilecek")
        return _render_place_detail(db, p)
    finally:
        db.close()


def _render_seo_landing(key: str):
    meta = SEO_LANDINGS.get(key)
    if not meta:
        return redirect("/")
    db = SessionLocal()
    try:
        rows, total = query_places(
            db,
            category=meta.get("category"),
            subcategory=meta.get("subcategory"),
            order="rating" if meta.get("category") == "food" else "date",
            limit=60,
        )
        exclude = set(meta.get("exclude_sub") or ())
        places = [place_public(p) for p in rows if (p.subcategory or "") not in exclude]
        return render_template(
            "seo_landing.html",
            meta=meta,
            places=places,
            total=len(places),
            nav="kesfet",
            seo=for_seo_landing(meta, f"/{key}", places),
        )
    finally:
        db.close()


def _render_place_detail(db, p: Place):
    from catalog import DOCTOR_SPECS
    from models import review_dimension_avgs
    from seo import for_place

    p.views = int(p.views or 0) + 1
    db.commit()
    similar, _ = query_places(db, category=p.category, limit=6)
    similar = [place_public(s) for s in similar if s.id != p.id][:3]
    d = place_public(p)
    if d.get("img_full"):
        d["img_url"] = d["img_full"]
    d["maps"] = maps_url(p)
    venue_events = []
    if p.category in ("event", "concert", "theater") and (p.venue_name or p.address):
        vn = (p.venue_name or "").strip()
        addr = (p.address or "").strip()
        q = db.query(Place).filter(
            Place.status == "approved",
            Place.category.in_(("event", "concert", "theater")),
            Place.id != p.id,
        )
        if vn:
            q = q.filter((Place.venue_name == vn) | (Place.address == vn))
        elif addr:
            q = q.filter(Place.address == addr)
        venue_events = [place_public(x) for x in q.order_by(Place.starts_at.asc().nulls_last()).limit(8).all()]
    school_events = []
    if p.category == "school":
        school_events = [
            place_public(x)
            for x in db.query(Place)
            .filter(Place.status == "approved", Place.category == "event", Place.venue_name == p.slug)
            .order_by(Place.starts_at.desc().nulls_last())
            .limit(24)
            .all()
        ]
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
        is_fav = (
            db.query(Favorite).filter(Favorite.user_id == user.id, Favorite.place_id == p.id).first()
            is not None
        )
    from feed_social import going_count as _going_count, user_is_going

    going_count = _going_count(db, p.id)
    if user:
        is_going = user_is_going(db, user.id, p.id)
    dims = review_dimension_avgs(db, p.id)
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


@bp.route("/<ilce_slug>-restoranlari")
@bp.route("/<ilce_slug>-cafeler")
def seo_ilce_cat(ilce_slug: str):
    name = ILCE_SLUGS.get(ilce_slug)
    if not name:
        for ad in ILCELER:
            if slugify(ad) == ilce_slug:
                name = ad
                break
    if not name:
        return redirect("/")
    want_cafe = request.path.endswith("-cafeler")
    db = SessionLocal()
    try:
        if want_cafe:
            rows, _ = query_places(db, category="food", ilce=name, subcategory="cafe", order="rating", limit=60)
            meta = {
                "title": f"{name} Cafeler",
                "h1": f"{name}'de Cafeler",
                "desc": f"{name} ilçesindeki en iyi cafeler, çalışma alanları ve kahve mekanları — BursaApp.",
            }
        else:
            rows, _ = query_places(db, category="food", ilce=name, order="rating", limit=60)
            meta = {
                "title": f"{name} Restoranları",
                "h1": f"{name}'de Restoranlar",
                "desc": f"{name} restoran ve yeme-içme rehberi: İskender'den cafe'ye — BursaApp.",
            }
        places = [place_public(p) for p in rows]
        return render_template(
            "seo_landing.html",
            meta=meta,
            places=places,
            total=len(places),
            nav="ilce",
            seo=for_seo_landing(meta, request.path, places),
        )
    finally:
        db.close()


@bp.route("/api/v1/map")
def api_map():
    db = SessionLocal()
    try:
        rows = (
            db.query(Place)
            .filter(Place.status == "approved", Place.lat.isnot(None), Place.lng.isnot(None))
            .limit(300)
            .all()
        )
        return jsonify({"ok": True, "places": [place_public(p) for p in rows]})
    finally:
        db.close()


@bp.route("/api/v1/route")
def api_route():
    try:
        budget = int(request.args.get("budget") or 0)
    except ValueError:
        budget = 0
    try:
        people = int(request.args.get("people") or 2)
    except ValueError:
        people = 2
    db = SessionLocal()
    try:
        return jsonify({"ok": True, **build_day_route(db, budget_tl=budget, people=people)})
    finally:
        db.close()


@bp.route("/api/v1/ai", methods=["POST"])
def api_ai():
    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"ok": False, "error": "prompt gerekli"}), 400
    db = SessionLocal()
    try:
        return jsonify({"ok": True, **ai_suggest(db, prompt)})
    finally:
        db.close()
