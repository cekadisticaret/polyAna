"""
A1 LIVE — Analiz 1 Motoru (Gerçek Polymarket)

Algoritma: poly_predictor_analysis.py — Analiz 1 ile aynı (RSI + MACD + EMA).
Sabit $8–10–12/işlem (WR'ye göre), BTC+SOL.

Hafta sonu: dashboard anahtarı (Cum 22:00 otomatik kapanır · Pzt 12:00 açılır; manuel override mümkün).
Modlar: close (:02 — PM sonucu için) / open (:05) / weekly / stats
"""
import asyncio
import json
import math
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poly_predictor_analysis import predict, _fetch_klines
from pm_trader_helpers import (
    sanal_pnl, pm_realized_pnl, pm_tg_stake, resolve_open_slot_gates,
    slot_amount_log, skip_if_weekend_pause, pm_live_wr_amount, pm_live_amount_range_str,
)

# .env yükle
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from telegram_poly_channels import chat_pm_live

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8529258517:AAHuVn1VFftXK7RR2Z1w3UqyHGuHNDXDYI4"
CHAT_ID   = chat_pm_live()  # PolyAktif — 1. ANALİZ kanalından ayrı
LABEL     = "A1 LIVE"
_TZ_TR    = ZoneInfo("Europe/Istanbul")

_DIR              = os.path.dirname(os.path.abspath(__file__))
STATE_FILE        = os.path.join(_DIR, "poly_trader_analiz5_state.json")
HISTORY_FILE      = os.path.join(_DIR, "poly_trader_analiz5_history.json")
ALGO_ACCURACY_FILE = os.path.join(_DIR, "algo_accuracy.json")
_ALGO_SIGNALS_FILE = "/tmp/algo_signals.json"
WEEKLY_IMG   = "/tmp/poly_analiz5_weekly_heatmap.png"

INITIAL_BALANCE = 300.0
SYMBOLS            = ["BTCUSDT", "SOLUSDT"]
TRADE_AMOUNT       = 10.0  # genel WR veri yok veya tam %50
TRADE_AMOUNT_HIGH  = 12.0  # sembol genel WR > %50
TRADE_AMOUNT_LOW   = 8.0   # sembol genel WR < %50
MIN_STAT_COUNT  = 10


def _load_algo_snapshot() -> dict:
    """Mevcut algo_signals.json'dan per-sembol sinyal snapshot'ı döner."""
    try:
        if os.path.exists(_ALGO_SIGNALS_FILE):
            with open(_ALGO_SIGNALS_FILE) as f:
                data = json.load(f)
            # {algo_num: {"BTC": "UP", "ETH": "DOWN", ...}, ...}
            return data.get("signals", {})
    except Exception:
        pass
    return {}

def _update_algo_accuracy(pos: dict, win: bool) -> None:
    """Kapanan pozisyona göre her algoritmanın doğruluğunu günceller (genel + sembol bazlı)."""
    snapshot = pos.get("algo_snapshot", {})
    if not snapshot:
        return
    sym    = pos["symbol"].replace("USDT", "")
    pred   = pos["predicted_dir"]
    actual = pred if win else ("DOWN" if pred == "UP" else "UP")
    try:
        acc = {}
        if os.path.exists(ALGO_ACCURACY_FILE):
            with open(ALGO_ACCURACY_FILE) as f:
                acc = json.load(f)
        for algo_num, sigs in snapshot.items():
            algo_sig = sigs.get(sym) if isinstance(sigs, dict) else sigs
            if algo_sig not in ("UP", "DOWN"):
                continue
            correct = 1 if algo_sig == actual else 0
            # Genel toplam
            if algo_num not in acc:
                acc[algo_num] = {"name": "", "total": 0, "correct": 0, "by_sym": {}}
            acc[algo_num]["total"]   += 1
            acc[algo_num]["correct"] += correct
            # Sembol bazlı
            by_sym = acc[algo_num].setdefault("by_sym", {})
            if sym not in by_sym:
                by_sym[sym] = {"total": 0, "correct": 0}
            by_sym[sym]["total"]   += 1
            by_sym[sym]["correct"] += correct
        with open(ALGO_ACCURACY_FILE, "w") as f:
            json.dump(acc, f, indent=2)
    except Exception as e:
        print(f"[A1 LIVE] algo accuracy güncelleme hatası: {e}", file=sys.stderr)

# ── Polymarket Config ──────────────────────────────────────────
_PM_CLOB_HOST = "https://clob.polymarket.com"
_PM_GAMMA_URL = "https://gamma-api.polymarket.com/events"
_PM_HEADERS   = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_PM_ASSET_MAP = {"BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
                 "XRPUSDT": "xrp", "DOGEUSDT": "dogecoin", "BNBUSDT": "bnb"}
_PM_DRY_RUN   = os.getenv("POLY_DRY_RUN", "true").lower() == "true"

from pm_balance_guard import can_open_trade

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
            print(f"[A1 LIVE] Client init ({attempt+1}/3): {e}", file=sys.stderr)
            time.sleep(2)
    raise RuntimeError("Polymarket client oluşturulamadı")


def _pm_fetch_resolution(slug: str) -> dict | None:
    """PM market sonucu. Kesinleşmediyse None.
    closed=False olsa bile outcomePrices 0.99/0.01 ise sonuç sayılır.
    """
    if not slug:
        return None
    try:
        req = urllib.request.Request(
            f"{_PM_GAMMA_URL}?slug={slug}",
            headers=_PM_HEADERS,
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            pm_data = json.load(r)
        if not pm_data:
            return None
        pm_ev = pm_data[0]
        pm_m = pm_ev.get("markets", [{}])[0]
        raw_op = pm_m.get("outcomePrices")
        op = json.loads(raw_op) if isinstance(raw_op, str) else (raw_op or [])
        if not op or len(op) < 1:
            return None
        up_p = float(op[0])
        down_p = float(op[1]) if len(op) > 1 else (1.0 - up_p)
        closed = bool(pm_ev.get("closed"))
        decisive = up_p >= 0.99 or down_p >= 0.99 or up_p <= 0.01
        if not (closed or decisive):
            return None
        if up_p >= 0.99 or (decisive and up_p > down_p):
            up_won = True
        elif down_p >= 0.99 or up_p <= 0.01:
            up_won = False
        else:
            return None
        return {
            "up_won": up_won,
            "closed": closed,
            "up_price": up_p,
            "down_price": down_p,
            "title": pm_ev.get("title"),
        }
    except Exception as e:
        print(f"[A1 LIVE close] PM sonuç hatası ({slug}): {e}", file=sys.stderr)
        return None


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


def _pm_slot_label(pos: dict) -> str:
    """TG satırı: 07:00→08:00 İST · 12AM ET"""
    h = pos.get("entry_hour_tr")
    if h is None:
        return ""
    end = (int(h) + 1) % 24
    ist = f"{int(h):02d}:00→{end:02d}:00 İST"
    title = pos.get("pm_title") or ""
    if ", " in title and title.rstrip().endswith("ET"):
        et = title.rsplit(", ", 1)[-1].strip()
        return f"{ist} · {et}"
    slug = pos.get("pm_slug") or ""
    m = re.search(r"-(\d{1,2}(?:am|pm))-et$", slug, re.I)
    if not m:
        return ist
    raw = m.group(1).lower()
    if raw == "12am":
        et = "12AM ET"
    elif raw == "12pm":
        et = "12PM ET"
    elif raw.endswith("am"):
        et = f"{int(raw[:-2])}AM ET"
    else:
        et = f"{int(raw[:-2])}PM ET"
    return f"{ist} · {et}"


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
            print(f"[A1 LIVE] Gamma hatası ({slug}): {e}", file=sys.stderr)
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
                    neg_risk: bool = False, _retry: bool = True) -> dict | None:
    """token_id'yi amount_usd kadar satın al (FAK). Hata alırsa 10sn sonra 1 kez tekrar dener."""
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
            print(f"[A1 LIVE] Order başarısız: {mesaj}", file=sys.stderr)
            if _retry:
                print(f"[A1 LIVE] 10sn sonra tekrar deneniyor...", file=sys.stderr)
                time.sleep(10)
                return _pm_place_order(token_id, amount_usd, tick_size, neg_risk, _retry=False)
            _log_hata(token_id[:20], "order_basarisiz", mesaj)
            return None
        oid = resp.get("orderID") or resp.get("id", "")
        return {"order_id": oid, "size": size, "price": price, "spent": spent}
    except Exception as e:
        print(f"[A1 LIVE] Order hatası: {e}", file=sys.stderr)
        if _retry:
            print(f"[A1 LIVE] 10sn sonra tekrar deneniyor...", file=sys.stderr)
            time.sleep(10)
            return _pm_place_order(token_id, amount_usd, tick_size, neg_risk, _retry=False)
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
        print(f"[A1 LIVE] Hata loglanamadı: {ex}", file=sys.stderr)


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


def _trade_amount(history: list, symbol: str) -> float:
    """Sembol genel WR'ye göre tutar — dashboard Ayarlar (a1_amount_*)."""
    return pm_live_wr_amount("a1", history, symbol, get_symbol_stats)


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
    """Eski ad — fapi yok. kline/fiyat WS+spot; depth boş."""
    params = params or {}
    sym = str(params.get("symbol") or "")
    if path.endswith("/klines"):
        root = os.path.dirname(_DIR)
        if root not in sys.path:
            sys.path.insert(0, root)
        from binance_fapi_guard import public_klines
        return public_klines(
            sym,
            str(params.get("interval") or "1h"),
            int(params.get("limit") or 60),
            start_time_ms=params.get("startTime"),
        )
    if path.endswith("/ticker/price"):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        from binance_fapi_guard import get_last, get_mark
        px = get_last(sym) or get_mark(sym) or 0
        return {"price": px}
    if path.endswith("/premiumIndex"):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        from binance_fapi_guard import ws_premium
        hit = ws_premium(sym) or {}
        return {"lastFundingRate": hit.get("last_funding_rate") or 0, "markPrice": hit.get("mark") or 0}
    if path.endswith("/depth"):
        return {"bids": [], "asks": []}
    return {}


def fetch_klines(symbol: str, limit: int = 60) -> list[dict]:
    raw = _binance_get("/fapi/v1/klines", {"symbol": symbol, "interval": "1h", "limit": limit})
    return [{"open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
             "close": float(k[4]), "volume": float(k[5])} for k in raw]


def fetch_orderbook(symbol: str) -> dict:
    return {"bids": [], "asks": []}


def fetch_funding_rate(symbol: str) -> float:
    data = _binance_get("/fapi/v1/premiumIndex", {"symbol": symbol})
    return float(data.get("lastFundingRate", 0) or 0)


def fetch_price(symbol: str) -> float:
    """Anlık fiyat — WS mark/last."""
    data = _binance_get("/fapi/v1/ticker/price", {"symbol": symbol})
    return float(data.get("price") or 0)


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
        print(f"[A1 LIVE] {symbol} predict hatası: {e}", file=sys.stderr)
        return None

    if pred_obj is None:
        return None

    conf    = max(pred_obj.prob_up, pred_obj.prob_down)

    ind_ema_raw = pred_obj.trend.upper()
    rsi_vote  = +1 if pred_obj.rsi < 50 else -1
    macd_vote = +1 if pred_obj.macd_bull else -1
    ema_vote  = (+1 if "YUKARI" in ind_ema_raw
                 else -1 if "AŞAĞI" in ind_ema_raw
                 else 0)
    score = rsi_vote + macd_vote + ema_vote

    # Analiz 1 ile aynı: saatin başı fiyatı = Polymarket Price to Beat
    try:
        klines = await _fetch_klines(symbol, "1h", 3)
        price_to_beat = klines[-2]["close"] if klines and len(klines) >= 2 else pred_obj.current_price
    except Exception:
        price_to_beat = pred_obj.current_price

    return {
        "symbol":        symbol,
        "price":         price_to_beat,
        "current_price": pred_obj.current_price,
        "score":         score,
        "predicted_dir": pred_obj.predicted_dir,
        "amount":        TRADE_AMOUNT,
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
    if skip_if_weekend_pause("A1 LIVE", "close", now_tr):
        return

    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        print(f"[A1 LIVE close] {saat} İST — açık pozisyon yok")
        return

    lines        = []
    tur_pm_spent = 0.0   # bu tur toplam girilen miktar
    tur_pnl      = 0.0   # bu tur yön bazlı P&L tahmini
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
                    print(f"[A1 LIVE close] {pos['symbol']} fiyat hatası: {e}", file=sys.stderr)
                    failed_pos.append(pos)

        if klines is None:
            continue

        current_price = klines[-1]["close"]
        entry  = pos["entry_price"]
        pred   = pos["predicted_dir"]
        amount = pos.get("amount", TRADE_AMOUNT)
        binance_actual = "UP" if current_price >= entry else "DOWN"
        binance_win = (pred == binance_actual)

        # Gerçek PM emri varsa → PM sonucu esas; yoksa Binance fallback
        has_pm = bool(pos.get("pm_slug") and pos.get("pm_order_id") and not pos.get("pm_error"))
        pm_win = None
        pm_source = False
        if has_pm:
            res = _pm_fetch_resolution(pos["pm_slug"])
            if res is None:
                # Henüz kesinleşmedi — Binance ile kapatma; sonraki close'a bırak
                print(
                    f"[A1 LIVE close] {pos['symbol']} PM sonucu bekleniyor "
                    f"({pos.get('pm_slug')}) — ertelendi",
                    file=sys.stderr,
                )
                failed_pos.append(pos)
                continue
            token_dir = pos.get("pm_token_dir") or pred
            pm_win = (token_dir == "UP" and res["up_won"]) or (
                token_dir == "DOWN" and not res["up_won"]
            )
            actual = "UP" if res["up_won"] else "DOWN"
            win = bool(pm_win)
            pm_source = True
        else:
            actual = binance_actual
            win = binance_win

        pm_spent = float(pos.get("pm_spent") or amount or 0)
        pm_size = float(pos.get("pm_size") or 0)
        if pm_source and pm_size > 0 and pm_spent > 0:
            pnl_line = pm_realized_pnl(pos, win)
        else:
            pnl_line = sanal_pnl(pos, win)
        if pm_source:
            pm_tur_pnl += pnl_line

        vs = pos.get("votes", [])
        history.append({
            "symbol":           pos["symbol"],
            "predicted_dir":    pred,
            "actual_dir":       actual,
            "binance_actual":   binance_actual,
            "win":              win,
            "pm_win":           pm_win,
            "settle_source":    "pm" if pm_source else "binance",
            "entry_price":      entry,
            "exit_price":       current_price,
            "entry_time_tr":    pos["entry_time_tr"],
            "entry_hour_tr":    pos["entry_hour_tr"],
            "entry_dow":        pos["entry_dow"],
            "entry_is_weekend": pos["entry_is_weekend"],
            "score":            pos.get("score", 0),
            "amount":           amount,
            "pm_spent":         pos.get("pm_spent"),
            "pm_size":          pos.get("pm_size"),
            "pm_entry_price":   pos.get("pm_entry_price"),
            "pm_order_id":      pos.get("pm_order_id"),
            "pm_slug":          pos.get("pm_slug"),
            "pm_token_dir":     pos.get("pm_token_dir"),
            "pm_spent_original": pos.get("pm_spent_original"),
            "pm_partial_received": pos.get("pm_partial_received"),
            "pm_partial_sold_size": pos.get("pm_partial_sold_size"),
            "pm_partial_tp_done": pos.get("pm_partial_tp_done"),
            "a9_agree":         pos.get("a9_agree"),
            "exit_time_tr":     now_tr.isoformat(),
            "pnl":              pnl_line,
            "ind_rsi_ok":       _vote_ok(vs[0], actual) if len(vs) > 0 else None,
            "ind_macd_ok":      _vote_ok(vs[1], actual) if len(vs) > 1 else None,
            "ind_ema_ok":       _vote_ok(vs[2], actual) if len(vs) > 2 else None,
        })

        # Algoritma doğruluk: yön tahmini vs gerçekleşen (PM varsa PM yönü)
        _update_algo_accuracy(pos, win)

        icon     = "✅" if win else "❌"
        name     = pos["symbol"].replace("USDT", "")
        pct      = (current_price - entry) / entry * 100
        src_tag  = "🎯PM" if pm_source else "BN"
        bn_note  = ""
        if pm_source and binance_win != win:
            bn_note = f"  (BN:{'✅' if binance_win else '❌'})"
        tur_pnl += pnl_line
        slot = _pm_slot_label(pos)
        slot_part = f"  {slot}" if slot else ""
        lines.append(
            f"{icon} {name}  {pred}{slot_part}  {entry:.2f}→{current_price:.2f} ({pct:+.2f}%)  "
            f"{pm_tg_stake(pos)}  net {'+' if pnl_line >= 0 else ''}{pnl_line:.2f}$  "
            f"{src_tag}{bn_note}  skor:{pos.get('score', 0):+d}/3"
        )

    # Başarısız pozisyonları bir sonraki saate bırak
    state["open_positions"] = failed_pos
    save_state(state)
    save_history(history)

    # Hata olan pozisyonlar için bildirim
    if failed_pos:
        names = ", ".join(p["symbol"].replace("USDT", "") for p in failed_pos)
        print(f"[A1 LIVE close] {saat} — fiyat alınamadı: {names}")

    if not lines:
        print(f"[A1 LIVE close] {saat} İST — kapatılan pozisyon yok")
        return

    # total_pnl güncelle
    state["total_pnl"] = state.get("total_pnl", 0.0) + tur_pnl
    save_state(state)

    closed_all   = len(history)
    dir_wins     = sum(1 for t in history if t["win"])
    pm_bal       = _pm_get_balance()
    pm_bal_str   = f"${pm_bal:.2f}" if pm_bal >= 0 else "?"
    genel_str    = f"%{dir_wins/closed_all*100:.0f} ({closed_all} işlem)" if closed_all else "—"
    total_pnl    = state["total_pnl"]
    pnl_icon     = "🟢" if total_pnl >= 0 else "🔴"
    tur_pnl_str  = f"{'+'if tur_pnl >= 0 else ''}{tur_pnl:.0f}$"
    sep          = "━" * 26

    tg_send(
        f"{sep}\n"
        f"🏁 <b>A1 LIVE — {saat} Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {tur_pnl_str}  |  Bakiye: {pm_bal_str}\n"
        f"{pnl_icon} Toplam P&L: {'+'if total_pnl >= 0 else ''}{total_pnl:.2f}$  |  Genel: {genel_str}\n"
        f"{sep}"
    )
    print(f"[A1 LIVE close] {saat} İST — {len(lines)} pozisyon kapatıldı")


# ── OPEN ──────────────────────────────────────────────────────
def _try_pm_open(
    state: dict, sig: dict, *, hour_tr: int, dow: int, is_weekend: bool,
    now_tr: datetime, now: datetime, amount: float, algo_snapshot: dict,
) -> tuple[dict | None, str | None]:
    """PM pozisyonu açmayı dener. (pos, hata_tipi) döner."""
    et_hour = (now - timedelta(hours=4)).hour
    pos = {
        "symbol":           sig["symbol"],
        "predicted_dir":    sig["predicted_dir"],
        "entry_price":      sig.get("price") or sig.get("entry_price"),
        "entry_time_tr":    now_tr.isoformat(),
        "entry_hour_tr":    hour_tr,
        "entry_dow":        dow,
        "entry_is_weekend": is_weekend,
        "score":            sig.get("score", 0),
        "amount":           amount,
        "votes":            sig.get("votes", []),
    }
    pm = _pm_find_market(sig["symbol"], et_hour, now)
    if not pm or not pm.get("active") or pm.get("closed"):
        durum = "bulunamadı" if not pm else "kapalı"
        print(f"[A1 LIVE] {sig['symbol']} market {durum}", file=sys.stderr)
        _log_hata(sig["symbol"], "market_" + durum, f"et_hour={et_hour} slug aranıyor")
        return None, "market"
    token_id = pm["up_token"] if sig["predicted_dir"] == "UP" else pm["down_token"]
    order = _pm_place_order(token_id, amount, pm["tick_size"], pm["neg_risk"])
    if not order:
        dir_f = sig["predicted_dir"]
        print(f"[A1 LIVE] {sig['symbol']} PM order başarısız", file=sys.stderr)
        _log_hata(sig["symbol"], "order_basarisiz", f"dir={dir_f} amount={amount}")
        return None, "order"
    pos.update({
        "pm_slug": pm["slug"], "pm_title": pm["title"], "pm_token_id": token_id,
        "pm_token_dir": sig["predicted_dir"], "pm_size": order["size"],
        "pm_entry_price": order["price"], "pm_order_id": order["order_id"],
        "pm_spent": order["spent"], "algo_snapshot": algo_snapshot,
    })
    print(f"[A1 LIVE] PM order: {sig['symbol']} {sig['predicted_dir']} "
          f"{order['size']} shares @ {order['price']} (${order['spent']:.2f})")
    state["open_positions"].append(pos)
    return pos, None


async def run_open() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")
    history = load_history()
    if skip_if_weekend_pause("A1 LIVE", "open", now_tr, history=history):
        return

    hour_tr    = now_tr.hour
    dow        = now_tr.weekday()
    is_weekend = dow >= 5

    state   = load_state()

    # PM bakiye kontrolü
    if not _PM_DRY_RUN and not can_open_trade(LABEL, tg_send):
        return

    cold_skip, _, _, _, cold_note = resolve_open_slot_gates(history, hour_tr, 0)
    if cold_skip:
        print(f"[A1 LIVE open] {saat} — {cold_note} → işlem yok")
        return

    results = []
    for sym in SYMBOLS:
        sig = await analyze(sym)
        if not sig or not sig.get("predicted_dir"):
            continue
        results.append(sig)

    _algo_snapshot = _load_algo_snapshot()

    # Pozisyon aç + Polymarket order
    _market_skip    = []
    _order_fail     = []
    _newly_opened   = 0
    for sig in results:
        if sig["predicted_dir"]:
            base = _trade_amount(history, sig["symbol"])
            _sk, amount, hot_boost, cold_cut, gate_note = resolve_open_slot_gates(
                history, hour_tr, base
            )
            if gate_note:
                print(f"[A1 LIVE open] {gate_note}")
            slot_amount_log("A1 LIVE", hour_tr, base, amount, hot_boost, cold_cut)
            pos, err = _try_pm_open(
                state, sig, hour_tr=hour_tr, dow=dow, is_weekend=is_weekend,
                now_tr=now_tr, now=now, amount=amount,
                algo_snapshot=_algo_snapshot,
            )
            if pos:
                _newly_opened += 1
            elif err == "market":
                _market_skip.append(sig)
            elif err == "order":
                name_f = sig["symbol"].replace("USDT", "")
                print(f"[A1 LIVE] {name_f} ({sig['predicted_dir']}) PM order başarısız")
                _order_fail.append(sig)

    save_state(state)

    next_h   = f"{(hour_tr + 1) % 24:02d}:00"
    sep      = "━" * 26
    trade_lines = []
    for sig in results:
        name = sig["symbol"].replace("USDT", "")
        opened_pos = next((p for p in state["open_positions"] if p["symbol"] == sig["symbol"]), None)
        if opened_pos:
            d_icon = "📈" if opened_pos["predicted_dir"] == "UP" else "📉"
            d_tr   = "UP" if opened_pos["predicted_dir"] == "UP" else "DOWN"
            entry  = opened_pos.get("entry_price", 0)
            pm_spent = opened_pos.get("pm_spent", 0) or 0
            pm_size  = opened_pos.get("pm_size", 0) or 0
            to_win = f" → ${pm_size:.2f} kazanılacak" if pm_size > 0 else ""
            slot = _pm_slot_label(opened_pos)
            slot_part = f"  {slot}" if slot else ""
            trade_lines.append(
                f"  {d_icon} <b>{name}</b> {d_tr}{slot_part}  giriş:{entry:.2f}  ${pm_spent:.2f} risk{to_win}"
            )
        else:
            conf = sig.get("conf", 0) * 100
            d_tr = "UP" if sig["predicted_dir"] == "UP" else "DOWN"
            trade_lines.append(f"  ⛔ <b>{name}</b> {d_tr} konf:%{conf:.0f}  → girilmedi")

    error_lines = []
    if _market_skip:
        names = ", ".join(s["symbol"].replace("USDT", "") for s in _market_skip)
        error_lines.append(f"⚠️ PM market yok: {names}")
    if _order_fail:
        names = ", ".join(s["symbol"].replace("USDT", "") for s in _order_fail)
        error_lines.append(f"⚠️ PM order hatası: {names}")

    if _newly_opened == 0:
        print(f"[A1 LIVE open] {saat} İST — işlem yok")
        return

    if _newly_opened > 0:
        time.sleep(3)
    pm_bal        = _pm_get_balance()
    tur_spent_sum = sum(
        p.get("pm_spent", 0) for p in state["open_positions"]
        if p.get("entry_hour_tr") == hour_tr
    )
    tur_to_win    = sum(
        p.get("pm_size", 0) or 0 for p in state["open_positions"]
        if p.get("entry_hour_tr") == hour_tr
    )
    pm_bal_str = f"${pm_bal:.2f}" if pm_bal >= 0 else "?"
    bal_icon   = "🟢" if pm_bal > 50 else "🟡" if pm_bal > 20 else "🔴"
    closed_all = len(history)
    dir_wins   = sum(1 for t in history if t["win"])
    genel_dir  = f"%{dir_wins/closed_all*100:.0f} ({closed_all})" if closed_all else "—"
    win_str    = f" → kazanılacak: ${tur_to_win:.2f}" if tur_to_win > 0 else ""

    opened_lines = [ln for ln in trade_lines if "giriş:" in ln]
    parts = [
        sep,
        f"<b>A1 LIVE ✦ PolyAktif (Analiz 1 motoru) — {saat} - {next_h}</b>",
        "",
        "📂 <b>İşleme Girilenler:</b>",
    ]
    parts.extend(opened_lines)

    if error_lines:
        parts.append("")
        parts.extend(error_lines)

    parts += [
        "",
        f"{bal_icon} Bütçe: {pm_bal_str}  ⛔ Risk: ${tur_spent_sum:.2f}{win_str}",
        f"Yön doğruluğu: {genel_dir}",
        sep,
    ]

    tg_send("\n".join(parts))
    print(f"[A1 LIVE open] {saat} İST — {_newly_opened} işlem açıldı")


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
        f"A1 LIVE — Trend + MR + Orderflow + Funding  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
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

    tg_send_photo(WEEKLY_IMG, f"⚡ A1 LIVE Haftalık Rapor — {now_tr.strftime('%d.%m.%Y %H:%M İST')}\n"
                              f"{total} işlem | {genel} | Trend+MR+OF+Funding")

    ind_lines = _ind_stats_lines(history)
    tg_send(
        f"📊 <b>A1 LIVE HAFTALIK İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M İST')} İST\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {genel} başarı\n"
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"\n🔬 <b>Algoritma İsabet Oranı</b>\n" + "\n".join(ind_lines)
    )
    print(f"[A1 LIVE weekly] gönderildi — {total} işlem")


# ── STATS ─────────────────────────────────────────────────────
def run_stats() -> None:
    history   = load_history()
    state     = load_state()
    now_tr    = datetime.now(timezone.utc).astimezone(_TZ_TR)

    if not history:
        tg_send("📊 <b>A1 LIVE STATS</b>\nHenüz veri yok.")
        return

    total     = len(history)
    wins_all  = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"

    parts = [
        f"📊 <b>A1 LIVE İSTATİSTİKLER</b>",
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Toplam: {total} işlem  |  {_wr(wins_all, total)}",
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}",
        f"İşlem: BTC+SOL  {pm_live_amount_range_str('a1')}/işlem WR'ye göre (Analiz 1 motoru)",
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
    print("[A1 LIVE stats] gönderildi")


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
