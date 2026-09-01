"""Admin HTML — kuyruk onay / red / düzenle."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from auth import admin_required, load_user
from catalog import CATEGORIES, ILCELER, parse_dt, tags_dump, tags_load, unique_slug
from models import Place, SessionLocal

bp = Blueprint("admin_pages", __name__)


@bp.route("/admin")
@admin_required
def queue():
    status = (request.args.get("status") or "pending").strip()
    if status not in ("pending", "approved", "rejected"):
        status = "pending"
    db = SessionLocal()
    try:
        rows = db.query(Place).filter(Place.status == status).order_by(Place.id.desc()).all()
        counts = {
            "pending": db.query(Place).filter(Place.status == "pending").count(),
            "approved": db.query(Place).filter(Place.status == "approved").count(),
            "rejected": db.query(Place).filter(Place.status == "rejected").count(),
        }
        return render_template("admin/queue.html", rows=rows, status=status, counts=counts, nav="admin")
    finally:
        db.close()


@bp.route("/admin/places/<int:pid>/approve", methods=["POST"])
@admin_required
def approve(pid: int):
    user = load_user()
    db = SessionLocal()
    try:
        p = db.get(Place, pid)
        if p:
            p.status = "approved"
            p.reviewed_by_id = user.id
            p.reviewed_at = datetime.utcnow()
            p.reject_reason = ""
            db.commit()
            flash(f"Onaylandı: {p.title}", "ok")
    finally:
        db.close()
    return redirect(request.referrer or url_for("admin_pages.queue"))


@bp.route("/admin/places/<int:pid>/reject", methods=["POST"])
@admin_required
def reject(pid: int):
    user = load_user()
    reason = (request.form.get("reason") or "").strip()
    db = SessionLocal()
    try:
        p = db.get(Place, pid)
        if p:
            p.status = "rejected"
            p.reject_reason = reason or "uygun değil"
            p.reviewed_by_id = user.id
            p.reviewed_at = datetime.utcnow()
            db.commit()
            flash(f"Reddedildi: {p.title}", "err")
    finally:
        db.close()
    return redirect(request.referrer or url_for("admin_pages.queue"))


@bp.route("/admin/places/<int:pid>", methods=["GET", "POST"])
@admin_required
def edit(pid: int):
    db = SessionLocal()
    try:
        p = db.get(Place, pid)
        if p is None:
            flash("Kayıt yok", "err")
            return redirect(url_for("admin_pages.queue"))
        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            cat = (request.form.get("category") or "").strip()
            if not title:
                flash("Başlık gerekli", "err")
            else:
                p.title = title
                p.slug = unique_slug(db, title, exclude_id=p.id)
                if cat in {c["key"] for c in CATEGORIES}:
                    p.category = cat
                p.ilce = (request.form.get("ilce") or "").strip()
                p.address = (request.form.get("address") or "").strip()
                p.phone = (request.form.get("phone") or "").strip()
                p.web = (request.form.get("web") or "").strip()
                p.hours_text = (request.form.get("hours_text") or "").strip()
                p.price_band = (request.form.get("price_band") or "").strip()
                p.blurb = (request.form.get("blurb") or "").strip()
                p.body = (request.form.get("body") or "").strip()
                p.img_url = (request.form.get("img_url") or "").strip()
                p.venue_name = (request.form.get("venue_name") or "").strip()
                p.tags = tags_dump(request.form.get("tags") or "")
                p.starts_at = parse_dt(request.form.get("starts_at"))
                p.ends_at = parse_dt(request.form.get("ends_at"))
                p.featured = request.form.get("featured") == "1"
                try:
                    p.rating_admin = float(request.form.get("rating_admin") or "") or None
                except ValueError:
                    pass
                try:
                    p.lat = float(request.form.get("lat")) if request.form.get("lat") else None
                except ValueError:
                    p.lat = None
                try:
                    p.lng = float(request.form.get("lng")) if request.form.get("lng") else None
                except ValueError:
                    p.lng = None
                st = request.form.get("status")
                if st in ("pending", "approved", "rejected"):
                    p.status = st
                db.commit()
                flash("Kaydedildi", "ok")
                return redirect(url_for("admin_pages.edit", pid=p.id))
        return render_template(
            "admin/edit.html",
            p=p,
            tags_text=", ".join(tags_load(p.tags)),
            categories=CATEGORIES,
            ilceler=ILCELER,
            nav="admin",
        )
    finally:
        db.close()
