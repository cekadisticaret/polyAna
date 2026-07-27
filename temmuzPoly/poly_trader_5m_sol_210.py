"""
15M 210 SOL — 5M110Analiz FeatureEngine (gerçek PM, SOL only)
===========================================================
110'un birebir canlı kopyası: 110 aynı turda açtıysa mirror; açmadıysa 210 katiyen açmaz.

Gerçek PM: PM_5M_210_REAL_ENABLED (varsayılan true), işlem $4/$5/$6 (WR), başlangıç $300.
Cron: */15 * * * * — 110 snapshot poll (max 20 sn)
Hafta sonu: dashboard anahtarı (Cum 22:00 otomatik kapanır · Pzt 08:00 açılır; manuel override mümkün)
Gece duraklama: her gün 22:00 – 07:00 İST (open atlanır; close çalışır)
Modlar: open (varsayılan close+open) / hourly / weekly / stats
"""
from __future__ import annotations

import html
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analiz32_15m_signal_snapshot import wait_for_110_open_decision
from btc_5m_105_algo import fetch_klines_15m
import poly_trader_5m_common as _pm_common

# A1 Live ile aynı Telegram (PolyAktif bot)
from pm_trader_helpers import (
    PM_LIVE_TG_TOKEN as BOT_TOKEN,
    PM_LIVE_TG_CHAT as CHAT_ID,
    pm_15m_sanal_quote,
    pm_15m_find_market,
    sanal_pnl,
    sanal_debit_on_open,
    sanal_credit_on_close,
    pm_stake_fields,
    pm_5m_close,
    pm_5m_history_extras,
    pm_sanal_tg_quote,
    skip_if_weekend_pause,
)

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
STATE_FILE = os.path.join(_DIR, "poly_trader_5m_sol_210_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_5m_sol_210_history.json")
WEEKLY_IMG = "/tmp/poly_15m_sol_210_weekly.png"

SYMBOLS = ["SOLUSDT"]
SYMBOL = "SOLUSDT"
INITIAL_BALANCE = 300.0
TRADE_AMOUNT = 5.0
TRADE_AMOUNT_LOW = 4.0
TRADE_AMOUNT_HIGH = 6.0
_PERIOD_SECS = 900
_PERIOD_MIN = 15
_DAYS_TR = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

_PM_LIVE = os.getenv("PM_5M_210_REAL_ENABLED", "true").lower() in ("1", "true", "yes")
_PM_DRY_RUN = not _PM_LIVE

_PM_SANITY_MIN = 0.05
_PM_SANITY_MAX = 0.95
_PM_TRADE_MIN = 0.42
_PM_TRADE_MAX = 0.52
_PM_MIN_PAYOUT_RATIO = 1.25

LABEL = "15M 210 SOL"
SNAPSHOT_WAIT_SEC = 20  # 110 snapshot gelene kadar poll (race önleme)
SNAPSHOT_ORDER_BUFFER_SEC = 8  # snapshot sonrası PM emir için ayrılan süre
TG_HEADER = "210 SOL ✦ PolyAktif (110 canlı PM)"
STATS_SINCE_KEY = "stats_since_tr"
HOURLY_ROLLING_N = 10
_NIGHT_PAUSE_START = 22  # dahil
_NIGHT_PAUSE_END = 7     # hariç — 07:00 slotundan itibaren açılır


def _in_night_pause_tr(now_tr: datetime) -> bool:
    """Her gün 22:00–07:00 İST arası yeni işlem açılmaz."""
    h = now_tr.hour
    return h >= _NIGHT_PAUSE_START or h < _NIGHT_PAUSE_END


def tg_send(text: str) -> bool:
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(f"[{LABEL} TG] Hata: {e}")
        return False


def tg_send_photo(path: str, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(path, "rb") as f:
            img_data = f.read()
        boundary = "----210Boundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{CHAT_ID}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"heatmap.png\"\r\n"
            f"Content-Type: image/png\r\n\r\n"
        ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
    except Exception as e:
        print(f"[{LABEL} TG photo] Hata: {e}")


def _sym_name(symbol: str) -> str:
    return symbol.replace("USDT", "")


def _fmt_price(symbol: str, price: float) -> str:
    return f"{price:.2f}"


def _ensure_stats_epoch(state: dict) -> str:
    """İstatistik ve kayıt başlangıcı — ilk çalışmada şimdiki zaman."""
    if not state.get(STATS_SINCE_KEY):
        now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
        state[STATS_SINCE_KEY] = now_tr.isoformat()
        save_state(state)
    return state[STATS_SINCE_KEY]


def _history_tracked(history: list, state: dict) -> list:
    """stats_since'ten itibaren kapanmış gerçek PM işlemleri."""
    since = state.get(STATS_SINCE_KEY)
    rows = _effective_history(history)
    if not since:
        return rows
    return [t for t in rows if (t.get("exit_time_tr") or t.get("entry_time_tr") or "") >= since]


def _trade_amount(history: list, state: dict) -> float:
    amt, _ = _pm_common.trade_amount_by_wr(
        _history_tracked(history, state),
        low=TRADE_AMOUNT_LOW,
        mid=TRADE_AMOUNT,
        high=TRADE_AMOUNT_HIGH,
    )
    return amt


def _rolling_summary(trades: list, n: int = HOURLY_ROLLING_N) -> tuple[int, int, int, float]:
    tail = trades[-n:] if trades else []
    wins = sum(1 for t in tail if t.get("win"))
    losses = len(tail) - wins
    pnl = round(sum(t.get("pnl", 0) or 0 for t in tail), 2)
    return wins, losses, len(tail), pnl


def _tg_esc(text: str) -> str:
    return html.escape(str(text), quote=False)


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


def _effective_history(history: list) -> list:
    if _PM_LIVE:
        return [t for t in history if t.get("pm_dry_run") is False]
    return history


def _net_pnl(history: list) -> float:
    return round(sum(t.get("pnl", 0) or 0 for t in _effective_history(history)), 2)


def _sync_total_pnl(state: dict, history: list) -> None:
    state["total_pnl"] = _net_pnl(history)


def _sync_balance(state: dict, history: list) -> None:
    """Sanal bakiye = başlangıç + kapanmış işlemlerin net P&L'i (105 ile aynı)."""
    net = _net_pnl(history)
    state["balance"] = round(INITIAL_BALANCE + net, 2)
    state["total_pnl"] = net


def get_all_stats(history: list) -> tuple[int, int]:
    rows = _effective_history(history)
    return sum(1 for t in rows if t.get("win")), len(rows)


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


def _bal_line(state: dict) -> str:
    if _PM_LIVE:
        return _pm_common._pm_bal_line()
    at_risk = sum(
        (p.get("pm_spent") or p.get("amount", 0)) for p in state.get("open_positions", [])
    )
    bal = state["balance"]
    if at_risk > 0:
        return f"💰 Bakiye: ${bal:.2f}  |  📂 ${at_risk:.0f} riskte"
    return f"💰 Bakiye: ${bal:.2f}"


def _current_period_ts() -> int:
    now = int(time.time())
    return now - (now % _PERIOD_SECS)


def _resolve_period_candle(symbol: str, ts_period: int, retries: int = 8, wait_sec: float = 2.0) -> dict | None:
    target_ms = ts_period * 1000
    for _ in range(retries):
        for k in fetch_klines_15m(symbol, 30):
            if k["open_time"] == target_ms:
                return k
        time.sleep(wait_sec)
    return None


def _pm_resolve_market(symbol: str, ts_period: int, direction: str, amount: float,
                       *, mirror_110: bool = False) -> tuple[dict | None, str]:
    if not _PM_LIVE:
        pm = pm_15m_find_market(ts_period, symbol)
        if not pm or pm.get("closed"):
            return None, "PM market yok"
        tp = pm["up_price"] if direction == "UP" else pm["down_price"]
        if not (_PM_SANITY_MIN <= tp <= _PM_SANITY_MAX):
            return None, f"token @{tp:.2f} sanity dışı"
        if not mirror_110:
            if not (_PM_TRADE_MIN <= tp <= _PM_TRADE_MAX):
                return None, f"token @{tp:.2f} band dışı ({_PM_TRADE_MIN}–{_PM_TRADE_MAX})"
            est = round(amount / tp, 2) if tp > 0 else 0
            if est < amount * _PM_MIN_PAYOUT_RATIO:
                return None, f"payout {est/amount:.2f}x < {_PM_MIN_PAYOUT_RATIO} (@{tp:.2f})"
        pm["token_price"] = tp
        return pm, ""

    expected = f"sol-updown-15m-{ts_period}"
    _pm_common._PM_DRY_RUN = _PM_DRY_RUN
    for attempt in range(3):
        pm = _pm_common._pm_find_15m_market(ts_period, symbol)
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
        if not mirror_110:
            if not (_PM_TRADE_MIN <= tp <= _PM_TRADE_MAX):
                return None, f"token @{tp:.2f} band dışı ({_PM_TRADE_MIN}–{_PM_TRADE_MAX})"
            est = round(amount / tp, 2) if tp > 0 else 0
            if est < amount * _PM_MIN_PAYOUT_RATIO:
                return None, f"payout {est/amount:.2f}x < {_PM_MIN_PAYOUT_RATIO} (@{tp:.2f})"
        pm["token_price"] = tp
        return pm, ""
    return None, "PM fiyat/market geçersiz"


def _cumulative_line(history: list, state: dict) -> str:
    wins, total, net, since = _cumulative_stats(_history_tracked(history, state))
    if total == 0:
        return "📊 Net P&L: henüz kapanmış işlem yok"
    icon = "🟢" if net >= 0 else "🔴"
    scope = "gerçek PM" if _PM_LIVE else "sanal"
    since_part = f" · {since}'den beri" if since else ""
    return (
        f"📊 Net P&L ({scope}{since_part}): {icon} <b>{net:+.2f}$</b>"
        f"  |  {total} işlem  |  {_wr(wins, total)}"
    )


def _snapshot_wait_timeout(ts_period: int) -> float:
    """PM emir deadline'ına yetişecek snapshot bekleme süresi."""
    pm_deadline = ts_period + _pm_common._PM_OPEN_DEADLINE_SEC
    budget = pm_deadline - time.time() - SNAPSHOT_ORDER_BUFFER_SEC
    return max(0.0, min(SNAPSHOT_WAIT_SEC, budget))


def run() -> None:
    state = load_state()
    _ensure_stats_epoch(state)
    history = load_history()

    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    dow = now_tr.weekday()
    period_min = (now_tr.hour * 60 + now_tr.minute) // _PERIOD_MIN * _PERIOD_MIN
    ts_period = _current_period_ts()
    saat = f"{period_min // 60:02d}:{period_min % 60:02d}"
    next_period_min = period_min + _PERIOD_MIN
    next_saat = f"{(next_period_min % (24 * 60)) // 60:02d}:{next_period_min % 60:02d}"

    if skip_if_weekend_pause(LABEL, "run", now_tr):
        return

    closed_lines: list[str] = []
    tur_pnl = 0.0

    if state["open_positions"]:
        time.sleep(3)
        for pos in list(state["open_positions"]):
            sym = pos["symbol"]
            pos_ts = pos.get("ts_period") or pos.get("ts_5m")
            candle = _resolve_period_candle(sym, pos_ts) if pos_ts else None
            if candle is None:
                try:
                    candle = fetch_klines_15m(sym, 10)[-2]
                except Exception as e:
                    print(f"[{LABEL}] Kapanış fiyatı alınamadı ({sym}): {e}")
                    continue

            ref_open = candle["open"]
            prev_close = candle["close"]
            pred = pos["predicted_dir"]
            actual = "UP" if prev_close >= ref_open else "DOWN"
            win = pred == actual
            spent = pos.get("pm_spent") or pos.get("amount", _trade_amount(history, state))
            if _PM_LIVE:
                pnl, payout = pm_5m_close(pos, win)
                if win:
                    state["balance"] = round(state["balance"] + payout, 2)
            else:
                pnl = sanal_pnl(pos, win)
                sanal_credit_on_close(state, pos, win, pnl)

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
                "up_score": pos.get("up_score"),
                "down_score": pos.get("down_score"),
                "factors": pos.get("factors"),
                "htf_bias": pos.get("htf_bias"),
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
        save_state(state)
        save_history(history)

    open_lines: list[str] = []
    skip_lines: list[str] = []

    if _in_night_pause_tr(now_tr):
        print(f"[{LABEL}] {saat} İST — gece duraklama (22:00 – 07:00), yeni işlem yok")
        if closed_lines:
            _send_tg_round(saat, next_saat, state, history, closed_lines, open_lines, skip_lines, tur_pnl)
        return

    for sym in SYMBOLS:
        name = _sym_name(sym)
        snap_timeout = _snapshot_wait_timeout(ts_period)
        sig, opened_110, skip_110 = wait_for_110_open_decision(
            symbol=sym, ts_period=ts_period, timeout=snap_timeout,
        )

        if not opened_110:
            reason = skip_110 or "110 açmadı"
            skip_lines.append(f"⏸ {name} — 110 açmadı: {_tg_esc(reason)}")
            print(f"[{LABEL}] {saat} — {name} atlandı: 110 açmadı ({reason})")
            continue

        if sig is None:
            skip_lines.append(f"⚠️ {name} — veri yok")
            continue
        if sig.direction is None:
            reason = sig.skip_reason or "sinyal yok"
            skip_lines.append(f"⏸ {name} — {_tg_esc(reason)}")
            print(f"[{LABEL}] {saat} — {name} atlandı: {reason}")
            continue

        direction = sig.direction
        amount = _trade_amount(history, state)
        balance = state["balance"]

        if not _PM_LIVE and balance < amount:
            skip_lines.append(f"⏸ {name} — bakiye yetersiz")
            continue

        entry_p = sig.entry_price
        dir_tr = "YÜKSELİR" if direction == "UP" else "DÜŞER"
        dir_icon = "📈" if direction == "UP" else "📉"
        factor_hint = (sig.factors[0] if sig.factors else sig.htf_bias) or ""

        if not _PM_LIVE:
            pm_info, pm_skip = _pm_resolve_market(sym, ts_period, direction, amount)
            if not pm_info:
                skip_lines.append(f"⏸ {name} {direction} — {pm_skip}")
                continue
            pm_q = pm_15m_sanal_quote(ts_period, direction, amount, sym)
            token_price = pm_q.get("token_price") or pm_info.get("token_price")
            to_win = pm_q.get("to_win") or round(amount / max(float(token_price or 0.02), 0.02), 2)
            quote = pm_sanal_tg_quote(amount, token_price, to_win)

            pos = {
                "symbol": sym,
                "predicted_dir": direction,
                "entry_price": entry_p,
                "up_score": sig.up_score,
                "down_score": sig.down_score,
                "factors": sig.factors[:4],
                "htf_bias": sig.htf_bias,
                "confidence": sig.confidence,
                "entry_time_tr": now_tr.isoformat(),
                "entry_period_min": period_min,
                "entry_dow": dow,
                "entry_hour_tr": now_tr.hour,
                "ts_period": ts_period,
                "ts_5m": ts_period,
                "virtual": True,
                "pm_dry_run": True,
                **pm_q,
            }
            stake, _, _ = pm_stake_fields(pos)
            if balance < stake:
                skip_lines.append(f"⏸ {name} — bakiye yetersiz")
                continue
            sanal_debit_on_open(state, pos)
            state["open_positions"].append(pos)
            open_lines.append(
                f"{dir_icon} <b>{name} {dir_tr}</b>  "
                f"skor UP={sig.up_score} DOWN={sig.down_score}  "
                f"{quote}\n"
                f"Giriş: {_fmt_price(sym, entry_p)}  |  {_tg_esc(factor_hint)}"
            )
            print(f"[{LABEL}] {saat} — {name} {dir_tr} {quote} [SANAL A32]")
            continue

        # ── Canlı PM ──────────────────────────────────────────
        from pm_balance_guard import can_open_trade
        if not can_open_trade(LABEL, tg_send):
            skip_lines.append(f"⏸ {name} — gerçek PM kapalı (dashboard)")
            print(f"[{LABEL}] {saat} — {name} atlandı: dashboard PM kapalı")
            continue

        _pm_common._PM_DRY_RUN = _PM_DRY_RUN
        pm_info, pm_skip = _pm_resolve_market(sym, ts_period, direction, amount, mirror_110=True)
        if not pm_info:
            skip_lines.append(f"⏸ {name} {direction} — {pm_skip}")
            continue

        token_price = pm_info["token_price"]
        pm_slug = pm_info["slug"]
        to_win = round(amount / token_price, 2) if token_price > 0 else round(amount * 2, 2)

        token_id = pm_info["up_token"] if direction == "UP" else pm_info["down_token"]
        deadline = _pm_common._pm_open_deadline(ts_period)
        _pm_common._pm_period_warmup(ts_period)
        order_result = _pm_common._pm_place_order(
            token_id, amount, pm_info["tick_size"], pm_info["neg_risk"],
            deadline=deadline, skip_payout_check=True,
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
        factor_hint = (sig.factors[0] if sig.factors else sig.htf_bias) or ""

        state["open_positions"].append({
            "symbol": sym,
            "predicted_dir": direction,
            "entry_price": entry_p,
            "amount": amount,
            "pm_spent": amount,
            "to_win": to_win,
            "token_price": token_price,
            "up_score": sig.up_score,
            "down_score": sig.down_score,
            "factors": sig.factors[:4],
            "htf_bias": sig.htf_bias,
            "confidence": sig.confidence,
            "entry_time_tr": now_tr.isoformat(),
            "entry_period_min": period_min,
            "entry_dow": dow,
            "entry_hour_tr": now_tr.hour,
            "pm_slug": pm_slug,
            "pm_token_dir": direction,
            "pm_token_id": token_id,
            "ts_period": ts_period,
            "ts_5m": ts_period,
            "pm_size": to_win,
            "pm_entry_price": token_price,
            "pm_order_id": order_result.get("order_id", ""),
        })
        open_lines.append(
            f"{dir_icon} <b>{name} {dir_tr}</b>  "
            f"skor UP={sig.up_score} DOWN={sig.down_score}  "
            f"💵 ${amount:.2f} @{token_price:.2f} → 🏆 ${to_win:.2f}  🔴 GERÇEK PM\n"
            f"Giriş: {_fmt_price(sym, entry_p)}  |  {_tg_esc(factor_hint)}"
        )
        print(f"[{LABEL}] {saat} — {name} {dir_tr} ${amount:.2f}→${to_win:.2f} [GERÇEK PM A32]")

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
        if skip_lines:
            print(f"[{LABEL}] {saat} — atlandı (TG yok): {'; '.join(skip_lines)}")
        return

    sep = "━" * 26
    parts: list[str] = [f"<b>{TG_HEADER} — {saat} - {next_saat}</b>"]

    if closed_lines:
        win_all, tot_all = get_all_stats(_history_tracked(history, state))
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

    if skip_lines and (closed_lines or open_lines):
        parts.append("⏸ <b>Atlandı</b>\n" + "\n".join(skip_lines))

    msg = (
        f"{sep}\n"
        + "\n\n".join(parts)
        + f"\n{_cumulative_line(history, state)}\n"
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

    history = _effective_history(load_history())
    state = load_state()
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    if not history:
        tg_send(f"📊 <b>{TG_HEADER} WEEKLY</b>\nHenüz veri yok.")
        return

    grid_w_h = [[0] * 24 for _ in range(7)]
    grid_n_h = [[0] * 24 for _ in range(7)]
    for t in history:
        d, p = t.get("entry_dow"), t.get("entry_period_min")
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
    total = len(history)
    wins = sum(1 for t in history if t["win"])
    genel = f"%{wins/total*100:.0f}" if total else "—"
    mode = "GERÇEK PM $4-6" if _PM_LIVE else "SANAL"
    ax.set_title(
        f"{LABEL} — Haftalık  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
        f"Toplam: {total}  |  {genel}  |  {mode}",
        color="#4fc3f7", fontsize=9, fontweight="bold", pad=8,
    )
    fig.colorbar(im, ax=ax, fraction=0.01, pad=0.01)
    plt.tight_layout(pad=1.0)
    plt.savefig(WEEKLY_IMG, dpi=130, bbox_inches="tight", facecolor="#0a0e1a", pad_inches=0.1)
    plt.close()
    tg_send_photo(WEEKLY_IMG, f"📊 {TG_HEADER}  {now_tr.strftime('%d.%m.%Y')}  {total} işlem | {genel} | {mode}")


def _parse_tr_iso(iso: str) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TZ_TR)
        return dt.astimezone(_TZ_TR)
    except Exception:
        return None


def _in_hour_window(iso: str, hour_start: datetime, hour_end: datetime) -> bool:
    dt = _parse_tr_iso(iso)
    if dt is None:
        return False
    return hour_start <= dt < hour_end


def _trades_in_hour_window(history: list, state: dict, hour_start: datetime, hour_end: datetime) -> int:
    """Önceki 1 saat diliminde açılan veya kapanan 15m işlem sayısı."""
    seen = 0
    for t in _effective_history(history):
        if _in_hour_window(t.get("exit_time_tr") or "", hour_start, hour_end):
            seen += 1
        elif _in_hour_window(t.get("entry_time_tr") or "", hour_start, hour_end):
            seen += 1
    for pos in state.get("open_positions", []):
        if _in_hour_window(pos.get("entry_time_tr") or "", hour_start, hour_end):
            seen += 1
    return seen


def _fmt_stats_since(iso_tr: str) -> str:
    if not iso_tr:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_tr)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TZ_TR)
        return dt.astimezone(_TZ_TR).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return iso_tr[:16].replace("T", " ")


def run_hourly() -> None:
    if not _PM_LIVE:
        print(f"[{LABEL}] hourly atlandı — gerçek PM kapalı")
        return

    state = load_state()
    _ensure_stats_epoch(state)
    history = load_history()
    tracked = _history_tracked(history, state)
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    hour_end = now_tr.replace(minute=0, second=0, microsecond=0)
    hour_start = hour_end - timedelta(hours=1)
    prev_h = hour_start.hour
    hour_label = f"{prev_h:02d}:00 – {hour_end.hour:02d}:00"

    n_hour = _trades_in_hour_window(history, state, hour_start, hour_end)
    if n_hour == 0:
        print(
            f"[{LABEL}] hourly atlandı — {hour_label} İST aralığında 15m işlem yok",
        )
        return

    rw, rl, rn, rpnl = _rolling_summary(tracked)
    tw, tt, tpnl, since_d = _cumulative_stats(tracked)

    try:
        from pm_balance_guard import get_usdc_balance
        bal = get_usdc_balance()
        balance = bal if bal < 9999 else round(state.get("balance", INITIAL_BALANCE), 2)
    except Exception:
        balance = round(state.get("balance", INITIAL_BALANCE), 2)

    open_pos = state.get("open_positions", [])
    open_n = len(open_pos)
    risk = round(sum(p.get("pm_spent") or p.get("amount", 0) for p in open_pos), 2)

    sep = "━" * 26
    lines = [
        sep,
        f"📊 <b>{TG_HEADER} — Saatlik Özet</b>",
        f"🕐 {hour_label}  |  {now_tr.strftime('%d.%m.%Y')} İST",
        "",
    ]

    since_fmt = _fmt_stats_since(state.get(STATS_SINCE_KEY, ""))
    if rn == 0:
        lines.append(f"📂 Son {HOURLY_ROLLING_N} işlem: henüz kapanmış işlem yok")
        lines.append(f"📅 Kayıt başlangıcı: {since_fmt} İST")
    else:
        n_label = min(rn, HOURLY_ROLLING_N)
        ricon = "🟢" if rpnl >= 0 else "🔴"
        verb = "kazandırdı" if rpnl >= 0 else "zarar ettirdi"
        lines.append(
            f"📊 Son <b>{n_label}</b> işlem: {rw}✅ {rl}❌  |  WR {_wr(rw, rn)}"
        )
        lines.append(
            f"{ricon} Bu {n_label} işlem <b>{'+' if rpnl >= 0 else ''}{rpnl:.2f}$</b> {verb}"
        )
        if tt > n_label:
            ticon = "🟢" if tpnl >= 0 else "🔴"
            lines.append(
                f"📈 Toplam ({since_d or since_fmt[:10]}'den): "
                f"<b>{tt}</b> işlem  |  {ticon} {'+' if tpnl >= 0 else ''}{tpnl:.2f}$"
            )

    lines.append("")
    lines.append(f"💰 PM Bakiye: <b>${balance:.2f}</b>")

    if open_n:
        parts = []
        for pos in open_pos[:3]:
            d_tr = "YÜKSELİR" if pos.get("predicted_dir") == "UP" else "DÜŞER"
            amt = pos.get("pm_spent") or pos.get("amount", 0)
            parts.append(f"{d_tr} ${amt:.2f}")
        extra = f" +{open_n - 3} daha" if open_n > 3 else ""
        lines.append(f"🔴 Açık ({open_n}): {', '.join(parts)}{extra}  |  ${risk:.2f} risk")
    else:
        lines.append("⚪ Açık pozisyon yok")

    lines.append(sep)
    ok = tg_send("\n".join(lines))
    print(f"[{LABEL}] hourly özet: {'OK' if ok else 'HATA'} ({rn} işlem son {HOURLY_ROLLING_N})")


def run_stats() -> None:
    state = load_state()
    _ensure_stats_epoch(state)
    history = _history_tracked(load_history(), state)
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    total = len(history)
    wins = sum(1 for t in history if t.get("win"))
    net = round(sum(t.get("pnl", 0) or 0 for t in history), 2)
    mode = "🔴 GERÇEK PM $4-6" if _PM_LIVE else "🔶 SANAL"
    tg_send(
        f"📊 <b>{TG_HEADER} İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST  |  {mode}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {_wr(wins, total)}\n"
        f"{'🟢' if net >= 0 else '🔴'} P&amp;L: {net:+.2f}$\n"
        f"{_bal_line(state)}\n"
        f"SOL only · 5M110Analiz 15m · 110 snapshot · $4/$5/$6 (WR)"
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "weekly":
        run_weekly()
    elif mode == "hourly":
        run_hourly()
    elif mode == "stats":
        run_stats()
    else:
        run()
