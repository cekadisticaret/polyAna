#!/usr/bin/env python3
"""Her gece SEO / içerik denetimi — sonuçlar admin /admin/seo panelinde.

Cron: `bursaapp_nightly.py` içinde (02:30 İST). Tek başına:
  30 23 * * * cd /root/aiProject && python3 BursaApp/seo_nightly.py >> /tmp/bursaapp_seo_nightly.log 2>&1
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from models import Campaign, Place, SeoAudit, SessionLocal, init_db


def audit(db) -> tuple[str, list[dict]]:
    issues: list[dict] = []
    places = db.query(Place).filter(Place.status == "approved").all()
    by_title: dict[str, list[tuple[str, str]]] = {}
    for p in places:
        title = (p.title or "").strip().lower()
        by_title.setdefault(title, []).append((p.slug, p.category or ""))
        if not (p.img_url or "").strip():
            issues.append({"code": "missing_img", "slug": p.slug, "title": p.title, "category": p.category})
        if not (p.blurb or "").strip() or len(p.blurb.strip()) < 20:
            issues.append({"code": "weak_blurb", "slug": p.slug, "title": p.title, "category": p.category})
        if not (p.ilce or "").strip():
            issues.append({"code": "missing_ilce", "slug": p.slug, "title": p.title, "category": p.category})
        # yerel dosya kırık mı?
        img = p.img_url or ""
        if img.startswith("/static/"):
            path = os.path.join(_DIR, img.lstrip("/"))
            if not os.path.isfile(path):
                issues.append({"code": "broken_img_file", "slug": p.slug, "img": img})

    # Aynı başlık: etkinlik/konser tarih kopyaları ve visit↔family çiftleri sayılmaz
    _EVENTISH = frozenset({"concert", "theater", "cinema", "event", "org"})
    _PLACE_PAIR = frozenset({"visit", "family", "camp"})
    for title, rows in by_title.items():
        if not title or len(rows) < 2:
            continue
        cats = {c for _, c in rows}
        if cats <= _EVENTISH:
            continue
        if cats <= _PLACE_PAIR:
            continue
        issues.append(
            {
                "code": "duplicate_title",
                "title": title,
                "slugs": [s for s, _ in rows],
                "categories": sorted(cats),
            }
        )

    now = datetime.utcnow()
    for c in db.query(Campaign).filter(Campaign.status == "approved").limit(200).all():
        if c.ends_at and c.ends_at < now:
            issues.append(
                {
                    "code": "campaign_expired_still_approved",
                    "id": c.id,
                    "title": c.title,
                    "ends_at": c.ends_at.isoformat(),
                }
            )

    summary = (
        f"{len(issues)} bulgu · {len(places)} yayınlı yer · "
        f"img eksik {sum(1 for i in issues if i['code']=='missing_img')} · "
        f"zayıf metin {sum(1 for i in issues if i['code']=='weak_blurb')} · "
        f"ilçe eksik {sum(1 for i in issues if i['code']=='missing_ilce')} · "
        f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
    )
    return summary, issues


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        summary, issues = audit(db)
        row = SeoAudit(summary=summary, issues_json=json.dumps(issues, ensure_ascii=False))
        db.add(row)
        db.commit()
        print(summary)
        print(f"seo_audit id={row.id} issues={len(issues)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
