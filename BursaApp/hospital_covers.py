"""Hastane kapak fotoğrafları — elle eklenen görseller korunur.

Kural: static/hospital/{slug}.jpg veya hospitals.json img_url varsa
otomatik betikler (seed, SEO fix, visit copy) üzerine yazmaz.
"""
from __future__ import annotations

import os

_DIR = os.path.dirname(os.path.abspath(__file__))
HOSPITAL_DIR = os.path.join(_DIR, "static", "hospital")


def cover_file(slug: str) -> str:
    return os.path.join(HOSPITAL_DIR, f"{slug}.jpg")


def cover_url(slug: str) -> str:
    return f"/static/hospital/{slug}.jpg"


def has_cover_file(slug: str, *, min_bytes: int = 8000) -> bool:
    path = cover_file(slug)
    try:
        return os.path.isfile(path) and os.path.getsize(path) >= min_bytes
    except OSError:
        return False


def is_locked_path(rel: str, *, min_bytes: int = 8000) -> bool:
    """static/hospital/*.jpg mevcutsa otomatik kopya/fetch yasak."""
    rel = (rel or "").lstrip("/")
    if not rel.startswith("static/hospital/") or not rel.endswith(".jpg"):
        return False
    path = os.path.join(_DIR, rel)
    try:
        return os.path.isfile(path) and os.path.getsize(path) >= min_bytes
    except OSError:
        return False


def resolve_img_url(raw: dict, existing) -> str | None:
    """Seed için img_url. None = güncellemede mevcut DB değerini koru."""
    slug = raw.get("slug") or ""
    json_img = (raw.get("img_url") or "").strip()
    if json_img:
        return json_img
    if slug and has_cover_file(slug):
        return cover_url(slug)
    if existing is not None and (existing.img_url or "").strip():
        return None
    return ""
