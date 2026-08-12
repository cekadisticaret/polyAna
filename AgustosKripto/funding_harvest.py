#!/usr/bin/env python3
"""Funding hasadı tarayıcısı — delta-nötr fırsat listesi.

Neden: 118 sanal defterin 20.816 işleminde yön kenarı ölçülemedi
(kaldıraçsız ortalama getiri −0,0042%, t=−0,96) ama gidiş-dönüş komisyon
0,10%. Yön tahmininden kâr çıkmıyor. Funding ise yapısal bir gelir:
perp pozisyonu 8 saatte bir ödeme alır/verir ve delta-nötr kurulduğunda
fiyat yönünden bağımsızdır.

Bu modül EMİR GÖNDERMEZ. Sadece tarar, skorlar, raporlar ve isteğe bağlı
Telegram'a gönderir. Gerçek pozisyon açma bilinçli olarak dışarıda.

CLI:
  python3 AgustosKripto/funding_harvest.py scan
  python3 AgustosKripto/funding_harvest.py scan --top 20 --min-volume 20
  python3 AgustosKripto/funding_harvest.py report          # Telegram'a gönder
  python3 AgustosKripto/funding_harvest.py history SOLUSDT
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)
sys.path.insert(0, _DIR)

_ENV_FILE = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from binance_futures_client import BinanceFuturesClient  # noqa: E402

_TZ_TR = ZoneInfo("Europe/Istanbul")
LABEL = "Funding Hasadı"
STATE_FILE = os.path.join(_DIR, "funding_harvest_state.json")

# Varsayılan funding periyodu 8 saat, ama volatil altlarda 4 saat.
# Gerçek değer /fapi/v1/fundingInfo → fundingIntervalHours ile alınır;
# yanlış interval yıllık getiriyi 2 katına şişirir.
DEFAULT_INTERVAL_H = 8.0

# Delta-nötr kurulum maliyeti: iki bacak × (giriş + çıkış) maker komisyonu.
# Binance USDⓈ-M maker %0.02, spot maker %0.10 (BNB indirimi hariç).
# Muhafazakâr varsayım: toplam %0.08 round-trip.
ROUNDTRIP_COST_PCT = float(os.environ.get("FUNDING_ROUNDTRIP_COST", "0.08"))
# Bu eşiğin altındaki |funding| gürültü sayılır
MIN_ABS_RATE_PCT = float(os.environ.get("FUNDING_MIN_RATE", "0.03"))
# 24s quote hacmi (milyon USDT) — likidite filtresi
MIN_QUOTE_VOL_M = float(os.environ.get("FUNDING_MIN_VOLUME_M", "20"))

BOT_TOKEN = os.getenv("TELEGRAM_LAB_BOT_TOKEN", os.getenv("TELEGRAM_ANALIZ4_BOT_TOKEN", ""))
CHAT_ID = os.getenv("TELEGRAM_LAB_CHAT_ID", os.getenv("TELEGRAM_CHAT", ""))


def _tg(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[{LABEL}] Telegram anahtarı yok — gönderilmedi")
        return False
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        with urllib.request.urlopen(url, data=data, timeout=20) as r:
            r.read()
        return True
    except Exception as e:
        print(f"[{LABEL}] Telegram: {e}")
        return False


def fetch_universe(client: BinanceFuturesClient | None = None) -> list[dict]:
    """Tüm USDT perp'ler için funding + interval + 24s hacim."""
    c = client or BinanceFuturesClient()
    prem = c.premium_index()
    if isinstance(prem, dict):
        prem = [prem]

    # Sembol başına funding periyodu (4sa / 8sa)
    interval: dict[str, float] = {}
    try:
        for fi in c.funding_info():
            sym = str(fi.get("symbol") or "")
            h = float(fi.get("fundingIntervalHours") or 0)
            if sym and h > 0:
                interval[sym] = h
    except Exception as e:
        print(f"[{LABEL}] fundingInfo: {e}")

    # 24s hacim — likidite filtresi için
    vol: dict[str, float] = {}
    try:
        for t in c.get("/fapi/v1/ticker/24hr"):
            vol[str(t.get("symbol") or "")] = float(t.get("quoteVolume") or 0)
    except Exception as e:
        print(f"[{LABEL}] 24hr ticker: {e}")

    out = []
    for x in prem:
        sym = str(x.get("symbol") or "")
        if not sym.endswith("USDT"):
            continue
        try:
            rate = float(x.get("lastFundingRate") or 0)
            mark = float(x.get("markPrice") or 0)
            index = float(x.get("indexPrice") or 0)
        except (TypeError, ValueError):
            continue
        if mark <= 0:
            continue
        rate_pct = rate * 100.0
        iv = interval.get(sym, DEFAULT_INTERVAL_H)
        per_day = 24.0 / iv
        # Pozitif funding → longlar öder → SHORT perp tahsil eder
        side = "SHORT perp" if rate_pct > 0 else "LONG perp"
        basis_pct = ((mark - index) / index * 100.0) if index > 0 else 0.0
        out.append({
            "symbol": sym,
            "rate_pct": rate_pct,
            "abs_rate_pct": abs(rate_pct),
            "interval_h": iv,
            "daily_pct": abs(rate_pct) * per_day,
            "apr_pct": abs(rate_pct) * per_day * 365,
            "collect_side": side,
            "mark": mark,
            "index": index,
            "basis_pct": basis_pct,
            "quote_vol_m": vol.get(sym, 0.0) / 1e6,
            "next_funding_ms": x.get("nextFundingTime"),
        })
    return out


def breakeven_periods(row: dict) -> float | None:
    """Kurulum maliyetini kaç funding periyodunda geri alır?"""
    r = row.get("abs_rate_pct") or 0
    if r <= 0:
        return None
    return ROUNDTRIP_COST_PCT / r


def score(row: dict) -> float:
    """Basit skor: yıllık getiri × likidite güveni.

    Aşırı funding genelde aşırı yön baskısını yansıtır ve kalıcı olmaz;
    bu yüzden hacim düşükse skor sertçe cezalandırılır.
    """
    apr = row.get("apr_pct") or 0
    vol = row.get("quote_vol_m") or 0
    liq = min(1.0, vol / max(MIN_QUOTE_VOL_M, 1e-9))
    return apr * liq


def scan(
    *,
    top: int = 15,
    min_volume_m: float | None = None,
    min_rate_pct: float | None = None,
) -> dict:
    minv = MIN_QUOTE_VOL_M if min_volume_m is None else float(min_volume_m)
    minr = MIN_ABS_RATE_PCT if min_rate_pct is None else float(min_rate_pct)

    universe = fetch_universe()
    for r in universe:
        r["breakeven_periods"] = breakeven_periods(r)
        r["score"] = score(r)

    eligible = [
        r for r in universe
        if r["abs_rate_pct"] >= minr and r["quote_vol_m"] >= minv
    ]
    eligible.sort(key=lambda r: r["score"], reverse=True)

    rates = sorted(r["rate_pct"] for r in universe)
    median = rates[len(rates) // 2] if rates else 0.0

    return {
        "ok": True,
        "scanned_at_tr": datetime.now(_TZ_TR).isoformat(),
        "universe_n": len(universe),
        "median_rate_pct": median,
        "filters": {
            "min_abs_rate_pct": minr,
            "min_quote_vol_m": minv,
            "roundtrip_cost_pct": ROUNDTRIP_COST_PCT,
        },
        "eligible_n": len(eligible),
        "top": eligible[:top],
    }


def print_scan(res: dict) -> None:
    print(f"[{LABEL}] {res['scanned_at_tr'][:19]}")
    print(
        f"Evren: {res['universe_n']} USDT perp · medyan funding "
        f"{res['median_rate_pct']:+.4f}% / periyot"
    )
    f = res["filters"]
    print(
        f"Filtre: |funding| ≥ {f['min_abs_rate_pct']:.3f}% · "
        f"hacim ≥ ${f['min_quote_vol_m']:.0f}M · "
        f"kurulum maliyeti {f['roundtrip_cost_pct']:.2f}%"
    )
    print(f"Uygun: {res['eligible_n']} sembol")
    print()
    if not res["top"]:
        print("Eşiği geçen sembol yok — funding hasadı için uygun pencere değil.")
        return
    print(
        f"{'sembol':<16} {'funding':>10} {'per':>5} {'günlük':>9} {'yıllık':>8} "
        f"{'tahsil':>11} {'başabaş':>9} {'hacim$M':>9} {'baz%':>8}"
    )
    print("-" * 100)
    for r in res["top"]:
        be = r.get("breakeven_periods")
        be_s = f"{be:.1f} per" if be else "—"
        print(
            f"{r['symbol']:<16} {r['rate_pct']:>+10.4f} "
            f"{r.get('interval_h', 8):>4.0f}s {r['daily_pct']:>8.3f}% "
            f"{r['apr_pct']:>7.0f}% {r['collect_side']:>11} {be_s:>9} "
            f"{r['quote_vol_m']:>9.0f} {r['basis_pct']:>+8.3f}"
        )
    print()
    print(
        "Delta-nötr kurulum: tahsil yönünde perp + ters yönde spot. "
        "Yön riski yok, funding tahsil edilir."
    )
    print("Bu betik emir göndermez — yalnızca fırsat listesi üretir.")


def build_report(res: dict) -> str:
    lines = [
        f"<b>{LABEL}</b>",
        f"{res['scanned_at_tr'][:16].replace('T', ' ')} · "
        f"{res['universe_n']} perp · medyan {res['median_rate_pct']:+.4f}%/periyot",
        "",
    ]
    if not res["top"]:
        lines.append("Eşiği geçen sembol yok — uygun pencere değil.")
        return "\n".join(lines)
    lines.append(
        f"<b>Uygun {res['eligible_n']} sembol</b> "
        f"(|funding| ≥ {res['filters']['min_abs_rate_pct']:.3f}%, "
        f"hacim ≥ ${res['filters']['min_quote_vol_m']:.0f}M)"
    )
    lines.append("")
    for i, r in enumerate(res["top"][:10], 1):
        be = r.get("breakeven_periods")
        lines.append(
            f"{i}. <b>{r['symbol']}</b> {r['rate_pct']:+.4f}%"
            f"/{r.get('interval_h', 8):.0f}sa → {r['apr_pct']:.0f}%/yıl"
        )
        lines.append(
            f"    {r['collect_side']} · başabaş "
            f"{f'{be:.1f} periyot' if be else '—'} · "
            f"hacim ${r['quote_vol_m']:.0f}M"
        )
    lines.append("")
    lines.append(
        f"Kurulum maliyeti varsayımı {res['filters']['roundtrip_cost_pct']:.2f}% "
        f"(2 bacak maker round-trip)."
    )
    lines.append("Delta-nötr: tahsil yönünde perp + ters spot. Emir gönderilmedi.")
    return "\n".join(lines)


def save_snapshot(res: dict) -> None:
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(res, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[{LABEL}] snapshot: {e}")


def load_snapshot() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def show_history(symbol: str, limit: int = 30) -> None:
    """Bir sembolün geçmiş funding ödemeleri — kalıcılık kontrolü."""
    c = BinanceFuturesClient()
    rows = c.funding_rate_history(symbol, limit=limit)
    if not rows:
        print(f"[{LABEL}] {symbol} funding geçmişi yok")
        return
    vals, times = [], []
    print(f"[{LABEL}] {symbol.upper()} son {len(rows)} funding ödemesi")
    print(f"{'zaman (TR)':<20} {'oran%':>10}")
    print("-" * 32)
    for r in rows:
        try:
            ms = int(r.get("fundingTime") or 0)
            ts = datetime.fromtimestamp(ms / 1000, _TZ_TR)
            v = float(r.get("fundingRate") or 0) * 100
        except (TypeError, ValueError):
            continue
        vals.append(v)
        times.append(ms)
        print(f"{ts.strftime('%Y-%m-%d %H:%M'):<20} {v:>+10.4f}")
    if not vals:
        return
    # Periyodu ödeme zaman aralığından çıkar
    iv = DEFAULT_INTERVAL_H
    if len(times) >= 2:
        gaps = [
            (times[i] - times[i - 1]) / 3_600_000
            for i in range(1, len(times))
            if times[i] > times[i - 1]
        ]
        if gaps:
            iv = round(sorted(gaps)[len(gaps) // 2], 2) or DEFAULT_INTERVAL_H
    mean = sum(vals) / len(vals)
    same = sum(1 for v in vals if (v > 0) == (mean > 0))
    apr = mean * (24.0 / iv) * 365
    print("-" * 32)
    print(f"periyot {iv:.0f} saat · günde {24.0 / iv:.0f} ödeme")
    print(f"ortalama {mean:+.4f}% / periyot → {apr:+.0f}% / yıl")
    print(f"aynı işarette {same}/{len(vals)} periyot (kalıcılık göstergesi)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Funding hasadı tarayıcısı")
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("scan", help="Fırsatları tara ve yazdır")
    s.add_argument("--top", type=int, default=15)
    s.add_argument("--min-volume", type=float, default=None, help="24s hacim, milyon $")
    s.add_argument("--min-rate", type=float, default=None, help="min |funding| %%")
    s.add_argument("--json", action="store_true")

    r = sub.add_parser("report", help="Tara ve Telegram'a gönder")
    r.add_argument("--top", type=int, default=10)

    h = sub.add_parser("history", help="Sembolün funding geçmişi")
    h.add_argument("symbol")
    h.add_argument("--limit", type=int, default=30)

    args = ap.parse_args()
    cmd = args.cmd or "scan"

    if cmd == "history":
        show_history(args.symbol, limit=args.limit)
        return

    if cmd == "report":
        res = scan(top=args.top)
        save_snapshot(res)
        txt = build_report(res)
        print(txt)
        print()
        print("gönderildi" if _tg(txt) else "gönderilemedi")
        return

    res = scan(
        top=args.top,
        min_volume_m=args.min_volume,
        min_rate_pct=args.min_rate,
    )
    save_snapshot(res)
    if getattr(args, "json", False):
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print_scan(res)


if __name__ == "__main__":
    main()
