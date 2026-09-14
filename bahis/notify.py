"""Bahis Telegram — crypto-news-monitor kalıbı. Emir yok.

Varsayılan LAB bot/kanal (ANALİZ1 sohbetine düşmez).
TELEGRAM_BAHIS_BOT_TOKEN / TELEGRAM_BAHIS_CHAT_ID ile ezilir.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TR = ZoneInfo("Europe/Istanbul")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENT = os.path.join(os.path.dirname(__file__), "data", "tg_sent.json")
MAX_PER_RUN = 5
HORIZON_H = 48


def _load_env() -> None:
    path = os.path.join(ROOT, ".env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()


def _creds() -> tuple[str, str]:
    token = (os.getenv("TELEGRAM_BAHIS_BOT_TOKEN") or os.getenv("TELEGRAM_LAB_BOT_TOKEN") or "").strip()
    chat = (os.getenv("TELEGRAM_BAHIS_CHAT_ID") or os.getenv("TELEGRAM_LAB_CHAT_ID") or "").strip()
    analiz1 = (os.getenv("TELEGRAM_ANALIZ1_CHAT_ID") or "830754964").strip()
    if chat == analiz1:
        chat = (os.getenv("TELEGRAM_LAB_CHAT_ID") or "").strip()
        if chat == analiz1:
            chat = ""
    return token, chat


def send(text: str) -> bool:
    token, chat = _creds()
    if not token or not chat:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(url, data=body, timeout=12) as r:
            return r.status == 200
    except OSError:
        return False


def _sent_load() -> dict:
    if os.path.isfile(SENT):
        try:
            with open(SENT, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {"keys": []}


def _sent_add(key: str) -> None:
    pack = _sent_load()
    keys = [k for k in pack.get("keys") or [] if k != key][-400:]
    keys.append(key)
    tmp = SENT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"keys": keys}, f)
    os.replace(tmp, SENT)


def _soon(ko: str | None) -> bool:
    if not ko:
        return False
    try:
        dt = datetime.fromisoformat(ko)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TR)
    except ValueError:
        return False
    now = datetime.now(TR)
    return now <= dt <= now + timedelta(hours=HORIZON_H)


def value_items(limit: int = 16) -> list[dict]:
    from bahis import dixon_coles
    from bahis.value import edges, fair_1x2
    dc = dixon_coles.upcoming_preds(limit=limit)
    out = []
    for src in dc.get("preds") or []:
        if not _soon(src.get("kickoff")):
            continue
        mr = src.get("matchResult") or {}
        odds = src.get("odds") or {}
        fair = (fair_1x2(odds) or {}).get("fair") or {}
        for sel, field in (("1", "home"), ("X", "draw"), ("2", "away")):
            o = odds.get(field)
            if not o or float(o) <= 1:
                continue
            ev = edges(float(mr.get(sel) or 0), float(o), fair.get(sel))
            if ev["isValue"]:
                out.append({
                    "id": src["id"],
                    "sel": sel,
                    "home": src["home"]["name"],
                    "away": src["away"]["name"],
                    "when": src.get("when"),
                    "odds": ev["odds"],
                    "edge": ev["edgeFair"],
                    "src": src.get("odds_src") or "?",
                })
    out.sort(key=lambda x: x["edge"], reverse=True)
    return out


def alert_value(dry: bool = False) -> int:
    from bahis.leagues_cfg import current_league, get as get_league
    from bahis.risk import snapshot
    risk = snapshot()
    if risk.get("halted"):
        if not dry:
            send(f"BAHİS kesici: {risk.get('halt_reason')} · emir yok")
        return 0
    items = value_items()
    have = set((_sent_load().get("keys") or []))
    n = 0
    lg = get_league(current_league())["short"]
    for it in items:
        key = f"{it['id']}:{it['sel']}"
        if key in have:
            continue
        text = (
            f"BAHİS value · {lg}\n"
            f"{it['home']} — {it['away']}\n"
            f"{it['sel']} @ {it['odds']} · fair +{it['edge']*100:.1f}p · {it['when']}\n"
            f"oran {it['src']} · kupon açılmaz"
        )
        if dry:
            n += 1
        elif send(text):
            _sent_add(key)
            n += 1
        if n >= MAX_PER_RUN:
            break
    return n


def alert_line(mid: str, home: str, away: str, move: dict) -> None:
    key = f"line:{mid}:{move.get('ts') or ''}"
    if key in set(_sent_load().get("keys") or []):
        return
    pts = move.get("home_pts")
    if pts is None or abs(float(pts)) < 0.03:
        return
    send(
        f"BAHİS oran · {home} — {away}\n"
        f"1 implied {float(pts)*100:+.1f}p · kupon açılmaz"
    )
    _sent_add(key)
