#!/usr/bin/env python3
"""
BIST Tarayıcı Bot v1.0
RSI + MACD + EMA + ADX + Hacim — 15dk ve 1 saatte aynı anda sinyal arar
"""

import asyncio
import logging
import time
from datetime import datetime
import pandas as pd
import pandas_ta as ta
import requests
from tvDatafeed import TvDatafeed, Interval

# ==========================================
# === AYARLAR — BURAYA KEND İ BİLGİLERİNİ GİR ===
# ==========================================
TELEGRAM_TOKEN   = "8676924067:AAGJAqLzF0d8QRVLzqkKs-BE4e1UrZdd6nc"
TELEGRAM_CHAT_ID = "TELEGRAM_CHAT_ID_BURAYA"

# TradingView giriş (opsiyonel, girersen daha fazla veri alırsın)
TV_USERNAME = ""
TV_PASSWORD = ""

# Tarama saatleri (BIST: 10:00 - 18:00)
MARKET_OPEN  = 10
MARKET_CLOSE = 18

# Kaç dakikada bir tara
SCAN_INTERVAL_15M = 15 * 60   # 15 dakika
SCAN_INTERVAL_1H  = 60 * 60   # 1 saat

# ==========================================
# === STRATEJİ PARAMETRELERİ (v6.0 ile aynı) ===
# ==========================================
RSI_LENGTH     = 14
RSI_THRESHOLD  = 55
ADX_THRESHOLD  = 25
EMA_SHORT      = 20
EMA_LONG       = 50
VOL_LENGTH     = 20
VOL_MULT       = 1.5
DIST_THRESHOLD = 5.0
MACD_FAST      = 12
MACD_SLOW      = 26
MACD_SIGNAL    = 9

# ==========================================
# === BIST HİSSE LİSTESİ ===
# ==========================================
BIST_SYMBOLS = [
    "AEFES","AFYON","AGESA","AGROT","AKBNK","AKCNS","AKFEN","AKGRT","AKMGY","AKSA",
    "AKSEN","AKSGY","AKSUE","AKYHO","ALARK","ALBRK","ALCAR","ALFAS","ALGYO","ALKIM",
    "ALKLC","ALTNY","ALYAG","ANACM","ANELE","ANGEN","ANHYT","ANSGR","ARASE","ARCLK",
    "ARDYZ","ARENA","ARSAN","ARTMS","ARZUM","ASELS","ASGYO","ASTOR","ATAKP","ATATP",
    "ATEKS","ATLAS","ATSYH","AVHOL","AVOD","AVPGY","AYCES","AYEN","AYGAZ","AZTEK",
    "BAGFS","BAKAB","BALAT","BANVT","BASCM","BASGZ","BATRA","BAYRK","BCLPL","BEGYO",
    "BERA","BEYAZ","BFREN","BIENY","BIGCH","BIMAS","BINHO","BIOEN","BIONC","BJKAS",
    "BLCYT","BMSCH","BNTAS","BOBET","BORLS","BORSK","BOSSA","BPLAS","BRISA","BRKSN",
    "BRKVY","BRMEN","BRNKS","BROYN","BRSAN","BRYAT","BSOKE","BTCIM","BUCIM","BURCE",
    "BURVA","BVSAN","CCOLA","CELHA","CEMAS","CEMTS","CEOEM","CIMSA","CLEBI","CLKHO",
    "CMBTN","CMENT","COSMO","CRDFA","CRFSA","CUSAN","CWENE","DAPGM","DARDL","DENGE",
    "DERHL","DESA","DESPC","DEVA","DGATE","DGGYO","DITAS","DJIST","DMSAS","DNISI",
    "DOAS","DOBUR","DOCO","DOGUB","DOHOL","DPKIM","DRDOC","DTRND","DURDO","DYOBY",
    "ECILC","ECZYT","EDATA","EDIP","EFORC","EGEEN","EGEPO","EGGUB","EGPRO","EGSER",
    "EKGYO","EKSUN","ELITE","EMKEL","EMNIS","ENERY","ENJSA","ENKAI","ENTRA","ERCB",
    "ERDEM","ERDMR","EREGL","ERSU","ESCAR","ESCOM","ESEN","ETILR","ETYAT","EUHOL",
    "EUPWR","EUREN","EUYO","EVREN","FADCO","FENER","FLAP","FMIZP","FONET","FORMT",
    "FORTE","FROTO","FZLGY","GARAN","GARFA","GEDIK","GEDZA","GENIL","GENTS","GEREL",
    "GESAN","GLBMD","GLCVY","GLRYH","GLYHO","GMTAS","GOODY","GOZDE","GRSEL","GRTHO",
    "GSDDE","GSDHO","GSRAY","GUBRF","GWIND","GZNMI","HALKB","HATEK","HDFGS","HEDEF",
    "HEKTS","HLGYO","HOROZ","HRKET","HTTBT","HUBVC","HUNER","HURGZ","ICBCT","ICUGS",
    "IDEAS","IDGYO","IEYHO","IHAAS","IHEVA","IHGZT","IHLAS","IHLGM","IHYAY","IMASM",
    "INDES","INFO","INGRM","INTEM","INVEO","IPEKE","ISATR","ISBIR","ISCTR","ISFIN",
    "ISGSY","ISGYO","ISKPL","ISKUR","ISMEN","ISYAT","ITTFK","IZFAS","IZINV","IZMDC",
    "JANTS","KAPLM","KARCE","KAREL","KARSN","KARTN","KATMR","KCAER","KCHOL","KENT",
    "KERVN","KERVT","KFEIN","KGYO","KHOLR","KIMSE","KIPLR","KLGYO","KLKIM","KLMSN",
    "KLNMA","KLRHO","KLSER","KLSYN","KMPUR","KNFRT","KOCMT","KONKA","KONTR","KONYA",
    "KOPOL","KORDS","KOZAA","KOZAL","KRDMA","KRDMB","KRDMD","KRONT","KRPLS","KRSAN",
    "KRSTL","KRTEK","KTLEV","KUTPO","KUVVA","KUYAS","LIDER","LIDFA","LILAK","LKMNH",
    "LOGO","LRSHO","LYTUS","MAALT","MACKO","MAGEN","MAKIM","MAKTK","MANAS","MARBL",
    "MARKA","MARTI","MAVI","MEDTR","MEGMT","MEKAG","MEPET","MERCN","MERIT","MERKO",
    "METRO","METUR","MGROS","MIATK","MIGRS","MIPAZ","MMCAS","MNDRS","MNDTR","MOBTL",
    "MOGAN","MPARK","MRGYO","MRSHL","MSGYO","MTRKS","MZHLD","NATEN","NETAS","NIBAS",
    "NTHOL","NTTUR","NUGYO","NUHCM","OBAMS","OBASE","ODAS","ODINE","OFSYM","ONCSM",
    "ONRYT","ORCAY","ORGE","ORMA","OSMEN","OSTIM","OTKAR","OYAKC","OYAYO","OYLUM",
    "OZGYO","OZKGY","OZRDN","OZSUB","PAGYO","PAMEL","PAPIL","PARSN","PASEU","PCILT",
    "PEGYO","PENTA","PETKM","PETUN","PGSUS","PINSU","PKART","PKENT","PLTUR","PNSUT",
    "POLHO","POLTK","PRDGS","PRFBK","PRKAB","PRKME","PRZMA","PSDTC","PSGYO","QNBFB",
    "QNBFL","RALYH","RAYSG","REEDR","RGYAS","RTALB","RYSAS","SAFKR","SAHOL","SAMAT",
    "SAMFA","SANEL","SANFM","SANKO","SARKY","SASA","SAYAS","SDTTR","SEGYO","SEKFK",
    "SEKUR","SELEC","SELGD","SELVA","SEYKM","SILVR","SISE","SKBNK","SKYLP","SMART",
    "SNGYO","SNICA","SNKRN","SODSN","SOKE","SOKM","SONME","SRVGY","SUMAS","SUNTK",
    "SURGY","SUWEN","TABGD","TATGD","TAVHL","TBORG","TCELL","TCKRC","TDGYO","TEKTU",
    "TETMT","THYAO","TKNSA","TLMAN","TMSN","TOASO","TRCAS","TRGYO","TRILC","TSPOR",
    "TTKOM","TTRAK","TUCLK","TUKAS","TUPRS","TUREX","TURGG","TURSG","TZNGY","UCCMT",
    "UCRET","ULUFA","ULUSE","ULUUN","UMPAS","UNLU","USAK","USDTR","UTPYA","UZERB",
    "VAKBN","VAKFN","VAKKO","VANGD","VBTYZ","VERTU","VERUS","VESBE","VESTEL","VKFYO",
    "VKGYO","VRGYO","WINTA","WNTUR","XCORP","XELKT","XGIDA","XKMYA","XKURY","XMANA",
    "XSGRT","XSPOR","XTCRT","XTRZM","XUTEK","XUHIZ","XUMAL","XUSIN","YAPRK","YATAS",
    "YESIL","YEOTK","YGYO","YIGIT","YKBNK","YKSLN","YONGA","YUNSA","ZEDUR","ZOREN","ZRGYO"
]

# ==========================================
# === LOGGING ===
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scanner.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ==========================================
# === TELEGRAM ===
# ==========================================
def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            log.error(f"Telegram hata: {r.text}")
    except Exception as e:
        log.error(f"Telegram gönderilemedi: {e}")

# ==========================================
# === VERİ ÇEKME ===
# ==========================================
def get_data(tv: TvDatafeed, symbol: str, interval: Interval, bars: int = 100) -> pd.DataFrame | None:
    try:
        df = tv.get_hist(symbol=symbol, exchange="BIST", interval=interval, n_bars=bars)
        if df is None or len(df) < 60:
            return None
        df = df[["open", "high", "low", "close", "volume"]].copy()
        df.dropna(inplace=True)
        return df
    except Exception as e:
        log.debug(f"{symbol} veri hatası: {e}")
        return None

# ==========================================
# === İNDİKATÖR HESAPLAMA ===
# ==========================================
def calculate_indicators(df: pd.DataFrame) -> dict | None:
    try:
        c = df["close"]
        v = df["volume"]

        # RSI
        rsi_series = ta.rsi(c, length=RSI_LENGTH)
        rsi = rsi_series.iloc[-1]

        # EMA
        ema_short = ta.ema(c, length=EMA_SHORT).iloc[-1]
        ema_long  = ta.ema(c, length=EMA_LONG).iloc[-1]
        ema_long_prev = ta.ema(c, length=EMA_LONG).iloc[-6]

        # MACD
        macd_df  = ta.macd(c, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
        macd_val = macd_df[f"MACD_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"].iloc[-1]
        sig_val  = macd_df[f"MACDs_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}"].iloc[-1]

        # ADX
        adx_df  = ta.adx(df["high"], df["low"], c, length=14)
        adx_val = adx_df[f"ADX_14"].iloc[-1]

        # Hacim
        vol_avg   = v.rolling(VOL_LENGTH).mean().iloc[-1]
        vol_spike = v.iloc[-1] > vol_avg * VOL_MULT
        vol_ratio = v.iloc[-1] / vol_avg

        # RSI Momentum
        rsi_prev2 = rsi_series.iloc[-3]
        rsi_prev4 = rsi_series.iloc[-5]
        rsi_momentum = rsi > rsi_prev2 and rsi > rsi_prev4

        # Hesaplamalar
        macd_bull    = macd_val > sig_val
        ema_rising   = ema_long > ema_long_prev
        price_dist   = abs((c.iloc[-1] - ema_long) / ema_long) * 100
        not_too_far  = price_dist < DIST_THRESHOLD
        above_ema_s  = c.iloc[-1] > ema_short

        return {
            "rsi": round(rsi, 2),
            "adx": round(adx_val, 2),
            "macd_bull": macd_bull,
            "vol_spike": vol_spike,
            "vol_ratio": round(vol_ratio, 2),
            "ema_rising": ema_rising,
            "not_too_far": not_too_far,
            "above_ema_s": above_ema_s,
            "rsi_momentum": rsi_momentum,
            "price_dist": round(price_dist, 2),
            "price": round(c.iloc[-1], 2)
        }
    except Exception as e:
        log.debug(f"İndikatör hatası: {e}")
        return None

# ==========================================
# === SİNYAL KONTROLÜ ===
# ==========================================
def check_signal(ind: dict) -> bool:
    return (
        (ind["rsi"] > RSI_THRESHOLD or ind["rsi_momentum"]) and
        (ind["vol_spike"] or ind["vol_ratio"] > 1.2) and
        ind["above_ema_s"] and
        ind["adx"] > ADX_THRESHOLD and
        ind["macd_bull"] and
        ind["not_too_far"] and
        ind["ema_rising"] and
        ind["rsi"] > RSI_THRESHOLD and
        ind["vol_ratio"] > 1.2
    )

# ==========================================
# === ANA TARAMA FONKSİYONU ===
# ==========================================
def scan_all(tv: TvDatafeed):
    log.info(f"Tarama başladı — {len(BIST_SYMBOLS)} hisse")
    signals = []

    for symbol in BIST_SYMBOLS:
        # 15 dakikalık veri
        df_15m = get_data(tv, symbol, Interval.in_15_minute)
        if df_15m is None:
            continue

        # 1 saatlik veri
        df_1h = get_data(tv, symbol, Interval.in_1_hour)
        if df_1h is None:
            continue

        ind_15m = calculate_indicators(df_15m)
        ind_1h  = calculate_indicators(df_1h)

        if ind_15m is None or ind_1h is None:
            continue

        # Her iki zaman diliminde de sinyal var mı?
        signal_15m = check_signal(ind_15m)
        signal_1h  = check_signal(ind_1h)

        if signal_15m and signal_1h:
            signals.append({
                "symbol": symbol,
                "price": ind_15m["price"],
                "rsi_15m": ind_15m["rsi"],
                "rsi_1h": ind_1h["rsi"],
                "adx_15m": ind_15m["adx"],
                "adx_1h": ind_1h["adx"],
                "vol_ratio_15m": ind_15m["vol_ratio"],
                "vol_ratio_1h": ind_1h["vol_ratio"],
            })
            log.info(f"✅ SİNYAL: {symbol}")
        
        time.sleep(0.3)  # API rate limit için

    log.info(f"Tarama bitti — {len(signals)} sinyal bulundu")
    return signals

# ==========================================
# === BİLDİRİM GÖNDER ===
# ==========================================
def send_signals(signals: list):
    if not signals:
        log.info("Sinyal yok, bildirim gönderilmedi.")
        return

    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    msg = f"🚀 <b>BIST TARAYICI — {now}</b>\n"
    msg += f"━━━━━━━━━━━━━━━━━━━\n"
    msg += f"✅ <b>{len(signals)} hissede 15dk+1h sinyal!</b>\n\n"

    for s in signals:
        msg += (
            f"📌 <b>{s['symbol']}</b> — {s['price']} TL\n"
            f"   RSI: {s['rsi_15m']} (15m) / {s['rsi_1h']} (1h)\n"
            f"   ADX: {s['adx_15m']} (15m) / {s['adx_1h']} (1h)\n"
            f"   Hacim: {s['vol_ratio_15m']}x (15m) / {s['vol_ratio_1h']}x (1h)\n"
            f"   ━━━━━━━━━━━━━━\n"
        )

    msg += "\n⚠️ <i>Bu bir yatırım tavsiyesi değildir.</i>"
    send_telegram(msg)

# ==========================================
# === ZAMANLAYICI ===
# ==========================================
def is_market_open() -> bool:
    now = datetime.now()
    # Hafta sonu kontrolü (0=Pazartesi, 6=Pazar)
    if now.weekday() >= 5:
        return False
    return MARKET_OPEN <= now.hour < MARKET_CLOSE

def main():
    log.info("BIST Tarayıcı Bot başlatıldı")
    send_telegram("🤖 <b>BIST Tarayıcı Bot başlatıldı!</b>\nHer 15 dakikada BIST taranacak.")

    # TradingView bağlantısı
    if TV_USERNAME and TV_PASSWORD:
        tv = TvDatafeed(TV_USERNAME, TV_PASSWORD)
    else:
        tv = TvDatafeed()  # anonim bağlantı

    last_scan = 0

    while True:
        now = time.time()

        if is_market_open():
            if now - last_scan >= SCAN_INTERVAL_15M:
                try:
                    signals = scan_all(tv)
                    send_signals(signals)
                except Exception as e:
                    log.error(f"Tarama hatası: {e}")
                    send_telegram(f"⚠️ Tarama hatası: {e}")
                last_scan = now
        else:
            log.info("Borsa kapalı, bekleniyor...")

        time.sleep(60)  # Her dakika kontrol et

if __name__ == "__main__":
    main()
