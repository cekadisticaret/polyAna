#!/usr/bin/env python3
"""Doruk Sağlık Grubu hekim kadrosu — doruktip.com → doctors.json + doruk_doctors.json.

  python3 BursaApp/doruk_doctors_fetch.py
  python3 BursaApp/doruk_doctors_fetch.py --limit 5   # test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from enrich_doctors import fetch_html, strip_html

LIST_URL = "https://doruktip.com/hekimlerimiz.html"
DORUK_JSON = os.path.join(_DIR, "data", "doruk_doctors.json")
DOCTORS_JSON = os.path.join(_DIR, "data", "doctors.json")

HOSPITAL_BLURB = {
    "doruk-hastanesi": "Doruk Nilüfer",
    "doruk-cekirge": "Doruk Çekirge",
    "doruk-yildirim": "Doruk Yıldırım",
}


def map_hospital(text: str) -> str:
    t = (text or "").lower()
    if "yıldırım" in t or "yildirim" in t:
        return "doruk-yildirim"
    if "çekirge" in t or "cekirge" in t:
        return "doruk-cekirge"
    if "nilüfer" in t or "nilufer" in t:
        return "doruk-hastanesi"
    if "bursa hastanesi" in t:
        return "doruk-cekirge"
    return "doruk-hastanesi"


def short_branch(raw: str) -> str:
    b = (raw or "").strip()
    if not b:
        return "Poliklinik"
    low = b.lower()
    if "diyetisyen" in low:
        return "Diyetisyen"
    if "psikolog" in low:
        return "Klinik psikoloji"
    if "diş hekimi" in low:
        return "Diş hekimi"
    if "dil ve konuşma" in low:
        return "Dil ve konuşma terapisi"
    b = re.sub(r"\s+(uzmanı|uzman)\s*$", "", b, flags=re.I).strip()
    subs = (
        ("Kadın Hastalıkları ve Doğum", "Kadın doğum"),
        ("Çocuk Sağlığı ve Hastalıkları", "Çocuk sağlığı"),
        ("Kalp ve Damar Cerrahisi", "Kalp cerrahisi"),
        ("Göz Sağlığı ve Hastalıkları", "Göz"),
        ("Kulak Burun Boğaz", "KBB"),
        ("Deri ve Zührevi Hastalıklar", "Dermatoloji"),
        ("Fizik Tedavi ve Rehabilitasyon", "Fizik tedavi"),
        ("Enfeksiyon Hastalıkları", "Enfeksiyon"),
        ("Beyin ve Sinir Cerrahisi", "Beyin cerrahisi"),
        ("Göğüs Hastalıkları", "Göğüs"),
        ("Genel Cerrahi", "Genel cerrahi"),
        ("Kardiyoloji", "Kalp"),
        ("Anestezi ve Reanimasyon", "Anestezi"),
        ("Acil Hekimi", "Acil"),
        ("Radyoloji", "Radyoloji"),
        ("Üroloji", "Üroloji"),
        ("Nöroloji", "Nöroloji"),
        ("Ortopedi", "Ortopedi"),
        ("Psikiyatri", "Psikiyatri"),
        ("Onkoloji", "Onkoloji"),
        ("Gastroenteroloji", "Gastroenteroloji"),
        ("Göğüs Cerrahisi", "Göğüs cerrahisi"),
        ("Çocuk Cerrahisi", "Çocuk cerrahisi"),
        ("Plastik", "Plastik cerrahi"),
    )
    for old, new in subs:
        if old.lower() in low:
            return new
    return b[:48] if len(b) > 48 else b


def list_links(html: str) -> list[tuple[str, str]]:
    import html as html_mod

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'<a[^>]+href="(https://doruktip\.com/hekim/\d+/[^"]+\.html)"[^>]*>([^<]+)</a>',
        html,
    ):
        url, label = m.group(1), html_mod.unescape(m.group(2).strip())
        if url in seen or len(label) < 4:
            continue
        seen.add(url)
        out.append((label, url))
    return out


def profile_photo(html: str) -> str:
    og = re.search(r'property="og:image"\s+content="([^"]+)"', html)
    if og:
        url = og.group(1)
        if "-mobile3" in url:
            return url.replace("-mobile3", "")
        return url
    m = re.search(r'(https://doruktip\.com/paket/Fotograflar_tr/[^"\']+\.(?:jpe?g|png))', html)
    return m.group(1) if m else ""


def parse_profile(html: str, profile_url: str) -> dict | None:
    import html as html_mod

    h1 = re.search(r"<h1[^>]*>([^<]+)", html)
    if not h1:
        return None
    title = html_mod.unescape(h1.group(1)).strip()
    rows: dict[str, str] = {}
    for m in re.finditer(
        r'<td class="t700">([^<]+)</td>\s*<td>:</td>\s*<td>([^<]*)</td>',
        html,
    ):
        rows[html_mod.unescape(m.group(1)).strip()] = html_mod.unescape(m.group(2)).strip()
    branch_raw = rows.get("Branşı") or rows.get("Bransı") or ""
    hosp_raw = rows.get("Görev Yaptığı Hastaneler") or ""
    about = ""
    for m in re.finditer(r'<div class="col-md-12 baslik"><span>([^<]+)</span></div>\s*<div class="col-md-12">\s*<div[^>]*>\s*<ul class="iconlist">(.*?)</ul>', html, re.S):
        if "ilgi" in m.group(1).lower():
            about = strip_html(m.group(2))[:500]
            break
    slug_part = profile_url.rstrip("/").split("/")[-1].replace(".html", "")
    slug = f"doruk-{slug_part.replace('_', '-')}"[:80]
    hospital = map_hospital(hosp_raw)
    branch = short_branch(branch_raw)
    return {
        "slug": slug,
        "title": title,
        "hospital": hospital,
        "price_band": branch,
        "web": profile_url,
        "blurb": f"{branch} · {HOSPITAL_BLURB.get(hospital, 'Doruk')} resmi kadro.",
        "name": title,
        "profile_url": profile_url,
        "img_url": profile_photo(html),
        "department": branch_raw,
        "hospitals_text": hosp_raw,
        "about": about,
        "source": "doruktip",
    }


def merge_doctors_json(rows: list[dict]) -> tuple[int, int]:
    existing: list[dict] = []
    if os.path.isfile(DOCTORS_JSON):
        existing = json.loads(open(DOCTORS_JSON, encoding="utf-8").read())
    by_slug = {r["slug"]: r for r in existing if r.get("slug")}
    new = upd = 0
    for row in rows:
        seed = {k: row[k] for k in ("slug", "title", "hospital", "price_band", "web", "blurb") if k in row}
        if row["slug"] in by_slug:
            by_slug[row["slug"]].update(seed)
            upd += 1
        else:
            by_slug[row["slug"]] = seed
            new += 1
    merged = list(by_slug.values())
    merged.sort(key=lambda r: (r.get("hospital") or "", r.get("title") or ""))
    with open(DOCTORS_JSON, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return new, upd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="test için üst sınır")
    args = ap.parse_args()

    html = fetch_html(LIST_URL, referer=LIST_URL)
    if not html:
        print("liste alınamadı")
        sys.exit(1)
    links = list_links(html)
    if args.limit:
        links = links[: args.limit]
    print(f"profil sayısı: {len(links)}")

    catalog: list[dict] = []
    for i, (_label, url) in enumerate(links, 1):
        time.sleep(0.15)
        ph = fetch_html(url, referer=LIST_URL)
        if not ph:
            print("skip", url)
            continue
        row = parse_profile(ph, url)
        if not row:
            print("parse fail", url)
            continue
        catalog.append(row)
        if i % 25 == 0:
            print(f"  {i}/{len(links)}")

    os.makedirs(os.path.dirname(DORUK_JSON), exist_ok=True)
    with open(DORUK_JSON, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
        f.write("\n")
    new, upd = merge_doctors_json(catalog)
    print(f"doruk={len(catalog)} doctors.json new={new} upd={upd}")


if __name__ == "__main__":
    main()
