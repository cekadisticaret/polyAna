#!/usr/bin/env python3
"""
Twitter/X Otomatik Poster - @ZekaChain
BIST ve Kripto alınabilir listelerini görsel olarak paylaşır.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import tweepy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np
import urllib.request
import json
from datetime import datetime, timezone
from twitter_config import API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET

def get_twitter_client():
    client = tweepy.Client(
        consumer_key=API_KEY,
        consumer_secret=API_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET
    )
    auth = tweepy.OAuth1UserHandler(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
    api  = tweepy.API(auth)
    return client, api

def create_crypto_image(buyable, now_str, output="/tmp/zc_crypto.png"):
    n = len(buyable)
    fig, ax = plt.subplots(figsize=(6, 3.5 + n * 0.55))
    fig.patch.set_facecolor('#0a0e1a')
    ax.set_facecolor('#0a0e1a')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    y = 0.97
    ax.text(0.5, y, '📊 Kripto — Alınabilir Liste', transform=ax.transAxes,
            fontsize=13, fontweight='bold', color='#00e5ff', ha='center', va='top')
    ax.text(0.5, y - 0.07, f'🕐 {now_str}  |  30 Dakika  |  Binance Futures',
            transform=ax.transAxes, fontsize=8, color='#78909c', ha='center', va='top')
    y -= 0.17

    for i, r in enumerate(buyable):
        bg = '#131929' if i % 2 == 0 else '#0d1220'
        ax.add_patch(FancyBboxPatch((0.03, y - 0.10), 0.94, 0.11,
            boxstyle="round,pad=0.01", facecolor=bg, edgecolor='#1e3a5f', linewidth=1,
            transform=ax.transAxes))
        ax.text(0.08, y - 0.05, r['symbol'], transform=ax.transAxes,
                fontsize=11, fontweight='bold', color='#00e5ff', va='center')
        ax.text(0.92, y - 0.05, f"{r['change_pct']:+.2f}%", transform=ax.transAxes,
                fontsize=11, fontweight='bold', color='#69f0ae', va='center', ha='right')
        ax.text(0.92, y - 0.08, f"${r['price']:.5g}", transform=ax.transAxes,
                fontsize=8, color='#90caf9', va='center', ha='right')
        y -= 0.13

    ax.text(0.5, 0.02, '⚠️ Yatırım tavsiyesi değildir | @ZekaChain',
            transform=ax.transAxes, fontsize=7, color='#37474f', ha='center')

    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches='tight', facecolor='#0a0e1a', pad_inches=0.1)
    plt.close()
    return output

def create_bist_image(results, now_str, output="/tmp/zc_bist.png"):
    n = len(results)
    if n == 0:
        return None
    fig, ax = plt.subplots(figsize=(6, 3.5 + n * 0.55))
    fig.patch.set_facecolor('#0a0e1a')
    ax.set_facecolor('#0a0e1a')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    y = 0.97
    ax.text(0.5, y, '📊 BIST — Alınabilir Liste', transform=ax.transAxes,
            fontsize=13, fontweight='bold', color='#4fc3f7', ha='center', va='top')
    ax.text(0.5, y - 0.07, f'🕐 {now_str}  |  1 Saatlik  |  BIST',
            transform=ax.transAxes, fontsize=8, color='#78909c', ha='center', va='top')
    y -= 0.17

    for i, r in enumerate(results):
        bg = '#131929' if i % 2 == 0 else '#0d1220'
        ax.add_patch(FancyBboxPatch((0.03, y - 0.10), 0.94, 0.11,
            boxstyle="round,pad=0.01", facecolor=bg, edgecolor='#1e4d2b', linewidth=1,
            transform=ax.transAxes))
        ax.text(0.08, y - 0.05, r['ticker'], transform=ax.transAxes,
                fontsize=11, fontweight='bold', color='#69f0ae', va='center')
        ax.text(0.55, y - 0.05, f"RSI: {r['rsi']}  ADX: {r['adx']}", transform=ax.transAxes,
                fontsize=8, color='#ffd54f', va='center')
        ax.text(0.92, y - 0.05, f"{r['price']} ₺", transform=ax.transAxes,
                fontsize=10, fontweight='bold', color='#ffffff', va='center', ha='right')
        y -= 0.13

    ax.text(0.5, 0.02, '⚠️ Yatırım tavsiyesi değildir | @ZekaChain',
            transform=ax.transAxes, fontsize=7, color='#37474f', ha='center')

    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches='tight', facecolor='#0a0e1a', pad_inches=0.1)
    plt.close()
    return output

def post_tweet(client, api, text, img_path=None):
    if img_path:
        try:
            media = api.media_upload(filename=img_path)
            client.create_tweet(text=text, media_ids=[media.media_id])
            return
        except Exception:
            pass
    client.create_tweet(text=text)

def post_crypto_tweet():
    from crypto_tweet_generator import fetch_all_changes
    now = datetime.now(timezone.utc)
    ist_h   = (now.hour + 3) % 24
    now_str = f"{now.strftime('%d.%m.%Y')} {ist_h:02d}:{now.strftime('%M')}"

    print("📊 Kripto verileri alınıyor...")
    results = fetch_all_changes()
    buyable = sorted([r for r in results if r["change_pct"] < 0],
                     key=lambda x: x["change_pct"])[:5]

    if not buyable:
        print("Alınabilir coin bulunamadı.")
        return

    img = create_crypto_image(buyable, now_str)
    lines = "\n".join([f"{r['symbol']} {r['change_pct']:+.1f}% ${r['price']:.5g}" for r in buyable])
    tweet = f"📊 Kripto — 30dk En Çok Düşenler\n🕐 {now_str}\n\n{lines}\n\n⚠️ Yatırım tavsiyesi değildir\n#Kripto #Bitcoin #ZekaChain"

    print("🐦 Tweet atılıyor...")
    client, api = get_twitter_client()
    post_tweet(client, api, tweet, img)
    print("✅ Kripto tweet atıldı!")

def post_bist_tweet():
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from bist_scanner import scan
    now = datetime.now(timezone.utc)
    ist_h   = (now.hour + 3) % 24
    now_str = f"{now.strftime('%d.%m.%Y')} {ist_h:02d}:{now.strftime('%M')}"

    print("📊 BIST taranıyor...")
    results = scan("1h")

    if not results:
        print("BIST'te uygun hisse bulunamadı.")
        return

    img = create_bist_image(results, now_str)
    if not img:
        return

    lines = "\n".join([f"{r['ticker']} {r['price']}₺ RSI:{r['rsi']} ADX:{r['adx']}" for r in results[:5]])
    tweet = f"📊 BIST — 1s Alım Fırsatları\n🕐 {now_str}\n\n{lines}\n\n⚠️ Yatırım tavsiyesi değildir\n#BIST #Borsa #ZekaChain"

    print("🐦 BIST tweet atılıyor...")
    client, api = get_twitter_client()
    post_tweet(client, api, tweet, img)
    print("✅ BIST tweet atıldı!")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode in ("crypto", "both"):
        post_crypto_tweet()
    if mode in ("bist", "both"):
        post_bist_tweet()
