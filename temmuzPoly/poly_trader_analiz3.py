"""
3. ANALİZ — 4 Saatlik Teknik Durum Özeti → Telegram Bildirimi
==============================================================

NE OLDUĞU / NE OLMADIGI:
Bu script bir tahmin veya sinyal motoru DEĞİLDİR. BTC, ETH ve SOL için
RSI, MACD, EMA trend ve hacim gibi standart teknik göstergeleri hesaplayıp
objektif, olasılıksal bir OKUMA çıkarır. Kesin yön iddiasında BULUNMAZ.

Cron: 0 */4 * * * → her 4 saatte bir çalışır
Binance genel (public) REST API, API anahtarı gerekmez.
"""

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import urllib.request
import urllib.parse

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")
_DAYS_FULL_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

_DIR          = os.path.dirname(os.path.abspath(__file__))
STATE_FILE    = os.path.join(_DIR, "poly_trader_analiz3_state.json")
HISTORY_FILE  = os.path.join(_DIR, "poly_trader_analiz3_history.json")
MIN_STAT_COUNT = 5  # istatistik için min işlem sayısı

SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
}

INTERVAL        = "4h"
KLINE_LIMIT     = 300
KLINES_BASE_URL = "https://api.binance.com/api/v3/klines"

RSI_LENGTH    = 14
EMA_FAST      = 50
EMA_SLOW      = 200
MACD_FAST     = 12
MACD_SLOW     = 26
MACD_SIGNAL   = 9
VOLUME_LOOKBACK = 20


# ── Veri çekme ────────────────────────────────────────────────
def fetch_klines(symbol: str, interval: str = INTERVAL, limit: int = KLINE_LIMIT) -> pd.DataFrame:
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    resp = requests.get(KLINES_BASE_URL, params=params, timeout=15)
    resp.raise_for_status()
    cols = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_base_vol", "taker_quote_vol", "ignore",
    ]
    df = pd.DataFrame(resp.json(), columns=cols)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df


# ── Göstergeler ───────────────────────────────────────────────
def compute_rsi(close: pd.Series, length: int = RSI_LENGTH) -> pd.Series:
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)


def compute_macd(close: pd.Series):
    ema_fast    = close.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow    = close.ewm(span=MACD_SLOW, adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    hist        = macd_line - signal_line
    return macd_line, signal_line, hist


def compute_ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


# ── Analiz ────────────────────────────────────────────────────
@dataclass
class TeknikOzet:
    sembol:       str
    fiyat:        float
    rsi:          float
    rsi_durum:    str
    rsi_emoji:    str
    macd_durum:   str
    macd_emoji:   str
    trend:        str
    trend_emoji:  str
    hacim_durum:  str
    hacim_emoji:  str
    genel_okuma:  str
    genel_emoji:  str
    skor:         int   # -3..+3, pozitif = yukarı eğilimli
    prob_up:      float  # gösterge hizalamasına dayalı olasılık (0.0–1.0)


def analiz_et(sembol_kisa: str, df: pd.DataFrame) -> TeknikOzet:
    close  = df["close"]
    volume = df["volume"]

    rsi              = compute_rsi(close)
    _, _, hist       = compute_macd(close)
    ema_fast         = compute_ema(close, EMA_FAST)
    ema_slow         = compute_ema(close, EMA_SLOW)

    son_fiyat   = close.iloc[-1]
    son_rsi     = rsi.iloc[-1]
    son_hist    = hist.iloc[-1]
    onceki_hist = hist.iloc[-2]
    ort_hacim   = volume.iloc[-(VOLUME_LOOKBACK + 1):-1].mean()
    son_hacim   = volume.iloc[-1]

    skor = 0

    # RSI
    if son_rsi >= 70:
        rsi_durum, rsi_emoji = f"Aşırı alım ({son_rsi:.1f})", "🔴"
        skor -= 1
    elif son_rsi <= 30:
        rsi_durum, rsi_emoji = f"Aşırı satım ({son_rsi:.1f})", "🟢"
        skor += 1
    elif son_rsi >= 55:
        rsi_durum, rsi_emoji = f"Güçlü bölge ({son_rsi:.1f})", "🟡"
        skor += 1
    elif son_rsi <= 45:
        rsi_durum, rsi_emoji = f"Zayıf bölge ({son_rsi:.1f})", "🟡"
        skor -= 1
    else:
        rsi_durum, rsi_emoji = f"Nötr ({son_rsi:.1f})", "⚪"

    # MACD
    if son_hist > 0 and son_hist > onceki_hist:
        macd_durum, macd_emoji = "Pozitif momentum güçleniyor", "🟢"
        skor += 1
    elif son_hist > 0 and son_hist <= onceki_hist:
        macd_durum, macd_emoji = "Pozitif ama momentum zayıflıyor", "🟡"
    elif son_hist < 0 and son_hist < onceki_hist:
        macd_durum, macd_emoji = "Negatif momentum güçleniyor", "🔴"
        skor -= 1
    else:
        macd_durum, macd_emoji = "Negatif ama momentum zayıflıyor", "🟡"

    # Trend
    if ema_fast.iloc[-1] > ema_slow.iloc[-1]:
        trend, trend_emoji = "Yukarı yönlü (EMA50 &gt; EMA200)", "🟢"
        skor += 1
    else:
        trend, trend_emoji = "Aşağı yönlü (EMA50 &lt; EMA200)", "🔴"
        skor -= 1

    # Hacim
    if son_hacim > ort_hacim * 1.3:
        hacim_durum, hacim_emoji = "Ortalamanın belirgin üzerinde", "📊"
    elif son_hacim < ort_hacim * 0.7:
        hacim_durum, hacim_emoji = "Ortalamanın belirgin altında", "📉"
    else:
        hacim_durum, hacim_emoji = "Ortalama seviyede", "➡️"

    # Gösterge hizalamasına dayalı olasılık: her puan %6.5 ağırlık
    # skor=+3 → %70, skor=0 → %50, skor=-3 → %30
    prob_up = round(max(0.28, min(0.72, 0.50 + skor * 0.065)), 3)

    # Genel okuma
    if skor >= 2:
        genel_okuma = "Göstergeler genel olarak yukarı eğilimli"
        genel_emoji = "📈"
    elif skor <= -2:
        genel_okuma = "Göstergeler genel olarak aşağı eğilimli"
        genel_emoji = "📉"
    else:
        genel_okuma = "Göstergeler karışık / nötr"
        genel_emoji = "↔️"

    return TeknikOzet(
        sembol=sembol_kisa, fiyat=son_fiyat,
        rsi=son_rsi, rsi_durum=rsi_durum, rsi_emoji=rsi_emoji,
        macd_durum=macd_durum, macd_emoji=macd_emoji,
        trend=trend, trend_emoji=trend_emoji,
        hacim_durum=hacim_durum, hacim_emoji=hacim_emoji,
        genel_okuma=genel_okuma, genel_emoji=genel_emoji,
        skor=skor, prob_up=prob_up,
    )


# ── Mesaj oluşturma ───────────────────────────────────────────
def ozet_mesaji_olustur(
    ozetler: list[TeknikOzet],
    saat_str: str,
    history: list,
    hour_tr: int,
    dow: int,
) -> str:
    gun = _DAYS_FULL_TR[dow]
    lines = [f"📡 <b>3. ANALİZ — 4 Saatlik Teknik Özet</b>\n🕐 {saat_str}\n{'━'*26}"]

    for o in ozetler:
        prob_down  = 1.0 - o.prob_up
        yuzde_up   = int(o.prob_up * 100)
        yuzde_down = int(prob_down * 100)

        if o.prob_up >= 0.55:
            yon_emoji = "📈"
            yon_str   = f"<b>%{yuzde_up} artar</b> / %{yuzde_down} düşer"
        elif o.prob_up <= 0.45:
            yon_emoji = "📉"
            yon_str   = f"%{yuzde_up} artar / <b>%{yuzde_down} düşer</b>"
        else:
            yon_emoji = "↔️"
            yon_str   = f"%{yuzde_up} artar / %{yuzde_down} düşer"

        # Geçmiş başarı istatistiği
        sym_full    = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}[o.sembol]
        dow_w, dow_n = get_stats(history, sym_full, hour_tr, dow)
        all_w, all_n = get_stats(history, sym_full, hour_tr)
        if dow_n >= 3:
            gecmis = f"{gun} {hour_tr:02d}:00: {stat_str(dow_w, dow_n)}  |  genel: {stat_str(all_w, all_n)}"
        else:
            gecmis = f"{hour_tr:02d}:00 genel: {stat_str(all_w, all_n)}"

        lines.append(
            f"\n<b>{o.sembol}</b>  {o.fiyat:,.2f} USDT\n"
            f"  {yon_emoji} <b>Olasılık (4h):</b>  {yon_str}\n"
            f"  📊 <i>Geçmiş:</i>  {gecmis}"
        )

    lines.append(
        f"\n{'━'*26}\n"
        f"<i>⚠️ Bu mesaj yatırım tavsiyesi değildir. "
        f"Standart teknik göstergelerin objektif okumasıdır.</i>"
    )
    return "\n".join(lines)


# ── State & History ──────────────────────────────────────────
INITIAL_BALANCE = 300.0

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": INITIAL_BALANCE, "total_pnl": 0.0, "open_predictions": []}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_history(history: list) -> None:
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


# ── İstatistik ────────────────────────────────────────────────
def get_stats(history: list, symbol: str, hour_tr: int, dow: int | None = None) -> tuple[int, int]:
    trades = [
        t for t in history
        if t["symbol"] == symbol
        and t.get("entry_hour_tr") == hour_tr
        and (dow is None or t.get("entry_dow") == dow)
    ]
    wins = sum(1 for t in trades if t["win"])
    return wins, len(trades)


def stat_str(wins: int, total: int) -> str:
    if total == 0:
        return "ilk veri"
    warn = " ⚠️" if total < MIN_STAT_COUNT else ""
    return f"%{wins/total*100:.0f} ({wins}/{total}){warn}"


# ── Telegram ─────────────────────────────────────────────────
def tg_send(text: str) -> None:
    import json as _json
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = _json.dumps({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        print("Mesaj Telegram'a gönderildi.")
    except Exception as e:
        print(f"[TG] Hata: {e}", file=sys.stderr)


# ── Ana akış ─────────────────────────────────────────────────
def main():
    now_tr   = datetime.now(timezone.utc).astimezone(_TZ_TR)
    hour_tr  = now_tr.hour
    dow      = now_tr.weekday()
    saat_str = now_tr.strftime("%d.%m.%Y %H:%M İST")

    state   = load_state()
    history = load_history()

    # 1. Önceki tahminleri kapat
    kapanan_lines = []
    for pred in list(state["open_predictions"]):
        sym_full = pred["symbol"]
        kisa     = sym_full.replace("USDT", "")
        amount   = pred.get("amount", 10.0)
        try:
            df            = fetch_klines(sym_full, limit=2)
            current_price = float(df["close"].iloc[-1])
            entry         = pred["entry_price"]
            predicted_dir = pred["predicted_dir"]
            actual        = "UP" if current_price >= entry else "DOWN"
            win           = (predicted_dir == actual)
            pnl           = amount if win else -amount

            state["balance"]   = round(state.get("balance", INITIAL_BALANCE) + pnl, 2)
            state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

            history.append({
                "symbol":        sym_full,
                "predicted_dir": predicted_dir,
                "actual_dir":    actual,
                "win":           win,
                "entry_price":   entry,
                "exit_price":    current_price,
                "amount":        amount,
                "pnl":           pnl,
                "entry_time_tr": pred["entry_time_tr"],
                "entry_hour_tr": pred["entry_hour_tr"],
                "entry_dow":     pred["entry_dow"],
                "exit_time_tr":  now_tr.isoformat(),
                "ind_rsi_vote":  pred.get("ind_rsi_vote"),
                "ind_rsi_ok":    (pred.get("ind_rsi_vote") == actual) if pred.get("ind_rsi_vote") else None,
                "ind_macd_vote": pred.get("ind_macd_vote"),
                "ind_macd_ok":   (pred.get("ind_macd_vote") == actual) if pred.get("ind_macd_vote") else None,
                "ind_ema_vote":  pred.get("ind_ema_vote"),
                "ind_ema_ok":    (pred.get("ind_ema_vote") == actual) if pred.get("ind_ema_vote") else None,
            })
            icon = "✅" if win else "❌"
            pct  = (current_price - entry) / entry * 100
            kapanan_lines.append(
                f"{icon} <b>{kisa}</b> {predicted_dir}  "
                f"{entry:.2f}→{current_price:.2f} ({pct:+.2f}%)  "
                f"<b>{'+'if win else ''}{pnl:.0f}$</b>"
            )
            print(f"[3. ANALİZ] {kisa} kapatıldı: {icon} {predicted_dir} → {actual} | {pnl:+.0f}$")
        except Exception as e:
            print(f"[3. ANALİZ] {kisa} kapatma hatası: {e}", file=sys.stderr)
        time.sleep(0.2)

    state["open_predictions"] = []
    save_history(history)

    # 2. Yeni analiz yap
    ozetler = []
    for kisa_ad, sembol in SYMBOLS.items():
        try:
            df   = fetch_klines(sembol)
            ozet = analiz_et(kisa_ad, df)
            ozetler.append((ozet, float(df["close"].iloc[-1])))
        except Exception as e:
            print(f"{kisa_ad} için veri alınamadı: {e}", file=sys.stderr)
        time.sleep(0.3)

    # Olasılık uzaklığına göre sırala (50'den ne kadar uzak)
    ozetler.sort(key=lambda x: abs(x[0].prob_up - 0.5), reverse=True)

    # Para dağılımı: 1. → $20, 2. → $12, 3. → $8
    amounts = [20.0, 12.0, 8.0]
    for i, (ozet, entry_price) in enumerate(ozetler):
        amount        = amounts[i] if i < len(amounts) else 0.0
        predicted_dir = "UP" if ozet.prob_up >= 0.50 else "DOWN"
        if amount > 0:
            state["open_predictions"].append({
                "symbol":        {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}[ozet.sembol],
                "predicted_dir": predicted_dir,
                "entry_price":   entry_price,
                "amount":        amount,
                "entry_time_tr": now_tr.isoformat(),
                "entry_hour_tr": hour_tr,
                "entry_dow":     dow,
                "ind_rsi_vote":  "UP" if ozet.rsi < 50 else "DOWN",
                "ind_macd_vote": "UP" if "Pozitif" in ozet.macd_durum else "DOWN",
                "ind_ema_vote":  "UP" if "Yukarı" in ozet.trend else "DOWN",
            })

    save_state(state)

    if not ozetler:
        print("Hiçbir sembol için veri alınamadı.", file=sys.stderr)
        return

    just_ozetler = [o for o, _ in ozetler]

    # 3. Kapanış özeti + yeni işlemler Telegram mesajına ekle
    total_pnl  = state.get("total_pnl", 0.0)
    pnl_icon   = "🟢" if total_pnl >= 0 else "🔴"
    closed_all = len(history)
    win_all    = sum(1 for t in history if t["win"])
    genel      = f"%{win_all/closed_all*100:.0f}" if closed_all else "—"

    ozet_suffix = ""
    if kapanan_lines:
        ozet_suffix = (
            "\n\n📌 <b>Kapanan işlemler</b>\n" +
            "\n".join(kapanan_lines) +
            f"\n{pnl_icon} Bakiye: <b>${state['balance']:.2f}</b>  "
            f"|  Toplam P&L: <b>{'+'if total_pnl>=0 else ''}{total_pnl:.2f}$</b>  "
            f"|  {genel} ({closed_all} işlem)"
        )

    # Yeni işlemler özeti
    yeni_lines = []
    for i, (ozet, _) in enumerate(ozetler):
        amount = amounts[i] if i < len(amounts) else 0
        if amount > 0:
            predicted_dir = "UP" if ozet.prob_up >= 0.50 else "DOWN"
            dir_icon = "📈" if predicted_dir == "UP" else "📉"
            yuzde = int(max(ozet.prob_up, 1 - ozet.prob_up) * 100)
            rank  = "1." if i == 0 else "2."
            yeni_lines.append(f"  {rank} {dir_icon} <b>{ozet.sembol}</b> {predicted_dir}  %{yuzde}  → <b>{amount:.0f}$</b>")

    if yeni_lines:
        ozet_suffix += "\n\n🆕 <b>Yeni işlemler</b>\n" + "\n".join(yeni_lines)

    mesaj = ozet_mesaji_olustur(just_ozetler, saat_str, history, hour_tr, dow)
    if ozet_suffix:
        mesaj += ozet_suffix

    tg_send(mesaj)
    print(f"[3. ANALİZ] {saat_str} — {len(just_ozetler)} özet, {len(state['open_predictions'])} yeni işlem, bakiye: ${state['balance']:.2f}")


# ── Weekly: Pazar 00:00 — ısı haritası ───────────────────────
def _wr(wins: int, total: int) -> str:
    if total == 0:
        return "veri yok"
    return f"%{wins/total*100:.0f} ({wins}/{total})"


def _ind_stats_lines(history: list) -> list[str]:
    checks = [("RSI", "ind_rsi_ok"), ("MACD", "ind_macd_ok"), ("EMA", "ind_ema_ok")]
    lines = []
    for label, key in checks:
        vals = [t[key] for t in history if t.get(key) is not None]
        if vals:
            w   = sum(1 for v in vals if v)
            n   = len(vals)
            bar = "🟢" if w / n >= 0.6 else "🟡" if w / n >= 0.5 else "🔴"
            lines.append(f"  {bar} {label}: {_wr(w, n)}")
        else:
            lines.append(f"  ⚪ {label}: veri yok")
    return lines


def run_weekly() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as _np

    history = load_history()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)
    _DAYS_TR = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

    grid_w = [[0]*24 for _ in range(7)]
    grid_n = [[0]*24 for _ in range(7)]
    for t in history:
        d = t.get("entry_dow")
        h = t.get("entry_hour_tr")
        if d is None or h is None:
            continue
        grid_n[d][h] += 1
        if t["win"]:
            grid_w[d][h] += 1

    rate = _np.full((7, 24), _np.nan)
    for d in range(7):
        for h in range(24):
            if grid_n[d][h] >= 3:
                rate[d][h] = grid_w[d][h] / grid_n[d][h]

    fig, ax = plt.subplots(figsize=(14, 5))
    fig.patch.set_facecolor("#0a0e1a")
    ax.set_facecolor("#0a0e1a")

    cmap = mcolors.LinearSegmentedColormap.from_list(
        "cyan_green", ["#1a2a2a", "#006064", "#00e5ff"], N=256
    )
    cmap.set_bad(color="#141820")
    masked = _np.ma.masked_invalid(rate)
    im = ax.imshow(masked, cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")

    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=7, color="#78909c")
    ax.set_yticks(range(7))
    ax.set_yticklabels(_DAYS_TR, fontsize=9, color="#b0bec5", fontweight="bold")
    ax.tick_params(length=0)

    for d in range(7):
        for h in range(24):
            if not _np.isnan(rate[d][h]):
                pct  = int(rate[d][h] * 100)
                n    = grid_n[d][h]
                warn = "⚠" if n < MIN_STAT_COUNT else ""
                clr  = "white" if rate[d][h] >= 0.55 else "#78909c"
                ax.text(h, d, f"%{pct}{warn}\n({n})", ha="center", va="center",
                        fontsize=5.5, color=clr, linespacing=1.3)

    for x in range(25):
        ax.axvline(x - 0.5, color="#0a0e1a", linewidth=0.5)
    for y in range(8):
        ax.axhline(y - 0.5, color="#0a0e1a", linewidth=0.5)

    total = len(history)
    wins  = sum(1 for t in history if t["win"])
    genel = f"%{wins/total*100:.0f}" if total else "—"

    ax.set_title(
        f"3. ANALİZ — 4 Saatlik Teknik Başarı Haritası  ({now_tr.strftime('%d.%m.%Y')})\n"
        f"Toplam: {total} tahmin  |  {genel} doğruluk  |  RSI+MACD+EMA gösterge hizalaması",
        color="#00e5ff", fontsize=10, fontweight="bold", pad=10
    )
    ax.set_xlabel("Saat (İST)", color="#546e7a", fontsize=8)

    cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
    cbar.ax.yaxis.set_tick_params(color="#546e7a")
    cbar.set_label("Başarı Oranı", color="#546e7a", fontsize=8)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="#546e7a", fontsize=7)
    cbar.set_ticks([0.4, 0.5, 0.6, 0.7, 0.8])
    cbar.set_ticklabels(["%40", "%50", "%60", "%70", "%80"])

    plt.tight_layout(pad=1.2)
    img_path = "/tmp/teknik_weekly_heatmap.png"
    plt.savefig(img_path, dpi=150, bbox_inches="tight",
                facecolor="#0a0e1a", pad_inches=0.1)
    plt.close()

    caption = (
        f"📡 3. ANALİZ Haftalık Rapor — {now_tr.strftime('%d.%m.%Y')}\n"
        f"Toplam {total} tahmin | {genel} doğruluk | 4h RSI+MACD+EMA"
    )

    try:
        with open(img_path, "rb") as f:
            img_data = f.read()
        boundary = "----TeknikBoundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{CHAT_ID}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"teknik_heatmap.png\"\r\nContent-Type: image/png\r\n\r\n"
        ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
        print(f"[3. ANALİZ weekly] görsel gönderildi — {total} tahmin")
    except Exception as e:
        print(f"[3. ANALİZ weekly] Hata: {e}", file=sys.stderr)

    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    ind_lines = _ind_stats_lines(history)
    stats_msg = (
        f"📊 <b>3. ANALİZ HAFTALIK İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y')} İST\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {genel} başarı\n"
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"\n🔬 <b>İndikatör İsabet Oranı</b>\n"
        + "\n".join(ind_lines)
    )
    tg_send(stats_msg)


def run_stats() -> None:
    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)
    total     = len(history)
    wins      = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    genel     = f"%{wins/total*100:.0f}" if total else "—"
    ind_lines = _ind_stats_lines(history)

    dow_data: dict[int, list] = {}
    for t in history:
        d = t.get("entry_dow")
        if d is None:
            continue
        dow_data.setdefault(d, [0, 0])
        dow_data[d][1] += 1
        if t["win"]:
            dow_data[d][0] += 1

    dow_lines = []
    _DAYS_TR = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
    for d in range(7):
        if d not in dow_data:
            continue
        w, n = dow_data[d]
        bar = "🟢" if w/n >= 0.6 else "🟡" if w/n >= 0.5 else "🔴"
        dow_lines.append(f"  {bar} {_DAYS_TR[d]}: {_wr(w, n)}")

    sym_lines = []
    for kisa, full in {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}.items():
        s = [t for t in history if t["symbol"] == full]
        if s:
            sw = sum(1 for t in s if t["win"])
            sym_lines.append(f"  {'🟢' if sw/len(s)>=0.6 else '🟡' if sw/len(s)>=0.5 else '🔴'} {kisa}: {_wr(sw, len(s))}")

    parts = [
        f"📊 <b>3. ANALİZ İSTATİSTİKLER</b>",
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Toplam: {total} işlem  |  {genel} başarı",
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}",
    ]
    if sym_lines:
        parts.append(f"\n📌 <b>Sembol Bazlı</b>")
        parts.extend(sym_lines)
    if dow_lines:
        parts.append(f"\n📆 <b>Gün Bazlı</b>")
        parts.extend(dow_lines)
    parts.append(f"\n🔬 <b>İndikatör İsabet Oranı</b>")
    parts.extend(ind_lines)
    tg_send("\n".join(parts))
    print("[3. ANALİZ stats] gönderildi")


if __name__ == "__main__":
    import sys as _sys
    mode = _sys.argv[1] if len(_sys.argv) > 1 else "main"
    if mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        main()
