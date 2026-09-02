"""Yerel görsel önbellek — uzak URL'yi diskte tutar, TTL dolmadan yeniden indirmez."""
from __future__ import annotations

import os
import time
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_ROOT = os.path.join(_DIR, "static", "cache")
DEFAULT_TTL = 30 * 24 * 3600  # 30 gün
UA = "Mozilla/5.0 (compatible; BursaApp/1.0; +https://bursaapp.com)"


def cache_path(category: str, filename: str) -> str:
    cat = "".join(c for c in (category or "misc").lower() if c.isalnum() or c in "-_") or "misc"
    return os.path.join(CACHE_ROOT, cat, filename)


def public_url(category: str, filename: str) -> str:
    cat = "".join(c for c in (category or "misc").lower() if c.isalnum() or c in "-_") or "misc"
    return f"/static/cache/{cat}/{filename}"


def is_fresh(path: str, ttl: int = DEFAULT_TTL) -> bool:
    if not path or not os.path.isfile(path):
        return False
    try:
        return (time.time() - os.path.getmtime(path)) < ttl
    except OSError:
        return False


def ensure_cached(
    url: str,
    *,
    category: str,
    filename: str,
    ttl: int = DEFAULT_TTL,
    min_bytes: int = 2000,
) -> str | None:
    """
    URL'yi indirip static/cache altında tutar.
    Taze dosya varsa ağı yok sayar → sayfa yenilemede yeniden çekmez.
    Dönüş: /static/cache/... veya None.
    """
    if not url or not filename:
        return None
    dest = cache_path(category, filename)
    if is_fresh(dest, ttl) and os.path.getsize(dest) >= min_bytes:
        return public_url(category, filename)
    # Yerel static zaten varsa (seed) onu bozma — cache kopyası
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        if len(data) < min_bytes:
            return public_url(category, filename) if os.path.isfile(dest) else None
        tmp = dest + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
        return public_url(category, filename)
    except Exception:
        if os.path.isfile(dest) and os.path.getsize(dest) >= min_bytes:
            return public_url(category, filename)
        return None


def touch_local_static(rel_path: str) -> None:
    """Mevcut /static/... dosyasının mtime'ını güncellemez — sadece varlık kontrolü."""
    if not rel_path.startswith("/static/"):
        return
    full = os.path.join(_DIR, rel_path.lstrip("/"))
    if os.path.isfile(full):
        return
