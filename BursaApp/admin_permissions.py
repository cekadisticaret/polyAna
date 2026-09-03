"""Admin panel rolleri ve izin kontrolü."""
from __future__ import annotations

import json
import re
from typing import Iterable

# (anahtar, etiket, grup)
ADMIN_PERMISSIONS: tuple[tuple[str, str, str], ...] = (
    ("dashboard", "Dashboard", "Genel"),
    ("queue", "Yer kuyruğu", "İçerik"),
    ("categories", "Kategoriler", "İçerik"),
    ("places", "Yer düzenleme", "İçerik"),
    ("reviews", "İçerik moderasyonu", "Moderasyon"),
    ("photos", "Üye fotoğrafları", "Moderasyon"),
    ("claims", "Sahiplenme", "İşletme"),
    ("campaigns", "Kampanyalar", "İşletme"),
    ("matches", "Bursaspor maçları", "İçerik"),
    ("members", "Üye listesi", "Üyeler"),
    ("activity", "Aktivite / giriş", "Sistem"),
    ("seo", "SEO paneli", "Sistem"),
)

ALL_PERM_KEYS = frozenset(k for k, _, _ in ADMIN_PERMISSIONS)
_STAFF_ONLY = "__staff_only__"


def permission_groups() -> list[dict]:
    out: dict[str, list[dict]] = {}
    for key, label, group in ADMIN_PERMISSIONS:
        out.setdefault(group, []).append({"key": key, "label": label})
    return [{"label": g, "perms": items} for g, items in out.items()]


def parse_permissions(raw: str | None) -> set[str]:
    if not raw:
        return set()
    try:
        data = json.loads(raw)
    except Exception:
        return set()
    if not isinstance(data, list):
        return set()
    return {str(x) for x in data if str(x) in ALL_PERM_KEYS}


def dump_permissions(perms: Iterable[str]) -> str:
    clean = sorted({p for p in perms if p in ALL_PERM_KEYS})
    return json.dumps(clean, ensure_ascii=False)


def is_super_admin(user) -> bool:
    return bool(user) and getattr(user, "role", "") == "admin"


def is_editor(user) -> bool:
    return bool(user) and getattr(user, "role", "") == "editor"


def panel_perms(user) -> set[str]:
    if not user:
        return set()
    if is_super_admin(user):
        return set(ALL_PERM_KEYS)
    if is_editor(user):
        return parse_permissions(getattr(user, "permissions_json", None) or "[]")
    return set()


def can_access_panel(user) -> bool:
    return is_super_admin(user) or bool(panel_perms(user))


def has_perm(user, perm: str) -> bool:
    if not user:
        return False
    return perm in panel_perms(user)


def role_label(role: str) -> str:
    return {"admin": "Tam yetki", "editor": "Editör", "user": "Üye"}.get(role or "", role or "Üye")


def required_perm_for_path(path: str) -> str | None:
    p = (path or "").split("?", 1)[0].rstrip("/") or "/"
    if p.startswith("/admin/staff"):
        return _STAFF_ONLY
    if p.startswith("/admin/categories"):
        return "categories"
    if p.startswith("/admin/dashboard"):
        return "dashboard"
    if p.startswith("/admin/users"):
        return "members"
    if p.startswith("/admin/activity"):
        return "activity"
    if p.startswith("/admin/reviews"):
        return "reviews"
    if p.startswith("/admin/posts") or p.startswith("/admin/visit-notes"):
        return "reviews"
    if p.startswith("/admin/photos"):
        return "photos"
    if p.startswith("/admin/seo"):
        return "seo"
    if p.startswith("/admin/claims"):
        return "claims"
    if p.startswith("/admin/campaigns"):
        return "campaigns"
    if p.startswith("/admin/matches"):
        return "matches"
    if p == "/admin/new" or p.startswith("/admin/new/"):
        return "places"
    if re.match(r"^/admin/\d+/approve$", p) or re.match(r"^/admin/\d+/reject$", p):
        return "queue"
    if re.match(r"^/admin/\d+/edit$", p) or re.match(r"^/admin/\d+/delete$", p):
        return "places"
    if p == "/admin":
        return "queue"
    return "dashboard"


def check_path_access(user, path: str) -> tuple[bool, str | None]:
    """(izin_var, gerekli_izin veya staff_only)"""
    if not can_access_panel(user):
        return False, None
    need = required_perm_for_path(path)
    if need == _STAFF_ONLY:
        return is_super_admin(user), _STAFF_ONLY
    if need and not has_perm(user, need):
        return False, need
    return True, need


_PANEL_HOME = (
    ("dashboard", "/admin/dashboard"),
    ("queue", "/admin?status=pending"),
    ("categories", "/admin/categories"),
    ("reviews", "/admin/reviews"),
    ("photos", "/admin/photos"),
    ("claims", "/admin/claims"),
    ("campaigns", "/admin/campaigns"),
    ("matches", "/admin/matches"),
    ("members", "/admin/users"),
    ("activity", "/admin/activity"),
    ("seo", "/admin/seo"),
    ("places", "/admin/new"),
)


def first_panel_url(user) -> str:
    perms = panel_perms(user)
    for key, url in _PANEL_HOME:
        if key in perms:
            return url
    return "/admin/dashboard" if is_super_admin(user) else "/"
