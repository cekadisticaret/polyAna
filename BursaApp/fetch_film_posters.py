#!/usr/bin/env python3
"""Film kapaklarını gerçek afiş yap (Wikipedia / Commons). Salon görsellerine dokunmaz."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from models import Place, SessionLocal, init_db

UA = "BursaApp/1.0 (https://bursaapp.com; city guide)"

# slug → Wikipedia sayfa adayları (EN / TR)
FILM_WIKI = {
    "film-ataturk-zaferin-safagi": [
        "Atatürk:_Zaferin_Şafağı",
        "Ataturk:_Dawn_of_Victory",
    ],
    "film-the-odyssey": [
        "The_Odyssey_(2026_film)",
        "The_Odyssey_(film)",
    ],
    "film-orumbcek-adam": [
        "Spider-Man:_Brand_New_Day",
        "Örümcek-Adam:_Yepyeni_Bir_Gün",
    ],
    "film-minyonlar-canavarlar": [
        "Minions_and_Monsters",
        "Despicable_Me_4",
        "Minions_(film)",
    ],
    "film-coyote-acme": [
        "Coyote_vs._Acme",
        "Coyote_vs_Acme",
    ],
    "film-tadin-sihirli-lambasi": [
        "Tad_the_Lost_Explorer_and_the_Emerald_Scarab",
        "Tad:_The_Lost_Explorer",
        "Las_aventuras_de_Tadeo_Jones",
    ],
    "film-ruhlar-bolgesi": [
        "Insidious:_The_Further",
        "Insidious:_The_Red_Door",
        "Insidious_(film)",
        "Ruhlar_Bölgesi:_Aramızdalar",
    ],
    "film-sadece-bir-gece": [
        "Just_One_Night",
        "One_Night_(film)",
        "Sadece_Bir_Gece",
    ],
    "film-kopek-yildizlar": [
        "The_Dog_and_the_Stars",
        "Dog_Man_(film)",
        "Köpek_ve_Yıldızlar",
    ],
    "film-gercek-kayitlar-7": [
        "V/H/S/85",
        "V/H/S/94",
        "Found_footage_(film_technique)",
    ],
    "film-cebran": [
        "The_Prophet_(2014_film)",
        "Kahlil_Gibran's_The_Prophet",
        "Cebran",
    ],
}


def curl_json(url: str) -> dict | None:
    try:
        r = subprocess.run(
            ["curl", "-fsSL", "-A", UA, "--max-time", "25", url],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0 or not r.stdout:
            return None
        return json.loads(r.stdout)
    except Exception:
        return None


def curl_file(url: str, dest: str) -> bool:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    r = subprocess.run(
        [
            "curl",
            "-fsSL",
            "-A",
            UA,
            "-e",
            "https://en.wikipedia.org/",
            "--max-time",
            "45",
            "-o",
            dest,
            url,
        ],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 8000


def wiki_summary(lang: str, title: str) -> dict | None:
    t = urllib.parse.quote(title.replace(" ", "_"))
    return curl_json(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{t}")


def wiki_search(lang: str, q: str) -> list[str]:
    qq = urllib.parse.quote(q)
    data = curl_json(
        f"https://{lang}.wikipedia.org/w/api.php?action=opensearch&search={qq}&limit=5&namespace=0&format=json"
    )
    if not data or len(data) < 2:
        return []
    return list(data[1] or [])


def poster_from_summary(data: dict) -> str:
    if not data:
        return ""
    # original / thumbnail
    for key in ("originalimage", "thumbnail"):
        img = data.get(key) or {}
        src = img.get("source") or ""
        if src and ("poster" in src.lower() or src.endswith((".jpg", ".jpeg", ".png", ".webp"))):
            # strip query, bump width
            src = src.split("?")[0]
            src = re.sub(r"/\d+px-", "/800px-", src)
            return src
    return ""


def find_poster(slug: str, title: str) -> str:
    # 1) fixed candidates
    for cand in FILM_WIKI.get(slug, []):
        for lang in ("en", "tr"):
            data = wiki_summary(lang, cand)
            if not data or data.get("type") == "disambiguation":
                continue
            url = poster_from_summary(data)
            if url and "poster" in url.lower():
                return url
            if url and data.get("type") == "standard":
                # film page often has poster even without "poster" in filename
                desc = (data.get("description") or "").lower()
                if "film" in desc or "movie" in desc or "sinema" in desc:
                    return url
    # 2) search by title
    for lang in ("en", "tr"):
        for hit in wiki_search(lang, title):
            data = wiki_summary(lang, hit.replace(" ", "_"))
            url = poster_from_summary(data)
            if url and ("poster" in url.lower() or "film" in (data.get("description") or "").lower()):
                return url
    # 3) search "Title film poster"
    for lang in ("en", "tr"):
        for hit in wiki_search(lang, f"{title} film"):
            data = wiki_summary(lang, hit.replace(" ", "_"))
            url = poster_from_summary(data)
            if url:
                return url
    return ""


def to_jpeg(src_path: str, dest: str) -> bool:
    try:
        from PIL import Image

        im = Image.open(src_path).convert("RGB")
        # portrait afiş tercihi
        w, h = im.size
        if w > h:
            # yataysa ortala kırp 2:3
            target_w = int(h * 2 / 3)
            left = max(0, (w - target_w) // 2)
            im = im.crop((left, 0, left + target_w, h))
        im = im.resize((600, 900))
        im.save(dest, "JPEG", quality=90)
        return True
    except Exception as e:
        print("pil", e)
        return False


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        films = (
            db.query(Place)
            .filter(Place.category == "cinema", Place.status == "approved", Place.slug.like("film-%"))
            .all()
        )
        ok = 0
        for p in films:
            print("—", p.slug, p.title)
            url = find_poster(p.slug, p.title)
            if not url:
                print("  no poster")
                continue
            # Wikimedia Special:FilePath for full-ish
            if "upload.wikimedia.org" in url and "/thumb/" in url:
                # leave as is; often enough
                pass
            tmp = os.path.join(_DIR, "static", "cinema", f"_{p.slug}.img")
            dest = os.path.join(_DIR, "static", "cinema", f"{p.slug}.jpg")
            if not curl_file(url, tmp):
                print("  download fail", url[:80])
                continue
            if not to_jpeg(tmp, dest):
                os.replace(tmp, dest)
            else:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
            p.img_url = f"/static/cinema/{p.slug}.jpg"
            ok += 1
            print("  OK", os.path.getsize(dest), url[:70])
        db.commit()
        print(f"done {ok}/{len(films)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
