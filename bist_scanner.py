#!/usr/bin/env python3
"""
BIST Tarayıcı - Gaia Scanner v2
Cem'in iki Pine Script indikatörünü baz alarak BIST hisselerini tarar.

scan()          → Trend tarama: tüm indikatörler yeşil olan hisseler
scan_momentum() → Momentum tarama: güçlü günlük hareket + hacim patlaması
"""

import yfinance as yf
import pandas as pd
import numpy as np
import sys
from datetime import datetime

# =========================================
# BIST Hisse Listesi
# =========================================
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

# =========================================
# İNDİKATÖR FONKSİYONLARI
# =========================================

def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

def rsi(series, n=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/n, min_periods=n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/n, min_periods=n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def adx(high, low, close, n=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)

    dm_plus = high.diff()
    dm_minus = -low.diff()
    dm_plus = dm_plus.where((dm_plus > dm_minus) & (dm_plus > 0), 0)
    dm_minus = dm_minus.where((dm_minus > dm_plus) & (dm_minus > 0), 0)

    atr_ = tr.ewm(span=n, adjust=False).mean()
    di_plus = 100 * dm_plus.ewm(span=n, adjust=False).mean() / atr_
    di_minus = 100 * dm_minus.ewm(span=n, adjust=False).mean() / atr_
    dx = (abs(di_plus - di_minus) / (di_plus + di_minus).replace(0, np.nan)) * 100
    return dx.ewm(span=n, adjust=False).mean()

# =========================================
# TREND TARAMA
# =========================================

def check_ticker(ticker, interval="1h"):
    try:
        symbol = ticker + ".IS"
        period = "60d" if interval == "1h" else "90d"
        df = yf.Ticker(symbol).history(period=period, interval=interval)

        if df is None or len(df) < 210:
            return None

        c = df["Close"]
        v = df["Volume"]
        h = df["High"]
        l = df["Low"]

        ema50  = ema(c, 50)
        ema200 = ema(c, 200)
        rsi_v  = rsi(c, 14)
        adx_v  = adx(h, l, c, 14)

        fast_ma = ema(c, 12)
        slow_ma = ema(c, 26)
        macd_line = fast_ma - slow_ma
        signal_line = ema(macd_line, 9)

        vol_avg    = v.rolling(20).mean()
        tl_vol_sma = (c * v).rolling(20).mean()

        i = -2
        price       = c.iloc[i]
        e50         = ema50.iloc[i]
        e200        = ema200.iloc[i]
        rsi_val     = rsi_v.iloc[i]
        rsi_prev    = rsi_v.iloc[i-1]
        adx_val     = adx_v.iloc[i]
        macd_val    = macd_line.iloc[i]
        sig_val     = signal_line.iloc[i]
        vol_last    = v.iloc[i]
        vol_avg_val = vol_avg.iloc[i]
        tl_sma_val  = tl_vol_sma.iloc[i]

        # Günlük % değişim: 1h barda 6 bar geriye = yaklaşık 1 gün
        daily_pct = 0.0
        if len(c) >= 8:
            prev = c.iloc[i - 6]
            if prev > 0:
                daily_pct = round((price - prev) / prev * 100, 2)

        golden_cross = any(
            ema50.iloc[j-1] <= ema200.iloc[j-1] and ema50.iloc[j] > ema200.iloc[j]
            for j in range(-5, 0)
        )

        dist_pct = abs((price - e200) / e200) * 100

        # === KOŞULLAR (cond_not_too_far kaldırıldı) ===
        cond_price_above_emas = price > e50 and price > e200
        cond_rsi              = (rsi_val > 50 and rsi_val > rsi_prev) or rsi_val > 55
        cond_adx              = adx_val > 16
        cond_macd_bull        = macd_val > sig_val
        cond_vol_spike        = vol_last > vol_avg_val * 1.3
        cond_liquidity        = tl_sma_val >= 5_000_000

        all_green = all([
            cond_price_above_emas,
            cond_rsi,
            cond_adx,
            cond_macd_bull,
            cond_vol_spike,
            cond_liquidity,
        ])

        if all_green:
            return {
                "ticker":       ticker,
                "price":        round(price, 2),
                "rsi":          round(rsi_val, 1),
                "adx":          round(adx_val, 1),
                "dist_pct":     round(dist_pct, 2),
                "daily_pct":    daily_pct,
                "tl_vol_sma_m": round(tl_sma_val / 1_000_000, 1),
                "golden_cross": "EVET" if golden_cross else "YOK",
                "scan_type":    "trend",
            }
        return None
    except Exception:
        return None

# =========================================
# MOMENTUM TARAMA
# =========================================

def check_ticker_momentum(ticker):
    """
    Günlük büyük hareketleri yakalar.
    Koşullar:
      - Günlük değişim >= %5
      - Hacim > 20 günlük ortalama × 2.0
      - RSI > 60
      - TL hacim SMA >= 5M (likidite)
    """
    try:
        symbol = ticker + ".IS"
        df = yf.Ticker(symbol).history(period="60d", interval="1d")

        if df is None or len(df) < 22:
            return None

        c = df["Close"]
        v = df["Volume"]
        rsi_v      = rsi(c, 14)
        vol_avg    = v.rolling(20).mean()
        tl_vol_sma = (c * v).rolling(20).mean()

        # iloc[-1] = bugünün barı (açık veya kapanmış), iloc[-2] = dünün kapanışı
        price       = c.iloc[-1]
        prev_price  = c.iloc[-2]
        rsi_val     = rsi_v.iloc[-1]
        vol_last    = v.iloc[-1]
        vol_avg_val = vol_avg.iloc[-2]
        tl_sma_val  = tl_vol_sma.iloc[-2]

        daily_pct = round((price - prev_price) / prev_price * 100, 2) if prev_price > 0 else 0.0

        cond_momentum  = daily_pct >= 5.0
        cond_rsi       = rsi_val > 50
        cond_liquidity = tl_sma_val >= 5_000_000

        if all([cond_momentum, cond_rsi, cond_liquidity]):
            return {
                "ticker":       ticker,
                "price":        round(price, 2),
                "rsi":          round(rsi_val, 1),
                "adx":          0.0,
                "dist_pct":     0.0,
                "daily_pct":    daily_pct,
                "tl_vol_sma_m": round(tl_sma_val / 1_000_000, 1),
                "golden_cross": "YOK",
                "scan_type":    "momentum",
            }
        return None
    except Exception:
        return None

# =========================================
# SCAN FONKSİYONLARI
# =========================================

def scan(interval="1h"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n🌿 BIST Trend Tarayıcı | {interval.upper()} | {now}")
    print("=" * 65)
    print(f"Toplam {len(BIST_TICKERS)} hisse taranıyor...\n")

    results = []
    for ticker in BIST_TICKERS:
        r = check_ticker(ticker, interval)
        if r:
            results.append(r)
            print(f"  ✅ {ticker:8s} | {r['price']:>8} | RSI:{r['rsi']:>5} | ADX:{r['adx']:>5} | "
                  f"Günlük:{r['daily_pct']:>+6.1f}% | {r['tl_vol_sma_m']:>6}M TL")

    print("\n" + "=" * 65)
    if results:
        print(f"\n🟢 TREND — {len(results)} Hisse\n")
        print(f"{'HİSSE':<10} {'FİYAT':>8} {'RSI':>6} {'ADX':>6} {'GÜNLÜK':>8} {'TL HACİM':>10}")
        print("-" * 65)
        for r in sorted(results, key=lambda x: x['rsi'], reverse=True):
            gc = "✨GC" if r.get('golden_cross') == 'EVET' else "   "
            print(f"{r['ticker']:<10} {r['price']:>8} {r['rsi']:>6} {r['adx']:>6} "
                  f"{r['daily_pct']:>+7.1f}% {r['tl_vol_sma_m']:>9}M  {gc}")
    else:
        print("\n🔴 Kriterlerin tamamı yeşil olan hisse bulunamadı.")

    print(f"\n⏱  Tamamlandı: {datetime.now().strftime('%H:%M:%S')}")
    return results


def scan_momentum():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n🚀 BIST Momentum Tarayıcı | {now}")
    print("=" * 65)
    print(f"Toplam {len(BIST_TICKERS)} hisse taranıyor...\n")

    results = []
    for ticker in BIST_TICKERS:
        r = check_ticker_momentum(ticker)
        if r:
            results.append(r)
            print(f"  🚀 {ticker:8s} | {r['price']:>8} | RSI:{r['rsi']:>5} | "
                  f"Günlük:{r['daily_pct']:>+6.1f}% | {r['tl_vol_sma_m']:>6}M TL")

    print("\n" + "=" * 65)
    if results:
        print(f"\n🚀 MOMENTUM — {len(results)} Hisse\n")
        print(f"{'HİSSE':<10} {'FİYAT':>8} {'RSI':>6} {'GÜNLÜK':>8} {'TL HACİM':>10}")
        print("-" * 65)
        for r in sorted(results, key=lambda x: x['daily_pct'], reverse=True):
            print(f"{r['ticker']:<10} {r['price']:>8} {r['rsi']:>6} "
                  f"{r['daily_pct']:>+7.1f}% {r['tl_vol_sma_m']:>9}M")
    else:
        print("\n🔴 Momentum kriteri geçen hisse bulunamadı.")

    print(f"\n⏱  Tamamlandı: {datetime.now().strftime('%H:%M:%S')}")
    return results


if __name__ == "__main__":
    interval = sys.argv[1] if len(sys.argv) > 1 else "1h"
    if interval == "momentum":
        scan_momentum()
    else:
        scan(interval)
