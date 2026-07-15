"""
5M 103 — Analiz 10 Çift Konsensüs (BTC + SOL, Sanal)
====================================================
Sistem A: poly_predictor  |  Sistem B: Trend+MR+OF+Funding (5m)
A yönünde B'den ≥2/4 algo oy (net skor değil). Momentum filtresi.

$200 sanal, $6/işlem. BTC + SOL.
Gece modu: 22:00–07:00 İST yeni işlem yok
Cron: */5 * * * *
"""

import asyncio
import html
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poly_predictor_analysis import predict
from poly_trader_15m_btc import fetch_klines_5m, fetch_orderbook
from poly_trader_analiz10 import (
    algo_trend, algo_mr, algo_orderflow, algo_funding, fetch_funding_rate,
)
from momentum_filter import momentum_skip_reason_5m, recent_momentum

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

BOT_TOKEN = "8256912678:AAFWEoRWO7Z0siK_c4Dm5XjgtBKmh-wmF8E"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")

_DIR         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(_DIR, "poly_trader_5m_btc_103_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_5m_btc_103_history.json")
WEEKLY_IMG   = "/tmp/poly_5m_btc_103_weekly.png"

SYMBOLS         = ["BTCUSDT", "SOLUSDT"]
INITIAL_BALANCE = 200.0
TRADE_AMOUNT    =  6.0
_PERIOD_SECS    = 300
_DAYS_TR        = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

_PM_GAMMA_URL = "https://gamma-api.polymarket.com/events"
_PM_HEADERS   = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_PM_DRY_RUN   = True
_PM_SANITY_MIN = 0.05
_PM_SANITY_MAX = 0.95
_PM_TRADE_MIN  = 0.42
_PM_TRADE_MAX  = 0.52
_PM_MIN_PAYOUT_RATIO = 1.25
MIN_B_VOTES = 2  # A yönünde B'den en az 2/4 algo

_PM_ASSET = {"BTCUSDT": "btc", "SOLUSDT": "sol"}
LABEL = "5M 103"

_QUIET_START_HOUR = 22
_QUIET_END_HOUR   = 7


def _trading_allowed(now_tr: datetime) -> bool:
    h = now_tr.hour
    return _QUIET_END_HOUR <= h < _QUIET_START_HOUR


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": INITIAL_BALANCE, "open_positions": [], "total_pnl": 0.0}


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


def _wr(wins: int, total: int) -> str:
    return f"%{wins/total*100:.0f} ({wins}/{total})" if total else "veri yok"


def _tg_esc(text: str) -> str:
    return html.escape(str(text), quote=False)


def _sym_name(symbol: str) -> str:
    return symbol.replace("USDT", "")


def get_stats(history: list, symbol: str, period_min: int) -> tuple[int, int]:
    trades = [
        t for t in history
        if t.get("symbol") == symbol and t.get("entry_period_min") == period_min
    ]
    return sum(1 for t in trades if t["win"]), len(trades)


def get_all_stats(history: list, symbol: str | None = None) -> tuple[int, int]:
    trades = [t for t in history if symbol is None or t.get("symbol") == symbol]
    return sum(1 for t in trades if t["win"]), len(trades)


def tg_send(text: str) -> None:
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception as e:
        print(f"[TG] Hata: {e}")


def _current_5m_ts() -> int:
    now = int(time.time())
    return now - (now % _PERIOD_SECS)


def _resolve_period_candle(symbol: str, ts_5m: int, retries: int = 8, wait_sec: float = 2.0) -> dict | None:
    target_ms = ts_5m * 1000
    for _ in range(retries):
        for k in fetch_klines_5m(symbol, 30):
            if k["open_time"] == target_ms:
                return k
        time.sleep(wait_sec)
    return None


def _b_supports(dir_a: str, votes_b: list[int]) -> tuple[bool, str]:
    """B tarafı A yönünde en az MIN_B_VOTES oy ve karşı yönden fazla."""
    up_b = sum(1 for v in votes_b if v > 0)
    down_b = sum(1 for v in votes_b if v < 0)
    if dir_a == "UP":
        ok = up_b >= MIN_B_VOTES and up_b > down_b
        return ok, f"UP {up_b}/4"
    if dir_a == "DOWN":
        ok = down_b >= MIN_B_VOTES and down_b > up_b
        return ok, f"DOWN {down_b}/4"
    return False, "—"


async def analyze_symbol(symbol: str) -> dict | None:
    try:
        pred_obj = await predict(symbol)
        klines   = fetch_klines_5m(symbol, 150)
        ob       = fetch_orderbook(symbol)
        funding  = fetch_funding_rate(symbol)
    except Exception as e:
        print(f"[{LABEL}] {symbol} veri hatası: {e}", file=sys.stderr)
        return None

    v_trend, l_trend = algo_trend(klines)
    v_mr,    l_mr    = algo_mr(klines)
    v_of,    l_of    = algo_orderflow(klines, ob)
    v_fund,  l_fund  = algo_funding(funding)
    votes_b = [v_trend, v_mr, v_of, v_fund]
    score_b = sum(votes_b)
    momentum = recent_momentum(klines)

    if pred_obj is None:
        up_b = sum(1 for v in votes_b if v > 0)
        down_b = sum(1 for v in votes_b if v < 0)
        b_hint = f"UP {up_b}/4" if up_b > down_b else f"DOWN {down_b}/4" if down_b > up_b else "—"
        return {
            "symbol": symbol, "direction": None, "amount": 0.0,
            "entry_price": klines[-1]["open"],
            "conf_a": 0.0, "score_b": score_b,
            "skip_reason": f"Sistem A sinyal yok (B:{b_hint} skor:{score_b:+d})",
            "labels": [f"A:—", l_trend, l_mr, l_of],
            "votes": [0, v_trend, v_mr, v_of],
            "momentum": momentum,
        }

    dir_a  = pred_obj.predicted_dir
    conf_a = max(pred_obj.prob_up, pred_obj.prob_down)

    if dir_a is None:
        return {
            "symbol": symbol, "direction": None, "amount": 0.0,
            "entry_price": klines[-1]["open"],
            "conf_a": conf_a, "score_b": score_b,
            "skip_reason": "Sistem A yön vermedi",
            "labels": [f"A:{conf_a*100:.0f}%", l_trend, l_mr, l_of],
            "votes": [0, v_trend, v_mr, v_of],
            "momentum": momentum,
        }

    b_ok, b_detail = _b_supports(dir_a, votes_b)
    if not b_ok:
        return {
            "symbol": symbol, "direction": None, "amount": 0.0,
            "entry_price": klines[-1]["open"],
            "conf_a": conf_a, "score_b": score_b,
            "skip_reason": f"konsensüs yok (A:{dir_a} B:{b_detail}, min {MIN_B_VOTES}/4)",
            "labels": [f"A:{conf_a*100:.0f}%", l_trend, l_mr, l_of],
            "votes": [+1 if dir_a == "UP" else -1, v_trend, v_mr, v_of],
            "momentum": momentum,
        }

    align_b = sum(1 for v in votes_b if (dir_a == "UP" and v > 0) or (dir_a == "DOWN" and v < 0))
    if conf_a >= 0.65 and align_b >= 3:
        tier = "💪 Her iki sistem güçlü"
    elif conf_a >= 0.65 or align_b >= 3:
        tier = "⚡ Bir güçlü bir orta"
    else:
        tier = "📊 İkisi orta"

    skip_reason = momentum_skip_reason_5m(dir_a, symbol)
    base = {
        "symbol": symbol, "entry_price": klines[-1]["open"],
        "conf_a": conf_a, "score_b": score_b, "tier": tier,
        "labels": [f"A:{conf_a*100:.0f}%", l_trend, l_mr, l_of],
        "votes": [+1 if dir_a == "UP" else -1, v_trend, v_mr, v_of],
        "momentum": momentum,
    }

    if skip_reason:
        return {**base, "direction": None, "amount": 0.0,
                "skip_reason": skip_reason, "raw_direction": dir_a}

    return {**base, "direction": dir_a, "amount": TRADE_AMOUNT, "skip_reason": None}


def _pm_find_5m_market(symbol: str, ts_5m: int) -> dict | None:
    asset = _PM_ASSET.get(symbol)
    if not asset:
        return None
    slug = f"{asset}-updown-5m-{ts_5m}"
    try:
        req = urllib.request.Request(f"{_PM_GAMMA_URL}?slug={slug}", headers=_PM_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        if not data:
            return None
        m      = data[0].get("markets", [{}])[0]
        raw_op = m.get("outcomePrices")
        op     = json.loads(raw_op) if isinstance(raw_op, str) else (raw_op or [])
        return {
            "slug": slug, "ts_5m": ts_5m,
            "up_price": float(op[0]) if len(op) >= 2 else 0.5,
            "down_price": float(op[1]) if len(op) >= 2 else 0.5,
        }
    except Exception as e:
        print(f"[{LABEL}] Gamma ({slug}): {e}", file=sys.stderr)
    return None


def _pm_resolve_market(symbol: str, ts_5m: int, direction: str) -> tuple[dict | None, str]:
    asset = _PM_ASSET.get(symbol, "btc")
    expected = f"{asset}-updown-5m-{ts_5m}"
    for attempt in range(3):
        pm = _pm_find_5m_market(symbol, ts_5m)
        if not pm:
            if attempt < 2:
                time.sleep(2)
            continue
        if pm.get("slug") != expected:
            continue
        tp = pm["up_price"] if direction == "UP" else pm["down_price"]
        if _PM_DRY_RUN:
            pm["token_price"] = tp if tp else 0.5
            return pm, ""
        if not (_PM_SANITY_MIN <= tp <= _PM_SANITY_MAX):
            if attempt < 2:
                time.sleep(2)
            continue
        if not (_PM_TRADE_MIN <= tp <= _PM_TRADE_MAX):
            return None, f"token @{tp:.2f} band dışı"
        est = round(TRADE_AMOUNT / tp, 2) if tp > 0 else 0
        if est < TRADE_AMOUNT * _PM_MIN_PAYOUT_RATIO:
            return None, f"payout {est/TRADE_AMOUNT:.2f}x düşük"
        pm["token_price"] = tp
        return pm, ""
    return None, "PM market/fiyat yok"


async def run_async() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    dow    = now_tr.weekday()
    saat   = now_tr.strftime("%H:%M")
    period_min = (now_tr.hour * 60 + now_tr.minute) // 5 * 5
    ts_5m  = _current_5m_ts()

    state   = load_state()
    history = load_history()
    closed_lines = []
    tur_pnl = 0.0

    if state["open_positions"]:
        time.sleep(1)
        for pos in list(state["open_positions"]):
            sym    = pos["symbol"]
            pos_ts = pos.get("ts_5m")
            candle = _resolve_period_candle(sym, pos_ts) if pos_ts else None
            if candle is None:
                try:
                    candle = fetch_klines_5m(sym, 10)[-2]
                except Exception:
                    continue

            ref_open   = candle["open"]
            prev_close = candle["close"]
            pred   = pos["predicted_dir"]
            amount = pos.get("amount", TRADE_AMOUNT)
            to_win = pos.get("to_win", amount * 2)
            actual = "UP" if prev_close >= ref_open else "DOWN"
            win    = pred == actual
            pnl    = round(to_win - amount, 2) if win else -amount

            if win:
                state["balance"] = round(state["balance"] + to_win, 2)
            tur_pnl += pnl
            state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

            history.append({
                "symbol": sym, "predicted_dir": pred, "actual_dir": actual,
                "win": win, "entry_price": ref_open, "exit_price": prev_close,
                "amount": amount, "to_win": to_win, "pnl": pnl,
                "entry_time_tr": pos["entry_time_tr"],
                "entry_period_min": pos.get("entry_period_min"),
                "entry_dow": pos.get("entry_dow"),
                "exit_time_tr": now_tr.isoformat(),
                "conf_a": pos.get("conf_a"), "score_b": pos.get("score_b"),
                "tier": pos.get("tier"), "votes": pos.get("votes"),
                "pm_slug": pos.get("pm_slug"), "token_price": pos.get("token_price"),
                "pm_dry_run": _PM_DRY_RUN,
            })

            name = _sym_name(sym)
            icon = "✅" if win else "❌"
            dir_tr = "YÜKSELİR" if pred == "UP" else "DÜŞER"
            pct = (prev_close - ref_open) / ref_open * 100 if ref_open else 0
            fmt = f"{ref_open:,.2f}" if sym == "BTCUSDT" else f"{ref_open:.2f}"
            fmt2 = f"{prev_close:,.2f}" if sym == "BTCUSDT" else f"{prev_close:.2f}"
            closed_lines.append(
                f"{icon} {name} {dir_tr}  {fmt}→{fmt2} ({pct:+.1f}%)"
                f"  {'+'+f'${to_win:.2f}' if win else '-$'+f'{amount:.0f}'}"
            )

        state["open_positions"] = []
        save_state(state)
        save_history(history)

    if closed_lines:
        win_all, tot_all = get_all_stats(history)
        sep = "━" * 26
        tg_send(
            f"{sep}\n🏁 <b>{LABEL} — {saat} Sonuçlar</b>\n"
            + "\n".join(closed_lines) + "\n"
            f"{'🟢' if tur_pnl >= 0 else '🔴'} Bu tur: {'+' if tur_pnl >= 0 else ''}{tur_pnl:.0f}$\n"
            f"{'🟢' if state['total_pnl'] >= 0 else '🔴'} Toplam P&amp;L: {'+' if state['total_pnl'] >= 0 else ''}{state['total_pnl']:.2f}$  |  {_wr(win_all, tot_all)}\n"
            f"{sep}"
        )

    if not _trading_allowed(now_tr):
        print(f"[{LABEL}] {saat} — gece modu (22:00–07:00 İST), yeni işlem yok")
        return

    ts_5m = _current_5m_ts()
    next_saat = (now_tr + timedelta(minutes=5)).strftime("%H:%M")
    sep = "━" * 26
    open_lines = []
    skip_lines = []

    for sym in SYMBOLS:
        result = await analyze_symbol(sym)
        if result is None:
            skip_lines.append(f"⚠️ {_sym_name(sym)} — veri yok")
            print(f"[{LABEL}] {saat} — {_sym_name(sym)} veri yok")
            continue

        name = _sym_name(sym)
        if result.get("direction") is None:
            reason = result.get("skip_reason") or "A10 konsensüs yok"
            skip_lines.append(f"⏸ {name} — {_tg_esc(reason)}")
            print(f"[{LABEL}] {saat} — {name} atlandı: {reason}")
            continue

        direction = result["direction"]
        amount    = result["amount"]
        entry_p   = result["entry_price"]

        if state["balance"] < amount:
            skip_lines.append(f"⏸ {name} — bakiye yetersiz")
            continue

        pm_info, pm_skip = _pm_resolve_market(sym, ts_5m, direction)
        if not pm_info:
            skip_lines.append(f"⏸ {name} {direction} — {pm_skip}")
            continue

        token_price = pm_info["token_price"]
        to_win = round(amount / token_price, 2)
        state["balance"] = round(state["balance"] - amount, 2)
        state["open_positions"].append({
            "symbol": sym, "predicted_dir": direction,
            "entry_price": entry_p, "amount": amount, "to_win": to_win,
            "token_price": token_price, "conf_a": result["conf_a"],
            "score_b": result["score_b"], "tier": result.get("tier"),
            "votes": result.get("votes"),
            "entry_time_tr": now_tr.isoformat(), "entry_period_min": period_min,
            "entry_dow": dow, "pm_slug": pm_info["slug"], "ts_5m": ts_5m,
        })

        dir_tr = "YÜKSELİR" if direction == "UP" else "DÜŞER"
        dir_icon = "📈" if direction == "UP" else "📉"
        fmt_p = f"{entry_p:,.2f}" if sym == "BTCUSDT" else f"{entry_p:.2f}"
        open_lines.append(
            f"{dir_icon} <b>{name} {dir_tr}</b>  ${amount:.2f} @{token_price:.2f} → 🏆 ${to_win:.2f}\n"
            f"   {result.get('tier', '')}  A:{result['conf_a']*100:.0f}% B:{result['score_b']:+d}  mom:{result.get('momentum')}\n"
            f"   Giriş: {fmt_p}"
        )
        print(f"[{LABEL}] {saat} — {name} {dir_tr} ${amount:.2f}→${to_win:.2f}")

    save_state(state)

    if open_lines:
        tg_send(
            f"{sep}\n🆕 <b>{LABEL} — {saat} → {next_saat}</b>  🔶 SANAL\n"
            + "\n".join(open_lines)
            + (("\n" + "\n".join(skip_lines)) if skip_lines else "")
            + f"\n💰 Bakiye: ${state['balance']:.2f}\n{sep}"
        )
    elif skip_lines:
        tg_send(
            f"{sep}\n⏸ <b>{LABEL} — {saat} İST</b>\n"
            + "\n".join(skip_lines) + f"\n💰 Bakiye: ${state['balance']:.2f}\n{sep}"
        )


def run() -> None:
    asyncio.run(run_async())


def run_stats() -> None:
    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)
    lines   = [f"📊 <b>{LABEL} İSTATİSTİK</b>", now_tr.strftime("%d.%m.%Y %H:%M") + " İST"]
    for sym in SYMBOLS:
        w, t = get_all_stats(history, sym)
        lines.append(f"{_sym_name(sym)}: {t} işlem  {_wr(w, t)}")
    lines.append(
        f"P&amp;L: {'+' if state.get('total_pnl',0)>=0 else ''}{state.get('total_pnl',0):.2f}$  |  Bakiye: ${state['balance']:.2f}"
    )
    tg_send("\n".join(lines))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "stats":
        run_stats()
    else:
        run()
