"""
5M 102 BTC — 101 + Momentum + KALEM (Sanal)
============================================
101'in 4-algo konsensüsü (≥2/4) + düzeltmeler:
  1. Orderflow v2: CVD/OB çelişince canlı orderbook'a öncelik
  2. Momentum filtresi: son 3 kapanmış 5m mum sinyale ters ise işlem yok
  3. KALEM (deneysel): fitil yapısı + 3 peş peşe aynı yön dinlenme

Sanal: UP $4 / DOWN $6 (gerçek PM: PM_5M_102_REAL_ENABLED=true)
Gece modu: 22:00–07:00 İST yeni işlem yok
Cron: */5 * * * *
"""

import html
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import poly_trader_15m_btc as _pm101
from poly_trader_15m_btc import (
    SYMBOL,
    algo_a1_rsi_macd_ema,
    algo_mr,
    algo_trend,
    fetch_klines_5m,
    fetch_orderbook,
    tg_send,
    tg_send_photo,
)

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

_TZ_TR    = ZoneInfo("Europe/Istanbul")

_DIR         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(_DIR, "poly_trader_5m_btc_102_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_5m_btc_102_history.json")
WEEKLY_IMG   = "/tmp/poly_5m_btc_102_weekly.png"

INITIAL_BALANCE   = 200.0
TRADE_AMOUNT_UP   =   4.0
TRADE_AMOUNT_DOWN =   6.0
_PERIOD_SECS      = 300
_MIN_CONSENSUS    = 2
_MOMENTUM_BARS    = 3
_MOMENTUM_FILTER  = os.getenv("PM_5M_102_MOMENTUM_FILTER", "true").lower() in ("1", "true", "yes")
_DAYS_TR          = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

_PM_GAMMA_URL = "https://gamma-api.polymarket.com/events"
_PM_HEADERS   = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_PM_LIVE      = os.getenv("PM_5M_102_REAL_ENABLED", "false").lower() in ("1", "true", "yes")
_PM_DRY_RUN   = not _PM_LIVE

LABEL = "5M 102 BTC"

_PM_SANITY_MIN = 0.05
_PM_SANITY_MAX = 0.95
_PM_TRADE_MIN  = 0.42
_PM_TRADE_MAX  = 0.52
_PM_MIN_PAYOUT_RATIO = 1.25

# Gece modu (İST): 22:00–07:00 arası yeni işlem açılmaz; kapanış devam eder
_QUIET_START_HOUR = 22
_QUIET_END_HOUR   = 7


def _trading_allowed(now_tr: datetime) -> bool:
    h = now_tr.hour
    return _QUIET_END_HOUR <= h < _QUIET_START_HOUR


def _trade_amount(direction: str) -> float:
    return TRADE_AMOUNT_UP if direction == "UP" else TRADE_AMOUNT_DOWN


def _pm_bal_line() -> str:
    return _pm101._pm_bal_line()


def _tg_balance(state: dict | None = None) -> str:
    """Gerçek PM: Poly USDC bakiyesi; sanal modda state."""
    if _PM_LIVE:
        from pm_balance_guard import get_usdc_balance
        bal = get_usdc_balance()
        if bal >= 9999:
            return "💰 Bakiye: PM sorgulanamadı"
        return f"💰 Bakiye: ${bal:.2f}"
    st = state if state is not None else load_state()
    return f"💰 Bakiye: ${st['balance']:.2f}"


def _bal_line(state: dict) -> str:
    return _pm_bal_line() if _PM_LIVE else _tg_balance(state)


def _sanal_find_5m_market(ts_5m: int, direction: str) -> tuple[dict | None, float | None]:
    """Sanal mod: Gamma fiyatı (emir yok)."""
    _pm101._PM_DRY_RUN = True
    pm = _pm101._pm_find_5m_market(ts_5m)
    if not pm:
        return None, None
    tp = pm["up_price"] if direction == "UP" else pm["down_price"]
    return pm, tp


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
    if total == 0:
        return "veri yok"
    return f"%{wins/total*100:.0f} ({wins}/{total})"


def get_stats(history: list, period_min: int, dow: int | None = None) -> tuple[int, int]:
    trades = [
        t for t in history
        if t.get("entry_period_min") == period_min
        and (dow is None or t.get("entry_dow") == dow)
    ]
    return sum(1 for t in trades if t["win"]), len(trades)


def get_all_stats(history: list) -> tuple[int, int]:
    return sum(1 for t in history if t["win"]), len(history)


def _tg_esc(text: str) -> str:
    return html.escape(str(text), quote=False)


def _resolve_period_candle(ts_5m: int, retries: int = 8, wait_sec: float = 2.0) -> dict | None:
    target_ms = ts_5m * 1000
    for _ in range(retries):
        for k in fetch_klines_5m(SYMBOL, 30):
            if k["open_time"] == target_ms:
                return k
        time.sleep(wait_sec)
    return None


def _current_5m_ts() -> int:
    now = int(time.time())
    return now - (now % _PERIOD_SECS)


def algo_orderflow_v2(klines: list[dict], ob: dict) -> tuple[int, str]:
    """101 OF + CVD/OB çelişince canlı orderbook öncelikli."""
    window    = klines[-20:]
    cvd_delta = sum(k["volume"] if k["close"] >= k["open"] else -k["volume"] for k in window)
    total_vol = sum(k["volume"] for k in window) or 1
    cvd_r     = cvd_delta / total_vol

    bids  = sum(float(b[1]) for b in ob.get("bids", [])[:10])
    asks  = sum(float(a[1]) for a in ob.get("asks", [])[:10])
    ob_r  = (bids - asks) / (bids + asks) if (bids + asks) else 0

    cvd_v = +1 if cvd_r > 0.05 else -1 if cvd_r < -0.05 else 0
    ob_v  = +1 if ob_r  > 0.10 else -1 if ob_r  < -0.10 else 0

    if cvd_v == ob_v:
        vote = cvd_v
    elif ob_v != 0:
        vote = ob_v
    elif cvd_v != 0:
        vote = cvd_v
    else:
        vote = 0

    tag = "v2" if cvd_v != ob_v and ob_v != 0 else ""
    arr = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    return vote, f"OF{tag} {arr}  CVD:{cvd_r:+.2f}  OB:{ob_r:+.2f}"


def _recent_momentum(klines: list[dict], n: int = _MOMENTUM_BARS) -> str:
    """Son n kapanmış 5m mumun yönü (açık mum hariç)."""
    if len(klines) < n + 1:
        return "MIXED"
    closed = klines[-(n + 1):-1]
    ups = sum(1 for k in closed if k["close"] >= k["open"])
    if ups >= n - 1:
        return "UP"
    if ups <= 1:
        return "DOWN"
    return "MIXED"


def analyze() -> dict | None:
    try:
        klines = fetch_klines_5m(SYMBOL, 150)
        ob     = fetch_orderbook(SYMBOL)
    except Exception as e:
        print(f"[{LABEL}] Veri hatası: {e}", file=sys.stderr)
        return None

    v1, l1 = algo_a1_rsi_macd_ema(klines)
    v2, l2 = algo_trend(klines)
    v3, l3 = algo_mr(klines)
    v4, l4 = algo_orderflow_v2(klines, ob)

    votes  = [v1, v2, v3, v4]
    labels = [l1, l2, l3, l4]
    up_v   = sum(1 for v in votes if v > 0)
    down_v = sum(1 for v in votes if v < 0)
    entry_price = klines[-1]["open"]
    momentum = _recent_momentum(klines)

    base = {
        "votes": votes,
        "labels": labels,
        "entry_price": entry_price,
        "momentum": momentum,
    }

    if up_v >= _MIN_CONSENSUS and up_v > down_v:
        direction = "UP"
        consensus = up_v
    elif down_v >= _MIN_CONSENSUS and down_v > up_v:
        direction = "DOWN"
        consensus = down_v
    else:
        return {
            **base,
            "direction": None,
            "consensus": max(up_v, down_v),
            "amount": 0.0,
            "skip_reason": None,
        }

    skip_reason = None
    if _MOMENTUM_FILTER:
        if direction == "DOWN" and momentum == "UP":
            skip_reason = f"momentum filtresi: son {_MOMENTUM_BARS} 5m mum yükseliş, DOWN engellendi"
        elif direction == "UP" and momentum == "DOWN":
            skip_reason = f"momentum filtresi: son {_MOMENTUM_BARS} 5m mum düşüş, UP engellendi"

    if skip_reason:
        return {
            **base,
            "direction": None,
            "consensus": consensus,
            "amount": 0.0,
            "raw_direction": direction,
            "skip_reason": skip_reason,
        }

    # --- KALEM: fitil filtresi ---
    from kalem_filters_102 import kalem_wick_skip
    kalem_wick = kalem_wick_skip(direction, klines)
    if kalem_wick:
        return {
            **base,
            "direction": None,
            "consensus": consensus,
            "amount": 0.0,
            "raw_direction": direction,
            "skip_reason": kalem_wick,
        }
    # --- /KALEM ---

    return {
        **base,
        "direction": direction,
        "consensus": consensus,
        "amount": _trade_amount(direction),
        "skip_reason": None,
    }


def _pm_resolve_market(ts_5m: int, direction: str, amount: float) -> tuple[dict | None, str]:
    expected = f"btc-updown-5m-{ts_5m}"
    _pm101._PM_DRY_RUN = _PM_DRY_RUN
    for attempt in range(3):
        pm = _pm101._pm_find_5m_market(ts_5m)
        if not pm:
            if attempt < 2:
                time.sleep(3)
            continue
        if pm.get("slug") != expected or pm.get("closed"):
            if attempt < 2:
                time.sleep(2)
            continue
        tp = pm["up_price"] if direction == "UP" else pm["down_price"]
        if not (_PM_SANITY_MIN <= tp <= _PM_SANITY_MAX):
            if attempt < 2:
                time.sleep(3)
            continue
        if not (_PM_TRADE_MIN <= tp <= _PM_TRADE_MAX):
            return None, f"token @{tp:.2f} band dışı ({_PM_TRADE_MIN}–{_PM_TRADE_MAX})"
        est = round(amount / tp, 2) if tp > 0 else 0
        if est < amount * _PM_MIN_PAYOUT_RATIO:
            return None, f"payout {est/amount:.2f}x < {_PM_MIN_PAYOUT_RATIO} (@{tp:.2f})"
        pm["token_price"] = tp
        return pm, ""
    return None, "PM fiyat/market geçersiz"


def run() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    dow    = now_tr.weekday()
    saat   = now_tr.strftime("%H:%M")

    cur_min    = now_tr.hour * 60 + now_tr.minute
    period_min = (cur_min // 5) * 5
    ts_5m      = _current_5m_ts()

    state   = load_state()
    history = load_history()
    closed_lines = []
    tur_pnl = 0.0

    if state["open_positions"]:
        time.sleep(1)
        for pos in list(state["open_positions"]):
            pos_ts = pos.get("ts_5m")
            candle = _resolve_period_candle(pos_ts) if pos_ts else None
            if candle is None:
                try:
                    candle = fetch_klines_5m(SYMBOL, 10)[-2]
                except Exception as e:
                    print(f"[{LABEL}] Kapanış fiyatı alınamadı: {e}")
                    continue

            ref_open   = candle["open"]
            prev_close = candle["close"]
            pred   = pos["predicted_dir"]
            amount = pos.get("amount", pos.get("pm_spent", TRADE_AMOUNT_DOWN))
            to_win = pos.get("to_win", amount * 2)
            actual = "UP" if prev_close >= ref_open else "DOWN"
            win    = (pred == actual)

            if win:
                if not _PM_LIVE:
                    state["balance"] = round(state["balance"] + to_win, 2)
                pnl = round(to_win - amount, 2)
            else:
                pnl = -amount

            tur_pnl += pnl
            state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

            history.append({
                "symbol": SYMBOL, "predicted_dir": pred, "actual_dir": actual,
                "win": win, "entry_price": ref_open, "exit_price": prev_close,
                "amount": amount, "to_win": to_win, "pnl": pnl,
                "entry_time_tr": pos["entry_time_tr"],
                "entry_period_min": pos.get("entry_period_min"),
                "entry_dow": pos.get("entry_dow"),
                "exit_time_tr": now_tr.isoformat(),
                "consensus": pos.get("consensus"),
                "votes": pos.get("votes"),
                "pm_slug": pos.get("pm_slug"),
                "pm_spent": pos.get("pm_spent", amount),
                "pm_size": pos.get("pm_size"),
                "pm_order_id": pos.get("pm_order_id"),
                "token_price": pos.get("token_price"),
                "pm_dry_run": _PM_DRY_RUN,
            })

            icon = "✅" if win else "❌"
            pct  = (prev_close - ref_open) / ref_open * 100
            dir_tr = "YÜKSELİR" if pred == "UP" else "DÜŞER"
            closed_lines.append(
                f"{icon} BTC {dir_tr}  {ref_open:,.0f}→{prev_close:,.0f} ({pct:+.1f}%)"
                f"  {'kazandı +$'+f'{to_win:.2f}' if win else 'kaybetti -$'+f'{amount:.0f}'}"
            )

        state["open_positions"] = []
        save_state(state)
        save_history(history)

    if closed_lines:
        win_all, tot_all = get_all_stats(history)
        pnl_icon = "🟢" if state["total_pnl"] >= 0 else "🔴"
        tur_icon = "🟢" if tur_pnl >= 0 else "🔴"
        sep = "━" * 26
        tg_send(
            f"{sep}\n"
            f"🏁 <b>{LABEL} — {saat} Sonuçlar</b>\n"
            + "\n".join(closed_lines) + "\n"
            f"{tur_icon} Bu tur: {'+'if tur_pnl>=0 else ''}{tur_pnl:.0f}$\n"
            f"{pnl_icon} Toplam P&amp;L: {'+'if state['total_pnl']>=0 else ''}{state['total_pnl']:.2f}$  |  Genel: {_wr(win_all, tot_all)}\n"
            f"{_bal_line(state)}\n"
            f"{sep}"
        )
        print(f"[{LABEL}] {saat} — {len(closed_lines)} pozisyon kapatıldı")

    if not _trading_allowed(now_tr):
        print(f"[{LABEL}] {saat} — gece modu (22:00–07:00 İST), yeni işlem yok")
        return

    ts_5m = _current_5m_ts()
    result = analyze()
    from pm_signal_sync import save_signal
    save_signal("102", ts_5m, result)

    if result is None:
        tg_send(f"⚠️ <b>{LABEL}</b> — {saat} veri alınamadı")
        return

    direction = result["direction"]
    amount    = result["amount"]
    entry_p   = result["entry_price"]
    consensus = result.get("consensus", 0)
    votes     = result.get("votes", [])
    labels    = result.get("labels", [])
    momentum  = result.get("momentum", "?")
    skip      = result.get("skip_reason")
    next_saat = (now_tr + timedelta(minutes=5)).strftime("%H:%M")
    prev_wins, prev_total = get_stats(history, period_min)
    all_wins, all_total   = get_all_stats(history)
    sep = "━" * 26

    if direction is None:
        msg_extra = _tg_esc(skip) if skip else f"Konsensüs yok ({consensus}/4)"
        tg_send(
            f"{sep}\n"
            f"⏸ <b>{LABEL} — {saat} İST</b>\n"
            f"{msg_extra}\n"
            f"📊 Momentum: {momentum}  |  {_tg_esc('  |  '.join(labels))}\n"
            f"{_tg_balance(state)}\n"
            f"{sep}"
        )
        print(f"[{LABEL}] {saat} — işlem yok ({skip or f'konsensüs {consensus}/4'})")
        return

    # --- KALEM: peş peşe aynı yön dinlenme ---
    from kalem_filters_102 import kalem_streak_skip
    kalem_streak = kalem_streak_skip(direction, history)
    if kalem_streak:
        tg_send(
            f"{sep}\n"
            f"⏸ <b>{LABEL} — {saat} İST</b>\n"
            f"{_tg_esc(kalem_streak)}\n"
            f"📊 Momentum: {momentum}  |  ham sinyal: {direction} ({consensus}/4)\n"
            f"{_tg_balance(state)}\n"
            f"{sep}"
        )
        print(f"[{LABEL}] {saat} — {kalem_streak}")
        return
    # --- /KALEM ---

    dir_tr   = "YÜKSELİR" if direction == "UP" else "DÜŞER"
    dir_icon = "📈" if direction == "UP" else "📉"
    vote_str = "  ".join(f"{'🟢' if v > 0 else '🔴' if v < 0 else '⚪'}" for v in votes)

    if not _PM_LIVE:
        if state["balance"] < amount:
            tg_send(
                f"{sep}\n⏸ <b>{LABEL} — {saat} İST</b>\n"
                f"Bakiye yetersiz (${state['balance']:.2f} &lt; ${amount:.0f})\n"
                f"{_tg_balance(state)}\n{sep}"
            )
            return

        pm_info, token_price = _sanal_find_5m_market(ts_5m, direction)
        pm_slug = pm_info["slug"] if pm_info else None
        to_win = round(amount / token_price, 2) if token_price and token_price > 0 else round(amount * 2, 2)
        price_str = f"@{token_price:.2f}" if token_price else ""

        state["balance"] = round(state["balance"] - amount, 2)
        state["open_positions"].append({
            "symbol": SYMBOL, "predicted_dir": direction,
            "entry_price": entry_p, "amount": amount, "pm_spent": amount, "to_win": to_win,
            "token_price": token_price, "consensus": consensus, "votes": votes,
            "entry_time_tr": now_tr.isoformat(), "entry_period_min": period_min,
            "entry_dow": dow, "pm_slug": pm_slug, "ts_5m": ts_5m, "virtual": True,
            "pm_dry_run": True,
        })
        save_state(state)
        tg_send(
            f"{sep}\n"
            f"🆕 <b>{LABEL} — {saat} → {next_saat}</b>  🔶 SANAL\n"
            f"{dir_icon} <b>BTC {dir_tr}</b>  ({consensus}/4)  💵 ${amount:.0f} {price_str} → 🏆 ${to_win:.2f}\n"
            f"Giriş: {entry_p:,.2f}  |  Momentum: {momentum}\n"
            f"{vote_str}\n"
            f"🕐 Bu periyot: {_wr(prev_wins, prev_total)}  |  Genel: {_wr(all_wins, all_total)}\n"
            f"{_tg_balance(state)}  |  🔴 ${amount:.0f} riskte\n"
            f"{sep}"
        )
        print(f"[{LABEL}] {saat} — {dir_tr} ${amount:.0f}→${to_win:.2f} [SANAL]")
        return

    from pm_balance_guard import can_open_trade
    if not can_open_trade(LABEL, tg_send):
        return

    _pm101._PM_DRY_RUN = _PM_DRY_RUN
    pm_info, pm_skip = _pm_resolve_market(ts_5m, direction, amount)
    if not pm_info:
        tg_send(
            f"{sep}\n"
            f"⚠️ <b>{LABEL} — {saat} İST</b>\n"
            f"Sinyal {direction} ({consensus}/4) ${amount:.0f} — {pm_skip}\n"
            f"{_pm_bal_line()}\n"
            f"{sep}"
        )
        print(f"[{LABEL}] {saat} — market atlandı: {pm_skip}")
        return

    token_price = pm_info["token_price"]
    pm_slug     = pm_info["slug"]
    to_win      = round(amount / token_price, 2) if token_price > 0 else round(amount * 2, 2)

    if not _pm101._pm_payout_ok(amount, to_win):
        tg_send(
            f"{sep}\n"
            f"🚫 <b>{LABEL} — {saat} İŞLEM YOK</b>\n"
            f"Payout oranı yüksek: ${amount:.2f} → ${to_win:.2f}\n"
            f"{dir_icon} BTC {dir_tr} ({consensus}/4)\n"
            f"{_pm_bal_line()}\n"
            f"{sep}"
        )
        return

    token_id = pm_info["up_token"] if direction == "UP" else pm_info["down_token"]
    deadline = _pm101._pm_open_deadline(ts_5m)
    _pm101._pm_period_warmup(ts_5m)
    order_result = _pm101._pm_place_order(
        token_id, amount, pm_info["tick_size"], pm_info["neg_risk"], deadline=deadline,
    )

    if order_result and order_result.get("_skip"):
        skip_reason = order_result.get("_skip", "unknown")
        tg_send(
            f"{sep}\n"
            f"⚠️ <b>{LABEL} — {saat} EMİR BAŞARISIZ</b>\n"
            f"Sebep: {_tg_esc(skip_reason)}\n"
            f"{dir_icon} BTC {dir_tr}  ${amount:.0f}  @{token_price:.2f}\n"
            f"{_pm_bal_line()}\n"
            f"{sep}"
        )
        print(f"[{LABEL}] {saat} — emir başarısız: {skip_reason}")
        return

    if not order_result:
        tg_send(f"⚠️ <b>{LABEL}</b> — PM order başarısız, {direction} {saat}")
        print(f"[{LABEL}] PM order başarısız")
        return

    to_win      = order_result["size"]
    amount      = order_result["spent"]
    token_price = order_result.get("price", token_price)
    pm_size     = order_result.get("size") or to_win

    state["open_positions"].append({
        "symbol": SYMBOL, "predicted_dir": direction,
        "entry_price": entry_p, "amount": amount, "pm_spent": amount, "to_win": to_win,
        "token_price": token_price, "consensus": consensus, "votes": votes,
        "entry_time_tr": now_tr.isoformat(), "entry_period_min": period_min,
        "entry_dow": dow, "pm_slug": pm_slug, "pm_token_dir": direction,
        "pm_token_id": token_id, "ts_5m": ts_5m,
        "pm_size": pm_size,
        "pm_order_id": order_result.get("order_id", ""),
    })
    save_state(state)

    pm_tag = "🔴 GERÇEK PM" if _PM_LIVE else "🔶 SANAL"
    tg_send(
        f"{sep}\n"
        f"🆕 <b>{LABEL} — {saat} → {next_saat}</b>  {pm_tag}\n"
        f"{dir_icon} <b>BTC {dir_tr}</b>  ({consensus}/4)  💵 ${amount:.2f} @{token_price:.2f} → 🏆 ${to_win:.2f}\n"
        f"Giriş: {entry_p:,.2f}  |  Momentum: {momentum}  |  Lot: UP${TRADE_AMOUNT_UP:.0f}/DOWN${TRADE_AMOUNT_DOWN:.0f}\n"
        f"{vote_str}\n"
        f"🕐 Bu periyot: {_wr(prev_wins, prev_total)}  |  Genel: {_wr(all_wins, all_total)}\n"
        f"{_tg_balance(state)}\n"
        f"{sep}"
    )
    print(f"[{LABEL}] {saat} — {dir_tr} {consensus}/4 mom={momentum}  ${amount:.2f}→${to_win:.2f} [PM]")


def run_weekly() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np

    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)
    if not history:
        tg_send(f"📊 <b>{LABEL} WEEKLY</b>\nHenüz veri yok.")
        return

    grid_w_h = [[0] * 24 for _ in range(7)]
    grid_n_h = [[0] * 24 for _ in range(7)]
    for t in history:
        d, p = t.get("entry_dow"), t.get("entry_period_min")
        if d is None or p is None:
            continue
        h = (p // 5) // 12
        if 0 <= h < 24:
            grid_n_h[d][h] += 1
            if t["win"]:
                grid_w_h[d][h] += 1

    rate = np.full((7, 24), np.nan)
    for d in range(7):
        for h in range(24):
            if grid_n_h[d][h] >= 3:
                rate[d][h] = grid_w_h[d][h] / grid_n_h[d][h]

    fig, ax = plt.subplots(figsize=(16, 5))
    fig.patch.set_facecolor("#0a0e1a")
    ax.set_facecolor("#0a0e1a")
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "gy", [(0.0, "#f9a825"), (0.5, "#388e3c"), (1.0, "#00e676")], N=256
    )
    cmap.set_bad(color="#141820")
    im = ax.imshow(np.ma.masked_invalid(rate), cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(24)], fontsize=6, color="#78909c", rotation=45)
    ax.set_yticks(range(7))
    ax.set_yticklabels(_DAYS_TR, fontsize=8, color="#b0bec5", fontweight="bold")
    total = len(history)
    wins  = sum(1 for t in history if t["win"])
    genel = f"%{wins/total*100:.0f}" if total else "—"
    ax.set_title(
        f"{LABEL} — Haftalık  ({now_tr.strftime('%d.%m.%Y')})  {total} işlem | {genel}",
        color="#4fc3f7", fontsize=9, fontweight="bold",
    )
    fig.colorbar(im, ax=ax, fraction=0.01, pad=0.01)
    plt.tight_layout(pad=1.0)
    plt.savefig(WEEKLY_IMG, dpi=130, bbox_inches="tight", facecolor="#0a0e1a")
    plt.close()
    tg_send_photo(WEEKLY_IMG, f"📊 {LABEL} Haftalık")


def run_stats() -> None:
    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)
    total   = len(history)
    wins    = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    tg_send(
        f"📊 <b>{LABEL} İSTATİSTİK</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST\n"
        f"Toplam: {total}  |  {_wr(wins, total)}\n"
        f"P&amp;L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  {_tg_balance(state)}"
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        run()
