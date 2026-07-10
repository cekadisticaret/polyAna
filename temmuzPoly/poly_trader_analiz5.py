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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poly_predictor_analysis import predict

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

AMOUNT_STRONG   = 9.0    # konf >= %65 (sinyal eşiği, analiz1 uyumlu)
AMOUNT_MODERATE = 8.0    # konf >= %57 (sinyal eşiği, analiz1 uyumlu)
TRADE_AMOUNT_HIGH = 9.0   # genel başarı > %50
TRADE_AMOUNT_MID  = 8.0   # genel başarı veri yok veya = %50
TRADE_AMOUNT_LOW  = 7.0   # genel başarı < %50
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
    """Polymarket saatlik marketi bul. ET tarih+saatine göre slug oluşturur."""
    asset = _PM_ASSET_MAP.get(symbol)
    if not asset:
        return None
    # ET tarihi = UTC − 4 saat (UTC tarihini değil, ET tarihini kullan)
    et_date = date_utc - timedelta(hours=4)
    month = et_date.strftime("%B").lower()
    day   = et_date.day
    year  = et_date.year
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
            mesaj = str(resp)
            print(f"[5. ANALİZ] Order başarısız: {mesaj}", file=sys.stderr)
            _log_hata(token_id[:20], "order_basarisiz", mesaj)
            return None
        oid = resp.get("orderID") or resp.get("id", "")
        return {"order_id": oid, "size": size, "price": price, "spent": spent}
    except Exception as e:
        print(f"[5. ANALİZ] Order hatası: {e}", file=sys.stderr)
        _log_hata(token_id[:20], "order_exception", str(e))
        return None


# ── Hata Loglama ──────────────────────────────────────────────
_HATA_FILE = os.path.join(_DIR, "analiz1_polyhata.json")

def _log_hata(symbol: str, hata_turu: str, detay: str) -> None:
    try:
        kayitlar = []
        if os.path.exists(_HATA_FILE):
            with open(_HATA_FILE) as f:
                kayitlar = json.load(f)
        kayitlar.append({
            "zaman": datetime.now(timezone.utc).astimezone(_TZ_TR).isoformat(),
            "symbol": symbol,
            "hata_turu": hata_turu,
            "detay": detay,
        })
        with open(_HATA_FILE, "w") as f:
            json.dump(kayitlar, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        print(f"[5. ANALİZ] Hata loglanamadı: {ex}", file=sys.stderr)


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


# ── Tam sembol analizi (poly_predictor_analysis motoru) ───────
async def analyze(symbol: str) -> dict | None:
    try:
        pred_obj = await predict(symbol)
    except Exception as e:
        print(f"[5. ANALİZ] {symbol} predict hatası: {e}", file=sys.stderr)
        return None

    if pred_obj is None:
        return None

    conf    = max(pred_obj.prob_up, pred_obj.prob_down)
    amount  = AMOUNT_STRONG if conf >= 0.65 else AMOUNT_MODERATE  # eşik yok, her sinyal açılır

    ind_ema_raw = pred_obj.trend.upper()
    rsi_vote  = +1 if pred_obj.rsi < 50 else -1
    macd_vote = +1 if pred_obj.macd_bull else -1
    ema_vote  = (+1 if "YUKARI" in ind_ema_raw
                 else -1 if "AŞAĞI" in ind_ema_raw
                 else 0)
    score = rsi_vote + macd_vote + ema_vote

    return {
        "symbol":        symbol,
        "price":         pred_obj.current_price,
        "score":         score,
        "predicted_dir": pred_obj.predicted_dir,
        "amount":        amount,
        "conf":          conf,
        "votes":         [rsi_vote, macd_vote, ema_vote],
        "labels":        [f"RSI:{pred_obj.rsi:.0f}", f"MACD:{'bull' if pred_obj.macd_bull else 'bear'}", pred_obj.trend],
    }


# ── Algoritma isabet istatistiği ──────────────────────────────
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


# ── CLOSE ─────────────────────────────────────────────────────
async def run_close() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")

    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        tg_send(f"⏸ <b>5. ANALİZ ✦ PolyAktif İşlemler (1. Analiz) — {saat} İST</b>\nKapatılacak açık pozisyon yok.")
        print(f"[5. ANALİZ close] {saat} İST — açık pozisyon yok")
        return

    lines        = []
    tur_pm_spent = 0.0   # bu tur kapatılan pozisyonların toplam girilen miktarı
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
            "ind_rsi_ok":       _vote_ok(vs[0], actual) if len(vs) > 0 else None,
            "ind_macd_ok":      _vote_ok(vs[1], actual) if len(vs) > 1 else None,
            "ind_ema_ok":       _vote_ok(vs[2], actual) if len(vs) > 2 else None,
        })

        icon     = "✅" if win else "❌"
        name     = pos["symbol"].replace("USDT", "")
        pct      = (current_price - entry) / entry * 100
        pm_spent = pos.get("pm_spent", 0)
        tur_pm_spent += pm_spent
        # A1 ve A9 — girişteki yön (sonuç değil)
        a1_dir   = "↑" if pred == "UP" else "↓"
        a9_agree = pos.get("a9_agree")
        if a9_agree is True:
            a9_dir = a1_dir          # A9 aynı yönü seçti
        elif a9_agree is False:
            a9_dir = "↑" if pred == "DOWN" else "↓"  # A9 ters yön
        else:
            a9_dir = "—"             # A9 sessizdi
        lines.append(
            f"{icon} {name}  {pred}  {entry:.2f}→{current_price:.2f} ({pct:+.2f}%)  "
            f"skor:{pos.get('score', 0):+d}/3  -${pm_spent:.0f}  A1{a1_dir} A9{a9_dir}"
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

    closed_all  = len(history)
    dir_wins    = sum(1 for t in history if t["win"])
    pm_bal      = _pm_get_balance()
    pm_bal_str  = f"${pm_bal:.2f}" if pm_bal >= 0 else "?"
    genel_dir   = f"%{dir_wins/closed_all*100:.0f} ({closed_all})" if closed_all else "—"
    pnl_icon    = "🟢" if pm_tur_pnl >= 0 else "🔴"
    # Kapanan pozisyonların giriş saatinden açılış bilgisi (entry_time_tr'deki saat:dk)
    open_saat   = f"{int(saat[:2]):02d}:05"
    sep         = "━" * 26

    tg_send(
        f"{sep}\n"
        f"<b>5. ANALİZ ✦ PolyAktif İşlemler (1. Analiz) — {open_saat} - {saat}</b>\n"
        + "\n".join(lines) + "\n\n"
        f"{pnl_icon} Bütçe: {pm_bal_str}  ⛔ İşleme girilen miktar: ${tur_pm_spent:.0f}\n"
        f"Yön doğruluğu: {genel_dir}\n"
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
        sig = await analyze(sym)
        if sig:
            results.append(sig)

    # Mevcut ET saati (EDT = UTC-4)
    et_now   = now - timedelta(hours=4)
    et_hour  = et_now.hour

    # Analiz9 sinyallerini oku
    _A9_SIGNALS_FILE = "/tmp/analiz9_signals.json"
    a9_signals: dict[str, str] = {}
    try:
        if os.path.exists(_A9_SIGNALS_FILE):
            with open(_A9_SIGNALS_FILE) as _f:
                _a9 = json.load(_f)
            # Sadece aynı saatin verisini kullan
            if _a9.get("hour_tr") == hour_tr:
                a9_signals = _a9.get("signals", {})
                print(f"[5. ANALİZ] A9 sinyalleri okundu: {a9_signals}")
            else:
                print(f"[5. ANALİZ] A9 sinyali farklı saate ait ({_a9.get('hour_tr')} ≠ {hour_tr}), yok sayıldı")
    except Exception as _e:
        print(f"[5. ANALİZ] A9 sinyal okuma hatası: {_e}", file=sys.stderr)

    # Geçmiş başarı oranına göre baz miktar hesapla
    for sig in results:
        if sig["amount"] > 0:
            sw, st = get_symbol_stats(history, sig["symbol"])
            rate   = sw / st if st else None
            base   = (TRADE_AMOUNT_HIGH if (rate is not None and rate > 0.5)
                      else TRADE_AMOUNT_LOW if (rate is not None and rate < 0.5)
                      else TRADE_AMOUNT_MID)
            # Analiz9 ile karşılaştır
            a9_dir = a9_signals.get(sig["symbol"])
            if a9_dir:
                if a9_dir == sig["predicted_dir"]:
                    sig["amount"]   = 10.0   # İkisi aynı yön → güçlü sinyal
                    sig["a9_agree"] = True
                else:
                    sig["amount"]   = 0.0    # Ters yön → işlem açma
                    sig["a9_agree"] = False
            else:
                sig["amount"]   = 7.0        # A9 sessiz → sabit $7
                sig["a9_agree"] = None

    # A9'un sinyali olan ama analiz5'in signal üretemediği semboller → $6 giriş
    a5_syms = {s["symbol"] for s in results}
    for sym, a9_dir in a9_signals.items():
        if sym not in a5_syms and sym in SYMBOLS:
            results.append({
                "symbol":        sym,
                "predicted_dir": a9_dir,
                "price":         None,   # run_open'da fetch edilecek
                "amount":        7.0,
                "score":         0,
                "conf":          0.0,
                "votes":         [0, 0, 0],
                "labels":        ["A9-only", "", ""],
                "a9_agree":      None,
                "a9_only":       True,
            })

    # Pozisyon aç + Polymarket order
    _market_skip    = []   # market bulunamadı/kapalı
    _order_fail     = []   # PM order başarısız
    _newly_opened   = 0
    for sig in results:
        if sig["amount"] > 0 and sig["predicted_dir"]:
            # A9-only sinyaller için fiyat çek
            if sig.get("a9_only") and sig.get("price") is None:
                try:
                    sig["price"] = fetch_price(sig["symbol"])
                except Exception as _fe:
                    print(f"[5. ANALİZ] {sig['symbol']} A9-only fiyat çekme hatası: {_fe}", file=sys.stderr)
                    _log_hata(sig["symbol"], "a9only_fiyat_hatasi", str(_fe))
                    _order_fail.append(sig)
                    continue

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
                "a9_agree":         sig.get("a9_agree"),
                "a9_only":          sig.get("a9_only", False),
            }
            # Sadece gerçek Polymarket orderı varsa pozisyon aç
            pm = _pm_find_market(sig["symbol"], et_hour, now)
            if not pm or not pm.get("active") or pm.get("closed"):
                durum = "bulunamadı" if not pm else "kapalı"
                print(f"[5. ANALİZ] {sig['symbol']} market {durum}", file=sys.stderr)
                _log_hata(sig["symbol"], "market_" + durum, f"et_hour={et_hour} slug aranıyor")
                _market_skip.append(sig)
                continue
            token_id = pm["up_token"] if sig["predicted_dir"] == "UP" else pm["down_token"]
            order    = _pm_place_order(token_id, sig["amount"], pm["tick_size"], pm["neg_risk"])
            if not order:
                print(f"[5. ANALİZ] {sig['symbol']} PM order başarısız, pozisyon açılmadı", file=sys.stderr)
                _log_hata(sig["symbol"], "order_basarisiz", f"dir={sig['predicted_dir']} amount={sig['amount']}")
                _order_fail.append(sig)
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
            _newly_opened += 1

    save_state(state)

    next_h   = f"{(hour_tr + 1) % 24:02d}:00"
    sep      = "━" * 26
    mini_sep = "━" * 10
    # Gerçekten bu turda açılan pozisyonlar (state'e eklenenler)
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

        # A9 ikonu
        a9_agree = sig.get("a9_agree")
        if a9_agree is True:
            a9_icon = "✅"
        elif a9_agree is False:
            a9_icon = "❌"
        elif sig.get("a9_only"):
            a9_icon = "🔹"
        else:
            a9_icon = "—"

        pm_spent_str = f"${matched_pos.get('pm_spent', 0):.0f}"
        lines.append(
            f"{dir_icon} <b>{name}</b>  {dir_tr}  {sig['price']:.2f}  skor:{score:+d}/3  {pm_spent_str} risk"
            f"  A9 {a9_icon}"
        )

    skip_lines = [
        f"⛔ {s['symbol'].replace('USDT','')} ({s['predicted_dir']}) → açılmadı (ters yön)"
        for s in skipped
    ]

    parts = [sep, f"<b>5. ANALİZ ✦ PolyAktif İşlemler (1. Analiz) — {saat} - {next_h}</b>"]

    if lines:
        parts.extend(lines)
        parts.append("")  # boş satır
    elif not any(s["amount"] > 0 for s in results):
        parts.append("⏸ <i>Bu saat sinyal yok.</i>")
    else:
        reasons = []
        if _market_skip:
            names = ", ".join(s["symbol"].replace("USDT", "") for s in _market_skip)
            reasons.append(f"market yok: {names}")
        if _order_fail:
            names = ", ".join(s["symbol"].replace("USDT", "") for s in _order_fail)
            reasons.append(f"order hatası: {names}")
        parts.append(f"⛔ <i>Sinyal var ama işlem açılmadı — {' | '.join(reasons)}</i>")
        parts.append("")

    if skip_lines:
        parts.extend(skip_lines)
        parts.append("")

    if _newly_opened > 0:
        time.sleep(3)  # Polymarket bakiyesinin güncellenmesi için bekle
    pm_bal        = _pm_get_balance()
    pm_at_risk    = sum(p.get("pm_spent", 0) for p in state["open_positions"])
    tur_spent_sum = sum(
        p.get("pm_spent", 0) for p in state["open_positions"]
        if p.get("entry_hour_tr") == hour_tr
    )
    pm_bal_str    = f"${pm_bal:.2f}" if pm_bal >= 0 else "?"
    bal_icon      = "🟢" if pm_bal > 150 else "🟡" if pm_bal > 50 else "🔴"

    closed_all = len(history)
    dir_wins   = sum(1 for t in history if t["win"])
    genel_dir  = f"%{dir_wins/closed_all*100:.0f} ({closed_all})" if closed_all else "—"

    parts.append(f"{bal_icon} Bütçe: {pm_bal_str}  ⛔ İşleme girilen miktar: ${tur_spent_sum:.0f}")
    parts.append(f"Yön doğruluğu: {genel_dir}")
    parts.append(sep)

    tg_send("\n".join(parts))
    print(f"[5. ANALİZ open] {saat} İST — {_newly_opened} işlem açıldı, {len(skipped)} elenendi")


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
    im = ax.imshow(np.ma.masked_invalid(rate), cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")

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
                    sw = grid_sym[sn]["w"][d][h]
                    sn_total = grid_sym[sn]["n"][d][h]
                    if sn_total > 0:
                        sym_parts.append(f"{sn}:+{sw}-{sn_total - sw}")
                sym_str = "\n".join(sym_parts)
                ax.text(h, d, f"%{pct}({n})\n{sym_str}", ha="center", va="center",
                        fontsize=5, color=clr, fontweight="bold", linespacing=1.5)

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
