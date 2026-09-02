#!/usr/bin/env python3
"""Bursa etkinlik/konser — Etkinlinkler'den gece çekimi (gerçek kapak fotoğrafı).

Kaynak: https://www.etkinlinkler.com/bursa
Cron (00:00 İST = 21:00 UTC):
  0 21 * * * cd /root/aiProject && python3 BursaApp/events_fetch.py >> /tmp/bursaapp_events_fetch.log 2>&1
"""
from __future__ import annotations

import io
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import urlparse

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import slugify, tags_dump
from models import Place, SessionLocal, init_db

LISTING_URL = "https://www.etkinlinkler.com/bursa"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; BursaAppBot/1.0; +https://bursaapp.com)"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

MONTH_TR = {
    "oca": 1,
    "sub": 2,
    "şub": 2,
    "mar": 3,
    "nis": 4,
    "may": 5,
    "haz": 6,
    "tem": 7,
    "agu": 8,
    "ağu": 8,
    "eyl": 9,
    "eki": 10,
    "kas": 11,
    "ara": 12,
}

CAT_MAP = {
    "konser": "concert",
    "elektronik müzik": "concert",
    "müzik": "concert",
    "tiyatro": "theater",
    "çocuk tiyatrosu": "theater",
    "oyun": "theater",
    "stand-up": "event",
    "standup": "event",
    "festival": "event",
    "workshop": "event",
    "fuar": "event",
    "spor": "event",
    "çocuk": "event",
}

VENUE_ILCE = (
    ("nilüfer", "Nilüfer"),
    ("nilufer", "Nilüfer"),
    ("mudanya", "Mudanya"),
    ("gemlik", "Gemlik"),
    ("inegöl", "İnegöl"),
    ("inegol", "İnegöl"),
    ("yıldırım", "Yıldırım"),
    ("yildirim", "Yıldırım"),
    ("osmangazi", "Osmangazi"),
    ("merinos", "Osmangazi"),
    ("kültürpark", "Osmangazi"),
    ("kulturpark", "Osmangazi"),
)


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_text(url: str) -> str:
    return fetch(url).decode("utf-8", "replace")


def norm_title(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"\b(konseri|konser|bursa)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def map_category(label: str) -> str:
    key = (label or "").strip().lower()
    for k, v in CAT_MAP.items():
        if k in key:
            return v
    return "event"


def guess_ilce(venue: str) -> str:
    v = (venue or "").lower()
    for needle, ilce in VENUE_ILCE:
        if needle in v:
            return ilce
    return "Osmangazi"


def parse_starts_from_path(path: str) -> datetime | None:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})-(\d{6})", path)
    if not m:
        return None
    y, mo, d, hm = m.groups()
    try:
        return datetime(int(y), int(mo), int(d), int(hm[:2]), int(hm[2:4]), int(hm[4:6]))
    except ValueError:
        return None


def parse_starts_from_text(text: str, fallback_year: int | None = None) -> datetime | None:
    """Örn: '18 Eylül Cuma - 21:00' / '02 Eylül Çarşamba - 21:00'."""
    t = unescape(text or "")
    m = re.search(
        r"(\d{1,2})\s+(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|Temmuz|"
        r"Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|Aralık|Aralik)"
        r".*?(\d{1,2}):(\d{2})",
        t,
        re.I,
    )
    if not m:
        return None
    day = int(m.group(1))
    mon_raw = m.group(2).lower()
    mon_key = mon_raw[:3]
    # şubat → şub
    if mon_raw.startswith("şub") or mon_raw.startswith("sub"):
        mon_key = "şub"
    elif mon_raw.startswith("ağu") or mon_raw.startswith("agu"):
        mon_key = "ağu"
    month = MONTH_TR.get(mon_key) or MONTH_TR.get(mon_key.replace("ş", "s").replace("ğ", "g"))
    if not month:
        return None
    hour, minute = int(m.group(3)), int(m.group(4))
    year = fallback_year or datetime.now().year
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def parse_cards(html: str) -> list[dict[str, Any]]:
    arts = re.findall(r'<article class="reference-event-card">(.*?)</article>', html, re.S)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for a in arts:
        href_m = re.search(
            r'href="(https://www\.etkinlinkler\.com/etkinlik/[^"]+)"', a
        )
        img_m = re.search(r'src="(https://cdn\.etkinlinkler\.com/[^"]+)"', a)
        title_m = re.search(r"<h3>([^<]+)</h3>", a) or re.search(
            r'<img[^>]+alt="([^"]+)"', a
        )
        cat_m = re.search(r'reference-event-card__category">([^<]+)', a)
        venue_m = re.search(
            r'reference-event-card__venue"[^>]*>.*?<span>([^<]+)</span>', a, re.S
        )
        time_m = re.search(r'reference-event-card__time">([^<]+)', a)
        price_m = re.search(r"<strong>([^<]*₺[^<]*)</strong>", a)
        if not href_m or not title_m:
            continue
        href = unescape(href_m.group(1).rstrip("/"))
        # /etkinlik/{slug}/{id}
        parts = urlparse(href).path.strip("/").split("/")
        if len(parts) < 3 or parts[0] != "etkinlik":
            continue
        path_slug, eid = parts[1], parts[2]
        if not eid.isdigit() or eid in seen:
            continue
        seen.add(eid)
        title = unescape(title_m.group(1)).strip()
        cat_label = unescape(cat_m.group(1)).strip() if cat_m else ""
        venue = unescape(venue_m.group(1)).strip() if venue_m else ""
        time_txt = unescape(time_m.group(1)).strip() if time_m else ""
        price = unescape(price_m.group(1)).strip() if price_m else ""
        img = unescape(img_m.group(1)) if img_m else ""
        starts = parse_starts_from_path(path_slug) or parse_starts_from_text(time_txt)
        kind = map_category(cat_label)
        out.append(
            {
                "eid": eid,
                "path_slug": path_slug,
                "title": title,
                "url": href,
                "image": img,
                "cat_label": cat_label,
                "category": kind,
                "venue": venue,
                "time_txt": time_txt,
                "price": price,
                "starts": starts,
                "ilce": guess_ilce(venue),
            }
        )
    return out


def _strip_tags(html: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    t = re.sub(r"</p\s*>", "\n\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = unescape(t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def parse_detail_payload(html: str) -> dict[str, Any]:
    """Etkinlinkler detay HTML → about / rules / platforms / local starts."""
    out: dict[str, Any] = {}
    title = re.search(r"<title>([^<]+)", html)
    if title:
        parts = [unescape(p).strip() for p in re.split(r"\s*\|\s*", title.group(1))]
        out["title_parts"] = parts
        if len(parts) > 1:
            local = parse_starts_from_text(parts[1])
            if local:
                out["starts_local"] = local
        if len(parts) > 3:
            out["venue"] = parts[3]

    og = re.search(
        r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', html
    ) or re.search(
        r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']', html
    )
    if og and og.group(1).startswith("http"):
        out["image"] = unescape(og.group(1))

    desc = re.search(
        r'property=["\']og:description["\'][^>]*content=["\']([^"\']*)', html
    ) or re.search(r'name=["\']description["\'][^>]*content=["\']([^"\']*)', html)
    if desc:
        out["desc"] = unescape(desc.group(1)).strip()[:380]

    about_m = re.search(
        r"Etkinlik Hakkında</h2>\s*(.*?)(?:<h2|Etkinlik Kuralları|#SAHNE)",
        html,
        re.S | re.I,
    )
    if about_m:
        about = _strip_tags(about_m.group(1))
        if len(about) > 80:
            out["about"] = about[:4000]

    rules_m = re.search(
        r"Etkinlik Kuralları.*?(?:<[^>]+>)?\s*([-–].*?)(?:</(?:div|section|details)|<h2|## Mekan)",
        html,
        re.S | re.I,
    )
    if rules_m:
        rules = _strip_tags(rules_m.group(1))
        # satırlara böl
        bits = [b.strip(" -–•\t") for b in re.split(r"\s*[-–]\s+", rules) if len(b.strip()) > 20]
        if bits:
            out["rules"] = bits[:20]

    # Platform + başlangıç fiyatı blokları
    platforms: list[dict[str, Any]] = []
    seen_plat: set[str] = set()
    for m in re.finditer(
        r"(BUBILET|BILETINIAL|BILETIX|PASSO|Biletix|Bubilet|Passo)"
        r".{0,220}?Başlayan fiyatlarla\s*\*?\*?([\d.\s]+)\s*₺",
        html,
        re.S | re.I,
    ):
        name = m.group(1).upper().replace("İ", "I")
        if name == "BILETIX":
            name = "BILETIX"
        elif name.startswith("BUBI"):
            name = "BUBILET"
        elif "NIAL" in name or "İNIAL" in name.upper():
            name = "BILETINIAL"
        elif name.startswith("PAS"):
            name = "PASSO"
        price_raw = re.sub(r"[^\d]", "", m.group(2) or "")
        if not price_raw or name in seen_plat:
            continue
        seen_plat.add(name)
        platforms.append({"name": name, "from_price": f"{int(price_raw)} ₺"})
    if not platforms:
        # yedek: tek tek "Platform **350₺**"
        for name in ("BUBILET", "BILETINIAL", "BILETIX", "PASSO"):
            if name.lower() not in html.lower():
                continue
            pm = re.search(
                rf"{name}.{{0,120}}?(\d[\d.\s]*)\s*₺",
                html,
                re.S | re.I,
            )
            if pm:
                price_raw = re.sub(r"[^\d]", "", pm.group(1))
                if price_raw:
                    platforms.append({"name": name, "from_price": f"{int(price_raw)} ₺"})
    if platforms:
        # en ucuz önce
        def _pnum(p: dict) -> int:
            return int(re.sub(r"[^\d]", "", p.get("from_price") or "0") or 0)

        platforms.sort(key=_pnum)
        platforms[0]["cheapest"] = True
        out["platforms"] = platforms
        out["price_min"] = platforms[0]["from_price"]
        out["price_max"] = max(platforms, key=_pnum)["from_price"]

    return out


def enrich_from_detail(item: dict[str, Any]) -> None:
    """Detay sayfası: açıklama, about, kurallar, platform fiyatları, yerel saat."""
    try:
        html = fetch_text(item["url"])
    except Exception as e:
        log(f"  detail skip {item['eid']}: {e}")
        return
    payload = parse_detail_payload(html)
    if payload.get("image"):
        item["image"] = payload["image"]
    if payload.get("desc"):
        item["desc"] = payload["desc"]
    if payload.get("about"):
        item["about"] = payload["about"]
        # kısa blurb yoksa about’tan
        if not item.get("desc"):
            item["desc"] = payload["about"][:380]
    if payload.get("rules"):
        item["rules"] = payload["rules"]
    if payload.get("platforms"):
        item["platforms"] = payload["platforms"]
        item["price_min"] = payload.get("price_min")
        item["price_max"] = payload.get("price_max")
        if payload.get("price_min"):
            item["price"] = payload["price_min"]
    # Title’daki yerel saat (15:00) path’teki UTC (12:00) yerine
    if payload.get("starts_local"):
        item["starts"] = payload["starts_local"]
    elif not item.get("starts") and payload.get("title_parts"):
        parts = payload["title_parts"]
        if len(parts) > 1:
            item["starts"] = parse_starts_from_text(parts[1]) or item.get("starts")
    if payload.get("venue") and not item.get("venue"):
        item["venue"] = payload["venue"]

def _ext_from_url_or_bytes(url: str, data: bytes) -> str:
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def download_cover(item: dict[str, Any]) -> str:
    """CDN kapak → static/{category}/{slug}.(jpg|png|webp). Dönüş: site yolu."""
    url = item.get("image") or ""
    if not url:
        return ""
    kind = item["category"]
    slug = item["place_slug"]
    dest_dir = os.path.join(_DIR, "static", kind)
    os.makedirs(dest_dir, exist_ok=True)
    try:
        data = fetch(url, timeout=40)
    except Exception as e:
        log(f"  img fail {slug}: {e}")
        return ""
    if len(data) < 800:
        return ""
    ext = _ext_from_url_or_bytes(url, data)
    # avif → jpg (yaygın tarayıcı / img tag uyumu)
    if ext == ".avif":
        try:
            from PIL import Image

            im = Image.open(io.BytesIO(data)).convert("RGB")
            dest = os.path.join(dest_dir, f"{slug}.jpg")
            im.save(dest, "JPEG", quality=88)
            return f"/static/{kind}/{slug}.jpg"
        except Exception:
            dest = os.path.join(dest_dir, f"{slug}.avif")
            with open(dest, "wb") as f:
                f.write(data)
            return f"/static/{kind}/{slug}.avif"
    # webp bırak veya jpg'ye çevir
    if ext == ".webp":
        try:
            from PIL import Image

            im = Image.open(io.BytesIO(data)).convert("RGB")
            dest = os.path.join(dest_dir, f"{slug}.jpg")
            im.save(dest, "JPEG", quality=88)
            return f"/static/{kind}/{slug}.jpg"
        except Exception:
            pass
    dest = os.path.join(dest_dir, f"{slug}{ext}")
    with open(dest, "wb") as f:
        f.write(data)
    return f"/static/{kind}/{slug}{ext}"


def make_place_slug(item: dict[str, Any]) -> str:
    starts = item.get("starts")
    base = slugify(item["title"])[:50]
    if starts:
        return f"{item['category'][:3]}-{base}-{starts.strftime('%Y%m%d')}"[:80]
    return f"el-{item['eid']}"[:80]


def find_existing(db, item: dict[str, Any]) -> Place | None:
    slug = item["place_slug"]
    p = db.query(Place).filter(Place.slug == slug).first()
    if p:
        return p
    p = db.query(Place).filter(Place.web == item["url"]).first()
    if p:
        return p
    # eski seed: aynı gün + benzer başlık
    starts = item.get("starts")
    if not starts:
        return None
    day0 = starts.replace(hour=0, minute=0, second=0, microsecond=0)
    day1 = starts.replace(hour=23, minute=59, second=59, microsecond=0)
    nt = norm_title(item["title"])
    if len(nt) < 3:
        return None
    cands = (
        db.query(Place)
        .filter(
            Place.category.in_(("concert", "theater", "event")),
            Place.starts_at >= day0,
            Place.starts_at <= day1,
        )
        .all()
    )
    for c in cands:
        cn = norm_title(c.title)
        if not cn:
            continue
        if nt == cn or nt in cn or cn in nt:
            return c
    return None


def upsert(db, item: dict[str, Any], img_path: str) -> str:
    from models import merge_place_extra

    starts = item.get("starts")
    venue = item.get("venue") or ""
    blurb = item.get("desc") or ""
    about = (item.get("about") or "").strip()
    if not blurb:
        bits = [x for x in (venue, item.get("time_txt"), item.get("price")) if x]
        blurb = " · ".join(bits)[:380]
    body = about or blurb
    hours = ""
    if starts:
        hours = starts.strftime("%d.%m.%Y %H:%M")
    elif item.get("time_txt"):
        hours = item["time_txt"][:160]
    price = item.get("price_min") or item.get("price") or "Yaklaşan"
    fields = dict(
        title=item["title"][:200],
        category=item["category"],
        subcategory=slugify(item.get("cat_label") or item["category"])[:48],
        ilce=item.get("ilce") or "Osmangazi",
        address=venue[:280],
        web=item["url"][:280],
        hours_text=hours,
        price_band=str(price)[:80],
        blurb=blurb[:400],
        body=body[:8000],
        tags=tags_dump(
            [item["category"], item.get("cat_label") or "", "etkinlinkler"]
        ),
        featured=False,
        status="approved",
        starts_at=starts,
        ends_at=None,
        venue_name=venue[:200],
        ticket_price=str(price)[:80],
        ticket_url=item["url"][:280],
    )
    if img_path:
        fields["img_url"] = img_path[:500]

    extra_patch: dict[str, Any] = {"source": "etkinlinkler", "source_url": item["url"]}
    if item.get("platforms"):
        extra_patch["platforms"] = item["platforms"]
    if item.get("rules"):
        extra_patch["rules"] = item["rules"]
    if item.get("about"):
        extra_patch["about"] = item["about"][:4000]
    if item.get("price_min"):
        extra_patch["price_min"] = item["price_min"]
    if item.get("price_max"):
        extra_patch["price_max"] = item["price_max"]

    p = find_existing(db, item)
    if p is None:
        # slug çakışırsa eid ekle
        slug = item["place_slug"]
        if db.query(Place).filter(Place.slug == slug).first():
            slug = f"el-{item['eid']}"
        p = Place(slug=slug, **fields)
        db.add(p)
        db.flush()
        merge_place_extra(p, extra_patch)
        return "insert"
    for k, v in fields.items():
        setattr(p, k, v)
    merge_place_extra(p, extra_patch)
    return "update"


def _is_stock_photo(img_url: str) -> bool:
    """Visit/mekan yedek kopyası mı? (gerçek poster değil)."""
    if not img_url or not img_url.startswith("/static/"):
        return True
    path = os.path.join(_DIR, img_url.lstrip("/"))
    if not os.path.isfile(path) or os.path.getsize(path) < 4000:
        return True
    # bilinen visit yedekleri
    visit_dir = os.path.join(_DIR, "static", "visit")
    try:
        import hashlib

        h = hashlib.md5(open(path, "rb").read()).hexdigest()
        if os.path.isdir(visit_dir):
            for fn in os.listdir(visit_dir):
                if not fn.endswith(".jpg"):
                    continue
                vp = os.path.join(visit_dir, fn)
                if os.path.getsize(vp) != os.path.getsize(path):
                    continue
                if hashlib.md5(open(vp, "rb").read()).hexdigest() == h:
                    return True
    except Exception:
        pass
    return False


def wiki_artist_image(title: str) -> str | None:
    """tr/en Wikipedia özet — poster yoksa sanatçı foto yedeği."""
    import json
    from urllib.parse import quote

    clean = re.sub(r"\s*[·•\-–].*$", "", title or "").strip()
    clean = re.sub(
        r"\b(konseri|konser|bursa|electric|rengahenk)\b",
        "",
        clean,
        flags=re.I,
    ).strip(" ·-")
    if len(clean) < 3:
        return None
    candidates = [clean]
    if clean.lower() in ("nilüfer", "nilufer"):
        candidates = ["Nilüfer (şarkıcı)", clean]
    aliases = {
        "mustafa sandal": ["Mustafa Sandal"],
        "evgeny grinko": ["Evgeny Grinko", "Yevgeny Grinko"],
        "gökhan türkmen": ["Gökhan Türkmen"],
        "melis fis": ["Melis Fis"],
        "motive": ["Motive (rapper)", "Motive"],
        "hirai": ["HiraiZerdüş", "Hirai Zerdüş"],
        "düş sokağı": ["Düş Sokağı Sakinleri"],
        "dus sokagi": ["Düş Sokağı Sakinleri"],
    }
    key = clean.lower()
    for k, al in aliases.items():
        if k in key:
            candidates = al + candidates
            break
    hosts = (
        "https://tr.wikipedia.org/api/rest_v1/page/summary/",
        "https://en.wikipedia.org/api/rest_v1/page/summary/",
    )
    for name in candidates:
        for host in hosts:
            url = host + quote(name.replace(" ", "_"))
            try:
                data = json.loads(fetch(url, timeout=20).decode("utf-8", "replace"))
            except Exception:
                continue
            src = (data.get("originalimage") or data.get("thumbnail") or {}).get(
                "source"
            )
            if src and src.startswith("http"):
                return src
    return None


def backfill_stock_photos(db) -> int:
    """Etkinlinkler'de olmayan tarihli kayıtlar — Wikipedia sanatçı foto."""
    now = datetime.now()
    rows = (
        db.query(Place)
        .filter(
            Place.status == "approved",
            Place.category.in_(("concert", "theater", "event")),
            Place.starts_at.isnot(None),
            Place.starts_at >= now.replace(hour=0, minute=0, second=0, microsecond=0),
        )
        .all()
    )
    n = 0
    for p in rows:
        if not _is_stock_photo(p.img_url or ""):
            continue
        src = wiki_artist_image(p.title)
        if not src:
            log(f"  wiki miss {p.slug}")
            continue
        item = {
            "category": p.category,
            "place_slug": p.slug,
            "image": src,
            "title": p.title,
        }
        path = download_cover(item)
        if not path:
            continue
        p.img_url = path
        n += 1
        log(f"  wiki {p.slug} ← {src[-50:]}")
    return n



def backfill_details(limit: int = 40) -> int:
    """Mevcut etkinlinkler kayıtlarını detay sayfasından zenginleştir."""
    from models import merge_place_extra

    init_db()
    db = SessionLocal()
    n = 0
    try:
        rows = (
            db.query(Place)
            .filter(
                Place.status == "approved",
                Place.category.in_(("concert", "theater", "event")),
                Place.web.ilike("%etkinlinkler.com%"),
            )
            .order_by(Place.starts_at.asc().nulls_last())
            .limit(limit)
            .all()
        )
        for p in rows:
            item = {
                "eid": p.slug,
                "url": p.web or p.ticket_url,
                "title": p.title,
                "venue": p.venue_name,
                "category": p.category,
                "cat_label": p.subcategory,
                "price": p.ticket_price,
                "starts": p.starts_at,
                "place_slug": p.slug,
                "ilce": p.ilce,
            }
            if not item["url"]:
                continue
            enrich_from_detail(item)
            if item.get("about") or item.get("platforms") or item.get("rules"):
                if item.get("about"):
                    p.body = item["about"][:8000]
                    if not p.blurb or len(p.blurb) < 40:
                        p.blurb = item.get("desc") or item["about"][:380]
                if item.get("starts"):
                    p.starts_at = item["starts"]
                    p.hours_text = item["starts"].strftime("%d.%m.%Y %H:%M")
                if item.get("price"):
                    p.ticket_price = str(item["price"])[:80]
                    p.price_band = str(item["price"])[:80]
                patch = {"source": "etkinlinkler", "source_url": item["url"]}
                for k in ("platforms", "rules", "about", "price_min", "price_max"):
                    if item.get(k):
                        patch[k] = item[k]
                merge_place_extra(p, patch)
                n += 1
                log(f"  enrich {p.slug}")
        db.commit()
    finally:
        db.close()
    return n


def run() -> int:
    init_db()
    log("fetch listing " + LISTING_URL)
    try:
        html = fetch_text(LISTING_URL)
    except Exception as e:
        log(f"LISTING FAIL: {e}")
        return 1
    cards = parse_cards(html)
    log(f"cards={len(cards)}")
    if not cards:
        log("no cards — abort")
        return 2

    db = SessionLocal()
    n_ins = n_upd = n_img = 0
    try:
        for item in cards:
            enrich_from_detail(item)
            item["place_slug"] = make_place_slug(item)
            existing = find_existing(db, item)
            if existing is not None:
                item["place_slug"] = existing.slug
            img_path = download_cover(item)
            if img_path:
                n_img += 1
            action = upsert(db, item, img_path)
            if action == "insert":
                n_ins += 1
            else:
                n_upd += 1
            log(
                f"  {action} {item['category']} {item['place_slug']} "
                f"img={'yes' if img_path else 'no'} · {item['title'][:40]}"
            )
        n_wiki = backfill_stock_photos(db)
        # Yeni / güncellenen etkinlikler için bildirim kuyruğu
        try:
            from notify import enqueue, flush_outbox, recipients_for_kind

            fresh = [
                c
                for c in cards
                if c.get("starts") and c["starts"] >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            ][:12]
            for item in fresh:
                kind = item["category"]
                emails = recipients_for_kind(db, kind)
                if not emails:
                    continue
                enqueue(
                    kind=kind,
                    title=f"Bursa · {item['title']}",
                    body=(
                        f"{item.get('venue') or ''} · {item.get('time_txt') or ''} "
                        f"\n{item.get('url') or ''}"
                    ).strip(),
                    url=item.get("url") or "",
                    user_emails=emails[:80],
                )
            flush_outbox(limit=20)
        except Exception as e:
            log(f"notify skip: {e}")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    log(f"done insert={n_ins} update={n_upd} images={n_img} wiki={n_wiki}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("backfill-details", "enrich"):
        lim = int(sys.argv[2]) if len(sys.argv) > 2 else 40
        log(f"backfill-details limit={lim}")
        print("enriched", backfill_details(lim))
        raise SystemExit(0)

    raise SystemExit(run())
