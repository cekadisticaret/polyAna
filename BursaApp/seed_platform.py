#!/usr/bin/env python3
"""Kampanya, kupon, editoryal, yemek fiyat tahmini seed."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import tags_dump
from models import Campaign, Coupon, Editorial, Place, SessionLocal, init_db


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        # yemek tahmini maliyet
        for p in db.query(Place).filter(Place.category == "food", Place.est_meal_tl == 0).all():
            sub = (p.subcategory or "").lower()
            p.est_meal_tl = {
                "iskender": 450,
                "kebap": 400,
                "doner": 280,
                "inegol-kofte": 280,
                "cafe": 150,
                "kahvalti": 320,
                "tatli": 120,
                "pastane": 100,
                "burger": 250,
                "pizza": 260,
            }.get(sub, 300)

        # kampanyalar
        if db.query(Campaign).count() == 0:
            foods = db.query(Place).filter(Place.status == "approved", Place.category == "food").limit(5).all()
            now = datetime.utcnow()
            samples = [
                ("%20 indirim", "Öğle menüsünde %20"),
                ("2 Kahve + Tatlı 250 TL", "Hafta içi geçerli"),
                ("Hafta içi özel menü", "12:00–15:00"),
            ]
            for i, p in enumerate(foods[:3]):
                badge, body = samples[i]
                db.add(
                    Campaign(
                        place_id=p.id,
                        title=f"{p.title} kampanyası",
                        body=body,
                        badge=badge,
                        status="approved",
                        starts_at=now - timedelta(days=1),
                        ends_at=now + timedelta(days=30),
                    )
                )

        if db.query(Coupon).filter(Coupon.code == "BURSAAPP20").first() is None:
            place = db.query(Place).filter(Place.status == "approved", Place.category == "food").first()
            db.add(
                Coupon(
                    code="BURSAAPP20",
                    place_id=place.id if place else None,
                    title="%20 BursaApp indirimi",
                    discount_pct=20,
                    max_uses=500,
                    status="active",
                    expires_at=datetime.utcnow() + timedelta(days=90),
                )
            )

        editorials = [
            ("nilufer-en-iyi-kahvalti", "Nilüfer'in en iyi kahvaltı mekanları", "kahvalti", "Nilüfer"),
            ("bursa-en-iyi-burger", "Bursa'nın en iyi burgerleri", "burger", None),
            ("bursa-ciftler", "Bursa'da çiftlerin gidebileceği yerler", "cafe", None),
            ("bursa-manzarali-cafe", "Bursa'nın en iyi manzaralı cafeleri", "cafe", None),
        ]
        for slug, title, sub, ilce in editorials:
            if db.query(Editorial).filter(Editorial.slug == slug).first():
                continue
            q = db.query(Place).filter(Place.status == "approved", Place.category == "food")
            if sub:
                q = q.filter(Place.subcategory == sub)
            if ilce:
                q = q.filter(Place.ilce == ilce)
            rows = q.limit(8).all()
            if not rows and sub:
                rows = db.query(Place).filter(Place.status == "approved", Place.category == "food").limit(6).all()
            db.add(
                Editorial(
                    slug=slug,
                    title=title,
                    blurb="BursaApp editöryel seçkisi — puan + kalite.",
                    place_slugs=json.dumps([p.slug for p in rows], ensure_ascii=False),
                    status="approved",
                )
            )

        db.commit()
        print("platform seed ok", "campaigns", db.query(Campaign).count(), "coupons", db.query(Coupon).count())
    finally:
        db.close()


if __name__ == "__main__":
    main()
