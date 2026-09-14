#!/usr/bin/env python3
"""Instagram Bursa hero görselleri — manzara/tarih odaklı, insan figürü filtresi.

  python3 BursaApp/instagram_bursa_fetch.py
  python3 BursaApp/instagram_bursa_fetch.py --dry-run

Env (isteğe bağlı): INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(_DIR, "data", "instagram_bursa.json")
CACHE_DIR = os.path.join(_DIR, "static", "cache", "ig_bursa")
UA = {"User-Agent": "Mozilla/5.0 (compatible; BursaApp/1.0; +https://bursaapp.com)"}
IST = ZoneInfo("Europe/Istanbul")

# Manzara / tarih etiketleri önce; genel #bursa en sonda
HASHTAGS = (
    "cumalikizik",
    "golyazi",
    "bursadagezilecekyerler",
    "visitbursa",
    "uludagbursa",
    "yesilbursa",
    "bursatr",
    "bursa",
)
MAX_IG_SLIDES = 10
MAX_SLIDES = 14
MIN_IG_SLIDES = 4

# Caption'da varsa kesin atla (insan, moda, yemek reklamı)
BLOCK_RE = re.compile(
    r"\b("
    r"selfie|portre|portrait|insan|yüz|yuz|face|wedding|düğün|dugun|gelin|damat|"
    r"nişan|nisan|çift|couple|aile|family|bebek|baby|mezuniyet|graduation|"
    r"doğum\s*günü|dogum\s*gunu|birthday|model|dans|dance|headshot|makeup|makyaj|"
    r"outfit|kombin|elbise|etek|butik|moda|stoklarımız|stoklarimiz|bayılacak|"
    r"kızlar|kizlar|oyuncu|çalışan|calisan|köfte|kofte|dürüm|durum|pideci|"
    r"sipariş|siparis|reklam|☎|tel:|whatsapp|indirim|kampanya|kargo|"
    r"gelinlik|damatlık|damatlik|mezat|takım\s*foto|grup\s*foto"
    r")\b",
    re.I,
)

SCENERY_RE = re.compile(
    r"\b("
    r"gezilecek|manzara|tarih|tarihi|doğa|doga|şelale|selale|göl|gol|"
    r"uludağ|uludag|camii|cami|han|türbe|turbe|kale|panorama|köy|koy|"
    r"yeşil|yesil|hisar|teleferik|ormanı|ormani|dağ|dag|manzara|rotası|rotasi|"
    r"unesco|osmanlı|osmanli|müze|muze|sokak|evler|renkli\s*ev"
    r")\b",
    re.I,
)

PLACE_TITLES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"cumalıkızık|cumalikizik", re.I), "Cumalıkızık"),
    (re.compile(r"gölyazı|golyazi|uluabat", re.I), "Gölyazı · Uluabat"),
    (re.compile(r"ulu\s*cami", re.I), "Ulu Cami"),
    (re.compile(r"tophane|hisar", re.I), "Tophane · Hisar"),
    (re.compile(r"yeşil\s*türbe|yesil\s*turbe", re.I), "Yeşil Türbe"),
    (re.compile(r"inkaya|çınar|cinari", re.I), "İnkaya Çınarı"),
    (re.compile(r"koza\s*han", re.I), "Koza Han"),
    (re.compile(r"suuçtu|suuctu|şelale", re.I), "Suuçtu Şelalesi"),
    (re.compile(r"tirilye|zeytinbağı|zeytinbagi", re.I), "Tirilye"),
    (re.compile(r"panorama\s*1326", re.I), "Panorama 1326"),
    (re.compile(r"muradiye", re.I), "Muradiye"),
    (re.compile(r"uludağ|uludag", re.I), "Uludağ"),
    (re.compile(r"nilüfer|nilufer", re.I), "Nilüfer"),
    (re.compile(r"emir\s*sultan", re.I), "Emir Sultan"),
    (re.compile(r"irgandi|köprü|kopru", re.I), "İrgandi Köprüsü"),
]

STATIC_FILL: list[tuple[str, str]] = [
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

POST_URL_RE = re.compile(
    r"https://www\.instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)/?",
    re.I,
)


def _load_env() -> None:
    for path in (os.path.join(_DIR, ".env"), os.path.join(os.path.dirname(_DIR), ".env")):
        if not os.path.isfile(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def _is_profile_pic(url: str) -> bool:
    u = url.lower()
    return (
        "profile_pic" in u
        or "s150x150" in u
        or "stp=dst-jpg_s150" in u
        or "/t51.2885-19/" in u
        or "/t51.82787-19/" in u
    )


def _image_ok_url(url: str) -> bool:
    if _is_profile_pic(url):
        return False
    if re.search(r"s\d{2,3}x\d{2,3}", url) and not re.search(r"s640|s1080|s720|e35", url):
        return False
    return True


def _pretty_title(caption: str, hashtag: str = "") -> str:
    text = re.sub(r"^Image\s*\d+\s*:\s*", "", (caption or "").strip(), flags=re.I)
    blob = f"{text} #{hashtag.lstrip('#')}"
    for pat, label in PLACE_TITLES:
        if pat.search(blob):
            return label
    tags = re.findall(r"#([a-z0-9ğüşıöç_]+)", blob, re.I)
    for tag in tags:
        t = tag.lower()
        if t in ("bursa", "bursatr", "kesfet", "keşfet", "instagram", "reels", "reel"):
            continue
        if len(t) > 3:
            return t.replace("_", " ").title()[:40]
    line = re.sub(r"[@#]\S+", "", text).strip()
    line = re.sub(r"\s+", " ", line)
    if len(line) >= 8:
        return line[:56].rstrip(" .,") + ("…" if len(line) > 56 else "")
    return "Bursa"


def _caption_score(caption: str, permalink: str, hashtag: str) -> int:
    blob = f"{caption} #{hashtag} {permalink}"
    if BLOCK_RE.search(blob):
        return -99
    score = 0
    for pat, _ in PLACE_TITLES:
        if pat.search(blob):
            score += 4
    if SCENERY_RE.search(blob):
        score += 3
    if re.search(r"#bursa(da)?gezilecek|#visitbursa|#cumalikizik|#golyazi", blob, re.I):
        score += 2
    if "/reel/" in (permalink or "").lower():
        score -= 3
    if re.search(r"@[a-z0-9_.]{3,}", caption or "", re.I):
        score -= 2
    if re.search(r"^Image\s*\d+\s*:", caption or "", re.I) and score < 4:
        score -= 1
    return score


def _caption_ok(caption: str, permalink: str, hashtag: str) -> bool:
    return _caption_score(caption, permalink, hashtag) >= 2


def _fetch_jina_tag(hashtag: str, *, retries: int = 3) -> str:
    tag = hashtag.lstrip("#")
    src = f"https://www.instagram.com/explore/tags/{urllib.parse.quote(tag)}/"
    jina = "https://r.jina.ai/" + src
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(jina, headers={**UA, "Accept": "text/plain"})
            with urllib.request.urlopen(req, timeout=50) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            time.sleep(2 + attempt * 2)
    raise last_err or OSError("jina fail")


def _parse_jina_markdown(text: str, hashtag: str) -> list[dict]:
    rows: list[dict] = []
    seen_img: set[str] = set()
    blocks = re.split(r"(?=!\[)", text)
    for block in blocks:
        m_img = re.search(r"!\[([^\]]*)\]\((https://scontent[^)]+)\)", block)
        if not m_img:
            continue
        caption = m_img.group(1).strip()
        img_url = m_img.group(2).strip()
        if not _image_ok_url(img_url) or img_url in seen_img:
            continue
        post_m = POST_URL_RE.search(block)
        permalink = post_m.group(0) if post_m else ""
        score = _caption_score(caption, permalink, hashtag)
        if score < 2:
            continue
        seen_img.add(img_url)
        rows.append(
            {
                "img_remote": img_url,
                "title": _pretty_title(caption, hashtag),
                "permalink": permalink,
                "hashtag": hashtag,
                "score": score,
            }
        )
    rows.sort(key=lambda r: r.get("score") or 0, reverse=True)
    return rows


def _fetch_graph_api(hashtag: str, *, limit: int = 20) -> list[dict]:
    token = (os.environ.get("INSTAGRAM_ACCESS_TOKEN") or "").strip()
    user_id = (os.environ.get("INSTAGRAM_USER_ID") or "").strip()
    tag_id = (os.environ.get("INSTAGRAM_HASHTAG_ID") or "").strip()
    if not token or not user_id:
        return []
    if not tag_id:
        q = urllib.parse.urlencode({"user_id": user_id, "q": hashtag.lstrip("#")})
        url = f"https://graph.facebook.com/v21.0/ig_hashtag_search?{q}&access_token={token}"
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read()
            data = json.loads(raw.decode())
            items = data.get("data") or []
            if items:
                tag_id = str(items[0].get("id") or "")
        except Exception as e:
            print("graph hashtag_search fail", e, file=sys.stderr)
            return []
    if not tag_id:
        return []
    fields = "caption,media_type,media_url,permalink,thumbnail_url,timestamp"
    q = urllib.parse.urlencode({"user_id": user_id, "fields": fields, "limit": str(limit)})
    url = f"https://graph.facebook.com/v21.0/{tag_id}/top_media?{q}&access_token={token}"
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25).read()
        data = json.loads(raw.decode())
    except Exception as e:
        print("graph top_media fail", e, file=sys.stderr)
        return []
    out: list[dict] = []
    for item in data.get("data") or []:
        if item.get("media_type") not in ("IMAGE", "CAROUSEL_ALBUM"):
            continue
        cap = (item.get("caption") or "").strip()
        permalink = (item.get("permalink") or "").strip()
        score = _caption_score(cap, permalink, hashtag)
        if score < 2:
            continue
        img = (item.get("media_url") or item.get("thumbnail_url") or "").strip()
        if not img:
            continue
        out.append(
            {
                "img_remote": img,
                "title": _pretty_title(cap, hashtag),
                "permalink": permalink,
                "hashtag": hashtag,
                "score": score,
            }
        )
    out.sort(key=lambda r: r.get("score") or 0, reverse=True)
    return out


def _download(url: str, dest: str) -> bool:
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        req = urllib.request.Request(url, headers={**UA, "Referer": "https://www.instagram.com/"})
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = resp.read()
        if len(data) < 8000:
            return False
        with open(dest, "wb") as f:
            f.write(data)
        return True
    except OSError as e:
        print("download fail", dest, e, file=sys.stderr)
        return False


def _local_path(remote: str, permalink: str) -> str:
    key = permalink or remote
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    ext = ".png" if ".png" in remote.lower() else ".jpg"
    return os.path.join(CACHE_DIR, f"{h}{ext}")


def collect_candidates() -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()

    for tag in HASHTAGS:
        for row in _fetch_graph_api(tag, limit=12):
            k = row.get("img_remote") or ""
            if k and k not in seen:
                seen.add(k)
                rows.append(row)
        if len(rows) >= MAX_IG_SLIDES * 2:
            break

    if len(rows) < MAX_IG_SLIDES * 2:
        for tag in HASHTAGS:
            try:
                md = _fetch_jina_tag(tag)
                parsed = _parse_jina_markdown(md, tag)
                print(f"#{tag}: {len(parsed)} aday (jina)")
            except Exception as e:
                print(f"jina fail #{tag}:", e, file=sys.stderr)
                continue
            for row in parsed:
                k = row.get("img_remote") or ""
                if not k or k in seen:
                    continue
                seen.add(k)
                rows.append(row)
            if len(rows) >= MAX_IG_SLIDES * 2:
                break

    rows.sort(key=lambda r: r.get("score") or 0, reverse=True)
    return rows[: MAX_IG_SLIDES * 2]


def build_slides(candidates: list[dict], *, download: bool = True) -> list[dict]:
    slides: list[dict] = []
    for row in candidates:
        if len(slides) >= MAX_IG_SLIDES:
            break
        remote = row.get("img_remote") or ""
        if not remote:
            continue
        title = row.get("title") or "Bursa"
        local = _local_path(remote, row.get("permalink") or "")
        web_path = "/static/cache/ig_bursa/" + os.path.basename(local)
        if download:
            if not os.path.isfile(local):
                if not _download(remote, local):
                    continue
        else:
            web_path = remote
        slides.append(
            {
                "img": web_path,
                "title": title,
                "permalink": row.get("permalink") or "",
                "hashtag": row.get("hashtag") or "",
                "source": "instagram",
            }
        )
    return slides


def _pad_static(slides: list[dict]) -> list[dict]:
    seen_imgs = {s["img"] for s in slides}
    seen_titles = {s["title"] for s in slides}
    for src, title in STATIC_FILL:
        if len(slides) >= MAX_SLIDES:
            break
        web = f"/static/{src}"
        if web in seen_imgs or title in seen_titles:
            continue
        if not os.path.isfile(os.path.join(_DIR, "static", src.replace("visit/", "visit/"))):
            continue
        slides.append({"img": web, "title": title, "permalink": "", "hashtag": "", "source": "static"})
        seen_imgs.add(web)
        seen_titles.add(title)
    return slides


def run(*, dry_run: bool = False) -> int:
    _load_env()
    candidates = collect_candidates()
    if not candidates:
        print("Aday bulunamadı — mevcut JSON korunuyor.", file=sys.stderr)
        return 1
    ig_slides = build_slides(candidates, download=not dry_run)
    if len(ig_slides) < MIN_IG_SLIDES:
        print(f"Yetersiz IG slayt ({len(ig_slides)}) — mevcut JSON korunuyor.", file=sys.stderr)
        return 1
    slides = _pad_static(list(ig_slides))
    payload = {
        "generated_at": datetime.now(IST).isoformat(timespec="minutes"),
        "hashtags": list(HASHTAGS),
        "slides": slides,
        "ig_count": len(ig_slides),
        "note": "Manzara/tarih caption skoru; reel/mod/yemek reklamı elendi; statik yedek dolgu.",
    }
    if dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:5000])
        return 0
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"OK {len(ig_slides)} IG + {len(slides) - len(ig_slides)} statik = {len(slides)} slayt → {OUT_JSON}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    raise SystemExit(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
