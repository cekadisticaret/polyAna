#!/usr/bin/env python3
"""
BIST %Güven Tarayıcı — 15 Dakika
Pine Script "SOL 5dk Tahmin Sinyali" mantığının BIST uyarlaması.

Skorlama (maks 100):
  RSI(14)       : <35 → +20 AL   | >65 → -20 SAT
  EMA 9/21/55   : 9>21>55 → +25  | 9<21<55 → -25
  MACD Hist     : artıyor → +20   | azalıyor → -20
  Momentum (5b) : >+0.1% → +20   | <-0.1% → -20
  Hacim         : >1.5x + yuk → +15 | >1.5x + aşağı → -15

Telegram: %65 ve üstü sinyaller otomatik gönderilir.

Kullanım:
  python3 yuzdeBist.py            → tüm BIST taranır
  python3 yuzdeBist.py THYAO GARAN → belirli hisseler
"""

import sys
import warnings
warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
import requests

# ─── AYARLAR ───────────────────────────────────────────────────────────────
RSI_PERIOD       = 14
EMA_FAST         = 9
EMA_MID          = 21
EMA_SLOW         = 55
MACD_FAST        = 12
MACD_SLOW        = 26
MACD_SIGNAL      = 9
MOM_PERIOD       = 5
VOL_PERIOD       = 20
MIN_CONFIDENCE   = 50   # taramaya dahil edilecek min skor (%)
TG_MIN_CONFIDENCE = 65  # Telegram'a gönderilecek min skor (%)

BIST_SESSION_START = (9, 50)   # İstanbul saati
BIST_SESSION_END   = (18, 30)

# ─── BIST HİSSE LİSTESİ ───────────────────────────────────────────────────
BIST_TICKERS = [
    "A1CAP","A1YEN","ACSEL","ADEL","ADESE","ADGYO","AEFES","AFYON","AGHOL","AGROT",
    "AHGAZ","AHSGY","AKBNK","AKCNS","AKENR","AKFGY","AKFIS","AKFYE","AKGRT","AKMGY",
    "AKSA","AKSEN","AKSGY","AKSUE","AKYHO","ALARK","ALBRK","ALCAR","ALCTL","ALFAS",
    "ALGYO","ALKIM","ALVES","ANELE","ANGEN","ANHYT","ANSGR","ARASE","ARCLK","ARDYZ",
    "ARENA","ARSAN","ASELS","ASGYO","ASTOR","ATAGY","ATAKP","ATATP","ATEKS","ATLAS",
    "ATSYH","AVGYO","AVHOL","AVOD","AVPGY","AVTUR","AYDEM","AYEN","AYES","AYGAZ",
    "AZTEK","BAGFS","BAKAB","BALAT","BANVT","BARMA","BASCM","BAYRK","BEGYO","BERA",
    "BEYAZ","BFREN","BIMAS","BINHO","BIOEN","BIZIM","BJKAS","BLCYT","BMSCH","BNTAS",
    "BOSSA","BRISA","BRKO","BRKSN","BRMEN","BRSAN","BRYAT","BSOKE","BTCIM","BUCIM",
    "BURCE","BURVA","BVSAN","CANTE","CASA","CCOLA","CELHA","CEMAS","CEMTS","CEOEM",
    "CIMSA","CLEBI","CMBTN","CONSE","COSMO","CRDFA","CRFSA","CUSAN","CVKMD","DAGI",
    "DAPGM","DARDL","DCTTR","DESA","DESPC","DEVA","DGATE","DGNMO","DIRIT","DITAS",
    "DMSAS","DOAS","DOBUR","DOCO","DOFER","DOHOL","DOKTA","DURDO","DYOBY","ECILC",
    "ECZYT","EDATA","EDIP","EGGUB","EGPRO","EGSER","EKGYO","EKIZ","EMKEL","EMNIS",
    "ENERY","ENJSA","ENKAI","ENSRI","EPLAS","ERBOS","EREGL","ERSU","ESCAR","ESCOM",
    "ESEN","ETILR","ETYAT","EUKYO","EUYO","FADE","FENER","FLAP","FMIZP","FONET",
    "FORMT","FRIGO","FROTO","GARAN","GEDIK","GEDZA","GENIL","GEREL","GESAN","GLBMD",
    "GLRMK","GLRYH","GLYHO","GMTAS","GOKNR","GOLTS","GOODY","GOZDE","GRSEL","GSDDE",
    "GSDHO","GSRAY","GUBRF","GZNMI","HALKB","HATEK","HDFGS","HEDEF","HEKTS","HKTM",
    "HLGYO","HOROZ","HTTBT","HUBVC","HUNER","HURGZ","ICBCT","IDGYO","IEYHO","IHEVA",
    "IHLAS","IHLGM","IHYAY","IMASM","INDES","INFO","INTEM","INVEO","INVES","ISBIR",
    "ISCTR","ISDMR","ISFIN","ISGSY","ISMEN","ISSEN","IZENR","IZFAS","IZINV","JANTS",
    "KAPLM","KAREL","KARSN","KARTN","KATMR","KAYSE","KCAER","KCHOL","KENT","KERVN",
    "KFEIN","KGYO","KIMMR","KLGYO","KLKIM","KLMSN","KLSER","KLSYN","KMPUR","KNFRT",
    "KONKA","KONTR","KONYA","KORDS","KOZAL","KRDMA","KRDMB","KRDMD","KRGYO","KRONT",
    "KRPLS","KRSTL","KRVGD","KSTUR","KTLEV","KTSKR","KUTPO","KUYAS","KZBGY","KZGYO",
    "LIDER","LINK","LKMNH","LOGO","LUKSK","MAALT","MAGEN","MAKIM","MANAS","MARKA",
    "MAVI","MEDTR","MEGAP","MEKAG","MERCN","MERIT","MERKO","METRO","MGROS","MHRGY",
    "MIATK","MNDRS","MNDTR","MOBTL","MOGAN","MPARK","MRGYO","MRSHL","MSGYO","MTRKS",
    "MTRYO","MZHLD","NATEN","NETAS","NIBAS","NTGAZ","NTHOL","NUGYO","NUHCM","ODAS",
    "ONCSM","ORGE","ORMA","OSMEN","OSTIM","OTKAR","OYAKC","OYLUM","OYYAT","OZGYO",
    "OZKGY","OZRDN","PAGYO","PAMEL","PAPIL","PARSN","PASEU","PATEK","PCILT","PENTA",
    "PETKM","PGSUS","PINSU","PKART","PKENT","PLTUR","POLHO","POLTK","PRKAB","PRKME",
    "PRZMA","PSDTC","QNBFK","QUAGR","RALYH","RAYSG","REEDR","RGYAS","RNPOL","RODRG",
    "RTALB","RUBNS","RYGYO","RYSAS","SAFKR","SAHOL","SAMAT","SANEL","SANFM","SANKO",
    "SARKY","SASA","SAYAS","SEGMN","SEKFK","SELEC","SELVA","SEYKM","SISE","SKBNK",
    "SMART","SMRTG","SNICA","SODSN","SOKE","SOKM","SONME","SRVGY","SUMAS","SURGY",
    "SUWEN","TABGD","TATGD","TAVHL","TCELL","TEKTU","THYAO","TKFEN","TKNSA","TLMAN",
    "TMPOL","TMSN","TOASO","TRCAS","TRENJ","TRGYO","TRHOL","TRILC","TRMET","TSKB",
    "TSPOR","TTRAK","TUKAS","TUPRS","TUREX","TURGG","TURSG","UFUK","ULAS","ULKER",
    "ULUSE","ULUUN","UNLU","USAK","VAKBN","VAKFN","VAKKO","VANGD","VBTYZ","VERUS",
    "VESBE","VESTL","VKFYO","VKGYO","YAPRK","YATAS","YAYLA","YBTAS","YEOTK","YGGYO",
    "YGYO","YKBNK","YONGA","YUNSA","YYAPI","ZEDUR","ZOREN",
]

# ─── YARDIMCI FONKSİYONLAR ────────────────────────────────────────────────

def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()

def _rsi(series: pd.Series, n: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def _macd_hist(series: pd.Series, fast: int, slow: int, sig: int) -> pd.Series:
    macd_line   = _ema(series, fast) - _ema(series, slow)
    signal_line = _ema(macd_line, sig)
    return macd_line - signal_line

def in_bist_session() -> bool:
    """Şu an BIST seans saatleri içinde mi?"""
    ist = pytz.timezone("Europe/Istanbul")
    now = datetime.now(ist)
    if now.weekday() >= 5:  # cumartesi / pazar
        return False
    t = (now.hour, now.minute)
    return BIST_SESSION_START <= t <= BIST_SESSION_END

# ─── ANA SKOR FONKSİYONU ──────────────────────────────────────────────────

def analyze(ticker: str) -> dict | None:
    """
    Verilen BIST hissesi için 5 dakikalık veri çeker,
    Pine Script mantığıyla güven skoru hesaplar.
    Sinyal yoksa None döner.
    """
    try:
        symbol = ticker + ".IS"
        df = yf.Ticker(symbol).history(period="7d", interval="15m")

        if df is None or len(df) < 60:
            return None

        # Son tam bar (iloc[-2]) — son bar henüz kapanmamış olabilir
        i = -2

        c = df["Close"]
        v = df["Volume"]

        # RSI
        rsi_val   = _rsi(c, RSI_PERIOD).iloc[i]
        rsi_bull  = rsi_val < 35
        rsi_bear  = rsi_val > 65
        rsi_score = 20 if rsi_bull else (-20 if rsi_bear else 0)

        # EMA
        ema9  = _ema(c, EMA_FAST).iloc[i]
        ema21 = _ema(c, EMA_MID).iloc[i]
        ema55 = _ema(c, EMA_SLOW).iloc[i]
        ema_bull  = ema9 > ema21 > ema55
        ema_bear  = ema9 < ema21 < ema55
        ema_score = 25 if ema_bull else (-25 if ema_bear else 0)

        # MACD Histogram
        hist     = _macd_hist(c, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
        h_now    = hist.iloc[i]
        h_prev   = hist.iloc[i - 1]
        macd_bull  = h_now > 0 and h_now > h_prev
        macd_bear  = h_now < 0 and h_now < h_prev
        macd_score = 20 if macd_bull else (-20 if macd_bear else 0)

        # Momentum (5 bar)
        if len(c) < abs(i) + MOM_PERIOD + 1:
            return None
        mom_pct    = (c.iloc[i] - c.iloc[i - MOM_PERIOD]) / c.iloc[i - MOM_PERIOD] * 100
        mom_bull   = mom_pct > 0.1
        mom_bear   = mom_pct < -0.1
        mom_score  = 20 if mom_bull else (-20 if mom_bear else 0)

        # Hacim
        avg_vol   = v.rolling(VOL_PERIOD).mean().iloc[i]
        vol_ratio = v.iloc[i] / avg_vol if avg_vol > 0 else 0
        vol_bull  = vol_ratio > 1.5 and mom_pct > 0
        vol_bear  = vol_ratio > 1.5 and mom_pct < 0
        vol_score = 15 if vol_bull else (-15 if vol_bear else 0)

        total      = rsi_score + ema_score + macd_score + mom_score + vol_score
        bull_score = max(total, 0)
        bear_score = max(-total, 0)

        is_bull = total >= MIN_CONFIDENCE
        is_bear = total <= -MIN_CONFIDENCE

        if not is_bull and not is_bear:
            return None

        direction = "YUKARI" if is_bull else "ASAGI"
        confidence = bull_score if is_bull else bear_score

        return {
            "ticker":     ticker,
            "direction":  direction,
            "confidence": confidence,
            "price":      round(c.iloc[i], 2),
            "rsi":        round(rsi_val, 1),
            "ema_txt":    "YUKARI" if ema_bull else ("ASAGI" if ema_bear else "KARIŞIK"),
            "macd_txt":   "POZ" if macd_bull else ("NEG" if macd_bear else "NÖTR"),
            "mom_pct":    round(mom_pct, 3),
            "vol_ratio":  round(vol_ratio, 2),
            "scores": {
                "RSI": rsi_score, "EMA": ema_score, "MACD": macd_score,
                "MOM": mom_score, "VOL": vol_score,
            },
        }
    except Exception:
        return None

# ─── ÇIKTI FORMATLAYICI ───────────────────────────────────────────────────

def _format_result(r: dict) -> str:
    arrow = "▲" if r["direction"] == "YUKARI" else "▼"
    color = "🟢" if r["direction"] == "YUKARI" else "🔴"
    lines = [
        f"{color} {arrow} {r['ticker']}  {r['direction']} %{r['confidence']}",
        f"   Fiyat: {r['price']} TL  |  RSI: {r['rsi']}  |  EMA: {r['ema_txt']}",
        f"   MACD: {r['macd_txt']}  |  Mom: {r['mom_pct']:+.3f}%  |  Hacim: {r['vol_ratio']:.2f}x",
    ]
    return "\n".join(lines)

def format_telegram(results: list[dict]) -> str:
    """Telegram mesajı için hazır metin."""
    now  = datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
    bull = [r for r in results if r["direction"] == "YUKARI"]
    bear = [r for r in results if r["direction"] == "ASAGI"]

    parts = [f"📊 *BIST 15dk Güven Taraması* — {now}\n"]

    if bull:
        parts.append("*▲ YUKARI Sinyaller*")
        for r in sorted(bull, key=lambda x: -x["confidence"]):
            parts.append(
                f"🟢 `{r['ticker']}` — *%{r['confidence']}* | {r['price']} TL | RSI {r['rsi']}"
            )

    if bear:
        parts.append("\n*▼ AŞAĞI Sinyaller*")
        for r in sorted(bear, key=lambda x: -x["confidence"]):
            parts.append(
                f"🔴 `{r['ticker']}` — *%{r['confidence']}* | {r['price']} TL | RSI {r['rsi']}"
            )

    if not bull and not bear:
        parts.append("ℹ️ Sinyal bulunamadı.")

    return "\n".join(parts)

# ─── TELEGRAM ─────────────────────────────────────────────────────────────

def send_telegram(text: str) -> bool:
    """telegram_config.py'deki BOT_TOKEN_YUZDE ve CHAT_ID_YUZDE ile mesaj gönderir."""
    try:
        sys.path.insert(0, "/root/aiProject")
        from telegram_config import BOT_TOKEN_YUZDE as BOT_TOKEN, CHAT_ID_YUZDE as chat_id

        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={
            "chat_id":    str(chat_id),
            "text":       text,
            "parse_mode": "Markdown",
        }, timeout=10)

        if resp.status_code == 200:
            print("✅ Telegram gönderildi.")
            return True
        else:
            print(f"❌ Telegram hatası: {resp.status_code} — {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Telegram exception: {e}")
        return False

# ─── ANA TARAMA ───────────────────────────────────────────────────────────

def scan(tickers: list[str] | None = None, notify: bool = True) -> list[dict]:
    """
    Tüm listeyi tara. notify=True ise %65+ sinyalleri Telegram'a gönder.
    """
    if tickers is None:
        tickers = BIST_TICKERS

    if not in_bist_session():
        ist = pytz.timezone("Europe/Istanbul")
        now = datetime.now(ist).strftime("%H:%M")
        print(f"⚠️  BIST seansı dışında ({now} İstanbul). Yine de taranıyor...")

    now_str = datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
    print(f"\n📊 BIST %Güven Tarayıcı | 15dk | {now_str}")
    print(f"   {len(tickers)} hisse taranıyor | sinyal eşiği: %{MIN_CONFIDENCE} | Telegram eşiği: %{TG_MIN_CONFIDENCE}")
    print("=" * 60)

    results = []
    for i, ticker in enumerate(tickers, 1):
        r = analyze(ticker)
        if r:
            results.append(r)
            print(_format_result(r))
            print()
        elif i % 50 == 0:
            print(f"   ... {i}/{len(tickers)} işlendi")

    print("=" * 60)
    if results:
        bull = [x for x in results if x["direction"] == "YUKARI"]
        bear = [x for x in results if x["direction"] == "ASAGI"]
        print(f"Sonuç: {len(bull)} YUKARI  |  {len(bear)} ASAGI  |  toplam {len(results)} sinyal")
    else:
        print("Sinyal bulunamadı.")

    # Telegram: sadece güven >= TG_MIN_CONFIDENCE olanları gönder
    if notify:
        tg_results = [r for r in results if r["confidence"] >= TG_MIN_CONFIDENCE]
        if tg_results:
            msg = format_telegram(tg_results)
            print("\n─── Telegram Gönderiliyor ───")
            print(msg)
            send_telegram(msg)
        else:
            print(f"\nℹ️  %{TG_MIN_CONFIDENCE}+ güven sinyali yok, Telegram gönderilmedi.")

    return results


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else None
    scan(tickers, notify=True)
