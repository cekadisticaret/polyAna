"""
BIST Saatlik Sinyal Tarayıcı — v2 (BIST Özelleştirilmiş)

6 BIST-spesifik indikatör:
  1. EMA Crossover  (5/15 saatlik) — hızlı trend
  2. RSI Bölgesi   (14, 35/65)    — momentum/aşırı bölge
  3. Hacim Onayı   (10-bar avg)   — hacim olmayan sinyal geçersiz
  4. VWAP Pozisyon (günlük)       — BIST'in en güçlü intraday filtresi
  Analiz 1 (poly_predictor_analysis) mantığı BIST'e uyarlandı:
  - Momentum yerine Mean Reversion (dip yakalama)
  - RSI5 oversold + Bollinger alt band = ana giriş sinyali
  - MACD histogram dönüşü = momentum teyidi
  - EMA15/50 trend filtresi + VWAP + Hacim kalitesi

Sonuç penceresi: 4h (1h çok kısa; 4h'te başarı daha anlamlı)
Eşik: ≥5/8 güçlü, 4/8 orta
"""

import sys, os, time, json, urllib.request, urllib.error
from datetime import datetime, date
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Europe/Istanbul")

BOT_TOKEN  = "8256912678:AAFWEoRWO7Z0siK_c4Dm5XjgtBKmh-wmF8E"
CHAT_ID    = "830754964"

_DIR         = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(_DIR, "bist_scanner_history.json")

MIN_VOLUME     = 50_000   # minimum saatlik hacim (TL)
MIN_BARS       = 30       # minimum mum sayısı (MACD için 26+ gerekli)
TOP_N          = 10       # bildirimde gösterilecek max hisse
SCORE_STRONG   = 5        # güçlü sinyal (5+/8 max)
SCORE_MODERATE = 4        # orta sinyal (4/8)

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

# ── Teknik yardımcılar ───────────────────────────────────────
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
    deltas = [vals[i] - vals[i-1] for i in range(1, len(vals))]
    gains  = [max(d, 0) for d in deltas[-n:]]
    losses = [max(-d, 0) for d in deltas[-n:]]
    ag, al = sum(gains)/n, sum(losses)/n
    return 100 - 100/(1 + ag/al) if al else 100.0


def _bollinger(vals: list[float], n: int = 20, k: float = 1.5):
    w = vals[-n:] if len(vals) >= n else vals
    m = sum(w) / len(w)
    s = (sum((x-m)**2 for x in w) / len(w)) ** 0.5
    return m + k*s, m, m - k*s


def _vwap(klines: list[dict]) -> float:
    """Günlük VWAP: son 8 bar (≈ günün başından itibaren)."""
    window = klines[-8:]
    num = sum(((k["high"]+k["low"]+k["close"])/3) * k["volume"] for k in window)
    den = sum(k["volume"] for k in window)
    return num / den if den > 0 else klines[-1]["close"]


def _macd(closes: list[float]) -> tuple[float, float, float]:
    """MACD (12,26,9). Returns: (macd_line, signal_line, histogram)."""
    if len(closes) < 26:
        return 0.0, 0.0, 0.0
    e12 = _ema(closes, 12)
    e26 = _ema(closes, 26)
    macd_line = [e12[i] - e26[i] for i in range(len(e26))]
    signal    = _ema(macd_line, 9)
    hist      = macd_line[-1] - signal[-1]
    return macd_line[-1], signal[-1], hist


# ── Poly-Predictor İlhamlı BIST İndikatörleri (v3) ────────────
# RSI5 MR + BB dokunuş max +2; diğerleri max +1 → toplam max 8
IND_NAMES = ["RSI5-MR", "BB-Dip", "MACD-Dönüş", "VWAP", "EMA-Trend", "Hacim"]


def algo_rsi5_mr(klines: list[dict]) -> tuple[int, str]:
    """
    RSI5 Mean Reversion — poly_predictor'ın ana katmanı.
    Oversold bölge = potansiyel dip = AL sinyali.
    Overbought = riskli, sinyal yok (BIST long-only).
    """
    closes   = [k["close"] for k in klines]
    rsi5     = _rsi(closes, 5)
    rsi5_prev = _rsi(closes[:-2], 5) if len(closes) > 7 else rsi5
    rsi5_dir  = rsi5 - rsi5_prev  # pozitif = toparlanıyor

    if rsi5 < 20:
        return +2, f"RSI5:{rsi5:.0f} aşırı satım (güçlü dip)"
    elif rsi5 < 35 and rsi5_dir >= 0:
        return +1, f"RSI5:{rsi5:.0f}↑ satım toparlanıyor"
    elif rsi5 < 35:
        return +1, f"RSI5:{rsi5:.0f} satım bölgesi"
    elif rsi5 > 78:
        return -1, f"RSI5:{rsi5:.0f} aşırı alım, riskli"
    else:
        return  0, f"RSI5:{rsi5:.0f} nötr"


def algo_bollinger_dip(klines: list[dict]) -> tuple[int, str]:
    """
    Bollinger Band (20, 2σ) dip dokunuşu.
    Alt banda yakın/altında → güçlü MR sinyali.
    Üst banda yakın → direnç.
    """
    closes     = [k["close"] for k in klines]
    upper, mid, lower = _bollinger(closes, 20, 2.0)
    price      = closes[-1]
    price_prev = closes[-2] if len(closes) > 1 else price
    pos        = (price - lower) / (upper - lower) if upper != lower else 0.5

    if price <= lower:
        return +2, f"BB:alt altında pos:{pos:.2f} (güçlü dip)"
    elif pos < 0.20:
        recovery = price >= price_prev
        return +1, f"BB:dip{'↑' if recovery else ''} pos:{pos:.2f}"
    elif pos > 0.85:
        return -1, f"BB:üst direnç pos:{pos:.2f}"
    else:
        return  0, f"BB:nötr pos:{pos:.2f}"


def algo_macd_turn(klines: list[dict]) -> tuple[int, str]:
    """
    MACD histogram dönüşü — momentum teyidi.
    Negatiften pozitife dönen histogram = en güçlü al sinyali.
    """
    closes = [k["close"] for k in klines]
    _, _, hist      = _macd(closes)
    _, _, hist_prev = _macd(closes[:-1]) if len(closes) > 27 else (0, 0, hist)
    turning_up = hist > hist_prev

    if hist < 0 and turning_up:
        return +1, f"MACD↑ dip dönüşü hist:{hist:.4f}"
    elif hist >= 0 and turning_up:
        return +1, f"MACD↑ pozitif hist:{hist:.4f}"
    elif hist < 0 and not turning_up:
        return -1, f"MACD↓ düşüş hist:{hist:.4f}"
    else:
        return  0, f"MACD→ nötr hist:{hist:.4f}"


def algo_vwap(klines: list[dict]) -> tuple[int, str]:
    """
    VWAP pozisyonu — kurumsal referans.
    Fiyat VWAP altında = ucuz / VWAP üstü = pahalı.
    """
    vwap  = _vwap(klines)
    price = klines[-1]["close"]
    diff  = (price - vwap) / vwap

    if diff < -0.005:
        return +1, f"VWAP↓ ucuz ({diff*100:+.2f}%) VWAP:{vwap:.2f}"
    elif diff > 0.005:
        return -1, f"VWAP↑ pahalı ({diff*100:+.2f}%) VWAP:{vwap:.2f}"
    else:
        return  0, f"VWAP→ yakın ({diff*100:+.2f}%)"


def algo_ema_trend(klines: list[dict]) -> tuple[int, str]:
    """
    EMA15/50 orta vadeli trend filtresi.
    Trend yukarıdaysa dip alım anlamlı; trend aşağıdaysa riskli.
    """
    closes = [k["close"] for k in klines]
    e15    = _ema(closes, 15)
    e50    = _ema(closes, 50) if len(closes) >= 50 else e15
    slope15 = (e15[-1] - e15[-3]) / e15[-3] * 100 if len(e15) >= 3 else 0

    if e15[-1] > e50[-1] and slope15 > 0:
        return +1, f"EMA↑ 15>50 slope:{slope15:+.2f}%"
    elif e15[-1] < e50[-1] and slope15 < 0:
        return -1, f"EMA↓ trend aşağı slope:{slope15:+.2f}%"
    else:
        return  0, f"EMA→ karışık slope:{slope15:+.2f}%"


def algo_volume_quality(klines: list[dict]) -> tuple[int, str]:
    """
    Hacim kalitesi — MR için tersine çevrilmiş mantık.
    Düşük hacimde düşüş (satış baskısı yok) → dip yakın.
    Yüksek hacimde toparlanma → kurumsal alım.
    """
    vols     = [k["volume"] for k in klines]
    avg_vol  = sum(vols[-10:]) / 10 if len(vols) >= 10 else sum(vols)/len(vols)
    recent   = sum(vols[-3:]) / 3 if len(vols) >= 3 else vols[-1]
    last_bar = klines[-1]
    bullish  = last_bar["close"] > last_bar["open"]
    ratio    = recent / avg_vol if avg_vol > 0 else 1.0

    if bullish and ratio >= 1.3:
        return +1, f"Hacim↑ toparlanma ×{ratio:.1f}"
    elif not bullish and ratio < 0.7:
        return +1, f"Hacim→ sessiz düşüş ×{ratio:.1f} (baskı yok)"
    elif not bullish and ratio >= 1.5:
        return -1, f"Hacim↓ satış baskısı ×{ratio:.1f}"
    else:
        return  0, f"Hacim→ normal ×{ratio:.1f}"


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


# ── Tek hisse analizi ─────────────────────────────────────────
def analyze(symbol: str) -> dict | None:
    klines = fetch_ohlcv(symbol)
    if not klines or len(klines) < MIN_BARS:
        return None
    v1, l1 = algo_rsi5_mr(klines)
    v2, l2 = algo_bollinger_dip(klines)
    v3, l3 = algo_macd_turn(klines)
    v4, l4 = algo_vwap(klines)
    v5, l5 = algo_ema_trend(klines)
    v6, l6 = algo_volume_quality(klines)
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
            "votes":        s["votes"],
            "price_signal": s["price"],
            "price_1h":     None,
            "price_2h":     None,
            "price_3h":     None,
            "price_4h":     None,
            "pct_1h":       None,
            "pct_2h":       None,
            "pct_3h":       None,
            "pct_4h":       None,
            "result":       None,
            "pct":          None,
        })
    save_history(history)


def _get_current_price(symbol: str) -> float | None:
    """yfinance ile anlık fiyat çek."""
    try:
        import yfinance as yf
        df = yf.Ticker(f"{symbol}.IS").history(period="1d", interval="1h")
        if df is not None and len(df) > 0:
            return round(float(df["Close"].iloc[-1]), 4)
    except Exception:
        pass
    return None


def resolve_previous_signals(hour: int, today: str) -> None:
    """
    1-4 saat önceki sinyallerin fiyatlarını güncelle.
    Her saat çalışır, offset kadar önceki sinyalin Nh alanını doldurur.
    """
    history = load_history()
    updated = False

    for offset in range(1, 5):
        target_hour = hour - offset
        if target_hour < 0:
            continue
        field_p = f"price_{offset}h"
        field_pct = f"pct_{offset}h"

        for entry in history:
            if (entry["date"] != today
                    or entry["hour"] != target_hour
                    or entry.get(field_p) is not None):
                continue
            price = _get_current_price(entry["symbol"])
            if price is None:
                continue
            pct = (price - entry["price_signal"]) / entry["price_signal"] * 100
            entry[field_p]   = round(price, 2)
            entry[field_pct] = round(pct, 2)

            # Win/loss 4 saatlik sonuca göre belirlenir (1h çok kısa)
            if offset == 4:
                entry["pct"]    = round(pct, 2)
                entry["result"] = "✅" if pct > 0 else "❌"
            updated = True
            time.sleep(0.15)

    if updated:
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
             f"🎯 Genel Başarı: {wins}/{total}  ({rate:.0f}%)"]

    # ── İndikatör bazında isabet istatistiği ──
    # Sadece sonucu belli (✅/❌) olan girişler
    resolved = [e for e in today_entries if e["result"] in ("✅", "❌")]
    if resolved:
        lines.append("\n📊 <b>İndikatör İsabeti:</b>")
        for i, name in enumerate(IND_NAMES):
            ind_wins = ind_total = 0
            for e in resolved:
                votes = e.get("votes", [])
                if i >= len(votes) or votes[i] == 0:
                    continue  # bu indikatör nötr oy vermiş, saymıyoruz
                ind_total += 1
                # İndikatörün oyu doğruysa: oy yönü ile gerçek hareket aynı
                correct = (votes[i] > 0 and e["pct"] > 0) or (votes[i] < 0 and e["pct"] < 0)
                if correct:
                    ind_wins += 1
            if ind_total > 0:
                r = ind_wins / ind_total * 100
                bar = "🟢" if r >= 60 else "🟡" if r >= 45 else "🔴"
                lines.append(f"  {bar} {name:<8} {ind_wins}/{ind_total}  ({r:.0f}%)")

    # ── Saatlik detay ──
    by_hour: dict = {}
    for e in sorted(today_entries, key=lambda x: (x["hour"], x["symbol"])):
        by_hour.setdefault(e["hour"], []).append(e)

    lines.append("")
    for h, entries in by_hour.items():
        lines.append(f"🕐 <b>{h:02d}:05</b>")
        for e in entries:
            votes = e.get("votes", [])
            vi    = "".join("🟢" if v > 0 else "🔴" if v < 0 else "⚪" for v in votes)
            # 1-4 saatlik değişim zinciri
            chain = []
            for n in range(1, 5):
                pct_n = e.get(f"pct_{n}h")
                if pct_n is not None:
                    arrow = "↑" if pct_n > 0 else "↓" if pct_n < 0 else "→"
                    chain.append(f"+{n}h:{arrow}{abs(pct_n):.1f}%")
                else:
                    chain.append(f"+{n}h:—")
            chain_str = "  ".join(chain)
            lines.append(
                f"  {e['result']} <b>{e['symbol']}</b>  {e['price_signal']:.2f}₺\n"
                f"    {chain_str}  {vi}"
            )

    lines.append(sep)

    # Mesajı 4000 karakter sınırına göre parçalara böl
    full_text = "\n".join(lines)
    MAX_LEN = 4000
    if len(full_text) <= MAX_LEN:
        tg_send(full_text)
    else:
        # Özet (ilk kısım) her zaman gönder
        summary_end = next(
            (i for i, l in enumerate(lines) if l.startswith("🕐")), len(lines)
        )
        tg_send("\n".join(lines[:summary_end]))
        # Saat detaylarını grupla ve gönder
        chunk, chunk_len = [], 0
        for line in lines[summary_end:]:
            addition = len(line) + 1
            if chunk_len + addition > MAX_LEN and chunk:
                tg_send("\n".join(chunk))
                chunk, chunk_len = [], 0
            chunk.append(line)
            chunk_len += addition
        if chunk:
            tg_send("\n".join(chunk))

    print(f"[BIST Tarayıcı] Gün sonu raporu gönderildi: {wins}/{total} isabet")


# ── Ana tarama ────────────────────────────────────────────────
def run_scan() -> None:
    now_tr = datetime.now(_TZ)
    hour   = now_tr.hour
    dow    = now_tr.weekday()  # 0=Pzt, 6=Paz
    saat   = now_tr.strftime("%H:%M")

    today = now_tr.strftime("%Y-%m-%d")

    # Hafta sonu → çık
    if dow >= 5:
        print(f"[BIST Tarayıcı] {saat} IST — hafta sonu, çıkılıyor")
        return

    # Gün sonu raporu: saat 18'de çalış
    if hour == 18:
        run_eod_report()
        return

    # Seans dışı (gün sonu hariç) → çık
    if hour < 10 or hour > 18:
        print(f"[BIST Tarayıcı] {saat} IST — seans dışı, çıkılıyor")
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
    next_h   = f"{(hour+4)%24:02d}:00"

    if not top:
        tg_send(
            f"{sep}\n"
            f"📊 <b>BIST Sinyal — {saat} IST</b>\n"
            f"⏸ Bu saat güçlü sinyal bulunamadı.\n"
            f"{sep}"
        )
        print(f"[BIST Tarayıcı] Sinyal yok")
        return

    lines = [f"{sep}", f"📊 <b>BIST Sinyal — {saat} IST  ⏳ 1-4 saat hedef</b>"]

    strong = [r for r in top if r["score"] >= SCORE_STRONG]
    medium = [r for r in top if SCORE_MODERATE <= r["score"] < SCORE_STRONG]

    if strong:
        lines.append(f"🔥 <b>Güçlü ({len(strong)})</b>")
        for r in strong:
            vi = ["🟢" if v > 0 else "🔴" if v < 0 else "⚪" for v in r["votes"]]
            lines.append(
                f"📈 <b>{r['symbol']}</b>  skor:{r["score"]:+d}/8  fiyat:{r['price']:.2f}₺\n"
                f"   {'  '.join(vi)}"
            )

    if medium:
        lines.append(f"📌 <b>Orta ({len(medium)})</b>")
        for r in medium:
            vi = ["🟢" if v > 0 else "🔴" if v < 0 else "⚪" for v in r["votes"]]
            lines.append(
                f"↗️ <b>{r['symbol']}</b>  skor:{r["score"]:+d}/8  fiyat:{r['price']:.2f}₺  "
                f"{''.join(vi)}"
            )

    lines.append(f"<i>Tarama: {len(SYMBOLS)} hisse | Eşik: ≥{SCORE_MODERATE}/8</i>")
    lines.append(sep)

    tg_send("\n".join(lines))

    # Sinyalleri isabet takibi için kaydet
    record_signals(top, hour, today)

    print(f"[BIST Tarayıcı] {saat} — {len(strong)} güçlü, {len(medium)} orta sinyal gönderildi")


def run_weekly_report() -> None:
    """Cuma 19:00 haftalık özet raporu."""
    history = load_history()
    if not history:
        tg_send("📋 <b>BIST Haftalık Rapor</b>\nHenüz veri yok.")
        return

    # Son 5 iş günü
    from datetime import timedelta
    today    = date.today()
    week_ago = (today - timedelta(days=7)).isoformat()
    entries  = [e for e in history
                if e["date"] >= week_ago and e["result"] in ("✅", "❌")]

    if not entries:
        tg_send("📋 <b>BIST Haftalık Rapor</b>\nBu hafta çözümlenen sinyal yok.")
        return

    wins  = sum(1 for e in entries if e["result"] == "✅")
    total = len(entries)
    rate  = wins / total * 100 if total else 0

    sep   = "━" * 28
    lines = [sep,
             f"📋 <b>BIST Haftalık Rapor</b>",
             f"📅 {week_ago} – {today.isoformat()}",
             f"🎯 Genel Başarı: {wins}/{total}  ({rate:.0f}%)"]

    # İndikatör bazında haftalık isabet
    lines.append("\n📊 <b>İndikatör Performansı (haftalık):</b>")
    for i, name in enumerate(IND_NAMES):
        iw = it = 0
        for e in entries:
            votes = e.get("votes", [])
            if i >= len(votes) or votes[i] == 0 or e["pct"] is None:
                continue
            it += 1
            if (votes[i] > 0 and e["pct"] > 0) or (votes[i] < 0 and e["pct"] < 0):
                iw += 1
        if it > 0:
            r   = iw / it * 100
            bar = "🟢" if r >= 60 else "🟡" if r >= 45 else "🔴"
            lines.append(f"  {bar} {name:<8} {iw}/{it}  ({r:.0f}%)")

    # En başarılı hisseler
    sym_stats: dict = {}
    for e in entries:
        s = e["symbol"]
        sym_stats.setdefault(s, {"w": 0, "t": 0})
        sym_stats[s]["t"] += 1
        if e["result"] == "✅":
            sym_stats[s]["w"] += 1

    ranked = sorted(sym_stats.items(),
                    key=lambda x: (x[1]["w"] / x[1]["t"], x[1]["t"]),
                    reverse=True)

    lines.append("\n🏆 <b>En Başarılı Hisseler:</b>")
    for sym, st in ranked[:8]:
        r = st["w"] / st["t"] * 100
        bar = "🟢" if r >= 60 else "🟡" if r >= 45 else "🔴"
        lines.append(f"  {bar} <b>{sym}</b>  {st['w']}/{st['t']}  ({r:.0f}%)")

    # Günlük özet
    lines.append("\n📆 <b>Günlük Özet:</b>")
    by_date: dict = {}
    for e in entries:
        by_date.setdefault(e["date"], {"w": 0, "t": 0})
        by_date[e["date"]]["t"] += 1
        if e["result"] == "✅":
            by_date[e["date"]]["w"] += 1
    for d, st in sorted(by_date.items()):
        r = st["w"] / st["t"] * 100
        bar = "🟢" if r >= 60 else "🟡" if r >= 45 else "🔴"
        lines.append(f"  {bar} {d}  {st['w']}/{st['t']}  ({r:.0f}%)")

    lines.append(sep)
    tg_send("\n".join(lines))
    print("[BIST Tarayıcı] Haftalık rapor gönderildi")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "weekly":
        run_weekly_report()
    else:
        run_scan()
