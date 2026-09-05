#!/usr/bin/env python3
"""Bursa haber videoları — resmi YouTube kanalları RSS (embed sitede kalır).

  python3 BursaApp/bursa_youtube_fetch.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_DIR, "data", "bursa_news_videos.json")
UA = {"User-Agent": "Mozilla/5.0 (compatible; BursaApp/1.0; +https://bursaapp.com)"}
IST = ZoneInfo("Europe/Istanbul")
ATOM = "{http://www.w3.org/2005/Atom}"
YT = "{http://www.youtube.com/xml/schemas/2015}"
MEDIA = "{http://search.yahoo.com/mrss/}"

# Resmi / yerel kanallar — RSS channel_id
CHANNELS: list[tuple[str, str, str]] = [
    ("UCwR4mXD5d5jTbdZUadFfhFg", "Bursaspor", "spor"),
    ("UCXJ77pTF-Io17sp5LrG8rCA", "Bursa Haber TV", "genel"),
    ("UCwFMjH2wEekJd06bjISeWSA", "Bursa Büyükşehir Belediyesi", "sehir"),
]


def _parse_ts(raw: str) -> str:
    if not raw:
        return datetime.now(IST).isoformat(timespec="minutes")
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(IST).isoformat(timespec="minutes")
        return parsedate_to_datetime(raw).astimezone(IST).isoformat(timespec="minutes")
    except Exception:
        return datetime.now(IST).isoformat(timespec="minutes")


def fetch_channel(channel_id: str, channel_name: str, topic: str, *, limit: int = 8) -> list[dict]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read()
    except Exception as e:
        print("yt rss fail", channel_name, e)
        return []
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print("yt xml fail", channel_name, e)
        return []
    author = root.find(f"{ATOM}author/{ATOM}name")
    ch_label = (author.text or channel_name).strip()
    out = []
    for entry in root.findall(f"{ATOM}entry")[:limit]:
        vid_el = entry.find(f"{YT}videoId")
        if vid_el is None or not vid_el.text:
            continue
        vid = vid_el.text.strip()
        title = (entry.findtext(f"{ATOM}title") or "").strip()
        published = entry.findtext(f"{ATOM}published") or ""
        if not title:
            continue
        out.append(
            {
                "id": vid,
                "title": title[:180],
                "channel": ch_label,
                "channel_id": channel_id,
                "topic": topic,
                "published_at": _parse_ts(published),
                "embed_url": f"https://www.youtube-nocookie.com/embed/{vid}",
                "watch_url": f"https://www.youtube.com/watch?v={vid}",
                "thumb": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
            }
        )
    return out


def collect_videos(*, per_channel: int = 6) -> list[dict]:
    seen: set[str] = set()
    items: list[dict] = []
    for cid, name, topic in CHANNELS:
        for v in fetch_channel(cid, name, topic, limit=per_channel):
            if v["id"] in seen:
                continue
            seen.add(v["id"])
            items.append(v)
    items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return items


def run(*, dry: bool = False) -> dict:
    videos = collect_videos()
    payload = {
        "generated_at": datetime.now(IST).isoformat(timespec="minutes"),
        "videos": videos,
    }
    print(f"videos={len(videos)}")
    if dry:
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:2000])
        return payload
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print("wrote", OUT)
    return payload


if __name__ == "__main__":
    run(dry="--dry-run" in sys.argv)
