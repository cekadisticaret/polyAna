#!/usr/bin/env python3
"""Bursa şehir haberleri — Google News RSS + özgün BursaApp özeti.

Kaynak linki korunur; metin birebir kopyalanmaz. Detay sayfası için gövde üretilir.

  python3 BursaApp/bursa_news_fetch.py
  python3 BursaApp/bursa_news_fetch.py --dry-run

Cron (≈2 saatte bir, :20):
  20 */2 * * * cd /root/aiProject && python3 BursaApp/bursa_news_fetch.py >> /tmp/bursa_news.log 2>&1
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from catalog import slugify

OUT = os.path.join(_DIR, "data", "bursa_news.json")
UA = {"User-Agent": "BursaApp/1.0 (+https://bursaapp.com; bursa news desk)"}
IST = ZoneInfo("Europe/Istanbul")
MAX_ARTICLES = 300

COVER_POOL = [
    "/static/visit/ulu-cami.jpg",
    "/static/visit/koza-han.jpg",
    "/static/visit/kale-sokak.jpg",
    "/static/visit/tophane.jpg",
    "/static/visit/golyazi.jpg",
    "/static/visit/cumalikizik.jpg",
    "/static/visit/karacabey-longozu.jpg",
    "/static/visit/iznik-surlar.jpg",
    "/static/visit/hanlar-kapalicarsi.jpg",
    "/static/visit/emir-sultan.jpg",
    "/static/visit/panorama-1326.jpg",
    "/static/visit/mudanya-mutareke-evi.jpg",
]

FEEDS: list[tuple[str, str]] = [
    ("sehir", "Bursa haber"),
    ("sehir", "Bursa belediye"),
    ("ekonomi", "Bursa sanayi ekonomi"),
    ("ulasim", "Bursa trafik ulaşım"),
    ("kultur", "Bursa kültür etkinlik"),
    ("egitim", "Bursa eğitim üniversite"),
    ("saglik", "Bursa sağlık hastane"),
    ("spor", "Bursa spor"),
    ("genel", "Bursa"),
]

DISCLAIMER = (
    "Haberler Google Haberler RSS üzerinden derlenir; başlık ve özet BursaApp editör masasında "
    "yeniden yazılır. Tam metin ve güncel gelişmeler için kaynak bağlantısını kullanın."
)


def _gnews(q: str) -> str:
    return (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode({"q": q, "hl": "tr", "gl": "TR", "ceid": "TR:tr"})
    )


def _get(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _strip(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _clean_title(title: str) -> str:
    t = _strip(title)
    parts = re.split(r"\s+[-–|]\s+", t)
    if len(parts) >= 2 and len(parts[-1]) < 40:
        t = " - ".join(parts[:-1]).strip() or t
    return t[:180]


def _detect_topic(title: str, hint: str, snippet: str) -> str:
    blob = f"{title} {snippet}".lower()
    if any(k in blob for k in ("bursaspor", "timsah", "yeşil beyaz", "yeşil-beyaz")):
        return "spor"
    if any(k in blob for k in ("palut", "taraftarımız", "taraftarimiz", "passolig", "trendyol 1")):
        return "spor"
    if hint and hint in {"sehir", "ekonomi", "ulasim", "kultur", "egitim", "saglik", "spor", "genel"}:
        base = hint
    else:
        base = "genel"
    rules = [
        ("ulasim", ("trafik", "metro", "bursaray", "otobüs", "otoyol", "ulaşım", "kaza")),
        ("ekonomi", ("fabrika", "sanayi", "ihracat", "yatırım", "işletme", "ekonomi", "organize")),
        ("kultur", ("konser", "tiyatro", "festival", "sergi", "müze", "kültür", "etkinlik")),
        ("egitim", ("okul", "üniversite", "öğrenci", "meb", "eğitim", "dershane")),
        ("saglik", ("hastane", "sağlık", "doktor", "ameliyat", "aşı")),
        ("sehir", ("belediye", "başkan", "meclis", "ilçe", "osmangazi", "nilüfer", "yıldırım")),
        ("spor", ("maç", "takım", "lig", "futbol", "basketbol")),
    ]
    for topic, keys in rules:
        if any(k in blob for k in keys):
            return topic
    return base


def _pick_cover(uid: str, topic: str) -> str:
    if not COVER_POOL:
        return ""
    bump = {
        "sehir": 0,
        "ekonomi": 2,
        "ulasim": 4,
        "kultur": 6,
        "egitim": 8,
        "saglik": 10,
        "spor": 1,
        "genel": 3,
    }.get(topic, 0)
    idx = (int(uid[:8], 16) + bump) % len(COVER_POOL)
    return COVER_POOL[idx]


def _rewrite_blurb(title: str, source: str, topic: str, snippet: str) -> str:
    t = _clean_title(title)
    src = source or "yerel basın"
    lead = snippet[:220].rstrip(".,; ") + "…" if snippet and len(snippet) > 40 else ""
    topic_lines = {
        "sehir": (
            f"Şehir masası: {src} “{t}” başlığını öne çıkardı. "
            f"BursaApp notu — belediye ve ilçe kararları günlük hayatı doğrudan etkiler; "
            f"resmi duyuru gelmeden spekülasyonu kesin bilgi sanmayın."
        ),
        "ekonomi": (
            f"Ekonomi hattı: {src} “{t}” diye aktardı. "
            f"Sanayi ve istihdam Bursa'nın omurgası; rakam ve resmi açıklamayı birlikte okuyun."
        ),
        "ulasim": (
            f"Ulaşım: {src} “{t}” satırını işledi. "
            f"Trafik ve toplu taşıma planınızı etkileyebilir — alternatif güzergâhları not edin."
        ),
        "kultur": (
            f"Kültür / etkinlik: {src} “{t}” duyurdu. "
            f"Bilet ve saat için kaynağı teyit edin; BursaApp takviminde de benzer etkinliklere bakın."
        ),
        "egitim": (
            f"Eğitim: {src} “{t}” gündeme taşıdı. "
            f"Okul ve üniversite duyurularında resmi kanalları esas alın."
        ),
        "saglik": (
            f"Sağlık: {src} “{t}” başlığını verdi. "
            f"Tıbbi karar için haber metni yeterli değildir; uzman ve resmi kurumları dinleyin."
        ),
        "spor": (
            f"Spor: {src} “{t}” yazdı. "
            f"Bursaspor özelinde ayrıntılı masamız /bursaspor sayfasında."
        ),
        "genel": (
            f"Gündem: {src} “{t}” notunu düştü. "
            f"BursaApp özeti — şehir nabzını buradan süzüyoruz; ayrıntı için kaynağa gidin."
        ),
    }
    base = topic_lines.get(topic, topic_lines["genel"])
    if lead and topic != "spor":
        return f"{lead} {base}"
    return base


def _build_body(title: str, source: str, topic: str, snippet: str, url: str) -> dict:
    t = _clean_title(title)
    src = source or "kaynak site"
    snippet = _strip(snippet)[:480]
    ilce_hit = None
    for name in ("Osmangazi", "Nilüfer", "Yıldırım", "Mudanya", "Gemlik", "İnegöl", "İznik", "Karacabey"):
        if name.lower() in t.lower() or name.lower() in snippet.lower():
            ilce_hit = name
            break

    summary_bits = []
    if snippet:
        summary_bits.append(
            f"Basın tarafında öne çıkan satır şu: {snippet[:320]}{'…' if len(snippet) > 320 else ''}"
        )
    summary_bits.append(
        f"Başlık “{t}” — {src} üzerinden Bursa gündemine yansıdı. "
        f"BursaApp bu satırı şehir rehberi kullanıcıları için bağlama oturtur; haber metnini birebir aktarmayız."
    )

    local_bits = []
    if ilce_hit:
        local_bits.append(
            f"Haberde {ilce_hit} vurgusu var. İlçe bazlı ulaşım, yoğunluk ve yerel duyuruları "
            f"ayrı takip etmek faydalı — özellikle trafik ve belediye kararlarında."
        )
    else:
        local_bits.append(
            "Bursa'nın 17 ilçesi aynı başlığı farklı etkileyebilir. "
            "Resmi belediye kanalları ve valilik duyurularıyla çapraz kontrol edin."
        )
    topic_notes = {
        "ekonomi": "OSB ve sanayi hattı şehir ekonomisinin kalbi; yatırım haberlerinde süre ve istihdam rakamlarına dikkat.",
        "ulasim": "Bursaray, metro ve ana arterlerdeki değişiklikler günlük rotayı etkiler — planınızı güncel tutun.",
        "kultur": "Merinos, Kültürpark ve sahil hattı etkinlikleri hafta sonu planına eklenebilir.",
        "egitim": "Okul takvimi ve sınav dönemlerinde servis/trafik yoğunluğu artabilir.",
        "saglik": "Acil durumda 112; randevu ve tedavi kararı için hastane/resmi hatları kullanın.",
        "spor": "Bursaspor maç ve transfer gündemi için yeşil-beyaz masamız ayrı güncellenir.",
    }
    if topic in topic_notes:
        local_bits.append(topic_notes[topic])

    source_bits = [
        f"Tam metin ve güncel gelişmeler için orijinal kaynağa gidin: {src}.",
        "BursaApp haber masası birkaç saatte bir yenilenir; kritik duyurularda resmi kurum sitelerini esas alın.",
    ]

    sections = [
        {"h2": "Ne oldu?", "paras": summary_bits},
        {"h2": "Bursa bağlamı", "paras": local_bits},
        {"h2": "Kaynak", "paras": source_bits},
    ]
    body_plain = " ".join(summary_bits + local_bits)[:500]
    return {"sections": sections, "body_plain": body_plain, "source_url": url}


def fetch_rss_items(url: str, topic_hint: str) -> list[dict]:
    try:
        raw = _get(url)
    except Exception as e:
        print("rss fail", url, e)
        return []
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print("xml fail", url, e)
        return []
    out = []
    for it in root.findall(".//item"):
        title = _clean_title(it.findtext("title") or "")
        link = (it.findtext("link") or "").strip()
        desc = _strip(it.findtext("description") or "")
        source_el = it.find("source")
        source = (source_el.text or "").strip() if source_el is not None else ""
        if not source:
            source = "Google Haberler"
        pub = it.findtext("pubDate") or ""
        try:
            ts = parsedate_to_datetime(pub).astimezone(IST).isoformat(timespec="minutes")
        except Exception:
            ts = datetime.now(IST).isoformat(timespec="minutes")
        if not title or not link:
            continue
        low = title.lower()
        if "bursa" not in low and "bursa" not in desc.lower():
            continue
        topic = _detect_topic(title, topic_hint, desc)
        uid = hashlib.sha1(f"{title}|{source}|{link}".encode()).hexdigest()[:12]
        slug = f"{slugify(title)[:52]}-{uid[:8]}".strip("-")
        blurb = _rewrite_blurb(title, source, topic, desc)
        body = _build_body(title, source, topic, desc, link)
        out.append(
            {
                "id": uid,
                "slug": slug,
                "title": title,
                "source": source,
                "url": link,
                "published_at": ts,
                "topic": topic,
                "blurb": blurb,
                "img_url": _pick_cover(uid, topic),
                "sections": body["sections"],
                "body_plain": body["body_plain"],
            }
        )
    return out


def collect_articles(limit: int = 40) -> list[dict]:
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    items: list[dict] = []
    for topic_hint, query in FEEDS:
        url = _gnews(query)
        for it in fetch_rss_items(url, topic_hint):
            uid = it["id"]
            tkey = re.sub(r"\W+", "", it["title"].lower())[:56]
            if uid in seen_ids or tkey in seen_titles:
                continue
            seen_ids.add(uid)
            seen_titles.add(tkey)
            items.append(it)
        time.sleep(0.35)
    items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return items[:limit]


def merge_archive(existing: list[dict], fresh: list[dict]) -> list[dict]:
    by_id = {a["id"]: a for a in existing if a.get("id")}
    for a in fresh:
        by_id[a["id"]] = a
    merged = list(by_id.values())
    merged.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return merged[:MAX_ARTICLES]


def run(*, dry: bool = False) -> dict:
    existing = []
    if os.path.isfile(OUT):
        try:
            existing = json.loads(open(OUT, encoding="utf-8").read()).get("articles") or []
        except Exception:
            existing = []
    fresh = collect_articles(48)
    articles = merge_archive(existing, fresh)
    payload = {
        "generated_at": datetime.now(IST).isoformat(timespec="minutes"),
        "disclaimer": DISCLAIMER,
        "articles": articles,
    }
    print(f"fresh={len(fresh)} total={len(articles)}")
    if dry:
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:2500])
        return payload
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("wrote", OUT)
    try:
        from bursa_youtube_fetch import run as yt_run

        yt_run()
    except Exception as e:
        print("youtube skip", e)
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry=bool(args.dry_run))


if __name__ == "__main__":
    main()
