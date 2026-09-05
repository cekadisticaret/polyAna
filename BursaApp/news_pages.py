"""Bursa haber JSON — okuma, filtre, sayfalama."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
NEWS_PATH = os.path.join(_DIR, "data", "bursa_news.json")
IST = ZoneInfo("Europe/Istanbul")

NEWS_TOPICS: dict[str, str] = {
    "sehir": "Şehir",
    "ekonomi": "Ekonomi",
    "ulasim": "Ulaşım",
    "kultur": "Kültür",
    "egitim": "Eğitim",
    "saglik": "Sağlık",
    "spor": "Spor",
    "genel": "Gündem",
}


def load_news_feed() -> dict:
    if not os.path.isfile(NEWS_PATH):
        return {"generated_at": "", "articles": [], "disclaimer": ""}
    try:
        data = json.loads(open(NEWS_PATH, encoding="utf-8").read())
        if isinstance(data, dict):
            data.setdefault("articles", [])
            return data
    except Exception:
        pass
    return {"generated_at": "", "articles": [], "disclaimer": ""}


def _parse_ts(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(IST)
    except Exception:
        return None


def fmt_news_date(raw: str) -> str:
    dt = _parse_ts(raw)
    if not dt:
        return raw or ""
    now = datetime.now(IST)
    diff = now - dt
    if diff.total_seconds() < 3600:
        m = max(1, int(diff.total_seconds() // 60))
        return f"{m} dk önce"
    if diff.total_seconds() < 86400:
        h = max(1, int(diff.total_seconds() // 3600))
        return f"{h} saat önce"
    if diff.days < 7:
        return f"{diff.days} gün önce"
    return dt.strftime("%d.%m.%Y · %H:%M")


def infer_topic(art: dict) -> str:
    """RSS ipucu yanlış kaldıysa başlık/özetten düzelt (Palut, Bursaspor vb.)."""
    blob = f"{art.get('title') or ''} {art.get('blurb') or ''}".lower()
    if any(
        k in blob
        for k in (
            "bursaspor",
            "timsah",
            "yeşil beyaz",
            "yeşil-beyaz",
            "palut",
            "passolig",
            "taraftarımız",
            "taraftarimiz",
            "1. lig",
            "trendyol 1",
        )
    ):
        return "spor"
    return art.get("topic") or "genel"


def decorate_article(art: dict) -> dict:
    out = dict(art)
    topic = infer_topic(out)
    out["topic"] = topic
    out["topic_label"] = NEWS_TOPICS.get(topic, "Gündem")
    out["date_label"] = fmt_news_date(out.get("published_at") or "")
    out["path"] = f"/haber/{out.get('slug') or out.get('id')}"
    return out


def list_articles(
    *,
    topic: str = "",
    q: str = "",
    page: int = 1,
    per_page: int = 12,
) -> tuple[list[dict], int, dict]:
    feed = load_news_feed()
    rows = [decorate_article(a) for a in (feed.get("articles") or [])]
    if topic and topic in NEWS_TOPICS:
        rows = [a for a in rows if (a.get("topic") or "genel") == topic]
    if q:
        like = q.strip().lower()
        rows = [
            a
            for a in rows
            if like in (a.get("title") or "").lower()
            or like in (a.get("blurb") or "").lower()
            or like in (a.get("source") or "").lower()
        ]
    total = len(rows)
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 12), 48))
    start = (page - 1) * per_page
    page_rows = rows[start : start + per_page]
    pages = max(1, (total + per_page - 1) // per_page)
    return page_rows, total, {
        "page": page,
        "pages": pages,
        "per_page": per_page,
        "generated_at": feed.get("generated_at") or "",
        "disclaimer": feed.get("disclaimer") or "",
    }


def get_article(slug: str) -> dict | None:
    slug = (slug or "").strip()
    if not slug:
        return None
    feed = load_news_feed()
    for raw in feed.get("articles") or []:
        if raw.get("slug") == slug or raw.get("id") == slug:
            art = decorate_article(raw)
            art["generated_at"] = feed.get("generated_at") or ""
            art["disclaimer"] = feed.get("disclaimer") or ""
            return art
    return None


def related_articles(art: dict, *, limit: int = 4) -> list[dict]:
    topic = art.get("topic") or "genel"
    sid = art.get("id")
    out = []
    for raw in load_news_feed().get("articles") or []:
        if raw.get("id") == sid:
            continue
        dec = decorate_article(raw)
        if dec.get("topic") != topic:
            continue
        out.append(dec)
        if len(out) >= limit:
            break
    if len(out) < limit:
        seen = {sid} | {a["id"] for a in out}
        for raw in load_news_feed().get("articles") or []:
            if raw.get("id") in seen:
                continue
            out.append(decorate_article(raw))
            if len(out) >= limit:
                break
    return out


def headline_articles(*, limit: int = 6) -> list[dict]:
    rows, _, _ = list_articles(page=1, per_page=limit)
    return rows


def load_bursaspor_sidebar() -> dict:
    """Hero sağ panel — maç + yeşil-beyaz gündem."""
    path = os.path.join(_DIR, "data", "bursaspor_feed.json")
    out: dict = {"next_match": None, "headlines": [], "form": []}
    if not os.path.isfile(path):
        return out
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return out
    desk = data.get("desk") or {}
    out["next_match"] = desk.get("next_match")
    out["form"] = desk.get("form") or []
    for raw in (data.get("news") or [])[:5]:
        out["headlines"].append(
            {
                "title": raw.get("title") or "",
                "url": raw.get("url") or "",
                "topic": raw.get("topic") or "genel",
                "date_label": fmt_news_date(raw.get("published_at") or ""),
            }
        )
    return out


def load_bursaspor_videos(*, limit: int = 6) -> list[dict]:
    rows = []
    for v in load_videos():
        if v.get("channel") == "Bursaspor" or v.get("topic") == "spor":
            rows.append(v)
    return rows[:limit]


def load_videos() -> list[dict]:
    path = os.path.join(_DIR, "data", "bursa_news_videos.json")
    if not os.path.isfile(path):
        return []
    try:
        data = json.loads(open(path, encoding="utf-8").read())
        rows = data.get("videos") or []
        for v in rows:
            v.setdefault("embed_url", f"https://www.youtube-nocookie.com/embed/{v.get('id', '')}")
            v.setdefault("thumb", f"https://img.youtube.com/vi/{v.get('id', '')}/hqdefault.jpg")
            v["topic_label"] = NEWS_TOPICS.get(v.get("topic") or "genel", "Gündem")
            v["date_label"] = fmt_news_date(v.get("published_at") or "")
        return rows
    except Exception:
        return []


def _tokenize(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9çğıöşü]{3,}", (s or "").lower())}


def match_video(article: dict | None, videos: list[dict] | None = None) -> dict | None:
    vids = videos if videos is not None else load_videos()
    if not vids or not article:
        return None
    title_t = _tokenize(article.get("title") or "")
    title_low = (article.get("title") or "").lower()
    topic = article.get("topic") or "genel"
    is_bursaspor = any(
        k in title_low
        for k in ("bursaspor", "timsah", "palut", "yeşil beyaz", "yeşil-beyaz", "1. lig")
    ) or topic == "spor"

    if is_bursaspor:
        pool = [v for v in vids if v.get("channel") == "Bursaspor"]
        if not pool:
            return None
        best = None
        best_score = -1
        for v in pool:
            score = len(title_t & _tokenize(v.get("title") or "")) * 2
            if score > best_score:
                best_score = score
                best = v
        return best or pool[0]

    best = None
    best_score = -1
    for v in vids:
        score = len(title_t & _tokenize(v.get("title") or ""))
        if v.get("topic") == topic:
            score += 3
        if score > best_score:
            best_score = score
            best = v
    if best_score >= 2:
        return best
    for v in vids:
        if v.get("topic") == topic:
            return v
    return None


def videos_for_topic(topic: str, *, limit: int = 4, exclude_id: str = "") -> list[dict]:
    rows = []
    for v in load_videos():
        if exclude_id and v.get("id") == exclude_id:
            continue
        if topic == "spor":
            if v.get("channel") == "Bursaspor" or v.get("topic") == "spor":
                rows.append(v)
        elif v.get("topic") == topic or topic == "genel":
            rows.append(v)
        if len(rows) >= limit:
            break
    return rows


def reading_minutes(art: dict) -> int:
    text = art.get("body_plain") or art.get("blurb") or ""
    for sec in art.get("sections") or []:
        text += " " + " ".join(sec.get("paras") or [])
    words = len(re.findall(r"\w+", text, re.UNICODE))
    return max(1, round(words / 180))
