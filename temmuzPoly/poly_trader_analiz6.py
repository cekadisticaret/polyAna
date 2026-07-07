"""
6. ANALİZ — Multi-Timeframe Konsensüs Trader

3 farklı zaman diliminin aynı yönü göstermesi gerekiyor:
  1. 15m  → EMA9/EMA21 crossover + RSI(14) momentum
  2. 1h   → RSI(14) zonu + Bollinger Band pozisyonu
  3. 4h   → EMA20/EMA50 uzun vadeli trend filtresi

Oy sistemi (her zaman dilimi +1/−1/0):
  |toplam| == 3  →  $20 işlem (tam konsensüs)
  |toplam| == 2  →  $12 işlem (2/3 konsensüs)
  |toplam| <= 1  →  işlem açılmaz

Modlar: close / open / weekly / stats
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

_DIR         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(_DIR, "poly_trader_analiz6_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_analiz6_history.json")
WEEKLY_IMG   = "/tmp/poly_analiz6_weekly_heatmap.png"

INITIAL_BALANCE = 300.0
SYMBOLS         = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
_DAYS_TR        = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_DAYS_FULL_TR   = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

AMOUNT_STRONG   = 20.0   # |skor| == 3 (tam konsensüs)
AMOUNT_MODERATE = 12.0   # |skor| == 2 (2/3 konsensüs)
MIN_STAT_COUNT  = 10


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
def _wr(wins: int, total: int, warn_low: bool = False) -> str:
    if total == 0:
        return "veri yok"
    pct = wins / total * 100
    low = " ⚠️" if warn_low and total < MIN_STAT_COUNT else ""
    return f"%{pct:.0f} ({wins}/{total}){low}"


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


def _vote_ok(vote: int, actual: str) -> bool | None:
    if vote == 0:
        return None
    return (vote > 0) == (actual == "UP")


# ── Telegram ─────────────────────────────────────────────────
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
        boundary = "----Analiz4Boundary"
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


def fetch_klines(symbol: str, interval: str = "1h", limit: int = 60) -> list[dict]:
    raw = _binance_get("/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    return [{"open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
             "close": float(k[4]), "volume": float(k[5])} for k in raw]


# ── Teknik hesaplamalar ───────────────────────────────────────
def _ema(values: list[float], period: int) -> list[float]:
    k    = 2 / (period + 1)
    out  = [values[0]]
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
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def _bollinger(closes: list[float], period: int = 20, mult: float = 2.0) -> tuple[float, float, float]:
    w   = closes[-period:] if len(closes) >= period else closes
    mid = sum(w) / len(w)
    std = math.sqrt(sum((x - mid) ** 2 for x in w) / len(w))
    return mid + mult * std, mid, mid - mult * std


# ── Multi-Timeframe Algoritmaları ─────────────────────────────

def algo_15m(klines_15m: list[dict]) -> tuple[int, str]:
    """15 dakika: EMA9/EMA21 crossover + RSI momentum."""
    closes = [k["close"] for k in klines_15m]
    e9     = _ema(closes, 9)
    e21    = _ema(closes, 21)
    rsi    = _rsi(closes, 14)
    cross  = e9[-1] - e21[-1]
    slope  = e9[-1] - e9[-3] if len(e9) >= 3 else 0

    ema_v = +1 if cross > 0 and slope > 0 else -1 if cross < 0 and slope < 0 else 0
    rsi_v = +1 if rsi < 45 else -1 if rsi > 55 else 0
    vote  = ema_v if ema_v == rsi_v else (ema_v or rsi_v)
    arr   = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    return vote, f"15m {arr}  EMA:{cross/closes[-1]*100:+.2f}%  RSI:{rsi:.0f}"


def algo_1h(klines_1h: list[dict]) -> tuple[int, str]:
    """1 saat: RSI(14) zonu + Bollinger Band pozisyonu."""
    closes = [k["close"] for k in klines_1h]
    rsi    = _rsi(closes, 14)
    upper, mid, lower = _bollinger(closes, 20, 2.0)
    price  = closes[-1]
    bb_pos = (price - mid) / (upper - mid) if upper != mid else 0

    rsi_v = +1 if rsi <= 40 else -1 if rsi >= 60 else 0
    bb_v  = +1 if price < lower else -1 if price > upper else 0

    vote  = max(-1, min(1, rsi_v + bb_v))
    arr   = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    bb_lbl = "alt" if price <= lower else "üst" if price >= upper else f"{bb_pos:+.1f}"
    return vote, f"1h {arr}  RSI:{rsi:.0f}  BB:{bb_lbl}"


def algo_4h(klines_4h: list[dict]) -> tuple[int, str]:
    """4 saat: EMA20/EMA50 uzun vadeli trend filtresi."""
    closes = [k["close"] for k in klines_4h]
    e20    = _ema(closes, 20)
    e50    = _ema(closes, 50)
    cross  = e20[-1] - e50[-1]
    slope  = e20[-1] - e20[-3] if len(e20) >= 3 else 0
    pct    = cross / closes[-1] * 100

    if cross > 0 and slope > 0:
        return +1, f"4h ↑  E20&gt;E50 ({pct:+.2f}%)"
    elif cross < 0 and slope < 0:
        return -1, f"4h ↓  E20&lt;E50 ({pct:+.2f}%)"
    else:
        return  0, f"4h →  karışık ({pct:+.2f}%)"


# ── EkonoFizik (artık kullanılmıyor — MTF ile değiştirildi) ───
def algo_hurst(klines: list[dict]) -> tuple[int, str]:
    """
    Hurst Exponent (R/S analizi, 50 bar).
    H > 0.55 → trending (momentum sinyalini güçlendir)
    H < 0.45 → mean-reverting (MR sinyalini güçlendir)
    0.45–0.55 → rastgele yürüyüş → 0
    """
    import math
    closes = [k["close"] for k in klines[-60:]]
    if len(closes) < 20:
        return 0, "Hurst → veri yetersiz"

    def rs(series):
        n = len(series)
        mean = sum(series) / n
        deviations = [x - mean for x in series]
        cumdev = []
        s = 0
        for d in deviations:
            s += d
            cumdev.append(s)
        R = max(cumdev) - min(cumdev)
        std = (sum((x - mean) ** 2 for x in series) / n) ** 0.5
        return R / std if std > 0 else 0

    windows = [10, 20, 40]
    points = []
    for w in windows:
        if len(closes) >= w:
            r = rs(closes[-w:])
            if r > 0:
                points.append((math.log(w), math.log(r)))

    if len(points) < 2:
        return 0, "Hurst → hesaplanamadı"

    # Lineer regresyon → eğim = H
    n = len(points)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    H = num / den if den > 0 else 0.5

    # Son 20 barda Kalman/EMA trendini belirle (oy yönü için)
    e_short = _ema(closes, 5)
    e_long  = _ema(closes, 20)
    trend_up = e_short[-1] > e_long[-1]

    if H > 0.55:
        vote = +1 if trend_up else -1
        return vote, f"Hurst ↑  H={H:.2f} trend→{'UP' if trend_up else 'DN'}"
    elif H < 0.45:
        vote = -1 if trend_up else +1  # mean-reversion: trend'e karşı
        return vote, f"Hurst MR  H={H:.2f} revert→{'DN' if trend_up else 'UP'}"
    else:
        return 0, f"Hurst →  H={H:.2f} rastgele"


def algo_kalman(klines: list[dict]) -> tuple[int, str]:
    """
    1-D Kalman Filter: gürültüyü süzerek gerçek trendi tahmin eder.
    EMA'ya göre çok daha az gecikmeli.
    Kalman eğiminin yönü ve büyüklüğü oy üretir.
    """
    closes = [k["close"] for k in klines[-50:]]
    if len(closes) < 10:
        return 0, "Kalman → veri yetersiz"

    # Kalman parametreleri
    Q = 1e-4   # process noise
    R = 0.1    # measurement noise
    x = closes[0]   # initial state
    P = 1.0         # initial covariance

    smoothed = []
    for z in closes:
        # Predict
        P = P + Q
        # Update
        K = P / (P + R)
        x = x + K * (z - x)
        P = (1 - K) * P
        smoothed.append(x)

    # Son 5 bardaki eğim (normalize)
    slope  = (smoothed[-1] - smoothed[-5]) / smoothed[-5] * 100 if smoothed[-5] != 0 else 0
    thresh = 0.08  # %0.08 eşik

    if slope > thresh:
        return +1, f"Kalman ↑  eğim:{slope:+.3f}%"
    elif slope < -thresh:
        return -1, f"Kalman ↓  eğim:{slope:+.3f}%"
    else:
        return  0, f"Kalman →  eğim:{slope:+.3f}%"


def algo_perm_entropy(klines: list[dict]) -> tuple[int, str]:
    """
    Permutation Entropy (m=3, tau=1).
    Fiyat serisinin tahmin edilebilirliğini ölçer.
    PE < 0.70 → düzenli/trend → trend yönünde oy
    PE > 0.90 → kaotik/rastgele → 0
    """
    import math
    closes = [k["close"] for k in klines[-50:]]
    n = len(closes)
    m, tau = 3, 1
    if n < m * tau + 5:
        return 0, "PEnt → veri yetersiz"

    patterns: dict = {}
    for i in range(n - (m - 1) * tau):
        sub = [closes[i + j * tau] for j in range(m)]
        perm = tuple(sorted(range(m), key=lambda x: sub[x]))
        patterns[perm] = patterns.get(perm, 0) + 1

    total = sum(patterns.values())
    pe = -sum((c / total) * math.log(c / total) for c in patterns.values())
    # max entropy = log(m!) = log(6) for m=3
    pe_norm = pe / math.log(math.factorial(m))

    # Trend yönü: son 10 bara EMA5 vs EMA10
    e5  = _ema(closes, 5)
    e10 = _ema(closes, 10)
    trend_up = e5[-1] > e10[-1]

    if pe_norm < 0.70:
        vote = +1 if trend_up else -1
        arr  = "↑" if trend_up else "↓"
        return vote, f"PEnt {arr}  PE={pe_norm:.2f} düzenli"
    elif pe_norm > 0.90:
        return 0, f"PEnt →  PE={pe_norm:.2f} kaotik"
    else:
        return 0, f"PEnt →  PE={pe_norm:.2f} nötr"


def algo_hilbert_cycle(klines: list[dict]) -> tuple[int, str]:
    """
    Ehlers Hilbert Transform — Dominant Cycle Phase.
    Fiyatın döngüsel bileşenini çıkarıp faz yönünü belirler.
    Artan faz → yükselen half-cycle → +1
    Azalan faz → düşen half-cycle → -1
    """
    import math
    closes = [k["close"] for k in klines[-50:]]
    n = len(closes)
    if n < 20:
        return 0, "Hilbert → veri yetersiz"

    # Ehlers 4-bar weighted smooth
    smooth = [closes[i] if i < 3 else
              (4*closes[i] + 3*closes[i-1] + 2*closes[i-2] + closes[i-3]) / 10
              for i in range(n)]

    # High-pass detrender (Ehlers katsayıları)
    coef = 0.0962
    c1   = 0.5769
    adj  = 0.075 * 1 + 0.54
    det  = [0.0] * n
    for i in range(6, n):
        det[i] = (coef*smooth[i] + c1*smooth[i-2] - c1*smooth[i-4] - coef*smooth[i-6]) * adj

    # InPhase (I1) ve Quadrature (Q1)
    I1 = [0.0] * n
    Q1 = [0.0] * n
    for i in range(6, n):
        Q1[i] = (coef*det[i] + c1*det[i-2] - c1*det[i-4] - coef*det[i-6]) * adj
        I1[i] = det[i-3]

    # EMA smoothed I/Q (alpha=0.2)
    sI, sQ = [0.0]*n, [0.0]*n
    a = 0.2
    for i in range(1, n):
        sI[i] = a*I1[i] + (1-a)*sI[i-1]
        sQ[i] = a*Q1[i] + (1-a)*sQ[i-1]

    # Phase = atan2(Q, I) → son iki bar faz farkı
    def safe_atan2(q, i_val):
        return math.degrees(math.atan2(q, i_val)) if (q != 0 or i_val != 0) else 0.0

    ph_now  = safe_atan2(sQ[-1],  sI[-1])
    ph_prev = safe_atan2(sQ[-2],  sI[-2])
    delta   = ph_now - ph_prev

    # Wrap around ±180
    if delta >  180: delta -= 360
    if delta < -180: delta += 360

    # Period estimate
    period = abs(360 / delta) if delta != 0 else 20

    if delta > 1.5:
        return +1, f"Hilbert ↑  faz:+{delta:.1f}° T≈{period:.0f}bar"
    elif delta < -1.5:
        return -1, f"Hilbert ↓  faz:{delta:.1f}° T≈{period:.0f}bar"
    else:
        return  0, f"Hilbert →  faz:{delta:.1f}° T≈{period:.0f}bar"


# ── Tam sembol analizi (Multi-Timeframe) ──────────────────────
def analyze(symbol: str) -> dict | None:
    try:
        klines_15m = fetch_klines(symbol, "15m", 60)
        klines_1h  = fetch_klines(symbol, "1h",  60)
        klines_4h  = fetch_klines(symbol, "4h",  50)
    except Exception as e:
        print(f"[6. ANALİZ] {symbol} veri hatası: {e}", file=sys.stderr)
        return None

    v1, l1 = algo_15m(klines_15m)
    v2, l2 = algo_1h(klines_1h)
    v3, l3 = algo_4h(klines_4h)
    score  = v1 + v2 + v3

    amount = AMOUNT_STRONG if abs(score) == 3 else AMOUNT_MODERATE if abs(score) == 2 else 0.0

    return {
        "symbol":        symbol,
        "price":         klines_1h[-1]["close"],
        "score":         score,
        "predicted_dir": "UP" if score > 0 else "DOWN" if score < 0 else None,
        "amount":        amount,
        "votes":         [v1, v2, v3],
        "labels":        [l1, l2, l3],
    }


# ── Algoritma isabet istatistiği ──────────────────────────────
def _ind_stats_lines(history: list) -> list[str]:
    checks = [("15m", "ind_15m_ok"), ("1h", "ind_1h_ok"), ("4h", "ind_4h_ok")]
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


# ── CLOSE ─────────────────────────────────────────────────────
async def run_close() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")

    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        tg_send(f"⏸ <b>6. ANALİZ (Hurst Exponent) — {saat} İST</b>\nKapatılacak açık pozisyon yok.")
        print(f"[6. ANALİZ close] {saat} İST — açık pozisyon yok")
        return

    lines      = []
    toplam_pnl = 0.0
    failed_pos = []

    for pos in list(state["open_positions"]):
        klines = None
        for attempt in range(2):
            try:
                klines = fetch_klines(pos["symbol"], 2)
                break
            except Exception as e:
                if attempt == 0:
                    import time as _time; _time.sleep(4)
                else:
                    print(f"[6. ANALİZ close] {pos['symbol']} fiyat hatası: {e}", file=sys.stderr)
                    failed_pos.append(pos)

        if klines is None:
            continue

        current_price = klines[-1]["close"]
        entry  = pos["entry_price"]
        pred   = pos["predicted_dir"]
        amount = pos.get("amount", AMOUNT_STRONG)
        actual = "UP" if current_price >= entry else "DOWN"
        win    = (pred == actual)
        pnl    = amount if win else -amount
        toplam_pnl += pnl

        state["balance"]   = round(state["balance"] + pnl, 2)
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

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
            "exit_time_tr":     now_tr.isoformat(),
            "pnl":              pnl,
            "ind_15m_ok":       _vote_ok(vs[0], actual) if len(vs) > 0 else None,
            "ind_1h_ok":        _vote_ok(vs[1], actual) if len(vs) > 1 else None,
            "ind_4h_ok":        _vote_ok(vs[2], actual) if len(vs) > 2 else None,
        })

        icon    = "✅" if win else "❌"
        name    = pos["symbol"].replace("USDT", "")
        pct     = (current_price - entry) / entry * 100
        pnl_str = f"+{pnl:.0f}$" if win else f"{pnl:.0f}$"
        lines.append(
            f"{icon} {name}  {pred}  {entry:.2f} → {current_price:.2f} ({pct:+.2f}%)  "
            f"{pnl_str}  skor:{pos.get("score", 0):+d}/3"
        )

    # Başarısız pozisyonları bir sonraki saate bırak
    state["open_positions"] = failed_pos
    save_state(state)
    save_history(history)

    # Hata olan pozisyonlar için bildirim
    if failed_pos:
        names = ", ".join(p["symbol"].replace("USDT", "") for p in failed_pos)
        tg_send(f"⚠️ <b>6. ANALİZ</b> — {names} fiyatı alınamadı (timeout), bir sonraki saate bırakıldı.")

    if not lines:
        return

    total_pnl  = state.get("total_pnl", 0.0)
    pnl_icon   = "🟢" if total_pnl >= 0 else "🔴"
    closed_all = len(history)
    win_all    = sum(1 for t in history if t["win"])
    genel      = f"%{win_all/closed_all*100:.0f}" if closed_all else "—"
    sep        = "━" * 26

    tg_send(
        f"{sep}\n"
        f"🏁 <b>6. ANALİZ (Hurst Exponent) — {int(saat[:2]):02d}:00 Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+'if toplam_pnl>=0 else ''}{toplam_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{pnl_icon} Toplam P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all} işlem)\n"
        f"{sep}"
    )
    print(f"[6. ANALİZ close] {saat} İST — {len(lines)} pozisyon kapatıldı")


# ── OPEN ──────────────────────────────────────────────────────
async def run_open() -> None:
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

    # Pozisyon aç
    for sig in results:
        if sig["amount"] > 0 and sig["predicted_dir"]:
            state["open_positions"].append({
                "symbol":           sig["symbol"],
                "predicted_dir":    sig["predicted_dir"],
                "entry_price":      sig["price"],
                "entry_time_tr":    now_tr.isoformat(),
                "entry_hour_tr":    hour_tr,
                "entry_dow":        dow,
                "entry_is_weekend": is_weekend,
                "score":            sig["score"],
                "amount":           sig["amount"],
                "votes":            sig["votes"],
            })

    save_state(state)

    next_h   = f"{(hour_tr + 1) % 24:02d}:00"
    sep      = "━" * 26
    mini_sep = "━" * 10
    opened   = [s for s in results if s["amount"] > 0 and s["predicted_dir"]]
    skipped  = [s for s in results if s["amount"] == 0]

    lines = []
    for sig in opened:
        sym      = sig["symbol"]
        name     = sym.replace("USDT", "")
        score    = sig["score"]
        amount   = sig["amount"]
        dir_icon = "📈" if sig["predicted_dir"] == "UP" else "📉"
        dir_tr   = "YÜKSELİR" if sig["predicted_dir"] == "UP" else "DÜŞER"
        hour_wins, hour_total = get_stats(history, sym, hour_tr)
        sym_wins,  sym_total  = get_symbol_stats(history, sym)
        low_data = hour_total < MIN_STAT_COUNT

        vote_icons = []
        for v, lbl in zip(sig["votes"], sig["labels"]):
            icon = "🟢" if v > 0 else "🔴" if v < 0 else "⚪"
            vote_icons.append(f"{icon} {lbl}")

        vi = vote_icons
        lines.append(
            f"{dir_icon} <b>{name}</b>  {dir_tr}  skor:{score:+d}/3  {amount:.0f}$  giriş:{sig['price']:.2f}\n"
            f"   {vi[0]}\n"
            f"   {vi[1]}\n"
            f"   {vi[2]}\n"
            f"   🕐 {hour_tr:02d}:00→{next_h} başarı: {_wr(hour_wins, hour_total, warn_low=low_data)}"
            f"  |  genel: {_wr(sym_wins, sym_total)}"
        )

    skip_lines = [
        f"⛔ {s['symbol'].replace('USDT','')}  skor:{s['score']:+d}/3  → işlem açılmadı"
        for s in skipped
    ]

    parts = [sep, f"🆕 <b>6. ANALİZ (MTF: 15m+1h+4h) — {saat} - {next_h} Yeni İşlemler</b>"]

    if lines:
        parts.extend(lines)
    else:
        parts.append("⏸ <i>Bu saat konsensüs yok (15m+1h+4h aynı yönü göstermiyor).</i>")

    if skip_lines:
        parts.append(mini_sep)
        parts.extend(skip_lines)
        parts.append(mini_sep)

    _at_risk4 = sum(p.get("amount", AMOUNT_STRONG) for p in state["open_positions"])
    parts.append(f"💰 Ana: ${state['balance'] - _at_risk4:.2f}  |  📂 Açık: {len(state['open_positions'])} poz ${_at_risk4:.0f}  |  Toplam: ${state['balance']:.2f}")
    parts.append(
        f"<i>Eşik: |skor|≥5→{AMOUNT_STRONG:.0f}$  |skor|=4→{AMOUNT_MODERATE:.0f}$  ≤3→yok</i>"
    )
    parts.append(sep)

    tg_send("\n".join(parts))
    print(f"[6. ANALİZ open] {saat} İST — {len(opened)} işlem açıldı, {len(skipped)} elenendi")


# ── WEEKLY ────────────────────────────────────────────────────
def run_weekly() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np

    history   = load_history()
    state     = load_state()
    now_tr    = datetime.now(timezone.utc).astimezone(_TZ_TR)
    total     = len(history)
    wins      = sum(1 for t in history if t["win"])
    genel     = f"%{wins/total*100:.0f}" if total else "—"
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"

    grid_w = [[0]*24 for _ in range(7)]
    grid_n = [[0]*24 for _ in range(7)]
    for t in history:
        d = t.get("entry_dow")
        h = t.get("entry_hour_tr")
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

    fig, ax = plt.subplots(figsize=(14, 5))
    fig.patch.set_facecolor("#0a0e1a")
    ax.set_facecolor("#0a0e1a")

    cmap = mcolors.LinearSegmentedColormap.from_list(
        "poly_green", ["#1a2a1a", "#1b5e20", "#00c853"], N=256
    )
    cmap.set_bad(color="#141820")
    im = ax.imshow(np.ma.masked_invalid(rate), cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")

    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=7, color="#78909c")
    ax.set_yticks(range(7))
    ax.set_yticklabels(_DAYS_TR, fontsize=9, color="#b0bec5", fontweight="bold")
    ax.tick_params(length=0)

    for d in range(7):
        for h in range(24):
            if not np.isnan(rate[d][h]):
                pct = int(rate[d][h] * 100)
                n   = grid_n[d][h]
                w   = grid_w[d][h]
                if rate[d][h] >= 0.65:
                    clr = "white"
                elif rate[d][h] >= 0.50:
                    clr = "#e8f5e9"
                elif rate[d][h] >= 0.40:
                    clr = "#1a0800"
                else:
                    clr = "#3d1000"
                ax.text(h, d, f"%{pct}{'⚠' if n < MIN_STAT_COUNT else ''}\n+{grid_w[d][h]}-{n-grid_w[d][h]}",
                        ha="center", va="center", fontsize=5.5, color=clr, linespacing=1.3)

    for x in range(25): ax.axvline(x - 0.5, color="#0a0e1a", linewidth=0.5)
    for y in range(8):  ax.axhline(y - 0.5, color="#0a0e1a", linewidth=0.5)

    ax.set_title(
        f"6. ANALİZ — Trend + MR + Orderflow + Funding  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
        f"Toplam: {total} işlem  |  {genel} doğruluk",
        color="#f9a825", fontsize=10, fontweight="bold", pad=10
    )
    ax.set_xlabel("Saat (İST)", color="#546e7a", fontsize=8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
    cbar.set_label("Başarı Oranı", color="#546e7a", fontsize=8)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="#546e7a", fontsize=7)
    cbar.set_ticks([0.4, 0.5, 0.6, 0.7, 0.8])
    cbar.set_ticklabels(["%40", "%50", "%60", "%70", "%80"])

    plt.tight_layout(pad=1.2)
    plt.savefig(WEEKLY_IMG, dpi=150, bbox_inches="tight", facecolor="#0a0e1a", pad_inches=0.1)
    plt.close()

    tg_send_photo(WEEKLY_IMG, f"⚡ 6. ANALİZ Haftalık Rapor — {now_tr.strftime('%d.%m.%Y %H:%M İST')}\n"
                              f"{total} işlem | {genel} | Trend+MR+OF+Funding")

    ind_lines = _ind_stats_lines(history)
    tg_send(
        f"📊 <b>6. ANALİZ HAFTALIK İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M İST')} İST\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {genel} başarı\n"
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"\n🔬 <b>Algoritma İsabet Oranı</b>\n" + "\n".join(ind_lines)
    )
    print(f"[6. ANALİZ weekly] gönderildi — {total} işlem")


# ── STATS ─────────────────────────────────────────────────────
def run_stats() -> None:
    history   = load_history()
    state     = load_state()
    now_tr    = datetime.now(timezone.utc).astimezone(_TZ_TR)

    if not history:
        tg_send("📊 <b>6. ANALİZ STATS</b>\nHenüz veri yok.")
        return

    total     = len(history)
    wins_all  = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"

    parts = [
        f"📊 <b>6. ANALİZ İSTATİSTİKLER</b>",
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Toplam: {total} işlem  |  {_wr(wins_all, total)}",
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}",
        f"Eşik: |skor|≥5→{AMOUNT_STRONG:.0f}$  |skor|=4→{AMOUNT_MODERATE:.0f}$",
        f"\n🔬 <b>Algoritma İsabet Oranı</b>", *_ind_stats_lines(history),
    ]

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
        rows = sorted([(h, w, n) for h, (w, n) in hour_data.items() if n >= 3],
                      key=lambda x: x[1]/x[2], reverse=True)
        for h, w, n in rows[:5]:
            bar = "🟢" if w/n >= 0.6 else "🟡" if w/n >= 0.5 else "🔴"
            parts.append(f"  {bar} {h:02d}:00  {_wr(w, n)}")

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
        parts.append(f"  {'📅' if d < 5 else '🏖'}{bar} {_DAYS_TR[d]}  {_wr(w, n)}")

    tg_send("\n".join(parts))
    print("[6. ANALİZ stats] gönderildi")


# ── Giriş noktası ─────────────────────────────────────────────
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        asyncio.run(run_close())
    elif mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        asyncio.run(run_open())
