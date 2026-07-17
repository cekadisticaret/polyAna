"""
5M 105 — 102 + MR Veto + Trend Nötr (BTC, Sanal)
================================================
btc_5m_105_algo: 4-algo konsensüs + iki düzeltme.

$200 başlangıç, $8/$10/$12 (WR'ye göre) sanal simülasyon. PM_5M_105_REAL_ENABLED=false
Telegram: 8799859033 bot — tur bildirimi.
Cron: */5 * * * * (24/7)
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
import poly_trader_5m_common as _pm_common
from poly_tg_5m_102 import tg_send, tg_send_photo
from pm_trader_helpers import pm_5m_sanal_quote, sanal_pnl, pm_5m_close, pm_5m_history_extras, pm_5m_find_market, pm_sanal_tg_quote

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

SYMBOLS           = ["BTCUSDT"]
SYMBOL            = "BTCUSDT"
INITIAL_BALANCE   = 200.0
TRADE_AMOUNT      = 10.0   # WR = %50 veya veri yok
TRADE_AMOUNT_LOW  = 8.0    # WR < %50
TRADE_AMOUNT_HIGH = 12.0   # WR > %50
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

LABEL = "5M 105 BTC"


def _sym_name(symbol: str) -> str:
    return symbol.replace("USDT", "")


def _fmt_price(symbol: str, price: float) -> str:
    return f"{price:,.2f}" if symbol == "BTCUSDT" else f"{price:.2f}"


def _trading_allowed(_now_tr: datetime) -> bool:
    return True


def _trade_amount(history: list) -> float:
    amt, _ = _pm_common.trade_amount_by_wr(
        _effective_history(history),
        low=TRADE_AMOUNT_LOW,
        mid=TRADE_AMOUNT,
        high=TRADE_AMOUNT_HIGH,
    )
    return amt


def _pm_bal_line() -> str:
    return _pm_common._pm_bal_line()


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
    _pm_common._PM_DRY_RUN = True
    pm = _pm_common._pm_find_5m_market(ts_5m)
    if not pm:
        return None, None
    tp = pm["up_price"] if direction == "UP" else pm["down_price"]
    return pm, tp


def _pm_resolve_market(symbol: str, ts_5m: int, direction: str, amount: float) -> tuple[dict | None, str]:
    if _PM_LIVE and symbol != "BTCUSDT":
        return None, "gerçek PM yalnızca BTC"
    if not _PM_LIVE:
        pm = pm_5m_find_market(ts_5m, symbol)
        if not pm or pm.get("closed"):
            return None, "PM market yok"
        tp = pm["up_price"] if direction == "UP" else pm["down_price"]
        if not (_PM_SANITY_MIN <= tp <= _PM_SANITY_MAX):
            return None, f"token @{tp:.2f} sanity dışı"
        if not (_PM_TRADE_MIN <= tp <= _PM_TRADE_MAX):
            return None, f"token @{tp:.2f} band dışı ({_PM_TRADE_MIN}–{_PM_TRADE_MAX})"
        est = round(amount / tp, 2) if tp > 0 else 0
        if est < amount * _PM_MIN_PAYOUT_RATIO:
            return None, f"payout {est/amount:.2f}x < {_PM_MIN_PAYOUT_RATIO} (@{tp:.2f})"
        pm["token_price"] = tp
        return pm, ""

    expected = f"btc-updown-5m-{ts_5m}"
    _pm_common._PM_DRY_RUN = _PM_DRY_RUN
    for attempt in range(3):
        pm = _pm_common._pm_find_5m_market(ts_5m)
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
    rows = _effective_history(history)
    return sum(1 for t in rows if t.get("win")), len(rows)


def _effective_history(history: list) -> list:
    """Gerçek PM modunda yalnızca canlı işlemler (sanal dönem hariç)."""
    if _PM_LIVE:
        return [t for t in history if t.get("pm_dry_run") is False]
    return list(history)


def _net_pnl(history: list) -> float:
    return round(sum(t.get("pnl", 0) or 0 for t in _effective_history(history)), 2)


def _cumulative_stats(history: list) -> tuple[int, int, float, str]:
    rows = _effective_history(history)
    wins = sum(1 for t in rows if t.get("win"))
    total = len(rows)
    net = round(sum(t.get("pnl", 0) or 0 for t in rows), 2)
    since = ""
    if rows:
        d = rows[0].get("entry_time_tr", "")[:10]
        if len(d) == 10:
            y, m, day = d.split("-")
            since = f"{day}.{m}.{y}"
    return wins, total, net, since


def _cumulative_line(history: list) -> str:
    wins, total, net, since = _cumulative_stats(history)
    if total == 0:
        return "📊 Net P&L: henüz kapanmış işlem yok"
    icon = "🟢" if net >= 0 else "🔴"
    scope = "gerçek PM" if _PM_LIVE else "sanal"
    since_part = f" · {since}'den beri" if since else ""
    return (
        f"📊 Net P&L ({scope}{since_part}): {icon} <b>{net:+.2f}$</b>"
        f"  |  {total} işlem  |  {_wr(wins, total)}"
    )


def _sync_total_pnl(state: dict, history: list) -> None:
    state["total_pnl"] = _net_pnl(history)


def _sync_balance(state: dict, history: list) -> None:
    """Sanal bakiye = başlangıç + kapanmış işlemlerin net PM P&L'i."""
    net = _net_pnl(history)
    state["balance"] = round(INITIAL_BALANCE + net, 2)
    state["total_pnl"] = net


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


def run() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    dow    = now_tr.weekday()
    period_min = (now_tr.hour * 60 + now_tr.minute) // 5 * 5
    ts_5m      = _current_5m_ts()
    saat = f"{period_min // 60:02d}:{period_min % 60:02d}"
    next_period_min = period_min + 5
    next_saat = f"{next_period_min // 60:02d}:{next_period_min % 60:02d}"

    state   = load_state()
    history = load_history()
    if not _PM_LIVE:
        _sync_balance(state, history)

    closed_lines = []
    tur_pnl = 0.0

    if state["open_positions"]:
        time.sleep(3)
        for pos in list(state["open_positions"]):
            sym = pos["symbol"]
            pos_ts = pos.get("ts_5m")
            candle = _resolve_period_candle(sym, pos_ts) if pos_ts else None
            if candle is None:
                try:
                    candle = fetch_klines_5m(sym, 10)[-2]
                except Exception as e:
                    print(f"[{LABEL}] Kapanış fiyatı alınamadı ({sym}): {e}")
                    continue

            ref_open   = candle["open"]
            prev_close = candle["close"]
            pred   = pos["predicted_dir"]
            actual = "UP" if prev_close >= ref_open else "DOWN"
            win    = pred == actual
            spent = pos.get("pm_spent") or pos.get("amount", _trade_amount(history))
            if _PM_LIVE:
                pnl, payout = pm_5m_close(pos, win)
                if win:
                    state["balance"] = round(state["balance"] + payout, 2)
            else:
                pnl = sanal_pnl(pos, win)

            tur_pnl += pnl

            history.append({
                "symbol": sym,
                "predicted_dir": pred,
                "actual_dir": actual,
                "win": win,
                "entry_price": ref_open,
                "exit_price": prev_close,
                "amount": pos.get("amount", spent),
                "pnl": pnl,
                "entry_time_tr": pos["entry_time_tr"],
                "entry_period_min": pos.get("entry_period_min"),
                "entry_dow": pos.get("entry_dow"),
                "entry_hour_tr": pos.get("entry_hour_tr"),
                "exit_time_tr": now_tr.isoformat(),
                "consensus": pos.get("consensus"),
                "votes": pos.get("votes"),
                "labels": pos.get("labels"),
                "momentum": pos.get("momentum"),
                "pm_dry_run": _PM_DRY_RUN,
                **pm_5m_history_extras(pos),
            })

            name = _sym_name(sym)
            icon = "✅" if win else "❌"
            dir_tr = "YÜKSELİR" if pred == "UP" else "DÜŞER"
            pct = (prev_close - ref_open) / ref_open * 100 if ref_open else 0
            closed_lines.append(
                f"{icon} {name} {dir_tr}  {_fmt_price(sym, ref_open)}→{_fmt_price(sym, prev_close)} ({pct:+.1f}%)"
                f"  {'+'+f'${pnl:.2f}' if win else '-$'+f'{spent:.2f}'}"
            )

        state["open_positions"] = []
        if _PM_LIVE:
            _sync_total_pnl(state, history)
        else:
            _sync_balance(state, history)
        save_state(state)
        save_history(history)

    open_lines = []
    skip_lines = []

    for sym in SYMBOLS:
        name = _sym_name(sym)
        sig = analyze(symbol=sym)

        try:
            from pm_signal_sync import save_signal
            save_signal(f"105_{name.lower()}", ts_5m, sig.to_dict() if sig else None)
        except Exception as e:
            print(f"[{LABEL}] save_signal: {e}")

        if sig is None:
            skip_lines.append(f"⚠️ {name} — veri yok")
            continue

        if sig.direction is None:
            reason = sig.skip_reason or f"Konsensüs yok ({sig.consensus}/{_TOTAL_ALGOS})"
            skip_lines.append(f"⏸ {name} — {_tg_esc(reason)}")
            print(f"[{LABEL}] {saat} — {name} atlandı: {reason}")
            continue

        direction = sig.direction
        amount = _trade_amount(history)
        if not _PM_LIVE:
            _sync_balance(state, history)
        balance = state["balance"]

        if not _PM_LIVE and balance < amount:
            skip_lines.append(f"⏸ {name} — bakiye yetersiz")
            continue

        entry_p = sig.entry_price
        dir_tr = "YÜKSELİR" if direction == "UP" else "DÜŞER"
        dir_icon = "📈" if direction == "UP" else "📉"
        icons = " ".join("🟢" if v > 0 else "🔴" if v < 0 else "⚪" for v in sig.votes)

        if not _PM_LIVE:
            pm_info, pm_skip = _pm_resolve_market(sym, ts_5m, direction, amount)
            if not pm_info:
                skip_lines.append(f"⏸ {name} {direction} — {pm_skip}")
                continue
            pm_q = pm_5m_sanal_quote(ts_5m, direction, amount, sym)
            token_price = pm_q.get("token_price") or pm_info.get("token_price")
            to_win = pm_q.get("to_win") or round(amount / max(token_price, 0.02), 2)
            quote = pm_sanal_tg_quote(amount, token_price, to_win)

            state["open_positions"].append({
                "symbol": sym, "predicted_dir": direction,
                "entry_price": entry_p, "consensus": sig.consensus, "votes": sig.votes,
                "labels": sig.labels, "momentum": sig.momentum,
                "entry_time_tr": now_tr.isoformat(), "entry_period_min": period_min,
                "entry_dow": dow, "entry_hour_tr": now_tr.hour,
                "ts_5m": ts_5m, "virtual": True,
                "pm_dry_run": True,
                **pm_q,
            })
            open_lines.append(
                f"{dir_icon} <b>{name} {dir_tr}</b>  ({sig.consensus}/{_TOTAL_ALGOS})  "
                f"{quote}\n"
                f"Giriş: {_fmt_price(sym, entry_p)}  |  Momentum: {sig.momentum}\n"
                f"{icons}"
            )
            print(f"[{LABEL}] {saat} — {name} {dir_tr} {quote} [SANAL]")
            continue

        if sym != "BTCUSDT":
            skip_lines.append(f"⏸ {name} — gerçek PM yalnızca BTC")
            continue

        from pm_balance_guard import can_open_trade
        if not can_open_trade(LABEL, tg_send):
            save_state(state)
            if closed_lines:
                _send_tg_round(saat, next_saat, state, history, closed_lines, [], [], tur_pnl)
            return

        _pm_common._PM_DRY_RUN = _PM_DRY_RUN
        pm_info, pm_skip = _pm_resolve_market(sym, ts_5m, direction, amount)
        if not pm_info:
            skip_lines.append(f"⏸ {name} {direction} — {pm_skip}")
            continue

        token_price = pm_info["token_price"]
        pm_slug = pm_info["slug"]
        to_win = round(amount / token_price, 2) if token_price > 0 else round(amount * 2, 2)

        if not _pm_common._pm_payout_ok(amount, to_win):
            skip_lines.append(f"⏸ {name} — payout düşük")
            continue

        token_id = pm_info["up_token"] if direction == "UP" else pm_info["down_token"]
        deadline = _pm_common._pm_open_deadline(ts_5m)
        _pm_common._pm_period_warmup(ts_5m)
        order_result = _pm_common._pm_place_order(
            token_id, amount, pm_info["tick_size"], pm_info["neg_risk"], deadline=deadline,
        )

        if order_result and order_result.get("_skip"):
            skip_lines.append(f"⏸ {name} — emir başarısız")
            continue
        if not order_result:
            skip_lines.append(f"⏸ {name} — PM order başarısız")
            continue

        to_win = order_result["size"]
        amount = order_result["spent"]
        token_price = order_result.get("price", token_price)
        pm_size = order_result.get("size") or to_win

        state["open_positions"].append({
            "symbol": sym, "predicted_dir": direction,
            "entry_price": entry_p, "amount": amount, "pm_spent": amount, "to_win": to_win,
            "token_price": token_price, "consensus": sig.consensus, "votes": sig.votes,
            "labels": sig.labels, "momentum": sig.momentum,
            "entry_time_tr": now_tr.isoformat(), "entry_period_min": period_min,
            "entry_dow": dow, "entry_hour_tr": now_tr.hour,
            "pm_slug": pm_slug, "pm_token_dir": direction,
            "pm_token_id": token_id, "ts_5m": ts_5m, "pm_size": pm_size,
            "pm_entry_price": token_price,
            "pm_order_id": order_result.get("order_id", ""),
        })
        open_lines.append(
            f"{dir_icon} <b>{name} {dir_tr}</b>  ({sig.consensus}/{_TOTAL_ALGOS})  "
            f"💵 ${amount:.2f} @{token_price:.2f} → 🏆 ${to_win:.2f}  🔴 GERÇEK PM"
        )
        print(f"[{LABEL}] {saat} — {name} {dir_tr} {sig.consensus}/{_TOTAL_ALGOS}  ${amount:.2f}→${to_win:.2f} [PM]")

    if not _PM_LIVE:
        _sync_balance(state, history)
    save_state(state)
    _send_tg_round(saat, next_saat, state, history, closed_lines, open_lines, skip_lines, tur_pnl)


def _send_tg_round(
    saat: str,
    next_saat: str,
    state: dict,
    history: list,
    closed_lines: list,
    open_lines: list,
    skip_lines: list,
    tur_pnl: float,
) -> None:
    if not closed_lines and not open_lines:
        return

    sep = "━" * 26
    parts: list[str] = [f"<b>{LABEL} — {saat}</b>"]

    if closed_lines:
        win_all, tot_all = get_all_stats(history)
        parts.append(
            "🏁 <b>Sonuçlar</b> (biten tur)\n"
            + "\n".join(closed_lines)
            + f"\n{'🟢' if tur_pnl >= 0 else '🔴'} Bu tur: {tur_pnl:+.2f}$"
            + f"  |  {_wr(win_all, tot_all)}"
        )

    if open_lines:
        parts.append(
            f"🆕 <b>{saat} → {next_saat}</b>  "
            f"{'🔶 SANAL' if not _PM_LIVE else '🔴 GERÇEK PM'}\n"
            + "\n".join(open_lines)
        )

    msg = (
        f"{sep}\n"
        + "\n\n".join(parts)
        + f"\n{_cumulative_line(history)}\n"
        + f"{_bal_line(state)}\n"
        f"{sep}"
    )
    ok = tg_send(msg)
    kind = "kapanış+açılış" if closed_lines and open_lines else "kapanış" if closed_lines else "açılış"
    print(f"[{LABEL}] {saat} — TG {kind} gönderildi" if ok else f"[{LABEL}] {saat} — TG {kind} HATA")


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
