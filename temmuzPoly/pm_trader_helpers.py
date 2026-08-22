"""Polymarket order yardımcıları — gerçek PM trader'lar için ortak."""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from zoneinfo import ZoneInfo

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import binance_fapi_guard  # noqa: E402,F401  — fapi okuma kesici

_PM_CLOB_HOST = "https://clob.polymarket.com"
_PM_GAMMA_URL = "https://gamma-api.polymarket.com/events"
_PM_HEADERS   = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_PM_ASSET_MAP = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
    "XRPUSDT": "xrp", "DOGEUSDT": "dogecoin", "BNBUSDT": "bnb",
}
_TZ_TR = ZoneInfo("Europe/Istanbul")

# Hafta sonu duraklama: Cum 22:00 – Pzt resume_hour İST
WEEKEND_RESUME_HOUR = 11          # sanal + erken Live grupları
WEEKEND_RESUME_LATE_HOUR = 12     # A1 / A2 / A10 Live
PM_DRY_RUN = os.getenv("POLY_DRY_RUN", "true").lower() == "true"
PM_ORDER_ATTEMPTS = 3
PM_ORDER_NOT_READY_ATTEMPTS = 8  # "order manager not ready" → 10sn × 8 ≈ 70sn
PM_ORDER_RETRY_SEC = 10
# Manuel trade-desk: kısa retry (UI ~1 dk bekletmesin)
PM_ORDER_INTERACTIVE_ATTEMPTS = 3
PM_ORDER_INTERACTIVE_NOT_READY = 3
PM_ORDER_INTERACTIVE_RETRY_SEC = 2

_PM_CLIENT = None
_PM_CLIENT_TS = 0.0
_PM_CLIENT_TTL_SEC = 300.0  # API key yeniden türetmeyi kes
_PM_CLIENT_LOCK = None


def _pm_client_lock():
    global _PM_CLIENT_LOCK
    if _PM_CLIENT_LOCK is None:
        import threading
        _PM_CLIENT_LOCK = threading.Lock()
    return _PM_CLIENT_LOCK


def pm_invalidate_client() -> None:
    global _PM_CLIENT, _PM_CLIENT_TS
    with _pm_client_lock():
        _PM_CLIENT = None
        _PM_CLIENT_TS = 0.0


def _pm_order_not_ready(err: str | None) -> bool:
    low = (err or "").lower()
    return "order manager not ready" in low or (
        "please retry" in low and ("425" in low or "not ready" in low)
    )

# Gerçek PM trader'lar — A1 Live / A2 Live aynı Telegram kanalı (TELEGRAM_PM_LIVE_CHAT_ID)
PM_LIVE_TG_TOKEN = "8529258517:AAHuVn1VFftXK7RR2Z1w3UqyHGuHNDXDYI4"
PM_LIVE_TG_CHAT = "830754964"  # geriye uyumluluk; tg_send_pm_live chat_pm_live() kullanır


def tg_send_pm_live(text: str, *, label: str = "PM") -> bool:
    """A1 Live ile aynı PolyAktif bot + chat."""
    from telegram_poly_channels import chat_pm_live
    chat_id = chat_pm_live()
    if not chat_id:
        print(f"[{label} TG] PM live kanalı tanımlı değil (TELEGRAM_PM_LIVE_CHAT_ID) — atlandı")
        return False
    try:
        url = f"https://api.telegram.org/bot{PM_LIVE_TG_TOKEN}/sendMessage"
        data = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(f"[{label} TG] Hata: {e}", file=sys.stderr)
        return False


def in_weekend_pause_tr(now_tr: datetime, *, resume_hour: int = WEEKEND_RESUME_HOUR) -> bool:
    """Cuma 22:00 – Pazartesi resume_hour İST arası yeni işlem açılmaz.

    Varsayılan WEEKEND_RESUME_HOUR=11. A1/A2/A10 Live için 12 kullanılır.
    """
    dow = now_tr.weekday()  # 0=Pzt … 4=Cum 5=Cmt 6=Paz
    h = now_tr.hour
    if dow == 4 and h >= 22:
        return True
    if dow == 5:
        return True
    if dow == 6:
        return True
    if dow == 0 and h < resume_hour:
        return True
    return False


# A1 Live / A2 Live / A10 Live — Cum 22:00 → Pzt 12:00
_WEEKEND_RESUME_12_LABELS = frozenset({
    "A1 LIVE",
    "5. ANALİZ",  # A1 legacy label
    "2. ANALİZ LIVE",
    "10. ANALİZ LIVE",
})


# Hafta sonu da çalışmaya devam eden sanal trader'lar (algoritma-islemler — tamamı)
_SANAL_WEEKEND_FREE_LABELS = frozenset({
    "1. ANALİZ",
    "2. ANALİZ",
    "6. ANALİZ",
    "6. ANALİZ V2",
    "6. ANALİZ V3",
    "15. ANALİZ",
    "A2",
    "B1#01",
    "B1#02",
    "B1#03 MUM ANALİZ",
    "B1#04",
})


def _is_algo_islemler_label(label: str) -> bool:
    """algoritma-islemler sayfasındaki sanal defter etiketleri — 7/24."""
    if not label:
        return False
    u = label.strip().upper()
    if u == "A2" or u.startswith("A2#"):
        return True
    for prefix in ("1. ANALİZ", "2. ANALİZ", "6. ANALİZ", "15. ANALİZ", "B1#", "C1#", "X1#", "E01", "COMBO"):
        if label.startswith(prefix):
            return True
    return False

_SANAL_WEEKEND_LABELS = frozenset({
    "10. ANALİZ",
    "15M 110 SOL",
    "15M 309 Squeeze Mom",
    "15M 316 Supertrend",
    "15M 317 SuperTrend v2",
    "15M A2",
})


def _weekend_pause_applies(label: str) -> bool:
    if _is_algo_islemler_label(label):
        return False
    if label in _SANAL_WEEKEND_FREE_LABELS:
        return False
    if label in _SANAL_WEEKEND_LABELS:
        return True
    # Tüm 15M sanal etiketleri (15M 309 …)
    if label.startswith("15M"):
        return True
    try:
        from pm_balance_guard import is_live_pm_label
        return is_live_pm_label(label)
    except Exception:
        return False


def skip_if_weekend_pause(
    label: str,
    mode: str,
    now_tr: datetime | None = None,
    history: list | None = None,
) -> bool:
    """Hafta sonu duraklamasında True — gerçek PM + seçili sanal trader'lar.

    Close modu atlanmaz. Open'da history + güçlü slot (WR>%85) varsa hafta sonu geçer.
    """
    if mode == "close":
        return False
    if now_tr is None:
        now_tr = datetime.now(_TZ_TR)
    elif now_tr.tzinfo is None:
        now_tr = now_tr.replace(tzinfo=_TZ_TR)
    else:
        now_tr = now_tr.astimezone(_TZ_TR)
    try:
        from pm_balance_guard import skip_algo_islemler_open_deferred
        if skip_algo_islemler_open_deferred(label, now_tr):
            return True
    except Exception:
        pass
    if not _weekend_pause_applies(label):
        return False
    # Dashboard'dan açık bırakılan Live analiz — hafta sonu da işlem açabilir
    try:
        from pm_balance_guard import is_dashboard_live_open
        if is_dashboard_live_open(label):
            return False
    except Exception:
        pass
    resume_hour = (
        WEEKEND_RESUME_LATE_HOUR
        if (label or "").upper() in {x.upper() for x in _WEEKEND_RESUME_12_LABELS}
        else WEEKEND_RESUME_HOUR
    )
    if in_weekend_pause_tr(now_tr, resume_hour=resume_hour):
        if mode == "open" and history is not None and is_slot_force_hot(history, now_tr.hour):
            print(
                f"[{label} {mode}] {now_tr.strftime('%H:%M')} İST — "
                f"hafta sonu ama güçlü slot (WR>%{SLOT_FORCE_WR:.0f}) → açılış serbest"
            )
            return False
        end = f"Pzt {resume_hour:02d}:00"
        print(
            f"[{label} {mode}] {now_tr.strftime('%H:%M')} İST — "
            f"hafta sonu duraklama (Cum 22:00 – {end}), işlem yok"
        )
        return True
    return False


# Sanal trader giriş tutarları (1. Analiz mantığı — A1 Live hariç ortak)
SANAL_INITIAL_BALANCE = 1000.0
SANAL_TRADE_AMOUNT = 16.0       # eski sabit (A10 dual vb. — WR kademesi değil)
SANAL_TRADE_AMOUNT_HIGH = 20.0
SANAL_TRADE_AMOUNT_LOW = 12.0

# Algoritma-işlemler sanal — sembol WR kademesi (soğuk saat −%30 ayrıca)
COMBO_FAMILY_KEYS = frozenset({"analiz1", "c101", "a2_05_v2", "combo"})
COMBO_FAMILY_INIT = 1000.0
COMBO_FAMILY_WR = (24.0, 36.0, 48.0)
SANAL_WR_DEFAULT = COMBO_FAMILY_WR


def symbol_wr_amount(history: list, symbol: str) -> float:
    """Sembol WR → $24 / $36 / $48 (veri yok → orta)."""
    low, mid, high = SANAL_WR_DEFAULT
    return wr_tier_amount(history, symbol, low, mid, high)


def wr_tier_amount(
    history: list, symbol: str, low: float, mid: float, high: float,
) -> float:
    """Sembol WR → düşük/orta/yüksek tutar."""
    trades = [t for t in history if t.get("symbol") == symbol]
    if not trades:
        return mid
    wins = sum(1 for t in trades if t.get("win"))
    rate = wins / len(trades)
    if rate > 0.5:
        return high
    if rate < 0.5:
        return low
    return mid


def sanal_wr_amount_defaults(book_key: str) -> tuple[float, float, float]:
    return SANAL_WR_DEFAULT


def load_sanal_wr_amounts(book_key: str) -> tuple[float, float, float]:
    """Poly sanal defter — sembol WR giriş kademeleri (analiz5_settings.json)."""
    low_d, mid_d, high_d = sanal_wr_amount_defaults(book_key)
    if not os.path.exists(_PM_LIVE_SETTINGS_FILE):
        return low_d, mid_d, high_d
    try:
        with open(_PM_LIVE_SETTINGS_FILE) as f:
            data = json.load(f)
        low = float(data.get(f"sanal_{book_key}_amount_low", low_d))
        mid = float(data.get(f"sanal_{book_key}_amount_mid", mid_d))
        high = float(data.get(f"sanal_{book_key}_amount_high", high_d))
        return low, mid, high
    except Exception:
        return low_d, mid_d, high_d


def save_sanal_wr_amounts(
    book_key: str, low: float, mid: float, high: float,
) -> tuple[float, float, float]:
    low = round(max(1.0, min(100.0, float(low))), 2)
    mid = round(max(1.0, min(100.0, float(mid))), 2)
    high = round(max(1.0, min(100.0, float(high))), 2)
    data: dict = {}
    if os.path.exists(_PM_LIVE_SETTINGS_FILE):
        try:
            with open(_PM_LIVE_SETTINGS_FILE) as f:
                data = json.load(f)
        except Exception:
            data = {}
    data[f"sanal_{book_key}_amount_low"] = low
    data[f"sanal_{book_key}_amount_mid"] = mid
    data[f"sanal_{book_key}_amount_high"] = high
    with open(_PM_LIVE_SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return low, mid, high


def symbol_wr_amount_for_book(history: list, symbol: str, book_key: str) -> float:
    low, mid, high = load_sanal_wr_amounts(book_key)
    return wr_tier_amount(history, symbol, low, mid, high)


def sanal_wr_amount_range_str(book_key: str) -> str:
    low, _, high = load_sanal_wr_amounts(book_key)
    return f"${low:.0f}–${high:.0f}"


_PM_LIVE_SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "analiz5_settings.json"
)
_PM_LIVE_AMOUNT_DEFAULTS: dict[str, tuple[float, float, float]] = {
    "a1": (8.0, 10.0, 12.0),
    "a2": (6.0, 7.0, 8.0),
    "a10": (8.0, 10.0, 12.0),
    "a6": (8.0, 10.0, 12.0),
    "a6v2": (8.0, 10.0, 12.0),
    "a6v3": (8.0, 10.0, 12.0),
    "a2_16": (8.0, 12.0, 16.0),
    "a2_02": (4.0, 5.0, 6.0),
    "a2_08": (4.0, 5.0, 6.0),
    "a2_03": (4.0, 5.0, 6.0),
    "a2_04": (4.0, 5.0, 6.0),
    "a2_05": (4.0, 5.0, 6.0),
    "a2_06": (4.0, 5.0, 6.0),
    "a2_07": (4.0, 5.0, 6.0),
    "a15": (12.0, 16.0, 20.0),
    # B1#05 backfill'de kenar bulunamadı (edge +0,6 puan) — en düşük kademe
    "b1_05": (4.0, 5.0, 6.0),
    "b1_mum": (6.0, 8.0, 10.0),
}


def load_pm_live_amounts(system: str) -> tuple[float, float, float]:
    """Dashboard analiz5_settings.json → (low, mid, high) gerçek PM giriş tutarları."""
    defaults = _PM_LIVE_AMOUNT_DEFAULTS.get(system, (8.0, 10.0, 12.0))
    if not os.path.exists(_PM_LIVE_SETTINGS_FILE):
        return defaults
    try:
        with open(_PM_LIVE_SETTINGS_FILE) as f:
            data = json.load(f)
        low = float(data.get(f"{system}_amount_low", defaults[0]))
        mid = float(data.get(f"{system}_amount_mid", defaults[1]))
        high = float(data.get(f"{system}_amount_high", defaults[2]))
        return low, mid, high
    except Exception:
        return defaults


def pm_live_amount_range_str(system: str) -> str:
    low, _, high = load_pm_live_amounts(system)
    return f"${low:.0f}–${high:.0f}"


def pm_live_wr_amount(
    system: str,
    history: list,
    symbol: str,
    get_symbol_stats,
) -> float:
    """Gerçek PM — sembol WR'ye göre düşük/orta/yüksek tutar (dashboard ayarlı)."""
    low, mid, high = load_pm_live_amounts(system)
    wins, total = get_symbol_stats(history, symbol)
    if not total:
        return mid
    rate = wins / total
    if rate > 0.5:
        return high
    if rate < 0.5:
        return low
    return mid


def pm_get_client(*, force: bool = False):
    """Clob client — API key türetmeyi TTL boyunca cache'le (her emirde ~sn kaybı olmasın)."""
    global _PM_CLIENT, _PM_CLIENT_TS
    from py_clob_client_v2 import ClobClient
    pk = os.getenv("POLY_PRIVATE_KEY", "")
    funder = os.getenv("POLY_FUNDER", "")
    now = time.time()
    with _pm_client_lock():
        if (
            not force
            and _PM_CLIENT is not None
            and (now - _PM_CLIENT_TS) < _PM_CLIENT_TTL_SEC
        ):
            return _PM_CLIENT
    last_err = None
    for attempt in range(3):
        try:
            temp = ClobClient(host=_PM_CLOB_HOST, chain_id=137, key=pk)
            creds = temp.create_or_derive_api_key()
            if creds is None:
                time.sleep(0.5)
                continue
            client = ClobClient(
                host=_PM_CLOB_HOST, chain_id=137, key=pk,
                creds=creds, signature_type=1, funder=funder,
            )
            with _pm_client_lock():
                _PM_CLIENT = client
                _PM_CLIENT_TS = time.time()
            return client
        except Exception as e:
            last_err = e
            print(f"[PM] Client init ({attempt+1}/3): {e}", file=sys.stderr)
            time.sleep(0.5)
    raise RuntimeError(f"Polymarket client oluşturulamadı: {last_err}")


def pm_get_balance() -> float:
    try:
        from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
        client = pm_get_client()
        bal = client.get_balance_allowance(
            params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        )
        return int(bal.get("balance", 0)) / 1e6
    except Exception:
        return -1.0


def pm_conditional_shares(token_id: str) -> float:
    """Zincirdeki conditional token adedi (-1 = okunamadı)."""
    from decimal import Decimal, ROUND_DOWN
    try:
        from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
        client = pm_get_client()
        bal = client.get_balance_allowance(
            BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
        )
        raw = int(bal.get("balance", 0))
        return float(Decimal(str(raw / 1_000_000)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
    except Exception:
        return -1.0


def _pm_recover_filled_order(
    token_id: str,
    shares_before: float,
    size: float,
    price: float,
    spent: float,
    *,
    label: str,
) -> dict | None:
    """Timeout/başarısız yanıt sonrası zincirde dolmuş emri yakala."""
    shares = pm_conditional_shares(token_id)
    if shares < 0:
        return None
    before = max(0.0, shares_before)
    delta = round(shares - before, 2)
    if delta < 0.5:
        return None
    use_size = delta if delta >= 0.5 else size
    use_spent = round(use_size * price, 2) if price > 0 else spent
    print(
        f"[{label}] Emir yanıt vermedi ama zincirde {use_size} share var — recover",
        file=sys.stderr,
    )
    return {
        "order_id": f"recovered:{token_id[:18]}",
        "size": use_size,
        "price": price,
        "spent": use_spent,
        "recovered": True,
    }


def pm_find_market(symbol: str, et_hour: int, date_utc) -> dict | None:
    asset = _PM_ASSET_MAP.get(symbol)
    if not asset:
        return None
    et_date = date_utc - timedelta(hours=4)
    month = et_date.strftime("%B").lower()
    day   = et_date.day
    year  = et_date.year
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
            print(f"[PM] Gamma hatası ({slug}): {e}", file=sys.stderr)
    return None


_PM_CLOB_BOOK_URL = "https://clob.polymarket.com/book"

# Polymarket taker ücreti: fee = C × rate × p × (1−p), USDC cinsinden, yalnız taker öder.
# Kripto kategorisi rate = 0.07 (Gamma: feeType=crypto_fees_v2). Ücret p=0.50'de zirve yapar,
# yani saatlik up/down piyasalarının tam oturduğu bantta en pahalıdır.
PM_TAKER_FEE_RATE = 0.07


def pm_taker_fee(size: float, price: float, rate: float = PM_TAKER_FEE_RATE) -> float:
    """Alınan `size` adet için PM taker ücreti (USDC)."""
    if size <= 0 or not (0.0 < price < 1.0):
        return 0.0
    return round(size * rate * price * (1.0 - price), 5)


_PM_BOOK_CACHE: dict[str, tuple[float, dict | None]] = {}
_PM_BOOK_TTL = 20.0

# Borsa varsayılanları — emir defteri kendi değerini bildirirse o kullanılır.
PM_MIN_ORDER_SIZE = 5.0
PM_TICK_SIZE = 0.01


def pm_order_book(token_id: str) -> dict | None:
    """CLOB emir defteri — ask seviyeleri artan fiyat sırasında, borsa limitleriyle.

    A2 gibi tek süreçte onlarca defter koşturan çağrılar aynı token'ı tekrar tekrar
    sorduğu için sonuç kısa süre önbelleklenir.

    Döner: `{"asks": [(fiyat, adet), …], "min_order_size": …, "tick_size": …}`
    """
    if not token_id:
        return None
    hit = _PM_BOOK_CACHE.get(token_id)
    if hit and (time.time() - hit[0]) < _PM_BOOK_TTL:
        return hit[1]
    try:
        req = urllib.request.Request(
            f"{_PM_CLOB_BOOK_URL}?token_id={token_id}", headers=_PM_HEADERS,
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = json.load(r)
    except Exception as e:
        print(f"[PM] Emir defteri hatası ({token_id[:16]}): {e}", file=sys.stderr)
        _PM_BOOK_CACHE[token_id] = (time.time(), None)
        return None
    levels = []
    for a in raw.get("asks") or []:
        try:
            p, s = float(a["price"]), float(a["size"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0.0 < p < 1.0 and s > 0:
            levels.append((p, s))
    levels.sort(key=lambda x: x[0])
    out = None
    if levels:
        try:
            mins = float(raw.get("min_order_size") or PM_MIN_ORDER_SIZE)
        except (TypeError, ValueError):
            mins = PM_MIN_ORDER_SIZE
        try:
            tick = float(raw.get("tick_size") or PM_TICK_SIZE)
        except (TypeError, ValueError):
            tick = PM_TICK_SIZE
        out = {"asks": levels, "min_order_size": mins, "tick_size": tick}
    _PM_BOOK_CACHE[token_id] = (time.time(), out)
    return out


def pm_best_ask(token_id: str) -> float | None:
    """En iyi (en ucuz) satış fiyatı. Tek adetlik referans; dolum için `pm_sanal_fill`."""
    book = pm_order_book(token_id)
    return book["asks"][0][0] if book else None


def pm_book_vwap(token_id: str, amount_usd: float) -> tuple[float | None, bool]:
    """`amount_usd`'lik alımın emir defteri yürünerek bulunan ortalama fiyatı.

    Canlıdaki `client.calculate_market_price(..., BUY, amount, FAK)` ile aynı işi
    yapar: en ucuz seviyeden başlayıp para bitene kadar seviyeleri tüketir. Büyük
    emir ince defteri yürüdüğü için en iyi ask'ten pahalıya gelebilir.

    Döner: `(vwap, defter_yetersiz_mi)`.
    """
    book = pm_order_book(token_id)
    if not book or amount_usd <= 0:
        return None, False
    remaining, shares, cost = float(amount_usd), 0.0, 0.0
    for price, size in book["asks"]:
        if remaining <= 1e-9:
            break
        take = min(size, remaining / price)
        shares += take
        cost += take * price
        remaining -= take * price
    if shares <= 0:
        return None, False
    return cost / shares, remaining > 0.01


def pm_sanal_fill(token_id: str, amount_usd: float,
                  fallback_price: float | None = None) -> dict | None:
    """Sanal defterin dolumu — canlı `pm_place_order` ile **birebir aynı** formül.

    Sanal ile canlı arasındaki sapmanın sebebi buydu: sanal `amount/en_iyi_ask`
    diyordu, canlı ise derinlik VWAP'ını 2 haneye yuvarlayıp borsa minimumuna
    tamamlıyordu. Ölçüldü (2026-08-14, $10 kademe): ETH'de en iyi ask 0,160 iken
    canlının ödediği 0,17 (%6 pahalı), SOL'da 0,140 → 0,15 (%7). Aynı sinyal
    sanalda kârlı, canlıda zararlı görünüyordu.

    Defter okunamazsa `fallback_price` (Gamma mid) ile aynı yuvarlama uygulanır.
    """
    if amount_usd <= 0:
        return None
    book = pm_order_book(token_id)
    if book:
        vwap, short = pm_book_vwap(token_id, amount_usd)
        mins, src = book["min_order_size"], "book"
    else:
        vwap, short, mins, src = fallback_price, False, PM_MIN_ORDER_SIZE, "mid"
    if vwap is None or not (0.0 < vwap < 1.0):
        return None

    # Buradan aşağısı pm_place_order'ın kopyası — kasıtlı olarak satır satır aynı.
    price = max(0.02, min(0.98, round(vwap, 2)))
    raw_sz = float(Decimal(str(amount_usd / price)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
    size, price = pm_fit_buy(max(mins, raw_sz), price)
    spent = round(size * price, 2)
    return {
        "price": price,
        "size": size,
        "spent": spent,
        "vwap": round(vwap, 4),
        "src": src,
        "book_short": short,
    }


def pm_fit_buy(size: float, price: float, min_shares: float = 5.0) -> tuple[float, float]:
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


def pm_log_hata(hata_file: str, symbol: str, hata_turu: str, detay: str) -> None:
    try:
        kayitlar = []
        if os.path.exists(hata_file):
            with open(hata_file) as f:
                kayitlar = json.load(f)
        kayitlar.append({
            "zaman": datetime.now(timezone.utc).astimezone(_TZ_TR).isoformat(),
            "symbol": symbol,
            "hata_turu": hata_turu,
            "detay": detay,
        })
        with open(hata_file, "w") as f:
            json.dump(kayitlar, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        print(f"[PM] Hata loglanamadı: {ex}", file=sys.stderr)


_PM_LAST_ORDER_ERROR: str | None = None


def pm_last_order_error() -> str:
    return _PM_LAST_ORDER_ERROR or "PM emri gönderilemedi"


def pm_clob_error_tr(err: str | Exception) -> str:
    """CLOB / PolyApiException metnini dashboard için Türkçe özete çevir."""
    import re

    s = str(err or "").strip()
    if not s:
        return "Bilinmeyen PM hatası"

    low = s.lower()
    m = re.search(r"status_code=(\d+)", s)
    code = int(m.group(1)) if m else None

    if "order manager not ready" in low or code == 425:
        return "Polymarket emir sistemi henüz hazır değil — 1–2 dakika bekleyip tekrar deneyin"
    if "internal server error" in low or code == 500:
        return "Polymarket sunucu hatası — birkaç dakika sonra tekrar deneyin"
    if code == 502 or "bad gateway" in low:
        return "Polymarket geçici olarak yanıt vermiyor — kısa süre sonra tekrar deneyin"
    if code == 503 or "service unavailable" in low:
        return "Polymarket aşırı yüklü veya bakımda — sonra tekrar deneyin"
    if code == 429 or "rate limit" in low or "too many" in low:
        return "Çok fazla istek — birkaç saniye bekleyip tekrar deneyin"
    if "no orders found" in low:
        return "Yeterli likidite yok — emir eşleşmedi"
    if "fak eşleşmedi" in low or "fak eslesmedi" in low:
        return "Satış emri eşleşmedi — likidite düşük olabilir"
    if "invalid token" in low or "orderbook" in low:
        return "Piyasa kapandı veya emir defteri yok — settle bekleniyor"
    if "unauthorized" in low or code == 401:
        return "PM API yetkisi yok — oturum veya anahtarları kontrol edin"
    if "insufficient" in low or ("balance" in low and "order" in low):
        return "Yetersiz bakiye — PM cüzdanını kontrol edin"
    if "min" in low and ("size" in low or "amount" in low):
        return "Minimum emir boyutu karşılanmıyor"

    dm = re.search(r"error_message=\{([^}]+)\}", s)
    if dm:
        inner = dm.group(1).lower()
        if "order manager not ready" in inner:
            return "Polymarket emir sistemi henüz hazır değil — 1–2 dakika bekleyip tekrar deneyin"
        if "internal server error" in inner:
            return "Polymarket sunucu hatası — birkaç dakika sonra tekrar deneyin"

    if "polyapiexception" in low:
        if code:
            return f"Polymarket API hatası (HTTP {code}) — kısa süre sonra tekrar deneyin"
        return "Polymarket API hatası — kısa süre sonra tekrar deneyin"

    if len(s) > 100:
        return s[:97] + "…"
    return s


def pm_place_order(
    token_id: str, amount_usd: float, tick_size: str = "0.01",
    neg_risk: bool = False, *, label: str = "PM", hata_file: str | None = None,
    max_attempts: int | None = None,
    interactive: bool = False,
) -> dict | None:
    global _PM_LAST_ORDER_ERROR
    last_err: str | None = None
    shares_before = pm_conditional_shares(token_id)
    last_size = 0.0
    last_price = 0.0
    last_spent = 0.0
    attempt = 0
    if max_attempts is None:
        max_attempts = (
            PM_ORDER_INTERACTIVE_ATTEMPTS if interactive else PM_ORDER_ATTEMPTS
        )
    not_ready_cap = (
        PM_ORDER_INTERACTIVE_NOT_READY if interactive else PM_ORDER_NOT_READY_ATTEMPTS
    )
    retry_sec = (
        PM_ORDER_INTERACTIVE_RETRY_SEC if interactive else PM_ORDER_RETRY_SEC
    )
    limit = max(1, int(max_attempts))

    while attempt < limit:
        attempt += 1
        try:
            from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions
            from py_clob_client_v2.order_builder.constants import BUY
            from decimal import Decimal, ROUND_DOWN
            client = pm_get_client()
            price  = float(client.calculate_market_price(token_id, "BUY", amount_usd, OrderType.FAK))
            price  = max(0.02, min(0.98, round(price, 2)))
            raw_sz = float(Decimal(str(amount_usd / price)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
            size, price = pm_fit_buy(max(5.0, raw_sz), price)
            spent  = round(size * price, 2)
            last_size, last_price, last_spent = size, price, spent
            if PM_DRY_RUN:
                print(f"[{label} DRY RUN] {token_id[:16]}… {size} shares @ {price:.2f} (~${spent:.2f})")
                return {"order_id": "DRY_RUN", "size": size, "price": price, "spent": spent}
            args = OrderArgs(token_id=token_id, price=price, size=size, side=BUY)
            signed = client.create_order(args, PartialCreateOrderOptions())
            resp   = client.post_order(signed, order_type=OrderType.FAK)
            if resp and resp.get("success"):
                oid = resp.get("orderID") or resp.get("id", "")
                _PM_LAST_ORDER_ERROR = None
                return {"order_id": oid, "size": size, "price": price, "spent": spent}
            last_err = str(resp)
            print(
                f"[{label}] Order başarısız ({attempt}/{limit}): {last_err}",
                file=sys.stderr,
            )
        except Exception as e:
            last_err = str(e)
            print(
                f"[{label}] Order hatası ({attempt}/{limit}): {e}",
                file=sys.stderr,
            )
            low = last_err.lower()
            if "unauthorized" in low or "invalid api" in low or "api key" in low:
                pm_invalidate_client()

        recovered = _pm_recover_filled_order(
            token_id, shares_before, last_size, last_price, last_spent, label=label,
        )
        if recovered:
            _PM_LAST_ORDER_ERROR = None
            return recovered

        if _pm_order_not_ready(last_err):
            limit = max(limit, not_ready_cap)

        if attempt < limit:
            print(
                f"[{label}] {retry_sec}s beklenip tekrar denenecek"
                + (" (PM not ready)" if _pm_order_not_ready(last_err) else "")
                + "…",
                file=sys.stderr,
            )
            time.sleep(retry_sec)

    if hata_file and last_err:
        pm_log_hata(hata_file, token_id[:20], "order_basarisiz", last_err)
    _PM_LAST_ORDER_ERROR = pm_clob_error_tr(last_err or "order failed")
    return None


def pm_try_open(
    state: dict, symbol: str, predicted_dir: str, entry_price: float,
    amount: float, *, hour_tr: int, dow: int, is_weekend: bool,
    now_tr: datetime, now: datetime, label: str, hata_file: str,
    extra_fields: dict | None = None,
) -> tuple[dict | None, str | None]:
    et_hour = (now - timedelta(hours=4)).hour
    pos = {
        "symbol":           symbol,
        "predicted_dir":    predicted_dir,
        "entry_price":      entry_price,
        "entry_time_tr":    now_tr.isoformat(),
        "entry_hour_tr":    hour_tr,
        "entry_dow":        dow,
        "entry_is_weekend": is_weekend,
        "amount":           amount,
    }
    if extra_fields:
        pos.update(extra_fields)
    pm = pm_find_market(symbol, et_hour, now)
    if not pm or not pm.get("active") or pm.get("closed"):
        durum = "bulunamadı" if not pm else "kapalı"
        print(f"[{label}] {symbol} market {durum}", file=sys.stderr)
        pm_log_hata(hata_file, symbol, "market_" + durum, f"et_hour={et_hour}")
        return None, "market"
    token_id = pm["up_token"] if predicted_dir == "UP" else pm["down_token"]
    order = pm_place_order(token_id, amount, pm["tick_size"], pm["neg_risk"],
                           label=label, hata_file=hata_file)
    if not order:
        print(f"[{label}] {symbol} PM order başarısız", file=sys.stderr)
        pm_log_hata(hata_file, symbol, "order_basarisiz", f"dir={predicted_dir} amount={amount}")
        return None, "order"
    pos.update({
        "pm_slug": pm["slug"], "pm_title": pm["title"], "pm_token_id": token_id,
        "pm_token_dir": predicted_dir, "pm_size": order["size"],
        "pm_entry_price": order["price"], "pm_order_id": order["order_id"],
        "pm_spent": order["spent"],
        "pm_fee": pm_taker_fee(order["size"], order["price"]),
        "pm_quote_src": "fill",
    })
    print(f"[{label}] PM order: {symbol} {predicted_dir} "
          f"{order['size']} shares @ {order['price']} (${order['spent']:.2f})")
    state["open_positions"].append(pos)
    return pos, None


def pm_resolve_pnl(pos: dict) -> tuple[bool | None, float, str]:
    """PM market kapandıysa (win, pnl, ekstra metin) döner."""
    if not pos.get("pm_slug"):
        return None, 0.0, ""
    try:
        req = urllib.request.Request(
            f"{_PM_GAMMA_URL}?slug={pos['pm_slug']}", headers=_PM_HEADERS,
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            pm_data = json.load(r)
        if not pm_data:
            return None, 0.0, ""
        pm_ev = pm_data[0]
        pm_m  = pm_ev.get("markets", [{}])[0]
        raw_op = pm_m.get("outcomePrices")
        op     = json.loads(raw_op) if isinstance(raw_op, str) else (raw_op or [])
        if not op or not pm_ev.get("closed"):
            return None, 0.0, ""
        up_won  = float(op[0]) >= 0.99
        our_won = (pos["pm_token_dir"] == "UP" and up_won) or \
                  (pos["pm_token_dir"] == "DOWN" and not up_won)
        pm_spent = pos.get("pm_spent", 0)
        pm_size  = pos.get("pm_size", 0)
        fee      = pm_position_fee(pos)
        pnl_val  = round(pm_size - pm_spent - fee, 2) if our_won else round(-pm_spent - fee, 2)
        extra    = f"  |  🎯PM: {'+'if our_won else ''}{pnl_val:.2f}$"
        return our_won, pnl_val, extra
    except Exception as e:
        print(f"[PM] Sonuç hatası: {e}", file=sys.stderr)
        return None, 0.0, ""


def pm_sanal_quote(symbol: str, direction: str, amount_usd: float, now: datetime) -> dict | None:
    """1h PM sanal kotasyonu (emir yok) — canlı emirle aynı dolum ve ücret hesabı.

    Amaç: sanalda kârlı görünen bir defter canlıya alındığında da kârlı olsun.
    Bunun için giriş fiyatı, adet ve harcama `pm_sanal_fill` üzerinden canlı
    `pm_place_order` ile aynı formülle bulunur; üstüne PM taker ücreti eklenir.
    Kazanç tarafı zaten gerçek: kazanan her adet tam $1 öder (`to_win = size`).
    """
    et_hour = (now - timedelta(hours=4)).hour
    pm = pm_find_market(symbol, et_hour, now)
    if not pm or pm.get("closed"):
        return None
    op = pm.get("outcome_prices") or []
    if len(op) < 2:
        return None
    mid = float(op[0]) if direction == "UP" else float(op[1])
    token = pm["up_token"] if direction == "UP" else pm["down_token"]
    fill = pm_sanal_fill(token, amount_usd, fallback_price=mid)
    if not fill:
        return None
    tp, size, spent = fill["price"], fill["size"], fill["spent"]
    if not (0.02 <= tp <= 0.98):
        return None
    return {
        "pm_slug": pm["slug"],
        "pm_title": pm.get("title", ""),
        "pm_token_dir": direction,
        "pm_entry_price": tp,
        "pm_quote_src": fill["src"],
        "pm_fill_vwap": fill["vwap"],
        "pm_mid_price": round(mid, 4),
        "pm_fee": pm_taker_fee(size, tp),
        "pm_spent": spent,
        "pm_size": size,
        "to_win": size,
    }


def apply_pm_quote(pos: dict, symbol: str, direction: str, amount: float, now: datetime) -> dict:
    q = pm_sanal_quote(symbol, direction, amount, now)
    if q:
        pos.update(q)
    return pos


# Saatlik sanal (A1/A2/A6/A10): net kazanç >= stake'in bu oranı yoksa işlem açılmaz
HOURLY_MIN_NET_PROFIT_RATIO = 0.5


def pm_net_profit(pos: dict) -> float:
    spent, size, _ = pm_stake_fields(pos)
    if spent <= 0 or size <= 0:
        return 0.0
    return round(size - spent, 2)


def pm_hourly_profit_entry_ok(
    pos: dict,
    min_ratio: float = HOURLY_MIN_NET_PROFIT_RATIO,
) -> tuple[bool, str]:
    """PM kotasyonunda net kazanç (to_win − spent) >= stake × min_ratio ise True."""
    spent, size, ep = pm_stake_fields(pos)
    if size <= 0 or ep <= 0 or not pos.get("pm_slug"):
        return False, "PM kotasyonu yok — işlem açılmaz (2× stake kullanılmaz)"
    net = round(size - spent, 2)
    need = round(spent * min_ratio, 2)
    if net >= need:
        return True, ""
    need_pct = int(round(min_ratio * 100))
    got_pct = int(round(net / spent * 100)) if spent else 0
    return (
        False,
        f"PM kazanç düşük: +${net:.2f} (%{got_pct}) < %{need_pct} (+${need:.2f} gerekli, @{ep:.2f})",
    )


def pm_stake_fields(pos: dict) -> tuple[float, float, float]:
    """(harcama, to_win/pm_size, token_fiyat) — giriş kotasyonundan."""
    spent = float(pos.get("pm_spent") or pos.get("amount") or 0)
    entry_p = float(pos.get("pm_entry_price") or pos.get("token_price") or 0)
    size = float(pos.get("pm_size") or pos.get("to_win") or 0)
    if size <= 0 and spent > 0 and entry_p > 0 and (
        pos.get("pm_entry_price") is not None or pos.get("token_price") is not None
    ):
        size = round(spent / entry_p, 2)
    return spent, size, entry_p


def pm_payout_fields(pos: dict) -> dict:
    """PM giriş kotasyonu — kazanırsa toplam ödeme ve taker ücreti düşülmüş net kâr."""
    spent, size, ep = pm_stake_fields(pos)
    live = size > 0 and spent > 0
    fee = pm_position_fee(pos) if live else 0.0
    return {
        "pm_spent": round(spent, 2),
        "pm_size": round(size, 2) if size > 0 else 0.0,
        "to_win": round(size, 2) if size > 0 else 0.0,
        "win_payout": round(size, 2) if size > 0 else None,
        "win_profit": round(size - spent - fee, 2) if live else None,
        "win_profit_gross": round(size - spent, 2) if live else None,
        "pm_fee": round(fee, 4) if live else None,
        "pm_entry_price": ep if ep > 0 else None,
        "has_pm_quote": bool(size > 0 and ep > 0 and pos.get("pm_slug")),
    }


def sanal_at_risk(state: dict) -> float:
    total = 0.0
    for p in state.get("open_positions", []):
        spent, _, _ = pm_stake_fields(p)
        total += spent
    return round(total, 2)


def sanal_tg_balance_footer(state: dict) -> str:
    """Sanal PM TG — Ana (serbest) / Riskte / Toplam equity."""
    at_risk = sanal_at_risk(state)
    total = round(float(state.get("balance", SANAL_INITIAL_BALANCE)), 2)
    ana = round(total - at_risk, 2)
    n = len(state.get("open_positions", []))
    return (
        f"💰 Ana: ${ana:.2f}  |  📂 Riskte: ${at_risk:.0f}  |  "
        f"Toplam: ${total:.2f}  |  Acik: {n}"
    )


def pm_tg_stake(pos: dict) -> str:
    spent, size, ep = pm_stake_fields(pos)
    if size > 0 and spent > 0 and ep > 0:
        net = round(size - spent, 2)
        return f"💵 ${spent:.2f}@{ep:.2f} → +${net:.2f} net (${size:.2f} toplam)"
    if size > 0 and spent > 0:
        net = round(size - spent, 2)
        return f"💵 ${spent:.2f} → +${net:.2f} net (${size:.2f} toplam)"
    return f"💵 ${spent:.2f}" if spent > 0 else ""


def pm_sanal_tg_quote(spent: float, token_price: float | None, pm_size: float) -> str:
    """Sanal 5m açılış satırı — net kazanç PM kotasyonundan (toplam ödeme − risk)."""
    spent = round(float(spent), 2)
    size = round(float(pm_size), 2)
    net = round(size - spent, 2)
    if token_price and 0 < token_price < 1:
        return f"💵 ${spent:.2f}@{token_price:.2f} → +${net:.2f} net (${size:.2f} toplam)"
    return f"💵 ${spent:.2f} → +${net:.2f} net (${size:.2f} toplam)"


def pm_history_extras(pos: dict) -> dict:
    extras: dict = {}
    for k in (
        "pm_spent", "pm_size", "pm_entry_price", "to_win", "token_price", "pm_slug", "pm_order_id", "tier",
        "pm_fee", "pm_quote_src", "pm_mid_price",
        "pm_spent_original", "pm_partial_received", "pm_partial_sold_size", "pm_partial_tp_done",
    ):
        if pos.get(k) is not None:
            extras[k] = pos[k]
    return extras


def pm_position_fee(pos: dict) -> float:
    """Pozisyonun PM taker ücreti — girişte kaydedildiyse onu, yoksa kotasyondan hesaplar."""
    rec = pos.get("pm_fee")
    if rec is not None:
        try:
            return round(float(rec), 5)
        except (TypeError, ValueError):
            pass
    spent, size, price = pm_stake_fields(pos)
    if size <= 0 or spent <= 0:
        return 0.0
    return pm_taker_fee(size, price)


def sanal_pnl(pos: dict, win: bool) -> float:
    """Net P&L — PM taker ücreti düşülmüş. Ücret girişte ödenir, sonuçtan bağımsızdır."""
    spent, size, _ = pm_stake_fields(pos)
    if size > 0 and spent > 0:
        fee = pm_position_fee(pos)
        return round(size - spent - fee, 2) if win else round(-spent - fee, 2)
    if not win:
        return round(-spent, 2) if spent > 0 else 0.0
    return 0.0


def pm_sanal_slot_candle(symbol: str, entry_time_tr: str) -> tuple[float, float] | None:
    """PM slot saatinin Binance 1h open/close (İST entry_time_tr). Spot mum."""
    try:
        et = datetime.fromisoformat(entry_time_tr.replace("Z", "+00:00")).astimezone(_TZ_TR)
    except Exception:
        return None
    slot = et.replace(minute=0, second=0, microsecond=0)
    ms = int(slot.timestamp() * 1000)
    try:
        from binance_fapi_guard import public_klines
        data = public_klines(symbol, "1h", 1, start_time_ms=ms)
    except Exception as e:
        print(f"[pm_sanal_slot_candle] {symbol} {slot:%H:%M} mum yok: {e}")
        return None
    if not data:
        return None
    k = data[0]
    return float(k[1]), float(k[4])


def pm_sanal_settle_trade(pos: dict, hour_open: float, hour_close: float) -> dict:
    """PM sanal sonuç: saat open (price-to-beat) vs saat close."""
    pred = pos.get("predicted_dir") or pos.get("algo_signal") or ""
    actual = "UP" if hour_close >= hour_open else "DOWN"
    win = pred == actual
    pnl = sanal_pnl(pos, win)
    return {
        "actual_dir": actual,
        "win": win,
        "pnl": pnl,
        "pm_fee": pm_position_fee(pos),
        "entry_price": hour_open,
        "exit_price": hour_close,
    }


def pm_sanal_close_position(pos: dict) -> dict | None:
    """Açık pozisyonu PM slot mumu ile kapat — None = mum alınamadı."""
    candle = pm_sanal_slot_candle(pos.get("symbol") or "", pos.get("entry_time_tr") or "")
    if not candle:
        return None
    return pm_sanal_settle_trade(pos, candle[0], candle[1])


def pm_realized_pnl(pos: dict, win: bool) -> float:
    """Kısmi kar al sonrası nihai P&L (eski 210 pozisyonları için geriye uyum)."""
    partial = float(pos.get("pm_partial_received") or 0)
    spent_orig = float(
        pos.get("pm_spent_original") or pos.get("pm_spent") or pos.get("amount") or 0
    )
    _, size, _ = pm_stake_fields(pos)
    if partial > 0 and spent_orig > 0:
        remainder = size if win else 0.0
        return round(partial + remainder - spent_orig, 2)
    return sanal_pnl(pos, win)


def sanal_debit_on_open(state: dict, pos: dict) -> float:
    """Açılışta stake bakiyeden düşülür (A2 modeli)."""
    spent, _, _ = pm_stake_fields(pos)
    if spent > 0:
        state["balance"] = round(state.get("balance", 0) - spent, 2)
    return spent


def sanal_credit_on_close(state: dict, pos: dict, win: bool, pnl: float) -> None:
    """Kapanış: kazançta pm_size geri, kayıpta 0; total_pnl güncellenir."""
    _, size, _ = pm_stake_fields(pos)
    if win and size > 0:
        state["balance"] = round(state.get("balance", 0) + size, 2)
    state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)


def sanal_close_balance(state: dict, pos: dict, win: bool) -> float:
    """Bakiye += net PM P&L (açılışta pm_spent düşülmüşse tutarlı)."""
    pnl = sanal_pnl(pos, win)
    state["balance"] = round(state.get("balance", 0) + pnl, 2)
    state["total_pnl"] = round(state.get("total_pnl", 0) + pnl, 2)
    return pnl


_PM_5M_ASSET = {
    "BTCUSDT": "btc", "SOLUSDT": "sol", "ETHUSDT": "eth",
}


def pm_5m_find_market(ts_5m: int, symbol: str = "BTCUSDT") -> dict | None:
    """5m up/down market gamma fiyatı."""
    return pm_updown_find_market(ts_5m, symbol, period_min=5)


def pm_15m_find_market(ts_15m: int, symbol: str = "SOLUSDT") -> dict | None:
    """15m up/down market gamma fiyatı."""
    return pm_updown_find_market(ts_15m, symbol, period_min=15)


def pm_updown_find_market(ts: int, symbol: str, period_min: int = 5) -> dict | None:
    asset = _PM_5M_ASSET.get(symbol, "btc")
    slug = f"{asset}-updown-{period_min}m-{ts}"
    try:
        req = urllib.request.Request(f"{_PM_GAMMA_URL}?slug={slug}", headers=_PM_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        if not data:
            return None
        event = data[0]
        markets = event.get("markets", [])
        if not markets:
            return None
        m = markets[0]
        raw_op = m.get("outcomePrices")
        op = json.loads(raw_op) if isinstance(raw_op, str) else (raw_op or [])
        return {
            "slug": slug,
            "title": event.get("title", ""),
            "closed": event.get("closed", False),
            "up_price": float(op[0]) if len(op) >= 2 else 0.5,
            "down_price": float(op[1]) if len(op) >= 2 else 0.5,
        }
    except Exception as e:
        print(f"[PM] 5m gamma hatası ({slug}): {e}", file=sys.stderr)
    return None


def pm_5m_sanal_quote(ts_5m: int, direction: str, amount: float, symbol: str = "BTCUSDT") -> dict:
    """5m PM kotasyon alanları (emir yok)."""
    return pm_updown_sanal_quote(ts_5m, direction, amount, symbol, period_min=5)


def pm_15m_sanal_quote(ts_15m: int, direction: str, amount: float, symbol: str = "SOLUSDT") -> dict:
    """15m PM kotasyon alanları (emir yok)."""
    return pm_updown_sanal_quote(ts_15m, direction, amount, symbol, period_min=15)


def pm_updown_sanal_quote(ts: int, direction: str, amount: float, symbol: str, period_min: int = 5) -> dict:
    pm = pm_updown_find_market(ts, symbol, period_min=period_min)
    out: dict = {"amount": amount, "pm_spent": round(amount, 2)}
    tp = 0.50
    if pm and not pm.get("closed"):
        tp = pm["up_price"] if direction == "UP" else pm["down_price"]
        if tp and 0.02 <= tp <= 0.98:
            size = round(amount / tp, 2)
            out.update({
                "pm_slug": pm["slug"],
                "token_price": tp,
                "pm_entry_price": tp,
                "pm_spent": round(amount, 2),
                "pm_size": size,
                "to_win": size,
            })
            return out
    fb_size = round(amount / tp, 2) if 0.02 <= tp <= 0.98 else round(amount / 0.50, 2)
    out.update({"pm_size": fb_size, "to_win": fb_size, "pm_entry_price": tp, "token_price": tp})
    return out


def pm_5m_history_extras(pos: dict) -> dict:
    extras: dict = {}
    for k in ("pm_spent", "pm_size", "pm_entry_price", "to_win", "token_price", "pm_slug", "pm_order_id",
              "pm_fee", "pm_quote_src", "pm_mid_price"):
        if pos.get(k) is not None:
            extras[k] = pos[k]
    if "pm_spent" not in extras and pos.get("amount") is not None:
        extras["pm_spent"] = pos["amount"]
    if "pm_entry_price" not in extras and pos.get("token_price") is not None:
        extras["pm_entry_price"] = pos["token_price"]
    if "pm_size" not in extras and pos.get("to_win") is not None:
        extras["pm_size"] = pos["to_win"]
    return extras


def pm_5m_close(pos: dict, win: bool) -> tuple[float, float]:
    """(pnl, payout) — girişte kaydedilen PM kotasyonuna göre."""
    pnl = pm_realized_pnl(pos, win)
    _, size, _ = pm_stake_fields(pos)
    payout = size if win else 0.0
    return pnl, payout


def pm_5m_fetch_resolution(slug: str, min_decisive: float = 0.99) -> dict | None:
    """PM 5m market sonucu. Kesinleşmediyse None.

    min_decisive: örn. 0.99 sıkı; periyot bitince 0.90 ile erken kabul.
    closed=True ise fiyat çoğunluğuna göre sonuçlanır.
    """
    if not slug:
        return None
    thr = float(min_decisive)
    thr = max(0.51, min(0.99, thr))
    low = round(1.0 - thr, 4)
    try:
        req = urllib.request.Request(f"{_PM_GAMMA_URL}?slug={slug}", headers=_PM_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            pm_data = json.load(r)
        if not pm_data:
            return None
        pm_ev = pm_data[0]
        pm_m = pm_ev.get("markets", [{}])[0]
        raw_op = pm_m.get("outcomePrices")
        op = json.loads(raw_op) if isinstance(raw_op, str) else (raw_op or [])
        if not op:
            return None
        up_p = float(op[0])
        down_p = float(op[1]) if len(op) > 1 else (1.0 - up_p)
        closed = bool(pm_ev.get("closed"))
        decisive = up_p >= thr or down_p >= thr or up_p <= low
        if not (closed or decisive):
            return None
        if up_p >= thr or (decisive and up_p > down_p):
            up_won = True
        elif down_p >= thr or up_p <= low:
            up_won = False
        elif closed:
            up_won = up_p >= down_p
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
        print(f"[PM] 5m sonuç hatası ({slug}): {e}", file=sys.stderr)
    return None


pm_fetch_resolution = pm_5m_fetch_resolution  # 1h saatlik marketler de aynı format

# Dashboard "En Etkili Zaman" ile aynı mantık — bottom 3 saat -%30.
# Hot-hour büyütme kapalı: 3 işlemle "etkili saat" seçildiği için gürültüye bahis
# büyütüyordu — boost'lu 90 sanal işlem %26.7 WR / -$570, normaller %55.2 / +$1770
# (ölçüm 2026-08-11). 1.0 = nötr; apply_hot_hour_boost da bu sabiti kullanır.
HOT_HOUR_BOOST = 1.0
HOT_HOUR_MIN_TRADES = 3
COLD_HOUR_CUT = 0.7
SLOT_TOP_N = 3


def _hour_slot_candidates(
    history: list,
    *,
    min_trades: int = HOT_HOUR_MIN_TRADES,
) -> list[tuple[int, int, float]]:
    hour_day: dict[int, dict[int, dict[str, int]]] = {}
    for t in history:
        dow = t.get("entry_dow")
        hour = t.get("entry_hour_tr")
        if dow is None or hour is None:
            continue
        hour_day.setdefault(hour, {}).setdefault(dow, {"w": 0, "t": 0})
        hour_day[hour][dow]["t"] += 1
        if t.get("win"):
            hour_day[hour][dow]["w"] += 1

    out: list[tuple[int, int, float]] = []
    for h, day_data in hour_day.items():
        good_days = [
            v for v in day_data.values()
            if v["t"] >= 1 and v["w"] / v["t"] > 0.5
        ]
        all_w = sum(v["w"] for v in day_data.values())
        all_t = sum(v["t"] for v in day_data.values())
        if all_t < min_trades:
            continue
        wr = all_w / all_t * 100 if all_t else 0.0
        out.append((h, len(good_days), wr))
    return out


def compute_top_slot_hours(
    history: list,
    *,
    min_trades: int = HOT_HOUR_MIN_TRADES,
    top_n: int = SLOT_TOP_N,
) -> frozenset[int]:
    """Birden fazla günde tutarlı başarılı saatler (dashboard top_slots ile uyumlu)."""
    slots = [
        (h, good_days, wr)
        for h, good_days, wr in _hour_slot_candidates(history, min_trades=min_trades)
        if good_days >= 1
    ]
    slots.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return frozenset(h for h, _, _ in slots[:top_n])


def compute_bottom_slot_hours(
    history: list,
    *,
    min_trades: int = HOT_HOUR_MIN_TRADES,
    top_n: int = SLOT_TOP_N,
) -> frozenset[int]:
    """En düşük WR'li saatler (dashboard bottom_slots ile uyumlu)."""
    slots = list(_hour_slot_candidates(history, min_trades=min_trades))
    slots.sort(key=lambda x: (x[2], -x[1]))
    return frozenset(h for h, _, _ in slots[:top_n])


def resolve_slot_trade_amount(
    base_amount: float,
    hour_tr: int,
    history: list,
    *,
    cut: float = COLD_HOUR_CUT,
) -> tuple[float, bool, bool]:
    """Bottom 3 saatte -%30, top 3 saatte tutar sabit (hot öncelikli).

    Top 3 saat hâlâ cut'ı bloklar, ama tutarı artırmaz.
    """
    if hour_tr in compute_top_slot_hours(history):
        return base_amount, False, False
    if hour_tr in compute_bottom_slot_hours(history):
        return round(base_amount * cut, 2), False, True
    return base_amount, False, False


def slot_amount_log(label: str, hour_tr: int, base: float, amount: float, hot_boost: bool, cold_cut: bool) -> None:
    if cold_cut:
        print(f"[{label}] ❄️ zayıf saat {hour_tr:02d}:00 — ${base:.0f} → ${amount:.0f} (-30%)")



# ── Güçlü / zayıf saat (En Etkili Zaman) ──
# Zayıf saatte tutar -%30 (open blok yok). Güçlü saat artık tutarı etkilemez;
# SLOT_FORCE_WR yalnızca hafta sonu duraklama bypass'ında kullanılır.
SLOT_FORCE_WR = 85.0
SLOT_COLD_BAD_DAYS = 3
SLOT_COLD_LOSSES = 4


def hour_slot_detail(history: list, hour_tr: int, *, min_trades: int = 1) -> dict | None:
    day_data: dict[int, dict[str, int]] = {}
    for tr in history or []:
        if tr.get("entry_hour_tr") != hour_tr:
            continue
        dow = tr.get("entry_dow")
        if dow is None:
            continue
        day_data.setdefault(dow, {"w": 0, "t": 0})
        day_data[dow]["t"] += 1
        if tr.get("win"):
            day_data[dow]["w"] += 1
    if not day_data:
        return None
    all_w = sum(v["w"] for v in day_data.values())
    all_t = sum(v["t"] for v in day_data.values())
    if all_t < min_trades:
        return None
    good_days = sum(1 for v in day_data.values() if v["t"] >= 1 and v["w"] / v["t"] > 0.5)
    bad_days = sum(1 for v in day_data.values() if v["t"] >= 1 and v["w"] / v["t"] <= 0.5)
    return {
        "hour": hour_tr,
        "w": all_w,
        "t": all_t,
        "losses": all_t - all_w,
        "wr": round(all_w / all_t * 100, 1) if all_t else 0.0,
        "good_days": good_days,
        "bad_days": bad_days,
    }


def is_slot_force_hot(history: list, hour_tr: int) -> bool:
    d = hour_slot_detail(history, hour_tr, min_trades=HOT_HOUR_MIN_TRADES)
    return bool(d and d["wr"] > SLOT_FORCE_WR)


def is_slot_cold_block(history: list, hour_tr: int) -> tuple[bool, str]:
    d = hour_slot_detail(history, hour_tr, min_trades=1)
    if not d:
        return False, ""
    if d["bad_days"] >= SLOT_COLD_BAD_DAYS:
        return True, (
            f"soğuk saat {hour_tr:02d}:00 — {d['bad_days']} başarısız gün "
            f"(WR %{d['wr']:.0f}, {d['w']}/{d['t']})"
        )
    if d["losses"] >= SLOT_COLD_LOSSES:
        return True, (
            f"soğuk saat {hour_tr:02d}:00 — {d['losses']} kayıp "
            f"(WR %{d['wr']:.0f}, {d['w']}/{d['t']})"
        )
    return False, ""


def resolve_open_slot_gates(
    history: list,
    hour_tr: int,
    base_amount: float,
) -> tuple[bool, float, bool, bool, str]:
    """(skip, amount, force_hot, cold_cut, note). skip her zaman False — soğuk saat gate kaldırıldı.

    Güçlü saatte sabit $25'e zorlama kaldırıldı (aynı hot-hour gürültüsü, daha büyük
    çarpan). is_slot_force_hot yalnızca hafta sonu duraklama bypass'ında kullanılır.
    """
    amount, hot_boost, cold_cut = resolve_slot_trade_amount(base_amount, hour_tr, history)
    return False, amount, hot_boost, cold_cut, ""


def apply_hot_hour_boost(
    base_amount: float,
    hour_tr: int,
    history: list,
    boost: float = HOT_HOUR_BOOST,
) -> tuple[float, bool]:
    """En etkili saatlerde giriş tutarını artır. HOT_HOUR_BOOST=1.0 olduğu için nötr."""
    if hour_tr in compute_top_slot_hours(history):
        return round(base_amount * boost, 2), True
    return base_amount, False


def apply_cold_hour_cut(
    base_amount: float,
    hour_tr: int,
    history: list,
    *,
    cut: float = COLD_HOUR_CUT,
) -> tuple[float, bool]:
    """En başarısız saatlerde giriş tutarını düşür (varsayılan -%30)."""
    if hour_tr in compute_top_slot_hours(history):
        return base_amount, False
    if hour_tr in compute_bottom_slot_hours(history):
        return round(base_amount * cut, 2), True
    return base_amount, False


def trades_for_exit_day(history: list, day) -> list:
    """exit_time_tr (İST) belirtilen takvim gününe düşen kapalı işlemler."""
    ds = day.isoformat()
    out = [
        t for t in history
        if (t.get("exit_time_tr") or "")[:10] == ds
    ]
    out.sort(key=lambda t: t.get("exit_time_tr") or "")
    return out


def format_daily_history_tg(
    label: str,
    trades: list,
    day,
    now_tr: datetime | None = None,
    suffix: str = "",
) -> list[str]:
    """Günlük işlem geçmişi Telegram mesaj(ları). 4096 karakter sınırına böler."""
    now_tr = now_tr or datetime.now(_TZ_TR)
    day_str = day.strftime("%d.%m.%Y")
    wins = sum(1 for t in trades if t.get("win"))
    total = len(trades)
    pnl = round(sum(float(t.get("pnl") or 0) for t in trades), 2)
    pnl_icon = "🟢" if pnl >= 0 else "🔴"

    header = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📋 <b>{label} — Günlük Rapor ({day_str})</b>",
        f"🕐 {now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"📊 {wins}/{total} kazanç  |  {pnl_icon} Net: {pnl:+.2f}$",
    ]
    if suffix:
        header.append(suffix)
    header.append("")

    if not trades:
        return ["\n".join(header + ["ℹ️ Bu gün kapanan işlem yok."])]

    def _fmt_time(iso: str) -> str:
        if not iso or len(iso) < 16:
            return "??:??"
        return iso[11:16]

    body_lines = []
    for i, t in enumerate(reversed(trades), 1):
        sym = (t.get("symbol") or "").replace("USDT", "")
        pred = t.get("predicted_dir", "?")
        actual = t.get("actual_dir", "?")
        icon = "✅" if t.get("win") else "❌"
        pnl_t = float(t.get("pnl") or 0)
        amt = float(t.get("amount") or t.get("pm_spent") or 0)
        t0 = _fmt_time(t.get("entry_time_tr", ""))
        t1 = _fmt_time(t.get("exit_time_tr", ""))
        body_lines.append(
            f"{i}. {icon} <b>{sym}</b> {pred}→{actual}  ${amt:.0f}  {pnl_t:+.2f}$\n"
            f"   {t0} → {t1}"
        )

    chunks: list[str] = []
    current = header[:]
    for line in body_lines:
        candidate = "\n".join(current + [line])
        if len(candidate) > 3900 and len(current) > len(header):
            chunks.append("\n".join(current))
            current = [f"📋 <b>{label} — devam ({day_str})</b>", ""]
        current.append(line)
    chunks.append("\n".join(current))
    return chunks
