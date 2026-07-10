"""
8. ANALİZ — MR + OrderFlow + RSI Sanal Trader

3 bağımsız algoritmanın oylarını birleştirerek sinyal üretir:
  1. RSI          → RSI(14) oversold/overbought sinyali
  2. MR           → Mean Reversion: RSI(14) + Bollinger Bands(20,2)
  3. OrderFlow    → CVD yaklaşımı + Order Book imbalance

Oy sistemi (her algoritma +1/−1/0):
  |toplam| == 3  →  $20 işlem
  |toplam| == 2  →  $12 işlem
  |toplam| <= 1  →  işlem açılmaz

Modlar: close / open / weekly / stats

Cron:
  0 * * * 1-7   close  (saat başı)
  8 * * * 1-7   open   (8 geçe)
  0 21 * * 6    weekly (Pazar 00:00 İST)
"""
import asyncio
import json
import math
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")

_DIR          = os.path.dirname(os.path.abspath(__file__))
STATE_FILE    = os.path.join(_DIR, "poly_trader_analiz8_state.json")
HISTORY_FILE  = os.path.join(_DIR, "poly_trader_analiz8_history.json")
WEEKLY_IMG    = "/tmp/poly_analiz8_weekly_heatmap.png"

INITIAL_BALANCE = 300.0
AMOUNT_HIGH     = 16.0   # |skor| == 3 (tüm algoritmalar aynı yön)
AMOUNT_STRONG   = 12.0   # |skor| == 2
AMOUNT_MODERATE =  8.0   # |skor| == 1
SYMBOLS         = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
MIN_STAT_COUNT  = 3
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


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol]
    return sum(1 for t in trades if t["win"]), len(trades)


def _vote_ok(vote: int, actual: str) -> bool | None:
    if vote == 0:
        return None
    return (vote > 0) == (actual == "UP")


# ── Telegram ──────────────────────────────────────────────────
def tg_send(text: str) -> None:
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception as e:
        print(f"[TG] Hata: {e}")


def tg_send_photo(path: str, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(path, "rb") as f:
            img_data = f.read()
        boundary = "----Analiz8Boundary"
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


# ── Binance veri çekme ────────────────────────────────────────
def _binance_get(path: str, params: dict | None = None) -> dict | list:
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


def fetch_orderbook(symbol: str) -> dict:
    return _binance_get("/fapi/v1/depth", {"symbol": symbol, "limit": 20})


# ── Teknik hesaplamalar ───────────────────────────────────────
def _ema(vals: list[float], n: int) -> list[float]:
    if not vals:
        return []
    k = 2 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    diffs  = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [max(d, 0) for d in diffs]
    losses = [max(-d, 0) for d in diffs]
    ag     = sum(gains[-period:]) / period
    al     = sum(losses[-period:]) / period
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def _bollinger(closes: list[float], period: int = 20, mult: float = 2.0) -> tuple[float, float, float]:
    w   = closes[-period:] if len(closes) >= period else closes
    mid = sum(w) / len(w)
    std = math.sqrt(sum((x - mid) ** 2 for x in w) / len(w))
    return mid + mult * std, mid, mid - mult * std


# ── 3 Algoritma ───────────────────────────────────────────────

def algo_rsi(klines: list[dict]) -> tuple[int, str]:
    """RSI(14) — sadece aşırı bölgelerde sinyal (nötr bölge = nötr oy)."""
    closes = [k["close"] for k in klines]
    rsi    = _rsi(closes, 14)
    rsi_prev = _rsi(closes[:-3], 14) if len(closes) > 17 else rsi
    recovering = rsi > rsi_prev  # oversold'dan toparlanıyor mu?

    if rsi <= 30:
        vote = +1
        arr  = "↑"
    elif rsi <= 40 and recovering:
        vote = +1
        arr  = "↑~"
    elif rsi >= 70:
        vote = -1
        arr  = "↓"
    elif rsi >= 60 and not recovering:
        vote = -1
        arr  = "↓~"
    else:
        vote = 0
        arr  = "→"
    return vote, f"RSI {arr}  {rsi:.0f}"


def algo_mr(klines: list[dict]) -> tuple[int, str]:
    """Mean Reversion — RSI(14) + Bollinger Bands(20,2) + EMA trend filtresi."""
    closes      = [k["close"] for k in klines]
    rsi         = _rsi(closes, 14)
    upper, mid, lower = _bollinger(closes, 20, 2.0)
    price       = closes[-1]
    ema20       = _ema(closes, 20)
    ema50       = _ema(closes, 50) if len(closes) >= 50 else ema20
    trend_up    = ema20[-1] > ema50[-1]
    trend_down  = ema20[-1] < ema50[-1]

    # Sadece BB bandına dokunuş + RSI onayı ile sinyal
    at_lower = price <= lower * 1.005  # alt banda yakın/altında
    at_upper = price >= upper * 0.995  # üst banda yakın/üstünde

    if at_lower and rsi <= 45 and trend_up:
        vote, lbl = +1, "alt-band+trend↑"
    elif at_lower and rsi <= 40:
        vote, lbl = +1, "alt-band aşırı"
    elif at_upper and rsi >= 55 and trend_down:
        vote, lbl = -1, "üst-band+trend↓"
    elif at_upper and rsi >= 60:
        vote, lbl = -1, "üst-band aşırı"
    else:
        vote, lbl = 0, "orta"

    arr = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    return vote, f"MR {arr}  RSI:{rsi:.0f}  BB:{lbl}"


def algo_orderflow(klines: list[dict], ob: dict) -> tuple[int, str]:
    """OrderFlow — CVD + Order Book imbalance."""
    window    = klines[-20:]
    cvd_delta = sum(k["volume"] if k["close"] >= k["open"] else -k["volume"] for k in window)
    total_vol = sum(k["volume"] for k in window) or 1
    cvd_r     = cvd_delta / total_vol

    bids  = sum(float(b[1]) for b in ob.get("bids", [])[:10])
    asks  = sum(float(a[1]) for a in ob.get("asks", [])[:10])
    ob_r  = (bids - asks) / (bids + asks) if (bids + asks) else 0

    cvd_v = +1 if cvd_r > 0.08 else -1 if cvd_r < -0.08 else 0
    ob_v  = +1 if ob_r  > 0.15 else -1 if ob_r  < -0.15 else 0

    vote  = cvd_v if cvd_v == ob_v else (cvd_v or ob_v)
    arr   = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    return vote, f"OF {arr}  CVD:{cvd_r:+.2f}  OB:{ob_r:+.2f}"


# ── Tam sembol analizi ────────────────────────────────────────
def analyze(symbol: str) -> dict | None:
    try:
        klines = fetch_klines(symbol, 60)
        ob     = fetch_orderbook(symbol)
    except Exception as e:
        print(f"[8. ANALİZ] {symbol} veri hatası: {e}", file=sys.stderr)
        return None

    v1, l1 = algo_rsi(klines)
    v2, l2 = algo_mr(klines)
    v3, l3 = algo_orderflow(klines, ob)
    score  = v1 + v2 + v3

    amount = (AMOUNT_HIGH     if abs(score) == 3
              else AMOUNT_STRONG   if abs(score) == 2
              else AMOUNT_MODERATE if abs(score) == 1
              else 0.0)
    direction = "UP" if score > 0 else "DOWN" if score < 0 else None

    return {
        "symbol":    symbol,
        "score":     score,
        "amount":    amount,
        "direction": direction,
        "price":     klines[-1]["close"],
        "votes":     [v1, v2, v3],
        "labels":    [l1, l2, l3],
    }


# ── CLOSE ──────────────────────────────────────────────────────
def run_close() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")

    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        print(f"[8. ANALİZ close] {saat} İST — açık pozisyon yok")
        return

    lines = []
    for pos in list(state["open_positions"]):
        try:
            klines = fetch_klines(pos["symbol"], 2)
        except Exception as e:
            print(f"[8. ANALİZ close] {pos['symbol']} fiyat hatası: {e}", file=sys.stderr)
            continue

        current_price = klines[-1]["close"]
        entry  = pos["entry_price"]
        pred   = pos["predicted_dir"]
        amount = pos.get("amount", AMOUNT_MODERATE)
        actual = "UP" if current_price >= entry else "DOWN"
        win    = (pred == actual)

        pnl = amount * 0.9 if win else -amount
        state["balance"] += pnl
        state["total_pnl"] = state.get("total_pnl", 0.0) + pnl

        vs = pos.get("votes", [])
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
            "score":            pos.get("score", 0),
            "amount":           amount,
            "pnl":              round(pnl, 2),
            "exit_time_tr":     now_tr.isoformat(),
            "ind_rsi_ok":       _vote_ok(vs[0], actual) if len(vs) > 0 else None,
            "ind_mr_ok":        _vote_ok(vs[1], actual) if len(vs) > 1 else None,
            "ind_of_ok":        _vote_ok(vs[2], actual) if len(vs) > 2 else None,
        })

        icon = "✅" if win else "❌"
        name = pos["symbol"].replace("USDT", "")
        pct  = (current_price - entry) / entry * 100
        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        lines.append(
            f"{icon} {name}  {pred}  {entry:.2f} → {current_price:.2f} ({pct:+.2f}%)  "
            f"skor:{pos.get('score',0):+d}/3  {pnl_str}"
        )

    state["open_positions"] = []
    save_state(state)
    save_history(history)

    if not lines:
        return

    total = len(history)
    wins  = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    sep = "━" * 26
    tg_send(
        f"{sep}\n"
        f"🏁 <b>8. ANALİZ TERS SİSTEM — {saat} Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"{pnl_icon} P&L bu tur: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"Genel: {_wr(wins, total)}\n"
        f"{sep}"
    )
    print(f"[8. ANALİZ close] {saat} İST — {len(lines)} pozisyon kapatıldı")


# ── OPEN ───────────────────────────────────────────────────────
def run_open() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    hour_tr    = now_tr.hour
    dow        = now_tr.weekday()
    is_weekend = dow >= 5
    saat       = now_tr.strftime("%H:%M")

    state   = load_state()
    history = load_history()

    results = []
    for sym in SYMBOLS:
        sig = analyze(sym)
        if sig:
            results.append(sig)
        time.sleep(0.4)

    # Ters sinyal: algoritmanın dediğinin tersini al (test sistemi)
    for r in results:
        if r["direction"] == "UP":
            r["direction"] = "DOWN"
        elif r["direction"] == "DOWN":
            r["direction"] = "UP"

    tradeable = [r for r in results if r["amount"] > 0 and r["direction"]]

    if not tradeable:
        total = len(history)
        wins  = sum(1 for t in history if t["win"])
        tg_send(
            f"⏸ <b>8. ANALİZ TERS SİSTEM — {saat} İST</b>\n"
            f"Güçlü sinyal yok (RSI+MR+OF konsensüs gerekli)\n"
            f"📊 Genel: {_wr(wins, total)}  |  💰 ${state['balance']:.2f}"
        )
        print(f"[8. ANALİZ open] {saat} İST — işlem sinyali yok")
        return

    lines = []
    for sig in tradeable:
        pos = {
            "symbol":           sig["symbol"],
            "predicted_dir":    sig["direction"],
            "entry_price":      sig["price"],
            "entry_time_tr":    now_tr.isoformat(),
            "entry_hour_tr":    hour_tr,
            "entry_dow":        dow,
            "entry_is_weekend": is_weekend,
            "score":            sig["score"],
            "amount":           sig["amount"],
            "votes":            sig["votes"],
        }
        state["open_positions"].append(pos)
        state["balance"] -= sig["amount"]

        name   = sig["symbol"].replace("USDT", "")
        arr    = "🔺" if sig["direction"] == "UP" else "🔻"
        s_icon = "💪" if abs(sig["score"]) == 3 else "⚡"
        lines.append(
            f"{arr} {name}  {sig['direction']}  ${sig['price']:.2f}  "
            f"skor:{sig['score']:+d}/3  ${sig['amount']:.0f}  {s_icon}"
        )
        for lbl in sig["labels"]:
            lines.append(f"   └ {lbl}")

    save_state(state)

    total = len(history)
    wins  = sum(1 for t in history if t["win"])
    day_lbl = _DAYS_FULL_TR[dow]
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    sep = "━" * 26

    tg_send(
        f"{sep}\n"
        f"🔬 <b>8. ANALİZ TERS SİSTEM — {saat} İST</b>  ({day_lbl})\n"
        f"<b>RSI + MR + OrderFlow</b>\n"
        + "\n".join(lines) + "\n"
        f"{sep}\n"
        f"{pnl_icon} Bakiye: ${state['balance']:.2f}  |  📊 {_wr(wins, total)}"
    )
    print(f"[8. ANALİZ open] {saat} İST — {len(tradeable)} işlem açıldı")


# ── İndikatör isabet yardımcısı ───────────────────────────────
def _ind_stats_lines(history: list) -> list[str]:
    checks = [("RSI", "ind_rsi_ok"), ("MR", "ind_mr_ok"), ("OF", "ind_of_ok")]
    lines  = []
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


# ── WEEKLY ─────────────────────────────────────────────────────
def run_weekly() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np
    from collections import defaultdict

    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)

    if not history:
        tg_send("📊 <b>8. ANALİZ TERS SİSTEM HAFTALIK</b>\nHenüz veri yok.")
        return

    days  = _DAYS_TR
    hours = list(range(0, 24))
    rate  = defaultdict(lambda: defaultdict(lambda: float("nan")))
    grid_sym = {s.replace("USDT", ""): {"w": defaultdict(lambda: defaultdict(int)),
                                          "n": defaultdict(lambda: defaultdict(int))}
                for s in SYMBOLS}

    for t in history:
        h  = t.get("entry_hour_tr")
        d  = t.get("entry_dow")
        sn = t["symbol"].replace("USDT", "")
        if h is not None and d is not None:
            if "win" in t:
                vals = rate[d][h]
                if isinstance(vals, float) and math.isnan(vals):
                    rate[d][h] = []
                rate[d][h].append(1 if t["win"] else 0)
            grid_sym[sn]["n"][d][h] += 1
            if t.get("win"):
                grid_sym[sn]["w"][d][h] += 1

    data   = np.full((7, 24), np.nan)
    counts = np.zeros((7, 24), dtype=int)
    for d in range(7):
        for h in range(24):
            vals = rate[d][h]
            if isinstance(vals, list):
                counts[d][h] = len(vals)
                if len(vals) >= MIN_STAT_COUNT:
                    data[d][h] = sum(vals) / len(vals)

    total     = len(history)
    wins_all  = sum(1 for t in history if t["win"])
    genel     = _wr(wins_all, total)
    balance   = state.get("balance", INITIAL_BALANCE)
    total_pnl = state.get("total_pnl", 0.0)
    sym_names = [s.replace("USDT", "") for s in SYMBOLS]

    sym_stats = []
    for sym in SYMBOLS:
        name = sym.replace("USDT", "")
        sym_trades = [t for t in history if t["symbol"] == sym]
        sym_wins   = sum(1 for t in sym_trades if t["win"])
        if sym_trades:
            sym_stats.append(f"{name}: {len(sym_trades)} işlem / {sym_wins} başarılı (%{sym_wins/len(sym_trades)*100:.0f})")
    sym_line = "   |   ".join(sym_stats)

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

    fig, ax = plt.subplots(figsize=(16, 7))
    fig.patch.set_facecolor("#0a0e1a")
    ax.set_facecolor("#0d1117")

    im = ax.imshow(data, cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in hours], fontsize=7, color="#546e7a")
    ax.set_yticks(range(7))
    ax.set_yticklabels(days, fontsize=9, color="#b0bec5")

    for d in range(7):
        for h in range(24):
            if not np.isnan(data[d][h]):
                pct  = int(data[d][h] * 100)
                n    = counts[d][h]
                clr  = "white" if data[d][h] >= 0.50 else "#1a1400"
                sym_parts = []
                for sn in sym_names:
                    sw       = grid_sym[sn]["w"][d][h]
                    sn_total = grid_sym[sn]["n"][d][h]
                    if sn_total > 0:
                        sym_parts.append(f"{sn}:+{sw}-{sn_total - sw}")
                sym_str = "\n".join(sym_parts)
                ax.text(h, d, f"%{pct}({n})\n{sym_str}", ha="center", va="center",
                        fontsize=5, color=clr, fontweight="bold", linespacing=1.5)

    for x in range(25):
        ax.axvline(x - 0.5, color="#0a0e1a", linewidth=0.5)
    for y in range(8):
        ax.axhline(y - 0.5, color="#0a0e1a", linewidth=0.5)

    ax.set_title(
        f"8. ANALİZ — RSI + MR + OrderFlow  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
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
        f"📊 8. ANALİZ Haftalık Rapor — {now_tr.strftime('%d.%m.%Y %H:%M İST')}\n"
        f"Toplam {total} işlem | {genel} başarı | ${balance:.2f}"
    )
    tg_send_photo(WEEKLY_IMG, caption)

    ind_lines = _ind_stats_lines(history)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    tg_send(
        f"📊 <b>8. ANALİZ TERS SİSTEM HAFTALIK İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {genel} başarı\n"
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${balance:.2f}\n"
        f"\n🔬 <b>Algoritma İsabet Oranı</b>\n" + "\n".join(ind_lines)
    )
    print(f"[8. ANALİZ weekly] haftalık görsel gönderildi — {total} işlem")


# ── STATS ──────────────────────────────────────────────────────
def run_stats() -> None:
    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)

    if not history:
        tg_send("📊 <b>8. ANALİZ TERS SİSTEM STATS</b>\nHenüz veri yok.")
        return

    total     = len(history)
    wins_all  = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"

    parts = [
        f"📊 <b>8. ANALİZ TERS SİSTEM İSTATİSTİKLER</b>",
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Toplam: {total} işlem  |  {_wr(wins_all, total)}",
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}",
        f"\n🔬 <b>Algoritma İsabet Oranı</b>",
        *_ind_stats_lines(history),
    ]

    for sym in SYMBOLS:
        name = sym.replace("USDT", "")
        w, n = get_symbol_stats(history, sym)
        if n > 0:
            parts.append(f"  {name}: {_wr(w, n)}")

    tg_send("\n".join(parts))
    print(f"[8. ANALİZ stats] rapor gönderildi")


# ── Entry ──────────────────────────────────────────────────────
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        run_close()
    elif mode == "open":
        run_open()
    elif mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        print(f"Bilinmeyen mod: {mode}")
        sys.exit(1)
