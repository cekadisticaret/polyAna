"""
10. ANALİZ — Çift Konsensüs Sanal

İki bağımsız sistem aynı yönü göstermeden işlem açılmaz:
  Sistem A: poly_predictor_analysis.py (Analiz 1/5 motoru)
  Sistem B: Trend + MR + OrderFlow + Funding (Analiz 4/9 motoru)

Sanal: $300 bakiye, sabit $10/işlem. Gerçek PM kapalı.

Modlar: close / open / weekly / stats
Cron:
  0 * * * *   close
  6 * * * *   open
  0 21 * * 6  weekly
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

# .env önce
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poly_predictor_analysis import predict, _fetch_klines

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8722131600:AAH8eg11cvm1xU0KiKEjzCIVsc-RSgkZi4Y"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")
_DIR         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(_DIR, "poly_trader_analiz10_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_analiz10_history.json")
WEEKLY_IMG   = "/tmp/poly_weekly_heatmap_a10.png"

INITIAL_BALANCE = 300.0
TRADE_AMOUNT    = 10.0   # sabit sanal işlem tutarı

SYMBOLS   = ["BTCUSDT", "SOLUSDT"]  # ETH/XRP/DOGE/BNB pasif
_DAYS_TR  = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
IND_NAMES = ["PolyPred", "Trend", "MR", "OF"]


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
    return f"%{wins/total*100:.0f} ({wins}/{total})" if total else "veri yok"


def _ema(values: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
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
    return 100 - 100 / (1 + ag / al) if al else 100.0


def _bollinger(closes: list[float], period: int = 20, mult: float = 2.0):
    w   = closes[-period:] if len(closes) >= period else closes
    mid = sum(w) / len(w)
    std = math.sqrt(sum((x - mid) ** 2 for x in w) / len(w))
    return mid + mult * std, mid, mid - mult * std


def _binance_get(path: str, params: dict) -> any:
    qs  = urllib.parse.urlencode(params)
    url = f"https://fapi.binance.com{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def fetch_klines(symbol: str, limit: int = 60) -> list[dict]:
    raw = _binance_get("/fapi/v1/klines", {"symbol": symbol, "interval": "1h", "limit": limit})
    return [{"open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
             "close": float(k[4]), "volume": float(k[5])} for k in raw]


def fetch_orderbook(symbol: str) -> dict:
    return _binance_get("/fapi/v1/depth", {"symbol": symbol, "limit": 20})


def fetch_funding_rate(symbol: str) -> float:
    data = _binance_get("/fapi/v1/premiumIndex", {"symbol": symbol})
    return float(data.get("lastFundingRate", 0))


# ── Sistem B algoritmaları (Analiz 4/9 ile birebir aynı) ──────
def algo_trend(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines]
    e20    = _ema(closes, 20)
    e50    = _ema(closes, 50)
    cross  = e20[-1] - e50[-1]
    slope  = e20[-1] - e20[-4] if len(e20) >= 4 else 0
    pct    = cross / closes[-1] * 100
    if cross > 0 and slope > 0:
        return +1, f"Trend↑ E20&gt;E50 ({pct:+.2f}%)"
    elif cross < 0 and slope < 0:
        return -1, f"Trend↓ E20&lt;E50 ({pct:+.2f}%)"
    else:
        return  0, f"Trend→ karışık ({pct:+.2f}%)"


def algo_mr(klines: list[dict]) -> tuple[int, str]:
    closes         = [k["close"] for k in klines]
    rsi            = _rsi(closes, 14)
    upper, _, lower = _bollinger(closes, 20, 2.0)
    price          = closes[-1]
    rsi_v = +1 if rsi <= 35 else -1 if rsi >= 65 else 0
    bb_v  = +1 if price <= lower else -1 if price >= upper else 0
    vote  = max(-1, min(1, rsi_v + bb_v))
    arr   = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    bb_lbl = "alt" if price <= lower else "üst" if price >= upper else "orta"
    return vote, f"MR{arr} RSI:{rsi:.0f} BB:{bb_lbl}"


def algo_orderflow(klines: list[dict], ob: dict) -> tuple[int, str]:
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
    return vote, f"OF{arr} CVD:{cvd_r:+.2f} OB:{ob_r:+.2f}"


def algo_funding(rate: float) -> tuple[int, str]:
    pct = rate * 100
    if rate > 0.0005:
        return -1, f"Fund↓ aşırı long ({pct:.3f}%)"
    elif rate < -0.0005:
        return +1, f"Fund↑ aşırı short ({pct:.3f}%)"
    else:
        return  0, f"Fund→ nötr ({pct:.3f}%)"


# ── Çift Konsensüs Analizi ────────────────────────────────────
async def analyze(symbol: str) -> dict | None:
    """
    Sistem A: poly_predictor → predicted_dir + konf
    Sistem B: Trend+MR+OF+Funding → score/4
    Sadece ikisi aynı yönde sinyal verirse işlem açılır.
    """
    # Sistem A
    try:
        pred_obj = await predict(symbol)
    except Exception as e:
        print(f"[10. ANALİZ] {symbol} SistemA hatası: {e}", file=sys.stderr)
        pred_obj = None

    # Sistem B
    try:
        klines  = fetch_klines(symbol, 60)
        ob      = fetch_orderbook(symbol)
        funding = fetch_funding_rate(symbol)
    except Exception as e:
        print(f"[10. ANALİZ] {symbol} SistemB hatası: {e}", file=sys.stderr)
        return None

    v_trend, l_trend = algo_trend(klines)
    v_mr,    l_mr    = algo_mr(klines)
    v_of,    l_of    = algo_orderflow(klines, ob)
    v_fund,  l_fund  = algo_funding(funding)
    score_b = v_trend + v_mr + v_of + v_fund

    dir_b = "UP" if score_b > 0 else "DOWN" if score_b < 0 else None
    strong_b = abs(score_b) >= 3  # 3-4/4 konsensüs

    if pred_obj is None:
        return None

    dir_a    = pred_obj.predicted_dir
    conf_a   = max(pred_obj.prob_up, pred_obj.prob_down)
    strong_a = conf_a >= 0.65

    # Yön çelişiyorsa veya biri nötrse işlem yok
    if dir_a is None or dir_b is None or dir_a != dir_b:
        return None

    # İkisi aynı yönde → tier etiketi (tutar run_open'da sabit $10)
    if strong_a and strong_b:
        tier = "💪 Her iki sistem güçlü"
    elif strong_a or strong_b:
        tier = "⚡ Bir güçlü bir orta"
    else:
        tier = "📊 İkisi orta"

    price = klines[-2]["close"]  # son kapanan mum = Polymarket Price to Beat

    return {
        "symbol":        symbol,
        "price":         price,
        "direction":     dir_a,
        "amount":        TRADE_AMOUNT,
        "tier":          tier,
        "conf_a":        conf_a,
        "score_b":       score_b,
        "labels":        [f"A:konf%{conf_a*100:.0f}", l_trend, l_mr, l_of],
        "votes":         [+1 if dir_a=="UP" else -1, v_trend, v_mr, v_of],
    }


# ── Telegram ─────────────────────────────────────────────────
def tg_send(text: str) -> None:
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"
        }).encode()
        with urllib.request.urlopen(
            urllib.request.Request(url, data=body), timeout=10
        ) as r:
            r.read()
    except Exception as e:
        print(f"[TG] Hata: {e}")


def tg_send_photo(path: str, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(path, "rb") as f:
            img_data = f.read()
        boundary = "----A10Boundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{CHAT_ID}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"heatmap.png\"\r\nContent-Type: image/png\r\n\r\n"
        ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()
        with urllib.request.urlopen(
            urllib.request.Request(url, data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}),
            timeout=20
        ) as r:
            r.read()
    except Exception as e:
        print(f"[TG photo] Hata: {e}")


# ── CLOSE ─────────────────────────────────────────────────────
async def run_close() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")

    state   = load_state()
    history = load_history()
    sep     = "━" * 26

    if not state["open_positions"]:
        tg_send(f"⏸ <b>10. ANALİZ ✦ Sanal — {saat} İST</b>\nKapatılacak açık pozisyon yok.")
        print(f"[10. ANALİZ close] {saat} İST — açık pozisyon yok")
        return

    lines        = []
    tur_pnl      = 0.0
    failed_pos   = []

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
        win    = pred == actual
        pnl    = round(amount if win else -amount, 2)
        if win:
            state["balance"] = round(state["balance"] + amount * 2, 2)
        tur_pnl += pnl
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

        votes = pos.get("votes", [None, None, None, None])
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
            "pnl":              pnl,
            "virtual":          True,
            "exit_time_tr":     now_tr.isoformat(),
            "score_b":          pos.get("score_b", 0),
            "conf_a":           pos.get("conf_a", 0),
            "votes":            votes,
            "ind_poly_ok":      win,
            "ind_trend_ok":     (votes[1] == (+1 if actual=="UP" else -1)) if votes[1] else None,
            "ind_mr_ok":        (votes[2] == (+1 if actual=="UP" else -1)) if votes[2] else None,
            "ind_of_ok":        (votes[3] == (+1 if actual=="UP" else -1)) if votes[3] else None,
        })

        icon    = "✅" if win else "❌"
        name    = pos["symbol"].replace("USDT", "")
        pct     = (current_price - entry) / entry * 100
        pnl_str = f"kazandı +${amount:.0f}" if win else f"kaybetti -${amount:.0f}"
        lines.append(
            f"{icon} {name}  {pred}  {entry:.2f}→{current_price:.2f} ({pct:+.2f}%)  {pnl_str}"
        )

    state["open_positions"] = failed_pos
    if failed_pos:
        names = ", ".join(p["symbol"].replace("USDT", "") for p in failed_pos)
        tg_send(f"⚠️ <b>10. ANALİZ</b> — {names} fiyatı alınamadı.")

    save_state(state)
    save_history(history)

    if not lines:
        return

    save_state(state)

    closed_all = len(history)
    win_all    = sum(1 for t in history if t["win"])
    genel      = _wr(win_all, closed_all)
    total_pnl  = state.get("total_pnl", 0.0)
    pnl_icon   = "🟢" if total_pnl >= 0 else "🔴"
    bal_str    = f"${state.get('balance', INITIAL_BALANCE):.2f} (sanal)"
    saat_round = f"{int(saat[:2]):02d}:00"
    tur_pnl_str = f"{'+'if tur_pnl >= 0 else ''}{tur_pnl:.0f}$"

    tg_send(
        f"{sep}\n"
        f"🏁 <b>10. ANALİZ — {saat_round} Sonuçlar</b>  🔶 SANAL\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {tur_pnl_str}  |  Bakiye: {bal_str}\n"
        f"{pnl_icon} Toplam P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Genel: {genel}\n"
        f"{sep}"
    )
    print(f"[10. ANALİZ close] {saat} İST — {len(lines)} pozisyon kapatıldı")


# ── OPEN ──────────────────────────────────────────────────────
async def run_open() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    hour_tr    = now_tr.hour
    dow        = now_tr.weekday()
    is_weekend = dow >= 5
    saat       = now_tr.strftime("%H:%M")
    sep        = "━" * 26
    next_h     = f"{(hour_tr + 1) % 24:02d}:00"

    state   = load_state()

    candidates = []
    skipped    = []
    for sym in SYMBOLS:
        sig = await analyze(sym)
        if sig is None:
            skipped.append(sym)
            continue
        candidates.append(sig)
        time.sleep(0.2)

    _newly_opened = 0
    for sig in candidates:
        if state.get("balance", INITIAL_BALANCE) < TRADE_AMOUNT:
            print(f"[10. ANALİZ] Sanal bakiye yetersiz: ${state.get('balance', 0):.2f}")
            continue
        if any(p["symbol"] == sig["symbol"] for p in state["open_positions"]):
            continue
        state["open_positions"].append({
            "symbol":           sig["symbol"],
            "predicted_dir":    sig["direction"],
            "entry_price":      sig["price"],
            "entry_time_tr":    now_tr.isoformat(),
            "entry_hour_tr":    hour_tr,
            "entry_dow":        dow,
            "entry_is_weekend": is_weekend,
            "amount":           TRADE_AMOUNT,
            "conf_a":           sig["conf_a"],
            "score_b":          sig["score_b"],
            "votes":            sig["votes"],
            "tier":             sig["tier"],
            "virtual":          True,
        })
        state["balance"] = round(state.get("balance", INITIAL_BALANCE) - TRADE_AMOUNT, 2)
        _newly_opened += 1
        print(f"[10. ANALİZ] Sanal: {sig['symbol']} {sig['direction']} ${TRADE_AMOUNT:.0f}")

    save_state(state)

    at_risk = sum(p.get("amount", TRADE_AMOUNT) for p in state["open_positions"])
    bal_str = f"${state.get('balance', INITIAL_BALANCE):.2f}"

    trade_lines = []
    for sig in candidates:
        name = sig["symbol"].replace("USDT", "")
        opened_pos = next(
            (p for p in state["open_positions"]
             if p["symbol"] == sig["symbol"] and p.get("entry_hour_tr") == hour_tr),
            None,
        )
        if opened_pos:
            d_icon = "📈" if opened_pos["predicted_dir"] == "UP" else "📉"
            d_tr   = "YÜKSELİR" if opened_pos["predicted_dir"] == "UP" else "DÜŞER"
            trade_lines.append(
                f"{d_icon} <b>{name}</b>  {d_tr}  {sig['price']:.2f}  💵${TRADE_AMOUNT:.0f} risk\n"
                f"   {sig['tier']}  |  A:konf%{sig['conf_a']*100:.0f}  B:skor{sig['score_b']:+d}/4\n"
                f"   {' | '.join(sig['labels'][1:])}"
            )
        else:
            trade_lines.append(
                f"⛔ <b>{name}</b>  {sig['direction']}  → açılmadı (bakiye/pozisyon)"
            )

    if trade_lines and _newly_opened > 0:
        tg_send(
            f"{sep}\n"
            f"🆕 <b>10. ANALİZ ✦ Çift Konsensüs — {saat} - {next_h}</b>  🔶 SANAL\n"
            f"💵 Sabit işlem: ${TRADE_AMOUNT:.0f}\n\n"
            + "\n".join(trade_lines) + "\n"
            f"{sep}\n"
            f"💰 Bakiye: {bal_str}  |  Açık: ${at_risk:.0f}  |  Açılan: {_newly_opened}\n"
            f"{sep}"
        )
    elif skipped and not candidates:
        tg_send(
            f"⏸ <b>10. ANALİZ ✦ Çift Konsensüs — {saat} İST</b>\n"
            f"İki sistem konsensüs sağlayamadı — {', '.join(s.replace('USDT','') for s in skipped)} elenendi.\n"
            f"💰 Bakiye: {bal_str}"
        )

    print(f"[10. ANALİZ open] {saat} İST — {_newly_opened} sanal işlem, {len(skipped)} elendi")


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

    sym_names = [s.replace("USDT", "") for s in SYMBOLS]
    grid_w = [[0]*24 for _ in range(7)]
    grid_n = [[0]*24 for _ in range(7)]
    grid_sym = {s: {"w": [[0]*24 for _ in range(7)], "n": [[0]*24 for _ in range(7)]} for s in sym_names}

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

    rate = np.full((7, 24), np.nan)
    for d in range(7):
        for h in range(24):
            if grid_n[d][h] >= 3:
                rate[d][h] = grid_w[d][h] / grid_n[d][h]

    fig, ax = plt.subplots(figsize=(16, 7))
    fig.patch.set_facecolor("#0a0e1a")
    ax.set_facecolor("#0a0e1a")

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
    cmap.set_bad(color="#141820")

    masked = np.ma.masked_invalid(rate)
    im = ax.imshow(masked, cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")

    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=7, color="#78909c")
    ax.set_yticks(range(7))
    ax.set_yticklabels(_DAYS_TR, fontsize=9, color="#b0bec5", fontweight="bold")
    ax.tick_params(length=0)

    for d in range(7):
        for h in range(24):
            if not np.isnan(rate[d][h]):
                pct  = int(rate[d][h] * 100)
                n    = grid_n[d][h]
                clr  = "white" if rate[d][h] >= 0.50 else "#1a1400"
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

    total     = len(history)
    wins      = sum(1 for t in history if t["win"])
    genel     = f"%{wins/total*100:.0f}" if total else "—"
    balance   = state.get("balance", INITIAL_BALANCE)
    total_pnl = state.get("total_pnl", 0.0)

    sym_stats = []
    for sym in SYMBOLS:
        name = sym.replace("USDT", "")
        st   = [t for t in history if t["symbol"] == sym]
        sw   = sum(1 for t in st if t["win"])
        if st:
            sym_stats.append(f"{name}: {len(st)}/{sw} (%{sw/len(st)*100:.0f})")
    sym_line = "   |   ".join(sym_stats)

    ax.set_title(
        f"10. ANALİZ ✦ Çift Konsensüs — Haftalık Başarı Haritası  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
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

    if not history:
        tg_send("📊 <b>10. ANALİZ ✦ Çift Konsensüs</b>\nHenüz veri yok.")
        return

    caption = (
        f"📊 10. ANALİZ ✦ Çift Konsensüs Haftalık Rapor — {now_tr.strftime('%d.%m.%Y %H:%M İST')}\n"
        f"Toplam {total} işlem | {genel} başarı | ${balance:.2f}"
    )
    tg_send_photo(WEEKLY_IMG, caption)

    ind_lines = []
    for i, name in enumerate(IND_NAMES):
        key = ["ind_poly_ok", "ind_trend_ok", "ind_mr_ok", "ind_of_ok"][i]
        ind_trades = [t for t in history if t.get(key) is not None]
        ind_ok     = sum(1 for t in ind_trades if t[key])
        if ind_trades:
            r    = ind_ok / len(ind_trades) * 100
            icon = "🟢" if r >= 60 else "🟡" if r >= 45 else "🔴"
            ind_lines.append(f"  {icon} {name:<10}: %{r:.0f} ({ind_ok}/{len(ind_trades)})")

    pnl_icon = "🟢" if total_pnl >= 0 else "🔴"
    tg_send(
        f"📊 <b>10. ANALİZ HAFTALIK İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {genel} başarı\n"
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${balance:.2f}\n"
        f"\n🔬 <b>Algoritma İsabet Oranı</b>\n" + "\n".join(ind_lines)
    )
    print(f"[10. ANALİZ weekly] haftalık görsel gönderildi — {total} işlem")


# ── STATS ─────────────────────────────────────────────────────
def run_stats() -> None:
    history = load_history()
    state   = load_state()
    if not history:
        tg_send("📊 <b>10. ANALİZ İSTATİSTİKLER</b>\nHenüz veri yok.")
        return
    resolved = [t for t in history if t.get("win") is not None]
    wins  = sum(1 for t in resolved if t["win"])
    total = len(resolved)
    tg_send(
        f"📊 <b>10. ANALİZ ✦ Çift Konsensüs İSTATİSTİKLER</b>\n"
        f"Toplam: {total} işlem  |  {_wr(wins, total)} başarı\n"
        f"Sanal işlem: sabit ${TRADE_AMOUNT:.0f}  |  P&L: {state.get('total_pnl',0):+.2f}$  |  Bakiye: ${state.get('balance', INITIAL_BALANCE):.2f}"
    )


# ── Entry ─────────────────────────────────────────────────────
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "open"
    if cmd == "close":
        asyncio.run(run_close())
    elif cmd == "open":
        asyncio.run(run_open())
    elif cmd == "weekly":
        run_weekly()
    elif cmd == "stats":
        run_stats()
    else:
        print(f"Bilinmeyen mod: {cmd}")
