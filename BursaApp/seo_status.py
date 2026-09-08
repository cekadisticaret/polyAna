"""SEO / Google durum kontrolü — admin dashboard + /admin/seo."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

_DIR = os.path.dirname(os.path.abspath(__file__))
_CFG = os.path.join(_DIR, "data", "seo_config.json")


def _load_cfg() -> dict:
    try:
        with open(_CFG, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cfg(patch: dict) -> dict:
    cur = _load_cfg()
    cur.update(patch or {})
    os.makedirs(os.path.dirname(_CFG), exist_ok=True)
    with open(_CFG, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)
    return cur


def google_verification_token() -> str:
    env = (os.environ.get("GOOGLE_SITE_VERIFICATION") or "").strip()
    if env:
        return env
    return str(_load_cfg().get("google_site_verification") or "").strip()


def ga_measurement_id() -> str:
    """GA4 Measurement ID (G-XXXX). Env > seo_config."""
    env = (os.environ.get("GA_MEASUREMENT_ID") or os.environ.get("GOOGLE_ANALYTICS_ID") or "").strip()
    if env:
        return env
    return str(_load_cfg().get("ga_measurement_id") or "").strip()


def google_ads_id() -> str:
    """Google Ads dönüşüm etiketi (AW-XXXX). Env > seo_config."""
    env = (os.environ.get("GOOGLE_ADS_ID") or "").strip()
    if env:
        return env
    return str(_load_cfg().get("google_ads_id") or "").strip()


def gsc_connected() -> bool:
    """Domain DNS doğrulama veya manuel işaret — HTML meta şart değil."""
    cfg = _load_cfg()
    if cfg.get("gsc_connected") is True:
        return True
    return bool(google_verification_token())


def _check(ok: bool, label: str, detail: str = "", *, critical: bool = False) -> dict:
    return {
        "ok": bool(ok),
        "label": label,
        "detail": detail or "",
        "critical": bool(critical),
        "status": "ok" if ok else ("warn" if not critical else "fail"),
    }


def collect(app=None, db=None) -> dict[str, Any]:
    """Canlı teknik SEO + Google kayıt durumu."""
    from seo import site_base

    checks: list[dict] = []
    token = google_verification_token()
    connected = gsc_connected()
    cfg = _load_cfg()
    base = site_base()

    # Google Search Console — domain mülk veya HTML meta
    prop = (cfg.get("gsc_property") or "bursaapp.com").strip()
    checks.append(
        _check(
            connected,
            "Google Search Console mülkü",
            (
                f"{prop} bağlı"
                + (f" · {cfg.get('gsc_note')}" if cfg.get("gsc_note") else "")
                if connected
                else "Search Console’da mülk yok / işaretlenmedi"
            ),
            critical=True,
        )
    )
    if token:
        checks.append(
            _check(True, "HTML doğrulama kodu", f"Meta token kayıtlı ({token[:8]}…)"),
        )
    elif connected:
        checks.append(
            _check(
                True,
                "Doğrulama yöntemi",
                "Domain / DNS (HTML meta gerekmez)",
            )
        )

    client = None
    home_html = ""
    robots = ""
    sm_index = ""
    sm_pages_n = 0
    sm_places_n = 0
    try:
        if app is None:
            from app import app as flask_app

            app = flask_app
        client = app.test_client()
        home = client.get("/")
        home_html = home.get_data(as_text=True) if home.status_code == 200 else ""
        robots = client.get("/robots.txt").get_data(as_text=True) if True else ""
        sm_index = client.get("/sitemap.xml").get_data(as_text=True)
        pages = client.get("/sitemap-pages.xml").get_data(as_text=True)
        places = client.get("/sitemap-places.xml").get_data(as_text=True)
        sm_pages_n = pages.count("<url>")
        sm_places_n = places.count("<url>")
    except Exception as e:
        checks.append(_check(False, "Yerel HTTP kontrol", str(e)[:160], critical=True))

    if home_html:
        has_meta = bool(token) and (
            f'content="{token}"' in home_html or "google-site-verification" in home_html
        )
        # token yoksa meta da olamaz
        if token:
            checks.append(
                _check(
                    has_meta,
                    "Ana sayfada GSC meta etiketi",
                    "google-site-verification head içinde",
                    critical=True,
                )
            )
        checks.append(
            _check(
                'rel="canonical"' in home_html or "rel='canonical'" in home_html,
                "Canonical link",
                "Ana sayfa <link rel=canonical>",
            )
        )
        checks.append(
            _check("og:title" in home_html and "og:image" in home_html, "Open Graph", "og:title + og:image")
        )
        checks.append(
            _check("application/ld+json" in home_html, "JSON-LD yapılandırılmış veri", "Organization/WebSite")
        )
        checks.append(
            _check(
                'name="description"' in home_html or "name='description'" in home_html,
                "Meta description",
            )
        )

    checks.append(
        _check(
            "Sitemap:" in robots and "User-agent:" in robots,
            "robots.txt",
            f"Sitemap satırı · Disallow /admin",
            critical=True,
        )
    )
    checks.append(
        _check(
            "sitemapindex" in sm_index or "<urlset" in sm_index,
            "sitemap.xml",
            f"pages {sm_pages_n} · places {sm_places_n} URL",
            critical=True,
        )
    )
    checks.append(
        _check(
            base.startswith("https://"),
            "HTTPS site URL",
            base,
            critical=True,
        )
    )

    # İçerik denetimi (SeoAudit)
    audit_summary = ""
    audit_at = None
    audit_issues = 0
    if db is not None:
        try:
            from models import SeoAudit

            latest = db.query(SeoAudit).order_by(SeoAudit.id.desc()).first()
            if latest:
                audit_summary = latest.summary or ""
                audit_at = latest.created_at
                try:
                    audit_issues = len(json.loads(latest.issues_json or "[]"))
                except Exception:
                    audit_issues = 0
            checks.append(
                _check(
                    latest is not None,
                    "Gece içerik SEO denetimi",
                    audit_summary or "Henüz çalışmamış — /admin/seo → Şimdi çalıştır",
                )
            )
        except Exception:
            pass

    # Cron ipucu (dosya yoksa bile sabit beklenen ifade)
    cron_ok = False
    try:
        import subprocess

        out = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.DEVNULL)
        cron_ok = "bursaapp_nightly" in out or "seo_nightly" in out
        cron_hint = (
            "30 23 * * * (02:30 İST, bursaapp_nightly)"
            if "bursaapp_nightly" in out
            else ("seo_nightly crontab’ta" if cron_ok else "crontab’ta nightly/seo yok")
        )
    except Exception:
        cron_ok = False
        cron_hint = "crontab okunamadı"
    checks.append(
        _check(
            cron_ok,
            "seo_nightly cron",
            cron_hint,
        )
    )

    try:
        from ai_seo import collect_checks as ai_collect_checks, ai_grade

        ai_checks = ai_collect_checks(app=app, db=db)
        checks.extend(ai_checks)
        ai_grade_s, ai_ok, ai_total = ai_grade(ai_checks)
    except Exception as e:
        ai_grade_s, ai_ok, ai_total = "uyarı", 0, 0
        checks.append(_check(False, "Yapay zeka SEO modülü", str(e)[:120]))

    ok_n = sum(1 for c in checks if c["ok"])
    fail_n = sum(1 for c in checks if not c["ok"] and c.get("critical"))
    warn_n = sum(1 for c in checks if not c["ok"] and not c.get("critical"))
    if fail_n:
        grade = "kritik"
    elif warn_n:
        grade = "uyarı"
    else:
        grade = "iyi"

    meta_ok = next(
        (c["ok"] for c in checks if c["label"].startswith("Ana sayfada GSC")),
        False,
    )

    return {
        "checked_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "site_url": base,
        "google_token_set": bool(token),
        "google_connected": connected,
        "google_verified_meta": bool(token and meta_ok),
        "gsc_note": (
            str(cfg.get("gsc_note") or "").strip()
            or (
                "Search Console mülkü bağlı — sol menüden Site Haritaları’na https://bursaapp.com/sitemap.xml ekle; performans birkaç gün sonra dolar."
                if connected
                else "Google kaydı eksik: Search Console’da mülk ekle veya HTML kodunu kaydet."
            )
        ),
        "grade": grade,
        "ok_n": ok_n,
        "fail_n": fail_n,
        "warn_n": warn_n,
        "total": len(checks),
        "checks": checks,
        "sitemap_pages": sm_pages_n,
        "sitemap_places": sm_places_n,
        "audit_summary": audit_summary,
        "audit_at": audit_at,
        "audit_issues": audit_issues,
        "sitemap_submit_url": f"{base}/sitemap.xml",
        "robots_url": f"{base}/robots.txt",
        "llms_url": f"{base}/llms.txt",
        "llms_full_url": f"{base}/llms-full.txt",
        "ai_seo_grade": ai_grade_s,
        "ai_seo_ok": ai_ok,
        "ai_seo_total": ai_total,
    }
