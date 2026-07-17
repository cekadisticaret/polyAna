#!/usr/bin/env python3
"""
2. Analiz — 1 yıllık walk-forward backtest (SOL, saatlik)

Canlı mantığı taklit eder:
  - :05 open → poly_predictor_analysis.predict() (opsiyonel: ABD kapalıyken fallback)
  - :00 close → entry vs 1h kapanış (UP/DOWN)
  - Stake: açılışta düş, kazançta pm_size geri (sabit 0.50 token simülasyonu)
  - Tutar: $10 / $15 / $20 (sembol WR tier, geçmişe göre)

Not: CVD/orderbook/funding geçmişi olmadığı için predict'e nötr flow enjekte edilir.
"""
from __future__ import annotations

import argparse
import urllib.parse
import urllib.request
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiohttp

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import poly_predictor_analysis as pa
from poly_predictor_analysis import predict, _rsi, _macd, _ema

_TZ_TR = ZoneInfo("Europe/Istanbul")
_ET_ZONE = ZoneInfo("America/New_York")

INITIAL_BALANCE = 300.0
TRADE_AMOUNT = 15.0
TRADE_AMOUNT_HIGH = 20.0
TRADE_AMOUNT_LOW = 10.0
SYMBOL = "SOLUSDT"
TOKEN_SIM = 0.50  # PM gamma yok → sabit token fiyatı

BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID = "830754964"


@dataclass
class Trade:
    entry_time: str
    exit_time: str
    symbol: str
    predicted_dir: str
    actual_dir: str
    win: bool
    entry_price: float
    exit_price: float
    amount: float
    pnl: float
    signal_mode: str
    balance_after: float


def _us_market_open(ts: datetime) -> bool:
    et = ts.astimezone(_ET_ZONE)
    if et.weekday() >= 5:
        return False
    mins = et.hour * 60 + et.minute
    return 9 * 60 + 30 <= mins < 16 * 60


def _neutral_preloaded(klines: list[dict]) -> dict:
    return {
        "klines": klines,
        "cvd": (0.0, 0.0),
        "ob": 0.0,
        "large": 0.5,
        "taker": 0.5,
        "funding": 0.0,
        "ls": 1.0,
        "liq": (0.0, 0.0),
    }


def _fallback_from_klines(klines: list[dict]):
    if len(klines) < 10:
        return None
    closes = [k["close"] for k in klines]
    current = closes[-1]
    rsi = _rsi(closes)
    macd_val, macd_sig = _macd(closes)
    ema9, ema21 = _ema(closes, 9)[-1], _ema(closes, 21)[-1]
    votes = [
        1 if rsi < 50 else -1,
        1 if macd_val > macd_sig else -1,
        1 if ema9 > ema21 else -1,
    ]
    direction = "UP" if sum(votes) > 0 else "DOWN"
    trend = "YUKARI" if ema9 > ema21 else "AŞAĞI" if ema9 < ema21 else "YATAY"

    class _P:
        pass

    p = _P()
    p.predicted_dir = direction
    p.current_price = current
    p.rsi = rsi
    p.macd_bull = macd_val > macd_sig
    p.trend = trend
    return p


async def fetch_klines_history(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
) -> list[dict]:
    url = "https://fapi.binance.com/fapi/v1/klines"
    out: list[dict] = []
    cur = start_ms
    async with aiohttp.ClientSession() as session:
        while cur < end_ms:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": cur,
                "endTime": end_ms,
                "limit": 1000,
            }
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
                data = await r.json()
            if not isinstance(data, list) or not data:
                break
            for k in data:
                out.append({
                    "open_time": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "taker_buy": float(k[9]),
                })
            last_open = int(data[-1][0])
            nxt = last_open + 1
            if nxt <= cur:
                break
            cur = nxt
            if len(data) < 1000:
                break
            await asyncio.sleep(0.05)
    # dedupe
    seen = set()
    deduped = []
    for b in out:
        if b["open_time"] in seen:
            continue
        seen.add(b["open_time"])
        deduped.append(b)
    return deduped


def _dyn_amount(history: list[Trade]) -> float:
    if not history:
        return TRADE_AMOUNT
    wins = sum(1 for t in history if t.win)
    rate = wins / len(history)
    if rate > 0.5:
        return TRADE_AMOUNT_HIGH
    if rate < 0.5:
        return TRADE_AMOUNT_LOW
    return TRADE_AMOUNT


def _apply_synthetic_pm(pos: dict, amount: float) -> None:
    pos["pm_spent"] = amount
    pos["pm_size"] = round(amount / TOKEN_SIM, 2)
    pos["pm_entry_price"] = TOKEN_SIM
    pos["to_win"] = pos["pm_size"]


def _resolve_pnl(pos: dict, win: bool) -> float:
    spent = float(pos.get("pm_spent") or pos.get("amount") or 0)
    size = float(pos.get("pm_size") or 0)
    if size > 0 and spent > 0:
        return round(size - spent, 2) if win else round(-spent, 2)
    return round(-spent, 2) if not win else 0.0


async def run_backtest(
    days: int = 365,
    symbol: str = SYMBOL,
    unlimited: bool = False,
    standard_only: bool = False,
) -> dict:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days + 5)  # warmup
    print(f"Veri çekiliyor: {symbol} 1h ({days} gün + warmup)...")
    bars = await fetch_klines_history(
        symbol, "1h",
        int(start.timestamp() * 1000),
        int(end.timestamp() * 1000),
    )
    if len(bars) < 100:
        raise RuntimeError(f"Yetersiz veri: {len(bars)} bar")

    test_start_ms = int((end - timedelta(days=days)).timestamp() * 1000)
    warmup = 60

    balance = INITIAL_BALANCE
    total_pnl = 0.0
    history: list[Trade] = []
    open_pos = None
    skipped = 0
    skipped_balance = 0
    signals_std = signals_fb = 0

    for i in range(warmup, len(bars) - 1):
        bar = bars[i]
        if bar["open_time"] < test_start_ms and open_pos is None:
            # test penceresi öncesi sadece pozisyon taşıma yoksa atla
            if i + 1 < len(bars) and bars[i + 1]["open_time"] < test_start_ms:
                continue

        # ── CLOSE — bar i kapanışı ──
        if open_pos is not None and open_pos["settle_idx"] == i:
            entry = open_pos["entry_price"]
            exit_p = bar["close"]
            pred = open_pos["predicted_dir"]
            actual = "UP" if exit_p >= entry else "DOWN"
            win = pred == actual
            pnl = _resolve_pnl(open_pos, win)
            if win:
                balance = round(balance + open_pos["pm_size"], 2)
            total_pnl = round(total_pnl + pnl, 2)

            ts_open = datetime.fromtimestamp(open_pos["open_ms"] / 1000, tz=timezone.utc)
            ts_close = datetime.fromtimestamp(bar["open_time"] / 1000 + 3600, tz=timezone.utc)
            if ts_open.astimezone(_TZ_TR).timestamp() >= datetime.fromtimestamp(
                test_start_ms / 1000, tz=timezone.utc
            ).astimezone(_TZ_TR).timestamp():
                history.append(Trade(
                    entry_time=ts_open.astimezone(_TZ_TR).isoformat(),
                    exit_time=ts_close.astimezone(_TZ_TR).isoformat(),
                    symbol=symbol,
                    predicted_dir=pred,
                    actual_dir=actual,
                    win=win,
                    entry_price=entry,
                    exit_price=exit_p,
                    amount=open_pos["amount"],
                    pnl=pnl,
                    signal_mode=open_pos["signal_mode"],
                    balance_after=balance,
                ))
            open_pos = None

        # ── OPEN — bar i kapandıktan sonra (:05, bir sonraki saat bar i+1) ──
        if open_pos is not None:
            continue
        if i + 1 >= len(bars):
            continue
        if bars[i + 1]["open_time"] < test_start_ms:
            continue

        open_ms = bars[i + 1]["open_time"] + 5 * 60 * 1000
        ts_open = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc)
        us_open = _us_market_open(ts_open)

        kslice = bars[max(0, i - 59): i + 1]
        if len(kslice) < 30:
            continue

        pa._slot_utc_ms = open_ms
        pred = await predict(symbol, preloaded=_neutral_preloaded(kslice))
        sig_mode = "standard"
        if pred is None and not us_open and not standard_only:
            pred = _fallback_from_klines(kslice)
            sig_mode = "fallback" if pred else "none"
        elif pred is None:
            sig_mode = "none"

        if pred is None:
            skipped += 1
            continue

        if sig_mode == "standard":
            signals_std += 1
        elif sig_mode == "fallback":
            signals_fb += 1

        amount = _dyn_amount(history)
        pos = {
            "symbol": symbol,
            "predicted_dir": pred.predicted_dir,
            "entry_price": bars[i]["close"],
            "amount": amount,
            "signal_mode": sig_mode,
            "settle_idx": i + 1,
            "open_ms": open_ms,
        }
        _apply_synthetic_pm(pos, amount)
        stake = pos["pm_spent"]
        if not unlimited and balance < stake:
            skipped += 1
            skipped_balance += 1
            continue
        if not unlimited:
            balance = round(balance - stake, 2)
        else:
            balance = round(balance - stake, 2)  # takip amaçlı, negatif olabilir
        open_pos = pos

    pa._slot_utc_ms = None

    wins = sum(1 for t in history if t.win)
    total = len(history)
    wr = wins / total * 100 if total else 0.0
    monthly: dict[str, float] = {}
    for t in history:
        mk = t.entry_time[:7]
        monthly[mk] = round(monthly.get(mk, 0) + t.pnl, 2)

    peak = INITIAL_BALANCE
    max_dd = 0.0
    eq = INITIAL_BALANCE
    for t in history:
        eq = t.balance_after
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100 if peak else 0
        max_dd = max(max_dd, dd)

    return {
        "symbol": symbol,
        "days": days,
        "initial_balance": INITIAL_BALANCE,
        "final_balance": round(balance, 2),
        "total_pnl": round(total_pnl, 2),
        "trades": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate_pct": round(wr, 1),
        "max_drawdown_pct": round(max_dd, 1),
        "skipped_hours": skipped,
        "skipped_insufficient_balance": skipped_balance,
        "unlimited_balance": unlimited,
        "standard_only": standard_only,
        "signals_standard": signals_std,
        "signals_fallback": signals_fb,
        "monthly_pnl": monthly,
        "trade_list": [asdict(t) for t in history],
    }


def _print_summary(r: dict) -> None:
    print("\n" + "=" * 52)
    print(f"  2. ANALİZ BACKTEST — {r['symbol']} — son {r['days']} gün")
    print("=" * 52)
    print(f"  İşlem      : {r['trades']} ({r['wins']}W / {r['losses']}L)")
    print(f"  Win rate   : {r['win_rate_pct']}%")
    print(f"  P&L        : {'+' if r['total_pnl']>=0 else ''}${r['total_pnl']:.2f}")
    print(f"  Bakiye     : ${r['initial_balance']:.0f} → ${r['final_balance']:.2f}")
    print(f"  Max DD     : {r['max_drawdown_pct']}%")
    print(f"  Sinyal     : std={r['signals_standard']} fb={r['signals_fallback']} skip={r['skipped_hours']}")
    if r.get("skipped_insufficient_balance"):
        print(f"  Bakiye skip: {r['skipped_insufficient_balance']} saat (hesap eridi)")
    if r.get("standard_only"):
        print("  Mod        : sadece standard (fallback kapalı)")
    print("\n  Aylık P&L:")
    for m, p in sorted(r["monthly_pnl"].items()):
        bar = "+" if p >= 0 else ""
        print(f"    {m}: {bar}${p:.2f}")
    print("=" * 52)


def tg_send(text: str) -> None:
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=body)
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
        print("[TG] Gönderildi")
    except Exception as e:
        print(f"[TG] Hata: {e}")


def _fmt_result_block(r: dict, title: str) -> list[str]:
    lines = [
        f"<b>{title}</b>",
        f"  İşlem: {r['trades']} ({r['wins']}W/{r['losses']}L)  WR: {r['win_rate_pct']}%",
        f"  P&L: {'+' if r['total_pnl'] >= 0 else ''}${r['total_pnl']:.0f}  "
        f"Bakiye: ${r['initial_balance']:.0f}→${r['final_balance']:.0f}",
        f"  Sinyal: std={r['signals_standard']} fb={r['signals_fallback']} skip={r['skipped_hours']}",
    ]
    if r.get("skipped_insufficient_balance"):
        lines.append(f"  Bakiye skip: {r['skipped_insufficient_balance']} saat")
    return lines


def build_telegram_report(
    all_real: dict, all_unl: dict, std_real: dict, std_unl: dict,
) -> str:
    sep = "━" * 28
    parts = [
        sep,
        "📊 <b>2. ANALİZ — 1Y BACKTEST RAPORU</b>",
        f"SOLUSDT · son {all_real['days']} gün · simülasyon",
        "",
        "🔬 <b>Fallback kısıtlama ne demek?</b>",
        "• <b>Standard</b>: predict() sinyal verirse işlem",
        "• <b>Fallback</b>: predict boş + ABD kapalı → RSI/MACD/EMA",
        "• <b>Sadece standard</b>: fallback saatlerinde işlem <u>açılmaz</u>",
        "",
        "CVD/OB/funding geçmişi yok (nötr flow). PM token 0.50.",
        "",
        "📈 <b>Mevcut (fallback açık)</b>",
        *_fmt_result_block(all_real, "Gerçekçi $300"),
        *_fmt_result_block(all_unl, "Tam 1Y sınırsız")[1:],
        "",
        "✅ <b>Sadece standard</b>",
        *_fmt_result_block(std_real, "Gerçekçi $300"),
        *_fmt_result_block(std_unl, "Tam 1Y sınırsız")[1:],
        "",
        "📌 <b>Sinyal WR (tam 1Y)</b>",
    ]

    def _mode_wr(r: dict, mode: str) -> str:
        trades = [t for t in r.get("trade_list", []) if t["signal_mode"] == mode]
        if not trades:
            return "—"
        w = sum(1 for t in trades if t["win"])
        return f"{w}/{len(trades)} = %{w/len(trades)*100:.1f}"

    parts.append(f"  Standard: {_mode_wr(std_unl, 'standard')}")
    parts.append(f"  Fallback: {_mode_wr(all_unl, 'fallback')} (eski mod)")
    parts.append("")
    parts.append("🛠 Canlı: ALLOW_FALLBACK=False")
    parts.append("  ABD kapalı + predict boş → işlem yok")
    parts.append(sep)
    return "\n".join(parts)


async def run_report(days: int = 365) -> None:
    print("Rapor için backtestler çalışıyor...")
    all_real = await run_backtest(days=days, unlimited=False, standard_only=False)
    all_unl = await run_backtest(days=days, unlimited=True, standard_only=False)
    std_real = await run_backtest(days=days, unlimited=False, standard_only=True)
    std_unl = await run_backtest(days=days, unlimited=True, standard_only=True)
    msg = build_telegram_report(all_real, all_unl, std_real, std_unl)
    tg_send(msg)


async def main():
    p = argparse.ArgumentParser(description="2. Analiz 1Y backtest")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--symbol", default=SYMBOL)
    p.add_argument("--unlimited", action="store_true", help="Bakiye bitse de devam (tam dönem WR)")
    p.add_argument("--standard-only", action="store_true", help="Fallback kapalı — sadece predict()")
    p.add_argument("--telegram", action="store_true", help="4 senaryo karşılaştırmalı rapor → TG")
    p.add_argument("--out", default=os.path.join(_DIR, "backtest_analiz2_1y.json"))
    args = p.parse_args()

    if args.telegram:
        await run_report(days=args.days)
        return

    t0 = time.time()
    result = await run_backtest(
        days=args.days,
        symbol=args.symbol,
        unlimited=args.unlimited,
        standard_only=args.standard_only,
    )
    _print_summary(result)

    slim = {k: v for k, v in result.items() if k != "trade_list"}
    slim["last_20"] = result["trade_list"][-20:]
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nTam liste → {args.out} ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    asyncio.run(main())
