#!/usr/bin/env python3
"""Bildirim outbox — e-posta veya dosya kuyruğu (SMTP yoksa log).

Kullanım:
  from notify import enqueue, flush_outbox
  enqueue(kind="concert", title="…", body="…", url="…")
  flush_outbox()  # SMTP_HOST varsa gönderir, yoksa data/notify_outbox.jsonl
"""
from __future__ import annotations

import json
import logging
import os
import smtplib
import time
from datetime import datetime
from email.message import EmailMessage
from typing import Any

_DIR = os.path.dirname(os.path.abspath(__file__))
OUTBOX = os.path.join(_DIR, "data", "notify_outbox.jsonl")
_log = logging.getLogger("bursaapp.notify")


def smtp_ready() -> bool:
    """SMTP_HOST tanımlıysa True (kimlik bilgisi kontrolü login anında)."""
    return bool((os.environ.get("SMTP_HOST") or "").strip())


def enqueue(
    *,
    kind: str,
    title: str,
    body: str = "",
    url: str = "",
    user_emails: list[str] | None = None,
) -> None:
    row = {
        "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "kind": kind,
        "title": title,
        "body": body,
        "url": url,
        "emails": user_emails or [],
        "sent": False,
    }
    os.makedirs(os.path.dirname(OUTBOX), exist_ok=True)
    with open(OUTBOX, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _smtp_send(to: str, subject: str, body: str) -> bool:
    host = (os.environ.get("SMTP_HOST") or "").strip()
    if not host:
        return False
    port = int(os.environ.get("SMTP_PORT") or "587")
    user = (os.environ.get("SMTP_USER") or "").strip()
    password = (os.environ.get("SMTP_PASS") or "").strip()
    from_addr = (os.environ.get("SMTP_FROM") or user or "noreply@bursaapp.com").strip()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.set_content(body)
    with smtplib.SMTP(host, port, timeout=20) as s:
        s.starttls()
        if user and password:
            s.login(user, password)
        s.send_message(msg)
    return True


def send_email_now(to: str, subject: str, body: str) -> bool:
    """Anında SMTP dener; yapılandırma yoksa veya hata olursa False."""
    if not smtp_ready():
        return False
    try:
        return _smtp_send(to, subject, body)
    except Exception as e:
        _log.warning("SMTP send failed to=%s err=%s", to, e)
        return False


def flush_outbox(limit: int = 50) -> dict[str, int]:
    """Bekleyen satırları SMTP ile dener; gönderilenleri sent=true yazar."""
    if not os.path.isfile(OUTBOX):
        return {"pending": 0, "sent": 0, "kept": 0}
    if not smtp_ready():
        # SMTP yok — kuyruk dosyada kalsın, sent=false
        pending = 0
        for line in open(OUTBOX, encoding="utf-8"):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not row.get("sent"):
                pending += 1
        return {"pending": pending, "sent": 0, "kept": pending, "smtp": False}
    lines = open(OUTBOX, encoding="utf-8").read().splitlines()
    kept: list[str] = []
    sent = pending = 0
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            row: dict[str, Any] = json.loads(line)
        except Exception:
            kept.append(line)
            continue
        if row.get("sent"):
            kept.append(line)
            continue
        pending += 1
        if sent >= limit:
            kept.append(line)
            continue
        emails = row.get("emails") or []
        ok_any = False
        for em in emails:
            try:
                if _smtp_send(em, row.get("title") or "BursaApp", row.get("body") or ""):
                    ok_any = True
            except Exception as e:
                _log.warning("SMTP flush failed to=%s err=%s", em, e)
                ok_any = False
        if ok_any:
            row["sent"] = True
            row["sent_at"] = time.time()
            sent += 1
        kept.append(json.dumps(row, ensure_ascii=False))
    with open(OUTBOX, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + ("\n" if kept else ""))
    return {"pending": pending, "sent": sent, "kept": len(kept)}


def recipients_for_kind(db, kind: str) -> list[str]:
    """Tercihine göre e-posta listesi."""
    from models import User

    q = db.query(User).filter(User.email.isnot(None))
    emails: list[str] = []
    for u in q.all():
        if kind == "concert" and not u.notify_concert:
            continue
        if kind == "theater" and not u.notify_theater:
            continue
        if kind in ("event", "festival") and not u.notify_festival:
            continue
        if kind == "campaign" and not u.notify_campaign:
            continue
        if kind == "place" and not u.notify_new_place:
            continue
        if u.email and "@" in u.email:
            emails.append(u.email.strip())
    return emails


def _tg_creds() -> tuple[str, str]:
    token = (os.environ.get("BURSAAPP_TG_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("BURSAAPP_TG_CHAT_ID") or os.environ.get("TELEGRAM_CHAT") or "").strip()
    return token, chat


def telegram_send(text: str) -> bool:
    """BursaApp bot ile Telegram mesajı. Başarısızsa False (kayıt akışını bozmaz)."""
    import urllib.parse
    import urllib.request

    token, chat = _tg_creds()
    if not token or not chat:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {"chat_id": chat, "text": text, "disable_web_page_preview": "1"}
    ).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=12) as r:
            raw = json.loads(r.read().decode())
        return bool(raw.get("ok"))
    except Exception:
        return False


def notify_place_approved(db, place) -> None:
    """Onaylanan yeni mekan — notify_new_place açık kullanıcılara mail."""
    emails = recipients_for_kind(db, "place")
    if not emails:
        return
    try:
        from seo import abs_url
    except Exception:
        abs_url = lambda p: p  # type: ignore[assignment,misc]
    slug = getattr(place, "slug", "") or ""
    title = getattr(place, "title", "") or "Yeni mekan"
    ilce = getattr(place, "ilce", "") or ""
    blurb = (getattr(place, "blurb", "") or getattr(place, "body", "") or "").strip()
    path = f"/yer/{slug}" if slug else "/yeme-icme"
    body = "\n".join(x for x in (ilce, blurb[:240] if blurb else "") if x)
    enqueue(
        kind="place",
        title=f"Bursa · Yeni mekan: {title}",
        body=body,
        url=abs_url(path),
        user_emails=emails[:80],
    )
    flush_outbox(limit=20)


def notify_register(*, name: str, email: str, user_id: int | None = None, source: str = "web") -> None:
    """Yeni üye kaydı — Telegram: başlık + kayıt bilgileri (şifre yok)."""
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
    lines = [
        "BursaApp kayıt yapıldı",
        "",
        f"Ad: {name}",
        f"E-posta: {email}",
    ]
    if user_id is not None:
        lines.append(f"Üye no: {user_id}")
    lines.append(f"Kaynak: {source}")
    lines.append(f"Zaman: {now} İST")
    telegram_send("\n".join(lines))
