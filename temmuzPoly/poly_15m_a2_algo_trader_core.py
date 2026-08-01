"""15M A2 Top3 — Squeeze / Supertrend / SuperTrend v2 sanal trader çekirdeği.

A2#09/#16/#17 sinyallerinin 15m versiyonu. 1h A2 koduna dokunmaz.
Telegram: 15M 110 ile aynı bot (poly_tg_5m_102).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import algo_signals as sig
from algo_catalog_extended import squeeze_momentum
from poly_tg_5m_102 import tg_send
from pm_trader_helpers import (
    SANAL_INITIAL_BALANCE,
    pm_15m_sanal_quote,
    pm_5m_history_extras,
    pm_sanal_tg_quote,
    resolve_slot_trade_amount,
    sanal_pnl,
    skip_if_weekend_pause,
    slot_amount_log,
)

_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_FILE = os.path.join(_DIR, "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

_TZ_TR = ZoneInfo("Europe/Istanbul")
_PERIOD_SECS = 900
_PERIOD_MIN = 15
OPEN_DELAY_SEC = 1
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
AMOUNT_LOW = 6.0
AMOUNT_MID = 8.0
AMOUNT_HIGH = 10.0
KLINES_LIMIT = 200


@dataclass(frozen=True)
class M15Config:
    num: int
    key: str
    label: str
    algo_name: str
    signal_fn: Callable
    state_file: str
    history_file: str


def _build_configs() -> list[M15Config]:
    specs = [
        (309, "Squeeze Mom", "Squeeze Momentum (BB+KC)", squeeze_momentum),
        (316, "Supertrend", "Supertrend", sig.supertrend),
        (317, "SuperTrend v2", "SuperTrend v2 (7,2.0)", sig.supertrend_v2),
    ]
    out: list[M15Config] = []
    for num, short, full_name, fn in specs:
        key = f"15m_{num}"
        out.append(
            M15Config(
                num=num,
                key=key,
                label=f"15M {num} {short}",
                algo_name=full_name,
                signal_fn=fn,
                state_file=os.path.join(_DIR, f"poly_trader_{key}_state.json"),
                history_file=os.path.join(_DIR, f"poly_trader_{key}_history.json"),
            )
        )
    return out


ALL_CONFIGS = _build_configs()
CONFIG_BY_NUM = {c.num: c for c in ALL_CONFIGS}


def _wr(wins: int, total: int) -> str:
    return f"%{wins / total * 100:.0f} ({wins}/{total})" if total else "veri yok"


def _sym_short(symbol: str) -> str:
    return symbol.replace("USDT", "")


def _load_state(cfg: M15Config) -> dict:
    if os.path.exists(cfg.state_file):
        try:
            with open(cfg.state_file) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": SANAL_INITIAL_BALANCE, "open_positions": [], "total_pnl": 0.0}


def _save_state(cfg: M15Config, state: dict) -> None:
    with open(cfg.state_file, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _load_history(cfg: M15Config) -> list:
    if os.path.exists(cfg.history_file):
        try:
            with open(cfg.history_file) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_history(cfg: M15Config, history: list) -> None:
    with open(cfg.history_file, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _current_period_ts() -> int:
    now = int(time.time())
    return now - (now % _PERIOD_SECS)


def _fetch_klines_15m(symbol: str, limit: int = KLINES_LIMIT) -> list[dict]:
    """Binance 15m — algo_signals o/h/l/c/v formatı + open_time."""
    url = (
        f"https://fapi.binance.com/fapi/v1/klines"
        f"?symbol={symbol}&interval=15m&limit={limit}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as r:
        raw = json.loads(r.read().decode())
    return [
        {
            "open_time": int(x[0]),
            "o": float(x[1]),
            "h": float(x[2]),
            "l": float(x[3]),
            "c": float(x[4]),
            "v": float(x[5]),
            "open": float(x[1]),
            "high": float(x[2]),
            "low": float(x[3]),
            "close": float(x[4]),
        }
        for x in raw
    ]


def _resolve_period_candle(symbol: str, ts_period: int, retries: int = 6, wait_sec: float = 2.0) -> dict | None:
    target_ms = ts_period * 1000
    for _ in range(retries):
        try:
            for k in _fetch_klines_15m(symbol, 40):
                if k["open_time"] == target_ms:
                    return k
        except Exception as e:
            print(f"[15M A2] candle fetch {symbol}: {e}", file=sys.stderr)
        time.sleep(wait_sec)
    return None


def _symbol_wr_amount(history: list, symbol: str) -> float:
    trades = [t for t in history if t.get("symbol") == symbol]
    if not trades:
        return AMOUNT_MID
    wins = sum(1 for t in trades if t.get("win"))
    rate = wins / len(trades)
    if rate > 0.5:
        return AMOUNT_HIGH
    if rate < 0.5:
        return AMOUNT_LOW
    return AMOUNT_MID


def _resolve_amount(history: list, sym: str, hour_tr: int) -> tuple[float, bool, bool]:
    base = _symbol_wr_amount(history, sym)
    return resolve_slot_trade_amount(base, hour_tr, history)


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol]
    return sum(1 for t in trades if t["win"]), len(trades)


def _signal_for(cfg: M15Config, symbol: str) -> tuple[str | None, float | None]:
    """Kapalı 15m mumlarla sinyal + giriş fiyatı (son kapalı close)."""
    try:
        kl = _fetch_klines_15m(symbol, KLINES_LIMIT)
    except Exception as e:
        print(f"[{cfg.label}] {symbol} kline: {e}", file=sys.stderr)
        return None, None
    if len(kl) < 30:
        return None, None
    closed = kl[:-1]  # oluşan mumu çıkar
    try:
        direction = cfg.signal_fn(closed)
    except Exception as e:
        print(f"[{cfg.label}] {symbol} sinyal: {e}", file=sys.stderr)
        return None, None
    if direction not in ("UP", "DOWN"):
        return None, None
    return direction, float(closed[-1]["c"])


def run_close(cfg: M15Config) -> tuple[list[str], float]:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    state = _load_state(cfg)
    history = _load_history(cfg)
    if not state["open_positions"]:
        return [], 0.0

    time.sleep(2)
    lines: list[str] = []
    tur_pnl = 0.0
    kept: list[dict] = []

    for pos in list(state["open_positions"]):
        sym = pos["symbol"]
        pos_ts = pos.get("ts_period")
        candle = _resolve_period_candle(sym, pos_ts) if pos_ts else None
        if candle is None:
            try:
                candle = _fetch_klines_15m(sym, 10)[-2]
            except Exception as e:
                print(f"[{cfg.label}] close {sym}: {e}", file=sys.stderr)
                kept.append(pos)
                continue

        ref_open = float(candle["open"])
        prev_close = float(candle["close"])
        pred = pos["predicted_dir"]
        actual = "UP" if prev_close >= ref_open else "DOWN"
        win = pred == actual
        pnl = sanal_pnl(pos, win)
        tur_pnl += pnl
        state["balance"] = round(state["balance"] + pnl, 2)
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

        rec = {
            "symbol": sym,
            "predicted_dir": pred,
            "actual_dir": actual,
            "win": win,
            "entry_price": ref_open,
            "exit_price": prev_close,
            "amount": pos.get("amount", AMOUNT_MID),
            "pnl": pnl,
            "entry_time_tr": pos.get("entry_time_tr"),
            "entry_period_min": pos.get("entry_period_min"),
            "entry_dow": pos.get("entry_dow"),
            "entry_hour_tr": pos.get("entry_hour_tr"),
            "exit_time_tr": now_tr.isoformat(),
            "algo_name": pos.get("algo_name", cfg.algo_name),
            "algo_num": cfg.num,
            **pm_5m_history_extras(pos),
        }
        history.append(rec)

        name = _sym_short(sym)
        icon = "✅" if win else "❌"
        pct = (prev_close - ref_open) / ref_open * 100 if ref_open else 0
        pnl_str = f"+{pnl:.2f}$" if win else f"{pnl:.2f}$"
        lines.append(
            f"{icon} {name}  {pred}  {ref_open:.2f}→{prev_close:.2f} ({pct:+.1f}%)  {pnl_str}"
        )

    state["open_positions"] = kept
    _save_state(cfg, state)
    _save_history(cfg, history)
    print(f"[{cfg.label} close] {len(lines)} pozisyon kapatıldı")
    return lines, tur_pnl


def run_open(cfg: M15Config) -> list[str]:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    hour_tr = now_tr.hour
    dow = now_tr.weekday()
    period_min = (now_tr.hour * 60 + now_tr.minute) // _PERIOD_MIN * _PERIOD_MIN
    ts_period = _current_period_ts()

    state = _load_state(cfg)
    history = _load_history(cfg)
    lines: list[str] = []

    for sym in SYMBOLS:
        direction, entry_price = _signal_for(cfg, sym)
        name = _sym_short(sym)
        if direction is None or entry_price is None:
            print(f"[{cfg.label} open] {sym} — NEUTRAL/veri yok")
            continue

        amount, hot_boost, cold_cut = _resolve_amount(history, sym, hour_tr)
        slot_amount_log(cfg.label, hour_tr, _symbol_wr_amount(history, sym), amount, hot_boost, cold_cut)

        pm_q = pm_15m_sanal_quote(ts_period, direction, amount, sym)
        pos = {
            "symbol": sym,
            "predicted_dir": direction,
            "entry_price": entry_price,
            "entry_time_tr": now_tr.isoformat(),
            "entry_period_min": period_min,
            "entry_dow": dow,
            "entry_hour_tr": hour_tr,
            "ts_period": ts_period,
            "amount": amount,
            "hot_hour_boost": hot_boost,
            "cold_hour_cut": cold_cut,
            "algo_name": cfg.algo_name,
            "algo_num": cfg.num,
            "virtual": True,
            **pm_q,
        }
        state["open_positions"].append(pos)

        dir_icon = "📈" if direction == "UP" else "📉"
        dir_tr = "YÜKSELİR" if direction == "UP" else "DÜŞER"
        sym_w, sym_t = get_symbol_stats(history, sym)
        quote = pm_sanal_tg_quote(amount, pm_q.get("token_price"), pm_q.get("to_win"))
        tags = ""
        if hot_boost:
            tags += "  🔥+%40"
        if cold_cut:
            tags += "  ❄️-%30"
        live_tag = ""
        if cfg.num == 309:
            try:
                from poly_trader_15m_309_live import mirror_open_from_sanal
                live_line = mirror_open_from_sanal(
                    symbol=sym,
                    direction=direction,
                    entry_price=entry_price,
                    ts_period=ts_period,
                    period_min=period_min,
                    dow=dow,
                    hour_tr=hour_tr,
                    now_tr=now_tr,
                )
                if live_line:
                    live_tag = "  🔴+$3 LIVE"
            except Exception as e:
                print(f"[{cfg.label}] live mirror hata: {e}", file=sys.stderr)

        lines.append(
            f"{dir_icon} <b>{name}</b>  {dir_tr}  giriş:{entry_price:.2f}  {quote}{tags}{live_tag}\n"
            f"   genel: {_wr(sym_w, sym_t)}"
        )
        print(f"[{cfg.label} open] {name} {dir_tr} ${amount:.0f}{live_tag}")

    _save_state(cfg, state)
    return lines


def _tg_round(
    cfg: M15Config,
    saat: str,
    next_saat: str,
    closed: list[str],
    opened: list[str],
    tur_pnl: float,
) -> None:
    if not closed and not opened:
        return
    state = _load_state(cfg)
    history = _load_history(cfg)
    wins = sum(1 for t in history if t.get("win"))
    total = len(history)
    sep = "━" * 26
    parts = [f"<b>{cfg.label} — {saat}</b>  🔶 SANAL"]
    if closed:
        parts.append(
            "🏁 <b>Sonuçlar</b>\n"
            + "\n".join(closed)
            + f"\n{'🟢' if tur_pnl >= 0 else '🔴'} Bu tur: {tur_pnl:+.2f}$"
            + f"  |  {_wr(wins, total)}"
        )
    if opened:
        parts.append(f"🆕 <b>{saat} → {next_saat}</b>\n" + "\n".join(opened))
    msg = (
        f"{sep}\n"
        + "\n\n".join(parts)
        + f"\n💰 Bakiye: ${state['balance']:.2f}  |  📂 Açık: {len(state.get('open_positions', []))} poz\n"
        f"{sep}"
    )
    try:
        tg_send(msg)
        print(f"[{cfg.label}] TG gönderildi")
    except Exception as e:
        print(f"[{cfg.label}] TG hata: {e}", file=sys.stderr)


def run_all(configs: list[M15Config] | None = None) -> None:
    """Her 15dk: close önceki tur → open yeni tur (110 tarzı).

    Cum 22:00 – Pzt 08:00 İST: yalnızca close; yeni open yok (Pzt 08:00'de devam).
    """
    cfgs = configs or ALL_CONFIGS
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    period_min = (now_tr.hour * 60 + now_tr.minute) // _PERIOD_MIN * _PERIOD_MIN
    saat = f"{period_min // 60:02d}:{period_min % 60:02d}"
    next_period_min = period_min + _PERIOD_MIN
    next_saat = f"{(next_period_min % (24 * 60)) // 60:02d}:{next_period_min % 60:02d}"
    pause_open = skip_if_weekend_pause("15M A2", "open", now_tr)

    for cfg in cfgs:
        closed, tur_pnl = run_close(cfg)
        if cfg.num == 309:
            try:
                from poly_trader_15m_309_live import run_close as live_close
                live_close(wait=False)  # sanal close zaten 2s bekledi
            except Exception as e:
                print(f"[{cfg.label}] live close hata: {e}", file=sys.stderr)
        if pause_open:
            opened = []
        else:
            if OPEN_DELAY_SEC > 0:
                time.sleep(OPEN_DELAY_SEC)
            opened = run_open(cfg)  # 309: sanal açarken aynı anda live mirror
        if closed or opened:
            _tg_round(cfg, saat, next_saat, closed, opened, tur_pnl)


def run_weekly(configs: list[M15Config] | None = None) -> None:
    cfgs = configs or ALL_CONFIGS
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    lines = [
        "📊 <b>15M A2 Top3 — Haftalık</b>",
        now_tr.strftime("%d.%m.%Y %H:%M") + " İST",
        "━" * 28,
    ]
    for cfg in cfgs:
        history = _load_history(cfg)
        state = _load_state(cfg)
        total = len(history)
        if total == 0:
            lines.append(f"  ⚪ {cfg.label}: veri yok")
            continue
        wins = sum(1 for t in history if t.get("win"))
        wr = wins / total * 100
        pnl = state.get("total_pnl", 0.0)
        bal = state.get("balance", SANAL_INITIAL_BALANCE)
        icon = "🟢" if wr >= 55 else "🟡" if wr >= 50 else "🔴"
        lines.append(
            f"  {icon} {cfg.label}: %{wr:.0f} ({wins}/{total})"
            f"  P&L {'+' if pnl >= 0 else ''}{pnl:.1f}$  |  ${bal:.2f}"
        )
    tg_send("\n".join(lines))
