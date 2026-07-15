"""
5M 105 BTC — 102 + MR Veto + Trend Nötr (Sanal)
===============================================
btc_5m_105_algo: 4-algo konsensüs + momentum + iki düzeltme.

$200 sanal bakiye, $8/işlem. Gerçek PM: PM_5M_105_REAL_ENABLED=true
Telegram: 102 saatlik özet botu (8799859033) — 102 işlem bildirimlerinden ayrı.
Gece modu: 22:00–07:00 İST yeni işlem yok
Cron: */5 * * * *
"""

import html
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from btc_5m_105_algo import analyze, format_signal, fetch_klines_5m
import poly_trader_15m_btc as _pm101
from poly_tg_5m_102 import tg_send, tg_send_photo

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
STATE_FILE   = os.path.join(_DIR, "poly_trader_5m_btc_105_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_5m_btc_105_history.json")
WEEKLY_IMG   = "/tmp/poly_5m_btc_105_weekly.png"

SYMBOL            = "BTCUSDT"
INITIAL_BALANCE   = 200.0
TRADE_AMOUNT      = 8.0
TRADE_AMOUNT_UP   = 8.0
TRADE_AMOUNT_DOWN = 8.0
_PERIOD_SECS      = 300
_TOTAL_ALGOS      = 4
_DAYS_TR          = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

_PM_GAMMA_URL = "https://gamma-api.polymarket.com/events"
_PM_HEADERS   = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_PM_LIVE      = os.getenv("PM_5M_105_REAL_ENABLED", "false").lower() in ("1", "true", "yes")
_PM_DRY_RUN   = not _PM_LIVE

_PM_SANITY_MIN = 0.05
_PM_SANITY_MAX = 0.95
_PM_TRADE_MIN  = 0.42
_PM_TRADE_MAX  = 0.52
_PM_MIN_PAYOUT_RATIO = 1.25

_QUIET_START_HOUR = 22
_QUIET_END_HOUR   = 7

LABEL = "5M 105 BTC"


def _trading_allowed(now_tr: datetime) -> bool:
    h = now_tr.hour
    return _QUIET_END_HOUR <= h < _QUIET_START_HOUR


def _trade_amount(_direction: str) -> float:
    return TRADE_AMOUNT


def _pm_bal_line() -> str:
    return _pm101._pm_bal_line()


def _tg_balance(state: dict | None = None) -> str:
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
    _pm101._PM_DRY_RUN = True
    pm = _pm101._pm_find_5m_market(ts_5m)
    if not pm:
        return None, None
    tp = pm["up_price"] if direction == "UP" else pm["down_price"]
    return pm, tp


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


def get_stats(history: list, period_min: int, dow: int | None = None) -> tuple[int, int]:
    trades = [
        t for t in history
        if t.get("entry_period_min") == period_min
        and (dow is None or t.get("entry_dow") == dow)
    ]
    return sum(1 for t in trades if t["win"]), len(trades)


def get_all_stats(history: list) -> tuple[int, int]:
    return sum(1 for t in history if t["win"]), len(history)


def _current_5m_ts() -> int:
    now = int(time.time())
    return now - (now % _PERIOD_SECS)


def _resolve_period_candle(ts_5m: int, retries: int = 8, wait_sec: float = 2.0) -> dict | None:
    target_ms = ts_5m * 1000
    for _ in range(retries):
        for k in fetch_klines_5m(SYMBOL, 30):
            if k["open_time"] == target_ms:
                return k
        time.sleep(wait_sec)
    return None


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
        time.sleep(3)
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
            amount = pos.get("amount", pos.get("pm_spent", TRADE_AMOUNT))
            to_win = pos.get("to_win", amount * 2)
            actual = "UP" if prev_close >= ref_open else "DOWN"
            win    = pred == actual

            if win:
                if not _PM_LIVE:
                    state["balance"] = round(state["balance"] + to_win, 2)
                pnl = round(to_win - amount, 2)
            else:
                pnl = -amount

            tur_pnl += pnl
            state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

            history.append({
                "symbol": SYMBOL,
                "predicted_dir": pred,
                "actual_dir": actual,
                "win": win,
                "entry_price": ref_open,
                "exit_price": prev_close,
                "amount": amount,
                "to_win": to_win,
                "pnl": pnl,
                "entry_time_tr": pos["entry_time_tr"],
                "entry_period_min": pos.get("entry_period_min"),
                "entry_dow": pos.get("entry_dow"),
                "exit_time_tr": now_tr.isoformat(),
                "consensus": pos.get("consensus"),
                "votes": pos.get("votes"),
                "labels": pos.get("labels"),
                "momentum": pos.get("momentum"),
                "pm_slug": pos.get("pm_slug"),
                "pm_spent": pos.get("pm_spent", amount),
                "pm_size": pos.get("pm_size"),
                "pm_order_id": pos.get("pm_order_id"),
                "token_price": pos.get("token_price"),
                "pm_dry_run": _PM_DRY_RUN,
            })

            icon = "✅" if win else "❌"
            dir_tr = "YÜKSELİR" if pred == "UP" else "DÜŞER"
            pct = (prev_close - ref_open) / ref_open * 100 if ref_open else 0
            closed_lines.append(
                f"{icon} BTC {dir_tr}  {ref_open:,.0f}→{prev_close:,.0f} ({pct:+.1f}%)"
                f"  {'kazandı +$'+f'{to_win:.2f}' if win else 'kaybetti -$'+f'{amount:.0f}'}"
            )

        state["open_positions"] = []
        save_state(state)
        save_history(history)

    if closed_lines:
        win_all, tot_all = get_all_stats(history)
        tur_icon = "🟢" if tur_pnl >= 0 else "🔴"
        display_pnl = (
            round(state["balance"] - INITIAL_BALANCE, 2)
            if not _PM_LIVE
            else state["total_pnl"]
        )
        pnl_icon = "🟢" if display_pnl >= 0 else "🔴"
        sep = "━" * 26
        ok = tg_send(
            f"{sep}\n🏁 <b>{LABEL} — {saat} Sonuçlar</b>\n"
            + "\n".join(closed_lines) + "\n"
            f"{tur_icon} Bu tur: {tur_pnl:+.2f}$\n"
            f"{pnl_icon} Toplam P&amp;L: {display_pnl:+.2f}$  |  {_wr(win_all, tot_all)}\n"
            f"{_bal_line(state)}\n"
            f"{sep}"
        )
        if ok:
            print(f"[{LABEL}] {saat} — {len(closed_lines)} pozisyon kapatıldı, Sonuçlar gönderildi")
        else:
            print(f"[{LABEL}] {saat} — {len(closed_lines)} pozisyon kapatıldı, Sonuçlar TG HATA")

    if not _trading_allowed(now_tr):
        print(f"[{LABEL}] {saat} — gece modu (22:00–07:00 İST), yeni işlem yok")
        return

    balance = state["balance"]
    sig = analyze()

    try:
        from pm_signal_sync import save_signal
        save_signal("105", ts_5m, sig.to_dict() if sig else None)
    except Exception as e:
        print(f"[{LABEL}] save_signal: {e}")

    next_saat = (now_tr + timedelta(minutes=5)).strftime("%H:%M")
    sep = "━" * 26

    if sig is None:
        tg_send(f"⚠️ <b>{LABEL}</b> — {saat} veri alınamadı")
        return

    if sig.direction is None:
        reason = sig.skip_reason or f"Konsensüs yok ({sig.consensus}/{_TOTAL_ALGOS})"
        icons = " ".join("🟢" if v > 0 else "🔴" if v < 0 else "⚪" for v in sig.votes)
        tg_send(
            f"{sep}\n⏸ <b>{LABEL} — {saat} İST</b>\n"
            f"{_tg_esc(reason)}\n"
            f"{icons}  mom:{sig.momentum}\n"
            f"💰 Bakiye: ${balance:.2f}\n{sep}"
        )
        print(f"[{LABEL}] {saat} — atlandı: {reason}")
        return

    direction = sig.direction
    amount    = TRADE_AMOUNT
    if not _PM_LIVE and balance < amount:
        tg_send(
            f"{sep}\n⏸ <b>{LABEL} — {saat} İST</b>\n"
            f"Bakiye yetersiz (${balance:.2f} &lt; ${amount:.0f})\n"
            f"{_tg_balance(state)}\n{sep}"
        )
        return

    entry_p = sig.entry_price
    prev_wins, prev_total = get_stats(history, period_min)
    all_wins, all_total   = get_all_stats(history)
    dir_tr   = "YÜKSELİR" if direction == "UP" else "DÜŞER"
    dir_icon = "📈" if direction == "UP" else "📉"
    icons = " ".join("🟢" if v > 0 else "🔴" if v < 0 else "⚪" for v in sig.votes)

    if not _PM_LIVE:
        pm_info, token_price = _sanal_find_5m_market(ts_5m, direction)
        pm_slug = pm_info["slug"] if pm_info else None
        to_win = round(amount / token_price, 2) if token_price and token_price > 0 else round(amount * 2, 2)
        price_str = f"@{token_price:.2f}" if token_price else ""

        state["balance"] = round(balance - amount, 2)
        state["open_positions"].append({
            "symbol": SYMBOL, "predicted_dir": direction,
            "entry_price": entry_p, "amount": amount, "pm_spent": amount, "to_win": to_win,
            "token_price": token_price, "consensus": sig.consensus, "votes": sig.votes,
            "labels": sig.labels, "momentum": sig.momentum,
            "entry_time_tr": now_tr.isoformat(), "entry_period_min": period_min,
            "entry_dow": dow, "pm_slug": pm_slug, "ts_5m": ts_5m, "virtual": True,
            "pm_dry_run": True,
        })
        save_state(state)
        tg_send(
            f"{sep}\n🆕 <b>{LABEL} — {saat} → {next_saat}</b>  🔶 SANAL\n"
            f"{dir_icon} <b>BTC {dir_tr}</b>  ({sig.consensus}/{_TOTAL_ALGOS})  💵 ${amount:.0f} {price_str} → 🏆 ${to_win:.2f}\n"
            f"Giriş: {entry_p:,.2f}  |  Momentum: {sig.momentum}\n"
            f"{icons}\n"
            f"🕐 Bu periyot: {_wr(prev_wins, prev_total)}  |  Genel: {_wr(all_wins, all_total)}\n"
            f"{_tg_balance(state)}  |  🔴 ${amount:.0f} riskte\n{sep}"
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
            f"Sinyal {direction} ({sig.consensus}/{_TOTAL_ALGOS}) ${amount:.0f} — {pm_skip}\n"
            f"{_pm_bal_line()}\n{sep}"
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
            f"Payout oranı düşük: ${amount:.2f} → ${to_win:.2f}\n"
            f"{dir_icon} BTC {dir_tr} ({sig.consensus}/{_TOTAL_ALGOS})\n"
            f"{_pm_bal_line()}\n{sep}"
        )
        return

    token_id = pm_info["up_token"] if direction == "UP" else pm_info["down_token"]
    deadline = _pm101._pm_open_deadline(ts_5m)
    _pm101._pm_period_warmup(ts_5m)
    order_result = _pm101._pm_place_order(
        token_id, amount, pm_info["tick_size"], pm_info["neg_risk"], deadline=deadline,
    )

    if order_result and order_result.get("_skip"):
        tg_send(
            f"{sep}\n"
            f"⚠️ <b>{LABEL} — {saat} EMİR BAŞARISIZ</b>\n"
            f"Sebep: {_tg_esc(order_result.get('_skip', 'unknown'))}\n"
            f"{dir_icon} BTC {dir_tr}  ${amount:.0f}  @{token_price:.2f}\n"
            f"{_pm_bal_line()}\n{sep}"
        )
        print(f"[{LABEL}] {saat} — emir başarısız: {order_result.get('_skip')}")
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
        "token_price": token_price, "consensus": sig.consensus, "votes": sig.votes,
        "labels": sig.labels, "momentum": sig.momentum,
        "entry_time_tr": now_tr.isoformat(), "entry_period_min": period_min,
        "entry_dow": dow, "pm_slug": pm_slug, "pm_token_dir": direction,
        "pm_token_id": token_id, "ts_5m": ts_5m, "pm_size": pm_size,
        "pm_order_id": order_result.get("order_id", ""),
    })
    save_state(state)

    pm_tag = "🔴 GERÇEK PM"
    tg_send(
        f"{sep}\n"
        f"🆕 <b>{LABEL} — {saat} → {next_saat}</b>  {pm_tag}\n"
        f"{dir_icon} <b>BTC {dir_tr}</b>  ({sig.consensus}/{_TOTAL_ALGOS})  💵 ${amount:.2f} @{token_price:.2f} → 🏆 ${to_win:.2f}\n"
        f"Giriş: {entry_p:,.2f}  |  Momentum: {sig.momentum}  |  Lot: ${TRADE_AMOUNT:.0f}\n"
        f"{icons}\n"
        f"🕐 Bu periyot: {_wr(prev_wins, prev_total)}  |  Genel: {_wr(all_wins, all_total)}\n"
        f"{_bal_line(state)}\n{sep}"
    )
    print(f"[{LABEL}] {saat} — {dir_tr} {sig.consensus}/{_TOTAL_ALGOS}  ${amount:.2f}→${to_win:.2f} [PM]")


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
        d = t.get("entry_dow")
        p = t.get("entry_period_min")
        if d is None or p is None:
            continue
        h = p // 60
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
    ax.tick_params(length=0)

    total = len(history)
    wins  = sum(1 for t in history if t["win"])
    genel = f"%{wins/total*100:.0f}" if total else "—"
    balance = state.get("balance", INITIAL_BALANCE)
    total_pnl = state.get("total_pnl", 0.0)
    ax.set_title(
        f"{LABEL} — Haftalık Isı Haritası  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
        f"Toplam: {total} işlem  |  {genel}  |  Bakiye: ${balance:.2f}  |  P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$",
        color="#4fc3f7", fontsize=9, fontweight="bold", pad=8,
    )
    fig.colorbar(im, ax=ax, fraction=0.01, pad=0.01)
    plt.tight_layout(pad=1.0)
    plt.savefig(WEEKLY_IMG, dpi=130, bbox_inches="tight", facecolor="#0a0e1a", pad_inches=0.1)
    plt.close()
    tg_send_photo(WEEKLY_IMG, f"📊 {LABEL} Haftalık  {now_tr.strftime('%d.%m.%Y')}  {total} işlem | {genel}")


def run_stats() -> None:
    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)
    total   = len(history)
    wins    = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    tg_send(
        f"📊 <b>{LABEL} İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {_wr(wins, total)}\n"
        f"{'🟢' if total_pnl >= 0 else '🔴'} P&amp;L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"Başlangıç: ${INITIAL_BALANCE:.2f}"
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        run()
