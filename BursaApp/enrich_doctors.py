#!/usr/bin/env python3
"""Doktor foto + özgeçmiş: Acıbadem resmi kadro (LinkedIn scrape yok).

Kaynak: acibadem.com.tr doktor listesi (profil görseli + about).
Çalıştır: python3 enrich_doctors.py
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import unicodedata
import urllib.request
from urllib.parse import quote

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from models import Place, SessionLocal, init_db, merge_place_extra, place_extra

CDN = "https://yenicms.acibadem.com.tr"
SITE = "https://www.acibadem.com.tr"
UA = "Mozilla/5.0 (compatible; BursaApp/1.0; +https://bursaapp.com)"
DATA = os.path.join(_DIR, "data", "acibadem_bursa_doctors.json")


def norm(s: str) -> str:
    s = (s or "").upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("İ", "I").replace("I", "I")
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    # unvanları at
    for t in ("PROF DR", "PROF", "DOC DR", "DOC", "DR", "OP DR", "UZM DR", "UZM"):
        s = re.sub(rf"\b{t}\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    t = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    t = re.sub(r"(?is)<style.*?>.*?</style>", " ", t)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</p>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def fetch_bytes(url: str) -> bytes | None:
    """curl kullan — sunucu urllib tünelini engelliyor."""
    import subprocess
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path = tmp.name
        r = subprocess.run(
            [
                "curl",
                "-fsSL",
                "-A",
                UA,
                "-e",
                "https://www.acibadem.com.tr/",
                "-H",
                "Accept: image/avif,image/webp,image/*,*/*;q=0.8",
                "--max-time",
                "45",
                "-o",
                path,
                url,
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            print("fetch fail", url[:80], r.stderr[:120] if r.stderr else r.returncode)
            try:
                os.unlink(path)
            except Exception:
                pass
            return None
        with open(path, "rb") as f:
            data = f.read()
        os.unlink(path)
        return data if len(data) > 3000 else None
    except Exception as e:
        print("fetch fail", url[:80], e)
        return None


def abs_img(path: str) -> str:
    if not path:
        return ""
    if path.startswith("http"):
        return path
    return "https://yenicms.acibadem.com.tr" + (path if path.startswith("/") else "/" + path)


def load_aci() -> list[dict]:
    if not os.path.isfile(DATA):
        return []
    with open(DATA, encoding="utf-8") as f:
        rows = json.load(f)
    # normalize interests
    for r in rows:
        it = r.get("interests")
        if isinstance(it, list):
            r["interests"] = [
                (x.get("name") if isinstance(x, dict) else str(x)) for x in it if x
            ]
        elif isinstance(it, str) and it:
            r["interests"] = [it]
        else:
            r["interests"] = []
    return rows


def match_score(place_title: str, aci: dict) -> int:
    pn = norm(place_title)
    an = norm(aci.get("name") or "")
    last = norm(aci.get("last") or "")
    first = norm(aci.get("first") or "")
    if not pn or not an:
        return 0
    if pn == an:
        return 100
    if last and last in pn and first and first.split()[0] in pn:
        return 90
    if last and last in pn:
        # soyad eşleşmesi
        return 70
    # token overlap
    pt, at = set(pn.split()), set(an.split())
    if not pt or not at:
        return 0
    inter = pt & at
    return int(100 * len(inter) / max(len(pt), len(at)))


def linkedin_search(name: str) -> str:
    q = quote(f"{name} Bursa doktor OR hekim OR Acıbadem")
    return f"https://www.linkedin.com/search/results/people/?keywords={q}"


def specialty_areas(band: str) -> list[str]:
    b = (band or "").lower()
    table = {
        "üroloji": ["Üroloji muayene", "Böbrek taşı", "Prostat", "Androloji"],
        "kalp": ["Kardiyoloji muayene", "EKG / efor", "Koroner hastalık"],
        "onkoloji": ["Medikal onkoloji", "Kemoterapi planı", "Takip"],
        "psikiyatri": ["Psikiyatrik değerlendirme", "Anksiyete / depresyon", "İlaç tedavisi"],
        "beyin": ["Beyin cerrahisi", "Omurga", "Travma"],
        "kbb": ["Kulak burun boğaz", "Sinüzit", "Ses / işitme"],
        "göz": ["Göz muayene", "Katarakt", "Retina"],
        "genel cerrahi": ["Genel cerrahi", "Laparoskopi", "Meme / tiroid"],
        "ortopedi": ["Ortopedi", "Spor yaralanması", "Protez"],
        "kadın": ["Kadın doğum", "Gebelik takibi", "Jinekoloji"],
        "çocuk": ["Çocuk sağlığı", "Aşı / takip"],
        "nöroloji": ["Nöroloji", "Baş ağrısı", "Epilepsi"],
        "dermatoloji": ["Cilt hastalıkları", "Estetik dermatoloji"],
    }
    for k, v in table.items():
        if k in b:
            return v
    return [f"{band} uzmanlık alanı", "Poliklinik muayene", "Tedavi planı"] if band else []


def enrich() -> None:
    init_db()
    aci_rows = load_aci()
    if not aci_rows:
        print("Acıbadem veri yok — önce JSON üret")
        return
    db = SessionLocal()
    try:
        docs = db.query(Place).filter(Place.category == "doctor", Place.status == "approved").all()
        used = set()
        matched = 0
        photos = 0
        for p in docs:
            # Acıbadem kadrosu yalnız acibadem venue
            is_aci = (p.venue_name or "") == "acibadem-bursa" or (p.slug or "").startswith("aci-")
            best, score = None, 0
            if is_aci:
                for a in aci_rows:
                    if a.get("code") in used:
                        continue
                    sc = match_score(p.title, a)
                    if sc > score:
                        best, score = a, sc
            if not best or score < 85:
                # yine de alan doldur
                ex = place_extra(p)
                areas = specialty_areas(p.price_band or "")
                if areas and not ex.get("services"):
                    merge_place_extra(p, {"services": areas})
                if not ex.get("linkedin_url"):
                    merge_place_extra(p, {"linkedin_url": linkedin_search(p.title)})
                continue

            used.add(best.get("code") or best.get("name"))
            matched += 1
            about = strip_html(best.get("about") or "")
            interests = best.get("interests") or []
            if isinstance(interests, str):
                interests = [interests]
            units = best.get("units") or []
            path = best.get("profile_path") or ""
            profile_url = (SITE + path) if path.startswith("/") else (path or p.web or "")
            img_url = abs_img(best.get("profil_image") or "")

            local = os.path.join(_DIR, "static", "doctor", f"{p.slug}.jpg")
            if img_url:
                data = fetch_bytes(img_url)
                if data and len(data) > 3000:
                    # png/webp → jpg kaydet (uzantı jpg ama içerik orijinal olabilir; tarayıcı OK)
                    # gerçek jpg'ye çevir
                    try:
                        from PIL import Image
                        from io import BytesIO

                        im = Image.open(BytesIO(data)).convert("RGB")
                        # banner ise ortala kırp portrait
                        w, h = im.size
                        if w > h * 1.2:
                            side = h
                            left = (w - side) // 2
                            im = im.crop((left, 0, left + side, h))
                        im = im.resize((800, 800))
                        im.save(local, "JPEG", quality=88)
                    except Exception:
                        with open(local, "wb") as f:
                            f.write(data)
                    p.img_url = f"/static/doctor/{p.slug}.jpg"
                    photos += 1

            if about:
                p.body = about[:4000]
                # blurb: ilk cümle
                first = about.split(".")[0].strip()
                if len(first) >= 20:
                    p.blurb = (first[:280] + ".") if not first.endswith(".") else first[:281]
            if best.get("email"):
                # email'i public yazma — sadece iletişim notu
                pass
            years = best.get("experience_years")
            merge_place_extra(
                p,
                {
                    "specialty_detail": ", ".join(units) if units else (p.price_band or ""),
                    "services": interests[:12] or specialty_areas(p.price_band or ""),
                    "experience_years": str(years) if years not in (None, "") else "",
                    "profile_url": profile_url,
                    "linkedin_url": linkedin_search(
                        f"{best.get('first','')} {best.get('last','')}".strip() or p.title
                    ),
                    "source": "acibadem",
                    "fee_note": "Randevu ve ücret için Acıbadem / MHRS. BursaApp randevu satmaz.",
                },
            )
            if profile_url:
                p.web = profile_url
            print(f"OK {p.slug} ← {best.get('name')} score={score} photo={'y' if img_url else 'n'}")

        db.commit()
        print(f"matched={matched}/{len(docs)} photos={photos}")
    finally:
        db.close()


if __name__ == "__main__":
    # interests fix in saved json units were names already
    enrich()
