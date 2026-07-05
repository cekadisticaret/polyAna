"""
BIST Saatlik Sinyal Tarayıcı
BIST100 dışındaki hisseler için 6 indikatör tabanlı yükseliş sinyali.
Çalışma: BIST seans saatlerinde her saat :05'te
"""

import sys, os, math, time, json, urllib.request, urllib.error
from datetime import datetime, date
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Europe/Istanbul")

BOT_TOKEN  = "8256912678:AAFWEoRWO7Z0siK_c4Dm5XjgtBKmh-wmF8E"
CHAT_ID    = "830754964"

_DIR         = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(_DIR, "bist_scanner_history.json")

MIN_VOLUME  = 100_000   # minimum ortalama saatlik hacim (TL)
MIN_BARS    = 30        # minimum mum sayısı
TOP_N       = 10        # bildirimde gösterilecek max hisse
SCORE_STRONG   = 5      # güçlü sinyal (5-6/6)
SCORE_MODERATE = 3      # orta sinyal (3-4/6)

# ── BIST100 DışI Hisseler (likit seçim) ──────────────────────
SYMBOLS = [
    "AGHOL","AGROT","AKGRT","AKSEN","AKYHO","ALARK","ALBRK",
    "ALFAS","ALKIM","ALTNY","ANHYT","ANSGR","ARASE","ARDYZ",
    "ARENA","ARSAN","ASTOR","ATAKP","ATATP","AYEN","AYCES",
    "BASGZ","BERA","BFREN","BIENY","BIGCH","BIOEN","BIYOM",
    "BVSAN","CANTE","CEMTS","CLEBI","CSNAT","CSTLO","CWENE",
    "DAGHL","DAGI","DEAS","DEVA","DGKLB","DMSAS","DNISI",
    "DOKTA","DURDO","DYOBY","ECILC","ECZYT","EGEEN","EGPRO",
    "ENERY","ERBOS","ESCOM","ETILR","EUPWR","EYGYO","FENER",
    "FLAP","FONET","FZLGY","GARFA","GENIL","GENTS","GEREL",
    "GLYHO","GMTAS","GOLTS","GOODY","GWIND","HATEK","HEKTS",
    "HLGYO","IMASM","INDES","ISFIN","ISYHO","ITTFH","IZFAS",
    "IZTAR","JANTS","KENT","KERVT","KLGYO","KNFRT","KONYA",
    "KORDS","KRDMA","KRDMB","KRVGD","KUYAS","LEYKM","LGMYO",
    "LINK","LYDHO","MAGEN","MAKIM","MAKTK","MEGAP","MEPET",
    "MERCN","MERIT","METRO","MIATK","MOBTL","MPARK","MZHLD",
    "NATEN","NETAS","NTHOL","ODAS","ONBIO","ORGE","ORMA",
    "OSMEN","OYAKC","OYLKS","OZBAL","PEKGY","PKENT","PLTUR",
    "PNSUT","POLHO","PSGYO","RAYSG","REEDR","REYSA","RGYAS",
    "RNPOL","RODRG","ROYAL","SAFKN","SAGYO","SAMAT","SANEL",
    "SANFM","SARKY","SELEC","SELGD","SELVA","SENTE","SEYKM",
    "SILVR","SMART","SUMAS","SUWEN","TABGD","TATGD","TGSAS",
    "TKFEN","TKNSA","TLMAN","TMPOL","TRCAS","TRILC","TUCLK",
    "TURGG","TUKAS","TZNGY","UCAK","ULUUN","USAK","VAKFN",
    "VBTS","VERUS","VESBE","VKGYO","WNDW","YATAS","YBTAS",
    "YEOTK","YGYO","YYLGD","ZEDUR","ZRGYO","AEDAS","AFYON",
    "AGESA","AHGAZ","AKCNS","AKENR","AKFGY","AKSA","BRYAT",
    "BSOKE","BUCIM","BURCE","BURVA","DOHOL","EKGYO",
]

# ── Yardımcı ─────────────────────────────────────────────────
def tg_send(text: str) -> None:
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
    except Exception as e:
        print(f"[TG] Hata: {e}", file=sys.stderr)


def _ema(vals: list[float], n: int) -> list[float]:
    if not vals:
        return []
    k = 2 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _rsi(vals: list[float], n: int = 14) -> float:
    if len(vals) < n + 1:
        return 50.0
    deltas = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
    gains  = [max(d, 0) for d in deltas[-n:]]
    losses = [max(-d, 0) for d in deltas[-n:]]
    ag, al = sum(gains) / n, sum(losses) / n
    return 100 - 100 / (1 + ag / al) if al else 100.0


def _bollinger(vals: list[float], n: int = 20, k: float = 2.0):
    w = vals[-n:]
    m = sum(w) / len(w)
    s = (sum((x - m) ** 2 for x in w) / len(w)) ** 0.5
    return m + k * s, m, m - k * s


# ── Veri Çekme ───────────────────────────────────────────────
def fetch_ohlcv(symbol: str) -> list[dict] | None:
    """yfinance ile saatlik OHLCV verisi çek."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(f"{symbol}.IS")
        df = ticker.history(period="10d", interval="1h")
        if df is None or len(df) < MIN_BARS:
            return None
        rows = []
        for ts, row in df.iterrows():
            rows.append({
                "open":   float(row["Open"]),
                "high":   float(row["High"]),
                "low":    float(row["Low"]),
                "close":  float(row["Close"]),
                "volume": float(row["Volume"]),
            })
        # Hacim filtresi: son 20 barlık ortalama hacim
        avg_vol = sum(r["volume"] for r in rows[-20:]) / min(20, len(rows))
        if avg_vol < MIN_VOLUME:
            return None
        return rows
    except Exception:
        return None


# ── 6 İndikatör ──────────────────────────────────────────────
def algo_trend(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines]
    e20 = _ema(closes, 20)
    e50 = _ema(closes, 50)
    cross = e20[-1] - e50[-1]
    slope = e20[-1] - e20[-4] if len(e20) >= 4 else 0
    pct   = cross / closes[-1] * 100
    if cross > 0 and slope > 0:
        return +1, f"Trend↑ E20&gt;E50 ({pct:+.2f}%)"
    elif cross < 0 and slope < 0:
        return -1, f"Trend↓ E20&lt;E50 ({pct:+.2f}%)"
    else:
        return  0, f"Trend→ karışık ({pct:+.2f}%)"


def algo_mr(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines]
    rsi    = _rsi(closes, 14)
    upper, _, lower = _bollinger(closes, 20, 2.0)
    price  = closes[-1]
    rsi_v  = +1 if rsi <= 35 else -1 if rsi >= 65 else 0
    bb_v   = +1 if price <= lower else -1 if price >= upper else 0
    vote   = max(-1, min(1, rsi_v + bb_v))
    arr    = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    bb_lbl = "alt" if price <= lower else "üst" if price >= upper else "orta"
    return vote, f"MR{arr} RSI:{rsi:.0f} BB:{bb_lbl}"


def algo_hurst(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines[-60:]]
    if len(closes) < 20:
        return 0, "Hurst→ yetersiz"

    def rs(series):
        n    = len(series)
        mean = sum(series) / n
        dev  = [x - mean for x in series]
        cum  = []
        s = 0
        for d in dev:
            s += d
            cum.append(s)
        R   = max(cum) - min(cum)
        std = (sum((x - mean) ** 2 for x in series) / n) ** 0.5
        return R / std if std > 0 else 0

    points = []
    for w in [10, 20, 40]:
        if len(closes) >= w:
            r = rs(closes[-w:])
            if r > 0:
                points.append((math.log(w), math.log(r)))

    if len(points) < 2:
        return 0, "Hurst→ hesaplanamadı"

    xs, ys = [p[0] for p in points], [p[1] for p in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(len(xs)))
    den = sum((xs[i] - mx) ** 2 for i in range(len(xs)))
    H   = num / den if den > 0 else 0.5

    e5, e10 = _ema(closes, 5), _ema(closes, 10)
    up = e5[-1] > e10[-1]

    if H > 0.55:
        v = +1 if up else -1
        return v, f"Hurst{'↑' if up else '↓'} H={H:.2f} trend"
    elif H < 0.45:
        v = -1 if up else +1
        return v, f"Hurst{'↓' if up else '↑'} H={H:.2f} MR"
    else:
        return 0, f"Hurst→ H={H:.2f}"


def algo_kalman(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines[-50:]]
    if len(closes) < 10:
        return 0, "Kalman→ yetersiz"
    Q, R, x, P = 1e-4, 0.1, closes[0], 1.0
    sm = []
    for z in closes:
        P = P + Q
        K = P / (P + R)
        x = x + K * (z - x)
        P = (1 - K) * P
        sm.append(x)
    slope = (sm[-1] - sm[-5]) / sm[-5] * 100 if sm[-5] != 0 else 0
    if slope > 0.08:
        return +1, f"Kalman↑ {slope:+.3f}%"
    elif slope < -0.08:
        return -1, f"Kalman↓ {slope:+.3f}%"
    else:
        return  0, f"Kalman→ {slope:+.3f}%"


def algo_perm_entropy(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines[-50:]]
    m, tau = 3, 1
    if len(closes) < m * tau + 5:
        return 0, "PEnt→ yetersiz"
    patterns: dict = {}
    for i in range(len(closes) - (m - 1) * tau):
        sub  = [closes[i + j * tau] for j in range(m)]
        perm = tuple(sorted(range(m), key=lambda x: sub[x]))
        patterns[perm] = patterns.get(perm, 0) + 1
    total = sum(patterns.values())
    pe    = -sum((c / total) * math.log(c / total) for c in patterns.values())
    pe_n  = pe / math.log(math.factorial(m))
    e5, e10 = _ema(closes, 5), _ema(closes, 10)
    up = e5[-1] > e10[-1]
    if pe_n < 0.70:
        v = +1 if up else -1
        return v, f"PEnt{'↑' if up else '↓'} PE={pe_n:.2f}"
    elif pe_n > 0.90:
        return 0, f"PEnt→ kaotik PE={pe_n:.2f}"
    else:
        return 0, f"PEnt→ PE={pe_n:.2f}"


def algo_hilbert(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines[-50:]]
    n = len(closes)
    if n < 20:
        return 0, "Hilbert→ yetersiz"
    smooth = [closes[i] if i < 3 else
              (4*closes[i]+3*closes[i-1]+2*closes[i-2]+closes[i-3])/10
              for i in range(n)]
    coef, c1, adj = 0.0962, 0.5769, 0.075*1+0.54
    det = [0.0]*n
    for i in range(6, n):
        det[i] = (coef*smooth[i]+c1*smooth[i-2]-c1*smooth[i-4]-coef*smooth[i-6])*adj
    I1, Q1 = [0.0]*n, [0.0]*n
    for i in range(6, n):
        Q1[i] = (coef*det[i]+c1*det[i-2]-c1*det[i-4]-coef*det[i-6])*adj
        I1[i] = det[i-3]
    sI, sQ, a = [0.0]*n, [0.0]*n, 0.2
    for i in range(1, n):
        sI[i] = a*I1[i]+(1-a)*sI[i-1]
        sQ[i] = a*Q1[i]+(1-a)*sQ[i-1]
    def atan2d(q, iv):
        return math.degrees(math.atan2(q, iv)) if (q or iv) else 0.0
    delta = atan2d(sQ[-1], sI[-1]) - atan2d(sQ[-2], sI[-2])
    if delta >  180: delta -= 360
    if delta < -180: delta += 360
    T = abs(360/delta) if delta else 20
    if delta > 1.5:
        return +1, f"Hilbert↑ faz:+{delta:.1f}°"
    elif delta < -1.5:
        return -1, f"Hilbert↓ faz:{delta:.1f}°"
    else:
        return  0, f"Hilbert→ faz:{delta:.1f}°"


# ── Tek hisse analizi ─────────────────────────────────────────
def analyze(symbol: str) -> dict | None:
    klines = fetch_ohlcv(symbol)
    if not klines or len(klines) < MIN_BARS:
        return None
    v1, l1 = algo_trend(klines)
    v2, l2 = algo_mr(klines)
    v3, l3 = algo_hurst(klines)
    v4, l4 = algo_kalman(klines)
    v5, l5 = algo_perm_entropy(klines)
    v6, l6 = algo_hilbert(klines)
    score  = v1 + v2 + v3 + v4 + v5 + v6
    return {
        "symbol": symbol,
        "price":  klines[-1]["close"],
        "score":  score,
        "votes":  [v1, v2, v3, v4, v5, v6],
        "labels": [l1, l2, l3, l4, l5, l6],
        "volume": sum(k["volume"] for k in klines[-6:]) / 6,
    }


# ── İsabet Takibi ─────────────────────────────────────────────
def load_history() -> list:
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history: list) -> None:
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def record_signals(signals: list, hour: int, today: str) -> None:
    """Verilen sinyalleri geçmiş dosyasına kaydet."""
    history = load_history()
    for s in signals:
        history.append({
            "date":         today,
            "hour":         hour,
            "symbol":       s["symbol"],
            "score":        s["score"],
            "price_signal": s["price"],
            "price_1h":     None,
            "result":       None,
            "pct":          None,
        })
    save_history(history)


def resolve_previous_signals(hour: int, today: str) -> None:
    """Bir önceki saatin sinyallerini mevcut fiyatla kapat."""
    history = load_history()
    prev_hour = hour - 1
    pending = [e for e in history
               if e["date"] == today and e["hour"] == prev_hour and e["result"] is None]
    if not pending:
        return

    # Fiyatları çek
    for entry in pending:
        try:
            import yfinance as yf
            df = yf.Ticker(f"{entry['symbol']}.IS").history(period="1d", interval="1h")
            if df is not None and len(df) > 0:
                current = float(df["Close"].iloc[-1])
                pct     = (current - entry["price_signal"]) / entry["price_signal"] * 100
                entry["price_1h"] = round(current, 2)
                entry["pct"]      = round(pct, 2)
                # Pozitif skor → yükselmesi bekleniyor
                if entry["score"] > 0:
                    entry["result"] = "✅" if pct > 0 else "❌"
                else:
                    entry["result"] = "✅" if pct < 0 else "❌"
        except Exception:
            entry["result"] = "?"
        time.sleep(0.2)

    save_history(history)


def run_eod_report() -> None:
    """Gün sonu isabet raporu gönder (18:05)."""
    today   = date.today().isoformat()
    history = load_history()
    today_entries = [e for e in history if e["date"] == today and e["result"] is not None]

    if not today_entries:
        return

    wins  = sum(1 for e in today_entries if e["result"] == "✅")
    total = len(today_entries)
    rate  = wins / total * 100 if total else 0

    sep   = "━" * 28
    lines = [sep, f"📋 <b>BIST Günlük İsabet Raporu — {today}</b>",
             f"🎯 Başarı: {wins}/{total}  ({rate:.0f}%)"]

    # Sonuçları saate göre grupla
    by_hour: dict = {}
    for e in sorted(today_entries, key=lambda x: (x["hour"], x["symbol"])):
        h = e["hour"]
        by_hour.setdefault(h, []).append(e)

    for h, entries in by_hour.items():
        lines.append(f"\n🕐 <b>{h:02d}:05 sinyalleri</b>")
        for e in entries:
            pct_str = f"{e['pct']:+.1f}%" if e["pct"] is not None else "?"
            lines.append(
                f"  {e['result']} <b>{e['symbol']}</b>  skor:{e['score']:+d}/6  "
                f"{e['price_signal']:.2f}→{e.get('price_1h') or '?'}₺  ({pct_str})"
            )

    lines.append(sep)
    tg_send("\n".join(lines))
    print(f"[BIST Tarayıcı] Gün sonu raporu gönderildi: {wins}/{total} isabet")


# ── Ana tarama ────────────────────────────────────────────────
def run_scan() -> None:
    now_tr = datetime.now(_TZ)
    hour   = now_tr.hour
    dow    = now_tr.weekday()  # 0=Pzt, 6=Paz
    saat   = now_tr.strftime("%H:%M")

    today = now_tr.strftime("%Y-%m-%d")

    # Hafta sonu veya seans dışı → çık
    if dow >= 5 or hour < 10 or hour >= 18:
        print(f"[BIST Tarayıcı] {saat} IST — seans dışı, çıkılıyor")
        return

    # Gün sonu raporu: 18:05 çalışırsa (saat 18'de cron çalışır)
    if hour == 18:
        run_eod_report()
        return

    # Bir önceki saatin sinyallerini kapat (isabet takibi)
    if hour > 10:
        resolve_previous_signals(hour, today)

    print(f"[BIST Tarayıcı] {saat} IST — {len(SYMBOLS)} hisse taranıyor...")

    results = []
    for sym in SYMBOLS:
        try:
            sig = analyze(sym)
            if sig and sig["score"] >= SCORE_MODERATE:
                results.append(sig)
        except Exception as e:
            print(f"  {sym} hata: {e}", file=sys.stderr)
        time.sleep(0.3)  # rate limit

    # Skora göre sırala
    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:TOP_N]

    sep      = "━" * 28
    next_h   = f"{(hour+1)%24:02d}:00"

    if not top:
        tg_send(
            f"{sep}\n"
            f"📊 <b>BIST Sinyal — {saat} IST</b>\n"
            f"⏸ Bu saat güçlü sinyal bulunamadı.\n"
            f"{sep}"
        )
        print(f"[BIST Tarayıcı] Sinyal yok")
        return

    lines = [f"{sep}", f"📊 <b>BIST Sinyal — {saat} - {next_h} IST</b>"]

    strong = [r for r in top if r["score"] >= SCORE_STRONG]
    medium = [r for r in top if SCORE_MODERATE <= r["score"] < SCORE_STRONG]

    if strong:
        lines.append(f"🔥 <b>Güçlü ({len(strong)})</b>")
        for r in strong:
            vi = ["🟢" if v > 0 else "🔴" if v < 0 else "⚪" for v in r["votes"]]
            lines.append(
                f"📈 <b>{r['symbol']}</b>  skor:{r['score']:+d}/6  fiyat:{r['price']:.2f}₺\n"
                f"   {'  '.join(vi)}"
            )

    if medium:
        lines.append(f"📌 <b>Orta ({len(medium)})</b>")
        for r in medium:
            vi = ["🟢" if v > 0 else "🔴" if v < 0 else "⚪" for v in r["votes"]]
            lines.append(
                f"↗️ <b>{r['symbol']}</b>  skor:{r['score']:+d}/6  fiyat:{r['price']:.2f}₺  "
                f"{''.join(vi)}"
            )

    lines.append(f"<i>Tarama: {len(SYMBOLS)} hisse | Eşik: ≥{SCORE_MODERATE}/6</i>")
    lines.append(sep)

    tg_send("\n".join(lines))

    # Sinyalleri isabet takibi için kaydet
    record_signals(top, hour, today)

    print(f"[BIST Tarayıcı] {saat} — {len(strong)} güçlü, {len(medium)} orta sinyal gönderildi")


if __name__ == "__main__":
    run_scan()
