"""
5. ANALİZ — Çoklu Algoritma Sanal Trader

4 bağımsız algoritmanın oylarını birleştirerek sinyal üretir:
  1. Trend Following  → EMA20/EMA50 crossover + slope
  2. Mean Reversion   → RSI(14) + Bollinger Bands(20,2)
  3. Orderflow        → CVD yaklaşımı + Order Book imbalance
  4. Funding Rate     → Binance futures funding rate (contrarian)

Oy sistemi (her algoritma +1/−1/0):
  |toplam| ≥ 3  →  $20 işlem
  |toplam| = 2  →  $12 işlem
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
BOT_TOKEN = "8529258517:AAHuVn1VFftXK7RR2Z1w3UqyHGuHNDXDYI4"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")

_DIR         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(_DIR, "poly_trader_analiz5_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_analiz5_history.json")
WEEKLY_IMG   = "/tmp/poly_analiz5_weekly_heatmap.png"

INITIAL_BALANCE = 300.0
SYMBOLS         = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
_DAYS_TR        = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_DAYS_FULL_TR   = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

AMOUNT_STRONG   = 12.0   # |skor| >= 3
AMOUNT_MODERATE = 8.0    # |skor| == 2
MIN_STAT_COUNT  = 10

# ── Polymarket Config ──────────────────────────────────────────
_PM_CLOB_HOST = "https://clob.polymarket.com"
_PM_GAMMA_URL = "https://gamma-api.polymarket.com/events"
_PM_HEADERS   = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_PM_ASSET_MAP = {"BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana"}
_PM_DRY_RUN   = os.getenv("POLY_DRY_RUN", "true").lower() == "true"


def _pm_get_client():
    """Her çağrıda taze cred türet — 401 retry ile güvenli."""
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
            print(f"[5. ANALİZ] Client init ({attempt+1}/3): {e}", file=sys.stderr)
            time.sleep(2)
    raise RuntimeError("Polymarket client oluşturulamadı")


def _pm_get_balance() -> float:
    """Proxy wallet USDC bakiyesi (CLOB). Hata durumunda -1 döner."""
    try:
        from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
        client = _pm_get_client()
        bal = client.get_balance_allowance(
            params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        )
        return int(bal.get("balance", 0)) / 1e6
    except Exception:
        return -1.0


def _pm_find_market(symbol: str, et_hour: int, date_utc) -> dict | None:
    """Polymarket saatlik marketi bul. ET saatine göre slug oluşturur."""
    asset = _PM_ASSET_MAP.get(symbol)
    if not asset:
        return None
    month = date_utc.strftime("%B").lower()
    day   = date_utc.day
    year  = date_utc.year
    # Saat formatı: 9am, 10am, 12pm, 1pm...
    if et_hour == 0:
        h_str = "12am"
    elif et_hour < 12:
        h_str = f"{et_hour}am"
    elif et_hour == 12:
        h_str = "12pm"
    else:
        h_str = f"{et_hour - 12}pm"
    slugs = [
        f"{asset}-up-or-down-{month}-{day}-{year}-{h_str}-et",
        f"{asset}-up-or-down-{month}-{day}-{h_str}-et",
    ]
    for slug in slugs:
        try:
            req = urllib.request.Request(f"{_PM_GAMMA_URL}?slug={slug}", headers=_PM_HEADERS)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.load(r)
            if not data:
                continue
            event = data[0]
            markets = event.get("markets", [])
            if not markets:
                continue
            m      = markets[0]
            raw_tk = m.get("clobTokenIds", [])
            tokens = json.loads(raw_tk) if isinstance(raw_tk, str) else raw_tk
            if len(tokens) < 2:
                continue
            raw_op = m.get("outcomePrices")
            op     = json.loads(raw_op) if isinstance(raw_op, str) else (raw_op or [])
            return {
                "slug":           event.get("slug", slug),
                "title":          event.get("title", ""),
                "active":         event.get("active", False),
                "closed":         event.get("closed", False),
                "up_token":       tokens[0],
                "down_token":     tokens[1],
                "tick_size":      str(m.get("orderPriceMinTickSize", "0.01")),
                "neg_risk":       bool(m.get("negRisk", False)),
                "outcome_prices": op,
            }
        except Exception as e:
            print(f"[5. ANALİZ] Gamma hatası ({slug}): {e}", file=sys.stderr)
    return None


def _pm_fit_buy(size: float, price: float, min_shares: float = 5.0) -> tuple[float, float]:
    """CLOB BUY: size×price tam sent olacak şekilde size ayarla (max 2 ondalık)."""
    from decimal import Decimal, ROUND_DOWN
    p = Decimal(str(round(price, 2)))
    if p <= 0:
        return size, price
    s = max(Decimal(str(round(size, 2))), Decimal(str(round(min_shares, 2))))
    step = Decimal("0.01")
    for _ in range(10000):
        m = s * p
        cents = m * 100
        if cents == cents.quantize(Decimal("1"), rounding=ROUND_DOWN):
            return float(s), float(p)
        s += step
    return float(s), float(p)


def _pm_place_order(token_id: str, amount_usd: float, tick_size: str = "0.01",
                    neg_risk: bool = False) -> dict | None:
    """token_id'yi amount_usd kadar satın al (FAK). {order_id, size, price, spent} döndürür."""
    try:
        from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions
        from py_clob_client_v2.order_builder.constants import BUY
        from decimal import Decimal, ROUND_DOWN
        client = _pm_get_client()
        price  = float(client.calculate_market_price(token_id, "BUY", amount_usd, OrderType.FAK))
        price  = max(0.02, min(0.98, round(price, 2)))
        raw_sz = float(Decimal(str(amount_usd / price)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
        size, price = _pm_fit_buy(max(5.0, raw_sz), price)
        spent  = round(size * price, 2)
        if _PM_DRY_RUN:
            print(f"[DRY RUN] {token_id[:16]}… {size} shares @ {price:.2f} (~${spent:.2f})")
            return {"order_id": "DRY_RUN", "size": size, "price": price, "spent": spent}
        args = OrderArgs(token_id=token_id, price=price, size=size, side=BUY)
        signed = client.create_order(args, PartialCreateOrderOptions())
        resp   = client.post_order(signed, order_type=OrderType.FAK)
        if not resp or not resp.get("success"):
            print(f"[5. ANALİZ] Order başarısız: {resp}", file=sys.stderr)
            return None
        oid = resp.get("orderID") or resp.get("id", "")
        return {"order_id": oid, "size": size, "price": price, "spent": spent}
    except Exception as e:
        print(f"[5. ANALİZ] Order hatası: {e}", file=sys.stderr)
        return None


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


def fetch_klines(symbol: str, limit: int = 60) -> list[dict]:
    raw = _binance_get("/fapi/v1/klines", {"symbol": symbol, "interval": "1h", "limit": limit})
    return [{"open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
             "close": float(k[4]), "volume": float(k[5])} for k in raw]


def fetch_orderbook(symbol: str) -> dict:
    return _binance_get("/fapi/v1/depth", {"symbol": symbol, "limit": 20})


def fetch_funding_rate(symbol: str) -> float:
    data = _binance_get("/fapi/v1/premiumIndex", {"symbol": symbol})
    return float(data.get("lastFundingRate", 0))


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


# ── 4 Algoritma ───────────────────────────────────────────────

def algo_trend(klines: list[dict]) -> tuple[int, str]:
    closes = [k["close"] for k in klines]
    e20    = _ema(closes, 20)
    e50    = _ema(closes, 50)
    cross  = e20[-1] - e50[-1]
    slope  = e20[-1] - e20[-4] if len(e20) >= 4 else 0
    pct    = cross / closes[-1] * 100

    if cross > 0 and slope > 0:
        return +1, f"Trend ↑  E20&gt;E50 ({pct:+.2f}%)"
    elif cross < 0 and slope < 0:
        return -1, f"Trend ↓  E20&lt;E50 ({pct:+.2f}%)"
    else:
        return  0, f"Trend →  karışık ({pct:+.2f}%)"


def algo_mr(klines: list[dict]) -> tuple[int, str]:
    closes     = [k["close"] for k in klines]
    rsi        = _rsi(closes, 14)
    upper, _, lower = _bollinger(closes, 20, 2.0)
    price      = closes[-1]

    rsi_v = +1 if rsi <= 35 else -1 if rsi >= 65 else 0
    bb_v  = +1 if price <= lower else -1 if price >= upper else 0

    vote  = max(-1, min(1, rsi_v + bb_v))
    arr   = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    bb_lbl = "alt" if price <= lower else "üst" if price >= upper else "orta"
    return vote, f"MR {arr}  RSI:{rsi:.0f}  BB:{bb_lbl}"


def algo_orderflow(klines: list[dict], ob: dict) -> tuple[int, str]:
    window    = klines[-20:]
    cvd_delta = sum(k["volume"] if k["close"] >= k["open"] else -k["volume"] for k in window)
    total_vol = sum(k["volume"] for k in window) or 1
    cvd_r     = cvd_delta / total_vol

    bids   = sum(float(b[1]) for b in ob.get("bids", [])[:10])
    asks   = sum(float(a[1]) for a in ob.get("asks", [])[:10])
    ob_r   = (bids - asks) / (bids + asks) if (bids + asks) else 0

    cvd_v  = +1 if cvd_r > 0.08 else -1 if cvd_r < -0.08 else 0
    ob_v   = +1 if ob_r  > 0.15 else -1 if ob_r  < -0.15 else 0

    vote   = cvd_v if cvd_v == ob_v else (cvd_v or ob_v)
    arr    = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    return vote, f"OF {arr}  CVD:{cvd_r:+.2f}  OB:{ob_r:+.2f}"


def algo_funding(rate: float) -> tuple[int, str]:
    pct = rate * 100
    if rate > 0.0005:
        return -1, f"Fund ↓  aşırı long (rate:{pct:.3f}%)"
    elif rate < -0.0005:
        return +1, f"Fund ↑  aşırı short (rate:{pct:.3f}%)"
    else:
        return  0, f"Fund →  nötr (rate:{pct:.3f}%)"


# ── Tam sembol analizi ────────────────────────────────────────
def analyze(symbol: str) -> dict | None:
    try:
        klines  = fetch_klines(symbol, 60)
        ob      = fetch_orderbook(symbol)
        funding = fetch_funding_rate(symbol)
    except Exception as e:
        print(f"[5. ANALİZ] {symbol} veri hatası: {e}", file=sys.stderr)
        return None

    v1, l1 = algo_trend(klines)
    v2, l2 = algo_mr(klines)
    v3, l3 = algo_orderflow(klines, ob)
    v4, l4 = algo_funding(funding)
    score   = v1 + v2 + v3 + v4

    amount = AMOUNT_STRONG if abs(score) >= 3 else AMOUNT_MODERATE if abs(score) == 2 else 0.0

    return {
        "symbol":        symbol,
        "price":         klines[-1]["close"],
        "score":         score,
        "predicted_dir": "UP" if score > 0 else "DOWN" if score < 0 else None,
        "amount":        amount,
        "votes":         [v1, v2, v3, v4],
        "labels":        [l1, l2, l3, l4],
    }


# ── Algoritma isabet istatistiği ──────────────────────────────
def _ind_stats_lines(history: list) -> list[str]:
    checks = [("Trend", "ind_trend_ok"), ("MR", "ind_mr_ok"),
              ("OF",    "ind_of_ok"),    ("Funding", "ind_fund_ok")]
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
        tg_send(f"⏸ <b>5. ANALİZ — {saat} İST</b>\nKapatılacak açık pozisyon yok.")
        print(f"[5. ANALİZ close] {saat} İST — açık pozisyon yok")
        return

    lines      = []
    pm_tur_pnl = 0.0  # Bu turdaki PM P&L
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
                    print(f"[5. ANALİZ close] {pos['symbol']} fiyat hatası: {e}", file=sys.stderr)
                    failed_pos.append(pos)

        if klines is None:
            continue

        current_price = klines[-1]["close"]
        entry  = pos["entry_price"]
        pred   = pos["predicted_dir"]
        amount = pos.get("amount", AMOUNT_STRONG)
        actual = "UP" if current_price >= entry else "DOWN"
        win    = (pred == actual)

        # Polymarket gerçek sonucu kontrol et
        pm_pnl_str  = ""
        pm_win      = None
        if pos.get("pm_slug") and not pos.get("pm_error"):
            try:
                req = urllib.request.Request(
                    f"{_PM_GAMMA_URL}?slug={pos['pm_slug']}",
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
                        our_won = (pos["pm_token_dir"] == "UP" and up_won) or \
                                  (pos["pm_token_dir"] == "DOWN" and not up_won)
                        pm_win   = our_won
                        pm_size  = pos.get("pm_size", 0)
                        pm_spent = pos.get("pm_spent", 0)
                        pm_pnl_val = round(pm_size - pm_spent, 2) if our_won else round(-pm_spent, 2)
                        pm_pnl_str  = f"  |  🎯PM: {'+'if our_won else ''}{pm_pnl_val:.2f}$"
                        pm_tur_pnl += pm_pnl_val
            except Exception as e:
                print(f"[5. ANALİZ close] PM sonuç hatası: {e}", file=sys.stderr)

        vs = pos.get("votes", [])
        history.append({
            "symbol":           pos["symbol"],
            "predicted_dir":    pred,
            "actual_dir":       actual,
            "win":              win,
            "pm_win":           pm_win,
            "entry_price":      entry,
            "exit_price":       current_price,
            "entry_time_tr":    pos["entry_time_tr"],
            "entry_hour_tr":    pos["entry_hour_tr"],
            "entry_dow":        pos["entry_dow"],
            "entry_is_weekend": pos["entry_is_weekend"],
            "score":            pos.get("score", 0),
            "amount":           amount,
            "pm_spent":         pos.get("pm_spent"),
            "pm_order_id":      pos.get("pm_order_id"),
            "exit_time_tr":     now_tr.isoformat(),
            "pnl":              pos.get("pm_spent", 0) * (-1 if not win else 1),
            "ind_trend_ok":     _vote_ok(vs[0], actual) if len(vs) > 0 else None,
            "ind_mr_ok":        _vote_ok(vs[1], actual) if len(vs) > 1 else None,
            "ind_of_ok":        _vote_ok(vs[2], actual) if len(vs) > 2 else None,
            "ind_fund_ok":      _vote_ok(vs[3], actual) if len(vs) > 3 else None,
        })

        icon    = "✅" if win else "❌"
        name    = pos["symbol"].replace("USDT", "")
        pct     = (current_price - entry) / entry * 100
        pm_spent = pos.get("pm_spent", 0)
        lines.append(
            f"{icon} {name}  {pred}  {entry:.2f} → {current_price:.2f} ({pct:+.2f}%)  "
            f"skor:{pos.get('score', 0):+d}/4  -${pm_spent:.2f} risk{pm_pnl_str}"
        )

    # Başarısız pozisyonları bir sonraki saate bırak
    state["open_positions"] = failed_pos
    save_state(state)
    save_history(history)

    # Hata olan pozisyonlar için bildirim
    if failed_pos:
        names = ", ".join(p["symbol"].replace("USDT", "") for p in failed_pos)
        tg_send(f"⚠️ <b>5. ANALİZ</b> — {names} fiyatı alınamadı (timeout), bir sonraki saate bırakıldı.")

    if not lines:
        return

    closed_all = len(history)
    pm_wins    = sum(1 for t in history if t.get("pm_win") is True)
    pm_closed  = sum(1 for t in history if t.get("pm_win") is not None)
    dir_wins   = sum(1 for t in history if t["win"])
    pm_bal     = _pm_get_balance()
    pm_bal_str = f"${pm_bal:.2f}" if pm_bal >= 0 else "?"
    genel_dir  = f"%{dir_wins/closed_all*100:.0f} ({closed_all})" if closed_all else "—"
    genel_pm   = f"%{pm_wins/pm_closed*100:.0f} ({pm_closed})" if pm_closed else "—"
    sep        = "━" * 26

    tg_send(
        f"{sep}\n"
        f"🏁 <b>5. ANALİZ — {int(saat[:2]):02d}:00 Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"Bu tur PM: {'+'if pm_tur_pnl>=0 else ''}{pm_tur_pnl:.2f}$  |  🟢 Bütçe: {pm_bal_str}\n"
        f"Yön doğruluğu: {genel_dir}  |  PM kazanma: {genel_pm}\n"
        f"{sep}"
    )
    print(f"[5. ANALİZ close] {saat} İST — {len(lines)} pozisyon kapatıldı")


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

    # Mevcut ET saati (EDT = UTC-4)
    et_now   = now - timedelta(hours=4)
    et_hour  = et_now.hour

    # Pozisyon aç + Polymarket order
    for sig in results:
        if sig["amount"] > 0 and sig["predicted_dir"]:
            pos = {
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
            }
            # Sadece gerçek Polymarket orderı varsa pozisyon aç
            pm = _pm_find_market(sig["symbol"], et_hour, now)
            if not pm or not pm.get("active") or pm.get("closed"):
                print(f"[5. ANALİZ] {sig['symbol']} market bulunamadı/kapalı", file=sys.stderr)
                continue
            token_id = pm["up_token"] if sig["predicted_dir"] == "UP" else pm["down_token"]
            order    = _pm_place_order(token_id, sig["amount"], pm["tick_size"], pm["neg_risk"])
            if not order:
                print(f"[5. ANALİZ] {sig['symbol']} PM order başarısız, pozisyon açılmadı", file=sys.stderr)
                continue
            pos["pm_slug"]        = pm["slug"]
            pos["pm_title"]       = pm["title"]
            pos["pm_token_id"]    = token_id
            pos["pm_token_dir"]   = sig["predicted_dir"]
            pos["pm_size"]        = order["size"]
            pos["pm_entry_price"] = order["price"]
            pos["pm_order_id"]    = order["order_id"]
            pos["pm_spent"]       = order["spent"]
            print(f"[5. ANALİZ] PM order: {sig['symbol']} {sig['predicted_dir']} "
                  f"{order['size']} shares @ {order['price']} (${order['spent']:.2f})")
            state["open_positions"].append(pos)

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

        # PM order bilgisi (sadece başarılı olanlar state'e eklendi)
        matched_pos = next(
            (p for p in state["open_positions"] if p["symbol"] == sym),
            None
        )
        if not matched_pos:
            continue  # PM order açılamamış, gösterme
        pm_str = ""
        if matched_pos.get("pm_order_id") == "DRY_RUN":
            pm_str = f"\n   🔶 DRY RUN: {matched_pos.get('pm_size',0):.1f} shares @ {matched_pos.get('pm_entry_price',0):.2f}"
        else:
            pm_str = f"\n   🟩 PM: {matched_pos.get('pm_size',0):.1f} shares @ {matched_pos.get('pm_entry_price',0):.2f} (${matched_pos.get('pm_spent',0):.2f})"

        lines.append(
            f"{dir_icon} <b>{name}</b>  {dir_tr}  skor:{score:+d}/4  giriş:{sig['price']:.2f}\n"
            f"   {vote_icons[0]}   {vote_icons[1]}\n"
            f"   {vote_icons[2]}   {vote_icons[3]}\n"
            f"   🕐 {hour_tr:02d}:00→{next_h} başarı: {_wr(hour_wins, hour_total, warn_low=low_data)}"
            f"  |  genel: {_wr(sym_wins, sym_total)}"
            f"{pm_str}"
        )

    skip_lines = [
        f"⛔ {s['symbol'].replace('USDT','')}  skor:{s['score']:+d}/4  → işlem açılmadı"
        for s in skipped
    ]

    parts = [sep, f"🆕 <b>5. ANALİZ — {saat} - {next_h} Yeni İşlemler</b>"]

    if lines:
        parts.extend(lines)
    else:
        parts.append("⏸ <i>Bu saat yeterli sinyal yok (|skor| ≤ 1).</i>")

    if skip_lines:
        parts.append(mini_sep)
        parts.extend(skip_lines)
        parts.append(mini_sep)

    pm_bal     = _pm_get_balance()
    pm_bal_str = f"${pm_bal:.2f}" if pm_bal >= 0 else "?"
    pm_at_risk = sum(p.get("pm_spent", 0) for p in state["open_positions"])
    parts.append(f"🟢 PM Bütçe: {pm_bal_str}  |  📂 Açık: {len(state['open_positions'])} poz  ${pm_at_risk:.2f} riskte")
    parts.append(
        f"<i>Eşik: |skor|≥3→{AMOUNT_STRONG:.0f}$  |skor|=2→{AMOUNT_MODERATE:.0f}$  ≤1→yok</i>"
    )
    parts.append(sep)

    tg_send("\n".join(parts))
    print(f"[5. ANALİZ open] {saat} İST — {len(opened)} işlem açıldı, {len(skipped)} elenendi")


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

    rate = np.full((7, 24), np.nan)
    for d in range(7):
        for h in range(24):
            if grid_n[d][h] >= 3:
                rate[d][h] = grid_w[d][h] / grid_n[d][h]

    fig, ax = plt.subplots(figsize=(16, 5))
    fig.patch.set_facecolor("#0a0e1a")
    ax.set_facecolor("#0a0e1a")

    cmap = mcolors.LinearSegmentedColormap.from_list(
        "green", ["#001a00", "#1b5e20", "#00e676"], N=256
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
                clr = "white" if rate[d][h] >= 0.55 else "#78909c"
                sym_parts = []
                for sn in sym_names:
                    sw = grid_sym[sn]["w"][d][h]
                    sn_total = grid_sym[sn]["n"][d][h]
                    if sn_total > 0:
                        sym_parts.append(f"{sn}:{sw}")
                sym_str = " ".join(sym_parts)
                ax.text(h, d, f"%{pct}\n{sym_str}", ha="center", va="center",
                        fontsize=5, color=clr, linespacing=1.4)

    for x in range(25): ax.axvline(x - 0.5, color="#0a0e1a", linewidth=0.5)
    for y in range(8):  ax.axhline(y - 0.5, color="#0a0e1a", linewidth=0.5)

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
        f"5. ANALİZ — Trend + MR + Orderflow + Funding  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
        f"Toplam: {total} işlem  |  {genel} doğruluk\n"
        f"{sym_line}",
        color="#00e676", fontsize=9, fontweight="bold", pad=10
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

    tg_send_photo(WEEKLY_IMG, f"⚡ 5. ANALİZ Haftalık Rapor — {now_tr.strftime('%d.%m.%Y %H:%M İST')}\n"
                              f"{total} işlem | {genel} | Trend+MR+OF+Funding")

    ind_lines = _ind_stats_lines(history)
    tg_send(
        f"📊 <b>5. ANALİZ HAFTALIK İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M İST')} İST\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {genel} başarı\n"
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"\n🔬 <b>Algoritma İsabet Oranı</b>\n" + "\n".join(ind_lines)
    )
    print(f"[5. ANALİZ weekly] gönderildi — {total} işlem")


# ── STATS ─────────────────────────────────────────────────────
def run_stats() -> None:
    history   = load_history()
    state     = load_state()
    now_tr    = datetime.now(timezone.utc).astimezone(_TZ_TR)

    if not history:
        tg_send("📊 <b>5. ANALİZ STATS</b>\nHenüz veri yok.")
        return

    total     = len(history)
    wins_all  = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"

    parts = [
        f"📊 <b>5. ANALİZ İSTATİSTİKLER</b>",
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Toplam: {total} işlem  |  {_wr(wins_all, total)}",
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}",
        f"Eşik: |skor|≥3→{AMOUNT_STRONG:.0f}$  |skor|=2→{AMOUNT_MODERATE:.0f}$",
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
    print("[5. ANALİZ stats] gönderildi")


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
