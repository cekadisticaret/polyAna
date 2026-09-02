"""Admin form yardımcılar — menü / galeri / ücret / kadro parse."""
from __future__ import annotations

import json
import os
import re
import uuid
from werkzeug.utils import secure_filename

_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_ROOT = os.path.join(_DIR, "static", "uploads")
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def parse_lines_kv(text: str, *, sep: str = "|") -> list[dict]:
    """Satır satır 'ad | fiyat | not' → [{name, price, note}]."""
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(sep)]
        name = parts[0] if parts else ""
        if not name:
            continue
        price = parts[1] if len(parts) > 1 else ""
        note = parts[2] if len(parts) > 2 else ""
        rows.append({"name": name, "price": price, "note": note})
    return rows


def parse_simple_list(text: str) -> list[str]:
    out = []
    for line in (text or "").replace(",", "\n").splitlines():
        s = line.strip()
        if s:
            out.append(s)
    return out


def parse_staff(text: str) -> list[dict]:
    """'Dr. Ali · Veteriner' veya 'Dr. Ali | Veteriner'."""
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            parts = [p.strip() for p in line.split("|", 1)]
        elif " · " in line:
            parts = [p.strip() for p in line.split(" · ", 1)]
        elif " - " in line:
            parts = [p.strip() for p in line.split(" - ", 1)]
        else:
            parts = [line, ""]
        rows.append({"name": parts[0], "role": parts[1] if len(parts) > 1 else ""})
    return rows


def format_menu_text(items: list) -> str:
    lines = []
    for it in items or []:
        if isinstance(it, dict):
            name = it.get("name") or ""
            price = it.get("price") or ""
            note = it.get("note") or it.get("desc") or ""
            if name:
                lines.append(" | ".join(x for x in (name, price, note) if x))
        elif isinstance(it, str) and it.strip():
            lines.append(it.strip())
    return "\n".join(lines)


def format_staff_text(items: list) -> str:
    lines = []
    for it in items or []:
        if isinstance(it, dict):
            name = it.get("name") or ""
            role = it.get("role") or ""
            if name:
                lines.append(f"{name} · {role}".rstrip(" ·"))
        elif isinstance(it, str) and it.strip():
            lines.append(it.strip())
    return "\n".join(lines)


def format_list_text(items: list) -> str:
    out = []
    for it in items or []:
        if isinstance(it, dict):
            name = it.get("name") or ""
            price = it.get("price") or ""
            note = it.get("note") or ""
            if name:
                out.append(" | ".join(x for x in (name, price, note) if x))
        elif isinstance(it, str) and it.strip():
            out.append(it.strip())
    return "\n".join(out)


def save_upload(file_storage, *, category: str = "misc") -> str | None:
    """Multipart dosyayı static/uploads/<cat>/ altına yazar; /static/... yolu döner."""
    if not file_storage or not getattr(file_storage, "filename", None):
        return None
    name = secure_filename(file_storage.filename or "")
    if not name:
        return None
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXT:
        return None
    cat = re.sub(r"[^a-z0-9_-]+", "", (category or "misc").lower()) or "misc"
    dest_dir = os.path.join(UPLOAD_ROOT, cat)
    os.makedirs(dest_dir, exist_ok=True)
    fname = f"{uuid.uuid4().hex[:12]}{ext}"
    path = os.path.join(dest_dir, fname)
    file_storage.save(path)
    return f"/static/uploads/{cat}/{fname}"


def build_extra_from_form(form, existing: dict | None = None) -> dict:
    ex = dict(existing or {})
    menu = parse_lines_kv(form.get("menu_lines") or "")
    fees = parse_lines_kv(form.get("fee_lines") or "")
    services = parse_simple_list(form.get("services_text") or "")
    staff = parse_staff(form.get("staff_lines") or "")
    gallery_raw = parse_simple_list(form.get("gallery_urls") or "")
    if menu:
        ex["menu"] = menu
    elif "menu_lines" in form:
        ex["menu"] = []
    if fees:
        ex["fees"] = fees
    elif "fee_lines" in form:
        ex["fees"] = []
    if services:
        ex["services"] = services
    elif "services_text" in form:
        ex["services"] = []
    if staff:
        ex["staff"] = staff
    elif "staff_lines" in form:
        ex["staff"] = []
    if gallery_raw:
        ex["gallery"] = gallery_raw
    elif "gallery_urls" in form:
        ex["gallery"] = []
    if "specialty_detail" in form:
        ex["specialty_detail"] = (form.get("specialty_detail") or "").strip()
    if "fee_note" in form:
        ex["fee_note"] = (form.get("fee_note") or "").strip()
    return ex


def dump_json_safe(obj) -> str:
    try:
        return json.dumps(obj or {}, ensure_ascii=False, indent=2)
    except Exception:
        return "{}"
