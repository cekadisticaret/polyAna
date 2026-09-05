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


def normalize_path(path: str) -> str:
    """Sayaç için yol — sorgu dizgisiz, uzun yollar kısaltılır."""
    p = ((path or "/").split("?")[0].split("#")[0].strip() or "/")
    if len(p) > 190:
        p = p[:190]
    return p


_PATH_LABELS = {
    "/": "Ana sayfa",
    "/feed": "Feed",
    "/kategoriler": "Kategoriler",
    "/hesap": "Profil",
    "/hesap/profil": "Feed · profil",
    "/gezilecek": "Gezilecek",
    "/yeme-icme": "Yeme-içme",
    "/oteller": "Oteller",
    "/konserler": "Konserler",
    "/etkinlikler": "Etkinlikler",
    "/nobetci-eczaneler": "Nöbetçi eczaneler",
    "/harita": "Harita",
    "/rota": "Rota",
    "/giris": "Giriş",
    "/kayit": "Kayıt",
}


def path_label(path: str) -> str:
    p = normalize_path(path)
    if p in _PATH_LABELS:
        return _PATH_LABELS[p]
    if p.startswith("/yer/"):
        return f"Yer · {p[5:]}"
    if p.startswith("/blog/"):
        return f"Blog · {p[6:]}"
    if p.startswith("/ilce/"):
        return f"İlçe · {p[6:]}"
    return p


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


def record_hit(db, *, day: str, vid: str, path: str = "/") -> None:
    from models import SiteDayStat, SitePageStat, SitePageVisitorDay, SiteVisitorDay

    norm = normalize_path(path)

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

    prow = db.query(SitePageStat).filter(SitePageStat.day == day, SitePageStat.path == norm).first()
    if prow is None:
        prow = SitePageStat(day=day, path=norm, pageviews=0, visitors=0)
        db.add(prow)
        db.flush()
    prow.pageviews = int(prow.pageviews or 0) + 1

    pex = (
        db.query(SitePageVisitorDay.id)
        .filter(SitePageVisitorDay.day == day, SitePageVisitorDay.path == norm, SitePageVisitorDay.vid == vid)
        .first()
    )
    if pex is None:
        db.add(SitePageVisitorDay(day=day, path=norm, vid=vid))
        prow.visitors = int(prow.visitors or 0) + 1


def track_response(request, response) -> None:
    """after_request içinde çağır — hata olursa sessiz geç."""
    try:
        if not _should_track(request, response.status_code):
            return
        from models import SessionLocal

        vid = ensure_vid(request, response)
        day = today_ist()
        path = request.path or "/"
        db = SessionLocal()
        try:
            record_hit(db, day=day, vid=vid, path=path)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
    except Exception:
        return


def reset_all_stats(db) -> None:
    """Kirlenmiş sayaçları sıfırla (bot / smoke şişirmesi sonrası)."""
    from models import SiteDayStat, SitePageStat, SitePageVisitorDay, SiteVisitorDay

    db.query(SitePageVisitorDay).delete()
    db.query(SitePageStat).delete()
    db.query(SiteVisitorDay).delete()
    db.query(SiteDayStat).delete()
    db.commit()


def top_pages(db, *, days: int = 7, limit: int = 25) -> dict:
    """En çok görüntülenen sayfalar — bugün + son N gün."""
    from models import SitePageStat
    from sqlalchemy import func

    today = today_ist()
    since = (datetime.now(_IST) - timedelta(days=max(0, days - 1))).strftime("%Y-%m-%d")

    today_rows = (
        db.query(SitePageStat)
        .filter(SitePageStat.day == today)
        .order_by(SitePageStat.pageviews.desc())
        .limit(limit)
        .all()
    )
    period_q = (
        db.query(
            SitePageStat.path,
            func.coalesce(func.sum(SitePageStat.pageviews), 0).label("pv"),
            func.coalesce(func.sum(SitePageStat.visitors), 0).label("uv"),
        )
        .filter(SitePageStat.day >= since)
        .group_by(SitePageStat.path)
        .order_by(func.sum(SitePageStat.pageviews).desc())
        .limit(limit)
    )
    period_rows = period_q.all()
    return {
        "today": today,
        "since": since,
        "today_pages": [
            {
                "path": r.path,
                "label": path_label(r.path),
                "pageviews": int(r.pageviews or 0),
                "visitors": int(r.visitors or 0),
            }
            for r in today_rows
        ],
        "period_pages": [
            {
                "path": r.path,
                "label": path_label(r.path),
                "pageviews": int(r.pv or 0),
                "visitors": int(r.uv or 0),
            }
            for r in period_rows
        ],
    }


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
