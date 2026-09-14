"""Mobil gezilecek yerler — web /gezilecek filtre/sıralama."""
from __future__ import annotations

from catalog import (
    ILCELER,
    VISIT_FEE,
    VISIT_KIND,
    VISIT_TAG,
    place_public,
    query_places,
    visit_fee_tier,
    visit_matches,
)


def build_visit_payload(
    db,
    *,
    q: str = "",
    ilce: str = "",
    sub: str = "",
    sort: str = "featured",
    kinds: list[str] | None = None,
    fees: list[str] | None = None,
    tags: list[str] | None = None,
    page: int = 1,
    per_page: int = 40,
) -> dict:
    q = (q or "").strip()
    ilce = (ilce or "").strip()
    sub = (sub or "").strip()
    sort = (sort or "featured").strip()
    if sort not in ("featured", "rating", "name"):
        sort = "featured"
    kinds = [k for k in (kinds or []) if k]
    fees = [f for f in (fees or []) if f]
    tags = [t for t in (tags or []) if t]
    page = max(1, page)

    rows, _ = query_places(
        db,
        category="visit",
        ilce=ilce or None,
        q=q or None,
        subcategory=sub or None,
        order="rating",
        limit=2500,
    )
    places = [place_public(p) for p in rows]
    if sub:
        places = [p for p in places if (p.get("subcategory") or "") == sub]

    filtered = [
        p
        for p in places
        if visit_matches(p, kinds=kinds or None, fees=fees or None, tags=tags or None)
    ]

    if sort == "name":
        filtered.sort(key=lambda p: (p.get("title") or "").lower())
    elif sort == "rating":
        filtered.sort(
            key=lambda p: (
                -(float(p["rating"]) if p.get("rating") is not None else -1),
                p.get("title") or "",
            )
        )
    else:
        filtered.sort(
            key=lambda p: (
                0 if p.get("featured") else 1,
                0 if not str(p.get("slug") or "").startswith("osm-visit-") else 1,
                -(float(p["rating"]) if p.get("rating") is not None else -1),
                p.get("title") or "",
            )
        )

    total = len(filtered)
    pages = max(1, (total + per_page - 1) // per_page)
    if page > pages:
        page = pages
    start = (page - 1) * per_page
    page_rows = filtered[start : start + per_page]

    for i, p in enumerate(page_rows, start=start + 1):
        p["rank"] = i
        p["fee_label"] = "Ücretli" if visit_fee_tier(p) == "ucretli" else "Ücretsiz"
        ex = p.get("extra") or {}
        gals = ex.get("gallery") if isinstance(ex.get("gallery"), list) else []
        gallery = [p.get("img_url")] + [g for g in gals if g and g != p.get("img_url")]
        p["gallery"] = [g for g in gallery if g][:6]

    hero = []
    if page == 1 and not q:
        for p in filtered[:5]:
            if p.get("img_url"):
                hero.append(p)
                if len(hero) >= 3:
                    break

    featured = [p for p in filtered if p.get("featured")][:8]
    if len(featured) < 4:
        featured = filtered[:8]

    return {
        "places": page_rows,
        "hero": hero,
        "featured": featured,
        "total": total,
        "page": page,
        "pages": pages,
        "districts": list(ILCELER),
        "filters": {
            "q": q,
            "ilce": ilce,
            "sub": sub,
            "sort": sort,
            "kinds": kinds,
            "fees": fees,
            "tags": tags,
        },
        "kinds": [{"key": k, "label": lab} for k, lab, _ in VISIT_KIND],
        "fees": [{"key": k, "label": lab} for k, lab in VISIT_FEE],
        "tags": [{"key": k, "label": lab} for k, lab in VISIT_TAG],
    }
