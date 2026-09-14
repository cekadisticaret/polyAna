"""Mobil hastane listesi — web /hastaneler ile aynı ilçe gruplama/filtre."""
from __future__ import annotations

from catalog import ILCELER, place_public, query_places, subcategory_label

HOSPITAL_BANDS = ("Özel", "Devlet", "Üniversite", "Kampüs", "Göz", "Diş")


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
    sub = (out.get("subcategory") or "").strip()
    out["subcategory_label"] = out.get("subcategory_label") or subcategory_label(sub) or ""
    extra = out.get("extra") or {}
    if isinstance(extra, dict):
        out["mhrs_url"] = (extra.get("mhrs_url") or "").strip()
    else:
        out["mhrs_url"] = ""
    if not out["mhrs_url"] and (out.get("price_band") or "") == "Devlet":
        out["mhrs_url"] = "https://mhrs.gov.tr/vatandas/#/Randevu"
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


def build_hospitals_payload(
    db,
    *,
    ilce: str = "",
    band: str = "",
) -> dict:
    ilce = (ilce or "").strip()
    band = (band or "").strip()

    rows, _total = query_places(
        db,
        category="hospital",
        ilce=ilce or None,
        order="rating",
        limit=500,
    )
    places = [place_public(p) for p in rows]
    if band:
        places = [p for p in places if (p.get("price_band") or "") == band]

    places.sort(
        key=lambda p: (
            0 if p.get("featured") else 1,
            -(float(p["rating"]) if p.get("rating") is not None else -1.0),
            p.get("title") or "",
        )
    )

    groups = _ilce_groups(places)
    total = len(places)
    ozel_n = sum(1 for p in places if (p.get("price_band") or "") == "Özel")

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
        "private_count": ozel_n,
        "hero_img": hero_img,
        "page_sub": "Devlet, özel, üniversite — karttaki hekimler o hastaneye bağlı",
        "hero_note": "Randevu MHRS / 182 · Acil 112",
        "districts": list(ILCELER),
        "bands": [{"key": b, "label": b} for b in HOSPITAL_BANDS],
        "filters": {"ilce": ilce, "band": band},
    }
