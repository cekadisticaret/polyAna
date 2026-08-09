"""Poly Algo Analist — Günlük Rapor. Tüm defterlerin (A1, A6 ailesi, A2#01-17, A10,
A15, B1#01/02) günlük performansını ve o gün eşik atlayan (watch/confident) yeni
kalıpları özetler, Anthropic API ile doğal dilde rapor üretir, Telegram'a gönderir.

Sayılar `algo_pattern_stats.py` tarafından hesaplanır; Claude sadece anlatır, sayı
uydurmaz. Ham istatistik tablosu şeffaflık için mesajın sonuna kod tarafından
(değişmeden) eklenir.

Cron: günde bir — `0 21 * * *` (UTC) = 00:00 İST
"""
import json
import os
import sys
import urllib.error
from datetime import datetime

import analyst_common as ac
from algo_pattern_stats import (
    compute_pattern_stats,
    daily_book_summary,
    diff_newly_significant,
    load_pattern_stats,
    save_pattern_stats,
    significant_patterns,
)

_REPORTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analyst_daily_reports.jsonl")
_REPORTS_MAX_LINES = 1000
_JOURNAL_LIMIT = 5

SYSTEM_PROMPT = """Sen Cem'in Polymarket sanal algoritmik trading defterlerini (A1, A6/A6V2/A6V3,
A2#01-17, A10, A15, B1#01/02) takip eden analist arkadaşısın. Bu senin GÜNLÜK RAPORUN —
3 saatlik kısa yorumlardan farklı olarak, günün genel tablosunu ve varsa yeni doğrulanan
kalıpları özetleyen daha kapsamlı ama yine samimi bir mesaj.

Sayılar (win_rate, pnl, N, tier, güven aralığı) SANA ÖNCEDEN HESAPLANMIŞ olarak veriliyor.
Bunları ASLA değiştirme, kendi yüzdeni uydurma — sadece olduğu gibi aktar ve yorumla.
tier alanı: "confident" (N>=20, güvenilir kalıp), "watch" (N=8-19, henüz erken izleniyor).

Görevin:
1. Günün genel tablosunu 2-3 cümlede özetle: hangi defterler bugün aktifti, en iyi/kötü
   performans kimdeydi (n_today, wr_today_pct, pnl_today alanlarına bak).
2. "newly_significant" bölümünde bugün eşik atlayan (yeni watch veya confident olan)
   kalıp varsa MUTLAKA vurgula — bu, "artık güvenilir hale geldi" ya da "izlemeye
   değer yeni bir eğilim çıktı" demek. N ve kazanma oranını olduğu gibi ver.
3. Hiç yeni kalıp yoksa bunu da söyle, "bugün yeni bir şey çıkmadı ama mevcut X kalıbı
   hâlâ geçerli" gibi devam eden önemli kalıplara değinebilirsin.
4. Önceki günlük raporlarını oku, tekrar etme, devamlılık kur (örn. "dün bahsettiğim
   X hâlâ geçerli / değişti").
5. Toplam 5-8 cümle, Türkçe, doğal, teknik jargonu abartma. Rapor gibi değil, sohbet
   eder gibi ama net bilgi verecek şekilde yaz.

Yanıtının SONUNA ayrı bir satırda, bir sonraki rapor için kısa özet ekle:
ÖZET: <tek cümle>"""


def _format_raw_table(day_summary: list[dict], newly: dict) -> str:
    lines = ["📊 Ham veri:"]
    active = [r for r in day_summary if r["n_today"]]
    for r in active[:20]:
        lines.append(
            f"  {r['label']}: bugün {r['n_today']} işlem, WR {r['wr_today_pct']}%, "
            f"PnL {r['pnl_today']:+.1f} | toplam {r['n_total']} işlem, WR {r['wr_total_pct']}%"
        )
    if newly["pairwise"] or newly["indicator"]:
        lines.append("\n🆕 Bugün eşik atlayan kalıplar:")
        for r in newly["pairwise"]:
            lines.append(
                f"  {json.dumps([r['book_a'], r['book_b']])}: anlaştıklarında "
                f"N={r['n_agree']} WR={r['win_rate_when_agree_pct']}% [{r['tier_agree']}]"
            )
        for r in newly["indicator"]:
            lines.append(
                f"  {r['book']} oybirliği: N={r['n_unanimous']} WR={r['win_rate_unanimous_pct']}% "
                f"[{r['tier_unanimous']}]"
            )
    return "\n".join(lines)


def _fetch_prev_reports(limit: int = _JOURNAL_LIMIT) -> list[dict]:
    if not os.path.exists(_REPORTS_FILE):
        return []
    try:
        with open(_REPORTS_FILE, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
    except Exception:
        return []
    return lines[-limit:][::-1]


def _append_report(entry: dict) -> None:
    lines: list[str] = []
    if os.path.exists(_REPORTS_FILE):
        try:
            with open(_REPORTS_FILE, encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            lines = []
    lines.append(json.dumps(entry, ensure_ascii=False) + "\n")
    if len(lines) > _REPORTS_MAX_LINES:
        lines = lines[-_REPORTS_MAX_LINES:]
    with open(_REPORTS_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def build_user_prompt(day_summary: list[dict], newly: dict, sig: dict, prev_reports: list[dict]) -> str:
    payload = {
        "date_tr": datetime.now(ac.TZ_TR).strftime("%Y-%m-%d"),
        "day_summary": [r for r in day_summary if r["n_today"]],
        "newly_significant": newly,
        "all_current_significant_patterns": sig,
    }
    parts = [
        "Günlük veri (JSON):",
        json.dumps(payload, ensure_ascii=False, indent=None),
    ]
    if prev_reports:
        parts.append("\nÖnceki günlük raporların (en yeni üstte):")
        parts.append(json.dumps(prev_reports, ensure_ascii=False, indent=None))
    return "\n".join(parts)


def main() -> int:
    missing = ac.required_env_missing()
    if missing:
        print(f"[daily_report] Eksik env: {missing}", file=sys.stderr)
        return 1

    before = load_pattern_stats()
    try:
        after = compute_pattern_stats()
    except Exception as e:
        print(f"[daily_report] pattern_stats hesaplanamadı: {e}", file=sys.stderr)
        return 1
    save_pattern_stats(after)

    day_summary = daily_book_summary()
    if not any(r["n_today"] for r in day_summary):
        print("[daily_report] Bugün hiç işlem yok, atlanıyor.")
        return 0

    newly = diff_newly_significant(before, after, min_tier="watch")
    sig = significant_patterns(after, min_tier="watch")
    prev_reports = _fetch_prev_reports()

    user_prompt = build_user_prompt(day_summary, newly, sig, prev_reports)
    try:
        commentary = ac.call_claude(SYSTEM_PROMPT, user_prompt, max_tokens=4096)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[daily_report] Claude çağrısı başarısız: {e}", file=sys.stderr)
        return 1

    if not commentary:
        print("[daily_report] Claude boş yanıt döndürdü.", file=sys.stderr)
        return 1

    summary_line = ""
    body = commentary
    if "ÖZET:" in commentary:
        body, _, summary_line = commentary.rpartition("ÖZET:")
        body = body.strip()
        summary_line = summary_line.strip()

    raw_table = _format_raw_table(day_summary, newly)
    today_str = datetime.now(ac.TZ_TR).strftime("%d.%m.%Y")
    tg_text = f"📅 Poly Algo Analist — Günlük Rapor ({today_str})\n\n{body}\n\n{raw_table}"
    # Telegram mesaj limiti ~4096 karakter — güvenli kırp
    if len(tg_text) > 4000:
        tg_text = tg_text[:3990] + "\n…(kırpıldı)"
    try:
        ac.send_telegram(tg_text)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"[daily_report] Telegram gönderilemedi: {e}", file=sys.stderr)

    entry = {
        "ts": datetime.now(ac.TZ_TR).isoformat(),
        "date_tr": today_str,
        "text": summary_line or body[:400],
        "n_newly_significant": len(newly["pairwise"]) + len(newly["indicator"]),
    }
    _append_report(entry)

    print("[daily_report] Tamamlandı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
