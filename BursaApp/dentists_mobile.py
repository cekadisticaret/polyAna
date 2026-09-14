"""Mobil diş hekimleri listesi — web /dis-hekimleri ile aynı birleşik kaynak."""
from __future__ import annotations

from catalog import ILCELER, place_public, query_places

DENTIST_BANDS = ("Devlet", "Özel", "Klinik")


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


def _ilce_groups(places: list[dict]) -> list[dict]:
    by: dict[str, list] = {}
    for p in places:
        by.setdefault(p.get("ilce") or "Diğer", []).append(_decorate_row(p))
    groups = []
    for ad in ILCELER:
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


def build_dentists_payload(
    db,
    *,
    ilce: str = "",
    band: str = "",
) -> dict:
    ilce = (ilce or "").strip()
    band = (band or "").strip()

    clinics, _ = query_places(db, category="dentist", ilce=ilce or None, order="rating", limit=500)
    docs_dis, _ = query_places(db, category="doctor", price_band="Diş", ilce=ilce or None, limit=200)
    docs_dh, _ = query_places(
        db, category="doctor", price_band="Diş hekimi", ilce=ilce or None, limit=200
    )
    seen_doc: set[int] = set()
    docs = []
    for p in docs_dis + docs_dh:
        if p.id in seen_doc:
            continue
        seen_doc.add(p.id)
        docs.append(p)

    places = [place_public(p) for p in clinics] + [place_public(p) for p in docs]
    if band:
        places = [p for p in places if (p.get("price_band") or "") == band]

    places.sort(
        key=lambda p: (
            0 if p.get("featured") else 1,
            0 if (p.get("price_band") or "") == "Devlet" else 1,
            -(float(p["rating"]) if p.get("rating") is not None else -1.0),
            p.get("title") or "",
        )
    )

    _attach_hospital_titles(db, places)
    groups = _ilce_groups(places)
    total = len(places)
    devlet_n = sum(1 for p in places if (p.get("price_band") or "") == "Devlet")

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
        "devlet_count": devlet_n,
        "hero_img": hero_img,
        "page_sub": "ADSM, özel klinik ve hastane diş hekimleri · MHRS / randevu",
        "hero_note": "Devlet ADSM · MHRS / 182 · Özel klinikler randevu ile",
        "districts": list(ILCELER),
        "bands": [{"key": b, "label": b} for b in DENTIST_BANDS],
        "filters": {"ilce": ilce, "band": band},
    }
