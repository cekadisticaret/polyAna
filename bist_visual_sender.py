#!/usr/bin/env python3
"""
BIST Tarayıcı - Görsel Telegram Gönderici
Tarama sonuçlarını güzel bir tablo görseli olarak gönderir.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import urllib.request
import urllib.parse
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np
from datetime import datetime
from bist_scanner import scan
from telegram_config import BOT_TOKEN, CHAT_ID


def create_image(results, interval, tarih, saat):
    fig_h = max(4.5, 2.2 + len(results) * 0.85)
    fig, ax = plt.subplots(figsize=(10, fig_h))
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#0d1117')
    ax.axis('off')

    # Başlık
    ax.text(0.5, 0.97, '📊 BIST Günlük Analiz', transform=ax.transAxes,
            fontsize=18, fontweight='bold', color='#58d68d',
            ha='center', va='top', fontfamily='monospace')
    ax.text(0.5, 0.91, f'🕐 {tarih}  |  {saat} İST  |  {interval.upper()}',
            transform=ax.transAxes, fontsize=11, color='#aaaaaa',
            ha='center', va='top', fontfamily='monospace')

    if not results:
        ax.text(0.5, 0.55, '🔴 Bu taramada kriterleri geçen\nhisse bulunamadı.',
                transform=ax.transAxes, fontsize=13, color='#e74c3c',
                ha='center', va='center', fontfamily='monospace')
    else:
        ax.text(0.5, 0.85, f'🟢  {len(results)} Hisse Tüm Kriterleri Geçti',
                transform=ax.transAxes, fontsize=12, color='#f9e79f',
                ha='center', va='top', fontweight='bold', fontfamily='monospace')

        # Tablo başlıkları
        cols   = ['HİSSE', 'FİYAT', 'RSI', 'ADX', 'UZAKLIK', 'TL HACİM', 'GC']
        widths = [0.13,     0.12,    0.10,  0.10,   0.12,      0.14,       0.08]
        xs = [0.03]
        for w in widths[:-1]:
            xs.append(xs[-1] + w)

        header_y = 0.77
        for col, x, w in zip(cols, xs, widths):
            ax.text(x + w/2, header_y, col, transform=ax.transAxes,
                    fontsize=9.5, fontweight='bold', color='#85c1e9',
                    ha='center', va='center', fontfamily='monospace')

        # Çizgi
        line = plt.Line2D([0.02, 0.98], [header_y - 0.03, header_y - 0.03],
                          transform=ax.transAxes, color='#2e4057', linewidth=1.2)
        ax.add_line(line)

        row_h = 0.085
        for i, r in enumerate(sorted(results, key=lambda x: x['rsi'], reverse=True)):
            y = header_y - 0.07 - i * row_h
            bg_color = '#1a2332' if i % 2 == 0 else '#141c27'

            rect = FancyBboxPatch((0.02, y - 0.035), 0.96, row_h - 0.01,
                                  boxstyle="round,pad=0.005",
                                  linewidth=0, facecolor=bg_color,
                                  transform=ax.transAxes)
            ax.add_patch(rect)

            gc = r.get('golden_cross', 'YOK')
            values = [
                r['ticker'],
                f"{r['price']}",
                f"{r['rsi']}",
                f"{r['adx']}",
                f"%{r['dist_pct']}",
                f"{r['tl_vol_sma_m']}M",
                "✅" if gc == "EVET" else "➖"
            ]
            colors = [
                '#58d68d',   # ticker - yeşil
                '#ffffff',   # fiyat
                '#f9e79f' if r['rsi'] > 65 else '#58d68d',  # rsi
                '#58d68d' if r['adx'] > 25 else '#f9e79f',  # adx
                '#58d68d' if r['dist_pct'] < 3 else '#f9e79f',  # uzaklık
                '#ffffff',   # hacim
                '#58d68d' if gc == "EVET" else '#aaaaaa',   # gc
            ]
            for val, x, w, c in zip(values, xs, widths, colors):
                ax.text(x + w/2, y, val, transform=ax.transAxes,
                        fontsize=9.5, color=c, ha='center', va='center',
                        fontfamily='monospace', fontweight='bold' if val == r['ticker'] else 'normal')

    # Alt not
    ax.text(0.5, 0.02,
            '⚠️ Yatırım tavsiyesi değildir  |  EMA50/200 · RSI · ADX · MACD · Hacim · Likidite',
            transform=ax.transAxes, fontsize=7.5, color='#555555',
            ha='center', va='bottom', fontfamily='monospace')

    path = '/tmp/bist_scan.png'
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches='tight', facecolor='#0d1117')
    plt.close()
    return path


def send_photo(path, caption=""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(path, 'rb') as f:
        boundary = b'----boundary'
        body = (
            b'------boundary\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n' +
            CHAT_ID.encode() +
            b'\r\n------boundary\r\nContent-Disposition: form-data; name="photo"; filename="bist.png"\r\nContent-Type: image/png\r\n\r\n' +
            f.read() +
            b'\r\n------boundary--\r\n'
        )
    req = urllib.request.Request(url, data=body,
                                 headers={'Content-Type': 'multipart/form-data; boundary=----boundary'})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def run(interval="1h"):
    now_utc = datetime.utcnow()
    istanbul_hour = (now_utc.hour + 3) % 24
    tarih = now_utc.strftime("%d.%m.%Y")
    saat = f"{istanbul_hour:02d}:{now_utc.strftime('%M')}"

    print("🔍 Tarama başlıyor...")
    results = scan(interval)

    print("🎨 Görsel oluşturuluyor...")
    img_path = create_image(results, interval, tarih, saat)

    print("📤 Telegram'a gönderiliyor...")
    resp = send_photo(img_path)
    if resp.get("ok"):
        print(f"✅ Görsel gönderildi! ({len(results)} hisse)")
    else:
        print(f"❌ Hata: {resp}")


if __name__ == "__main__":
    interval = sys.argv[1] if len(sys.argv) > 1 else "1h"
    run(interval)
