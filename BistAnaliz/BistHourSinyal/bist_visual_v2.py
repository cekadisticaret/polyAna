#!/usr/bin/env python3
"""
BIST Tarayıcı - Mobil Uyumlu Görsel v2
Dikey (portrait) format, kart tasarımı, telefonda okunması kolay.
Trend + Momentum iki ayrı bölüm.

Konum: BistAnaliz/BistHourSinyal/ — BistAnaliz/bist_scanner.py ve kök telegram_config kullanır.
"""

import sys
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))
_BISTANALIZ = os.path.abspath(os.path.join(_ROOT, ".."))
_REPO = os.path.abspath(os.path.join(_ROOT, "..", ".."))
sys.path.insert(0, _BISTANALIZ)
sys.path.insert(0, _REPO)

import urllib.request
import urllib.parse
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from matplotlib.gridspec import GridSpec
import numpy as np
from datetime import datetime, timezone
from bist_scanner import scan, scan_momentum

try:
    import telegram_config as _tg
    BOT_TOKEN = _tg.BOT_TOKEN
    CHAT_ID = _tg.CHAT_ID
    _hour = getattr(_tg, "CHAT_ID_BIST_HOUR", "") or ""
    TG_CHAT_ID = (_hour.strip() if _hour else "") or CHAT_ID
except ImportError:
    BOT_TOKEN = ""
    CHAT_ID = ""
    TG_CHAT_ID = ""


def _draw_section_header(ax, y, title, color_bg, color_edge, color_text):
    ax.add_patch(FancyBboxPatch((0.03, y - 0.058), 0.94, 0.06,
        boxstyle="round,pad=0.01", facecolor=color_bg, edgecolor=color_edge, linewidth=1.2,
        transform=ax.transAxes))
    ax.text(0.5, y - 0.027, title, transform=ax.transAxes,
            fontsize=10, fontweight='bold', color=color_text, ha='center', va='center')
    return y - 0.075


def _draw_card(ax, y, r, card_h, is_momentum=False):
    gc = r.get('golden_cross', 'YOK')
    rsi_color  = '#ef5350' if r['rsi'] > 70 else '#ffd54f' if r['rsi'] > 60 else '#69f0ae'
    adx_color  = '#69f0ae' if r['adx'] > 30 else '#ffd54f'
    dpct       = r.get('daily_pct', 0.0)
    dpct_color = '#ef5350' if dpct < 0 else '#69f0ae' if dpct >= 5 else '#ffd54f'

    edge_color = '#2d4a1e' if is_momentum else ('#1e4d2b' if gc == 'EVET' else '#1e2d4d')

    ax.add_patch(FancyBboxPatch((0.03, y - card_h + 0.01), 0.94, card_h,
        boxstyle="round,pad=0.012", facecolor='#131929',
        edgecolor=edge_color, linewidth=1.2,
        transform=ax.transAxes))

    # Hisse adı + fiyat
    ax.text(0.09, y - 0.028, r['ticker'], transform=ax.transAxes,
            fontsize=15, fontweight='bold', color='#ffa726' if is_momentum else '#69f0ae', va='center')
    ax.text(0.91, y - 0.028, f"{r['price']} ₺", transform=ax.transAxes,
            fontsize=12, fontweight='bold', color='#ffffff', va='center', ha='right')

    # İndikatör satırı
    indicator_y = y - 0.078
    if is_momentum:
        items = [
            ('RSI',     f"{r['rsi']}",        rsi_color),
            ('GÜNLÜK',  f"%{dpct:+.1f}",      dpct_color),
            ('HACİM',   f"{r['tl_vol_sma_m']}M", '#90caf9'),
        ]
        x_pos = [0.09, 0.35, 0.63]
    else:
        items = [
            ('RSI',    f"{r['rsi']}",         rsi_color),
            ('ADX',    f"{r['adx']}",          adx_color),
            ('GÜNLÜK', f"%{dpct:+.1f}",        dpct_color),
            ('HACİM',  f"{r['tl_vol_sma_m']}M", '#90caf9'),
        ]
        x_pos = [0.09, 0.31, 0.56, 0.76]

    for (label, val, color), xp in zip(items, x_pos):
        ax.text(xp, indicator_y + 0.018, label, transform=ax.transAxes,
                fontsize=6.5, color='#546e7a', va='center')
        ax.text(xp, indicator_y - 0.012, val, transform=ax.transAxes,
                fontsize=10, fontweight='bold', color=color, va='center')

    # Golden Cross badge (sadece trend)
    if not is_momentum and gc == 'EVET':
        ax.add_patch(FancyBboxPatch((0.73, y - 0.135), 0.2, 0.032,
            boxstyle="round,pad=0.005", facecolor='#1b3a1b', edgecolor='#69f0ae', linewidth=0.8,
            transform=ax.transAxes))
        ax.text(0.83, y - 0.119, '✨ Golden Cross', transform=ax.transAxes,
                fontsize=7, color='#69f0ae', ha='center', va='center')

    # Kriter satırı
    if is_momentum:
        criterias = ['VOL×2✅', 'RSI>60✅', 'LİK✅']
    else:
        criterias = ['EMA✅', 'RSI✅', 'ADX✅', 'MACD✅', 'VOL✅', 'LİK✅']
    for ci, crit in enumerate(criterias):
        cx = 0.08 + ci * (0.85 / len(criterias))
        ax.text(cx, y - 0.142, crit, transform=ax.transAxes,
                fontsize=6.5, color='#37474f', va='center')

    return y - (card_h + 0.018)


MAX_TREND_CARDS = 5
MAX_MOM_CARDS   = 5

def create_mobile_image(trend_results, momentum_results, interval, tarih, saat,
                        output_path='/tmp/bist_mobile.png'):
    trend_show = sorted(trend_results, key=lambda x: x['rsi'], reverse=True)[:MAX_TREND_CARDS]
    mom_show   = sorted(momentum_results, key=lambda x: x['daily_pct'], reverse=True)[:MAX_MOM_CARDS]

    n_trend = len(trend_show)
    n_mom   = len(mom_show)
    n_total = n_trend + n_mom

    fig_h = 4.5 + n_total * 2.1 + (0.5 if n_mom > 0 else 0)
    fig, ax = plt.subplots(figsize=(6, fig_h))
    fig.patch.set_facecolor('#0a0e1a')
    ax.set_facecolor('#0a0e1a')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    y = 0.98

    # === HEADER ===
    ax.add_patch(FancyBboxPatch((0.03, y - 0.09), 0.94, 0.1,
        boxstyle="round,pad=0.01", facecolor='#131929', edgecolor='#1e3a5f', linewidth=1.5,
        transform=ax.transAxes))
    ax.text(0.5, y - 0.025, '📊  BIST Günlük Analiz', transform=ax.transAxes,
            fontsize=14, fontweight='bold', color='#4fc3f7', ha='center', va='center')
    ax.text(0.5, y - 0.065, f'🕐 {tarih}   {saat} İST   {interval.upper()}',
            transform=ax.transAxes, fontsize=9, color='#78909c', ha='center', va='center')
    y -= 0.115

    # === ÖZET BADGE ===
    has_any = n_total > 0
    badge_color      = '#1b3a1b' if has_any else '#3a1b1b'
    badge_text_color = '#69f0ae' if has_any else '#ef9a9a'
    badge_text = (f'🟢 {n_trend} Trend  🚀 {n_mom} Momentum') if has_any else '🔴  Uygun Hisse Bulunamadı'
    ax.add_patch(FancyBboxPatch((0.03, y - 0.055), 0.94, 0.058,
        boxstyle="round,pad=0.01", facecolor=badge_color, edgecolor=badge_text_color, linewidth=1,
        transform=ax.transAxes))
    ax.text(0.5, y - 0.026, badge_text, transform=ax.transAxes,
            fontsize=10, fontweight='bold', color=badge_text_color, ha='center', va='center')
    y -= 0.075

    card_h = 0.175

    # === TREND KARTLARI ===
    n_trend_total = len(trend_results)
    if trend_show:
        label = f'📈  TREND  —  {n_trend_total} Hisse' + (f'  (ilk {MAX_TREND_CARDS})' if n_trend_total > MAX_TREND_CARDS else '')
        y = _draw_section_header(ax, y, label, '#0d1f0d', '#1e4d2b', '#69f0ae')
        for r in trend_show:
            y = _draw_card(ax, y, r, card_h, is_momentum=False)

    # === MOMENTUM KARTLARI ===
    n_mom_total = len(momentum_results)
    if mom_show:
        label = f'🚀  MOMENTUM  —  {n_mom_total} Hisse' + (f'  (ilk {MAX_MOM_CARDS})' if n_mom_total > MAX_MOM_CARDS else '')
        y = _draw_section_header(ax, y, label, '#1f1500', '#ff8f00', '#ffa726')
        for r in mom_show:
            y = _draw_card(ax, y, r, card_h, is_momentum=True)

    # === ALT FOOTER ===
    ax.add_patch(FancyBboxPatch((0.03, y - 0.055), 0.94, 0.052,
        boxstyle="round,pad=0.01", facecolor='#0d1117', edgecolor='#1e2d4d', linewidth=0.8,
        transform=ax.transAxes))
    ax.text(0.5, y - 0.027, '⚠️ Bu paylaşım yatırım tavsiyesi değildir.',
            transform=ax.transAxes, fontsize=7.5, color='#37474f', ha='center', va='center')

    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    plt.savefig(output_path, dpi=160, bbox_inches='tight', facecolor='#0a0e1a', pad_inches=0.1)
    plt.close()
    return output_path


def send_photo(path):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(path, 'rb') as f:
        boundary = '----boundary'
        body = (
            f'------boundary\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{TG_CHAT_ID}\r\n'
            f'------boundary\r\nContent-Disposition: form-data; name="photo"; filename="bist.png"\r\nContent-Type: image/png\r\n\r\n'
        ).encode() + f.read() + b'\r\n------boundary--\r\n'
    req = urllib.request.Request(url, data=body,
                                 headers={'Content-Type': 'multipart/form-data; boundary=----boundary'})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=body)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def calc_score(r):
    score = 0
    rsi = r.get("rsi", 0)
    adx = r.get("adx", 0)
    dpct = r.get("daily_pct", 0)
    vol = r.get("tl_vol_sma_m", 0)

    # ADX — trend gücü (0-35 puan)
    score += min(adx, 35)

    # RSI — ideal alım bölgesi 55-70 (0-35 puan)
    if 55 <= rsi <= 65:   score += 35   # tatlı nokta
    elif 65 < rsi <= 72:  score += 25   # ısınıyor
    elif 50 <= rsi < 55:  score += 15   # zayıf momentum
    elif rsi > 72:        score += 8    # aşırı alım

    # Günlük % — 1-8% ideal (0-20 puan), çok fazla hareket = düşük puan
    if 1 <= dpct <= 4:    score += 20
    elif 4 < dpct <= 8:   score += 12
    elif dpct > 8:        score += 4    # çok uzaklaşmış
    elif dpct > 0:        score += 8

    # Hacim — büyük hacim kurumsal ilgi (0-10 puan)
    score += min(vol / 50, 10)  # 500M TL = max 10 puan

    # Golden cross bonusu
    if r.get("golden_cross") == "EVET":
        score += 10

    return round(score, 1)


def run(interval="1h"):
    now = datetime.now(timezone.utc)
    istanbul_hour = (now.hour + 3) % 24
    tarih = now.strftime("%d.%m.%Y")
    saat = f"{istanbul_hour:02d}:{now.strftime('%M')}"

    print("🔍 Trend taraması başlıyor...")
    trend_results = scan(interval)

    print("🚀 Momentum taraması başlıyor...")
    momentum_results = scan_momentum()

    lines = [f"📊 <b>BIST Analiz</b> | {tarih} {saat} İST\n━━━━━━━━━━━━━━━━━━━━"]

    if not trend_results and not momentum_results:
        lines.append("🔴 Bu saatte uygun hisse bulunamadı.")
    else:
        if trend_results:
            top_trend = sorted(trend_results, key=lambda x: calc_score(x), reverse=True)[:MAX_TREND_CARDS]
            suffix = f"  (ilk {MAX_TREND_CARDS})" if len(trend_results) > MAX_TREND_CARDS else ""
            lines.append(f"\n📈 <b>TREND — {len(trend_results)} Hisse{suffix}</b>")
            for r in top_trend:
                score = calc_score(r)
                gc = " ✨" if r.get("golden_cross") == "EVET" else ""
                lines.append(
                    f"• <b>{r['ticker']}</b> {r['price']}₺"
                    f"  🎯<b>{score}</b>  RSI:{r['rsi']}  ADX:{r['adx']}"
                    f"  {r['daily_pct']:+.1f}%{gc}"
                )

        if momentum_results:
            top_mom = sorted(momentum_results, key=lambda x: calc_score(x), reverse=True)[:MAX_MOM_CARDS]
            suffix = f"  (ilk {MAX_MOM_CARDS})" if len(momentum_results) > MAX_MOM_CARDS else ""
            lines.append(f"\n🚀 <b>MOMENTUM — {len(momentum_results)} Hisse{suffix}</b>")
            for r in top_mom:
                score = calc_score(r)
                lines.append(
                    f"• <b>{r['ticker']}</b> {r['price']}₺"
                    f"  🎯<b>{score}</b>  RSI:{r['rsi']}"
                    f"  {r['daily_pct']:+.1f}%  {r['tl_vol_sma_m']}M"
                )

    lines.append("\n⚠️ Bu paylaşım yatırım tavsiyesi değildir.")
    msg = "\n".join(lines)
    send_message(msg)
    print(f"✅ Metin bildirimi gönderildi (Trend:{len(trend_results)}, Momentum:{len(momentum_results)})")


def run_example_notify():
    """Tarama yok; gerçek mesaj formatında tek örnek bildirim (Telegram test)."""
    now = datetime.now(timezone.utc)
    istanbul_hour = (now.hour + 3) % 24
    tarih = now.strftime("%d.%m.%Y")
    saat = f"{istanbul_hour:02d}:{now.strftime('%M')}"
    lines = [
        f"📊 <b>BIST Analiz</b> | {tarih} {saat} İST\n━━━━━━━━━━━━━━━━━━━━",
        "\n📈 <b>TREND — 127 Hisse  (ilk 5)</b>",
        "• <b>FROTO</b> 108.4₺  🎯<b>93.8</b>  RSI:61.9  ADX:38.5  +1.8%",
        "\n🚀 <b>MOMENTUM — 49 Hisse  (ilk 5)</b>",
        "• <b>EKGYO</b> 22.1₺  🎯<b>57.0</b>  RSI:60.4  +5.4%  1877.9M",
        "\n⚠️ Bu paylaşım yatırım tavsiyesi değildir.",
        "\n<i>— örnek / test mesajı (bist_visual_v2 --test) —</i>",
    ]
    send_message("\n".join(lines))
    print("✅ Örnek bildirim Telegram'a gönderildi.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--test", "--ornek", "test"):
        run_example_notify()
    else:
        interval = sys.argv[1] if len(sys.argv) > 1 else "1h"
        run(interval)
