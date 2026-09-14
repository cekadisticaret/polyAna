"""Bursa devlet diş birimleri — Sağlık Bakanlığı / MHRS resmi kaynakları.

Kaynaklar (uydurma yok):
  · bursaism.saglik.gov.tr ADSM tablosu
  · Kurum *.saglik.gov.tr iletişim (var adres / var telefon)
  · data/hospitals.json (price_band=Diş, teyitli web/tel)
  · SKRS GetSkrsKurum (ilKodu=16, isteğe bağlı önbellek)

MHRS randevu API'si halka açık değil; yalnızca mhrs.gov.tr bağlantısı verilir.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "data")
HOSPITALS_PATH = os.path.join(DATA, "hospitals.json")
SKRS_CACHE = os.path.join(DATA, "mhrs_skrs_dental.json")

MHRS_RANDEVU_URL = "https://mhrs.gov.tr/vatandas/#/Randevu"
MHRS_IL_KODU = 16
SKRS_GUID = "c3eade04-4f91-5dab-e043-14031b0ac9f9"
SKRS_URL = "https://skrs.saglik.gov.tr/api/SkrsService/GetSkrsKurum"

BURSAISM_ADSM_PAGE = (
    "https://bursaism.saglik.gov.tr/TR-15572/agiz-dis-sagligi-merkezleri-adsm.html"
)

# Kurum sitesi → dentist slug (mevcut kayıtlarla hizalı)
SITE_SLUG = {
    "bursaadseah.saglik.gov.tr": "bursa-adseah",
    "niluferadsm.saglik.gov.tr": "nilufer-adsm-dis",
    "niluferadsh.saglik.gov.tr": "nilufer-adsm-dis",
    "duacinariadsm.saglik.gov.tr": "bursa-duacinari-adsm",
}

ADSEAH_KNOWN = {
    "address": "Çekirge, Dr. Sadık Ahmet Cad., Osmangazi / Bursa",
    "phone": "444 0 476",
    "ilce": "Osmangazi",
}

# ISM tablo adı → slug
NAME_SLUG_HINTS: tuple[tuple[str, str], ...] = (
    ("duacinari", "bursa-duacinari-adsm"),
    ("duaçinari", "bursa-duacinari-adsm"),
    ("nilufer", "nilufer-adsm-dis"),
    ("nilüfer", "nilufer-adsm-dis"),
    ("eğitim ve araştırma", "bursa-adseah"),
    ("egitim ve arastirma", "bursa-adseah"),
    ("adseah", "bursa-adseah"),
)

DENTAL_SKRS = re.compile(r"a[gğ]ız|agiz|di[sş]|adsm", re.I)
TABLE_ROW = re.compile(
    r"<tr[^>]*>\s*<td[^>]*>.*?</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>",
    re.I | re.S,
)
CONTACT_JS = re.compile(
    r'var\s+adres\s*=\s*"([^"]+)";\s*var\s+telefon\s*=\s*"([^"]+)";',
    re.I | re.S,
)
STRIP_TAGS = re.compile(r"<[^>]+>")


def _slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().translate(str.maketrans("çğıöşü", "cgiosu"))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or "adsm-bursa"


def _norm_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10 and digits.startswith("224"):
        return f"0{digits[:3]} {digits[3:6]} {digits[6:8]} {digits[8:]}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"{digits[:4]} {digits[4:7]} {digits[7:9]} {digits[9:]}"
    return (raw or "").strip()[:40]


def _guess_ilce(title: str, address: str) -> str:
    blob = f"{title} {address}".upper()
    for ilce in (
        "Nilüfer", "Osmangazi", "Yıldırım", "İnegöl", "Mudanya", "Gemlik",
        "Mustafakemalpaşa", "Karacabey", "Kestel", "Gürsu", "Orhangazi",
    ):
        if ilce.upper() in blob or ilce.upper().replace("İ", "I") in blob:
            return ilce
    m = re.search(r"/\s*([A-ZÇĞİÖŞÜ]+)\s*$", address.upper())
    if m:
        cand = m.group(1).title().replace("I", "ı")
        if cand in ("Nilüfer", "Osmangazi", "Yıldırım", "Inegol", "Bursa"):
            return "İnegöl" if cand == "Inegol" else cand
    return ""


def _guess_slug(title: str) -> str:
    low = title.lower()
    for hint, slug in NAME_SLUG_HINTS:
        if hint in low:
            return slug
    return _slugify(title)


def _fetch_html(url: str, *, timeout: float = 20.0) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "BursaApp/1.0 (+https://bursaapp.com; mhrs dental)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _row_base(
    *,
    title: str,
    slug: str | None = None,
    ilce: str = "",
    address: str = "",
    phone: str = "",
    web: str = "",
    blurb: str = "",
    featured: bool = False,
    source: str = "mhrs",
) -> dict:
    slug = slug or _guess_slug(title)
    ilce = ilce or _guess_ilce(title, address) or "Bursa"
    phone_n = _norm_phone(phone)
    return {
        "title": title.strip(),
        "slug": slug,
        "ilce": ilce,
        "address": address.strip()[:280],
        "phone": phone_n,
        "web": (web or "").strip()[:280],
        "hours_text": "Mesai · MHRS / 182",
        "price_band": "Devlet",
        "featured": featured,
        "tags": ["mhrs", "devlet", "adsm", "verified", "dis"],
        "blurb": blurb or f"Resmi devlet ADSM · Randevu MHRS / 182 · {MHRS_RANDEVU_URL}",
        "mhrs_url": MHRS_RANDEVU_URL,
        "source": source,
    }


def fetch_bursaism_adsm_table() -> list[dict]:
    """bursaism.saglik.gov.tr resmi ADSM tablosu."""
    try:
        html = _fetch_html(BURSAISM_ADSM_PAGE, timeout=25)
    except Exception as exc:
        print(f"MHRS/ISM tablo uyarı ({exc})", flush=True)
        return []
    out: list[dict] = []
    for m in TABLE_ROW.finditer(html):
        name = STRIP_TAGS.sub(" ", m.group(1))
        name = re.sub(r"\s+", " ", name).strip()
        addr = STRIP_TAGS.sub(" ", m.group(2))
        addr = re.sub(r"\s+", " ", addr).strip()
        phone = STRIP_TAGS.sub(" ", m.group(3))
        phone = re.sub(r"\s+", " ", phone).strip()
        if not name or not DENTAL_SKRS.search(name):
            continue
        if re.search(r"ADSM ADI|TELEFON|FAKS|^NO$", name, re.I):
            continue
        if not re.search(r"\d{3}", phone):
            continue
        slug = _guess_slug(name)
        if "nilufer" in slug or "nilufer" in name.lower():
            slug = "nilufer-adsm-dis"
        elif "duacinari" in slug or "dua" in name.lower():
            slug = "bursa-duacinari-adsm"
        title = name.title() if name.isupper() else name
        if "duacinari" in slug or "dua" in name.lower():
            title = "Bursa Duaçınarı Ağız ve Diş Sağlığı Merkezi"
        elif "nilufer" in slug:
            title = "Nilüfer Ağız ve Diş Sağlığı Merkezi"
        out.append(
            _row_base(
                title=title,
                slug=slug,
                address=addr,
                phone=phone,
                web="https://bursaism.saglik.gov.tr/",
                blurb="Resmi kayıt · Bursa İl Sağlığı ADSM listesi · MHRS / 182.",
                source="mhrs_ism",
            )
        )
    return out


def fetch_saglik_site_contacts() -> list[dict]:
    """Kurum web sitesindeki var adres/telefon blokları."""
    sites = (
        ("https://bursaadseah.saglik.gov.tr/", "Bursa Ağız ve Diş Sağlığı Eğitim ve Araştırma Hastanesi", True),
        ("https://niluferadsm.saglik.gov.tr/", "Nilüfer Ağız ve Diş Sağlığı Merkezi", True),
        ("https://duacinariadsm.saglik.gov.tr/", "Bursa Duaçınarı Ağız ve Diş Sağlığı Merkezi", False),
    )
    out: list[dict] = []
    for url, title, featured in sites:
        host = urllib.parse.urlparse(url).netloc.lower()
        slug = SITE_SLUG.get(host) or _guess_slug(title)
        try:
            html = _fetch_html(url, timeout=20)
        except Exception:
            continue
        m = CONTACT_JS.search(html)
        if not m:
            continue
        addr, phone = m.group(1).strip(), m.group(2).strip()
        if slug == "bursa-adseah":
            addr = ADSEAH_KNOWN["address"]
            phone = ADSEAH_KNOWN["phone"]
        out.append(
            _row_base(
                title=title,
                slug=slug,
                address=addr,
                phone=phone,
                web=url,
                featured=featured,
                ilce=ADSEAH_KNOWN["ilce"] if slug == "bursa-adseah" else "",
                blurb="Resmi kurum sitesi · MHRS / 182.",
                source="mhrs_site",
            )
        )
    return out


def load_hospitals_dental() -> list[dict]:
    if not os.path.isfile(HOSPITALS_PATH):
        return []
    out: list[dict] = []
    for raw in json.loads(open(HOSPITALS_PATH, encoding="utf-8").read()):
        band = (raw.get("price_band") or "").strip()
        tags = raw.get("tags") or []
        title = (raw.get("title") or "").strip()
        if band != "Diş" and "dis" not in tags:
            continue
        if not title:
            continue
        if not (raw.get("phone") or raw.get("web")):
            continue
        slug = raw.get("slug") or ""
        if slug and not slug.endswith("-dis"):
            slug = f"{slug}-dis" if "adsm" in slug else slug
        out.append(
            _row_base(
                title=title,
                slug=slug or None,
                ilce=raw.get("ilce") or "",
                address=raw.get("address") or "",
                phone=raw.get("phone") or "",
                web=raw.get("web") or "",
                blurb=raw.get("blurb") or "Devlet diş · MHRS / 182.",
                featured=bool(raw.get("featured")),
                source="mhrs_hospital",
            )
        )
    return out


def _load_skrs_cache() -> list[dict] | None:
    if not os.path.isfile(SKRS_CACHE):
        return None
    try:
        data = json.loads(open(SKRS_CACHE, encoding="utf-8").read())
        if isinstance(data, list) and data:
            return data
    except Exception:
        pass
    return None


def _save_skrs_cache(rows: list[dict]) -> None:
    os.makedirs(DATA, exist_ok=True)
    with open(SKRS_CACHE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def fetch_skrs_dental(*, use_cache: bool = True, timeout: float = 90.0) -> list[dict]:
    """SKRS kurum listesi — Bursa, diş/adsm adı geçen aktif birimler."""
    if use_cache:
        cached = _load_skrs_cache()
        if cached is not None:
            return cached
    q = urllib.parse.urlencode(
        {"skrsCodeSystemGuid": SKRS_GUID, "ilKodu": str(MHRS_IL_KODU)}
    )
    url = f"{SKRS_URL}?{q}"
    rows_raw: list[dict] = []
    try:
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
            path = tmp.name
        r = subprocess.run(
            [
                "curl",
                "-fsSL",
                "--max-time",
                str(int(timeout)),
                "-A",
                "BursaApp/1.0 (+https://bursaapp.com)",
                "-o",
                path,
                url,
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise OSError(r.stderr[:200] or f"curl exit {r.returncode}")
        data = json.loads(open(path, encoding="utf-8").read())
        try:
            os.unlink(path)
        except OSError:
            pass
        rows_raw = data.get("sonuc") or []
    except Exception as exc:
        print(f"MHRS/SKRS uyarı ({exc})", flush=True)
        return _load_skrs_cache() or []
    out: list[dict] = []
    for r in rows_raw:
        if not r.get("AKTIF", True):
            continue
        name = (r.get("ADI") or "").strip()
        if not name or not DENTAL_SKRS.search(name):
            continue
        if re.search(r"birimi yok|laboratuvar", name, re.I):
            continue
        out.append(
            _row_base(
                title=name.title() if name.isupper() else name,
                address=f"{name} · Bursa",
                blurb="SKRS resmi kurum kaydı · MHRS / 182.",
                source="mhrs_skrs",
            )
        )
    if out:
        _save_skrs_cache(out)
    return out


def merge_mhrs_sources(*groups: list[dict]) -> list[dict]:
    """Öncelik: site iletişim > ISM tablo > hospitals > SKRS."""
    by_slug: dict[str, dict] = {}
    order = ("mhrs_site", "mhrs_ism", "mhrs_hospital", "mhrs_skrs", "mhrs")

    def score(row: dict) -> int:
        src = row.get("source") or "mhrs"
        try:
            return order.index(src)
        except ValueError:
            return len(order)

    for group in groups:
        for raw in group:
            slug = raw.get("slug") or _guess_slug(raw.get("title") or "")
            cur = by_slug.get(slug)
            if cur is None or score(raw) < score(cur):
                by_slug[slug] = dict(raw)
                continue
            for k, v in raw.items():
                if k in ("source",):
                    continue
                if v in (None, "", [], {}):
                    continue
                if k in ("phone", "web", "address") and cur.get(k):
                    if score(raw) >= score(cur):
                        continue
                cur[k] = v
            tags = list(cur.get("tags") or [])
            for t in raw.get("tags") or []:
                if t not in tags:
                    tags.append(t)
            cur["tags"] = tags
    rows = list(by_slug.values())
    rows.sort(key=lambda r: (0 if r.get("featured") else 1, r.get("ilce") or "", r.get("title") or ""))
    return rows


def fetch_official_dental(*, skrs: bool = True) -> list[dict]:
    """Tüm resmi devlet diş kaynaklarını birleştir."""
    ism = fetch_bursaism_adsm_table()
    sites = fetch_saglik_site_contacts()
    hospitals = load_hospitals_dental()
    skrs_rows: list[dict] = []
    if skrs:
        skrs_rows = fetch_skrs_dental()
    merged = merge_mhrs_sources(sites, ism, hospitals, skrs_rows)
    print(
        f"MHRS/resmi: {len(merged)} birim (site {len(sites)} · ISM {len(ism)} · hastane {len(hospitals)} · SKRS {len(skrs_rows)})",
        flush=True,
    )
    return merged


if __name__ == "__main__":
    for row in fetch_official_dental():
        print(f"- {row['slug']}: {row['title']} · {row.get('phone') or '—'}")
