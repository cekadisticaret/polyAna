"""Mobil doktor listesi — web /doktorlar ile aynı branş gruplama."""
from __future__ import annotations

from catalog import DOCTOR_SPECS, ILCELER, place_public, query_places


def _health_initial(title: str) -> str:
    for ch in (title or "").strip():
        if ch.isalpha():
            return ch.upper()
    return "?"


def _rx_hours_short(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    if len(t) <= 28:
        return t
    return t[:25].rstrip() + "…"


def _decorate_row(p: dict) -> dict:
    out = dict(p)
    out["initial"] = _health_initial(out.get("title") or "")
    out["hours_short"] = _rx_hours_short(out.get("hours_text") or "")
    if out.get("rating") is not None:
        try:
            out["rating_label"] = f"{float(out['rating']):.1f}"
        except (TypeError, ValueError):
            out["rating_label"] = ""
    else:
        out["rating_label"] = ""
    extra = out.get("extra") or {}
    if isinstance(extra, dict):
        out["mhrs_url"] = (extra.get("mhrs_url") or "").strip()
    else:
        out["mhrs_url"] = ""
    return out


def _spec_groups(places: list[dict]) -> list[dict]:
    by: dict[str, list] = {}
    for p in places:
        by.setdefault(p.get("price_band") or "Diğer", []).append(_decorate_row(p))
    groups = []
    for ad in DOCTOR_SPECS:
        if ad in by:
            groups.append({"label": ad, "places": by.pop(ad)})
    for ad, plist in by.items():
        groups.append({"label": ad, "places": plist})
    return groups


def _attach_hospital_titles(db, places: list[dict]) -> None:
    slugs = {p.get("hospital_slug") or p.get("venue_name") for p in places}
    slugs.discard("")
    slugs.discard(None)
    if not slugs:
        return
    from models import Place

    hs = {h.slug: h for h in db.query(Place).filter(Place.slug.in_(slugs)).all()}
    for p in places:
        h = hs.get(p.get("hospital_slug") or p.get("venue_name") or "")
        if h:
            p["hospital_title"] = h.title
            p["hospital_slug"] = h.slug


def build_doctors_payload(
    db,
    *,
    ilce: str = "",
    spec: str = "",
) -> dict:
    ilce = (ilce or "").strip()
    spec = (spec or "").strip()

    rows, total = query_places(
        db,
        category="doctor",
        ilce=ilce or None,
        price_band=spec or None,
        order="rating",
        limit=500,
    )
    places = [place_public(p) for p in rows]
    places.sort(
        key=lambda p: (
            0 if p.get("featured") else 1,
            -(float(p["rating"]) if p.get("rating") is not None else -1.0),
            p.get("title") or "",
        )
    )

    _attach_hospital_titles(db, places)
    groups = _spec_groups(places)
    total = len(places)
    brans_n = len({p.get("price_band") for p in places if p.get("price_band")})

    hero_img = ""
    for p in places:
        img = (p.get("img_url") or "").strip()
        if img:
            hero_img = img
            break

    return {
        "groups": groups,
        "total": total,
        "group_count": len(groups),
        "spec_count": brans_n,
        "hero_img": hero_img,
        "page_sub": "Branşa göre hekim — hastane sayfasına bağlı · randevu / tıbbi tavsiye yok",
        "hero_note": "Resmi kadro bağlantıları · MHRS / 182",
        "districts": list(ILCELER),
        "specs": [{"key": s, "label": s} for s in DOCTOR_SPECS],
        "filters": {"ilce": ilce, "spec": spec},
    }
