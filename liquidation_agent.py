"""
╔══════════════════════════════════════════════════════════════╗
║         LİKİDASYON AJAN v1.0                                 ║
║  Binance Futures · Telegram · Paper Trading                  ║
╚══════════════════════════════════════════════════════════════╝

Mantık:
  Büyük likidasyon tespit edilir
  → Likide olan pozisyon yönünün tersi trade açılır
  → Örnek: $500K+ LONG likidasyon → SHORT sinyali
  → Çünkü o yönde aşırı kaldıraç varmış ve temizlendi

Kurulum:
  pip install -r requirements.txt
  cp .env.example .env  → API anahtarlarını doldur
  python liquidation_agent.py
"""

import asyncio
import json
import time
import os
import aiohttp
import websockets
from datetime import datetime
from dataclasses import dataclass, field
from collections import deque
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# YAPILANDIRMA
# ─────────────────────────────────────────────────────────────

TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT   = os.getenv("TELEGRAM_CHAT",  "")

# Likidasyon eşikleri
LIQ_SMALL  = 100_000    # $100K  — küçük, logla
LIQ_MEDIUM = 300_000    # $300K  — orta, bildir
LIQ_LARGE  = 500_000    # $500K+ — büyük, trade sinyali

# Paper trading ayarları
PAPER_CAPITAL      = 1_000.0    # Başlangıç bakiyesi ($)
PAPER_RISK_PCT     = 0.02       # İşlem başına risk %2
PAPER_RR           = 2.0        # R:R oranı 1:2
PAPER_SL_PCT       = 0.005      # Stop %0.5 (ATR yerine sabit)
PAPER_MAX_POSITIONS = 3         # Aynı anda max açık pozisyon

# Cooldown — aynı sembolde peş peşe sinyal engelleme
COOLDOWN_SEC = 300  # 5 dakika

# ─────────────────────────────────────────────────────────────
# VERİ YAPILARI
# ─────────────────────────────────────────────────────────────

@dataclass
class Liquidation:
    ts:     float
    symbol: str
    side:   str    # "BUY" veya "SELL" (likide olan taraf)
    qty:    float
    price:  float
    usd:    float

@dataclass
class PaperPosition:
    id:         int
    symbol:     str
    side:       str    # "LONG" veya "SHORT"
    entry:      float
    sl:         float
    tp:         float
    size_usd:   float
    open_time:  float
    status:     str = "OPEN"   # OPEN / WIN / LOSS / MANUAL
    close_price: float = 0.0
    pnl:        float = 0.0

class State:
    def __init__(self):
        self.liqs         = deque(maxlen=10000)
        self.large_liqs   = deque(maxlen=500)
        self.positions: list[PaperPosition] = []
        self.closed_positions: list[PaperPosition] = []
        self.capital      = PAPER_CAPITAL
        self.peak_capital = PAPER_CAPITAL
        self.trade_id     = 0
        self.last_signal: dict[str, float] = {}  # sembol → son sinyal zamanı
        self.symbols: set[str] = set()
        self.prices: dict[str, float] = {}
        self.total_wins   = 0
        self.total_losses = 0
        self.start_time   = time.time()

STATE = State()

# ─────────────────────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────────────────────

async def telegram_send(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print(f"[TELEGRAM] {msg}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT,
        "text": msg,
        "parse_mode": "HTML"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    print(f"Telegram hata: {r.status}")
    except Exception as e:
        print(f"Telegram bağlantı hatası: {e}")

def fmt_usd(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v/1_000:.1f}K"
    return f"${v:.2f}"

# ─────────────────────────────────────────────────────────────
# PAPER TRADING MOTORU
# ─────────────────────────────────────────────────────────────

async def open_paper_trade(symbol: str, signal_side: str, reason: str, liq_usd: float):
    """
    signal_side: "LONG" veya "SHORT"
    Büyük LONG likidasyon → biz SHORT açarız (karşı yön)
    Büyük SHORT likidasyon → biz LONG açarız
    """
    # Cooldown kontrolü
    now = time.time()
    last = STATE.last_signal.get(symbol, 0)
    if now - last < COOLDOWN_SEC:
        remaining = int(COOLDOWN_SEC - (now - last))
        print(f"[COOLDOWN] {symbol} — {remaining}s bekle")
        return

    # Max pozisyon kontrolü
    open_count = sum(1 for p in STATE.positions if p.status == "OPEN")
    if open_count >= PAPER_MAX_POSITIONS:
        print(f"[MAX POS] {PAPER_MAX_POSITIONS} açık pozisyon doldu")
        return

    # Fiyat al
    price = STATE.prices.get(symbol, 0)
    if price <= 0:
        print(f"[HATA] {symbol} fiyatı yok")
        return

    # Pozisyon boyutu hesapla
    risk_usd  = STATE.capital * PAPER_RISK_PCT
    sl_dist   = price * PAPER_SL_PCT
    tp_dist   = sl_dist * PAPER_RR
    size_usd  = risk_usd / PAPER_SL_PCT  # risk / sl yüzdesi

    if signal_side == "LONG":
        sl = price - sl_dist
        tp = price + tp_dist
    else:
        sl = price + sl_dist
        tp = price - tp_dist

    STATE.trade_id += 1
    pos = PaperPosition(
        id        = STATE.trade_id,
        symbol    = symbol,
        side      = signal_side,
        entry     = price,
        sl        = sl,
        tp        = tp,
        size_usd  = size_usd,
        open_time = now
    )
    STATE.positions.append(pos)
    STATE.last_signal[symbol] = now

    # Telegram bildirimi
    emoji = "🟢" if signal_side == "LONG" else "🔴"
    msg = (
        f"{emoji} <b>PAPER TRADE AÇILDI #{pos.id}</b>\n\n"
        f"📌 Sembol: <b>{symbol}</b>\n"
        f"📊 Yön: <b>{signal_side}</b>\n"
        f"💰 Giriş: <b>{price:.6f}</b>\n"
        f"🛑 Stop: <b>{sl:.6f}</b> ({PAPER_SL_PCT*100:.1f}%)\n"
        f"🎯 Hedef: <b>{tp:.6f}</b> (R:R 1:{PAPER_RR})\n"
        f"📦 Boyut: <b>{fmt_usd(size_usd)}</b>\n"
        f"⚡ Tetikleyici: {reason}\n"
        f"💥 Likidasyon: <b>{fmt_usd(liq_usd)}</b>\n"
        f"💼 Bakiye: {fmt_usd(STATE.capital)}"
    )
    await telegram_send(msg)
    print(f"\n{'='*50}")
    print(f"TRADE AÇILDI #{pos.id} | {symbol} {signal_side} @ {price:.6f}")
    print(f"SL: {sl:.6f} | TP: {tp:.6f} | Boyut: {fmt_usd(size_usd)}")
    print(f"{'='*50}\n")

async def check_paper_positions():
    """Açık pozisyonları fiyatla karşılaştır, SL/TP kontrolü yap"""
    for pos in STATE.positions:
        if pos.status != "OPEN":
            continue

        price = STATE.prices.get(pos.symbol, 0)
        if price <= 0:
            continue

        hit_sl = hit_tp = False

        if pos.side == "LONG":
            hit_sl = price <= pos.sl
            hit_tp = price >= pos.tp
        else:
            hit_sl = price >= pos.sl
            hit_tp = price <= pos.tp

        if hit_tp or hit_sl:
            result   = "WIN" if hit_tp else "LOSS"
            cl_price = pos.tp if hit_tp else pos.sl
            pnl_pct  = PAPER_RR * PAPER_RISK_PCT if hit_tp else -PAPER_RISK_PCT
            pnl_usd  = STATE.capital * pnl_pct

            pos.status      = result
            pos.close_price = cl_price
            pos.pnl         = pnl_usd

            STATE.capital += pnl_usd
            STATE.peak_capital = max(STATE.peak_capital, STATE.capital)

            if hit_tp:
                STATE.total_wins += 1
            else:
                STATE.total_losses += 1

            STATE.closed_positions.append(pos)

            # Telegram bildirimi
            emoji  = "✅" if result == "WIN" else "❌"
            total  = STATE.total_wins + STATE.total_losses
            wr     = (STATE.total_wins / total * 100) if total > 0 else 0
            dd     = ((STATE.peak_capital - STATE.capital) / STATE.peak_capital * 100)

            msg = (
                f"{emoji} <b>PAPER TRADE KAPANDI #{pos.id}</b>\n\n"
                f"📌 Sembol: <b>{pos.symbol}</b>\n"
                f"📊 Yön: <b>{pos.side}</b>\n"
                f"💰 Giriş: {pos.entry:.6f} → Çıkış: {cl_price:.6f}\n"
                f"{'🎯' if hit_tp else '🛑'} {'TP' if hit_tp else 'SL'} tetiklendi\n"
                f"💵 PnL: <b>{'+' if pnl_usd > 0 else ''}{fmt_usd(pnl_usd)}</b> ({pnl_pct*100:+.1f}%)\n\n"
                f"📈 <b>İSTATİSTİK</b>\n"
                f"Win Rate: <b>{wr:.1f}%</b> ({STATE.total_wins}W / {STATE.total_losses}L)\n"
                f"Bakiye: <b>{fmt_usd(STATE.capital)}</b>\n"
                f"Drawdown: {dd:.1f}%"
            )
            await telegram_send(msg)
            print(f"\n{emoji} KAPANDI #{pos.id} | {pos.symbol} {pos.side} | {result} | PnL: {fmt_usd(pnl_usd)}")

    # Kapananları listeden temizle
    STATE.positions = [p for p in STATE.positions if p.status == "OPEN"]

# ─────────────────────────────────────────────────────────────
# LİKİDASYON MANTIĞI
# ─────────────────────────────────────────────────────────────

async def process_liquidation(liq: Liquidation):
    """
    Likidasyon geldi — büyüklüğüne göre işlem yap
    side = likide olan taraf
    Biz → karşı yöne trade açarız
    """
    # Logla
    now_str = datetime.now().strftime("%H:%M:%S")
    print(f"[{now_str}] LİQ {liq.symbol} {liq.side} {fmt_usd(liq.usd)}")

    # Küçük likidasyon — sadece logla
    if liq.usd < LIQ_MEDIUM:
        return

    # Orta likidasyon — Telegram'a bildir
    if liq.usd < LIQ_LARGE:
        emoji = "⚡"
        msg = (
            f"{emoji} <b>Orta Likidasyon</b>\n"
            f"📌 {liq.symbol} | {liq.side} likide edildi\n"
            f"💥 {fmt_usd(liq.usd)} @ {liq.price:.6f}\n"
            f"⏰ {now_str}"
        )
        await telegram_send(msg)
        return

    # Büyük likidasyon — trade sinyali
    # Likide olan LONG → biz SHORT açarız
    # Likide olan SHORT → biz LONG açarız
    signal_side = "SHORT" if liq.side == "BUY" else "LONG"
    reason = f"{fmt_usd(liq.usd)} {liq.side} likidasyon"

    emoji = "💣"
    alert_msg = (
        f"{emoji} <b>BÜYÜK LİKİDASYON!</b>\n"
        f"📌 {liq.symbol}\n"
        f"💥 {fmt_usd(liq.usd)} {liq.side} pozisyon likide edildi\n"
        f"📊 Sinyal: <b>{signal_side}</b> aç\n"
        f"⏰ {now_str}"
    )
    await telegram_send(alert_msg)

    # Peş peşe likidasyon kontrolü (cascade)
    recent = [
        l for l in STATE.large_liqs
        if l.symbol == liq.symbol
        and time.time() - l.ts < 60
        and l.side == liq.side
    ]
    if len(recent) >= 2:
        # Aynı yönde birden fazla büyük likidasyon = cascade
        # Daha güçlü sinyal
        cascade_usd = sum(l.usd for l in recent) + liq.usd
        cascade_msg = (
            f"🚨 <b>CASCADE LİKİDASYON!</b>\n"
            f"📌 {liq.symbol} — {len(recent)+1} ardışık {liq.side} likidasyon\n"
            f"💥 Toplam: {fmt_usd(cascade_usd)}\n"
            f"📊 Güçlü sinyal: <b>{signal_side}</b>"
        )
        await telegram_send(cascade_msg)

    STATE.large_liqs.append(liq)
    await open_paper_trade(liq.symbol, signal_side, reason, liq.usd)

# ─────────────────────────────────────────────────────────────
# BİNANCE FUTURES SEMBOL LİSTESİ
# ─────────────────────────────────────────────────────────────

async def get_all_futures_symbols() -> list[str]:
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                symbols = [
                    s["symbol"] for s in data["symbols"]
                    if s["status"] == "TRADING" and s["quoteAsset"] == "USDT"
                ]
                print(f"[INFO] {len(symbols)} USDT futures sembol bulundu")
                return symbols
    except Exception as e:
        print(f"[HATA] Sembol listesi alınamadı: {e}")
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

async def get_prices_snapshot():
    """Tüm futures fiyatlarını çek"""
    url = "https://fapi.binance.com/fapi/v1/ticker/price"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json()
                for item in data:
                    STATE.prices[item["symbol"]] = float(item["price"])
    except Exception as e:
        print(f"[HATA] Fiyat snapshot: {e}")

# ─────────────────────────────────────────────────────────────
# WEBSOCKET — LİKİDASYON STREAM
# ─────────────────────────────────────────────────────────────

async def liquidation_stream():
    """
    Binance Futures all liquidations stream
    Tüm sembollerin likidasyonlarını tek stream'den alır
    """
    url = "wss://fstream.binance.com/ws/!forceOrder@arr"
    print(f"[INFO] Likidasyon stream'e bağlanıyor...")

    while True:
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                print("[INFO] ✅ Likidasyon stream bağlandı")
                await telegram_send(
                    "🚀 <b>Likidasyon Ajan başladı</b>\n"
                    f"📊 Tüm Binance Futures izleniyor\n"
                    f"⚡ Eşik: {fmt_usd(LIQ_LARGE)}+\n"
                    f"💼 Paper bakiye: {fmt_usd(STATE.capital)}\n"
                    f"📱 Bildirimler aktif"
                )

                async for raw in ws:
                    data = json.loads(raw)
                    order = data.get("o", {})

                    symbol = order.get("s", "")
                    side   = order.get("S", "")    # BUY veya SELL
                    price  = float(order.get("ap", order.get("p", 0)))
                    qty    = float(order.get("q", 0))
                    usd    = price * qty

                    if not symbol or not side or usd <= 0:
                        continue

                    # Fiyatı güncelle
                    if price > 0:
                        STATE.prices[symbol] = price

                    liq = Liquidation(
                        ts     = time.time(),
                        symbol = symbol,
                        side   = side,
                        qty    = qty,
                        price  = price,
                        usd    = usd
                    )
                    STATE.liqs.append(liq)
                    STATE.symbols.add(symbol)

                    await process_liquidation(liq)

        except Exception as e:
            print(f"[HATA] Stream koptu: {e} — Yeniden bağlanıyor...")
            await asyncio.sleep(3)

# ─────────────────────────────────────────────────────────────
# POZISYON KONTROL LOOP
# ─────────────────────────────────────────────────────────────

async def position_monitor():
    """Her 10 saniyede açık pozisyonları kontrol et"""
    while True:
        await asyncio.sleep(10)
        if STATE.positions:
            await check_paper_positions()

# ─────────────────────────────────────────────────────────────
# FİYAT GÜNCELLEME LOOP
# ─────────────────────────────────────────────────────────────

async def price_updater():
    """Her 30 saniyede fiyat snapshot al"""
    while True:
        await get_prices_snapshot()
        await asyncio.sleep(30)

# ─────────────────────────────────────────────────────────────
# DURUM RAPORU
# ─────────────────────────────────────────────────────────────

async def status_reporter():
    """Her saat başı Telegram'a durum raporu gönder"""
    await asyncio.sleep(60)  # İlk 1 dakika bekle
    while True:
        await asyncio.sleep(3600)  # Her saat

        total  = STATE.total_wins + STATE.total_losses
        wr     = (STATE.total_wins / total * 100) if total > 0 else 0
        dd     = ((STATE.peak_capital - STATE.capital) / STATE.peak_capital * 100)
        pnl    = STATE.capital - PAPER_CAPITAL
        elapsed = int(time.time() - STATE.start_time)
        hours   = elapsed // 3600

        open_pos = [p for p in STATE.positions if p.status == "OPEN"]
        open_txt = ""
        for p in open_pos:
            cur_price = STATE.prices.get(p.symbol, p.entry)
            if p.side == "LONG":
                unrealized = (cur_price - p.entry) / p.entry * p.size_usd
            else:
                unrealized = (p.entry - cur_price) / p.entry * p.size_usd
            open_txt += f"\n  • {p.symbol} {p.side} | Unrealized: {fmt_usd(unrealized)}"

        msg = (
            f"📊 <b>SAATLIK RAPOR</b> ({hours}. saat)\n\n"
            f"💼 Bakiye: <b>{fmt_usd(STATE.capital)}</b>\n"
            f"💵 PnL: <b>{'+' if pnl >= 0 else ''}{fmt_usd(pnl)}</b>\n"
            f"📈 Win Rate: <b>{wr:.1f}%</b>\n"
            f"✅ Kazanç: {STATE.total_wins} | ❌ Kayıp: {STATE.total_losses}\n"
            f"📉 Max Drawdown: {dd:.1f}%\n"
            f"🔍 İzlenen sembol: {len(STATE.symbols)}\n"
            f"📋 Açık pozisyon: {len(open_pos)}"
            f"{open_txt if open_txt else ''}"
        )
        await telegram_send(msg)

# ─────────────────────────────────────────────────────────────
# TERMINAL DISPLAY
# ─────────────────────────────────────────────────────────────

async def terminal_display():
    await asyncio.sleep(5)
    while True:
        try:
            print("\033[H\033[J", end="")
            now = datetime.now().strftime("%H:%M:%S")
            elapsed = int(time.time() - STATE.start_time)
            total = STATE.total_wins + STATE.total_losses
            wr = (STATE.total_wins / total * 100) if total > 0 else 0
            pnl = STATE.capital - PAPER_CAPITAL

            print("╔══════════════════════════════════════════════════════╗")
            print(f"║  LİKİDASYON AJAN  │  {now}  │  +{elapsed//60:02d}:{elapsed%60:02d}  ║")
            print("╠══════════════════════════════════════════════════════╣")
            print(f"║  Bakiye: ${STATE.capital:>10,.2f}   PnL: {'+' if pnl>=0 else ''}{pnl:>+8,.2f}$  ║")
            print(f"║  Win Rate: {wr:>5.1f}%   W:{STATE.total_wins} / L:{STATE.total_losses:<6}             ║")
            print(f"║  İzlenen sembol: {len(STATE.symbols):<5}  Eşik: {fmt_usd(LIQ_LARGE):<10}    ║")
            print("╠══════════════════════════════════════════════════════╣")

            open_pos = [p for p in STATE.positions if p.status == "OPEN"]
            if open_pos:
                print("║  AÇIK POZİSYONLAR:                                   ║")
                for p in open_pos:
                    cur = STATE.prices.get(p.symbol, p.entry)
                    if p.side == "LONG":
                        unr = (cur - p.entry) / p.entry * p.size_usd
                    else:
                        unr = (p.entry - cur) / p.entry * p.size_usd
                    sign = "▲" if p.side == "LONG" else "▼"
                    print(f"║  #{p.id} {sign} {p.symbol:<12} {p.side:<6} Unr:{unr:>+7.2f}$  ║")
            else:
                print("║  Açık pozisyon yok                                   ║")

            print("╠══════════════════════════════════════════════════════╣")
            print("║  Son Likidasyonlar:                                   ║")
            recent = list(STATE.liqs)[-5:]
            for l in reversed(recent):
                ago = int(time.time() - l.ts)
                print(f"║  {l.symbol:<12} {l.side:<5} {fmt_usd(l.usd):>8}  {ago:>4}s önce       ║")

            print("╚══════════════════════════════════════════════════════╝")
            print("  Ctrl+C ile durdur")

        except Exception as e:
            pass

        await asyncio.sleep(2)

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

async def main():
    print("Likidasyon Ajan başlatılıyor...")
    print(f"Paper bakiye: ${PAPER_CAPITAL:,.0f}")
    print(f"Likidasyon eşiği: {fmt_usd(LIQ_LARGE)}")
    print(f"Telegram: {'✅ Aktif' if TELEGRAM_TOKEN else '❌ .env dosyasını doldur'}")

    # İlk fiyat snapshot
    await get_prices_snapshot()

    await asyncio.gather(
        liquidation_stream(),
        position_monitor(),
        price_updater(),
        status_reporter(),
        terminal_display()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAjan durduruldu.")
        total = STATE.total_wins + STATE.total_losses
        wr = (STATE.total_wins / total * 100) if total > 0 else 0
        print(f"Son bakiye: ${STATE.capital:,.2f}")
        print(f"PnL: ${STATE.capital - PAPER_CAPITAL:+,.2f}")
        print(f"Win Rate: {wr:.1f}% ({STATE.total_wins}W/{STATE.total_losses}L)")
