"""
TEPE / DÖNÜŞ TESPİT — Saatlik Bildirim
Her saat :01'de çalışır, BTC/ETH/SOL için tepe dönüşü kontrol eder.
Sinyal varsa A1 Live botuna bildirim gönderir.
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import numpy as np

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8529258517:AAHuVn1VFftXK7RR2Z1w3UqyHGuHNDXDYI4"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")

SYMBOLS = {
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
    "SOLUSDT": "SOL",
}

BINANCE_BASE = "https://fapi.binance.com"


# ── Binance veri çekme ─────────────────────────────────────────
def fetch_klines(symbol: str, interval: str = "1h", limit: int = 150) -> pd.DataFrame:
    url = f"{BINANCE_BASE}/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = json.load(r)
    df = pd.DataFrame(raw, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","qav","trades","tbav","tqav","ignore"
    ])
    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df = df.set_index("open_time")
    return df[["open","high","low","close","volume"]]


# ── Teknik göstergeler ─────────────────────────────────────────
def hesapla_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    kazanc = delta.clip(lower=0)
    kayip  = -delta.clip(upper=0)
    ortalama_kazanc = kazanc.rolling(period).mean()
    ortalama_kayip  = kayip.rolling(period).mean()
    rs  = ortalama_kazanc / ortalama_kayip.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def hesapla_macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_fast    = close.ewm(span=fast, adjust=False).mean()
    ema_slow    = close.ewm(span=slow, adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


def hesapla_ma_seti(close: pd.Series, fast=20, mid=50, slow=100):
    return close.rolling(fast).mean(), close.rolling(mid).mean(), close.rolling(slow).mean()


def bearish_divergence_var_mi(close: pd.Series, gosterge: pd.Series, lookback: int = 10) -> bool:
    if len(close) < lookback + 1:
        return False
    fiyat_simdi        = close.iloc[-1]
    fiyat_onceki_tepe  = close.iloc[-lookback:-1].max()
    gosterge_simdi     = gosterge.iloc[-1]
    gosterge_onceki    = gosterge.iloc[-lookback:-1].max()
    if pd.isna(gosterge_simdi) or pd.isna(gosterge_onceki):
        return False
    return (fiyat_simdi >= fiyat_onceki_tepe) and (gosterge_simdi < gosterge_onceki)


# ── Ana sinyal fonksiyonu ──────────────────────────────────────
def detect_top_reversal(df: pd.DataFrame, min_teyit: int = 3) -> dict:
    close = df["close"]
    fast_ma, mid_ma, slow_ma = hesapla_ma_seti(close)
    rsi = hesapla_rsi(close)
    macd_line, signal_line, hist = hesapla_macd(close)

    son    = df.iloc[-1]
    onceki = df.iloc[-2]
    signals = []

    govde    = abs(son.close - son.open)
    ust_fitil = son.high - max(son.close, son.open)
    if govde > 0 and ust_fitil > govde * 1.5:
        signals.append("Uzun üst gölge")

    if len(df) >= 5:
        son_govdeler = [abs(df.iloc[-i].close - df.iloc[-i].open) for i in range(1, 6)]
        if son_govdeler[0] < son_govdeler[-1] * 0.5:
            signals.append("Gövdeler küçülüyor")

    if son.close > onceki.close and son.volume < onceki.volume:
        signals.append("Fiyat ↑ Hacim ↓")

    if not pd.isna(fast_ma.iloc[-2]) and onceki.close > fast_ma.iloc[-2] and son.close < fast_ma.iloc[-1]:
        signals.append("MA20 altına düştü")

    if not pd.isna(fast_ma.iloc[-2]) and not pd.isna(mid_ma.iloc[-2]):
        if fast_ma.iloc[-2] > mid_ma.iloc[-2] and fast_ma.iloc[-1] < mid_ma.iloc[-1]:
            signals.append("MA20 ↓ MA50 kesti")

    if bearish_divergence_var_mi(close, rsi):
        signals.append("RSI bearish div.")

    if bearish_divergence_var_mi(close, macd_line):
        signals.append("MACD bearish div.")

    if len(macd_line) >= 2:
        if macd_line.iloc[-2] > signal_line.iloc[-2] and macd_line.iloc[-1] < signal_line.iloc[-1]:
            signals.append("MACD sinyal ↓ kesti")

    if len(rsi) >= 2 and rsi.iloc[-2] > 70 and rsi.iloc[-1] < 70:
        signals.append("RSI 70'den döndü")

    if len(df) >= 50:
        destek = df["close"].rolling(50).min().iloc[-1]
        if son.close < destek:
            signals.append("Destek kırıldı")

    toplam   = 10
    risk_pct = round(len(signals) / toplam * 100, 1)
    teyit    = len(signals) >= min_teyit

    return {
        "sinyaller":    signals,
        "kriter_sayisi": len(signals),
        "teyit":        teyit,
        "risk_skoru":   risk_pct,
        "rsi_son":      round(float(rsi.iloc[-1]), 1) if not pd.isna(rsi.iloc[-1]) else None,
        "fiyat":        round(float(son.close), 4),
    }


# ── Telegram ──────────────────────────────────────────────────
def tg_send(msg: str) -> None:
    data = urllib.parse.urlencode({
        "chat_id":                  CHAT_ID,
        "text":                     msg,
        "parse_mode":               "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=data, method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        json.load(r)


# ── Ana akış ──────────────────────────────────────────────────
def main() -> None:
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)
    saat    = now_tr.strftime("%H:%M")
    sep     = "━" * 26

    bulgular = []

    for sym, name in SYMBOLS.items():
        try:
            df     = fetch_klines(sym, interval="1h", limit=150)
            sonuc  = detect_top_reversal(df, min_teyit=3)
            if sonuc["teyit"]:
                bulgular.append((name, sonuc))
        except Exception as e:
            print(f"[tepe_donus] {sym} hata: {e}")

    if not bulgular:
        print(f"[tepe_donus] {saat} — sinyal yok")
        return

    lines = []
    for name, s in bulgular:
        rsi_str = f"  RSI:{s['rsi_son']}" if s["rsi_son"] else ""
        kriter  = f"{s['kriter_sayisi']}/10"
        risk    = f"%{s['risk_skoru']}"
        sig_str = " | ".join(s["sinyaller"])
        lines.append(
            f"🔻 <b>{name}</b>  ${s['fiyat']:,.2f}  kriter:{kriter}  risk:{risk}{rsi_str}\n"
            f"   <i>{sig_str}</i>"
        )

    msg = (
        f"{sep}\n"
        f"⚠️ <b>TEPE DÖNÜŞ TESPİT — {saat} İST</b>\n"
        + "\n".join(lines) + "\n"
        f"{sep}"
    )
    tg_send(msg)
    print(f"[tepe_donus] {saat} — {len(bulgular)} sinyal gönderildi: {[n for n,_ in bulgular]}")


if __name__ == "__main__":
    main()
