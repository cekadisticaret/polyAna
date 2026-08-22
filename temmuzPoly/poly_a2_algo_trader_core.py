"""Analiz 2 — 17 kârlı algo için bağımsız sanal trader çekirdeği."""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from algo_signals_v2 import ALGO_V2_META
from poly_predictor_analysis import _fetch_klines
from pm_trader_helpers import (
    SANAL_INITIAL_BALANCE,
    apply_pm_quote,
    load_sanal_wr_amounts,
    pm_hourly_profit_entry_ok,
    pm_sanal_settle_trade,
    pm_sanal_slot_candle,
    pm_tg_stake,
    resolve_slot_trade_amount,
    sanal_pnl,
    skip_if_weekend_pause,
    slot_amount_log,
    wr_tier_amount,
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
_DAYS_TR = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_SIGNALS_FILE = "/tmp/algo_signals_v2.json"

# A2 Top 17 — sanal analizler (8727030715) botundan AYRI kanal/bot
_DEFAULT_A2_TOKEN = os.getenv(
    "TELEGRAM_ANALIZ9_BOT_TOKEN",
    "8654967936:AAFp0hDESfXi0iZDRVc5I1JwyTS9N9_rAXE",
)
_DEFAULT_A2_CHAT = os.getenv(
    "TELEGRAM_ANALIZ9_CHAT_ID",
    os.getenv("TELEGRAM_POLY_TRADERS_CHAT_ID", os.getenv("TELEGRAM_CHAT", "")),
)
BOT_TOKEN = os.getenv("TELEGRAM_A2_BOT_TOKEN", _DEFAULT_A2_TOKEN)
CHAT_ID = os.getenv("TELEGRAM_A2_CHAT_ID", _DEFAULT_A2_CHAT)

# A2#09/#16/#17 → eski ALFA ANALİZ Telegram kanalı (8256912678)
_A2_ALFA_CHANNEL_ALGOS = frozenset({9, 16, 17})
_ALFA_BOT_TOKEN = os.getenv(
    "TELEGRAM_ALFA_BOT_TOKEN",
    "8256912678:AAFWEoRWO7Z0siK_c4Dm5XjgtBKmh-wmF8E",
)
_ALFA_CHAT_ID = os.getenv("TELEGRAM_ALFA_CHAT_ID") or os.getenv("TELEGRAM_POLY_TRADERS_CHAT_ID") or os.getenv("TELEGRAM_CHAT") or ""

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


@dataclass(frozen=True)
class A2Config:
    algo_num: int
    key: str
    label: str
    algo_name: str
    state_file: str
    history_file: str
    # Aşağıdakilerin varsayılanı mevcut 17 A2 defterinin davranışıdır; türev
    # defterler (ör. A2#05 V2) aynı sinyali farklı kurallarla koşturmak için ezer.
    min_entry_price: float | None = None   # None = fiyat tabanı yok
    # (alt, üst) — bilet bu yarı açık aralığa düşerse atlanır. Taban tüm ucuz
    # biletleri keserken bant yalnız ölçülen zarar dilimini keser.
    exclude_price_band: tuple[float, float] | None = None
    # (alt, üst) — |z| bu yarı açık aralığın DIŞINDAysa atlanır. Fiyat kuralları
    # piyasanın görüşünü süzer; bu sinyalin kendi güven derecesini süzer.
    z_gate: tuple[float, float] | None = None
    shadow_log: str | None = None          # atlanan slotları da kaydet (jsonl)
    live_mirror: bool = True               # False = gerçek para aynası hiç çağrılmaz
    init_balance: float | None = None      # None = SANAL_INITIAL_BALANCE ($1000)


Z_PERIOD = 20


def entry_zscore(klines: list[dict], period: int = Z_PERIOD) -> float | None:
    """Giriş anındaki z — `algo_signals.mean_reversion` ile birebir aynı aritmetik.

    Sinyal fonksiyonu z'yi hesaplayıp yalnız işaretini döndürüyor, büyüklüğü
    atıyor. Burada aynı pencereyi (son 20 kapanış, popülasyon std'si) yeniden
    kurup büyüklüğü de elde ediyoruz.
    """
    closes = [k["close"] for k in klines if k.get("close") is not None]
    if len(closes) < period:
        return None
    win = closes[-period:]
    mean = sum(win) / period
    std = math.sqrt(sum((v - mean) ** 2 for v in win) / period)
    if not std:
        return None
    return (win[-1] - mean) / std


def _shadow_write(cfg: A2Config, row: dict) -> None:
    """Alınan ve atlanan slotları birlikte kaydet — kapı eşiği veriden ayarlansın."""
    if not cfg.shadow_log:
        return
    try:
        with open(cfg.shadow_log, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[{cfg.label}] gölge günlüğü yazılamadı: {e}", file=sys.stderr)


def _symbol_wr_amount(cfg: A2Config, history: list, symbol: str) -> float:
    low, mid, high = load_sanal_wr_amounts(cfg.key)
    return wr_tier_amount(history, symbol, low, mid, high)


def _resolve_trade_amount(
    cfg: A2Config, history: list, sym: str, hour_tr: int,
) -> tuple[float, bool, bool]:
    base = _symbol_wr_amount(cfg, history, sym)
    return resolve_slot_trade_amount(base, hour_tr, history)


def _build_configs() -> list[A2Config]:
    out: list[A2Config] = []
    for num, name, _cat, _kind, _fn in ALGO_V2_META:
        key = f"a2_{num:02d}"
        out.append(
            A2Config(
                algo_num=num,
                key=key,
                label=f"A2#{num:02d} {name}",
                algo_name=name,
                state_file=os.path.join(_DIR, f"poly_trader_{key}_state.json"),
                history_file=os.path.join(_DIR, f"poly_trader_{key}_history.json"),
                # Ucuz bilet (0,40 altı) A2#05'te ölçülen zararın tamamıydı.
                min_entry_price=0.40 if num == 5 else None,
            )
        )
    return out


ALL_CONFIGS = _build_configs()
CONFIG_BY_NUM = {c.algo_num: c for c in ALL_CONFIGS}
CONFIG_BY_KEY = {c.key: c for c in ALL_CONFIGS}


def _wr(wins: int, total: int) -> str:
    return f"%{wins / total * 100:.0f} ({wins}/{total})" if total else "veri yok"


def _load_state(cfg: A2Config) -> dict:
    if os.path.exists(cfg.state_file):
        try:
            with open(cfg.state_file) as f:
                return json.load(f)
        except Exception:
            pass
    init = float(cfg.init_balance) if cfg.init_balance is not None else SANAL_INITIAL_BALANCE
    return {"balance": init, "open_positions": [], "total_pnl": 0.0}


def _save_state(cfg: A2Config, state: dict) -> None:
    with open(cfg.state_file, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _load_history(cfg: A2Config) -> list:
    if os.path.exists(cfg.history_file):
        try:
            with open(cfg.history_file) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_history(cfg: A2Config, history: list) -> None:
    with open(cfg.history_file, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def tg_send(text: str) -> None:
    """Varsayılan A2 Top 17 botu (8654967936)."""
    _tg_send_raw(text, BOT_TOKEN, CHAT_ID, "TG A2")


def tg_send_alfa_channel(text: str) -> None:
    """Eski ALFA ANALİZ bot + chat (8256912678)."""
    _tg_send_raw(text, _ALFA_BOT_TOKEN, _ALFA_CHAT_ID, "TG ALFA")


def tg_send_for_cfg(cfg: A2Config | None, text: str) -> None:
    """#09/#16/#17 → ALFA kanalı; diğer 14 → A2 kanalı."""
    if cfg and cfg.algo_num in _A2_ALFA_CHANNEL_ALGOS:
        tg_send_alfa_channel(text)
        return
    tg_send(text)


def _tg_send_raw(text: str, token: str, chat_id: str, log_label: str) -> None:
    """Telegram — 4096 limit; uzun özetleri parçala."""
    from telegram_poly_channels import ANALIZ1_CHAT_ID
    if not chat_id or chat_id == ANALIZ1_CHAT_ID:
        print(f"[{log_label}] kanal tanımlı değil veya 1. ANALİZ kanalı — atlandı")
        return
    max_len = 3900
    chunks: list[str] = []
    if len(text) <= max_len:
        chunks = [text]
    else:
        buf = ""
        for line in text.split("\n"):
            add = line + "\n"
            if len(buf) + len(add) > max_len and buf.strip():
                chunks.append(buf.rstrip())
                buf = add
            else:
                buf += add
        if buf.strip():
            chunks.append(buf.rstrip())

    for i, chunk in enumerate(chunks):
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"}
            if len(chunks) > 1:
                payload["text"] = f"({i + 1}/{len(chunks)})\n{chunk}"
            body = urllib.parse.urlencode(payload).encode()
            req = urllib.request.Request(url, data=body)
            with urllib.request.urlopen(req, timeout=15) as r:
                r.read()
        except Exception as e:
            print(f"[{log_label}] Hata ({i + 1}/{len(chunks)}): {e}", file=sys.stderr)


def _load_v2_signal(algo_num: int) -> dict | None:
    if not os.path.exists(_SIGNALS_FILE):
        return None
    try:
        with open(_SIGNALS_FILE) as f:
            data = json.load(f)
        return (data.get("signals") or {}).get(str(algo_num))
    except Exception as e:
        print(f"[A2#{algo_num:02d}] sinyal okuma hatası: {e}")
        return None


def _sym_short(symbol: str) -> str:
    return symbol.replace("USDT", "")


def get_stats(history: list, symbol: str, hour_tr: int) -> tuple[int, int]:
    trades = [
        t for t in history
        if t["symbol"] == symbol and t.get("entry_hour_tr") == hour_tr
    ]
    return sum(1 for t in trades if t["win"]), len(trades)


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol]
    return sum(1 for t in trades if t["win"]), len(trades)


async def run_close(cfg: A2Config, *, notify: bool = True) -> str | None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")
    state = _load_state(cfg)
    history = _load_history(cfg)

    if not state["open_positions"]:
        print(f"[{cfg.label} close] {saat} — açık pozisyon yok")
        return None

    lines: list[str] = []
    toplam_pnl = 0.0
    failed: list[dict] = []

    cur_hour = now_tr.hour
    for pos in list(state["open_positions"]):
        # Bu saatte yeni açılanı kapatma — A2#05 :02 open ile :02 toplu close çakışmasın.
        if pos.get("entry_hour_tr") == cur_hour:
            failed.append(pos)
            continue
        candle = pm_sanal_slot_candle(pos["symbol"], pos["entry_time_tr"])
        if not candle:
            failed.append(pos)
            continue
        hour_open, hour_close = candle
        settled = pm_sanal_settle_trade(pos, hour_open, hour_close)
        current_price = settled["exit_price"]
        entry = settled["entry_price"]
        pred = pos["predicted_dir"]
        actual = settled["actual_dir"]
        win = settled["win"]
        pnl = settled["pnl"]
        toplam_pnl += pnl
        state["balance"] = round(state["balance"] + pnl, 2)
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

        rec = {
            "symbol": pos["symbol"],
            "predicted_dir": pred,
            "actual_dir": actual,
            "win": win,
            "entry_price": entry,
            "exit_price": current_price,
            "entry_time_tr": pos["entry_time_tr"],
            "entry_hour_tr": pos["entry_hour_tr"],
            "entry_dow": pos["entry_dow"],
            "entry_is_weekend": pos["entry_is_weekend"],
            "amount": pos.get("amount") or _symbol_wr_amount(cfg, history, pos["symbol"]),
            "exit_time_tr": now_tr.isoformat(),
            "pnl": pnl,
            "algo_signal": pos.get("algo_signal"),
            "algo_name": pos.get("algo_name", cfg.algo_name),
            "algo_num": cfg.algo_num,
        }
        for k in ("pm_spent", "pm_size", "pm_entry_price", "to_win", "pm_slug",
                  "pm_fee", "pm_quote_src", "pm_mid_price",
                  "hot_hour_boost", "cold_hour_cut"):
            if pos.get(k) is not None:
                rec[k] = pos[k]
        history.append(rec)

        icon = "✅" if win else "❌"
        name = _sym_short(pos["symbol"])
        pct = (current_price - entry) / entry * 100
        pnl_str = f"+{pnl:.2f}$" if win else f"{pnl:.2f}$"
        lines.append(f"{icon} {name}  {pred}  {entry:.2f} → {current_price:.2f} ({pct:+.2f}%)  {pnl_str}")

    state["open_positions"] = failed
    _save_state(cfg, state)
    _save_history(cfg, history)

    if not lines:
        leftover = [p for p in failed if p.get("entry_hour_tr") != cur_hour]
        if leftover:
            print(f"[{cfg.label} close] {saat} — mum alınamadı, {len(leftover)} açık kaldı")
        return None

    total_pnl = state.get("total_pnl", 0.0)
    closed_all = len(history)
    win_all = sum(1 for t in history if t["win"])
    genel = f"%{win_all / closed_all * 100:.0f}" if closed_all else "—"
    saat_round = f"{int(saat[:2]):02d}:00"
    sep = "━" * 26
    block = (
        f"<b>{cfg.label}</b>\n"
        + "\n".join(lines)
        + f"\nBu tur: {'+' if toplam_pnl >= 0 else ''}{toplam_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{'🟢' if total_pnl >= 0 else '🔴'} Toplam P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all} işlem)"
    )
    if notify:
        msg = f"{sep}\n🏁 <b>{cfg.label} — {saat_round} Sonuçlar</b>\n{block}\n{sep}"
        tg_send_for_cfg(cfg, msg)
    print(f"[{cfg.label} close] {saat} — {len(lines)} pozisyon kapatıldı")
    return block if not notify else None


async def run_open(cfg: A2Config, *, notify: bool = True) -> str | None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    from pm_balance_guard import is_a2_live_dashboard_open
    if skip_if_weekend_pause("A2", "open", now_tr):
        if not is_a2_live_dashboard_open(cfg.algo_num):
            return None
    saat = now_tr.strftime("%H:%M")
    hour_tr = now_tr.hour
    dow = now_tr.weekday()
    is_weekend = dow >= 5

    state = _load_state(cfg)
    history = _load_history(cfg)
    sig_entry = _load_v2_signal(cfg.algo_num)
    if not sig_entry:
        print(f"[{cfg.label} open] {saat} — sinyal yok")
        return None

    candidates: list[dict] = []
    for sym in SYMBOLS:
        short = _sym_short(sym)
        direction = sig_entry.get(short)
        if direction not in ("UP", "DOWN"):
            print(f"[{cfg.label} open] {sym} — NEUTRAL, işlem yok")
            continue
        need_z = cfg.z_gate is not None or bool(cfg.shadow_log)
        try:
            klines = await _fetch_klines(sym, "1h", Z_PERIOD + 5 if need_z else 3)
            entry_price = klines[-2]["close"] if klines and len(klines) >= 2 else None
        except Exception:
            klines, entry_price = [], None
        if entry_price is None:
            continue
        candidates.append({
            "sym": sym,
            "direction": direction,
            "entry_price": entry_price,
            "z": entry_zscore(klines) if need_z else None,
        })

    already = {
        p.get("symbol")
        for p in state["open_positions"]
        if p.get("entry_hour_tr") == hour_tr
    }
    opened: list[dict] = []
    for c in candidates:
        if c["sym"] in already:
            print(f"[{cfg.label} open] {c['sym']} — bu saatte zaten açık, atlandı")
            continue
        sym = c["sym"]
        direction = c["direction"]
        dyn_amount, hot_boost, cold_cut = _resolve_trade_amount(cfg, history, sym, hour_tr)
        slot_amount_log(cfg.label, hour_tr, _symbol_wr_amount(cfg, history, sym), dyn_amount, hot_boost, cold_cut)
        pos = {
            "symbol": sym,
            "predicted_dir": direction,
            "entry_price": c["entry_price"],
            "entry_time_tr": now_tr.isoformat(),
            "entry_hour_tr": hour_tr,
            "entry_dow": dow,
            "entry_is_weekend": is_weekend,
            "amount": dyn_amount,
            "hot_hour_boost": hot_boost,
            "cold_hour_cut": cold_cut,
            "algo_signal": direction,
            "algo_name": cfg.algo_name,
            "algo_num": cfg.algo_num,
        }
        apply_pm_quote(pos, sym, direction, dyn_amount, datetime.now(timezone.utc))
        ok, skip_msg = pm_hourly_profit_entry_ok(pos)
        if not ok:
            print(f"[{cfg.label} open] {sym} — {skip_msg}")
            continue
        if cfg.min_entry_price is not None:
            entry_px = pos.get("pm_entry_price")
            if entry_px is None or float(entry_px) < cfg.min_entry_price:
                print(f"[{cfg.label} open] {sym} — bilet {entry_px} < "
                      f"{cfg.min_entry_price} fiyat tabanı, atlandı")
                continue
        if cfg.exclude_price_band is not None:
            band_lo, band_hi = cfg.exclude_price_band
            entry_px = pos.get("pm_entry_price")
            if entry_px is None or band_lo <= float(entry_px) < band_hi:
                print(f"[{cfg.label} open] {sym} — bilet {entry_px} "
                      f"[{band_lo}, {band_hi}) yasak bandında, atlandı")
                continue
        # z kapısı en sonda: gölge günlüğü yalnız diğer tüm kapıları geçmiş
        # slotları kaydetsin, yoksa "z olmasa açardık" okuması bozulur.
        zval = c.get("z")
        if cfg.z_gate is not None or cfg.shadow_log:
            z_lo, z_hi = cfg.z_gate or (None, None)
            in_gate = (
                zval is not None and z_lo is not None
                and z_lo <= abs(zval) < z_hi
            )
            _shadow_write(cfg, {
                "ts_tr": now_tr.isoformat(),
                "hour_tr": hour_tr,
                "symbol": sym,
                "direction": direction,
                "z": round(zval, 4) if zval is not None else None,
                "pm_price": pos.get("pm_entry_price"),
                "entry_price": c["entry_price"],
                "amount": dyn_amount,
                "taken": bool(in_gate) if cfg.z_gate is not None else True,
                "actual_dir": None,
                "win": None,
            })
            if cfg.z_gate is not None and not in_gate:
                zs = f"{zval:.2f}" if zval is not None else "yok"
                print(f"[{cfg.label} open] {sym} — |z| {zs} "
                      f"[{z_lo}, {z_hi}) kapısının dışında, atlandı")
                continue
        if zval is not None:
            pos["entry_z"] = round(zval, 4)
        state["open_positions"].append(pos)
        live_tag = ""
        try:
            from poly_a2_algo_live_core import get_live_spec, mirror_open_from_sanal
            # Türev defterler asıl defterin gerçek para aynasını tetiklemesin.
            live_spec = get_live_spec(cfg.algo_num) if cfg.live_mirror else None
            if live_spec:
                live_pos, live_err = await mirror_open_from_sanal(
                    live_spec, pos, entry_price=c["entry_price"], now_tr=now_tr,
                )
                if live_pos:
                    live_tag = "  🔴LIVE"
                elif live_err and live_err not in ("exists", "inactive"):
                    print(f"[{cfg.label} open] live mirror {sym}: {live_err}")
        except Exception as e:
            print(f"[{cfg.label} open] live mirror hata: {e}", file=sys.stderr)
        opened.append({
            **c,
            "pos": pos,
            "dyn_amount": dyn_amount,
            "hot_boost": hot_boost,
            "cold_cut": cold_cut,
            "live_tag": live_tag,
        })

    _save_state(cfg, state)

    if not opened:
        print(f"[{cfg.label} open] {saat} — işlem yok")
        return None

    next_h = f"{(hour_tr + 1) % 24:02d}:00"
    lines: list[str] = []
    for c in opened:
        sym = c["sym"]
        direction = c["direction"]
        name = _sym_short(sym)
        dir_icon = "📈" if direction == "UP" else "📉"
        dir_tr = "YÜKSELİR" if direction == "UP" else "DÜŞER"
        hour_wins, hour_total = get_stats(history, sym, hour_tr)
        sym_wins, sym_total = get_symbol_stats(history, sym)
        hot_boost = c["hot_boost"]
        cold_cut = c["cold_cut"]
        tags = ""
        if hot_boost:
            tags += "  🔥+%40"
        if cold_cut:
            tags += "  ❄️-%30"
        stake_line = pm_tg_stake(c["pos"])
        lines.append(
            f"{dir_icon} <b>{name}</b>  {dir_tr}  giriş:{c['entry_price']:.2f}  {stake_line}{tags}{c.get('live_tag', '')}\n"
            f"   🕐 {hour_tr:02d}:00→{next_h} İST başarı: {_wr(hour_wins, hour_total)}"
            f"  |  genel: {_wr(sym_wins, sym_total)}"
        )

    block = f"<b>{cfg.label}</b>\n" + "\n".join(lines) + f"\n💰 Bakiye: ${state['balance']:.2f}  |  📂 Açık: {len(state['open_positions'])} poz"
    if notify:
        sep = "━" * 26
        msg = (
            f"{sep}\n"
            f"🆕 <b>{cfg.label} — {saat} - {next_h} Yeni İşlemler</b>  🔶 SANAL\n"
            + "\n".join(lines)
            + f"\n{sep}\n"
            f"💰 Bakiye: ${state['balance']:.2f}  |  📂 Açık: {len(state['open_positions'])} poz\n"
            f"{sep}"
        )
        tg_send_for_cfg(cfg, msg)
    print(f"[{cfg.label} open] {saat} — {len(opened)} yeni işlem")
    return block if not notify else None


def run_weekly(cfg: A2Config) -> None:
    history = _load_history(cfg)
    state = _load_state(cfg)
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    total = len(history)
    if total == 0:
        tg_send_for_cfg(cfg, f"📊 <b>{cfg.label} HAFTALIK</b>\nHenüz veri yok.")
        return
    wins = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    _init = float(cfg.init_balance) if cfg.init_balance is not None else SANAL_INITIAL_BALANCE
    balance = state.get("balance", _init)
    tg_send_for_cfg(
        cfg,
        f"📊 <b>{cfg.label} HAFTALIK</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST\n"
        f"Toplam: {total} işlem  |  {_wr(wins, total)}\n"
        f"{'🟢' if total_pnl >= 0 else '🔴'} P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$  |  Bakiye: ${balance:.2f}"
    )


def run_weekly_all() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    lines = [f"📊 <b>A2 Top 17 — Haftalık Özet</b>", now_tr.strftime("%d.%m.%Y %H:%M") + " İST", "━" * 28]
    ranked: list[tuple[float, str]] = []
    for cfg in ALL_CONFIGS:
        history = _load_history(cfg)
        state = _load_state(cfg)
        total = len(history)
        if total == 0:
            continue
        wins = sum(1 for t in history if t["win"])
        wr = wins / total * 100
        pnl = state.get("total_pnl", 0.0)
        ranked.append((wr, f"  {'🟢' if wr >= 55 else '🟡' if wr >= 50 else '🔴'} {cfg.label}: %{wr:.0f} ({wins}/{total})  P&L {'+' if pnl >= 0 else ''}{pnl:.1f}$"))
    ranked.sort(key=lambda x: x[0], reverse=True)
    lines.extend(r for _, r in ranked)
    if len(lines) <= 3:
        lines.append("Henüz yeterli veri yok.")
    tg_send("\n".join(lines))


async def run_mode(mode: str, configs: list[A2Config] | None = None) -> None:
    cfgs = configs or ALL_CONFIGS
    batch = len(cfgs) > 1
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")
    sep = "━" * 26

    if mode == "close":
        blocks_a2: list[str] = []
        blocks_alfa: list[str] = []
        for cfg in cfgs:
            block = await run_close(cfg, notify=not batch)
            if not block:
                continue
            if cfg.algo_num in _A2_ALFA_CHANNEL_ALGOS:
                blocks_alfa.append(block)
            else:
                blocks_a2.append(block)
        if batch:
            saat_round = f"{int(saat[:2]):02d}:00"
            if blocks_a2:
                tg_send(
                    f"{sep}\n🏁 <b>A2 Top 17 — {saat_round} Sonuçlar</b>  🔶 SANAL\n\n"
                    + f"\n\n{sep}\n\n".join(blocks_a2)
                    + f"\n{sep}"
                )
            if blocks_alfa:
                tg_send_alfa_channel(
                    f"{sep}\n🏁 <b>A2 Top 3 — {saat_round} Sonuçlar</b>  🔶 SANAL\n\n"
                    + f"\n\n{sep}\n\n".join(blocks_alfa)
                    + f"\n{sep}"
                )
    elif mode == "open":
        from pm_balance_guard import is_a2_live_dashboard_open
        if skip_if_weekend_pause("A2", "open", now_tr):
            if not any(is_a2_live_dashboard_open(c.algo_num) for c in cfgs):
                return
        blocks_a2: list[str] = []
        blocks_alfa: list[str] = []
        for cfg in cfgs:
            block = await run_open(cfg, notify=not batch)
            if not block:
                continue
            if cfg.algo_num in _A2_ALFA_CHANNEL_ALGOS:
                blocks_alfa.append(block)
            else:
                blocks_a2.append(block)
        if batch:
            next_h = f"{(now_tr.hour + 1) % 24:02d}:00"
            if blocks_a2:
                tg_send(
                    f"{sep}\n🆕 <b>A2 Top 17 — {saat}-{next_h} Yeni İşlemler</b>  🔶 SANAL\n\n"
                    + f"\n\n{sep}\n\n".join(blocks_a2)
                    + f"\n{sep}"
                )
            if blocks_alfa:
                tg_send_alfa_channel(
                    f"{sep}\n🆕 <b>A2 Top 3 — {saat}-{next_h} Yeni İşlemler</b>  🔶 SANAL\n\n"
                    + f"\n\n{sep}\n\n".join(blocks_alfa)
                    + f"\n{sep}"
                )
    elif mode == "weekly":
        run_weekly_all()
        for cfg in cfgs:
            run_weekly(cfg)
    else:
        raise ValueError(f"Bilinmeyen mod: {mode}")
