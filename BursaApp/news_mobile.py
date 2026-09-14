"""Bursa haberleri — mobil API veri paketi."""
from __future__ import annotations

from news_pages import (
    NEWS_TOPICS,
    get_article,
    list_articles,
    load_bursaspor_sidebar,
    load_videos,
    match_video,
    reading_minutes,
    related_articles,
    videos_for_topic,
)


def _slim_video(v: dict) -> dict:
    return {
        "id": v.get("id"),
        "title": v.get("title"),
        "channel": v.get("channel"),
        "topic": v.get("topic"),
        "topic_label": v.get("topic_label"),
        "published_at": v.get("published_at"),
        "date_label": v.get("date_label"),
        "watch_url": v.get("watch_url"),
        "thumb": v.get("thumb"),
    }


def _slim_article(a: dict, *, full: bool = False) -> dict:
    out = {
        "id": a.get("id"),
        "slug": a.get("slug"),
        "title": a.get("title"),
        "blurb": a.get("blurb"),
        "source": a.get("source"),
        "url": a.get("url"),
        "published_at": a.get("published_at"),
        "topic": a.get("topic"),
        "topic_label": a.get("topic_label"),
        "date_label": a.get("date_label"),
        "img_url": a.get("img_url"),
        "path": a.get("path"),
    }
    if full:
        out.update(
            {
                "sections": a.get("sections") or [],
                "body_plain": a.get("body_plain") or "",
                "disclaimer": a.get("disclaimer") or "",
                "generated_at": a.get("generated_at") or "",
                "reading_minutes": reading_minutes(a),
            }
        )
    return out


def build_news_hub(*, topic: str = "", q: str = "", page: int = 1, per_page: int = 24) -> dict:
    topic = topic if topic in NEWS_TOPICS else ""
    articles, total, meta = list_articles(topic=topic, q=q, page=page, per_page=per_page)
    videos = [_slim_video(v) for v in load_videos()[:6]]
    return {
        "topics": NEWS_TOPICS,
        "articles": [_slim_article(a) for a in articles],
        "videos": videos,
        "featured_video": videos[0] if videos else None,
        "bursaspor": load_bursaspor_sidebar(),
        "meta": {
            **meta,
            "total": total,
            "topic": topic,
            "q": q.strip(),
        },
    }


def build_news_detail(slug: str) -> dict | None:
    art = get_article(slug)
    if not art:
        return None
    videos = load_videos()
    video = match_video(art, videos)
    topic = art.get("topic") or "genel"
    related = [_slim_article(a) for a in related_articles(art, limit=6)]
    topic_videos = [_slim_video(v) for v in videos_for_topic(topic, limit=4, exclude_id=(video or {}).get("id") or "")]
    payload = _slim_article(art, full=True)
    payload["related"] = related
    payload["video"] = _slim_video(video) if video else None
    payload["topic_videos"] = topic_videos
    return payload
