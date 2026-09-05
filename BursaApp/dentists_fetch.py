#!/usr/bin/env python3
"""Bursa diş hekimleri — MHRS/resmi ADSM + OSM + el seçimi + doktor birleşimi.

  python3 BursaApp/dentists_fetch.py              # → data/dentists.json
  python3 BursaApp/dentists_fetch.py --seed       # fetch + seed_health (DB)
  python3 BursaApp/dentists_fetch.py --geocode    # eksik koordinatları Nominatim ile doldur
  python3 BursaApp/dentists_fetch.py --no-skrs    # SKRS isteğini atla (yavaş ağ)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "data")
DENTISTS_PATH = os.path.join(DATA, "dentists.json")
CURATED_PATH = os.path.join(DATA, "dentists_curated.json")
DOCTORS_PATH = os.path.join(DATA, "doctors.json")
GEOCODE_CACHE = os.path.join(DATA, "dentist_geocode.json")

ILCELER = (
    "Osmangazi", "Nilüfer", "Yıldırım", "Mudanya", "Gemlik", "İnegöl",
    "Mustafakemalpaşa", "İznik", "Kestel", "Gürsu", "Orhangazi", "Karacabey",
    "Yenişehir", "Orhaneli", "Büyükorhan", "Harmancık", "Keles",
)
ILCE_NORM = {x.lower().replace("i", "ı"): x for x in ILCELER}

OVERPASS = "https://overpass.kumi.systems/api/interpreter"
PHOTON = "https://photon.komoot.io/api/"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
BURSA_BBOX = "28.07,39.48,30.18,40.52"

SKIP_NAME = re.compile(
    r"sokak|sokağı|cadde|bulvar|mahalle sınır|ilkokul|lise|fakülte inşaat|"
    r"konsolos|valiliği|koordinasyon|bedesten|dışkapı|dışkaya|dişçi sok|"
    r"camii|ilkokulu|üniversitesi diş hekimliği fakültesi temel",
    re.I,
)
DENTAL_NAME = re.compile(
    r"a[gğ]ız|agiz|di[sş]|dent|adsm|ortodont|implant|periodon|endodont|"
    r"protez|pedodont|poliklin|klinik|muayene|dental|bursadent|mesam|"
    r"dentgroup|beyaz|korudi[sş]|vizyon|tuval|meta|venüs|venus|yelken|güne[sş]",
    re.I,
)

from mhrs_dental import MHRS_RANDEVU_URL, fetch_official_dental

ORIGINAL_SLUGS = frozenset(
    {
        "nilufer-adsm-dis",
        "dentgroup-bursa",
        "pan-dental-bursa",
        "bursa-ortodonti-merkezi",
        "acibadem-dis-bursa",
        "medical-park-dis-bursa",
        "doruk-dis-cekirge",
        "smile-art-dis-klinigi",
        "bursa-cocuk-dis-klinigi",
    }
)

INVENTED_TITLE = re.compile(
    r"^Özel (Balat|Bursa Smile|Bursa İmplant|Dent Bursa|Denthalia|Görükle|Gülden|Hamitler|Oralis|Prestij|İdeal|Nova|Panayır|Siteler|Zafer|Altınova|Bağlarbaşı|Emek|Heykel|Medident|Çekirge|Davutdede|Demirtaş|Küplüpınar|White Smile|Orhaneli|Harmancık|Keles|Büyükorhan|Mudanya|Gemlik|Gürsu|Kestel|Orhangazi|MKP|Karacabey|Yenişehir|İznik|İnegöl)",
    re.I,
)
GENERIC_PRIVATE = re.compile(
    r"^(Gürsu|Kestel|Orhangazi|Mustafakemalpaşa|Karacabey|Yenişehir|İznik|İnegöl|Mudanya|Gemlik) (Ağız ve Diş Polikliniği|Diş Polikliniği|Diş Kliniği|Özel Diş Polikliniği)$",
    re.I,
)
REJECT_TITLES = frozenset(
    {
        "Bursa Ağız ve Diş Sağlığı Hastanesi",
        "Detay Diş Polikliniği",
        "Sinan Ülkü Diş Polikliniği",
        "Memorial Bursa · Ağız ve Diş",
        "Medicana Bursa · Diş",
        "Liv Hospital Bursa · Diş",
        "Gemlik Ağız ve Diş Sağlığı Polikliniği",
    }
)


def _has_phone(row: dict) -> bool:
    return bool(re.search(r"\d{7,}", row.get("phone") or ""))


def _has_web(row: dict) -> bool:
    return (row.get("web") or "").strip().startswith("http")


def _has_coords(row: dict) -> bool:
    return row.get("lat") not in (None, "") and row.get("lng") not in (None, "")


def is_verified(row: dict) -> bool:
    """Yalnız teyitli kayıtlar — web, telefon, koordinat, el seçimi veya resmi ADSM."""
    title = (row.get("title") or "").strip()
    if not title or title in REJECT_TITLES:
        return False
    if INVENTED_TITLE.search(title) or "Merkez Diş" in title:
        return False
    if GENERIC_PRIVATE.match(title):
        return False
    slug = row.get("slug") or ""
    src = (row.get("source") or "").lower()
    tags = row.get("tags") or []
    if src.startswith("mhrs") or "mhrs" in tags:
        return True
    if slug in ORIGINAL_SLUGS:
        return True
    if "verified" in tags and (_has_phone(row) or _has_web(row) or _has_coords(row)):
        return True
    if row.get("price_band") == "Devlet" and "adsm" in tags and (
        _has_web(row) or _has_phone(row) or slug in ORIGINAL_SLUGS
    ):
        return True
    if row.get("source") == "osm" and _has_coords(row):
        return True
    if title.startswith("Diş Hekimi ") and _has_coords(row):
        return True
    if _has_web(row) or _has_phone(row):
        return True
    return False


def purge_orphan_dentists(keep_slugs: set[str]) -> int:
    from models import Place, SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        orphans = db.query(Place).filter(Place.category == "dentist", Place.slug.notin_(keep_slugs)).all()
        for p in orphans:
            db.delete(p)
        db.commit()
        return len(orphans)
    finally:
        db.close()


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().translate(str.maketrans("çğıöşü", "cgiosu"))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or "dis-klinigi"


def norm_ilce(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return ""
    low = t.lower().replace("i", "ı")
    for key, val in ILCE_NORM.items():
        if key in low or low in key:
            return val
    for il in ILCELER:
        if il.lower() in t.lower():
            return il
    return t[:48]


def _title_key(title: str) -> str:
    s = unicodedata.normalize("NFKD", title or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    s = re.sub(r"\s+(AĞIZ|AGIZ)\s+VE\s+DI[SŞ]\s+SAĞLIĞI", " ADS ", s)
    s = re.sub(r"\s+POL[Iİ]KL[Iİ]N[Iİ][GĞ]I", " POL ", s)
    s = re.sub(r"\s+MERKEZ[Iİ]", " MER ", s)
    return re.sub(r"\s+", " ", s).strip()


def infer_band(title: str, tags: dict | None = None) -> str:
    n = (title or "").upper()
    tags = tags or {}
    hc = (tags.get("healthcare") or "").lower()
    if "ADSM" in n or "AĞIZ VE DİŞ SAĞLIĞI MERKEZ" in n or "EĞİTİM VE ARAŞTIRMA" in n:
        return "Devlet"
    if hc == "hospital" and "DİŞ" in n:
        return "Devlet"
    if any(x in n for x in ("HASTANE", "ACIBADEM", "MEDICAL PARK", "MEMORIAL", "MEDICANA", "DORUK", "LIV ")):
        return "Özel"
    if re.match(r"^(DT\.|UZM\.?\s*DT\.|DR\.?\s*DT\.|PROF\.?\s*DR\.?\s*)", n):
        return "Klinik"
    if "ÖZEL" in n or "KLINIK" in n or "KLİNİK" in n or "POLİKLİN" in n:
        return "Özel"
    return "Klinik"


def addr_from_tags(tags: dict) -> str:
    parts = []
    for k in ("addr:street", "addr:housenumber", "addr:neighbourhood", "addr:suburb"):
        v = (tags.get(k) or "").strip()
        if v:
            parts.append(v)
    if parts:
        line = " ".join(parts)
        ilce = norm_ilce(tags.get("addr:district") or tags.get("addr:suburb") or "")
        if ilce and ilce.lower() not in line.lower():
            line += f", {ilce}"
        return line[:280]
    return (tags.get("addr:full") or "")[:280]


def is_dental_name(name: str, tags: dict | None = None) -> bool:
    if not name or len(name.strip()) < 4:
        return False
    if SKIP_NAME.search(name):
        return False
    tags = tags or {}
    if tags.get("healthcare") == "dentist" or tags.get("amenity") == "dentist":
        return True
    spec = (tags.get("healthcare:speciality") or "").lower()
    if "dent" in spec:
        return True
    return bool(DENTAL_NAME.search(name))


def fetch_osm() -> list[dict]:
    boxes = (
        (40.05, 28.75, 40.35, 29.35),
        (39.48, 28.07, 40.05, 29.20),
        (39.48, 29.20, 40.05, 30.18),
        (40.05, 29.20, 40.52, 30.18),
    )
    out: list[dict] = []
    seen: set[str] = set()
    for s, w, n, e in boxes:
        q = f"""
        [out:json][timeout:90];
        (
          node["healthcare"="dentist"]({s},{w},{n},{e});
          way["healthcare"="dentist"]({s},{w},{n},{e});
          node["amenity"="dentist"]({s},{w},{n},{e});
          way["amenity"="dentist"]({s},{w},{n},{e});
        );
        out center tags;
        """
        req = urllib.request.Request(
            OVERPASS,
            data=f"data={urllib.parse.quote(q)}".encode(),
            headers={"User-Agent": "BursaApp/1.0 (+https://bursaapp.com)"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=100) as resp:
                data = json.loads(resp.read().decode())
        except Exception:
            time.sleep(2)
            continue
        for el in data.get("elements") or []:
            tags = el.get("tags") or {}
            name = (tags.get("name") or tags.get("name:tr") or "").strip()
            if not is_dental_name(name, tags):
                continue
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lng = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or lng is None:
                continue
            tk = _title_key(name)
            if tk in seen:
                continue
            seen.add(tk)
            band = infer_band(name, tags)
            out.append(
                {
                    "title": name,
                    "title_key": tk,
                    "lat": lat,
                    "lng": lng,
                    "ilce": norm_ilce(tags.get("addr:district") or tags.get("addr:suburb") or ""),
                    "address": addr_from_tags(tags),
                    "phone": (tags.get("phone") or tags.get("contact:phone") or "")[:40],
                    "web": (tags.get("website") or tags.get("contact:website") or "")[:280],
                    "hours_text": (tags.get("opening_hours") or "Randevu ile")[:80],
                    "price_band": band,
                    "blurb": f"OpenStreetMap · {name[:80]}",
                    "tags": ["osm", "dis"],
                    "source": "osm",
                }
            )
        time.sleep(1)
    return out


def fetch_photon() -> list[dict]:
    terms = (
        "ağız diş", "diş kliniği", "diş polikliniği", "ADSM", "dental", "ortodonti",
        "implant diş", "mesam", "bursadent", "dentgroup", "beyaz ışık", "acil diş",
        "diş hekimi", "estetik diş", "gülüş tasarım",
    )
    lats = [40.10, 40.20, 40.30]
    lons = [28.85, 29.00, 29.20]
    out: list[dict] = []
    seen: set[str] = set()
    for term in terms:
        for lat in lats:
            for lon in lons:
                url = PHOTON + "?" + urllib.parse.urlencode(
                    {
                        "q": term,
                        "lat": str(lat),
                        "lon": str(lon),
                        "limit": 30,
                        "bbox": BURSA_BBOX,
                    }
                )
                req = urllib.request.Request(url, headers={"User-Agent": "BursaApp/1.0"})
                try:
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        data = json.loads(resp.read().decode())
                except Exception:
                    continue
                for feat in data.get("features") or []:
                    props = feat.get("properties") or {}
                    name = (props.get("name") or "").strip()
                    if not is_dental_name(name, props):
                        continue
                    coords = (feat.get("geometry") or {}).get("coordinates") or []
                    if len(coords) < 2:
                        continue
                    lng, la = coords[0], coords[1]
                    if not (39.48 <= la <= 40.52 and 28.07 <= lng <= 30.18):
                        continue
                    tk = _title_key(name)
                    if tk in seen:
                        continue
                    seen.add(tk)
                    out.append(
                        {
                            "title": name,
                            "title_key": tk,
                            "lat": la,
                            "lng": lng,
                            "ilce": norm_ilce(
                                props.get("city") or props.get("district") or props.get("county") or ""
                            ),
                            "address": (props.get("street") or "")[:280],
                            "phone": "",
                            "web": "",
                            "hours_text": "Randevu ile",
                            "price_band": infer_band(name, props),
                            "blurb": f"Photon · {name[:80]}",
                            "tags": ["photon", "dis"],
                            "source": "photon",
                        }
                    )
    return out


def save_curated_snapshot(rows: list[dict]) -> None:
    if not rows:
        return
    os.makedirs(DATA, exist_ok=True)
    with open(CURATED_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def load_curated() -> list[dict]:
    if os.path.isfile(CURATED_PATH):
        return json.loads(open(CURATED_PATH, encoding="utf-8").read())
    if os.path.isfile(DENTISTS_PATH):
        old = json.loads(open(DENTISTS_PATH, encoding="utf-8").read())
        if old:
            save_curated_snapshot(old)
            print(f"Curated yedek: {CURATED_PATH} ({len(old)} kayıt)", flush=True)
        return old
    return []


def load_doctors_dental() -> list[dict]:
    if not os.path.isfile(DOCTORS_PATH):
        return []
    out: list[dict] = []
    for raw in json.loads(open(DOCTORS_PATH, encoding="utf-8").read()):
        band = (raw.get("price_band") or "").strip()
        title = (raw.get("title") or "").strip()
        blurb = (raw.get("blurb") or "").lower()
        if band not in ("Diş", "Diş hekimi") and not title.lower().startswith("dt."):
            if "diş" not in blurb and "dis " not in blurb:
                continue
        if not title:
            continue
        if not title.lower().startswith("dt."):
            title = title if "Dt." in title else f"Dt. {title.lstrip('Dr. ')}"
        out.append(
            {
                "slug": raw.get("slug") or slugify(title),
                "title": title,
                "ilce": norm_ilce(raw.get("ilce") or ""),
                "address": raw.get("address") or raw.get("venue_name") or "Bursa",
                "phone": raw.get("phone") or "",
                "web": raw.get("web") or "",
                "hours_text": raw.get("hours_text") or "Randevu ile",
                "price_band": "Klinik",
                "blurb": raw.get("blurb") or f"Diş hekimi · {title}",
                "tags": ["hekim", "dis"],
                "lat": raw.get("lat"),
                "lng": raw.get("lng"),
                "source": "doctor",
            }
        )
    return out


def merge_all(*groups: list[dict]) -> list[dict]:
    by_slug: dict[str, dict] = {}
    by_title: dict[str, str] = {}

    def upsert(raw: dict) -> None:
        c = dict(raw)
        if not is_verified(c):
            return
        title = (c.get("title") or "").strip()
        if not title or not is_dental_name(title, c):
            return
        tk = _title_key(title)
        slug = c.get("slug") or slugify(title)
        base_slug = slug
        i = 2
        while slug in by_slug and by_slug[slug].get("title_key") != tk:
            slug = f"{base_slug}-{i}"
            i += 1
        c["slug"] = slug
        c["title_key"] = tk
        if not c.get("ilce"):
            c["ilce"] = norm_ilce(c.get("address") or "") or "Osmangazi"
        if not c.get("price_band"):
            c["price_band"] = infer_band(title, c)
        if not c.get("hours_text"):
            c["hours_text"] = "Randevu ile"
        if not c.get("blurb"):
            c["blurb"] = f"{c['price_band']} · {title[:100]}"
        tags = list(c.get("tags") or ["dis"])
        if "dis" not in tags:
            tags.append("dis")
        c["tags"] = tags

        if tk in by_title and by_title[tk] in by_slug:
            base = by_slug[by_title[tk]]
        elif slug in by_slug:
            base = by_slug[slug]
        else:
            by_slug[slug] = c
            by_title[tk] = slug
            return

        for k, v in c.items():
            if k in ("source", "title_key"):
                continue
            if v in (None, "", [], {}):
                continue
            if k in ("lat", "lng") and base.get(k) not in (None, ""):
                continue
            base[k] = v
        base["featured"] = bool(c.get("featured") or base.get("featured"))
        merged_tags = list(base.get("tags") or [])
        for t in c.get("tags") or []:
            if t not in merged_tags:
                merged_tags.append(t)
        base["tags"] = merged_tags

    for group in groups:
        for raw in group:
            upsert(raw)

    rows = list(by_slug.values())
    rows.sort(
        key=lambda r: (
            0 if r.get("featured") else 1,
            0 if r.get("price_band") == "Devlet" else 1,
            0 if r.get("price_band") == "Özel" else 2,
            r.get("ilce") or "",
            r.get("title") or "",
        )
    )
    return rows


def load_geocode_cache() -> dict:
    if os.path.isfile(GEOCODE_CACHE):
        return json.loads(open(GEOCODE_CACHE, encoding="utf-8").read())
    return {}


def save_geocode_cache(cache: dict) -> None:
    os.makedirs(DATA, exist_ok=True)
    with open(GEOCODE_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def geocode_rows(rows: list[dict], *, limit: int = 500) -> int:
    cache = load_geocode_cache()
    filled = 0
    for r in rows:
        if r.get("lat") not in (None, "") and r.get("lng") not in (None, ""):
            continue
        if filled >= limit:
            break
        addr = (r.get("address") or "").strip()
        if not addr or addr == "Bursa":
            q = f"{r.get('title')}, {r.get('ilce') or 'Bursa'}, Bursa, Türkiye"
        else:
            q = f"{addr}, {r.get('ilce') or 'Bursa'}, Bursa, Türkiye"
        if q in cache:
            hit = cache[q]
        else:
            url = NOMINATIM + "?" + urllib.parse.urlencode(
                {"q": q, "format": "json", "limit": 1, "countrycodes": "tr"}
            )
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BursaApp/1.0 (+https://bursaapp.com; dentist geocode)"},
            )
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode())
                hit = data[0] if data else None
            except Exception:
                hit = None
            cache[q] = hit
            save_geocode_cache(cache)
            time.sleep(1.05)
        if hit:
            r["lat"] = float(hit["lat"])
            r["lng"] = float(hit["lon"])
            filled += 1
    return filled


def main() -> None:
    do_seed = "--seed" in sys.argv
    do_geocode = "--geocode" in sys.argv
    skip_photon = "--no-photon" in sys.argv

    skip_skrs = "--no-skrs" in sys.argv

    print("MHRS / Sağlık Bakanlığı (resmi ADSM)…", flush=True)
    try:
        mhrs_official = fetch_official_dental(skrs=not skip_skrs)
    except Exception as exc:
        print(f"MHRS uyarı ({exc})", flush=True)
        mhrs_official = []

    print("OSM diş klinikleri…", flush=True)
    try:
        osm = fetch_osm()
        print(f"OSM: {len(osm)}", flush=True)
    except Exception as exc:
        print(f"OSM uyarı ({exc})", flush=True)
        osm = []

    print("Photon araması…", flush=True)
    if skip_photon:
        photon = []
        print("Photon: atlandı (--no-photon)", flush=True)
    else:
        try:
            photon = fetch_photon()
            print(f"Photon: {len(photon)}", flush=True)
        except Exception as exc:
            print(f"Photon uyarı ({exc})", flush=True)
            photon = []

    curated = load_curated()
    doctors = load_doctors_dental()
    print(f"El seçimi: {len(curated)} · Doktor (Diş): {len(doctors)} · MHRS/resmi: {len(mhrs_official)}", flush=True)

    merged = merge_all(mhrs_official, curated, osm, photon, doctors)

    if do_geocode:
        need = sum(1 for r in merged if r.get("lat") in (None, "") and (r.get("address") or r.get("title")))
        print(f"Geocode: {need} kayıt bekliyor…", flush=True)
        n = geocode_rows(merged)
        print(f"Geocode: {n} koordinat eklendi", flush=True)

    os.makedirs(DATA, exist_ok=True)
    clean = []
    for r in merged:
        row = {k: v for k, v in r.items() if k not in ("source", "title_key")}
        if row.get("mhrs_url"):
            row.setdefault("hours_text", "Mesai · MHRS / 182")
        clean.append(row)
    with open(DENTISTS_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    with_coords = sum(1 for r in clean if r.get("lat") not in (None, ""))
    print(f"Yazıldı: {DENTISTS_PATH} ({len(clean)} kayıt · {with_coords} koordinatlı)", flush=True)
    ilce_counts: dict[str, int] = {}
    for r in clean:
        il = r.get("ilce") or "?"
        ilce_counts[il] = ilce_counts.get(il, 0) + 1
    for il in sorted(ilce_counts, key=lambda x: (-ilce_counts[x], x)):
        print(f"  {il}: {ilce_counts[il]}", flush=True)

    if do_seed:
        n_del = purge_orphan_dentists({r["slug"] for r in clean})
        if n_del:
            print(f"DB: {n_del} teyitsiz diş kaydı silindi", flush=True)
        seed = os.path.join(_DIR, "seed_health.py")
        print("DB seed…", flush=True)
        subprocess.run([sys.executable, seed], check=True, cwd=os.path.dirname(_DIR))


if __name__ == "__main__":
    main()
