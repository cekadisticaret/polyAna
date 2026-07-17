"""
5M 107 — 105 kopyası + yön yorgunluğu freni (BTC, Sanal)
========================================================
btc_5m_105_algo ile aynı sinyal; peş peşe 5 aynı yön açılış → 2 tur bekle.

$200 başlangıç, $8/$10/$12 (WR'ye göre), PM gamma kotasyonundan P&L. 24/7.
PM_5M_107_REAL_ENABLED=false (varsayılan, yalnızca sanal)
Telegram: 8256912678 bot (106 kanalı)
Cron: */5 * * * *
"""

import html
import json
import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from btc_5m_105_algo import analyze, fetch_klines_5m
import poly_trader_5m_common as _pm_common
from poly_trader_5m_common import tg_send, tg_send_photo
from pm_trader_helpers import pm_5m_sanal_quote, sanal_pnl, pm_5m_history_extras, pm_5m_find_market, pm_sanal_tg_quote

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

_TZ_TR = ZoneInfo("Europe/Istanbul")
_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(_DIR, "poly_trader_5m_btc_107_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_5m_btc_107_history.json")
WEEKLY_IMG = "/tmp/poly_5m_btc_107_weekly.png"

SYMBOLS = ["BTCUSDT"]
INITIAL_BALANCE = 200.0
TRADE_AMOUNT = 10.0
TRADE_AMOUNT_LOW = 8.0
TRADE_AMOUNT_HIGH = 12.0
_PERIOD_SECS = 300
_TOTAL_ALGOS = 4
_DAYS_TR = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

_PM_SANITY_MIN = 0.05
_PM_SANITY_MAX = 0.95
_PM_TRADE_MIN = 0.42
_PM_TRADE_MAX = 0.52
_PM_MIN_PAYOUT_RATIO = 1.25

# Peş peşe aynı yön açılış freni (105 analizinden)
_DIR_STREAK_CAP = 5
_DIR_COOLDOWN = 2

LABEL = "5M 107 BTC"


def _sym_name(symbol: str) -> str:
    return symbol.replace("USDT", "")


def _fmt_price(symbol: str, price: float) -> str:
    return f"{price:,.2f}" if symbol == "BTCUSDT" else f"{price:.2f}"


def _trading_allowed(_now_tr: datetime) -> bool:
    return True


def _trade_amount(history: list) -> float:
    amt, _ = _pm_common.trade_amount_by_wr(
        history,
        low=TRADE_AMOUNT_LOW,
        mid=TRADE_AMOUNT,
        high=TRADE_AMOUNT_HIGH,
    )
    return amt


def _ensure_brake_state(state: dict) -> None:
    state.setdefault("dir_streak", {"direction": None, "count": 0})
    state.setdefault("dir_cooldown", {"UP": 0, "DOWN": 0})


def _tick_cooldowns(state: dict) -> None:
    _ensure_brake_state(state)
    for d in ("UP", "DOWN"):
        if state["dir_cooldown"][d] > 0:
            state["dir_cooldown"][d] -= 1


def _direction_brake_skip(state: dict, direction: str) -> str | None:
    """Peş peşe aynı yön limiti — None = açılabilir."""
    _ensure_brake_state(state)
    cd = state["dir_cooldown"].get(direction, 0)
    if cd > 0:
        return f"Yön freni {direction}: {cd} tur bekle"
    streak = state["dir_streak"]
    if streak.get("direction") == direction and streak.get("count", 0) >= _DIR_STREAK_CAP:
        state["dir_cooldown"][direction] = _DIR_COOLDOWN
        state["dir_streak"] = {"direction": None, "count": 0}
        return f"Yön freni: peş peşe {_DIR_STREAK_CAP}x {direction} → {_DIR_COOLDOWN} tur bekle"
    return None


def _record_direction_open(state: dict, direction: str) -> None:
    _ensure_brake_state(state)
    streak = state["dir_streak"]
    if streak.get("direction") == direction:
        streak["count"] = streak.get("count", 0) + 1
    else:
        state["dir_streak"] = {"direction": direction, "count": 1}


def _pm_resolve_market(symbol: str, ts_5m: int, direction: str, amount: float) -> tuple[dict | None, str]:
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


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                st = json.load(f)
            _ensure_brake_state(st)
            return st
        except Exception:
            pass
    return {
        "balance": INITIAL_BALANCE,
        "open_positions": [],
        "total_pnl": 0.0,
        "dir_streak": {"direction": None, "count": 0},
        "dir_cooldown": {"UP": 0, "DOWN": 0},
    }


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


def get_all_stats(history: list) -> tuple[int, int]:
    return sum(1 for t in history if t.get("win")), len(history)


def _net_pnl(history: list) -> float:
    return round(sum(t.get("pnl", 0) or 0 for t in history), 2)


def _sync_balance(state: dict, history: list) -> None:
    net = _net_pnl(history)
    state["balance"] = round(INITIAL_BALANCE + net, 2)
    state["total_pnl"] = net


def _cumulative_line(history: list) -> str:
    wins, total = get_all_stats(history)
    net = _net_pnl(history)
    if total == 0:
        return "📊 Net P&L: henüz kapanmış işlem yok"
    icon = "🟢" if net >= 0 else "🔴"
    return f"📊 Net P&L (sanal): {icon} <b>{net:+.2f}$</b>  |  {total} işlem  |  {_wr(wins, total)}"


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


def _period_open_price(symbol: str, ts_5m: int, fallback: float) -> float:
    """5M periyot referans açılışı — Poly/Binance slot open (sig.entry_price değil)."""
    candle = _resolve_period_candle(symbol, ts_5m, retries=3, wait_sec=1.0)
    if candle:
        return float(candle["open"])
    try:
        kl = fetch_klines_5m(symbol, 5)
        if kl and kl[-1]["open_time"] == ts_5m * 1000:
            return float(kl[-1]["open"])
    except Exception:
        pass
    return fallback


def run() -> None:
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    dow = now_tr.weekday()
    period_min = (now_tr.hour * 60 + now_tr.minute) // 5 * 5
    ts_5m = _current_5m_ts()
    saat = f"{period_min // 60:02d}:{period_min % 60:02d}"
    next_period_min = period_min + 5
    next_saat = f"{next_period_min // 60:02d}:{next_period_min % 60:02d}"

    state = load_state()
    history = load_history()
    _sync_balance(state, history)
    _tick_cooldowns(state)

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

            ref_open = pos.get("entry_price") or candle["open"]
            prev_close = candle["close"]
            pred = pos["predicted_dir"]
            actual = "UP" if prev_close >= ref_open else "DOWN"
            win = pred == actual
            pnl = sanal_pnl(pos, win)
            spent = pos.get("pm_spent") or pos.get("amount", _trade_amount(history))
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
                "pm_dry_run": True,
                **pm_5m_history_extras(pos),
            })

            name = _sym_name(sym)
            icon = "✅" if win else "❌"
            dir_tr = "YÜKSELİR" if pred == "UP" else "DÜŞER"
            pct = (prev_close - ref_open) / ref_open * 100 if ref_open else 0
            closed_lines.append(
                f"{icon} {name} {dir_tr}  {_fmt_price(sym, ref_open)}→{_fmt_price(sym, prev_close)} ({pct:+.2f}%)"
                f"  {'+'+f'${pnl:.2f}' if win else '-$'+f'{spent:.2f}'}"
            )

        state["open_positions"] = []
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
            save_signal(f"107_{name.lower()}", ts_5m, sig.to_dict() if sig else None)
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

        brake = _direction_brake_skip(state, direction)
        if brake:
            skip_lines.append(f"⏸ {name} — {_tg_esc(brake)}")
            print(f"[{LABEL}] {saat} — {name} atlandı: {brake}")
            continue

        if state["balance"] < amount:
            skip_lines.append(f"⏸ {name} — bakiye yetersiz")
            continue

        pm_info, pm_skip = _pm_resolve_market(sym, ts_5m, direction, amount)
        if not pm_info:
            skip_lines.append(f"⏸ {name} {direction} — {pm_skip}")
            continue

        pm_q = pm_5m_sanal_quote(ts_5m, direction, amount, sym)
        token_price = pm_q.get("token_price") or pm_info.get("token_price")
        to_win = pm_q.get("to_win") or round(amount / max(token_price, 0.02), 2)
        quote = pm_sanal_tg_quote(amount, token_price, to_win)
        entry_p = _period_open_price(sym, ts_5m, sig.entry_price)

        _record_direction_open(state, direction)
        state["open_positions"].append({
            "symbol": sym,
            "predicted_dir": direction,
            "entry_price": entry_p,
            "consensus": sig.consensus,
            "votes": sig.votes,
            "labels": sig.labels,
            "momentum": sig.momentum,
            "entry_time_tr": now_tr.isoformat(),
            "entry_period_min": period_min,
            "entry_dow": dow,
            "entry_hour_tr": now_tr.hour,
            "ts_5m": ts_5m,
            "virtual": True,
            "pm_dry_run": True,
            **pm_q,
        })

        dir_tr = "YÜKSELİR" if direction == "UP" else "DÜŞER"
        dir_icon = "📈" if direction == "UP" else "📉"
        icons = " ".join("🟢" if v > 0 else "🔴" if v < 0 else "⚪" for v in sig.votes)
        streak_n = state["dir_streak"].get("count", 0)
        open_lines.append(
            f"{dir_icon} <b>{name} {dir_tr}</b>  ({sig.consensus}/{_TOTAL_ALGOS})  "
            f"{quote}\n"
            f"Giriş: {_fmt_price(sym, entry_p)}  |  mom:{sig.momentum}  |  seri:{streak_n}/{_DIR_STREAK_CAP}\n"
            f"{icons}"
        )
        print(f"[{LABEL}] {saat} — {name} {dir_tr} {quote} [SANAL] seri={streak_n}")

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
        parts.append(
            "🏁 <b>Sonuçlar</b> (biten tur)\n"
            + "\n".join(closed_lines)
            + f"\n{'🟢' if tur_pnl >= 0 else '🔴'} Bu tur: {tur_pnl:+.2f}$"
        )

    if open_lines:
        parts.append(
            f"🆕 <b>{saat} → {next_saat}</b>  🔶 SANAL\n"
            + "\n".join(open_lines)
        )

    msg = (
        f"{sep}\n"
        + "\n\n".join(parts)
        + f"\n{_cumulative_line(history)}\n"
        f"💰 Bakiye: ${state['balance']:.2f}\n"
        f"{sep}"
    )
    tg_send(msg)
    kind = "kapanış+açılış" if closed_lines and open_lines else "kapanış" if closed_lines else "açılış"
    print(f"[{LABEL}] {saat} — TG {kind} gönderildi")


def run_weekly() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np

    history = load_history()
    state = load_state()
    _sync_balance(state, history)
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)

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
    wins = sum(1 for t in history if t["win"])
    genel = f"%{wins/total*100:.0f}" if total else "—"
    balance = state.get("balance", INITIAL_BALANCE)
    total_pnl = state.get("total_pnl", _net_pnl(history))
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


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "weekly":
        run_weekly()
    else:
        run()
