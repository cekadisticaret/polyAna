"""15m yön trader çekirdeği — A3/A8 vb. sanal PM (109 kalıbı)."""
from __future__ import annotations

import html
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analiz32_15m_adapter import Signal15m
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
_DAYS_TR = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

SYMBOLS = ["SOLUSDT"]
INITIAL_BALANCE = 300.0
TRADE_AMOUNT = 10.0
TRADE_AMOUNT_LOW = 8.0
TRADE_AMOUNT_HIGH = 12.0
_PERIOD_SECS = 900
_PERIOD_MIN = 15

_PM_SANITY_MIN = 0.05
_PM_SANITY_MAX = 0.95
_PM_TRADE_MIN = 0.42
_PM_TRADE_MAX = 0.52
_PM_MIN_PAYOUT_RATIO = 1.25


@dataclass(frozen=True)
class Dir15mTraderConfig:
    label: str
    state_file: str
    history_file: str
    weekly_img: str
    pm_live_env: str
    analyze_fn: Callable[[str], Optional[Signal15m]]
    open_delay_sec: int
    stats_blurb: str
    weekend_pause: bool = True
    notify_all: bool = False
    slot_filter: Callable[[dict, list, datetime, int], str | None] | None = None
    on_close: Callable[[dict, list, bool, int], None] | None = None


class Dir15mTrader:
    def __init__(self, cfg: Dir15mTraderConfig) -> None:
        self.cfg = cfg
        self._pm_live = os.getenv(cfg.pm_live_env, "false").lower() in ("1", "true", "yes")
        self._pm_dry_run = not self._pm_live

    @staticmethod
    def _sym_name(symbol: str) -> str:
        return symbol.replace("USDT", "")

    @staticmethod
    def _fmt_price(symbol: str, price: float) -> str:
        return f"{price:.2f}"

    @staticmethod
    def _tg_esc(text: str) -> str:
        return html.escape(str(text), quote=False)

    @staticmethod
    def _wr(wins: int, total: int) -> str:
        return f"%{wins/total*100:.0f} ({wins}/{total})" if total else "veri yok"

    def load_state(self) -> dict:
        if os.path.exists(self.cfg.state_file):
            try:
                with open(self.cfg.state_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"balance": INITIAL_BALANCE, "open_positions": [], "total_pnl": 0.0, "loss_streak": 0, "cooldown_until": 0}

    def save_state(self, state: dict) -> None:
        with open(self.cfg.state_file, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def load_history(self) -> list:
        if os.path.exists(self.cfg.history_file):
            try:
                with open(self.cfg.history_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def save_history(self, history: list) -> None:
        with open(self.cfg.history_file, "w") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

    def _effective_history(self, history: list) -> list:
        if self._pm_live:
            return [t for t in history if t.get("pm_dry_run") is False]
        return history

    def _net_pnl(self, history: list) -> float:
        return round(sum(t.get("pnl", 0) or 0 for t in self._effective_history(history)), 2)

    def _sync_total_pnl(self, state: dict, history: list) -> None:
        state["total_pnl"] = self._net_pnl(history)

    def _trade_amount(self, history: list) -> float:
        amt, _ = _pm_common.trade_amount_by_wr(
            self._effective_history(history),
            low=TRADE_AMOUNT_LOW,
            mid=TRADE_AMOUNT,
            high=TRADE_AMOUNT_HIGH,
        )
        return amt

    def get_all_stats(self, history: list) -> tuple[int, int]:
        rows = self._effective_history(history)
        return sum(1 for t in rows if t.get("win")), len(rows)

    def _cumulative_stats(self, history: list) -> tuple[int, int, float, str]:
        rows = self._effective_history(history)
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

    def _bal_line(self, state: dict) -> str:
        if self._pm_live:
            return _pm_common._pm_bal_line()
        at_risk = sum(
            (p.get("pm_spent") or p.get("amount", 0)) for p in state.get("open_positions", [])
        )
        bal = state["balance"]
        if at_risk > 0:
            return f"💰 Bakiye: ${bal:.2f}  |  📂 ${at_risk:.0f} riskte"
        return f"💰 Bakiye: ${bal:.2f}"

    @staticmethod
    def _current_period_ts() -> int:
        now = int(time.time())
        return now - (now % _PERIOD_SECS)

    @staticmethod
    def _resolve_period_candle(symbol: str, ts_period: int, retries: int = 8, wait_sec: float = 2.0) -> dict | None:
        target_ms = ts_period * 1000
        for _ in range(retries):
            for k in fetch_klines_15m(symbol, 30):
                if k["open_time"] == target_ms:
                    return k
            time.sleep(wait_sec)
        return None

    def _pm_resolve_market(self, symbol: str, ts_period: int, direction: str, amount: float) -> tuple[dict | None, str]:
        if not self._pm_live:
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
        _pm_common._PM_DRY_RUN = self._pm_dry_run
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

    def _cumulative_line(self, history: list) -> str:
        wins, total, net, since = self._cumulative_stats(history)
        if total == 0:
            return "📊 Net P&L: henüz kapanmış işlem yok"
        icon = "🟢" if net >= 0 else "🔴"
        scope = "gerçek PM" if self._pm_live else "sanal"
        since_part = f" · {since}'den beri" if since else ""
        return (
            f"📊 Net P&L ({scope}{since_part}): {icon} <b>{net:+.2f}$</b>"
            f"  |  {total} işlem  |  {self._wr(wins, total)}"
        )

    def run(self) -> None:
        label = self.cfg.label
        now = datetime.now(timezone.utc)
        now_tr = now.astimezone(_TZ_TR)
        dow = now_tr.weekday()
        period_min = (now_tr.hour * 60 + now_tr.minute) // _PERIOD_MIN * _PERIOD_MIN
        ts_period = self._current_period_ts()
        saat = f"{period_min // 60:02d}:{period_min % 60:02d}"
        next_period_min = period_min + _PERIOD_MIN
        next_saat = f"{(next_period_min % (24 * 60)) // 60:02d}:{next_period_min % 60:02d}"

        if self.cfg.weekend_pause and skip_if_weekend_pause(label, "run", now_tr):
            return

        state = self.load_state()
        history = self.load_history()

        closed_lines: list[str] = []
        tur_pnl = 0.0

        if state["open_positions"]:
            time.sleep(3)
            for pos in list(state["open_positions"]):
                sym = pos["symbol"]
                pos_ts = pos.get("ts_period") or pos.get("ts_5m")
                candle = self._resolve_period_candle(sym, pos_ts) if pos_ts else None
                if candle is None:
                    try:
                        candle = fetch_klines_15m(sym, 10)[-2]
                    except Exception as e:
                        print(f"[{label}] Kapanış fiyatı alınamadı ({sym}): {e}")
                        continue

                ref_open = candle["open"]
                prev_close = candle["close"]
                pred = pos["predicted_dir"]
                actual = "UP" if prev_close >= ref_open else "DOWN"
                win = pred == actual
                spent = pos.get("pm_spent") or pos.get("amount", self._trade_amount(history))
                if self._pm_live:
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
                    "pm_dry_run": self._pm_dry_run,
                    **pm_5m_history_extras(pos),
                })
                if self.cfg.on_close:
                    self.cfg.on_close(state, history, win, ts_period)

                name = self._sym_name(sym)
                icon = "✅" if win else "❌"
                dir_tr = "YÜKSELİR" if pred == "UP" else "DÜŞER"
                pct = (prev_close - ref_open) / ref_open * 100 if ref_open else 0
                closed_lines.append(
                    f"{icon} {name} {dir_tr}  {self._fmt_price(sym, ref_open)}→{self._fmt_price(sym, prev_close)} ({pct:+.1f}%)"
                    f"  {'+'+f'${pnl:.2f}' if win else '-$'+f'{spent:.2f}'}"
                )

            state["open_positions"] = []
            if self._pm_live:
                self._sync_total_pnl(state, history)
            self.save_state(state)
            self.save_history(history)

        open_lines: list[str] = []
        skip_lines: list[str] = []

        if self.cfg.open_delay_sec > 0:
            time.sleep(self.cfg.open_delay_sec)

        if self.cfg.slot_filter:
            slot_skip = self.cfg.slot_filter(state, history, now_tr, ts_period)
            if slot_skip:
                skip_lines.append(f"⏸ slot — {self._tg_esc(slot_skip)}")
                print(f"[{label}] {saat} — açılış atlandı: {slot_skip}")
                self.save_state(state)
                self._send_tg_round(saat, next_saat, state, history, closed_lines, open_lines, skip_lines, tur_pnl)
                return

        for sym in SYMBOLS:
            name = self._sym_name(sym)

            def _skip(reason: str) -> None:
                print(f"[{label}] {saat} — {name} atlandı: {reason}")

            sig = self.cfg.analyze_fn(symbol=sym)

            if sig is None:
                _skip("veri yok")
                skip_lines.append(f"⚠️ {name} — veri yok")
                continue
            if sig.direction is None:
                reason = sig.skip_reason or "sinyal yok"
                _skip(reason)
                skip_lines.append(f"⏸ {name} — {self._tg_esc(reason)}")
                continue

            direction = sig.direction
            amount = self._trade_amount(history)
            balance = state["balance"]

            if not self._pm_live and balance < amount:
                _skip("bakiye yetersiz")
                skip_lines.append(f"⏸ {name} — bakiye yetersiz")
                continue

            entry_p = sig.entry_price
            dir_tr = "YÜKSELİR" if direction == "UP" else "DÜŞER"
            dir_icon = "📈" if direction == "UP" else "📉"
            factor_hint = (sig.factors[0] if sig.factors else sig.htf_bias) or ""

            if not self._pm_live:
                pm_info, pm_skip = self._pm_resolve_market(sym, ts_period, direction, amount)
                if not pm_info:
                    _skip(pm_skip or "PM market yok")
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
                    _skip("bakiye yetersiz (stake)")
                    skip_lines.append(f"⏸ {name} — bakiye yetersiz")
                    continue
                sanal_debit_on_open(state, pos)
                state["open_positions"].append(pos)
                open_lines.append(
                    f"{dir_icon} <b>{name} {dir_tr}</b>  "
                    f"skor UP={sig.up_score} DOWN={sig.down_score}  "
                    f"{quote}\n"
                    f"Giriş: {self._fmt_price(sym, entry_p)}  |  {self._tg_esc(factor_hint)}"
                )
                print(f"[{label}] {saat} — {name} {dir_tr} {quote} [SANAL]")
                continue

            from pm_balance_guard import can_open_trade
            if not can_open_trade(label, tg_send):
                _skip("PM açılış kapalı (dashboard)")
                skip_lines.append(f"⏸ {name} — gerçek PM kapalı")
                continue

            _pm_common._PM_DRY_RUN = self._pm_dry_run
            pm_info, pm_skip = self._pm_resolve_market(sym, ts_period, direction, amount)
            if not pm_info:
                _skip(pm_skip or "PM market yok")
                skip_lines.append(f"⏸ {name} {direction} — {pm_skip}")
                continue

            token_price = pm_info["token_price"]
            pm_slug = pm_info["slug"]
            to_win = round(amount / token_price, 2) if token_price > 0 else round(amount * 2, 2)
            if not _pm_common._pm_payout_ok(amount, to_win):
                _skip("payout düşük/yüksek")
                skip_lines.append(f"⏸ {name} — payout düşük/yüksek")
                continue

            token_id = pm_info["up_token"] if direction == "UP" else pm_info["down_token"]
            deadline = _pm_common._pm_open_deadline(ts_period)
            _pm_common._pm_period_warmup(ts_period)
            order_result = _pm_common._pm_place_order(
                token_id, amount, pm_info["tick_size"], pm_info["neg_risk"], deadline=deadline,
            )

            if order_result and order_result.get("_skip"):
                _skip("emir başarısız")
                skip_lines.append(f"⏸ {name} — emir başarısız")
                continue
            if not order_result:
                _skip("PM order başarısız")
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
                f"Giriş: {self._fmt_price(sym, entry_p)}  |  {self._tg_esc(factor_hint)}"
            )
            print(f"[{label}] {saat} — {name} {dir_tr} ${amount:.2f}→${to_win:.2f} [GERÇEK PM]")

        self.save_state(state)
        self._send_tg_round(saat, next_saat, state, history, closed_lines, open_lines, skip_lines, tur_pnl)

    def _send_tg_round(
        self,
        saat: str,
        next_saat: str,
        state: dict,
        history: list,
        closed_lines: list,
        open_lines: list,
        skip_lines: list,
        tur_pnl: float,
    ) -> None:
        label = self.cfg.label
        notify_all = self.cfg.notify_all
        if not closed_lines and not open_lines and not (notify_all and skip_lines):
            return

        sep = "━" * 26
        parts: list[str] = [f"<b>{label} — {saat}</b>"]

        if closed_lines:
            win_all, tot_all = self.get_all_stats(history)
            parts.append(
                "🏁 <b>Sonuçlar</b> (biten tur)\n"
                + "\n".join(closed_lines)
                + f"\n{'🟢' if tur_pnl >= 0 else '🔴'} Bu tur: {tur_pnl:+.2f}$"
                + f"  |  {self._wr(win_all, tot_all)}"
            )

        if open_lines:
            parts.append(
                f"🆕 <b>{saat} → {next_saat}</b>  "
                f"{'🔶 SANAL' if not self._pm_live else '🔴 GERÇEK PM'}\n"
                + "\n".join(open_lines)
            )

        if notify_all and skip_lines:
            parts.append("⏭ <b>Atlanan</b>\n" + "\n".join(skip_lines))

        msg = (
            f"{sep}\n"
            + "\n\n".join(parts)
            + f"\n{self._cumulative_line(history)}\n"
            + f"{self._bal_line(state)}\n"
            f"{sep}"
        )
        ok = tg_send(msg)
        if closed_lines and open_lines:
            kind = "kapanış+açılış"
        elif closed_lines:
            kind = "kapanış"
        elif open_lines:
            kind = "açılış"
        else:
            kind = "atlandı"
        print(f"[{label}] {saat} — TG {kind} gönderildi" if ok else f"[{label}] {saat} — TG {kind} HATA")

    def run_weekly(self) -> None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
        import numpy as np

        label = self.cfg.label
        history = self._effective_history(self.load_history())
        now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
        if not history:
            tg_send(f"📊 <b>{label} WEEKLY</b>\nHenüz veri yok.")
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
        mode = "GERÇEK PM $8-12" if self._pm_live else "SANAL"
        ax.set_title(
            f"{label} — Haftalık  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
            f"Toplam: {total}  |  {genel}  |  {mode}",
            color="#4fc3f7", fontsize=9, fontweight="bold", pad=8,
        )
        fig.colorbar(im, ax=ax, fraction=0.01, pad=0.01)
        plt.tight_layout(pad=1.0)
        plt.savefig(self.cfg.weekly_img, dpi=130, bbox_inches="tight", facecolor="#0a0e1a", pad_inches=0.1)
        plt.close()
        tg_send_photo(
            self.cfg.weekly_img,
            f"📊 {label} Haftalık  {now_tr.strftime('%d.%m.%Y')}  {total} işlem | {genel} | {mode}",
        )

    def run_stats(self) -> None:
        label = self.cfg.label
        history = self._effective_history(self.load_history())
        state = self.load_state()
        now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
        total = len(history)
        wins = sum(1 for t in history if t.get("win"))
        net = round(sum(t.get("pnl", 0) or 0 for t in history), 2)
        mode = "🔴 GERÇEK PM $8-12" if self._pm_live else "🔶 SANAL"
        tg_send(
            f"📊 <b>{label} İSTATİSTİKLER</b>\n"
            f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST  |  {mode}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Toplam: {total} işlem  |  {self._wr(wins, total)}\n"
            f"{'🟢' if net >= 0 else '🔴'} P&amp;L: {net:+.2f}$\n"
            f"{self._bal_line(state)}\n"
            f"{self.cfg.stats_blurb}"
        )

    def run_recent(self, limit: int = 10) -> None:
        label = self.cfg.label
        history = self._effective_history(self.load_history())
        state = self.load_state()
        now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
        rows = history[-limit:]
        if not rows:
            tg_send(f"📋 <b>{label} — son işlemler</b>\nHenüz kapanmış işlem yok.")
            return

        lines: list[str] = []
        for i, t in enumerate(reversed(rows), 1):
            sym = self._sym_name(t.get("symbol", "SOLUSDT"))
            pred = t.get("predicted_dir", "?")
            dir_tr = "YÜKSELİR" if pred == "UP" else "DÜŞER"
            icon = "✅" if t.get("win") else "❌"
            entry = t.get("entry_price")
            exit_p = t.get("exit_price")
            pnl = t.get("pnl", 0) or 0
            amt = t.get("amount", 0)
            et = (t.get("entry_time_tr") or "")[11:16] or "—"
            price_bit = ""
            if entry is not None and exit_p is not None:
                price_bit = f"  {self._fmt_price(t.get('symbol', 'SOLUSDT'), entry)}→{self._fmt_price(t.get('symbol', 'SOLUSDT'), exit_p)}"
            lines.append(
                f"{i}. {icon} {et} {sym} {dir_tr}{price_bit}  "
                f"{'+' if pnl >= 0 else ''}${pnl:.2f} (${amt:.0f})"
            )

        wins = sum(1 for t in rows if t.get("win"))
        net = round(sum(t.get("pnl", 0) or 0 for t in rows), 2)
        tg_send(
            f"📋 <b>{label} — son {len(rows)} işlem</b>\n"
            f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST  |  🔶 SANAL\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(lines) + "\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Özet: {self._wr(wins, len(rows))}  |  {'🟢' if net >= 0 else '🔴'} {net:+.2f}$\n"
            f"{self._bal_line(state)}"
        )

    def cli(self, mode: str) -> None:
        if mode == "weekly":
            self.run_weekly()
        elif mode == "stats":
            self.run_stats()
        elif mode == "recent":
            limit = 10
            if len(sys.argv) > 2:
                try:
                    limit = int(sys.argv[2])
                except ValueError:
                    pass
            self.run_recent(limit)
        else:
            self.run()
