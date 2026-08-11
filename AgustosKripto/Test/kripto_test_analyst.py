"""Kripto Test AI Analist — periyodik çalışır, Kripto Test sanal Binance Futures
defterlerini (Poly sinyal kaynaklı, $100 marj × 6 kaldıraç, 30 coin evreni) karşılaştırır,
Anthropic API ile doğal dilde yorum üretir, ayrı bir Telegram kanalına (LAB bot) gönderir
ve tam metni yerel bir feed dosyasına kaydeder — dashboard'daki Kripto Yapay Zeka Analiz
sayfası (`/kripto/yapay-zeka-analiz`) bu dosyayı okur.

İstatistiksel sayılar burada kodla hesaplanır; Claude bu sayıları YORUMLAR ama DEĞİŞTİRMEZ.

Cron: her 3 saatte bir — `20 */3 * * *` (Poly Algo Analist'ten 20 dk kaydırılmış)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
from datetime import datetime, timedelta, timezone

_DIR = os.path.dirname(os.path.abspath(__file__))
_AGUSTOS = os.path.dirname(_DIR)
_ROOT = os.path.dirname(_AGUSTOS)
_POLY = os.path.join(_ROOT, "temmuzPoly")
for _p in (_POLY, _AGUSTOS, _DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import analyst_common as ac  # noqa: E402
import runner as test_runner  # noqa: E402

_WINDOW_HOURS = 6
_DIGEST_LIMIT = 15
_JOURNAL_LIMIT = 8
_MIN_INTERVAL_HOURS = 3.0
# Cron `20 */3 * * *` (UTC) ile hizalı 3 saatlik pencere — dakika bazlı cooldown
# her ikinci çalışmayı atlıyordu (feed :20:22'de yazılıyor, cron :20:01'de tetikleniyor).
_CRON_SLOT_HOURS = 3
_FEED_FILE = os.path.join(_DIR, "kripto_analyst_feed.jsonl")
_FEED_MAX_LINES = 500

LAB_TOKEN = os.environ.get("TELEGRAM_LAB_BOT_TOKEN", "")
LAB_CHAT = os.environ.get("TELEGRAM_LAB_CHAT_ID", "")

_TRADE_FIELDS = (
    "symbol", "side", "win", "pnl", "entry_price", "exit_price",
    "entry_time_tr", "exit_time_tr", "interval", "close_reason", "score",
)

_FIELD_NOTES = """Alan açıklamaları:
- symbol/side: işlem sembolü ve yön (LONG/SHORT); win/pnl: kazandı mı ve net kâr/zarar
  (komisyon dahil, sanal $ — gerçek para değil)
- interval: 1h veya 4h — coin+algoritma geçmiş başarıya göre otomatik seçiliyor
- close_reason: pozisyon neden kapandı (örn. "1h_close"/"4h_close" süre doldu, "atr_stop"
  zarar-stop, "lock" kâr kilidi)
- score: sinyal kaynağının (Poly algoritması) verdiği güven skoru
- wr_all_time / wr_in_window: tüm zamanlar ve pencere içi kazanma yüzdesi
- Bu defterler Poly Algo (A1/A2#xx/A6 ailesi/B1 vb.) sinyallerini kullanıp gerçek Binance
  Futures fiyat hareketini test ediyor — $100 marj × 6 kaldıraç, ATR tabanlı zarar-stop,
  30 coinlik evren (BTC/ETH/SOL/BNB/XRP vb.)
"""

SYSTEM_PROMPT = f"""Sen Cem'in Kripto Test defterlerini (Poly sinyal kaynaklı, gerçek Binance
Futures fiyat hareketiyle test edilen sanal defterler) takip eden, ona doğal dilde fikir
sunan bir analist arkadaşsın. Robot gibi rapor yazma; "Cem, bu pencerede..." tarzı samimi
ama net bir üslup kullan. Kuru istatistik listeleme, gerçekten yorum yap.

{_FIELD_NOTES}

Görevin:
1. Verilen JSON'daki defterler (books) arasında aynı coinde farklı sonuç üreten örnekleri
   bul (biri kazanırken biri kaybetmiş, ya da hepsi aynı coinde tutarlı kazanmış/kaybetmiş).
2. close_reason ve interval alanlarını kullanarak farkın olası nedenini somut şekilde açıkla
   (örn. "A2#05 1h'de ATR stop'a çarptı ama B1#01 4h'de aynı coinde pozisyonu tuttu ve kazandı").
3. Önceki notlarını oku — daha önceki bir gözlemin bu sefer doğrulandı mı yoksa çürüdü mü,
   varsa belirt (devamlılık göster, sıfırdan başlama).
4. İlginç bir ayrışma yoksa bunu da olduğu gibi söyle, zorla hikaye uydurma.
5. Cevabın 3-6 cümle olsun, Türkçe, doğal, teknik jargonu abartma.

Yanıtının SONUNA ayrı bir satırda, bir sonraki not için kısa özet ekle:
ÖZET: <tek cümle>"""


def _parse_dt(ts: str | None):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ac.TZ_TR)
        return dt
    except (ValueError, TypeError):
        return None


def _trade_row(t: dict) -> dict:
    return {k: t.get(k) for k in _TRADE_FIELDS if t.get(k) is not None}


def build_digest(hours: float = _WINDOW_HOURS, limit: int = _DIGEST_LIMIT) -> dict:
    cutoff = datetime.now(ac.TZ_TR) - timedelta(hours=hours)
    books: list[dict] = []
    for book in test_runner.ALL_BOOKS:
        hp = test_runner._history_path_for_book(book)
        if not hp:
            continue
        try:
            hist = test_runner.load_history(hp)
        except Exception:
            continue
        resolved = [t for t in hist if t.get("win") is not None]
        if not resolved:
            continue
        resolved.sort(key=lambda t: t.get("exit_time_tr") or "", reverse=True)

        def _in_window(t: dict) -> bool:
            dt = _parse_dt(t.get("exit_time_tr"))
            return dt is not None and dt >= cutoff

        recent = [t for t in resolved if _in_window(t)][:limit]
        if not recent:
            continue
        wins_all = sum(1 for t in resolved if t.get("win"))
        pnl_all = sum(float(t.get("pnl") or 0) for t in resolved)
        wins_recent = sum(1 for t in recent if t.get("win"))
        pnl_recent = sum(float(t.get("pnl") or 0) for t in recent)
        books.append({
            "key": book["uid"],
            "label": test_runner.label(book),
            "trades_all_time": len(resolved),
            "wr_all_time": round(100.0 * wins_all / len(resolved), 1),
            "pnl_all_time": round(pnl_all, 2),
            "trades_in_window": len(recent),
            "wr_in_window": round(100.0 * wins_recent / len(recent), 1),
            "pnl_in_window": round(pnl_recent, 2),
            "recent_trades": [_trade_row(t) for t in recent],
        })
    return {
        "generated_at_tr": datetime.now(ac.TZ_TR).isoformat(),
        "hours": hours,
        "books": books,
    }


def _append_feed(entry: dict) -> None:
    lines: list[str] = []
    if os.path.exists(_FEED_FILE):
        try:
            with open(_FEED_FILE, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            lines = []
    lines.append(json.dumps(entry, ensure_ascii=False) + "\n")
    if len(lines) > _FEED_MAX_LINES:
        lines = lines[-_FEED_MAX_LINES:]
    with open(_FEED_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def _read_feed(limit: int = _JOURNAL_LIMIT) -> list[dict]:
    if not os.path.exists(_FEED_FILE):
        return []
    try:
        with open(_FEED_FILE, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except Exception:
        return []
    return rows[-limit:][::-1]


def _cron_slot(dt: datetime) -> tuple:
    """3 saatlik cron penceresi (UTC, `20 */3 * * *` ile aynı hizalama)."""
    utc = dt.astimezone(timezone.utc)
    return (utc.date(), utc.hour // _CRON_SLOT_HOURS)


def _cooldown_remaining_hours() -> float | None:
    """Bu 3 saatlik pencerede zaten bildirim varsa kalan süre (saat)."""
    rows = _read_feed(limit=1)
    if not rows:
        return None
    last_dt = _parse_dt(rows[0].get("ts"))
    if not last_dt:
        return None
    now = datetime.now(ac.TZ_TR)
    if _cron_slot(last_dt) == _cron_slot(now):
        # Aynı pencere — bir sonraki cron slotuna kadar bekle
        utc = now.astimezone(timezone.utc)
        next_slot_h = (utc.hour // _CRON_SLOT_HOURS + 1) * _CRON_SLOT_HOURS
        if next_slot_h >= 24:
            next_start = datetime(
                utc.year, utc.month, utc.day, tzinfo=timezone.utc,
            ) + timedelta(days=1)
        else:
            next_start = utc.replace(hour=next_slot_h, minute=20, second=0, microsecond=0)
        remaining_h = (next_start - utc).total_seconds() / 3600.0
        return max(remaining_h, 0.05)
    return None


def build_user_prompt(digest: dict, prev_entries: list[dict]) -> str:
    books = digest["books"]
    payload = {
        "generated_at_tr": digest.get("generated_at_tr"),
        "window_hours": digest.get("hours"),
        "books": books,
    }
    parts = [
        "Son pencere verisi (JSON):",
        json.dumps(payload, ensure_ascii=False, indent=None),
    ]
    prev_summaries = [
        {"ts": e.get("ts"), "summary": e.get("summary")}
        for e in prev_entries if e.get("summary")
    ]
    if prev_summaries:
        parts.append("\nSenin önceki notların (en yeni üstte):")
        parts.append(json.dumps(prev_summaries, ensure_ascii=False, indent=None))
    return "\n".join(parts)


def main() -> int:
    if not ac.ANTHROPIC_KEY:
        print("[kripto_analyst] ANTHROPIC_API_KEY eksik", file=sys.stderr)
        return 1
    if not LAB_TOKEN or not LAB_CHAT:
        print("[kripto_analyst] TELEGRAM_LAB_BOT_TOKEN/TELEGRAM_LAB_CHAT_ID eksik", file=sys.stderr)
        return 1

    force = os.environ.get("KRIPTO_TEST_ANALYST_FORCE", "").strip().lower() in ("1", "true", "yes")
    remaining = _cooldown_remaining_hours()
    if remaining is not None and not force:
        mins = max(1, int(remaining * 60))
        print(
            f"[kripto_analyst] Bu 3 saatlik pencerede zaten bildirim var "
            f"— sonraki cron ~{mins} dk sonra.",
        )
        return 0

    digest = build_digest()
    if not digest["books"]:
        print("[kripto_analyst] Pencerede işlem yok, atlanıyor.")
        return 0

    prev_entries = _read_feed(_JOURNAL_LIMIT)
    user_prompt = build_user_prompt(digest, prev_entries)

    try:
        commentary = ac.call_claude(SYSTEM_PROMPT, user_prompt)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[kripto_analyst] Claude çağrısı başarısız: {e}", file=sys.stderr)
        return 1

    if not commentary:
        print("[kripto_analyst] Claude boş yanıt döndürdü.", file=sys.stderr)
        return 1

    summary_line = ""
    body = commentary
    if "ÖZET:" in commentary:
        body, _, summary_line = commentary.rpartition("ÖZET:")
        body = body.strip()
        summary_line = summary_line.strip()

    now_str = datetime.now(ac.TZ_TR).strftime("%d.%m %H:%M")
    title = f"Kripto Test AI Analist — {now_str}"
    tg_text = f"\U0001f9ea {title}\n\n{body}"
    try:
        ac.send_telegram_to(LAB_TOKEN, LAB_CHAT, tg_text)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[kripto_analyst] Telegram gönderilemedi: {e}", file=sys.stderr)

    tags = [b["key"] for b in digest["books"]][:10]
    entry = {
        "ts": datetime.now(ac.TZ_TR).isoformat(),
        "kind": "periodic",
        "title": title,
        "body": body,
        "summary": summary_line or body[:300],
        "tags": tags,
    }
    _append_feed(entry)

    print("[kripto_analyst] Tamamlandı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
