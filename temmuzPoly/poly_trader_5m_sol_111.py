"""
15M 111 SOL — 5M110Analiz FeatureEngine + güçlendirilmiş filtreler (canlı PM, SOL only)
======================================================================================
110'un aynısı, farklar:
  - analiz32_15m_adapter_111 kullanılır (trend/momentum uyum + skor eşiği 15)
  - Ardışık kayıp soğuma periyodu: son 2 işlem kayıpsa 1 tur atlanır

Gerçek PM: PM_5M_111_REAL_ENABLED=true, işlem $8/$10/$12 (WR), başlangıç $300.
Cron: */15 * * * * — açılış +15 sn gecikme, 110 snapshot'ından sinyal · **7/24**
Modlar: open (varsayılan close+open) / weekly / stats
"""
from __future__ import annotations

import html
import json
import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analiz32_15m_adapter_111 import analyze_15m_from_110
from btc_5m_105_algo import fetch_klines_15m
import poly_trader_5m_common as _pm_common
from poly_tg_5m_102 import tg_send, tg_send_photo
from pm_trader_helpers import (
    pm_15m_sanal_quote,
    pm_15m_find_market,
    sanal_pnl,
    sanal_debit_on_open,
    sanal_credit_on_close,
    pm_stake_fields,
    pm_5m_close,
    pm_5m_history_extras,
    pm_sanal_tg_quote,
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
STATE_FILE = os.path.join(_DIR, "poly_trader_5m_sol_111_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_5m_sol_111_history.json")
WEEKLY_IMG = "/tmp/poly_15m_sol_111_weekly.png"

# ── "Filtre olmasaydı ne olurdu" gölge (shadow) log ──────────
# 111 filtreleri (skor eşiği / trend uyumu) bir sinyali elediğinde,
# gerçek para harcanmadan o sinyalin sonucu takip edilir.
SHADOW_PENDING_FILE = os.path.join(_DIR, "poly_trader_5m_sol_111_shadow_pending.json")
SHADOW_HISTORY_FILE = os.path.join(_DIR, "poly_trader_5m_sol_111_shadow_history.json")

SYMBOLS = ["SOLUSDT"]
SYMBOL = "SOLUSDT"
INITIAL_BALANCE = 300.0
TRADE_AMOUNT = 10.0
TRADE_AMOUNT_LOW = 8.0
TRADE_AMOUNT_HIGH = 12.0
_PERIOD_SECS = 900
_PERIOD_MIN = 15
_DAYS_TR = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

# ── 111: Ardışık kayıp soğuma periyodu ───────────────────────
CONSEC_LOSS_STOP = 2      # son N işlem kayıpsa soğumaya gir
COOLDOWN_ROUNDS = 1       # kaç tur (15dk periyodu) atlanacak

_PM_LIVE = os.getenv("PM_5M_111_REAL_ENABLED", "false").lower() in ("1", "true", "yes")
_PM_DRY_RUN = not _PM_LIVE

_PM_SANITY_MIN = 0.05
_PM_SANITY_MAX = 0.95
_PM_TRADE_MIN = 0.42
_PM_TRADE_MAX = 0.52
_PM_MIN_PAYOUT_RATIO = 1.25

LABEL = "15M 111 SOL"
OPEN_DELAY_SEC = 15  # 110'dan 15 sn sonra — aynı snapshot


def _sym_name(symbol: str) -> str:
    return symbol.replace("USDT", "")


def _fmt_price(symbol: str, price: float) -> str:
    return f"{price:.2f}"


def _trade_amount(history: list) -> float:
    amt, _ = _pm_common.trade_amount_by_wr(
        _effective_history(history),
        low=TRADE_AMOUNT_LOW,
        mid=TRADE_AMOUNT,
        high=TRADE_AMOUNT_HIGH,
    )
    return amt


def _tg_esc(text: str) -> str:
    return html.escape(str(text), quote=False)


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": INITIAL_BALANCE, "open_positions": [], "total_pnl": 0.0, "cooldown_skips_left": 0}


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


def _pm_resolve_market(symbol: str, ts_period: int, direction: str, amount: float) -> tuple[dict | None, str]:
    if not _PM_LIVE:
        pm = pm_15m_find_market(ts_period, symbol)
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
        if not (_PM_TRADE_MIN <= tp <= _PM_TRADE_MAX):
            return None, f"token @{tp:.2f} band dışı ({_PM_TRADE_MIN}–{_PM_TRADE_MAX})"
        est = round(amount / tp, 2) if tp > 0 else 0
        if est < amount * _PM_MIN_PAYOUT_RATIO:
            return None, f"payout {est/amount:.2f}x < {_PM_MIN_PAYOUT_RATIO} (@{tp:.2f})"
        pm["token_price"] = tp
        return pm, ""
    return None, "PM fiyat/market geçersiz"


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


# ── Gölge (shadow) log — "filtre olmasaydı ne olurdu" ────────
def load_shadow_pending() -> list:
    if os.path.exists(SHADOW_PENDING_FILE):
        try:
            with open(SHADOW_PENDING_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_shadow_pending(pending: list) -> None:
    with open(SHADOW_PENDING_FILE, "w") as f:
        json.dump(pending, f, indent=2, ensure_ascii=False)


def load_shadow_history() -> list:
    if os.path.exists(SHADOW_HISTORY_FILE):
        try:
            with open(SHADOW_HISTORY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_shadow_history(rows: list) -> None:
    with open(SHADOW_HISTORY_FILE, "w") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)


def _resolve_shadow_pending(now_tr: datetime) -> None:
    """Süresi dolmuş gölge sinyalleri gerçek fiyatla çözümler, shadow_history'ye yazar."""
    pending = load_shadow_pending()
    if not pending:
        return

    still_pending: list = []
    resolved: list = []
    for item in pending:
        candle = _resolve_period_candle(item["symbol"], item["ts_period"], retries=2, wait_sec=1.0)
        if candle is None:
            # mum henüz kapanmamış olabilir — bir sonraki turda tekrar denenir
            still_pending.append(item)
            continue

        ref_open = candle["open"]
        prev_close = candle["close"]
        actual = "UP" if prev_close >= ref_open else "DOWN"
        would_win = item["raw_direction"] == actual
        pct = (prev_close - ref_open) / ref_open * 100 if ref_open else 0

        resolved.append({
            **item,
            "actual_dir": actual,
            "exit_price": prev_close,
            "pct_change": round(pct, 3),
            "would_win": would_win,
            "resolved_time_tr": now_tr.isoformat(),
        })

    if resolved:
        history = load_shadow_history()
        history.extend(resolved)
        save_shadow_history(history)
        wins = sum(1 for r in resolved if r["would_win"])
        print(f"[{LABEL}] gölge çözümleme: {len(resolved)} sinyal, {wins} 'kazanırdı'")

    save_shadow_pending(still_pending)


def _log_shadow_skip(sig, sym: str, ts_period: int, now_tr: datetime) -> None:
    """111 filtreleri bir sinyali elediğinde (predictor kendi gate'ini geçmişti) kaydeder."""
    if not sig.raw_direction:
        return  # predictor zaten kendi gate'inde pas geçmiş, gölge işlem yok
    pending = load_shadow_pending()
    pending.append({
        "symbol": sym,
        "raw_direction": sig.raw_direction,
        "entry_price": sig.entry_price,
        "up_score": sig.up_score,
        "down_score": sig.down_score,
        "skip_reason": sig.skip_reason,
        "ts_period": ts_period,
        "entry_time_tr": now_tr.isoformat(),
    })
    save_shadow_pending(pending)


# ── 111: Ardışık kayıp tespiti ───────────────────────────────
def _consecutive_losses(history: list) -> int:
    """Son kapanan işlemlerden geriye doğru, art arda kaç kayıp var."""
    rows = _effective_history(history)
    count = 0
    for t in reversed(rows):
        if t.get("win") is False:
            count += 1
        else:
            break
    return count


def run() -> None:
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    dow = now_tr.weekday()
    period_min = (now_tr.hour * 60 + now_tr.minute) // _PERIOD_MIN * _PERIOD_MIN
    ts_period = _current_period_ts()
    saat = f"{period_min // 60:02d}:{period_min % 60:02d}"
    next_period_min = period_min + _PERIOD_MIN
    next_saat = f"{(next_period_min % (24 * 60)) // 60:02d}:{next_period_min % 60:02d}"

    state = load_state()
    state.setdefault("cooldown_skips_left", 0)
    history = load_history()

    _resolve_shadow_pending(now_tr)

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
            spent = pos.get("pm_spent") or pos.get("amount", _trade_amount(history))
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

    # ── 111: soğuma periyodu kontrolü (turun başında, tüm semboller için) ──
    if state.get("cooldown_skips_left", 0) > 0:
        state["cooldown_skips_left"] -= 1
        skip_lines.append(
            f"❄️ Soğuma periyodu — ardışık kayıp sonrası bekleniyor "
            f"({state['cooldown_skips_left']} tur kaldı)"
        )
        save_state(state)
        _send_tg_round(saat, next_saat, state, history, closed_lines, open_lines, skip_lines, tur_pnl)
        return

    consec = _consecutive_losses(history)
    if consec >= CONSEC_LOSS_STOP:
        state["cooldown_skips_left"] = COOLDOWN_ROUNDS
        skip_lines.append(
            f"❄️ {consec} ardışık kayıp — soğuma periyodu başlıyor ({COOLDOWN_ROUNDS} tur atlanacak)"
        )
        save_state(state)
        _send_tg_round(saat, next_saat, state, history, closed_lines, open_lines, skip_lines, tur_pnl)
        return

    if OPEN_DELAY_SEC > 0:
        time.sleep(OPEN_DELAY_SEC)

    for sym in SYMBOLS:
        name = _sym_name(sym)
        sig = analyze_15m_from_110(symbol=sym, ts_period=ts_period)

        if sig is None:
            skip_lines.append(f"⚠️ {name} — veri yok")
            continue
        if sig.direction is None:
            reason = sig.skip_reason or "sinyal yok"
            skip_lines.append(f"⏸ {name} — {_tg_esc(reason)}")
            print(f"[{LABEL}] {saat} — {name} atlandı: {reason}")
            _log_shadow_skip(sig, sym, ts_period, now_tr)
            continue

        direction = sig.direction
        amount = _trade_amount(history)
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
            print(f"[{LABEL}] {saat} — {name} {dir_tr} {quote} [SANAL A32-111]")
            continue

        # ── Canlı PM ──────────────────────────────────────────
        from pm_balance_guard import can_open_trade
        if not can_open_trade(LABEL, tg_send):
            save_state(state)
            if closed_lines:
                _send_tg_round(saat, next_saat, state, history, closed_lines, [], [], tur_pnl)
            return

        _pm_common._PM_DRY_RUN = _PM_DRY_RUN
        pm_info, pm_skip = _pm_resolve_market(sym, ts_period, direction, amount)
        if not pm_info:
            skip_lines.append(f"⏸ {name} {direction} — {pm_skip}")
            continue

        token_price = pm_info["token_price"]
        pm_slug = pm_info["slug"]
        to_win = round(amount / token_price, 2) if token_price > 0 else round(amount * 2, 2)
        if not _pm_common._pm_payout_ok(amount, to_win):
            skip_lines.append(f"⏸ {name} — payout düşük/yüksek")
            continue

        token_id = pm_info["up_token"] if direction == "UP" else pm_info["down_token"]
        deadline = _pm_common._pm_open_deadline(ts_period)
        _pm_common._pm_period_warmup(ts_period)
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
        print(f"[{LABEL}] {saat} — {name} {dir_tr} ${amount:.2f}→${to_win:.2f} [GERÇEK PM A32-111]")

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

    history = _effective_history(load_history())
    state = load_state()
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    if not history:
        tg_send(f"📊 <b>{LABEL} WEEKLY</b>\nHenüz veri yok.")
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
    mode = "GERÇEK PM $8-12" if _PM_LIVE else "SANAL"
    ax.set_title(
        f"{LABEL} — Haftalık  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
        f"Toplam: {total}  |  {genel}  |  {mode}",
        color="#4fc3f7", fontsize=9, fontweight="bold", pad=8,
    )
    fig.colorbar(im, ax=ax, fraction=0.01, pad=0.01)
    plt.tight_layout(pad=1.0)
    plt.savefig(WEEKLY_IMG, dpi=130, bbox_inches="tight", facecolor="#0a0e1a", pad_inches=0.1)
    plt.close()
    tg_send_photo(WEEKLY_IMG, f"📊 {LABEL} Haftalık  {now_tr.strftime('%d.%m.%Y')}  {total} işlem | {genel} | {mode}")


def _shadow_summary_line() -> str:
    rows = load_shadow_history()
    if not rows:
        return "🕶 Gölge (elenen sinyal): henüz veri yok"
    total = len(rows)
    would_wins = sum(1 for r in rows if r.get("would_win"))
    wr = f"%{would_wins/total*100:.0f}" if total else "—"
    score_skips = sum(1 for r in rows if "skor zayıf" in (r.get("skip_reason") or ""))
    trend_skips = sum(1 for r in rows if "çelişki" in (r.get("skip_reason") or ""))
    return (
        f"🕶 Gölge (elenen sinyal): {total} adet  |  'kazanırdı' oranı: {wr} ({would_wins}/{total})\n"
        f"   — skor eşiği: {score_skips}  |  trend/mom çelişkisi: {trend_skips}"
    )


def run_stats() -> None:
    history = _effective_history(load_history())
    state = load_state()
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    total = len(history)
    wins = sum(1 for t in history if t.get("win"))
    net = round(sum(t.get("pnl", 0) or 0 for t in history), 2)
    mode = "🔴 GERÇEK PM $8-12" if _PM_LIVE else "🔶 SANAL"
    tg_send(
        f"📊 <b>{LABEL} İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST  |  {mode}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {_wr(wins, total)}\n"
        f"{'🟢' if net >= 0 else '🔴'} P&amp;L: {net:+.2f}$\n"
        f"{_bal_line(state)}\n"
        f"{_shadow_summary_line()}\n"
        f"SOL only · 5M110Analiz 15m · 111 filtreleri (skor≥15, trend uyumu, soğuma) · $8/$10/$12 (WR)"
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        run()
