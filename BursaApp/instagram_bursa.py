"""Ana sayfa hero — Instagram #bursa slaytları (cache JSON)."""
from __future__ import annotations

import json
import os
import re

_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(_DIR, "data", "instagram_bursa.json")

# Yerel statik yedek (fetch yoksa)
DEFAULT_HERO_SLIDES: list[tuple[str, str]] = [
    ("visit/golyazi.jpg", "Gölyazı · Uluabat"),
    ("visit/ulu-cami.jpg", "Ulu Cami"),
    ("visit/cumalikizik.jpg", "Cumalıkızık"),
    ("visit/tophane.jpg", "Tophane · Hisar"),
    ("visit/yesil-turbe.jpg", "Yeşil Türbe"),
    ("visit/inkaya-cinari.jpg", "İnkaya Çınarı"),
    ("visit/koza-han.jpg", "Koza Han"),
    ("visit/suuctu.jpg", "Suuçtu Şelalesi"),
    ("visit/tirilye.jpg", "Tirilye / Zeytinbağı"),
    ("visit/panorama-1326.jpg", "Panorama 1326"),
    ("visit/kale-sokak.jpg", "Kale Sokak"),
    ("visit/muradiye.jpg", "Muradiye"),
]


def load_hero_slides(*, limit: int = 12) -> list[dict]:
    """Şablona uygun slayt listesi: img (url), title, permalink?, source."""
    out: list[dict] = []
    if os.path.isfile(JSON_PATH):
        try:
            raw = json.loads(open(JSON_PATH, encoding="utf-8").read())
            for row in raw.get("slides") or []:
                img = (row.get("img") or row.get("url") or "").strip()
                title = (row.get("title") or row.get("caption") or "Bursa").strip()[:80]
                if not img:
                    continue
                out.append(
                    {
                        "img": img,
                        "title": title,
                        "permalink": (row.get("permalink") or "").strip(),
                        "source": row.get("source") or "instagram",
                    }
                )
                if len(out) >= limit:
                    break
        except (OSError, json.JSONDecodeError):
            pass
    if out:
        return out
    return [
        {"img": f"/static/{src}", "title": title, "permalink": "", "source": "static"}
        for src, title in DEFAULT_HERO_SLIDES[:limit]
    ]
