"""Mobil nöbetçi eczane listesi — web /nobetci-eczaneler ile aynı gruplama/konum."""
from __future__ import annotations

import json
import os
import re

from catalog import ILCELER
from discover import haversine_m

_DIR = os.path.dirname(os.path.abspath(__file__))
_RX_MONTHS = "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split()


def _load_feed() -> dict:
    path = os.path.join(_DIR, "data", "nobetci_eczaneler.json")
    if not os.path.isfile(path):
        return {"ok": False, "pharmacies": [], "total": 0, "duty_date": "", "attribution": ""}
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return {"ok": False, "pharmacies": [], "total": 0, "duty_date": "", "attribution": ""}


def _rx_hours_short(text: str) -> str:
    times = re.findall(r"(\d{1,2}:\d{2})", text or "")
    if len(times) >= 2:
        return f"{times[0]} – {times[-1]}"
    t = (text or "").strip()
    if len(t) <= 28:
        return t
    return t[:25].rstrip() + "…"


def _rx_duty_label(feed: dict) -> str:
    raw = (feed.get("duty_date") or "").strip()[:10]
    if not raw:
        return ""
    try:
        from datetime import datetime as dt

        d = dt.strptime(raw, "%Y-%m-%d")
        return f"{d.day} {_RX_MONTHS[d.month - 1]} {d.year}"
    except Exception:
        return raw


def _decorate_rx(p: dict) -> dict:
    out = dict(p)
    name = (out.get("name") or "Eczane").strip()
    out["hours_short"] = _rx_hours_short(out.get("hours_text") or "")
    out["initial"] = name[0].upper() if name else "?"
    return out


def _rx_distance_label(distance_m: int | None) -> str:
    if distance_m is None:
        return ""
    if distance_m < 1000:
        return f"{distance_m} m"
    return f"{distance_m / 1000:.1f} km"


def _with_distance(items: list[dict], lat: float, lng: float) -> list[dict]:
    out: list[dict] = []
    for p in items:
        d = dict(p)
        plat, plng = d.get("lat"), d.get("lng")
        if plat is None or plng is None:
            d["distance_m"] = None
            d["walk_min"] = None
            d["distance_label"] = ""
        else:
            dm = int(round(haversine_m(lat, lng, float(plat), float(plng))))
            d["distance_m"] = dm
            d["walk_min"] = max(1, int(round(dm / 80)))
            d["distance_label"] = _rx_distance_label(dm)
        out.append(_decorate_rx(d))
    out.sort(key=lambda x: (x.get("distance_m") is None, x.get("distance_m") or 10**9))
    return out


def build_pharmacy_payload(
    *,
    ilce: str = "",
    lat: float | None = None,
    lng: float | None = None,
) -> dict:
    ilce = (ilce or "").strip()
    has_geo = lat is not None and lng is not None

    feed = _load_feed()
    items = [_decorate_rx(p) for p in (feed.get("pharmacies") or [])]
    if ilce:
        items = [p for p in items if (p.get("district") or "") == ilce]
    if has_geo:
        items = _with_distance(items, lat, lng)
    else:
        for p in items:
            p.setdefault("distance_label", "")

    districts = sorted({p.get("district") for p in (feed.get("pharmacies") or []) if p.get("district")})

    if has_geo:
        groups = [{"label": "Sana en yakın", "places": items}] if items else []
    else:
        by: dict[str, list] = {}
        for p in items:
            by.setdefault(p.get("district") or "Diğer", []).append(p)
        groups = []
        for ad in list(ILCELER) + [k for k in by if k not in ILCELER]:
            if ad in by:
                groups.append({"label": ad, "places": by.pop(ad)})
        for ad, plist in by.items():
            groups.append({"label": ad, "places": plist})

    duty_label = _rx_duty_label(feed)
    fetched_at = (feed.get("fetched_at") or "").strip()
    attribution = (feed.get("attribution") or "").strip()

    return {
        "ok": feed.get("ok", True),
        "duty_date": feed.get("duty_date") or "",
        "duty_label": duty_label,
        "fetched_at": fetched_at,
        "attribution": attribution,
        "source": feed.get("source") or "",
        "total": feed.get("total") or len(feed.get("pharmacies") or []),
        "count": len(items),
        "group_count": len(groups),
        "groups": groups,
        "districts": districts,
        "has_geo": has_geo,
        "lat": lat,
        "lng": lng,
        "filters": {"ilce": ilce},
        "page_sub": (
            "Konumuna göre sıralı — mesafe ve yürüme süresi tahmini."
            if has_geo
            else f"{feed.get('total') or len(items)} eczane açık · konumunu kullanarak yakın olanları gör."
        ),
        "hero_note": (
            f"Kaynak {attribution} · {fetched_at[:16].replace('T', ' ')}"
            if attribution and fetched_at
            else (f"Kaynak {attribution}" if attribution else "")
        ),
    }


def build_pharmacy_detail(slug: str) -> dict:
    slug = (slug or "").strip()
    feed = _load_feed()
    place = next((p for p in (feed.get("pharmacies") or []) if p.get("slug") == slug), None)
    if not place:
        return {"ok": False, "place": None, "duty_label": _rx_duty_label(feed)}
    place = _decorate_rx(place)
    osm_embed = ""
    if place.get("lat") is not None and place.get("lng") is not None:
        lat = float(place["lat"])
        lng = float(place["lng"])
        osm_embed = (
            "https://www.openstreetmap.org/export/embed.html"
            f"?bbox={lng - 0.012:.6f},{lat - 0.008:.6f},{lng + 0.012:.6f},{lat + 0.008:.6f}"
            f"&layer=mapnik&marker={lat},{lng}"
        )
    return {
        "ok": True,
        "place": place,
        "duty_label": _rx_duty_label(feed),
        "attribution": feed.get("attribution") or "",
        "osm_embed": osm_embed,
    }
