"""
7. ANALİZ — Momentum Confluence (Sıfırdan Tasarım)

5 tamamen bağımsız algoritma — diğer analizlerde kullanılmayan indikatörler:
  1. MACD          (12/26/9)   — momentum ivmesi ve dönüş
  2. Stochastic    (14/3)      — aşırı alım/satım + %K/%D çaprazı
  3. 4H Üst Trend  (EMA10/20)  — büyük resim, yalnızca bu sistemde var
  4. ATR Ivme       (14)        — son mumun ATR'a oranı, gürültüyü filtreler
  5. Mum Konsensüsü (son 5 mum) — body ağırlıklı çoğunluk oyu

Oy sistemi (her algoritma +1/−1/0):
  |toplam| ≥ 4  →  $20 işlem  (4-5/5 konsensüs)
  |toplam| = 3  →  $12 işlem  (3/5 konsensüs)
  |toplam| = 2  →  $8 işlem   (2/5 uyum)
  |toplam| ≤ 1  →  işlem açılmaz

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
STATE_FILE   = os.path.join(_DIR, "poly_trader_analiz7_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_analiz7_history.json")
WEEKLY_IMG   = "/tmp/poly_analiz7_weekly_heatmap.png"

INITIAL_BALANCE = 300.0
SYMBOLS         = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
_DAYS_TR        = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

AMOUNT_STRONG   = 20.0   # |skor| >= 4
AMOUNT_MODERATE = 12.0   # |skor| == 3
AMOUNT_WEAK     = 8.0    # |skor| == 2
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


def get_stats(history: list, symbol: str, hour_tr: int) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol and t.get("entry_hour_tr") == hour_tr]
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
        boundary = "----Analiz7Boundary"
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


def fetch_klines_1h(symbol: str, limit: int = 60) -> list[dict]:
    raw = _binance_get("/fapi/v1/klines", {"symbol": symbol, "interval": "1h", "limit": limit})
    return [{"open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
             "close": float(k[4]), "volume": float(k[5])} for k in raw]


def fetch_klines_4h(symbol: str, limit: int = 30) -> list[dict]:
    """4H mum verisi — yalnızca Analiz 7'de kullanılır."""
    raw = _binance_get("/fapi/v1/klines", {"symbol": symbol, "interval": "4h", "limit": limit})
    return [{"open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
             "close": float(k[4]), "volume": float(k[5])} for k in raw]


# ── Teknik yardımcılar ────────────────────────────────────────
def _ema(values: list[float], period: int) -> list[float]:
    k   = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _sma(values: list[float], period: int) -> list[float]:
    out = []
    for i in range(len(values)):
        w = values[max(0, i - period + 1): i + 1]
        out.append(sum(w) / len(w))
    return out


def _atr(klines: list[dict], period: int = 14) -> float:
    trs = []
    for i in range(1, len(klines)):
        h, l, pc = klines[i]["high"], klines[i]["low"], klines[i-1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return klines[-1]["high"] - klines[-1]["low"] or 1.0
    return sum(trs[-period:]) / min(period, len(trs))


# ── 5 Algoritma ───────────────────────────────────────────────

def algo_macd(klines: list[dict]) -> tuple[int, str]:
    """
    MACD (12/26/9) — momentum ivmesi.
    Sinyal: histogram yönü + MACD/Signal çaprazı birlikte.
    Diğer sistemlerde yok.
    """
    closes = [k["close"] for k in klines]
    if len(closes) < 27:
        return 0, "MACD→ yetersiz veri"

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = [ema12[i] - ema26[i] for i in range(len(ema26))]
    signal    = _ema(macd_line, 9)
    hist      = [macd_line[i] - signal[i] for i in range(len(signal))]

    h_now  = hist[-1]
    h_prev = hist[-2]
    m_now  = macd_line[-1]
    s_now  = signal[-1]

    # MACD sıfır çizgisinin hangi tarafında olduğu (ana trend)
    above_zero = m_now > 0

    # Histogram büyüyor mu (ivme artıyor)?
    growing    = h_now > h_prev

    if h_now > 0 and growing:
        return +1, f"MACD↑ hist:{h_now:+.2f} ivme artıyor"
    elif h_now > 0 and not growing and above_zero:
        return +1, f"MACD↑ pozitif bölge hist:{h_now:+.2f}"
    elif h_now < 0 and not growing:
        return -1, f"MACD↓ hist:{h_now:+.2f} ivme azalıyor"
    elif h_now < 0 and growing and not above_zero:
        return -1, f"MACD↓ negatif bölge hist:{h_now:+.2f}"
    else:
        return  0, f"MACD→ karışık hist:{h_now:+.2f}"


def algo_stochastic(klines: list[dict]) -> tuple[int, str]:
    """
    Stochastic (14/3) — aşırı alım/satım + %K/%D çaprazı.
    %K < 20: oversold → yükseliş beklentisi
    %K > 80: overbought → düşüş beklentisi
    %K/%D çaprazı yön teyidi sağlar.
    Diğer sistemlerde yok.
    """
    if len(klines) < 17:
        return 0, "Stoch→ yetersiz veri"

    period = 14
    smooth = 3

    k_raw = []
    for i in range(period - 1, len(klines)):
        window = klines[i - period + 1: i + 1]
        lo  = min(w["low"]  for w in window)
        hi  = max(w["high"] for w in window)
        cl  = klines[i]["close"]
        k_raw.append((cl - lo) / (hi - lo) * 100 if hi != lo else 50.0)

    pct_k = _sma(k_raw, smooth)
    pct_d = _sma(pct_k, smooth)

    kn, kp = pct_k[-1], pct_k[-2]
    dn     = pct_d[-1]

    cross_up   = kp < dn and kn >= dn  # %K %D'yi yukarı kesti
    cross_down = kp > dn and kn <= dn  # %K %D'yi aşağı kesti

    if kn < 20:
        return +1, f"Stoch↑ oversold %K:{kn:.0f} %D:{dn:.0f}"
    elif kn > 80:
        return -1, f"Stoch↓ overbought %K:{kn:.0f} %D:{dn:.0f}"
    elif cross_up and kn < 50:
        return +1, f"Stoch↑ çapraz yukarı %K:{kn:.0f}"
    elif cross_down and kn > 50:
        return -1, f"Stoch↓ çapraz aşağı %K:{kn:.0f}"
    else:
        return  0, f"Stoch→ nötr %K:{kn:.0f} %D:{dn:.0f}"


def algo_4h_trend(klines_4h: list[dict]) -> tuple[int, str]:
    """
    4H EMA10/EMA20 üst zaman dilimi trend filtresi.
    TÜM sistemler içinde yalnızca Analiz 7'de var.
    Büyük resmi görmek için — 1H sinyalleri büyük trendle çelişmesin.
    """
    if len(klines_4h) < 21:
        return 0, "4H→ yetersiz veri"

    closes = [k["close"] for k in klines_4h]
    e10    = _ema(closes, 10)
    e20    = _ema(closes, 20)
    diff   = e10[-1] - e20[-1]
    slope  = e10[-1] - e10[-3] if len(e10) >= 3 else 0
    pct    = diff / closes[-1] * 100

    if diff > 0 and slope > 0:
        return +1, f"4H↑ E10&gt;E20 ({pct:+.2f}%) slope+"
    elif diff < 0 and slope < 0:
        return -1, f"4H↓ E10&lt;E20 ({pct:+.2f}%) slope-"
    elif diff > 0:
        return +1, f"4H↑ E10&gt;E20 ({pct:+.2f}%)"
    elif diff < 0:
        return -1, f"4H↓ E10&lt;E20 ({pct:+.2f}%)"
    else:
        return  0, f"4H→ nötr ({pct:+.2f}%)"


def algo_atr_momentum(klines: list[dict]) -> tuple[int, str]:
    """
    ATR(14) ivme filtresi.
    Son mumun body büyüklüğü ATR'ın ne kadarı?
    Küçük body = belirsizlik → 0
    Büyük body = güçlü hareket → yönüne göre +1/-1
    Ayrıca: fiyat son mumun üst/alt yarısında mı?
    """
    if len(klines) < 16:
        return 0, "ATR→ yetersiz veri"

    atr    = _atr(klines, 14)
    last   = klines[-1]
    body   = abs(last["close"] - last["open"])
    ratio  = body / atr if atr > 0 else 0
    bullish = last["close"] > last["open"]

    # Son mumun yarı noktası — fiyat nerede kapandı?
    mid    = (last["high"] + last["low"]) / 2
    upper_half = last["close"] > mid

    if ratio > 0.6:
        # Güçlü body — net yön
        if bullish:
            return +1, f"ATR↑ güçlü yükseliş body:{ratio:.2f}×ATR"
        else:
            return -1, f"ATR↓ güçlü düşüş body:{ratio:.2f}×ATR"
    elif ratio > 0.3:
        # Orta body — yarı nokta pozisyonu teyit eder
        if bullish and upper_half:
            return +1, f"ATR↑ orta body üst yarı ({ratio:.2f}×)"
        elif not bullish and not upper_half:
            return -1, f"ATR↓ orta body alt yarı ({ratio:.2f}×)"
        else:
            return  0, f"ATR→ orta body karışık ({ratio:.2f}×)"
    else:
        # Doji/küçük body = belirsizlik
        return 0, f"ATR→ doji/küçük body ({ratio:.2f}×ATR)"


def algo_candle_consensus(klines: list[dict]) -> tuple[int, str]:
    """
    Son 5 mumun body ağırlıklı çoğunluk oyu.
    Doji'ler (body < aralığın %25'i) oy kullanamaz.
    Ağırlık: her mumun body/range oranı (daha büyük mum = daha güçlü oy)
    """
    if len(klines) < 6:
        return 0, "Mum→ yetersiz veri"

    window     = klines[-5:]
    bull_score = 0.0
    bear_score = 0.0

    for k in window:
        rng   = k["high"] - k["low"]
        body  = abs(k["close"] - k["open"])
        if rng == 0:
            continue
        weight = body / rng
        if weight < 0.25:
            continue  # Doji — oy yok
        if k["close"] > k["open"]:
            bull_score += weight
        else:
            bear_score += weight

    diff = bull_score - bear_score

    if diff > 0.8:
        return +1, f"Mum↑ boğa konsensüs (+{diff:.2f})"
    elif diff < -0.8:
        return -1, f"Mum↓ ayı konsensüs ({diff:.2f})"
    elif diff > 0.3:
        return +1, f"Mum↑ hafif boğa ({diff:+.2f})"
    elif diff < -0.3:
        return -1, f"Mum↓ hafif ayı ({diff:+.2f})"
    else:
        return  0, f"Mum→ karışık ({diff:+.2f})"


# ── Tam sembol analizi ────────────────────────────────────────
def analyze(symbol: str) -> dict | None:
    try:
        klines_1h = fetch_klines_1h(symbol, 60)
        klines_4h = fetch_klines_4h(symbol, 30)
    except Exception as e:
        print(f"[7. ANALİZ] {symbol} veri hatası: {e}", file=sys.stderr)
        return None

    v1, l1 = algo_macd(klines_1h)
    v2, l2 = algo_stochastic(klines_1h)
    v3, l3 = algo_4h_trend(klines_4h)
    v4, l4 = algo_atr_momentum(klines_1h)
    v5, l5 = algo_candle_consensus(klines_1h)

    score = v1 + v2 + v3 + v4 + v5

    if abs(score) >= 4:
        amount = AMOUNT_STRONG
    elif abs(score) == 3:
        amount = AMOUNT_MODERATE
    elif abs(score) == 2:
        amount = AMOUNT_WEAK
    else:
        amount = 0.0

    return {
        "symbol":        symbol,
        "price":         klines_1h[-1]["close"],
        "score":         score,
        "predicted_dir": "UP" if score > 0 else "DOWN" if score < 0 else None,
        "amount":        amount,
        "votes":         [v1, v2, v3, v4, v5],
        "labels":        [l1, l2, l3, l4, l5],
    }


# ── Algoritma isabet istatistiği ──────────────────────────────
def _ind_stats_lines(history: list) -> list[str]:
    checks = [
        ("MACD",    "ind_macd_ok"),
        ("Stoch",   "ind_stoch_ok"),
        ("4H Trend","ind_4h_ok"),
        ("ATR",     "ind_atr_ok"),
        ("Mum",     "ind_candle_ok"),
    ]
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
        tg_send(f"⏸ <b>7. ANALİZ — {saat} İST</b>\nKapatılacak açık pozisyon yok.")
        print(f"[7. ANALİZ close] {saat} İST — açık pozisyon yok")
        return

    lines      = []
    toplam_pnl = 0.0
    failed_pos = []

    for pos in list(state["open_positions"]):
        klines = None
        for attempt in range(2):
            try:
                klines = fetch_klines_1h(pos["symbol"], 2)
                break
            except Exception as e:
                if attempt == 0:
                    import time as _time; _time.sleep(4)
                else:
                    print(f"[7. ANALİZ close] {pos['symbol']} fiyat hatası: {e}", file=sys.stderr)
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
            "ind_macd_ok":      _vote_ok(vs[0], actual) if len(vs) > 0 else None,
            "ind_stoch_ok":     _vote_ok(vs[1], actual) if len(vs) > 1 else None,
            "ind_4h_ok":        _vote_ok(vs[2], actual) if len(vs) > 2 else None,
            "ind_atr_ok":       _vote_ok(vs[3], actual) if len(vs) > 3 else None,
            "ind_candle_ok":    _vote_ok(vs[4], actual) if len(vs) > 4 else None,
        })

        icon    = "✅" if win else "❌"
        name    = pos["symbol"].replace("USDT", "")
        pct     = (current_price - entry) / entry * 100
        pnl_str = f"+{pnl:.0f}$" if win else f"{pnl:.0f}$"
        lines.append(
            f"{icon} {name}  {pred}  {entry:.2f} → {current_price:.2f} ({pct:+.2f}%)  "
            f"{pnl_str}  skor:{pos.get('score', 0):+d}/5"
        )

    state["open_positions"] = failed_pos
    save_state(state)
    save_history(history)

    if failed_pos:
        names = ", ".join(p["symbol"].replace("USDT", "") for p in failed_pos)
        tg_send(f"⚠️ <b>7. ANALİZ</b> — {names} fiyatı alınamadı, bir sonraki saate bırakıldı.")

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
        f"🏁 <b>7. ANALİZ — {int(saat[:2]):02d}:00 Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+'if toplam_pnl>=0 else ''}{toplam_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{pnl_icon} Toplam P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all} işlem)\n"
        f"{sep}"
    )
    print(f"[7. ANALİZ close] {saat} İST — {len(lines)} pozisyon kapatıldı")


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

        v_lines = "\n   ".join(vote_icons)
        lines.append(
            f"{dir_icon} <b>{name}</b>  {dir_tr}  skor:{score:+d}/5  {amount:.0f}$  giriş:{sig['price']:.2f}\n"
            f"   {v_lines}\n"
            f"   🕐 {hour_tr:02d}:00→{next_h}  başarı: {_wr(hour_wins, hour_total, warn_low=low_data)}"
            f"  |  genel: {_wr(sym_wins, sym_total)}"
        )

    skip_lines = [
        f"⛔ {s['symbol'].replace('USDT','')}  skor:{s['score']:+d}/5  → işlem açılmadı"
        for s in skipped
    ]

    parts = [sep, f"🆕 <b>7. ANALİZ (Momentum Confluence) — {saat} - {next_h} Yeni İşlemler</b>"]

    if lines:
        parts.extend(lines)
    else:
        parts.append("⏸ <i>Bu saat yeterli sinyal yok (|skor| ≤ 1).</i>")

    if skip_lines:
        parts.append(mini_sep)
        parts.extend(skip_lines)
        parts.append(mini_sep)

    at_risk = sum(p.get("amount", AMOUNT_STRONG) for p in state["open_positions"])
    parts.append(
        f"💰 Ana: ${state['balance'] - at_risk:.2f}  |  📂 Açık: {len(state['open_positions'])} poz ${at_risk:.0f}  |  Toplam: ${state['balance']:.2f}"
    )
    parts.append(
        f"<i>Eşik: |skor|≥4→{AMOUNT_STRONG:.0f}$  |skor|=3→{AMOUNT_MODERATE:.0f}$  |skor|=2→{AMOUNT_WEAK:.0f}$  ≤1→yok</i>"
    )
    parts.append(sep)

    tg_send("\n".join(parts))
    print(f"[7. ANALİZ open] {saat} İST — {len(opened)} işlem açıldı, {len(skipped)} elenendi")


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
        "cyan", ["#001a1a", "#004d4d", "#00bcd4"], N=256
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
                clr = "white" if rate[d][h] >= 0.55 else "#78909c"
                ax.text(h, d, f"%{pct}{'⚠' if n < MIN_STAT_COUNT else ''}\n({n})",
                        ha="center", va="center", fontsize=5.5, color=clr, linespacing=1.3)

    for x in range(25): ax.axvline(x - 0.5, color="#0a0e1a", linewidth=0.5)
    for y in range(8):  ax.axhline(y - 0.5, color="#0a0e1a", linewidth=0.5)

    ax.set_title(
        f"7. ANALİZ — MACD + Stoch + 4H Trend + ATR + Mum  ({now_tr.strftime('%d.%m.%Y')})\n"
        f"Toplam: {total} işlem  |  {genel} doğruluk",
        color="#00bcd4", fontsize=10, fontweight="bold", pad=10
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

    tg_send_photo(WEEKLY_IMG,
        f"⚡ 7. ANALİZ Haftalık Rapor — {now_tr.strftime('%d.%m.%Y')}\n"
        f"{total} işlem | {genel} | MACD+Stoch+4H+ATR+Mum"
    )

    ind_lines = _ind_stats_lines(history)
    tg_send(
        f"📊 <b>7. ANALİZ HAFTALIK İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y')} İST\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {genel} başarı\n"
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"\n🔬 <b>Algoritma İsabet Oranı</b>\n" + "\n".join(ind_lines)
    )
    print(f"[7. ANALİZ weekly] gönderildi — {total} işlem")


# ── STATS (isteğe bağlı) ──────────────────────────────────────
def run_stats() -> None:
    history = load_history()
    state   = load_state()
    total   = len(history)
    wins    = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    ind_lines = _ind_stats_lines(history)
    print(f"7. ANALİZ STATS | {total} işlem | {_wr(wins, total)} | P&L: {total_pnl:+.2f}$")
    for l in ind_lines:
        print(l)


# ── Giriş noktası ─────────────────────────────────────────────
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        asyncio.run(run_close())
    elif mode == "open":
        asyncio.run(run_open())
    elif mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        print(f"Bilinmeyen mod: {mode}", file=sys.stderr)
        sys.exit(1)
