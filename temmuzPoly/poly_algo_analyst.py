"""Poly Algo Analist — periyodik çalışır, Poly sanal algoritmalarını (A1, A6 ailesi,
A2#01-17, A10, A15, B1#01/02) karşılaştırır, Anthropic API ile doğal dilde yorum/fikir
üretir, Telegram'a gönderir ve kısa özetini journal'a kaydeder.

İstatistiksel sayılar (kazanma oranı, güven aralığı) `algo_pattern_stats.py` tarafından
önceden hesaplanır; Claude bu sayıları YORUMLAR ama DEĞİŞTİRMEZ.

Cron: her 3 saatte bir — `0 */3 * * *`
"""
import json
import os
import sys
import urllib.error
from datetime import datetime

import analyst_common as ac
from algo_pattern_stats import compute_pattern_stats, significant_patterns

_DIGEST_HOURS = 6
_DIGEST_LIMIT = 15
_JOURNAL_LIMIT = 8

_FIELD_NOTES = """Alan açıklamaları:
- predicted_dir / actual_dir: algoritmanın tahmini yön ve gerçekleşen yön (UP/DOWN)
- win: tahmin doğru muydu; pnl: o işlemin kâr/zararı (defter parası, gerçek para değil)
- ind_rsi_vote / ind_macd_vote / ind_ema_vote: RSI, MACD, EMA indikatörlerinin yön oyu;
  ind_*_ok: o indikatörün oyu nihai kararla (predicted_dir) uyuştu mu
- algo_signal / algo_name / algo_num: işlemi tetikleyen alt algoritmanın adı/numarası (A2 ailesi gibi çoklu alt algoritma barındıran defterlerde)
- score: karar skoru (varsa)
- entry_is_weekend / entry_dow / entry_hour_tr: giriş zamanı bağlamı
- close_reason: pozisyonun neden kapandığı (süre doldu, stop, vb.)
- wr_all_time / wr_in_window: tüm zamanlar ve pencere içi kazanma yüzdesi

pattern_stats bölümündeki sayılar (win_rate_when_agree_pct, win_rate_unanimous_pct vb.)
ÖNCEDEN KODLA hesaplandı, Wilson güven aralığıyla birlikte geliyor. tier alanı:
"confident" (N>=20, güvenilir), "watch" (N=8-19, erken ama izleniyor). Bu sayıları
ASLA değiştirme veya kendi tahminini uydurma — sadece olduğu gibi aktar ve yorumla.
"""

SYSTEM_PROMPT = f"""Sen Cem'in Polymarket üzerinde çalışan sanal algoritmik trading defterlerini
(A1, A6/A6V2/A6V3, A2#01-17, A10, A15, B1#01/02) takip eden, ona doğal dilde fikir/gözlem
sunan bir analist arkadaşsın. Robot gibi rapor yazma; "Cem, son birkaç saatte..." tarzı
samimi ama net bir üslup kullan. Kuru istatistik listeleme, gerçekten yorum yap.

{_FIELD_NOTES}

Görevin:
1. Verilen JSON'daki defterler (books) arasında aynı sembol/saat diliminde farklı yön veya
   farklı sonuç üreten örnekleri bul (ör. biri UP dedi biri DOWN dedi, ya da ikisi de aynı
   yönü dedi ama biri kazandı biri kaybetti).
2. ind_rsi_vote / ind_macd_vote / ind_ema_vote / algo_signal gibi alanları kullanarak BU
   farkın olası nedenini somut şekilde açıkla (örn. "A1 kararını RSI'ye ağırlık vererek
   DOWN dedi ama MACD/EMA UP diyordu, bu yüzden A6'dan ayrıştı").
3. pattern_stats'ta "confident" veya "watch" tier'ında bir kalıp varsa ve bu pencereki
   işlemlerle ilgiliyse, mutlaka değin (N ve kazanma oranını olduğu gibi ver — "confident"
   ise "artık güvenilir bir kalıp" de, "watch" ise "henüz erken ama N=X ile şu görünüyor" de).
4. Önceki journal notlarını oku — daha önce ortaya attığın bir hipotez bu sefer doğrulandı
   mı yoksa çürüdü mü, varsa belirt (devamlılık göster, sıfırdan başlama).
5. İlginç bir ayrışma yoksa bunu da olduğu gibi söyle, zorla hikaye uydurma.
6. Cevabın 3-6 cümle olsun, Türkçe, doğal, teknik jargonu abartma.

Yanıtının SONUNA ayrı bir satırda, journal'a kaydedilecek 1 cümlelik kısa özeti şu formatta ekle:
ÖZET: <tek cümle>"""


def build_user_prompt(digest: dict, journal: dict, pattern_stats: dict) -> str:
    books = [b for b in digest.get("books", []) if b.get("trades_in_window")]
    payload = {
        "generated_at_tr": digest.get("generated_at_tr"),
        "window_hours": digest.get("hours"),
        "books": books,
    }
    journal_entries = journal.get("entries", [])
    sig = significant_patterns(pattern_stats, min_tier="watch")
    parts = [
        "Son pencere verisi (JSON):",
        json.dumps(payload, ensure_ascii=False, indent=None),
        "\nÖnceden hesaplanmış kalıp istatistikleri (pattern_stats — SAYILARI DEĞİŞTİRME):",
        json.dumps(sig, ensure_ascii=False, indent=None),
    ]
    if journal_entries:
        parts.append("\nSenin önceki notların (en yeni üstte):")
        parts.append(json.dumps(journal_entries, ensure_ascii=False, indent=None))
    return "\n".join(parts)


def main() -> int:
    missing = ac.required_env_missing()
    if missing:
        print(f"[analyst] Eksik env: {missing}", file=sys.stderr)
        return 1

    try:
        digest = ac.fetch_digest(hours=_DIGEST_HOURS, limit=_DIGEST_LIMIT)
        journal = ac.fetch_journal(limit=_JOURNAL_LIMIT)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[analyst] Digest/journal alınamadı: {e}", file=sys.stderr)
        return 1

    books = [b for b in digest.get("books", []) if b.get("trades_in_window")]
    if not books:
        print("[analyst] Pencerede işlem yok, atlanıyor.")
        return 0

    try:
        pattern_stats = compute_pattern_stats()
    except Exception as e:
        print(f"[analyst] pattern_stats hesaplanamadı: {e}", file=sys.stderr)
        pattern_stats = {"pairwise": [], "indicator": []}

    user_prompt = build_user_prompt(digest, journal, pattern_stats)
    try:
        commentary = ac.call_claude(SYSTEM_PROMPT, user_prompt)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[analyst] Claude çağrısı başarısız: {e}", file=sys.stderr)
        return 1

    if not commentary:
        print("[analyst] Claude boş yanıt döndürdü.", file=sys.stderr)
        return 1

    summary_line = ""
    body = commentary
    if "ÖZET:" in commentary:
        body, _, summary_line = commentary.rpartition("ÖZET:")
        body = body.strip()
        summary_line = summary_line.strip()

    now_str = datetime.now(ac.TZ_TR).strftime("%d.%m %H:%M")
    tg_text = f"\U0001f9e0 Poly Algo Analist — {now_str}\n\n{body}"
    if os.environ.get("ANALYST_SKIP_TELEGRAM"):
        ac.log_telegram_text(tg_text)
    elif ac.TG_CHAT and ac.TG_TOKEN:
        try:
            ac.send_telegram(tg_text)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"[analyst] Telegram gönderilemedi: {e}", file=sys.stderr)
    else:
        ac.log_telegram_text(tg_text)
        print("[analyst] Telegram chat yok — yalnız feed/journal.", file=sys.stderr)

    tags = [b["key"] for b in books][:10]
    title = f"Poly Algo Analist — {now_str}"
    try:
        ac.post_journal(
            summary_line or body[:300],
            tags,
            body=body,
            title=title,
            kind="periodic",
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[analyst] Journal/feed kaydı başarısız: {e}", file=sys.stderr)

    print("[analyst] Tamamlandı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
