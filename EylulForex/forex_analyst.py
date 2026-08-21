"""Forex CEM01 AI Analist — `/forex/grafik` sanal defter + grafik.

Poly Yapay Zeka Analiz ile aynı ritim: 3 saatte bir Claude yorumu, feed dosyası,
Telegram (analist kanalı varsa). CEM01 çekirdeğine yazmaz — `apply_signal` /
`forex_spot` çağırılmaz (o fonksiyonlar işlem açabilir).

Cron: `10 */3 * * *`
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
_POLY = _ROOT / "temmuzPoly"
sys.path.insert(0, str(_POLY))
sys.path.insert(0, str(_DIR))

import analyst_common as ac  # noqa: E402

_FEED = _DIR / "data" / "forex_analyst_feed.jsonl"
_FEED_MAX = 500
_WINDOW_HOURS = 6
_HIST_LIMIT = 12
_JOURNAL_LIMIT = 8
_CRON_SLOT_HOURS = 3

_FIELD_NOTES = """Alan açıklamaları (hepsi sanal CEM01 /forex/grafik — gerçek broker emri yok):
- quote: anlık XAUUSD bid/ask/spread ve fiyat kaynağı
- signal: Kalman+VWAP canlı yön (UP/DOWN/NEUTRAL), güven, katman skorları
- rail: M5/M15 teyit skorları
- levels: 5m destek/direnç
- book: $300 kasa · $100×500x sanal; açık pozisyon, stop/hedef, float, son red
- recent_trades: penceredeki kapanmış işlemler (pnl net, komisyon+swap dahil)
- candles_15m / candles_1m: son mumlar (OHLC)
"""

SYSTEM_PROMPT = f"""Sen Cem'in Forex CEM01 ekranını (/forex/grafik, sanal XAUUSD) takip eden
analist arkadaşısın. Robot rapor yazma; "Cem, grafikte..." tarzı samimi ama net ol.

{_FIELD_NOTES}

Görevin:
1. Fiyat, sinyal, M5/M15 rayı ve S/R'yi birlikte oku — yön tutarlı mı, yoksa ray ile
   Kalman çelişiyor mu, somut söyle.
2. Açık pozisyon varsa planı (giriş/stop/hedef/float) değerlendir; kapanmış son
   işlemlerde aynı hata tekrar ediyor mu (stop uzak, erken kâr, komisyon) bak.
3. Önceki notlarını oku — hipotezin doğrulandı mı çürüdü mü, varsa belirt.
4. Emir tavsiyesi verme ("şimdi al") — gözlem yaz. Zorla hikaye uydurma.
5. 3-6 cümle, Türkçe.

Yanıtının SONUNA:
ÖZET: <tek cümle>"""


def _parse_dt(ts: str | None):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ac.TZ_TR)
        return dt
    except (ValueError, TypeError):
        return None


def _px_row(c: dict) -> dict:
    return {
        "t": c.get("time"),
        "o": round(float(c["open"]), 2),
        "h": round(float(c["high"]), 2),
        "l": round(float(c["low"]), 2),
        "c": round(float(c["close"]), 2),
    }


def _pos_row(p: dict) -> dict:
    keys = (
        "side", "entry", "stop", "target", "mark", "float_net", "float_pnl",
        "volume", "open_time", "reason", "commission", "swap", "progress",
    )
    return {k: p.get(k) for k in keys if p.get(k) is not None}


def _trade_row(t: dict) -> dict:
    keys = (
        "side", "entry", "exit", "pnl", "gross", "commission", "swap",
        "reason", "open_time", "close_time", "volume",
    )
    return {k: t.get(k) for k in keys if t.get(k) is not None}


def build_digest(hours: float = _WINDOW_HOURS) -> dict:
    from forex_book import snapshot
    from forex_data import forex_quote, forex_rail, get_xau_klines
    from forex_signal import live_signal, sr_levels

    q = forex_quote()
    bid, ask = q.get("bid"), q.get("ask")
    try:
        rail = forex_rail()
    except Exception as e:
        rail = {"error": str(e)[:160]}
    try:
        sig = live_signal("1m")
    except Exception as e:
        sig = {"direction": "NEUTRAL", "error": str(e)[:160]}
    try:
        rows5, _ = get_xau_klines("5m", 120)
        levels = sr_levels(rows5)
    except Exception as e:
        levels = {"error": str(e)[:160]}
        rows5 = []
    try:
        rows1, src1 = get_xau_klines("1m", 40)
    except Exception:
        rows1, src1 = [], "?"
    try:
        rows15, src15 = get_xau_klines("15m", 24)
    except Exception:
        rows15, src15 = [], "?"

    book = snapshot(bid, ask, book="g1")
    cutoff = datetime.now(ac.TZ_TR) - timedelta(hours=hours)
    hist = book.get("history") or []
    recent = []
    for t in hist:
        dt = _parse_dt(t.get("close_time") or t.get("exit_time") or t.get("open_time"))
        if dt is not None and dt >= cutoff:
            recent.append(_trade_row(t))
        if len(recent) >= _HIST_LIMIT:
            break

    wins = sum(1 for t in recent if float(t.get("pnl") or 0) > 0)
    pnl_w = round(sum(float(t.get("pnl") or 0) for t in recent), 2)

    return {
        "generated_at_tr": datetime.now(ac.TZ_TR).isoformat(),
        "window_hours": hours,
        "screen": "/forex/grafik",
        "book_key": "g1",
        "quote": {
            "bid": q.get("bid"), "ask": q.get("ask"), "mid": q.get("mid"),
            "spread": q.get("spread"), "src": q.get("src"),
            "day_high": q.get("day_high"), "day_low": q.get("day_low"),
        },
        "signal": {
            k: sig.get(k) for k in (
                "direction", "confidence", "raw_score", "is_stable", "lean",
                "layers", "engine", "error",
            ) if sig.get(k) is not None
        },
        "rail": rail if isinstance(rail, dict) else {},
        "levels": {
            "support": (levels or {}).get("nearest_support") if isinstance(levels, dict) else None,
            "resistance": (levels or {}).get("nearest_resistance") if isinstance(levels, dict) else None,
            "tf": "5m",
        },
        "book": {
            "balance": book.get("balance"),
            "equity": book.get("equity"),
            "total_pnl": book.get("total_pnl"),
            "open_count": book.get("open_count"),
            "last_reject": book.get("last_reject"),
            "halted": book.get("halted"),
            "positions": [_pos_row(p) for p in (book.get("positions") or [])],
        },
        "window": {
            "trades": len(recent),
            "wins": wins,
            "pnl": pnl_w,
            "recent_trades": recent,
        },
        "candles_1m": [_px_row(c) for c in rows1[-16:]],
        "candles_15m": [_px_row(c) for c in rows15[-12:]],
        "klines_src": {"1m": src1, "15m": src15},
    }


def _append_feed(entry: dict) -> None:
    _FEED.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if _FEED.exists():
        try:
            lines = _FEED.read_text(encoding="utf-8").splitlines(True)
        except Exception:
            lines = []
    lines.append(json.dumps(entry, ensure_ascii=False) + "\n")
    if len(lines) > _FEED_MAX:
        lines = lines[-_FEED_MAX:]
    _FEED.write_text("".join(lines), encoding="utf-8")


def read_feed(limit: int = 50) -> list[dict]:
    if not _FEED.exists():
        return []
    try:
        rows = [json.loads(line) for line in _FEED.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return []
    return rows[-limit:][::-1]


def _cron_slot(dt: datetime) -> tuple:
    utc = dt.astimezone(timezone.utc)
    return (utc.date(), utc.hour // _CRON_SLOT_HOURS)


def _cooldown_remaining_hours() -> float | None:
    rows = read_feed(limit=1)
    if not rows:
        return None
    last_dt = _parse_dt(rows[0].get("ts"))
    if not last_dt:
        return None
    now = datetime.now(ac.TZ_TR)
    if _cron_slot(last_dt) != _cron_slot(now):
        return None
    utc = now.astimezone(timezone.utc)
    next_slot_h = (utc.hour // _CRON_SLOT_HOURS + 1) * _CRON_SLOT_HOURS
    if next_slot_h >= 24:
        next_start = datetime(utc.year, utc.month, utc.day, tzinfo=timezone.utc) + timedelta(days=1)
        next_start = next_start.replace(minute=10)
    else:
        next_start = utc.replace(hour=next_slot_h, minute=10, second=0, microsecond=0)
    return max((next_start - utc).total_seconds() / 3600.0, 0.05)


def build_user_prompt(digest: dict, prev_entries: list[dict]) -> str:
    slim = dict(digest)
    parts = [
        "CEM01 grafik anlık + pencere (JSON):",
        json.dumps(slim, ensure_ascii=False, indent=None, allow_nan=False),
    ]
    prev = [{"ts": e.get("ts"), "summary": e.get("summary")} for e in prev_entries if e.get("summary")]
    if prev:
        parts.append("\nSenin önceki notların (en yeni üstte):")
        parts.append(json.dumps(prev, ensure_ascii=False, indent=None))
    return "\n".join(parts)


def main() -> int:
    if not ac.ANTHROPIC_KEY:
        print("[forex_analyst] ANTHROPIC_API_KEY eksik", file=sys.stderr)
        return 1
    force = os.environ.get("FOREX_ANALYST_FORCE", "").strip().lower() in ("1", "true", "yes")
    remaining = _cooldown_remaining_hours()
    if remaining is not None and not force:
        mins = max(1, int(remaining * 60))
        print(f"[forex_analyst] Bu 3s pencerede zaten not var — ~{mins} dk sonra.")
        return 0

    digest = build_digest()
    prev = read_feed(_JOURNAL_LIMIT)
    try:
        commentary = ac.call_claude(SYSTEM_PROMPT, build_user_prompt(digest, prev))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[forex_analyst] Claude başarısız: {e}", file=sys.stderr)
        return 1
    if not commentary:
        print("[forex_analyst] Claude boş yanıt.", file=sys.stderr)
        return 1

    body = commentary
    summary = ""
    if "ÖZET:" in commentary:
        body, _, summary = commentary.rpartition("ÖZET:")
        body, summary = body.strip(), summary.strip()

    now_str = datetime.now(ac.TZ_TR).strftime("%d.%m %H:%M")
    title = f"Forex CEM01 Analist — {now_str}"
    tg_text = f"\U0001f4c8 {title}\n\n{body}"
    if os.environ.get("ANALYST_SKIP_TELEGRAM"):
        ac.log_telegram_text(tg_text)
    elif ac.TG_CHAT and ac.TG_TOKEN:
        try:
            ac.send_telegram(tg_text)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"[forex_analyst] Telegram yok: {e}", file=sys.stderr)
    else:
        ac.log_telegram_text(tg_text)
        print("[forex_analyst] Telegram chat yok — yalnız feed.", file=sys.stderr)

    _append_feed({
        "ts": datetime.now(ac.TZ_TR).isoformat(),
        "kind": "periodic",
        "title": title,
        "body": body,
        "summary": summary or body[:300],
        "tags": ["cem01", "xauusd"],
    })
    print("[forex_analyst] Tamamlandı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
