"""5M BTC trader ortak yardımcılar — Binance, 4-algo, PM emir (102/105/106)."""

import html
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8256912678:AAFWEoRWO7Z0siK_c4Dm5XjgtBKmh-wmF8E"
CHAT_ID   = "830754964"

SYMBOL = "BTCUSDT"
_PERIOD_SECS = 300
_PM_WARMUP_SEC = 3
_PM_OPEN_DEADLINE_SEC = 30
_PM_MAX_PAYOUT_RATIO = 2.5

_PM_GAMMA_URL = "https://gamma-api.polymarket.com/events"
_PM_CLOB_HOST = "https://clob.polymarket.com"
_PM_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_PM_DRY_RUN = True  # trader dosyası günceller

LABEL = "5M PM"


def _pm_bal_line() -> str:
    """Polymarket USDC bakiyesini çekip bildirim satırı döndür."""
    from pm_balance_guard import get_usdc_balance
    bal = get_usdc_balance()
    if bal >= 9999:
        return "🏦 PM Bakiye: sorgulanamadı"
    icon = "🟢" if bal > 0 else "🔴"
    return f"🏦 PM Bakiye: {icon} ${bal:.2f}"


# ── Telegram ─────────────────────────────────────────────────
def _tg_esc(text: str) -> str:
    """Algo etiketlerindeki < > & karakterleri HTML parse hatası vermesin."""
    return html.escape(str(text), quote=False)


def tg_send(text: str) -> None:
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception as e:
        body = ""
        if hasattr(e, "read"):
            try:
                body = e.read().decode()[:200]
            except Exception:
                pass
        print(f"[TG] Hata: {e} {body}")


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
    return [{"open_time": int(k[0]), "open":   float(k[1]), "high":  float(k[2]),
             "low":    float(k[3]), "close": float(k[4]),
             "volume": float(k[5])} for k in raw]


def _resolve_period_candle(ts_5m: int, retries: int = 8, wait_sec: float = 2.0) -> dict | None:
    """Pozisyonun ait olduğu 5m mumunu ts_5m ile bul (Binance gecikmesine karşı retry)."""
    target_ms = ts_5m * 1000
    for _ in range(retries):
        for k in fetch_klines_5m(SYMBOL, 30):
            if k["open_time"] == target_ms:
                return k
        time.sleep(wait_sec)
    return None


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


def _pm_fit_buy(size: float, price: float, min_shares: float = 5.0) -> tuple[float, float]:
    from decimal import Decimal, ROUND_DOWN
    p = Decimal(str(round(price, 2)))
    if p <= 0:
        return size, price
    s = max(Decimal(str(round(size, 2))), Decimal(str(round(min_shares, 2))))
    step = Decimal("0.01")
    for _ in range(10000):
        m = s * p
        if (m * 100) == (m * 100).quantize(Decimal("1"), rounding=ROUND_DOWN):
            return float(s), float(p)
        s += step
    return float(s), float(p)


def _pm_best_ask(client, token_id: str, amount_usd: float) -> float | None:
    """Gerçek en düşük ask — calculate_market_price yetersiz kalabiliyor."""
    from py_clob_client_v2 import OrderType
    try:
        book = client.get_order_book(token_id)
        asks = book.get("asks") or []
        if asks:
            return min(float(a["price"]) for a in asks)
    except Exception:
        pass
    try:
        return float(client.calculate_market_price(token_id, "BUY", amount_usd, OrderType.FAK))
    except Exception:
        return None


def _pm_payout_ratio(spent: float, to_win: float) -> float:
    if spent <= 0:
        return float("inf")
    return round(to_win / spent, 2)


def _pm_payout_ok(spent: float, to_win: float) -> bool:
    return to_win <= spent * _PM_MAX_PAYOUT_RATIO



def _pm_open_deadline(ts_5m: int) -> float:
    return ts_5m + _PM_OPEN_DEADLINE_SEC


def _pm_sleep_cap(deadline: float, sec: float) -> bool:
    """deadline'a kadar en fazla sec saniye bekle; süre varsa True."""
    left = deadline - time.time()
    if left <= 0:
        return False
    time.sleep(min(sec, left))
    return time.time() < deadline


def _pm_period_warmup(ts_5m: int) -> None:
    """5m periyot başında kısa warmup — deadline'ı aşmaz."""
    deadline = _pm_open_deadline(ts_5m)
    target   = ts_5m + _PM_WARMUP_SEC
    now      = time.time()
    if now < target:
        wait = min(target - now, deadline - now)
        if wait > 0:
            print(f"[{LABEL}] PM orderbook bekleniyor ({wait:.0f}s)...", file=sys.stderr)
            time.sleep(wait)


def _pm_place_order(token_id: str, amount_usd: float, tick_size: str = "0.01",
                    neg_risk: bool = False, deadline: float | None = None) -> dict | None:
    """FAK limit buy — best ask + slippage; deadline'a kadar kısa aralıklarla dener."""
    from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions
    from py_clob_client_v2.order_builder.constants import BUY
    from decimal import Decimal, ROUND_DOWN

    amount_usd = float(Decimal(str(amount_usd)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
    if _PM_DRY_RUN:
        client = _pm_get_client()
        price = _pm_best_ask(client, token_id, amount_usd) or 0.5
        price = max(0.02, min(0.98, round(price, 2)))
        est = round(amount_usd / price, 2) if price else amount_usd
        print(f"[DRY RUN] {token_id[:16]}… ${amount_usd:.2f} @ ~{price:.2f} (~{est} shares)")
        return {"order_id": "DRY_RUN", "size": est, "price": price, "spent": amount_usd}

    client = _pm_get_client()
    opts   = PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk)
    slips  = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05]
    attempt = 0
    payout_rejected = False
    last_reject: dict | None = None
    orderbook_miss = 0
    no_match = 0
    last_err = ""

    while True:
        if deadline and time.time() >= deadline:
            print(f"[{LABEL}] Emir süresi doldu (periyot+{_PM_OPEN_DEADLINE_SEC}s)", file=sys.stderr)
            break

        attempt += 1
        if attempt > 1:
            gap = min(2 + (attempt - 2), 5)
            if deadline:
                if not _pm_sleep_cap(deadline, gap):
                    continue
            else:
                time.sleep(gap)

        slip_idx = min(attempt - 1, len(slips) - 1)
        best = _pm_best_ask(client, token_id, amount_usd)
        if best is None:
            orderbook_miss += 1
            print(f"[{LABEL}] Orderbook yok (deneme {attempt})", file=sys.stderr)
            continue

        price = max(0.02, min(0.98, round(best + slips[slip_idx], 2)))
        raw_sz = float(Decimal(str(amount_usd / price)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
        size, price = _pm_fit_buy(max(5.0, raw_sz), price)
        spent = round(size * price, 2)

        if not _pm_payout_ok(spent, size):
            payout_rejected = True
            last_reject = {"spent": spent, "to_win": size, "price": price}
            print(
                f"[{LABEL}] Payout oranı yüksek ({size/spent:.2f}x), "
                f"deneme {attempt} atlandı (@{price:.2f})",
                file=sys.stderr,
            )
            continue

        try:
            args   = OrderArgs(token_id=token_id, price=price, size=size, side=BUY)
            signed = client.create_order(args, opts)
            resp   = client.post_order(signed, order_type=OrderType.FAK)
            if resp and resp.get("success"):
                oid = resp.get("orderID") or resp.get("id", "")
                print(f"[{LABEL}] PM order OK: {size} @ {price} (${spent:.2f}) deneme {attempt}")
                return {"order_id": oid, "size": size, "price": price, "spent": spent}
            print(f"[{LABEL}] Order başarısız (deneme {attempt}): {resp}", file=sys.stderr)
            last_err = str(resp)
        except Exception as e:
            err = str(e)
            last_err = err
            if "no match" in err.lower() or "no orders found" in err.lower():
                no_match += 1
            print(f"[{LABEL}] Order hatası (deneme {attempt}): {err}", file=sys.stderr)
            if "404" in err or "orderbook" in err.lower():
                if deadline:
                    _pm_sleep_cap(deadline, 2)
                else:
                    time.sleep(2)
                try:
                    client = _pm_get_client()
                except Exception:
                    pass

    if payout_rejected and last_reject:
        return {"_skip": "payout", **last_reject}
    if orderbook_miss and not no_match:
        return {"_skip": "orderbook", "attempts": attempt, "orderbook_miss": orderbook_miss}
    if no_match:
        return {"_skip": "no_match", "attempts": attempt, "no_match": no_match, "last_err": last_err}
    if deadline and time.time() >= deadline:
        return {"_skip": "deadline", "attempts": attempt, "orderbook_miss": orderbook_miss}
    return {"_skip": "unknown", "attempts": attempt, "last_err": last_err}
