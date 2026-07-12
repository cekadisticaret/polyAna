"""
5M BTC REAL TRADER — 4 Algoritma Konsensüs (Gerçek Polymarket)
==============================================
5M 101 ile aynı algoritmalar — gerçek Polymarket işlemleri.

4 algoritma oyu:
  1. RSI + MACD + EMA  (A1 motoru — 5m klines)
  2. Trend Following   (A4/A9 — EMA20/50 crossover)
  3. Mean Reversion    (A4/A9 — RSI + Bollinger Bands)
  4. Orderflow         (A4/A9 — CVD + Order Book imbalance)

Konsensüs:
  4/4 → $5     3/4 → $4     2/4 → $3    ≤1/4 → işlem yok

Market: btc-updown-5m-{unix_timestamp}
Bütçe:  Gerçek Polymarket (küçük miktarlar)
Cron:   */5 * * * *

Modlar:
  open    → pozisyon kapat (önceki) + yeni pozisyon aç
  weekly  → haftalık ısı haritası
  stats   → detaylı rapor
"""

import json
import math
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# .env yükle
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8256912678:AAFWEoRWO7Z0siK_c4Dm5XjgtBKmh-wmF8E"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")

_DIR         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(_DIR, "poly_trader_5m_btc_real_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_5m_btc_real_history.json")
WEEKLY_IMG   = "/tmp/poly_5m_btc_real_weekly.png"

SYMBOL           = "BTCUSDT"
INITIAL_BALANCE  = 0.0   # Gerçek sistem, sanal bakiye yok
AMOUNT_4         =  5.0   # 4/4 oylama
AMOUNT_3         =  4.0   # 3/4 oylama
AMOUNT_2         =  3.0   # 2/4 oylama
_PERIOD_SECS     = 300    # 5 dakika = 300 saniye
_DAYS_TR         = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_DAYS_FULL_TR    = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

# Polymarket
_PM_GAMMA_URL = "https://gamma-api.polymarket.com/events"
_PM_CLOB_HOST = "https://clob.polymarket.com"
_PM_HEADERS   = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_PM_DRY_RUN   = False  # GERÇEK: Polymarket işlem açar

LABEL = "5M BTC REAL"


# ── State & History ───────────────────────────────────────────
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
    return f"%{wins/total*100:.0f} ({wins}/{total})"


def get_stats(history: list, period_min: int, dow: int | None = None) -> tuple[int, int]:
    """5 dakikalık periyot bazlı istatistik."""
    trades = [
        t for t in history
        if t.get("entry_period_min") == period_min
        and (dow is None or t.get("entry_dow") == dow)
    ]
    return sum(1 for t in trades if t["win"]), len(trades)


def get_all_stats(history: list) -> tuple[int, int]:
    wins = sum(1 for t in history if t["win"])
    return wins, len(history)


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
        boundary = "----15mBoundary"
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


# ── Binance Veri ──────────────────────────────────────────────
def _binance_get(path: str, params: dict | None = None) -> dict | list:
    base = "https://fapi.binance.com"
    qs   = urllib.parse.urlencode(params or {})
    url  = f"{base}{path}?{qs}" if qs else f"{base}{path}"
    req  = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def fetch_klines_5m(symbol: str, limit: int = 150) -> list[dict]:
    """5 dakikalık Binance futures klines."""
    raw = _binance_get("/fapi/v1/klines", {"symbol": symbol, "interval": "5m", "limit": limit})
    return [{"open":   float(k[1]), "high":  float(k[2]),
             "low":    float(k[3]), "close": float(k[4]),
             "volume": float(k[5])} for k in raw]


def fetch_orderbook(symbol: str) -> dict:
    return _binance_get("/fapi/v1/depth", {"symbol": symbol, "limit": 20})


def fetch_funding_rate(symbol: str) -> float:
    data = _binance_get("/fapi/v1/premiumIndex", {"symbol": symbol})
    return float(data.get("lastFundingRate", 0))


# ── Teknik Hesaplamalar ───────────────────────────────────────
def _ema(values: list[float], period: int) -> list[float]:
    k   = 2 / (period + 1)
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
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def _bollinger(closes: list[float], period: int = 20) -> tuple[float, float, float]:
    w   = closes[-period:] if len(closes) >= period else closes
    mid = sum(w) / len(w)
    std = math.sqrt(sum((x - mid) ** 2 for x in w) / len(w))
    return mid + 2 * std, mid, mid - 2 * std


def _macd(closes: list[float]) -> tuple[float, float]:
    if len(closes) < 26:
        return 0.0, 0.0
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = [a - b for a, b in zip(ema12, ema26)]
    signal    = _ema(macd_line[-9:], 9) if len(macd_line) >= 9 else [macd_line[-1]]
    return macd_line[-1], signal[-1]


# ── 4 Algoritma (A1 + A4/A9 mirası) ─────────────────────────

def algo_a1_rsi_macd_ema(klines: list[dict]) -> tuple[int, str]:
    """A1 mirası: RSI + MACD + EMA trend."""
    closes = [k["close"] for k in klines]
    rsi    = _rsi(closes, 14)
    macd_v, signal_v = _macd(closes)
    e20 = _ema(closes, 20)
    e50 = _ema(closes, 50) if len(closes) >= 50 else e20

    rsi_v  = +1 if rsi < 40 else -1 if rsi > 60 else 0
    macd_v2 = +1 if macd_v > signal_v else -1 if macd_v < signal_v else 0
    ema_v  = +1 if e20[-1] > e50[-1] else -1

    score = rsi_v + macd_v2 + ema_v
    vote  = +1 if score >= 2 else -1 if score <= -2 else 0
    arr   = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    return vote, f"A1 {arr}  RSI:{rsi:.0f}  MACD:{'↑' if macd_v2>0 else '↓' if macd_v2<0 else '→'}  EMA:{'↑' if ema_v>0 else '↓'}"


def algo_trend(klines: list[dict]) -> tuple[int, str]:
    """A4/A9 mirası: EMA20/50 crossover + slope."""
    closes = [k["close"] for k in klines]
    e20    = _ema(closes, 20)
    e50    = _ema(closes, 50) if len(closes) >= 50 else _ema(closes, 20)
    cross  = e20[-1] - e50[-1]
    slope  = e20[-1] - e20[-4] if len(e20) >= 4 else 0
    pct    = cross / closes[-1] * 100

    if cross > 0 and slope > 0:
        return +1, f"Trend ↑  E20>E50 ({pct:+.2f}%)"
    elif cross < 0 and slope < 0:
        return -1, f"Trend ↓  E20<E50 ({pct:+.2f}%)"
    else:
        return  0, f"Trend →  karışık ({pct:+.2f}%)"


def algo_mr(klines: list[dict]) -> tuple[int, str]:
    """A4/A9 mirası: RSI + Bollinger Bands (Mean Reversion)."""
    closes       = [k["close"] for k in klines]
    rsi          = _rsi(closes, 14)
    upper, _, lower = _bollinger(closes, 20)
    price        = closes[-1]

    rsi_v = +1 if rsi <= 35 else -1 if rsi >= 65 else 0
    bb_v  = +1 if price <= lower else -1 if price >= upper else 0

    vote   = max(-1, min(1, rsi_v + bb_v))
    arr    = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    bb_lbl = "alt" if price <= lower else "üst" if price >= upper else "orta"
    return vote, f"MR {arr}  RSI:{rsi:.0f}  BB:{bb_lbl}"


def algo_orderflow(klines: list[dict], ob: dict) -> tuple[int, str]:
    """A4/A9 mirası: CVD + Order Book imbalance."""
    window    = klines[-20:]
    cvd_delta = sum(k["volume"] if k["close"] >= k["open"] else -k["volume"] for k in window)
    total_vol = sum(k["volume"] for k in window) or 1
    cvd_r     = cvd_delta / total_vol

    bids  = sum(float(b[1]) for b in ob.get("bids", [])[:10])
    asks  = sum(float(a[1]) for a in ob.get("asks", [])[:10])
    ob_r  = (bids - asks) / (bids + asks) if (bids + asks) else 0

    cvd_v = +1 if cvd_r > 0.05 else -1 if cvd_r < -0.05 else 0
    ob_v  = +1 if ob_r  > 0.10 else -1 if ob_r  < -0.10 else 0

    vote  = cvd_v if cvd_v == ob_v else (cvd_v or ob_v)
    arr   = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    return vote, f"OF {arr}  CVD:{cvd_r:+.2f}  OB:{ob_r:+.2f}"


# ── Tam Analiz ────────────────────────────────────────────────
def analyze() -> dict | None:
    try:
        klines  = fetch_klines_5m(SYMBOL, 150)
        ob      = fetch_orderbook(SYMBOL)
    except Exception as e:
        print(f"[{LABEL}] Veri hatası: {e}", file=sys.stderr)
        return None

    v1, l1 = algo_a1_rsi_macd_ema(klines)
    v2, l2 = algo_trend(klines)
    v3, l3 = algo_mr(klines)
    v4, l4 = algo_orderflow(klines, ob)

    up_votes   = sum(1 for v in [v1, v2, v3, v4] if v > 0)
    down_votes = sum(1 for v in [v1, v2, v3, v4] if v < 0)

    if up_votes > down_votes:
        direction = "UP"
        consensus = up_votes
    elif down_votes > up_votes:
        direction = "DOWN"
        consensus = down_votes
    else:
        direction = None
        consensus = 0

    if consensus < 2:
        return {
            "direction": None, "consensus": consensus,
            "votes": [v1, v2, v3, v4], "labels": [l1, l2, l3, l4],
            "entry_price": klines[-2]["close"],
            "amount": 0.0,
        }

    amount = (AMOUNT_4 if consensus == 4
              else AMOUNT_3 if consensus == 3
              else AMOUNT_2)

    return {
        "direction":   direction,
        "consensus":   consensus,
        "votes":       [v1, v2, v3, v4],
        "labels":      [l1, l2, l3, l4],
        "entry_price": klines[-2]["close"],
        "amount":      amount,
    }


# ── Polymarket 15m Market ─────────────────────────────────────
def _current_5m_ts() -> int:
    """Şu an geçerli 5 dakikalık periyodun Unix timestamp'i."""
    now = int(time.time())
    return now - (now % _PERIOD_SECS)  # 300 = 5 * 60


def _pm_find_5m_market(ts_5m: int) -> dict | None:
    """btc-updown-5m-{ts_5m} marketini Polymarket'ta ara."""
    slug = f"btc-updown-5m-{ts_5m}"
    try:
        req = urllib.request.Request(f"{_PM_GAMMA_URL}?slug={slug}", headers=_PM_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        if not data:
            return None
        event   = data[0]
        markets = event.get("markets", [])
        if not markets:
            return None
        m      = markets[0]
        raw_tk = m.get("clobTokenIds", [])
        tokens = json.loads(raw_tk) if isinstance(raw_tk, str) else raw_tk
        if len(tokens) < 2:
            return None
        raw_op = m.get("outcomePrices")
        op     = json.loads(raw_op) if isinstance(raw_op, str) else (raw_op or [])
        return {
            "slug":        slug,
            "title":       event.get("title", ""),
            "active":      event.get("active", False),
            "closed":      event.get("closed", False),
            "up_token":    tokens[0],
            "down_token":  tokens[1],
            "tick_size":   str(m.get("orderPriceMinTickSize", "0.01")),
            "neg_risk":    bool(m.get("negRisk", False)),
            "up_price":    float(op[0]) if len(op) >= 2 else 0.5,
            "down_price":  float(op[1]) if len(op) >= 2 else 0.5,
        }
    except Exception as e:
        print(f"[{LABEL}] Gamma hatası ({slug}): {e}", file=sys.stderr)
    return None


def _pm_get_client():
    from py_clob_client_v2 import ClobClient
    pk     = os.getenv("POLY_PRIVATE_KEY", "")
    funder = os.getenv("POLY_FUNDER", "")
    for attempt in range(3):
        try:
            temp  = ClobClient(host=_PM_CLOB_HOST, chain_id=137, key=pk)
            creds = temp.create_or_derive_api_key()
            if creds is None:
                time.sleep(2)
                continue
            return ClobClient(
                host=_PM_CLOB_HOST, chain_id=137, key=pk,
                creds=creds, signature_type=1, funder=funder,
            )
        except Exception as e:
            print(f"[{LABEL}] Client init ({attempt+1}/3): {e}", file=sys.stderr)
            time.sleep(2)
    raise RuntimeError("Polymarket client oluşturulamadı")


def _pm_place_order(token_id: str, amount_usd: float, tick_size: str = "0.01",
                    neg_risk: bool = False) -> dict | None:
    try:
        from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions
        from py_clob_client_v2.order_builder.constants import BUY
        from decimal import Decimal, ROUND_DOWN
        client = _pm_get_client()
        price  = float(client.calculate_market_price(token_id, "BUY", amount_usd, OrderType.FAK))
        price  = max(0.02, min(0.98, round(price, 2)))
        raw_sz = float(Decimal(str(amount_usd / price)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
        size   = max(5.0, raw_sz)
        spent  = round(size * price, 2)
        if _PM_DRY_RUN:
            print(f"[DRY RUN] token {token_id[:16]}… {size:.1f} shares @ {price:.2f} (~${spent:.2f})")
            return {"order_id": "DRY_RUN", "size": size, "price": price, "spent": spent}
        args   = OrderArgs(token_id=token_id, price=price, size=size, side=BUY)
        signed = client.create_order(args, PartialCreateOrderOptions())
        resp   = client.post_order(signed, order_type=OrderType.FAK)
        if not resp or not resp.get("success"):
            print(f"[{LABEL}] Order başarısız: {resp}", file=sys.stderr)
            return None
        oid = resp.get("orderID") or resp.get("id", "")
        return {"order_id": oid, "size": size, "price": price, "spent": spent}
    except Exception as e:
        print(f"[{LABEL}] Order hatası: {e}", file=sys.stderr)
        return None


# ── Ana Çalışma Mantığı ───────────────────────────────────────
def run() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    dow    = now_tr.weekday()
    saat   = now_tr.strftime("%H:%M")

    # 5 dakikalık periyot bilgileri
    cur_min = now_tr.hour * 60 + now_tr.minute
    period_min = (cur_min // 5) * 5   # 5dk'ya yuvarla (0=00:00, 5=00:05, ..., 1435=23:55)
    ts_5m      = _current_5m_ts()

    state   = load_state()
    history = load_history()

    # ── 1. KAPAT: Önceki periyot pozisyonları ──────────────────
    closed_lines = []
    tur_pnl = 0.0

    if state["open_positions"]:
        # Biraz bekle — mumun kapanmasını garantile
        time.sleep(3)
        try:
            klines = fetch_klines_5m(SYMBOL, 10)
            # klines[-2] = az önce kapanan 5m mumu
            prev_close = klines[-2]["close"]
            prev_open  = klines[-2]["open"]
        except Exception as e:
            print(f"[{LABEL}] Kapanış fiyatı alınamadı: {e}")
            prev_close = None
            prev_open  = None

        for pos in list(state["open_positions"]):
            entry   = pos["entry_price"]
            pred    = pos["predicted_dir"]
            amount  = pos.get("amount", AMOUNT_2)
            to_win  = pos.get("to_win", amount * 2)
            pm_slug = pos.get("pm_slug")
            pm_spent = pos.get("pm_spent", amount)

            # ── Polymarket gerçek sonucu sorgula ────────────────
            win      = None
            pm_pnl   = None
            actual   = None
            pm_note  = ""
            if pm_slug:
                try:
                    req = urllib.request.Request(
                        f"{_PM_GAMMA_URL}?slug={pm_slug}",
                        headers=_PM_HEADERS,
                    )
                    with urllib.request.urlopen(req, timeout=10) as r:
                        pm_data = json.load(r)
                    if pm_data:
                        pm_ev = pm_data[0]
                        pm_m  = pm_ev.get("markets", [{}])[0]
                        raw_op = pm_m.get("outcomePrices")
                        op     = json.loads(raw_op) if isinstance(raw_op, str) else (raw_op or [])
                        if op and pm_ev.get("closed"):
                            up_won  = float(op[0]) >= 0.99
                            our_won = (pos.get("pm_token_dir", pred) == "UP" and up_won) or \
                                      (pos.get("pm_token_dir", pred) == "DOWN" and not up_won)
                            win     = our_won
                            actual  = "UP" if up_won else "DOWN"
                            pm_size = pos.get("pm_size", to_win)
                            pm_pnl  = round(pm_size - pm_spent, 2) if our_won else round(-pm_spent, 2)
                            pm_note = f"  PM:{'✅' if our_won else '❌'}"
                except Exception as e:
                    print(f"[{LABEL}] PM sonuç hatası: {e}", file=sys.stderr)

            # PM sonucu gelmezse fiyat karşılaştırması ile karar ver
            if win is None:
                if prev_close is None:
                    continue
                actual = "UP" if prev_close >= entry else "DOWN"
                win    = (pred == actual)
                pm_pnl = round(to_win - amount, 2) if win else -amount

            pnl = pm_pnl if pm_pnl is not None else (round(to_win - amount, 2) if win else -amount)
            tur_pnl += pnl
            state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

            history.append({
                "symbol":           SYMBOL,
                "predicted_dir":    pred,
                "actual_dir":       actual,
                "win":              win,
                "entry_price":      entry,
                "exit_price":       prev_close,
                "amount":           amount,
                "pm_spent":         pm_spent,
                "to_win":           to_win,
                "pnl":              pnl,
                "entry_time_tr":    pos["entry_time_tr"],
                "entry_period_min": pos.get("entry_period_min"),
                "entry_dow":        pos.get("entry_dow"),
                "exit_time_tr":     now_tr.isoformat(),
                "consensus":        pos.get("consensus"),
                "votes":            pos.get("votes"),
                "pm_slug":          pm_slug,
                "pm_dry_run":       False,
            })

            icon   = "✅" if win else "❌"
            dir_tr = "YÜKSELİR" if pred == "UP" else "DÜŞER"
            pct    = (prev_close - entry) / entry * 100 if prev_close else 0
            closed_lines.append(
                f"{icon} BTC {dir_tr}  {entry:,.0f}→{prev_close:,.0f} ({pct:+.1f}%)"
                f"  {'kazandı +$'+f'{to_win:.2f}' if win else 'kaybetti -$'+f'{amount:.0f}'}"
                f"{pm_note}"
            )

        state["open_positions"] = []
        save_state(state)
        save_history(history)

    # Kapat bildirimi
    if closed_lines:
        win_all, tot_all = get_all_stats(history)
        pnl_icon  = "🟢" if state["total_pnl"] >= 0 else "🔴"
        tur_icon  = "🟢" if tur_pnl >= 0 else "🔴"
        sep = "━" * 26
        close_msg = (
            f"{sep}\n"
            f"🏁 <b>{LABEL} — {saat} Sonuçlar</b>\n"
            + "\n".join(closed_lines) + "\n"
            f"{tur_icon} Bu tur: {'+'if tur_pnl>=0 else ''}{tur_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
            f"{pnl_icon} Toplam P&amp;L: {'+'if state['total_pnl']>=0 else ''}{state['total_pnl']:.2f}$  |  Genel: {_wr(win_all, tot_all)}\n"
            f"{sep}"
        )
        tg_send(close_msg)
        print(f"[{LABEL}] {saat} — {len(closed_lines)} pozisyon kapatıldı")

    # ── 2. AÇ: Yeni 15m pozisyonu ──────────────────────────────
    result = analyze()
    if result is None:
        tg_send(f"⚠️ <b>{LABEL}</b> — {saat} veri alınamadı")
        return

    direction = result["direction"]
    consensus = result["consensus"]
    amount    = result["amount"]
    labels    = result["labels"]
    votes     = result["votes"]
    entry_p   = result["entry_price"]
    next_time = now_tr + timedelta(minutes=5)
    next_saat = next_time.strftime("%H:%M")

    # Geçmiş istatistik
    prev_wins, prev_total = get_stats(history, period_min)
    all_wins, all_total   = get_all_stats(history)

    sep = "━" * 26

    if direction is None:
        # Sinyal yok
        lines_out = []
        for i, (v, l) in enumerate(zip(votes, labels)):
            names = ["A1", "Trend", "MR", "OF"]
            icon  = "🟢" if v > 0 else "🔴" if v < 0 else "⚪"
            lines_out.append(f"  {icon} {names[i]}: {l}")
        msg = (
            f"{sep}\n"
            f"⏸ <b>{LABEL} — {saat} İST</b>\n"
            f"Konsensüs yok ({consensus}/4) → işlem açılmadı\n"
            + "\n".join(lines_out) + "\n"
            f"💰 Bakiye: ${state['balance']:.2f}\n"
            f"{sep}"
        )
        tg_send(msg)
        print(f"[{LABEL}] {saat} — konsensüs yok ({consensus}/4)")
        return

    # Market bul + TO WIN hesapla
    pm_slug    = None
    pm_info    = _pm_find_5m_market(ts_5m)
    token_price = None
    if pm_info and not pm_info.get("closed"):
        token_price = pm_info["up_price"] if direction == "UP" else pm_info["down_price"]
        pm_slug = pm_info["slug"]

    # to_win: kazanırsak alacağımız miktar (Polymarket pay-out)
    # Formül: $amount / token_price → kaç share aldık, her share $1 → to_win
    if token_price and token_price > 0:
        to_win = round(amount / token_price, 2)
    else:
        to_win = round(amount * 2, 2)   # fiyat alınamazsa %50 varsay

    # Gerçek Polymarket order aç
    order_result = None
    pm_token_dir = direction
    if pm_info and not pm_info.get("closed"):
        token_id = pm_info["up_token"] if direction == "UP" else pm_info["down_token"]
        order_result = _pm_place_order(token_id, amount, pm_info["tick_size"], pm_info["neg_risk"])
        if not order_result:
            tg_send(f"⚠️ <b>{LABEL}</b> — PM order başarısız, {direction} {saat}")
            print(f"[{LABEL}] PM order başarısız, işlem atlandı")
            return
        # Gerçek order'dan to_win ve spent güncelle
        to_win  = order_result["size"]       # share sayısı = max kazanç ($)
        amount  = order_result["spent"]       # gerçek harcanan miktar
    else:
        print(f"[{LABEL}] PM market bulunamadı veya kapalı, işlem atlandı")
        return

    # Bakiyeden harcanan miktarı düş
    state["balance"] = round(state["balance"] - amount, 2)

    # Pozisyonu state'e kaydet
    pos_data = {
        "symbol":           SYMBOL,
        "predicted_dir":    direction,
        "entry_price":      entry_p,
        "amount":           amount,
        "pm_spent":         amount,
        "to_win":           to_win,
        "token_price":      token_price,
        "consensus":        consensus,
        "votes":            votes,
        "entry_time_tr":    now_tr.isoformat(),
        "entry_period_min": period_min,
        "entry_dow":        dow,
        "pm_slug":          pm_slug,
        "pm_token_dir":     pm_token_dir,
        "ts_5m":            ts_5m,
    }
    if order_result:
        pos_data["pm_size"]     = order_result["size"]
        pos_data["pm_order_id"] = order_result.get("order_id", "")
    state["open_positions"].append(pos_data)
    save_state(state)

    # Bildirim
    dir_tr   = "YÜKSELİR" if direction == "UP" else "DÜŞER"
    dir_icon = "📈" if direction == "UP" else "📉"
    names    = ["A1", "Trend", "MR", "OF"]
    vote_str = "  ".join(
        f"{'🟢' if v > 0 else '🔴' if v < 0 else '⚪'} {names[i]}"
        for i, v in enumerate(votes)
    )
    price_str = f"@{token_price:.2f}" if token_price else ""

    msg = (
        f"{sep}\n"
        f"🆕 <b>{LABEL} — {saat} → {next_saat}</b>\n"
        f"{dir_icon} <b>BTC {dir_tr}</b>  ({consensus}/4)  💵 ${amount:.2f} {price_str} → 🏆 ${to_win:.2f}\n"
        f"Giriş: {entry_p:,.2f} USDT\n"
        f"{vote_str}\n"
        f"🕐 Bu periyot: {_wr(prev_wins, prev_total)}  |  Genel: {_wr(all_wins, all_total)}\n"
        f"PM: {pm_slug or 'bulunamadı'}\n"
        f"{sep}"
    )
    tg_send(msg)
    print(f"[{LABEL}] {saat} — {dir_tr} {consensus}/4  ${amount:.0f}→${to_win:.2f}  entry:{entry_p:,.2f}")


# ── WEEKLY ─────────────────────────────────────────────────────
def run_weekly() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np

    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)

    if not history:
        tg_send(f"📊 <b>{LABEL} WEEKLY</b>\nHenüz veri yok.")
        return

    # 7 gün × 288 periyot (5dk × 288 = 24 saat) grid
    grid_w = [[0] * 288 for _ in range(7)]
    grid_n = [[0] * 288 for _ in range(7)]
    for t in history:
        d = t.get("entry_dow")
        p = t.get("entry_period_min")
        if d is None or p is None:
            continue
        idx = p // 5
        grid_n[d][idx] += 1
        if t["win"]:
            grid_w[d][idx] += 1

    # Saatlik gruba topla (12 periyot = 1 saat) — görsel okunabilirlik
    grid_w_h = [[0] * 24 for _ in range(7)]
    grid_n_h = [[0] * 24 for _ in range(7)]
    for d in range(7):
        for idx in range(288):
            h = idx // 12
            grid_w_h[d][h] += grid_w[d][idx]
            grid_n_h[d][h] += grid_n[d][idx]

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

    masked = np.ma.masked_invalid(rate)
    im = ax.imshow(masked, cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(24)], fontsize=6, color="#78909c", rotation=45)
    ax.set_yticks(range(7))
    ax.set_yticklabels(_DAYS_TR, fontsize=8, color="#b0bec5", fontweight="bold")
    ax.tick_params(length=0)

    total = len(history)
    wins  = sum(1 for t in history if t["win"])
    genel = f"%{wins/total*100:.0f}" if total else "—"
    balance = state.get("balance", INITIAL_BALANCE)
    total_pnl = state.get("total_pnl", 0.0)

    ax.set_title(
        f"{LABEL} — Haftalık 15dk Isı Haritası  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
        f"Toplam: {total} işlem  |  {genel}  |  Bakiye: ${balance:.2f}  |  P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$",
        color="#4fc3f7", fontsize=9, fontweight="bold", pad=8
    )
    fig.colorbar(im, ax=ax, fraction=0.01, pad=0.01)
    plt.tight_layout(pad=1.0)
    plt.savefig(WEEKLY_IMG, dpi=130, bbox_inches="tight",
                facecolor="#0a0e1a", pad_inches=0.1)
    plt.close()

    caption = f"📊 {LABEL} Haftalık  {now_tr.strftime('%d.%m.%Y')}  {total} işlem | {genel} | ${balance:.2f}"
    tg_send_photo(WEEKLY_IMG, caption)
    print(f"[{LABEL}] weekly gönderildi — {total} işlem")


# ── STATS ─────────────────────────────────────────────────────
def run_stats() -> None:
    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)

    total    = len(history)
    wins_all = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"

    parts = [
        f"📊 <b>{LABEL} İSTATİSTİKLER</b>",
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Toplam: {total} işlem  |  {_wr(wins_all, total)}",
        f"{pnl_icon} P&amp;L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}",
        f"Başlangıç: ${INITIAL_BALANCE:.2f}",
    ]

    if history:
        parts.append(f"\n📅 <b>Gün Bazlı</b>")
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
            parts.append(f"  {bar} {_DAYS_TR[d]}  {_wr(w, n)}")

        # Konsensüs başarısı
        parts.append(f"\n🎯 <b>Konsensüs Bazlı</b>")
        for c in [2, 3, 4]:
            c_hist = [t for t in history if t.get("consensus") == c]
            if c_hist:
                cw = sum(1 for t in c_hist if t["win"])
                bar = "🟢" if cw/len(c_hist) >= 0.6 else "🟡" if cw/len(c_hist) >= 0.5 else "🔴"
                parts.append(f"  {bar} {c}/4 konsensüs: {_wr(cw, len(c_hist))}")

    tg_send("\n".join(parts))
    print(f"[{LABEL}] stats gönderildi")


# ── Giriş Noktası ─────────────────────────────────────────────
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        run()
