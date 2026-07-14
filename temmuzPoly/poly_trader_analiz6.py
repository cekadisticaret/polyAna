"""
6. ANALİZ BTC-SOL — RSI Diverjansı (14) Katı sanal trader

Algoritma: algo_signals.rsi_divergence_strict (#38)
Semboller: BTCUSDT, SOLUSDT
Sanal bütçe: $500  |  İşlem: $10 (veri az) veya WR'ye göre $8 / $12 / $20

Modlar: close / open / weekly / stats
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from algo_signals import rsi_divergence_strict

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA")
CHAT_ID   = os.getenv("TELEGRAM_CHAT", "830754964")
_TZ_TR    = ZoneInfo("Europe/Istanbul")

_DIR         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(_DIR, "poly_trader_analiz6_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_analiz6_history.json")
WEEKLY_IMG   = "/tmp/poly_analiz6_weekly_heatmap.png"

LABEL            = "6. ANALİZ BTC-SOL"
ALGO_NAME        = "RSI Div (Katı)"
INITIAL_BALANCE  = 500.0
SYMBOLS          = ["BTCUSDT", "SOLUSDT"]
_DAYS_TR         = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_DAYS_FULL_TR    = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

TRADE_AMOUNT_DEFAULT = 10.0   # yeterli geçmiş yok
TRADE_AMOUNT_LOW     =  8.0   # WR < %45
TRADE_AMOUNT_MID     = 12.0   # WR %45–55
TRADE_AMOUNT_HIGH    = 20.0   # WR > %55
MIN_STAT_COUNT       = 5
_ENABLED             = os.getenv("ANALIZ6_ENABLED", "true").lower() in ("1", "true", "yes")


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


# ── Yardımcılar ───────────────────────────────────────────────
def _wr(wins: int, total: int) -> str:
    if total == 0:
        return "veri yok"
    return f"%{wins / total * 100:.0f} ({wins}/{total})"


def get_stats(history: list, symbol: str, hour_tr: int, dow: int | None = None) -> tuple[int, int]:
    trades = [
        t for t in history
        if t["symbol"] == symbol
        and t.get("entry_hour_tr") == hour_tr
        and (dow is None or t.get("entry_dow") == dow)
    ]
    return sum(1 for t in trades if t["win"]), len(trades)


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol]
    return sum(1 for t in trades if t["win"]), len(trades)


def calc_amount(history: list, symbol: str) -> float:
    wins, total = get_symbol_stats(history, symbol)
    if total < MIN_STAT_COUNT:
        return TRADE_AMOUNT_DEFAULT
    rate = wins / total
    if rate > 0.55:
        return TRADE_AMOUNT_HIGH
    if rate < 0.45:
        return TRADE_AMOUNT_LOW
    return TRADE_AMOUNT_MID


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
        print(f"[TG] Hata: {e}", file=sys.stderr)


def tg_send_photo(path: str, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(path, "rb") as f:
            img_data = f.read()
        boundary = "----Analiz6Boundary"
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
        print(f"[TG photo] Hata: {e}", file=sys.stderr)


def _binance_get(path: str, params: dict | None = None) -> list | dict:
    base = "https://fapi.binance.com"
    qs   = urllib.parse.urlencode(params or {})
    url  = f"{base}{path}?{qs}" if qs else f"{base}{path}"
    req  = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def fetch_klines(symbol: str, limit: int = 60) -> list[dict]:
    raw = _binance_get("/fapi/v1/klines", {"symbol": symbol, "interval": "1h", "limit": limit})
    return [{"open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
             "close": float(k[4]), "volume": float(k[5])} for k in raw]


def _algo_kl(klines: list[dict]) -> list[dict]:
    return [{"o": k["open"], "h": k["high"], "l": k["low"],
             "c": k["close"], "v": k["volume"]} for k in klines]


def analyze_symbol(symbol: str) -> dict | None:
    klines = fetch_klines(symbol, 60)
    if len(klines) < 20:
        return None
    signal = rsi_divergence_strict(_algo_kl(klines), lookback=10)
    if signal not in ("UP", "DOWN"):
        return None
    entry_price = klines[-2]["close"] if len(klines) >= 2 else klines[-1]["close"]
    return {
        "symbol": symbol,
        "direction": signal,
        "entry_price": entry_price,
        "rsi_zone": "aşırı alım" if signal == "DOWN" else "aşırı satım/diverjans",
    }


# ── CLOSE ─────────────────────────────────────────────────────
def run_close() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")

    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        tg_send(
            f"🤖 <b>{LABEL}</b> — {now_tr.strftime('%d.%m.%Y')} {saat} İST\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏸ Kapatılacak açık pozisyon yok."
        )
        print(f"[{LABEL} close] {saat} — açık pozisyon yok")
        return

    lines      = []
    toplam_pnl = 0.0
    failed_pos = []

    for pos in list(state["open_positions"]):
        try:
            klines = fetch_klines(pos["symbol"], 2)
            if not klines:
                failed_pos.append(pos)
                continue
            current_price = klines[-1]["close"]
        except Exception:
            failed_pos.append(pos)
            continue

        entry  = pos["entry_price"]
        pred   = pos["predicted_dir"]
        amount = pos.get("amount", TRADE_AMOUNT_DEFAULT)
        actual = "UP" if current_price >= entry else "DOWN"
        win    = pred == actual
        pnl    = amount if win else -amount
        toplam_pnl += pnl

        state["balance"]   = round(state["balance"] + pnl, 2)
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

        history.append({
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
            "algo":             ALGO_NAME,
        })

        icon    = "✅" if win else "❌"
        name    = pos["symbol"].replace("USDT", "")
        pct     = (current_price - entry) / entry * 100
        pnl_str = f"+{pnl:.0f}$" if win else f"{pnl:.0f}$"
        lines.append(f"{icon} {name}  {pred}  {entry:.2f} → {current_price:.2f} ({pct:+.2f}%)  {pnl_str}")

    state["open_positions"] = failed_pos
    if failed_pos:
        names = ", ".join(p["symbol"].replace("USDT", "") for p in failed_pos)
        tg_send(f"⚠️ <b>{LABEL}</b> — {names} fiyatı alınamadı, bir sonraki saate bırakıldı.")

    save_state(state)
    save_history(history)

    total_pnl  = state.get("total_pnl", 0.0)
    pnl_icon   = "🟢" if total_pnl >= 0 else "🔴"
    closed_all = len(history)
    win_all    = sum(1 for t in history if t["win"])
    genel      = f"%{win_all / closed_all * 100:.0f}" if closed_all else "—"
    saat_round = f"{int(saat[:2]):02d}:00"
    sep        = "━" * 26

    tg_send(
        f"{sep}\n"
        f"🏁 <b>{LABEL} — {saat_round} Sonuçlar</b>\n"
        f"🔬 {ALGO_NAME}\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+' if toplam_pnl >= 0 else ''}{toplam_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{pnl_icon} Toplam P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all} işlem)\n"
        f"{sep}"
    )
    print(f"[{LABEL} close] {saat} — {len(lines)} pozisyon kapatıldı")


# ── OPEN ──────────────────────────────────────────────────────
def run_open() -> None:
    if not _ENABLED:
        print(f"[{LABEL}] devre dışı (ANALIZ6_ENABLED=false)")
        return

    now        = datetime.now(timezone.utc)
    now_tr     = now.astimezone(_TZ_TR)
    hour_tr    = now_tr.hour
    dow        = now_tr.weekday()
    is_weekend = dow >= 5
    saat       = now_tr.strftime("%H:%M")
    next_h     = f"{(hour_tr + 1) % 24:02d}:00"

    state   = load_state()
    history = load_history()
    opened  = []

    for sym in SYMBOLS:
        try:
            sig = analyze_symbol(sym)
        except Exception as e:
            print(f"[{LABEL}] {sym} analiz hatası: {e}", file=sys.stderr)
            continue
        if sig is None:
            print(f"[{LABEL}] {sym} — sinyal yok (NEUTRAL)")
            continue

        amount = calc_amount(history, sym)
        state["open_positions"].append({
            "symbol":           sym,
            "predicted_dir":    sig["direction"],
            "entry_price":      sig["entry_price"],
            "entry_time_tr":    now_tr.isoformat(),
            "entry_hour_tr":    hour_tr,
            "entry_dow":        dow,
            "entry_is_weekend": is_weekend,
            "amount":           amount,
            "algo":             ALGO_NAME,
        })
        opened.append({**sig, "amount": amount})

    save_state(state)

    sep   = "━" * 26
    lines = []
    for sig in opened:
        sym = sig["symbol"]
        name = sym.replace("USDT", "")
        dir_icon = "📈" if sig["direction"] == "UP" else "📉"
        dir_tr   = "YÜKSELİR" if sig["direction"] == "UP" else "DÜŞER"
        hw, ht = get_stats(history, sym, hour_tr)
        sw, st = get_symbol_stats(history, sym)
        lines.append(
            f"{dir_icon} <b>{name}</b>  {dir_tr}  giriş:{sig['entry_price']:.2f}  💵{sig['amount']:.0f}$\n"
            f"   🔬 {ALGO_NAME}  |  🕐 {hour_tr:02d}:00→{next_h} {_wr(hw, ht)}  |  genel {_wr(sw, st)}"
        )

    at_risk = sum(p.get("amount", TRADE_AMOUNT_DEFAULT) for p in state["open_positions"])
    if lines:
        msg = (
            f"{sep}\n"
            f"🆕 <b>{LABEL} — {saat} → {next_h} Yeni İşlemler</b>\n"
            + "\n".join(lines) + "\n"
            f"{sep}\n"
            f"💰 Serbest: ${state['balance'] - at_risk:.2f}  |  📂 Açık: {len(state['open_positions'])} poz ${at_risk:.0f}  |  Toplam: ${state['balance']:.2f}\n"
            f"<i>Lot: veri az→${TRADE_AMOUNT_DEFAULT:.0f}  düşük WR→${TRADE_AMOUNT_LOW:.0f}  orta→${TRADE_AMOUNT_MID:.0f}  yüksek→${TRADE_AMOUNT_HIGH:.0f}</i>\n"
            f"{sep}"
        )
    else:
        msg = (
            f"{sep}\n"
            f"🆕 <b>{LABEL} — {saat} → {next_h}</b>\n"
            f"⏸ <i>Katı RSI diverjans koşulu sağlanmadı — işlem yok.</i>\n"
            f"💰 Bakiye: ${state['balance']:.2f}\n"
            f"{sep}"
        )

    tg_send(msg)
    print(f"[{LABEL} open] {saat} — {len(opened)} yeni işlem")


# ── WEEKLY ────────────────────────────────────────────────────
def run_weekly() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np

    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)

    grid_w = [[0] * 24 for _ in range(7)]
    grid_n = [[0] * 24 for _ in range(7)]
    for t in history:
        d, h = t.get("entry_dow"), t.get("entry_hour_tr")
        if d is None or h is None:
            continue
        grid_n[d][h] += 1
        if t["win"]:
            grid_w[d][h] += 1

    rate = np.full((7, 24), np.nan)
    for d in range(7):
        for h in range(24):
            if grid_n[d][h] >= 3:
                rate[d][h] = grid_w[d][h] / grid_n[d][h]

    fig, ax = plt.subplots(figsize=(16, 6))
    fig.patch.set_facecolor("#0a0e1a")
    ax.set_facecolor("#0a0e1a")
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "gy", [("#4a3000", 0), ("#f9a825", .3), ("#388e3c", .5), ("#00e676", 1)], N=256
    )
    cmap.set_bad("#141820")
    im = ax.imshow(np.ma.masked_invalid(rate), cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=7, color="#78909c")
    ax.set_yticks(range(7))
    ax.set_yticklabels(_DAYS_TR, fontsize=9, color="#b0bec5")
    for d in range(7):
        for h in range(24):
            if not np.isnan(rate[d][h]):
                ax.text(h, d, f"%{int(rate[d][h]*100)}\n({grid_n[d][h]})",
                        ha="center", va="center", fontsize=6,
                        color="white" if rate[d][h] >= 0.5 else "#1a1400", fontweight="bold")

    total = len(history)
    wins  = sum(1 for t in history if t["win"])
    genel = f"%{wins/total*100:.0f}" if total else "—"
    balance = state.get("balance", INITIAL_BALANCE)
    ax.set_title(
        f"{LABEL} — Haftalık Harita  |  {genel}  |  ${balance:.2f}",
        color="#4fc3f7", fontsize=10, fontweight="bold", pad=10,
    )
    plt.tight_layout()
    plt.savefig(WEEKLY_IMG, dpi=150, bbox_inches="tight", facecolor="#0a0e1a")
    plt.close()

    tg_send_photo(WEEKLY_IMG, f"📊 {LABEL} haftalık — {total} işlem {genel}")
    print(f"[{LABEL} weekly] gönderildi — {total} işlem")


# ── STATS ─────────────────────────────────────────────────────
def run_stats() -> None:
    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)

    if not history:
        tg_send(f"📊 <b>{LABEL} STATS</b>\nHenüz veri yok.")
        return

    total     = len(history)
    wins_all  = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"

    parts = [
        f"📊 <b>{LABEL} İSTATİSTİKLER</b>",
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"🔬 Algoritma: {ALGO_NAME}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Toplam: {total} işlem  |  {_wr(wins_all, total)}",
        f"{pnl_icon} P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}",
    ]

    for sym in SYMBOLS:
        name   = sym.replace("USDT", "")
        s_hist = [t for t in history if t["symbol"] == sym]
        if not s_hist:
            continue
        sw, st = sum(1 for t in s_hist if t["win"]), len(s_hist)
        avg_amt = sum(t.get("amount", TRADE_AMOUNT_DEFAULT) for t in s_hist) / len(s_hist)
        parts.append(f"\n📌 <b>{name}</b>  {_wr(sw, st)}  |  ort. lot ${avg_amt:.0f}")

    tg_send("\n".join(parts))
    print(f"[{LABEL} stats] gönderildi")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        run_close()
    elif mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        run_open()
