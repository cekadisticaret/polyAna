"""Poly Algo Analist ortak yardımcıları — .env yükleme, dashboard API çağrıları,
Telegram gönderimi, Anthropic (Claude) çağrısı. `poly_algo_analyst.py` (3 saatlik) ve
`poly_algo_daily_report.py` (günlük) bu modülü paylaşır.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ENV_FILE = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE, encoding="utf-8") as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

TZ_TR = ZoneInfo("Europe/Istanbul")
DASH_BASE = "http://127.0.0.1:5050"
ANALYST_TOKEN = os.environ.get("ANALYST_API_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_ANALIST_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_ANALIST_CHAT_ID", "")
CLAUDE_MODEL = "claude-sonnet-5"
_TELEGRAM_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analyst_telegram_log.jsonl")
_TELEGRAM_LOG_MAX_LINES = 500


def required_env_missing() -> list[str]:
    return [
        name for name, val in (
            ("ANALYST_API_TOKEN", ANALYST_TOKEN),
            ("ANTHROPIC_API_KEY", ANTHROPIC_KEY),
            ("TELEGRAM_ANALIST_BOT_TOKEN", TG_TOKEN),
            ("TELEGRAM_ANALIST_CHAT_ID", TG_CHAT),
        ) if not val
    ]


def http_json(url: str, headers: dict | None = None, data: bytes | None = None,
              method: str = "GET", timeout: int = 30) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_digest(hours: float = 6, limit: int = 15) -> dict:
    url = f"{DASH_BASE}/poly/api/analyst/digest?hours={hours}&limit={limit}"
    return http_json(url, headers={"X-Analyst-Token": ANALYST_TOKEN})


def fetch_journal(limit: int = 8) -> dict:
    url = f"{DASH_BASE}/poly/api/analyst/journal?limit={limit}"
    return http_json(url, headers={"X-Analyst-Token": ANALYST_TOKEN})


def post_journal(
    text: str,
    tags: list[str],
    *,
    body: str | None = None,
    title: str | None = None,
    kind: str = "periodic",
) -> dict:
    payload: dict = {"text": text, "tags": tags, "kind": kind}
    if body:
        payload["body"] = body
    if title:
        payload["title"] = title
    data = json.dumps(payload).encode("utf-8")
    url = f"{DASH_BASE}/poly/api/analyst/journal"
    return http_json(
        url,
        headers={"X-Analyst-Token": ANALYST_TOKEN, "Content-Type": "application/json"},
        data=data,
        method="POST",
    )


def post_feed(title: str, body: str, kind: str = "periodic", tags: list[str] | None = None) -> dict:
    payload: dict = {"title": title, "body": body, "kind": kind}
    if tags:
        payload["tags"] = tags
    url = f"{DASH_BASE}/poly/api/analyst/feed"
    return http_json(
        url,
        headers={"X-Analyst-Token": ANALYST_TOKEN, "Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )


def _append_telegram_log(text: str) -> None:
    try:
        entry = {
            "ts": datetime.now(TZ_TR).isoformat(),
            "text": text[:12000],
        }
        lines: list[str] = []
        if os.path.exists(_TELEGRAM_LOG_FILE):
            with open(_TELEGRAM_LOG_FILE, encoding="utf-8") as f:
                lines = f.readlines()
        lines.append(json.dumps(entry, ensure_ascii=False) + "\n")
        if len(lines) > _TELEGRAM_LOG_MAX_LINES:
            lines = lines[-_TELEGRAM_LOG_MAX_LINES:]
        with open(_TELEGRAM_LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass


def log_telegram_text(text: str) -> None:
    _append_telegram_log(text)


def send_telegram(text: str) -> dict:
    _append_telegram_log(text)
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": TG_CHAT, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
    body = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
        "thinking": {"type": "disabled"},
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read().decode("utf-8"))
    return "".join(
        b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text"
    ).strip()
