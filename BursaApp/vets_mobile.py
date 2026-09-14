"""Mobil veteriner listesi — web /veterinerler ile aynı gruplama/filtre."""
from __future__ import annotations

from catalog import ILCELER, place_public, query_places, subcategory_label
from discover import FALLBACK_LAT, FALLBACK_LNG, nearby

VET_SUBS = (
    ("klinik", "Klinik"),
    ("poliklinik", "Poliklinik"),
    ("hastane", "Hayvan hastanesi"),
)


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
    out["subcategory_label"] = out.get("subcategory_label") or subcategory_label(sub) or (out.get("price_band") or "")
    dm = out.get("distance_m")
    if dm is not None:
        dm = int(dm)
        out["distance_label"] = f"{dm} m" if dm < 1000 else f"{dm / 1000:.1f} km"
    else:
        out["distance_label"] = ""
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


def build_vets_payload(
    db,
    *,
    tab: str = "hepsi",
    ilce: str = "",
    sub: str = "",
    lat: float | None = None,
    lng: float | None = None,
) -> dict:
    tab = (tab or "hepsi").strip().lower()
    if tab not in ("hepsi", "yakin"):
        tab = "hepsi"
    ilce = (ilce or "").strip()
    sub = (sub or "").strip()
    used_fallback = False

    if lat is None or lng is None:
        lat, lng = FALLBACK_LAT, FALLBACK_LNG
        used_fallback = True

    if tab == "yakin":
        data = nearby(db, lat, lng, category="vet", unlimited=True)
        places = [_decorate_row(p) for p in data["places"]]
        groups = [{"label": "Yakınında", "places": places}] if places else []
        page_sub = (
            f"Konumuna göre · {lat:.4f}, {lng:.4f}"
            if not used_fallback
            else "Konum alınamadı — Osmangazi merkez"
        )
    else:
        rows, total = query_places(
            db,
            category="vet",
            ilce=ilce or None,
            subcategory=sub or None,
            order="rating",
            limit=500,
        )
        places = [place_public(p) for p in rows]
        groups = _ilce_groups(places)
        total = len(places)
        page_sub = "Oda kayıtlı klinik ve hayvan hastanesi — randevu siteden yok"

    flat = [p for g in groups for p in g["places"]]
    total = len(flat)
    ozel_n = sum(1 for p in flat if (p.get("price_band") or "") == "Hastane")

    hero_img = ""
    for p in flat:
        img = (p.get("img_url") or "").strip()
        if img:
            hero_img = img
            break

    return {
        "tab": tab,
        "groups": groups,
        "total": total,
        "group_count": len(groups),
        "hospital_count": ozel_n,
        "hero_img": hero_img,
        "page_sub": page_sub,
        "used_fallback": used_fallback,
        "lat": lat,
        "lng": lng,
        "districts": list(ILCELER),
        "subs": [{"key": k, "label": lab} for k, lab in VET_SUBS],
        "filters": {"ilce": ilce, "sub": sub, "tab": tab},
        "hero_note": "Kaynak Bursa Veteriner Hekimler Odası kayıtlı işletmeler",
    }
