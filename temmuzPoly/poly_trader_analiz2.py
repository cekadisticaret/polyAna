"""
2. ANALİZ — Analiz 1 türevi (sanal)
Modlar:
  close   → saat başında  (0 * * * *): önceki saatin sonuçlarını kapatır, bildirir
  open    → 5 geçe        (5 * * * *): yeni tahmin, işlem açar (açılışta bakiye düşülür)
  preview → 45 geçe      (45 * * * *): bir sonraki saatin geçmiş başarı oranlarını bildirir
  weekly  → Cumartesi 21:00: haftalık ısı haritası
  stats   → manuel: detaylı başarı raporu

Algoritma: poly_predictor_analysis.py
Sanal bütçe: $300, işlem $12/$16/$20 (sembol WR — 1. Analiz mantığı).
Hacim filtresi yok. ALLOW_FALLBACK=False → sadece predict(); True ise ABD kapalıyken yedek RSI/MACD/EMA.
Gece modu kapalı. Hafta sonu duraklama: Cuma 22:00 – Pazar 18:00 İST (open/preview atlanır; close açık pozisyon varsa çalışır).
"""
import asyncio
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poly_predictor_analysis import predict, _fetch_klines, _rsi, _macd, _ema
from pm_trader_helpers import (
    apply_pm_quote, sanal_pnl, symbol_wr_amount, pm_hourly_profit_entry_ok,
    SANAL_INITIAL_BALANCE, SANAL_TRADE_AMOUNT,
    SANAL_TRADE_AMOUNT_HIGH, SANAL_TRADE_AMOUNT_LOW,
    pm_tg_stake, pm_stake_fields, pm_resolve_pnl,
    resolve_slot_trade_amount, slot_amount_log,
    skip_if_weekend_pause, resolve_open_slot_gates,
)

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")
_ET_ZONE  = ZoneInfo("America/New_York")

_DIR          = os.path.dirname(os.path.abspath(__file__))
STATE_FILE    = os.path.join(_DIR, "poly_trader_analiz2_state.json")
HISTORY_FILE  = os.path.join(_DIR, "poly_trader_analiz2_history.json")
WEEKLY_IMG    = "/tmp/poly_analiz2_weekly_heatmap.png"

INITIAL_BALANCE    = SANAL_INITIAL_BALANCE
TRADE_AMOUNT       = SANAL_TRADE_AMOUNT
TRADE_AMOUNT_HIGH  = SANAL_TRADE_AMOUNT_HIGH
TRADE_AMOUNT_LOW   = SANAL_TRADE_AMOUNT_LOW
SYMBOLS            = ["SOLUSDT"]
ALLOW_FALLBACK = False  # True: ABD kapalıyken RSI/MACD/EMA yedek; False: sadece predict()
_DAYS_TR        = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_DAYS_FULL_TR   = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


# ── State ─────────────────────────────────────────────────────
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


# ── İstatistik yardımcıları ───────────────────────────────────
def _wr(wins: int, total: int) -> str:
    if total == 0:
        return "veri yok"
    return f"%{wins/total*100:.0f} ({wins}/{total})"


def get_stats(history: list, symbol: str, hour_tr: int, dow: int | None = None) -> tuple[int, int]:
    """symbol + saat + isteğe bağlı gün bazlı istatistik: (wins, total)."""
    trades = [
        t for t in history
        if t["symbol"] == symbol
        and t.get("entry_hour_tr") == hour_tr
        and (dow is None or t.get("entry_dow") == dow)
    ]
    wins = sum(1 for t in trades if t["win"])
    return wins, len(trades)


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol]
    wins   = sum(1 for t in trades if t["win"])
    return wins, len(trades)


def _us_market_open(now: datetime) -> bool:
    """NYSE/NASDAQ normal seans: Pzt–Cum 09:30–16:00 ET."""
    et = now.astimezone(_ET_ZONE)
    if et.weekday() >= 5:
        return False
    mins = et.hour * 60 + et.minute
    return 9 * 60 + 30 <= mins < 16 * 60


@dataclass
class _FallbackPred:
    predicted_dir: str
    prob_up: float
    prob_down: float
    current_price: float
    rsi: float
    macd_bull: bool
    trend: str


async def _fallback_pred(symbol: str) -> _FallbackPred | None:
    """ABD kapalıyken predict() boş dönerse — RSI+MACD+EMA oy çoğunluğu."""
    klines = await _fetch_klines(symbol, "1h", 30)
    if len(klines) < 10:
        return None
    closes = [k["close"] for k in klines]
    current = closes[-1]
    rsi = _rsi(closes)
    macd_val, macd_sig = _macd(closes)
    ema9, ema21 = _ema(closes, 9)[-1], _ema(closes, 21)[-1]
    votes = [
        1 if rsi < 50 else -1,
        1 if macd_val > macd_sig else -1,
        1 if ema9 > ema21 else -1,
    ]
    direction = "UP" if sum(votes) > 0 else "DOWN"
    trend = "YUKARI" if ema9 > ema21 else "AŞAĞI" if ema9 < ema21 else "YATAY"
    conf = 0.55
    return _FallbackPred(
        predicted_dir=direction,
        prob_up=conf if direction == "UP" else 1 - conf,
        prob_down=1 - conf if direction == "UP" else conf,
        current_price=current,
        rsi=rsi,
        macd_bull=macd_val > macd_sig,
        trend=trend,
    )


async def _resolve_signal(symbol: str, us_open: bool) -> tuple[object | None, str]:
    """(pred, mode) — mode: standard | fallback | none."""
    pred = await predict(symbol)
    if pred is not None:
        return pred, "standard"
    if us_open or not ALLOW_FALLBACK:
        return None, "none"
    fb = await _fallback_pred(symbol)
    return (fb, "fallback") if fb else (None, "none")


def _stake(pos: dict) -> float:
    spent, _, _ = pm_stake_fields(pos)
    return spent


def _credit_on_close(state: dict, pos: dict, win: bool, pnl: float) -> None:
    """Açılışta düşülen stake: kazançta pm_size geri, kayıpta 0."""
    _, size, _ = pm_stake_fields(pos)
    if win and size > 0:
        state["balance"] = round(state["balance"] + size, 2)
    state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)


# ── Telegram ─────────────────────────────────────────────────
def tg_send(text: str) -> None:
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"
        }).encode()
        req = urllib.request.Request(url, data=body)
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception as e:
        print(f"[TG] Hata: {e}")


def tg_send_photo(path: str, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(path, "rb") as f:
            img_data = f.read()
        boundary = "----PolyBoundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{CHAT_ID}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"heatmap.png\"\r\nContent-Type: image/png\r\n\r\n"
        ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
    except Exception as e:
        print(f"[TG photo] Hata: {e}")


# ── CLOSE: Saat başı — önceki saatin sonuçlarını kapat ────────
async def run_close() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")
    if skip_if_weekend_pause("2. ANALİZ", "close", now_tr):
        return

    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        print(f"[2. ANALİZ close] {saat} İST — açık pozisyon yok")
        return

    lines      = []
    toplam_pnl = 0.0
    failed_pos = []

    for pos in list(state["open_positions"]):
        klines = await _fetch_klines(pos["symbol"], "1h", 2)
        if not klines:
            failed_pos.append(pos)
            continue
        current_price = klines[-1]["close"]

        entry  = pos["entry_price"]
        pred   = pos["predicted_dir"]
        amount = pos.get("amount", TRADE_AMOUNT)
        actual = "UP" if current_price >= entry else "DOWN"

        pm_win, pm_pnl, _ = pm_resolve_pnl(pos)
        if pm_win is not None:
            win = pm_win
            pnl = pm_pnl
        else:
            win = pred == actual
            pnl = sanal_pnl(pos, win)
        toplam_pnl += pnl

        _credit_on_close(state, pos, win, pnl)

        rec = {
            "symbol":           pos["symbol"],
            "predicted_dir":    pred,
            "actual_dir":       actual,
            "win":              win,
            "entry_price":      entry,
            "exit_price":       current_price,
            "entry_time_tr":    pos["entry_time_tr"],
            "entry_hour_tr":    pos["entry_hour_tr"],
            "entry_dow":        pos["entry_dow"],
            "entry_is_weekend": pos["entry_is_weekend"],
            "amount":           amount,
            "exit_time_tr":     now_tr.isoformat(),
            "pnl":              pnl,
            "pm_win":           pm_win if pm_win is not None else win,
            "ind_rsi_vote":     pos.get("ind_rsi_vote"),
            "ind_rsi_ok":       (pos.get("ind_rsi_vote") == actual) if pos.get("ind_rsi_vote") else None,
            "ind_macd_vote":    pos.get("ind_macd_vote"),
            "ind_macd_ok":      (pos.get("ind_macd_vote") == actual) if pos.get("ind_macd_vote") else None,
            "ind_ema_vote":     pos.get("ind_ema_vote"),
            "ind_ema_ok":       ((pos.get("ind_ema_vote") == actual)
                                 if pos.get("ind_ema_vote") and pos.get("ind_ema_vote") != "NEUTRAL"
                                 else None),
        }
        for k in ("pm_spent", "pm_size", "pm_entry_price", "to_win", "pm_slug"):
            if pos.get(k) is not None:
                rec[k] = pos[k]
        history.append(rec)

        icon    = "✅" if win else "❌"
        name    = pos["symbol"].replace("USDT", "")
        pct     = (current_price - entry) / entry * 100
        stake   = pm_tg_stake(pos) or f"💵 ${amount:.0f}"
        pnl_str = f"{'+' if pnl >= 0 else ''}{pnl:.2f}$"
        lines.append(
            f"{icon} {name}  {pred}  {entry:.2f} → {current_price:.2f} ({pct:+.2f}%)\n"
            f"   {stake}  net {pnl_str}"
        )

    state["open_positions"] = failed_pos

    if failed_pos:
        names = ", ".join(p["symbol"].replace("USDT", "") for p in failed_pos)
        print(f"[2. ANALİZ close] {saat} — fiyat alınamadı: {names}")
    save_state(state)
    save_history(history)

    if not lines:
        return

    total_pnl  = state.get("total_pnl", 0.0)
    pnl_icon   = "🟢" if total_pnl >= 0 else "🔴"
    closed_all = len(history)
    win_all    = sum(1 for t in history if t["win"])
    genel      = f"%{win_all/closed_all*100:.0f}" if closed_all else "—"
    saat_round = f"{int(saat[:2]):02d}:00"
    sep        = "━" * 26

    msg = (
        f"{sep}\n"
        f"🏁 <b>2. ANALİZ — {saat_round} Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+'if toplam_pnl>=0 else ''}{toplam_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{pnl_icon} Toplam P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all} işlem)\n"
        f"{sep}"
    )
    tg_send(msg)
    print(f"[2. ANALİZ close] {saat} İST — {len(lines)} pozisyon kapatıldı")


# ── OPEN: 5 geçe — yeni tahmin + pozisyon aç ─────────────────
async def run_open() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")

    hour_tr    = now_tr.hour
    dow        = now_tr.weekday()
    is_weekend = dow >= 5
    saat       = now_tr.strftime("%H:%M")
    tarih      = now_tr.strftime("%d.%m.%Y")

    state   = load_state()
    history = load_history()

    if skip_if_weekend_pause("2. ANALİZ", "open", now_tr, history=history):
        return
    cold_skip, _, _, _, cold_note = resolve_open_slot_gates(history, hour_tr, 0)
    if cold_skip:
        print(f"[2. ANALİZ open] {saat} — {cold_note} · işlem yok")
        return

    # ABD açık → Analiz 1 ile aynı; kapalı → ek yedek sinyal
    us_open = _us_market_open(now)
    opened  = []
    skipped = []

    for sym in SYMBOLS:
        pred_obj, sig_mode = await _resolve_signal(sym, us_open)
        if pred_obj is None:
            continue

        name = sym.replace("USDT", "")
        base_amount = symbol_wr_amount(history, sym)
        _sk, dyn_amount, hot_boost, cold_cut, gate_note = resolve_open_slot_gates(
            history, hour_tr, base_amount
        )
        if gate_note and hot_boost:
            print(f"[2. ANALİZ open] 🔥 {gate_note}")
        else:
            slot_amount_log("2. ANALİZ", hour_tr, base_amount, dyn_amount, hot_boost, cold_cut)

        try:
            klines = await _fetch_klines(sym, "1h", 3)
            entry_price = klines[-2]["close"] if klines and len(klines) >= 2 else pred_obj.current_price
        except Exception:
            entry_price = pred_obj.current_price

        ind_ema_raw = pred_obj.trend.upper()
        pos = {
            "symbol":           sym,
            "predicted_dir":    pred_obj.predicted_dir,
            "entry_price":      entry_price,
            "entry_time_tr":    now_tr.isoformat(),
            "entry_hour_tr":    hour_tr,
            "entry_dow":        dow,
            "entry_is_weekend": is_weekend,
            "amount":           dyn_amount,
            "hot_hour_boost":   hot_boost,
            "cold_hour_cut":    cold_cut,
            "signal_mode":      sig_mode,
            "us_market_open":   us_open,
            "ind_rsi_vote":     "UP" if pred_obj.rsi < 50 else "DOWN",
            "ind_rsi_val":      round(pred_obj.rsi, 1),
            "ind_macd_vote":    "UP" if pred_obj.macd_bull else "DOWN",
            "ind_ema_vote":     ("UP" if "YUKARI" in ind_ema_raw
                                 else "DOWN" if "AŞAĞI" in ind_ema_raw
                                 else "NEUTRAL"),
        }
        apply_pm_quote(pos, sym, pred_obj.predicted_dir, dyn_amount, now)
        ok, skip_msg = pm_hourly_profit_entry_ok(pos)
        if not ok:
            print(f"[2. ANALİZ open] {sym} — {skip_msg}")
            skipped.append(f"⏸ <b>{name}</b> — {skip_msg}")
            continue
        stake = _stake(pos)
        if state["balance"] < stake:
            print(f"[2. ANALİZ open] {sym} — yetersiz bakiye ${state['balance']:.2f} < ${stake:.0f}")
            continue
        state["balance"] = round(state["balance"] - stake, 2)
        state["open_positions"].append(pos)
        opened.append({
            "sym": sym, "pred_obj": pred_obj, "entry_price": entry_price,
            "pos": pos, "sig_mode": sig_mode,
        })

    save_state(state)

    next_h = f"{(hour_tr + 1) % 24:02d}:00"
    lines  = []
    for c in opened:
        sym      = c["sym"]
        pred_obj = c["pred_obj"]
        name     = sym.replace("USDT", "")
        conf     = max(pred_obj.prob_up, pred_obj.prob_down) * 100
        dir_icon = "📈" if pred_obj.predicted_dir == "UP" else "📉"
        dir_tr   = "YÜKSELİR" if pred_obj.predicted_dir == "UP" else "DÜŞER"
        hour_wins, hour_total = get_stats(history, sym, hour_tr)
        sym_wins,  sym_total  = get_symbol_stats(history, sym)
        pos         = c["pos"]
        entry_price = c["entry_price"]
        mode_tag    = "  🌙yedek" if c["sig_mode"] == "fallback" else ""
        pm_line     = pm_tg_stake(pos)
        spent, size, _ = pm_stake_fields(pos)
        if pm_line:
            pm_detail = f"   {pm_line}"
            if size > 0 and spent > 0:
                pm_detail += f"  (kazanırsa +${round(size - spent, 2):.2f})"
        else:
            pm_detail = f"   💵 ${pos.get('amount', TRADE_AMOUNT):.0f}  ⚠️ PM kotasyon alınamadı"
        lines.append(
            f"{dir_icon} <b>{name}</b>  {dir_tr}  konf:%{conf:.0f}  giriş:{entry_price:.2f}{mode_tag}\n"
            f"{pm_detail}\n"
            f"   🕐 {hour_tr:02d}:00→{next_h} İST başarı: {_wr(hour_wins, hour_total)}"
            f"  |  genel: {_wr(sym_wins, sym_total)}"
        )

    sep = "━" * 26
    sess_tag = "🇺🇸 ABD açık (Analiz 1 ile aynı)" if us_open else (
        "🌙 ABD kapalı (yedek sinyal)" if ALLOW_FALLBACK else "🌙 ABD kapalı (sadece standard — yedek kapalı)"
    )
    if not lines:
        print(f"[2. ANALİZ open] {saat} İST — işlem yok")
        return

    _at_risk = sum(p.get("pm_spent") or p.get("amount", TRADE_AMOUNT) for p in state["open_positions"])
    msg = (
        f"{sep}\n"
        f"🆕 <b>2. ANALİZ — {saat} - {next_h} Yeni İşlemler</b>  🔶 SANAL  {sess_tag}\n"
        f"<i>PM gamma kotasyonu — gerçek emir yok</i>\n"
        + "\n".join(lines)
        + (("\n" + "\n".join(skipped)) if skipped else "")
        + f"\n{sep}\n"
        f"💰 Bakiye: ${state['balance']:.2f}  |  📂 Açık: {len(state['open_positions'])} poz ${_at_risk:.0f} riskte\n"
        f"{sep}"
    )

    tg_send(msg)
    print(f"[2. ANALİZ open] {saat} İST — {len(lines)} açıldı")


# ── PREVIEW: 45 geçe — bir sonraki saatin başarı oranı önizleme
def run_preview() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    if skip_if_weekend_pause("2. ANALİZ", "preview", now_tr):
        return
    next_hour = (now_tr.hour + 1) % 24
    dow       = now_tr.weekday()
    gun_tr    = _DAYS_FULL_TR[dow]
    tarih     = now_tr.strftime("%d.%m.%Y")
    history   = load_history()

    lines = []
    for sym in SYMBOLS:
        name = sym.replace("USDT", "")

        # Bu gün + bu saat kombinasyonu
        dow_wins, dow_total = get_stats(history, sym, next_hour, dow)
        # Genel saat istatistiği (tüm günler)
        all_wins, all_total = get_stats(history, sym, next_hour)

        if all_total == 0:
            oran_str = "henüz veri yok"
            icon = "⚪"
        else:
            oran = all_wins / all_total * 100
            icon = "🟢" if oran >= 60 else "🟡" if oran >= 50 else "🔴"

            if dow_total >= 3:
                dow_oran = dow_wins / dow_total * 100
                oran_str = f"%{dow_oran:.0f} ({gun_tr})  |  genel %{oran:.0f}"
            else:
                oran_str = f"genel %{oran:.0f} ({all_total} işlem)"

        lines.append(f"{icon} <b>{name}</b>  {next_hour:02d}:00 İST  {oran_str}")

    sep = "━" * 26
    msg = (
        f"🔭 <b>2. ANALİZ — {tarih} {next_hour:02d}:00 İST ÖNİZLEME</b>\n{sep}\n"
        + "\n".join(lines) +
        f"\n{sep}\n"
        f"<i>Geçmiş başarı oranları — 05'te işlem açılacak</i>"
    )
    print(msg.replace("<b>", "").replace("</b>", ""))
    print(f"[2. ANALİZ preview] {now_tr.strftime('%H:%M')} İST — {next_hour:02d}:00 önizleme (TG atlanıyor)")


# ── WEEKLY: Pazar 00:00 — ısı haritası görseli ───────────────
def run_weekly() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np

    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)

    # 7 gün x 24 saat grid: (wins, total) — tüm semboller birleşik
    grid_w = [[0]*24 for _ in range(7)]
    grid_n = [[0]*24 for _ in range(7)]
    # Sembol bazlı grid: {sym: [[wins], [total]]}
    sym_names = [s.replace("USDT", "") for s in SYMBOLS]
    grid_sym  = {s: {"w": [[0]*24 for _ in range(7)], "n": [[0]*24 for _ in range(7)]} for s in sym_names}
    for t in history:
        d = t.get("entry_dow")
        h = t.get("entry_hour_tr")
        if d is None or h is None:
            continue
        grid_n[d][h] += 1
        if t["win"]:
            grid_w[d][h] += 1
        sn = t["symbol"].replace("USDT", "")
        if sn in grid_sym:
            grid_sym[sn]["n"][d][h] += 1
            if t["win"]:
                grid_sym[sn]["w"][d][h] += 1

    # Oran matrisi (NaN = veri yok)
    rate = np.full((7, 24), np.nan)
    for d in range(7):
        for h in range(24):
            if grid_n[d][h] >= 3:
                rate[d][h] = grid_w[d][h] / grid_n[d][h]

    fig, ax = plt.subplots(figsize=(16, 7))
    fig.patch.set_facecolor("#0a0e1a")
    ax.set_facecolor("#0a0e1a")

    # Sarı (<50%) → Yeşil (≥50%) renk skalası
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "gy_dual",
        [
            (0.00, "#4a3000"),
            (0.20, "#f9a825"),
            (0.30, "#fff176"),
            (0.31, "#388e3c"),
            (0.65, "#1b5e20"),
            (1.00, "#00e676"),
        ],
        N=256
    )
    cmap.set_bad(color="#141820")  # veri yok → koyu gri

    masked = np.ma.masked_invalid(rate)
    im = ax.imshow(masked, cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")

    # Eksler
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=7, color="#78909c")
    ax.set_yticks(range(7))
    ax.set_yticklabels(_DAYS_TR, fontsize=9, color="#b0bec5", fontweight="bold")
    ax.tick_params(length=0)

    # Hücre içine yüzde + sembol dağılımı yaz
    for d in range(7):
        for h in range(24):
            if not np.isnan(rate[d][h]):
                pct  = int(rate[d][h] * 100)
                n    = grid_n[d][h]
                clr  = "white" if rate[d][h] >= 0.50 else "#1a1400"
                sym_parts = []
                for sn in sym_names:
                    sw = grid_sym[sn]["w"][d][h]
                    sn_total = grid_sym[sn]["n"][d][h]
                    if sn_total > 0:
                        sym_parts.append(f"{sn}:+{sw}-{sn_total - sw}")
                sym_str = "\n".join(sym_parts)
                ax.text(h, d, f"%{pct}({n})\n{sym_str}", ha="center", va="center",
                        fontsize=5, color=clr, fontweight="bold", linespacing=1.5)

    # Izgara çizgileri
    for x in range(25):
        ax.axvline(x - 0.5, color="#0a0e1a", linewidth=0.5)
    for y in range(8):
        ax.axhline(y - 0.5, color="#0a0e1a", linewidth=0.5)

    # Başlık & colorbar
    total = len(history)
    wins  = sum(1 for t in history if t["win"])
    genel = f"%{wins/total*100:.0f}" if total else "—"
    balance = state.get("balance", INITIAL_BALANCE)
    total_pnl = state.get("total_pnl", 0.0)

    # Sembol bazlı istatistik
    sym_stats = []
    for sym in SYMBOLS:
        name = sym.replace("USDT", "")
        sym_trades = [t for t in history if t["symbol"] == sym]
        sym_wins   = sum(1 for t in sym_trades if t["win"])
        if sym_trades:
            sym_stats.append(f"{name}: {len(sym_trades)} işlem / {sym_wins} başarılı (%{sym_wins/len(sym_trades)*100:.0f})")
    sym_line = "   |   ".join(sym_stats)

    ax.set_title(
        f"2. ANALİZ — Haftalık Başarı Haritası  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
        f"Toplam: {total} işlem  |  {genel}  |  Bakiye: ${balance:.2f}  |  P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$\n"
        f"{sym_line}",
        color="#4fc3f7", fontsize=9, fontweight="bold", pad=10
    )
    ax.set_xlabel("Saat (İST)", color="#546e7a", fontsize=8)

    cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
    cbar.ax.yaxis.set_tick_params(color="#546e7a")
    cbar.set_label("Başarı Oranı", color="#546e7a", fontsize=8)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="#546e7a", fontsize=7)
    cbar.set_ticks([0.4, 0.5, 0.6, 0.7, 0.8])
    cbar.set_ticklabels(["%40", "%50", "%60", "%70", "%80"])

    plt.tight_layout(pad=1.2)
    plt.savefig(WEEKLY_IMG, dpi=150, bbox_inches="tight",
                facecolor="#0a0e1a", pad_inches=0.1)
    plt.close()

    caption = (
        f"📊 2. ANALİZ Haftalık Rapor — {now_tr.strftime('%d.%m.%Y %H:%M İST')}\n"
        f"Toplam {total} işlem | {genel} başarı | ${balance:.2f}"
    )
    tg_send_photo(WEEKLY_IMG, caption)

    ind_lines = _ind_stats_lines(history)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    tg_send(
        f"📊 <b>2. ANALİZ HAFTALIK İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {genel} başarı\n"
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${balance:.2f}\n"
        f"\n🔬 <b>Algoritma İsabet Oranı</b>\n" + "\n".join(ind_lines)
    )
    print(f"[2. ANALİZ weekly] haftalık görsel gönderildi — {total} işlem")


# ── İndikatör isabet yardımcısı ───────────────────────────────
def _ind_stats_lines(history: list) -> list[str]:
    checks = [("RSI", "ind_rsi_ok"), ("MACD", "ind_macd_ok"), ("EMA", "ind_ema_ok")]
    lines = []
    for label, key in checks:
        vals = [t[key] for t in history if t.get(key) is not None]
        if vals:
            w   = sum(1 for v in vals if v)
            n   = len(vals)
            bar = "🟢" if w / n >= 0.6 else "🟡" if w / n >= 0.5 else "🔴"
            lines.append(f"  {bar} {label}: {_wr(w, n)}")
        else:
            lines.append(f"  ⚪ {label}: veri yok")
    return lines


# ── STATS: Manuel detaylı rapor ──────────────────────────────
def run_stats() -> None:
    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)

    if not history:
        tg_send("📊 <b>2. ANALİZ STATS</b>\nHenüz veri yok.")
        return

    total    = len(history)
    wins_all = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"

    parts = [
        f"📊 <b>2. ANALİZ İSTATİSTİKLER</b>",
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Toplam: {total} işlem  |  {_wr(wins_all, total)}",
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}",
        f"\n🔬 <b>İndikatör İsabet Oranı</b>",
        *_ind_stats_lines(history),
    ]

    wd = [t for t in history if not t.get("entry_is_weekend")]
    we = [t for t in history if t.get("entry_is_weekend")]
    if wd or we:
        parts.append(f"\n📅 <b>Hafta İçi vs Hafta Sonu</b>")
        if wd:
            parts.append(f"  Hafta içi : {_wr(sum(1 for t in wd if t['win']), len(wd))}")
        if we:
            parts.append(f"  Hafta sonu: {_wr(sum(1 for t in we if t['win']), len(we))}")

    for sym in SYMBOLS:
        name   = sym.replace("USDT", "")
        s_hist = [t for t in history if t["symbol"] == sym]
        if not s_hist:
            continue
        sw, st = sum(1 for t in s_hist if t["win"]), len(s_hist)
        parts.append(f"\n📌 <b>{name}</b>  genel: {_wr(sw, st)}")

        hour_data: dict[int, list] = {}
        for t in s_hist:
            h = t.get("entry_hour_tr")
            if h is None:
                continue
            hour_data.setdefault(h, [0, 0])
            hour_data[h][1] += 1
            if t["win"]:
                hour_data[h][0] += 1

        rows = [(h, w, n) for h, (w, n) in hour_data.items() if n >= 3]
        rows.sort(key=lambda x: x[1]/x[2], reverse=True)
        for h, w, n in rows[:5]:
            bar = "🟢" if w/n >= 0.6 else "🟡" if w/n >= 0.5 else "🔴"
            parts.append(f"  {bar} {h:02d}:00 İST  {_wr(w, n)}")

        sym_wd = [t for t in s_hist if not t.get("entry_is_weekend")]
        sym_we = [t for t in s_hist if t.get("entry_is_weekend")]
        if sym_wd and sym_we:
            parts.append(
                f"  📅 Hafta içi {_wr(sum(1 for t in sym_wd if t['win']), len(sym_wd))}"
                f"  |  Sonu {_wr(sum(1 for t in sym_we if t['win']), len(sym_we))}"
            )

    parts.append(f"\n📆 <b>Gün Bazlı</b>")
    dow_data: dict[int, list] = {}
    for t in history:
        d = t.get("entry_dow")
        if d is None:
            continue
        dow_data.setdefault(d, [0, 0])
        dow_data[d][1] += 1
        if t["win"]:
            dow_data[d][0] += 1

    for d in range(7):
        if d not in dow_data:
            continue
        w, n = dow_data[d]
        bar = "🟢" if w/n >= 0.6 else "🟡" if w/n >= 0.5 else "🔴"
        wk  = "📅" if d < 5 else "🏖"
        parts.append(f"  {wk}{bar} {_DAYS_TR[d]}  {_wr(w, n)}")

    tg_send("\n".join(parts))
    print("[2. ANALİZ stats] gönderildi")


# ── Giriş noktası ─────────────────────────────────────────────
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        asyncio.run(run_close())
    elif mode == "preview":
        run_preview()
    elif mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        asyncio.run(run_open())
