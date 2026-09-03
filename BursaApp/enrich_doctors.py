#!/usr/bin/env python3
"""Doktor foto + özgeçmiş — hastane sitelerinden resmi kadro.

Kaynaklar: Acıbadem JSON · jimer.com.tr · gozvakfi.com (Nilüfer).
Medical Park sunucu IP'sine 403 veriyor — elle veya proxy gerekir.
Doruk kadrosu: önce `python3 doruk_doctors_fetch.py`, sonra bu betik.
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
DOCTORS_JSON = os.path.join(_DIR, "data", "doctors.json")
JIMER_LIST = "https://jimer.com.tr/tr/hekimler/jimer-hastanesi"
GOZ_NGM_LIST = "https://www.gozvakfi.com/hekimlerimiz/nilufer-goz-merkezi-bursa/"
KALPARITMI_HOME = "https://kalparitmi.com.tr/"
DORUK_JSON = os.path.join(_DIR, "data", "doruk_doctors.json")
DORUK_SITE = "https://doruktip.com/"


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


def _curl_to(path: str, url: str, *, referer: str = "", accept: str = "") -> bool:
    import subprocess

    cmd = ["curl", "-fsSL", "-A", UA, "--max-time", "45", "-o", path, url]
    if referer:
        cmd[6:6] = ["-e", referer]
    if accept:
        cmd[6:6] = ["-H", f"Accept: {accept}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("fetch fail", url[:80], r.stderr[:120] if r.stderr else r.returncode)
        return False
    return True


def fetch_html(url: str, referer: str = "") -> str:
    import subprocess
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path = tmp.name
        if not _curl_to(path, url, referer=referer, accept="text/html,*/*;q=0.8"):
            try:
                os.unlink(path)
            except Exception:
                pass
            return ""
        with open(path, encoding="utf-8", errors="replace") as f:
            data = f.read()
        os.unlink(path)
        return data
    except Exception as e:
        print("html fail", url[:80], e)
        return ""


def fetch_bytes(url: str, referer: str = "https://www.acibadem.com.tr/") -> bytes | None:
    """curl kullan — sunucu urllib tünelini engelliyor."""
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path = tmp.name
        if not _curl_to(
            path,
            url,
            referer=referer,
            accept="image/avif,image/webp,image/*,*/*;q=0.8",
        ):
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


def _fix_url(url: str) -> str:
    return (url or "").replace("\\", "/")


def load_jimer() -> list[dict]:
    html_text = fetch_html(JIMER_LIST, referer="https://jimer.com.tr/")
    if not html_text:
        return []
    rows = []
    for m in re.finditer(
        r'<a href="(https://jimer\.com\.tr/tr/hekim/[^"]+)">(.*?)<strong>([^<]+)</strong>',
        html_text,
        re.S,
    ):
        profile_url = m.group(1)
        block = m.group(2)
        name = html.unescape(m.group(3)).split(" - ")[0].strip()
        img_m = re.search(r'src="([^"]+upload/img[^"]+)"', block)
        if not img_m:
            continue
        rows.append(
            {
                "name": name,
                "img_url": _fix_url(img_m.group(1)),
                "profile_url": profile_url,
                "source": "jimer",
            }
        )
    return rows


def load_goz_nilufer() -> list[dict]:
    html_text = fetch_html(GOZ_NGM_LIST, referer="https://www.gozvakfi.com/")
    if not html_text:
        return []
    rows = []
    for m in re.finditer(
        r'class="gv-hekim-card[^"]*".*?href="([^"]+)".*?src="([^"]+)".*?gv-hekim-card__ad">([^<]+)',
        html_text,
        re.S,
    ):
        rows.append(
            {
                "name": html.unescape(m.group(3)).strip(),
                "img_url": m.group(2),
                "profile_url": m.group(1),
                "source": "gozvakfi",
            }
        )
    return rows


def load_kalparitmi() -> list[dict]:
    html_text = fetch_html(KALPARITMI_HOME, referer=KALPARITMI_HOME)
    if not html_text:
        return []
    rows = []
    for block in re.findall(r'<div class="kdoc">.*?</div>\s*</div>', html_text, re.S):
        img_m = re.search(
            r'<a class="kdoc-photo" href="([^"]+)"><img[^>]+src="([^"]+)"[^>]+alt="([^"]+)"',
            block,
        )
        if not img_m:
            continue
        sub_m = re.search(r'<div class="ksubt">([^<]+)</div>', block)
        badge_m = re.search(r'<span class="kbadge2">([^<]+)</span>', block)
        img = img_m.group(2)
        if not img.startswith("http"):
            img = KALPARITMI_HOME.rstrip("/") + img
        rows.append(
            {
                "name": html.unescape(img_m.group(3)).strip(),
                "img_url": img,
                "profile_url": img_m.group(1),
                "rank": html.unescape(sub_m.group(1)).strip() if sub_m else "",
                "department": html.unescape(badge_m.group(1)).strip() if badge_m else "",
                "source": "kalparitmi",
            }
        )
    return rows


def load_doruk() -> list[dict]:
    if not os.path.isfile(DORUK_JSON):
        return []
    with open(DORUK_JSON, encoding="utf-8") as f:
        return json.load(f)


def match_row(place_title: str, row: dict) -> int:
    return match_score(place_title, {"name": row.get("name") or ""})


def save_photo(place: Place, img_url: str, referer: str) -> bool:
    if not img_url:
        return False
    img_url = _fix_url(img_url)
    data = fetch_bytes(img_url, referer=referer)
    if not data:
        return False
    local = os.path.join(_DIR, "static", "doctor", f"{place.slug}.jpg")
    try:
        from io import BytesIO

        from PIL import Image

        im = Image.open(BytesIO(data)).convert("RGB")
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
    place.img_url = f"/static/doctor/{place.slug}.jpg"
    return True


def sync_doctors_json(db) -> int:
    """DB img_url → doctors.json (seed sonrası kaybolmasın)."""
    if not os.path.isfile(DOCTORS_JSON):
        return 0
    by_slug = {
        p.slug: p.img_url
        for p in db.query(Place).filter(Place.category == "doctor").all()
        if p.slug and p.img_url
    }
    with open(DOCTORS_JSON, encoding="utf-8") as f:
        rows = json.load(f)
    n = 0
    for row in rows:
        slug = row.get("slug")
        url = by_slug.get(slug)
        if url and row.get("img_url") != url:
            row["img_url"] = url
            n += 1
    if n:
        with open(DOCTORS_JSON, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
            f.write("\n")
    return n


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
    jimer_rows = load_jimer()
    goz_rows = load_goz_nilufer()
    kalp_rows = load_kalparitmi()
    doruk_rows = load_doruk()
    print(
        f"kaynak: acibadem={len(aci_rows)} jimer={len(jimer_rows)} "
        f"goz={len(goz_rows)} kalparitmi={len(kalp_rows)} doruk={len(doruk_rows)}"
    )

    db = SessionLocal()
    try:
        docs = db.query(Place).filter(Place.category == "doctor", Place.status == "approved").all()
        used_aci: set[str] = set()
        used_jimer: set[str] = set()
        used_goz: set[str] = set()
        used_kalp: set[str] = set()
        matched = 0
        photos = 0

        for p in docs:
            venue = p.venue_name or ""
            slug = p.slug or ""
            is_aci = venue == "acibadem-bursa" or slug.startswith("aci-")
            is_jimer = venue == "jimer-hastanesi" or slug.startswith("jimer-")
            is_goz = venue == "nilufer-goz-merkezi" or slug.startswith("ngm-")
            is_kalp = venue == "cekirge-kalp-aritmi" or slug.startswith("cka-")
            is_doruk = venue.startswith("doruk-") or slug.startswith("doruk-")

            if is_aci and aci_rows:
                best, score = None, 0
                for a in aci_rows:
                    code = a.get("code") or a.get("name") or ""
                    if code in used_aci:
                        continue
                    sc = match_score(p.title, a)
                    if sc > score:
                        best, score = a, sc
                if best and score >= 85:
                    used_aci.add(best.get("code") or best.get("name") or "")
                    matched += 1
                    about = strip_html(best.get("about") or "")
                    interests = best.get("interests") or []
                    if isinstance(interests, str):
                        interests = [interests]
                    units = best.get("units") or []
                    path = best.get("profile_path") or ""
                    profile_url = (SITE + path) if path.startswith("/") else (path or p.web or "")
                    img_url = abs_img(best.get("profil_image") or "")
                    if img_url and save_photo(p, img_url, SITE + "/"):
                        photos += 1
                    if about:
                        p.body = about[:4000]
                        first = about.split(".")[0].strip()
                        if len(first) >= 20:
                            p.blurb = (first[:280] + ".") if not first.endswith(".") else first[:281]
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
                    print(f"OK {p.slug} ← acibadem {best.get('name')} score={score}")
                    continue

            if is_doruk and doruk_rows:
                row = next((r for r in doruk_rows if r.get("slug") == p.slug), None)
                if row:
                    matched += 1
                    if save_photo(p, row.get("img_url") or "", DORUK_SITE):
                        photos += 1
                    extra = {
                        "profile_url": row.get("profile_url") or p.web or "",
                        "source": "doruktip",
                        "fee_note": "Randevu için doruktip.com / MHRS. BursaApp randevu satmaz.",
                    }
                    if row.get("department"):
                        extra["specialty_detail"] = row["department"]
                    if row.get("about"):
                        p.body = row["about"][:4000]
                    merge_place_extra(p, extra)
                    if row.get("profile_url"):
                        p.web = row["profile_url"]
                    print(f"OK {p.slug} ← doruktip {row.get('name')}")
                    continue

            ext_rows: list[dict] = []
            referer = ""
            used_set: set[str] = set()
            source = ""
            if is_jimer and jimer_rows:
                ext_rows, referer, used_set, source = jimer_rows, "https://jimer.com.tr/", used_jimer, "jimer"
            elif is_goz and goz_rows:
                ext_rows, referer, used_set, source = goz_rows, "https://www.gozvakfi.com/", used_goz, "gozvakfi"
            elif is_kalp and kalp_rows:
                ext_rows, referer, used_set, source = kalp_rows, KALPARITMI_HOME, used_kalp, "kalparitmi"

            if ext_rows:
                best, score = None, 0
                for row in ext_rows:
                    key = row.get("profile_url") or row.get("name") or ""
                    if key in used_set:
                        continue
                    sc = match_row(p.title, row)
                    if sc > score:
                        best, score = row, sc
                min_score = 85
                if best and score >= min_score:
                    used_set.add(best.get("profile_url") or best.get("name") or "")
                    matched += 1
                    if save_photo(p, best.get("img_url") or "", referer):
                        photos += 1
                    extra = {
                        "profile_url": best.get("profile_url") or p.web or "",
                        "source": source,
                        "fee_note": "Randevu için hastane sitesi / MHRS. BursaApp randevu satmaz.",
                    }
                    if best.get("department"):
                        extra["specialty_detail"] = best["department"]
                    if best.get("about"):
                        p.body = best["about"][:4000]
                    merge_place_extra(p, extra)
                    if best.get("profile_url"):
                        p.web = best["profile_url"]
                    print(f"OK {p.slug} ← {source} {best.get('name')} score={score}")
                    continue

            ex = place_extra(p)
            areas = specialty_areas(p.price_band or "")
            if areas and not ex.get("services"):
                merge_place_extra(p, {"services": areas})
            if not ex.get("linkedin_url"):
                merge_place_extra(p, {"linkedin_url": linkedin_search(p.title)})

        db.commit()
        synced = sync_doctors_json(db)
        print(f"matched={matched}/{len(docs)} photos={photos} json_sync={synced}")
    finally:
        db.close()


if __name__ == "__main__":
    # interests fix in saved json units were names already
    enrich()
