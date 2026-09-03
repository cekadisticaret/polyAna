"""Site ziyaretçi / sayfa görüntüleme sayacı — yalnız gerçek tarayıcı trafiği."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo

    _IST = ZoneInfo("Europe/Istanbul")
except Exception:  # pragma: no cover
    _IST = timezone(timedelta(hours=3))

COOKIE = "ba_vid"
_BOT_RE = re.compile(
    r"("
    r"bot|crawl|spider|slurp|bingpreview|facebookexternalhit|facebookcatalog|"
    r"meta-externalagent|preview|wget|curl|httpclient|httpx|aiohttp|scrapy|"
    r"selenium|headless|headlesschrome|phantom|puppeteer|playwright|lighthouse|"
    r"python-urllib|python-requests|urllib|go-http-client|java/|okhttp|"
    r"uptime|monitor|healthcheck|ensure_up|bytespider|semrush|ahrefs|petalbot|"
    r"mj12bot|dotbot|barkrowler|dataforseo|gptbot|claudebot|perplexitybot|"
    r"amazonbot|applebot|bingbot|yandex|duckduck|googleother|googlebot|"
    r"google-inspectiontool|storebot-google|adsbot-google|mediapartners-google|"
    r"feedfetcher-google|censysinspect|cyberconvoyscout|bursaapp|coptc|"
    r"compatible;\s*google|got/|wordpress/"
    r")",
    re.I,
)
# GoogleOther / Google-InspectionTool — Chrome taklidi; UA'da "bot" yoktu
_GOOGLE_FETCHER_UA = re.compile(
    r"Nexus 5X Build/MMB29P.*Chrome/.*\(compatible;\s*Google",
    re.I,
)
_SKIP_PREFIX = (
    "/static/",
    "/admin",
    "/api/",
    "/favicon",
    "/robots.txt",
    "/sitemap",
    "/manifest",
)


def today_ist() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d")


def client_ip(request) -> str:
    """Nginx X-Real-IP / X-Forwarded-For; yoksa remote_addr."""
    xri = (request.headers.get("X-Real-IP") or "").strip()
    if xri:
        return xri
    xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if xff:
        return xff
    return (request.remote_addr or "").strip()


def _is_loopback(ip: str) -> bool:
    ip = (ip or "").strip().lower()
    return (
        not ip
        or ip in ("127.0.0.1", "::1", "localhost", "0.0.0.0")
        or ip.startswith("127.")
        or ip.startswith("::ffff:127.")
    )


def _looks_like_browser(request) -> bool:
    """Bot UA'si olmasa bile tarayıcı sinyali olmayan istekleri ele."""
    ua = (request.headers.get("User-Agent") or "").strip()
    if len(ua) < 40:
        return False
    if _GOOGLE_FETCHER_UA.search(ua):
        return False
    al = (request.headers.get("Accept-Language") or "").strip()
    if len(al) < 2:
        return False
    accept = (request.headers.get("Accept") or "").strip()
    if not accept:
        return False
    sfd = (request.headers.get("Sec-Fetch-Dest") or "").strip().lower()
    if sfd and sfd not in ("document", "empty"):
        return False
    return True


def _should_track(request, status: int) -> bool:
    if (request.method or "") != "GET" or status >= 400:
        return False
    path = request.path or "/"
    if any(path.startswith(x) for x in _SKIP_PREFIX):
        return False
    ua = request.headers.get("User-Agent") or ""
    if not ua.strip() or _BOT_RE.search(ua):
        return False
    if _is_loopback(client_ip(request)):
        return False
    return _looks_like_browser(request)


def ensure_vid(request, response) -> str:
    """Cookie'den vid al; yoksa üret ve Set-Cookie yaz."""
    vid = (request.cookies.get(COOKIE) or "").strip()
    if len(vid) >= 8 and len(vid) <= 40 and all(c.isalnum() or c in "-_" for c in vid):
        return vid
    vid = uuid.uuid4().hex
    response.set_cookie(
        COOKIE,
        vid,
        max_age=365 * 24 * 3600,
        httponly=True,
        samesite="Lax",
        path="/",
    )
    return vid


def record_hit(db, *, day: str, vid: str) -> None:
    from models import SiteDayStat, SiteVisitorDay

    row = db.query(SiteDayStat).filter(SiteDayStat.day == day).first()
    if row is None:
        row = SiteDayStat(day=day, pageviews=0, visitors=0)
        db.add(row)
        db.flush()
    row.pageviews = int(row.pageviews or 0) + 1

    existed = (
        db.query(SiteVisitorDay.id)
        .filter(SiteVisitorDay.day == day, SiteVisitorDay.vid == vid)
        .first()
    )
    if existed is None:
        db.add(SiteVisitorDay(day=day, vid=vid))
        row.visitors = int(row.visitors or 0) + 1


def track_response(request, response) -> None:
    """after_request içinde çağır — hata olursa sessiz geç."""
    try:
        if not _should_track(request, response.status_code):
            return
        from models import SessionLocal

        vid = ensure_vid(request, response)
        day = today_ist()
        db = SessionLocal()
        try:
            record_hit(db, day=day, vid=vid)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
    except Exception:
        return


def reset_all_stats(db) -> None:
    """Kirlenmiş sayaçları sıfırla (bot / smoke şişirmesi sonrası)."""
    from models import SiteDayStat, SiteVisitorDay

    db.query(SiteVisitorDay).delete()
    db.query(SiteDayStat).delete()
    db.commit()


def summary(db, days: int = 14) -> dict:
    """Admin özet: bugün / 7g tekil / tüm zamanlar tekil + son N gün.

    Ziyaretçi = cookie `ba_vid` tekil kişi.
    7g ve toplam: günlük ziyaretçi toplamı DEĞİL — aynı kişi birden fazla güne
    girerse bir kez sayılır (DISTINCT vid).
    """
    from models import SiteDayStat, SiteVisitorDay
    from sqlalchemy import func

    today = today_ist()
    since7 = (datetime.now(_IST) - timedelta(days=6)).strftime("%Y-%m-%d")
    since_n = (datetime.now(_IST) - timedelta(days=max(0, days - 1))).strftime("%Y-%m-%d")

    today_row = db.query(SiteDayStat).filter(SiteDayStat.day == today).first()
    d7_pv = (
        db.query(func.coalesce(func.sum(SiteDayStat.pageviews), 0))
        .filter(SiteDayStat.day >= since7)
        .scalar()
    )
    total_pv = db.query(func.coalesce(func.sum(SiteDayStat.pageviews), 0)).scalar()
    d7_visitors = (
        db.query(func.count(func.distinct(SiteVisitorDay.vid)))
        .filter(SiteVisitorDay.day >= since7)
        .scalar()
    )
    total_visitors = db.query(func.count(func.distinct(SiteVisitorDay.vid))).scalar()
    series = (
        db.query(SiteDayStat)
        .filter(SiteDayStat.day >= since_n)
        .order_by(SiteDayStat.day.asc())
        .all()
    )
    return {
        "today": today,
        "today_pageviews": int(today_row.pageviews) if today_row else 0,
        "today_visitors": int(today_row.visitors) if today_row else 0,
        "d7_pageviews": int(d7_pv or 0),
        "d7_visitors": int(d7_visitors or 0),
        "total_pageviews": int(total_pv or 0),
        "total_visitors": int(total_visitors or 0),
        "series": [
            {"day": r.day, "pageviews": int(r.pageviews or 0), "visitors": int(r.visitors or 0)}
            for r in series
        ],
    }


if __name__ == "__main__":
    import sys

    from models import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        if "--reset" in sys.argv:
            reset_all_stats(db)
            print("stats wiped")
        print(summary(db))
    finally:
        db.close()
