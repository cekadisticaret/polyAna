#!/usr/bin/env python3
"""Bursaspor haber + maç masası (özgün özet, birebir kopya yok).

Kaynak: Google News RSS (+ isteğe bağlı spor RSS). Başlık/özetten ana fikir alınır,
BursaApp dilinde yeniden yazılır; kaynak linki korunur.

  python3 BursaApp/bursaspor_feed.py
  python3 BursaApp/bursaspor_feed.py --dry-run

Cron (İST 06:00 / 18:00 ≈ UTC 03:00 / 15:00):
  0 3,15 * * * cd /root/aiProject && python3 BursaApp/bursaspor_feed.py >> /tmp/bursaspor_feed.log 2>&1
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

OUT = os.path.join(_DIR, "data", "bursaspor_feed.json")
STANDINGS = os.path.join(_DIR, "data", "bursaspor_standings.json")
COVER_DIR = os.path.join(_DIR, "static", "cache", "bursaspor")
COVER_MANIFEST = os.path.join(COVER_DIR, "manifest.json")
UA = {"User-Agent": "BursaApp/1.0 (+https://bursaapp.com; bursaspor desk)"}
IST = ZoneInfo("Europe/Istanbul")


def _cover_pool() -> list[str]:
    if os.path.isfile(COVER_MANIFEST):
        try:
            rows = json.loads(open(COVER_MANIFEST, encoding="utf-8").read())
            if isinstance(rows, list) and rows:
                return [str(x) for x in rows if x]
        except Exception:
            pass
    if not os.path.isdir(COVER_DIR):
        return []
    out = []
    for name in sorted(os.listdir(COVER_DIR)):
        if name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            out.append(f"/static/cache/bursaspor/{name}")
    return out


def _pick_cover(uid: str, topic: str, pool: list[str]) -> str:
    if not pool:
        return ""
    # konu bazlı kaydırma + id hash
    bump = {"mac": 0, "transfer": 2, "yonetim": 4, "kadro": 6, "genel": 1}.get(topic, 0)
    idx = (int(uid[:8], 16) + bump) % len(pool)
    return pool[idx]

def _gnews(q: str) -> str:
    return (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode({"q": q, "hl": "tr", "gl": "TR", "ceid": "TR:tr"})
    )


FEEDS = [
    _gnews("Bursaspor"),
    _gnews("Bursaspor 1. Lig"),
    _gnews("Bursaspor maç"),
]


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
    # "Başlık - Kaynak" kalıbını sadeleştir
    parts = re.split(r"\s+[-–|]\s+", t)
    if len(parts) >= 2 and len(parts[-1]) < 40:
        t = " - ".join(parts[:-1]).strip() or t
    return t[:180]


def _topic(title: str) -> str:
    low = title.lower()
    if any(k in low for k in ("transfer", "imza", "bonservis", "kiralık", "göz dik")):
        return "transfer"
    if any(k in low for k in ("maç", "gol", "skor", "galibiyet", "beraberlik", "yenilgi", "fikstür")):
        return "mac"
    if any(k in low for k in ("başkan", "yönetim", "destek", "sponsor", "milyon")):
        return "yonetim"
    if any(k in low for k in ("antrenman", "kamp", "kadrodan", "sakat")):
        return "kadro"
    return "genel"


def rewrite_blurb(title: str, source: str, topic: str) -> str:
    """Kaynak metni kopyalamadan BursaApp masası dili."""
    t = _clean_title(title)
    src = source or "spor basını"
    # Sayısal ipuçları
    money = re.search(r"(\d+[\.,]?\d*)\s*(milyon|mn)\s*(tl|lira)?", t, re.I)
    person = None
    m = re.search(
        r"(Enes Çelik|Metehan Mimaroğlu|Aboubakar|[A-ZÇĞİÖŞÜ][a-zçğıöşü]+ [A-ZÇĞİÖŞÜ][a-zçğıöşü]+)",
        t,
    )
    if m:
        person = m.group(1)

    if topic == "transfer":
        who = f" Gündemde {person} adı geçiyor." if person else ""
        return (
            f"Transfer masasında hareket var: “{t}” başlığıyla {src} gündeme taşıdı.{who} "
            f"BursaApp notu — resmi açıklama gelmeden spekülasyonu skor gibi okumayın; "
            f"kadro planı ve bütçe çerçevesi netleşince buradan takip edin."
        )
    if topic == "mac":
        return (
            f"Saha tarafı: {src} “{t}” diye aktardı. "
            f"Bizim okuma — Timsah’ın 1. Lig temposunda puan kaybı/kazancı kadar "
            f"iç saha ritmi ve deplasman disiplini kritik; fikstür kartındaki sonraki rakibe bakın."
        )
    if topic == "yonetim":
        ekstra = ""
        if money:
            ekstra = f" Haberde {money.group(0)} bandında bir destek/jest vurgusu var."
        who = f" {person} konuşması öne çıkıyor." if person else ""
        return (
            f"Kulüp cephesi: {src} “{t}” diyerek yönetime dair not düştü.{who}{ekstra} "
            f"BursaApp yorumu — taraftar moralini yükselten haberler güzel; "
            f"kalıcı etki için saha sonuçları ve şeffaf iletişim birlikte yürümeli."
        )
    if topic == "kadro":
        return (
            f"Kadro / hazırlık: {src} “{t}” satırını işledi. "
            f"Masamızdan — sakatlık ve idman notlarını abartmadan takip edin; "
            f"asıl sinyal maç günü 11’i ve ilk 20 dakikadaki tempo."
        )
    return (
        f"Günün notu ({src}): “{t}”. "
        f"BursaApp özeti — yeşil-beyaz gündemi buradan süzüyoruz; "
        f"detay için kaynağa bakın, biz skor ve fikstürle çapraz okuyoruz."
    )


def fetch_rss_items(url: str, covers: list[str] | None = None) -> list[dict]:
    covers = covers if covers is not None else _cover_pool()
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
        if "bursaspor" not in title.lower() and "timsah" not in title.lower():
            # Google query already filtered; still keep
            pass
        link = (it.findtext("link") or "").strip()
        desc = _strip(it.findtext("description") or "")
        source_el = it.find("source")
        source = (source_el.text or "").strip() if source_el is not None else ""
        if not source:
            # title may include source
            source = "Google Haberler"
        pub = it.findtext("pubDate") or ""
        ts = None
        try:
            ts = parsedate_to_datetime(pub).astimezone(IST).isoformat(timespec="minutes")
        except Exception:
            ts = datetime.now(IST).isoformat(timespec="minutes")
        if not title or not link:
            continue
        topic = _topic(title)
        uid = hashlib.sha1(f"{title}|{source}".encode()).hexdigest()[:12]
        out.append(
            {
                "id": uid,
                "title": title,
                "source": source,
                "url": link,
                "published_at": ts,
                "topic": topic,
                "blurb": rewrite_blurb(title, source, topic),
                "img_url": _pick_cover(uid, topic, covers),
            }
        )
    return out


def load_standings() -> list[dict]:
    try:
        return json.loads(open(STANDINGS, encoding="utf-8").read())
    except Exception:
        return []


def bursaspor_row(standings: list[dict]) -> dict | None:
    for r in standings:
        if "Bursaspor" in str(r.get("team") or ""):
            return r
    return None


def build_desk(db) -> dict:
    """Maç masası: son sonuç + sıradaki maç + form + puan durumu yorumu."""
    from models import SportMatch

    rows = (
        db.query(SportMatch)
        .filter(SportMatch.club == "bursaspor", SportMatch.season == "2026-27")
        .order_by(SportMatch.kickoff_at.asc().nullslast(), SportMatch.week.asc().nullslast())
        .all()
    )
    played = [m for m in rows if m.home_score is not None and m.away_score is not None]
    upcoming = [m for m in rows if m.home_score is None or m.away_score is None]

    def label(m) -> str:
        return f"{m.home_team}–{m.away_team}"

    def result_line(m) -> str:
        hs, aws = int(m.home_score or 0), int(m.away_score or 0)
        us_home = bool(m.is_home)
        us = hs if us_home else aws
        them = aws if us_home else hs
        if us > them:
            tag = "Galibiyet"
        elif us == them:
            tag = "Beraberlik"
        else:
            tag = "Yenilgi"
        where = "iç saha" if us_home else "deplasman"
        return f"{tag} ({where}): {m.home_team} {hs}–{aws} {m.away_team}"

    last = played[-1] if played else None
    nxt = upcoming[0] if upcoming else None

    # form last 5
    form = []
    for m in played[-5:]:
        hs, aws = int(m.home_score or 0), int(m.away_score or 0)
        us = hs if m.is_home else aws
        them = aws if m.is_home else hs
        form.append("G" if us > them else ("B" if us == them else "M"))

    st = bursaspor_row(load_standings())
    stand_txt = ""
    if st:
        stand_txt = (
            f"Puan durumunda {st.get('pos')}. sıradayız "
            f"({st.get('p')}O {st.get('w')}G {st.get('d')}B {st.get('l')}M · {st.get('pts')} puan)."
        )

    form_txt = "Son 5: " + "-".join(form) if form else "Henüz yeterli lig örneği yok."
    last_txt = result_line(last) if last else "Oynanmış maç kaydı sınırlı."
    next_txt = ""
    if nxt:
        when = nxt.kickoff_at.astimezone(IST).strftime("%d.%m.%Y %H:%M") if nxt.kickoff_at else "tarih netleşecek"
        side = "Timsah Arena / iç saha" if nxt.is_home else "deplasman"
        next_txt = (
            f"Sırada: {label(nxt)} · {when} · {side}. "
            f"{'Ev sahibi avantajını tempo ve erken gol ile çevirmek lazım.' if nxt.is_home else 'Deplasmanda kompakt savunma + ikinci toplar kritik.'}"
        )

    analysis = (
        f"BursaApp Maç Masası — {datetime.now(IST).strftime('%d.%m.%Y %H:%M')}. "
        f"{stand_txt} {form_txt} Son not: {last_txt}. {next_txt} "
        f"Yorumumuz: 1. Lig’de üst sıra için istikrar şart; tek maçlık heyecanı sezon planına kurban etmeyin."
    ).strip()

    preview = ""
    if nxt:
        opp = nxt.away_team if nxt.is_home else nxt.home_team
        preview = (
            f"Önizleme — rakip {opp}. "
            f"{'Kendi sahamızda taraftar ritmi + erken baskı' if nxt.is_home else 'Deplasman set oyunu ve set parçaları'} "
            f"planın omurgası olmalı. Bilet / Passolig için resmi kanalları kullanın."
        )

    review = ""
    if last:
        review = (
            f"Maç arkası — {result_line(last)}. "
            f"Bizden satır: Skoru abartmadan okuyun; bir sonraki 90’da aynı temponun sürüp sürmediğine bakın."
        )

    return {
        "updated_at": datetime.now(IST).isoformat(timespec="minutes"),
        "analysis": analysis,
        "preview": preview,
        "review": review,
        "form": form,
        "standings_note": stand_txt,
        "next_match": {
            "home": nxt.home_team if nxt else "",
            "away": nxt.away_team if nxt else "",
            "kickoff": nxt.kickoff_at.astimezone(IST).strftime("%d.%m.%Y %H:%M") if nxt and nxt.kickoff_at else "",
            "is_home": bool(nxt.is_home) if nxt else None,
            "venue": (nxt.venue or "") if nxt else "",
        }
        if nxt
        else None,
        "last_match": {
            "home": last.home_team,
            "away": last.away_team,
            "home_score": last.home_score,
            "away_score": last.away_score,
            "is_home": bool(last.is_home),
        }
        if last
        else None,
    }


def collect_news(limit: int = 12) -> list[dict]:
    covers = _cover_pool()
    seen = set()
    items: list[dict] = []
    for url in FEEDS:
        for it in fetch_rss_items(url, covers):
            key = it["id"]
            if key in seen:
                continue
            # başlık benzerliği
            tkey = re.sub(r"\W+", "", it["title"].lower())[:48]
            if tkey in seen:
                continue
            seen.add(key)
            seen.add(tkey)
            items.append(it)
        time.sleep(0.4)
    # yeni önce
    items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return items[:limit]


def run(*, dry: bool = False) -> dict:
    from models import SessionLocal, init_db

    init_db()
    news = collect_news(14)
    db = SessionLocal()
    try:
        desk = build_desk(db)
    finally:
        db.close()

    payload = {
        "generated_at": datetime.now(IST).isoformat(timespec="minutes"),
        "desk": desk,
        "news": news,
    }
    print(f"news={len(news)} desk_ok={bool(desk.get('analysis'))}")
    if dry:
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:1500])
        return payload
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("wrote", OUT)
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry=bool(args.dry_run))


if __name__ == "__main__":
    main()
