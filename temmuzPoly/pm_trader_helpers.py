"""Polymarket order yardımcıları — gerçek PM trader'lar için ortak."""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_PM_CLOB_HOST = "https://clob.polymarket.com"
_PM_GAMMA_URL = "https://gamma-api.polymarket.com/events"
_PM_HEADERS   = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_PM_ASSET_MAP = {
    "BTCUSDT": "bitcoin", "ETHUSDT": "ethereum", "SOLUSDT": "solana",
    "XRPUSDT": "xrp", "DOGEUSDT": "dogecoin", "BNBUSDT": "bnb",
}
_TZ_TR = ZoneInfo("Europe/Istanbul")
PM_DRY_RUN = os.getenv("POLY_DRY_RUN", "true").lower() == "true"


def in_weekend_pause_tr(now_tr: datetime) -> bool:
    """Cuma 22:00 – Pazar 18:00 İST arası yeni işlem açılmaz."""
    dow = now_tr.weekday()  # 0=Pzt … 4=Cum 5=Cmt 6=Paz
    h = now_tr.hour
    if dow == 4 and h >= 22:
        return True
    if dow == 5:
        return True
    if dow == 6 and h < 18:
        return True
    return False


# Sanal trader giriş tutarları (1. Analiz mantığı — A5 hariç ortak)
SANAL_INITIAL_BALANCE = 300.0
SANAL_TRADE_AMOUNT = 16.0       # sembol WR veri yok veya tam %50
SANAL_TRADE_AMOUNT_HIGH = 20.0  # sembol genel WR > %50
SANAL_TRADE_AMOUNT_LOW = 12.0   # sembol genel WR < %50


def symbol_wr_amount(history: list, symbol: str) -> float:
    """Sembol bazlı geçmiş WR'ye göre işlem tutarı ($12 / $16 / $20)."""
    trades = [t for t in history if t.get("symbol") == symbol]
    if not trades:
        return SANAL_TRADE_AMOUNT
    wins = sum(1 for t in trades if t.get("win"))
    rate = wins / len(trades)
    if rate > 0.5:
        return SANAL_TRADE_AMOUNT_HIGH
    if rate < 0.5:
        return SANAL_TRADE_AMOUNT_LOW
    return SANAL_TRADE_AMOUNT


def pm_get_client():
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
            print(f"[PM] Client init ({attempt+1}/3): {e}", file=sys.stderr)
            time.sleep(2)
    raise RuntimeError("Polymarket client oluşturulamadı")


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


def pm_place_order(
    token_id: str, amount_usd: float, tick_size: str = "0.01",
    neg_risk: bool = False, *, label: str = "PM", hata_file: str | None = None,
    _retry: bool = True,
) -> dict | None:
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
        if PM_DRY_RUN:
            print(f"[{label} DRY RUN] {token_id[:16]}… {size} shares @ {price:.2f} (~${spent:.2f})")
            return {"order_id": "DRY_RUN", "size": size, "price": price, "spent": spent}
        args = OrderArgs(token_id=token_id, price=price, size=size, side=BUY)
        signed = client.create_order(args, PartialCreateOrderOptions())
        resp   = client.post_order(signed, order_type=OrderType.FAK)
        if not resp or not resp.get("success"):
            mesaj = str(resp)
            print(f"[{label}] Order başarısız: {mesaj}", file=sys.stderr)
            if _retry:
                time.sleep(10)
                return pm_place_order(
                    token_id, amount_usd, tick_size, neg_risk,
                    label=label, hata_file=hata_file, _retry=False,
                )
            if hata_file:
                pm_log_hata(hata_file, token_id[:20], "order_basarisiz", mesaj)
            return None
        oid = resp.get("orderID") or resp.get("id", "")
        return {"order_id": oid, "size": size, "price": price, "spent": spent}
    except Exception as e:
        print(f"[{label}] Order hatası: {e}", file=sys.stderr)
        if _retry:
            time.sleep(10)
            return pm_place_order(
                token_id, amount_usd, tick_size, neg_risk,
                label=label, hata_file=hata_file, _retry=False,
            )
        if hata_file:
            pm_log_hata(hata_file, token_id[:20], "order_exception", str(e))
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
        pnl_val  = round(pm_size - pm_spent, 2) if our_won else round(-pm_spent, 2)
        extra    = f"  |  🎯PM: {'+'if our_won else ''}{pnl_val:.2f}$"
        return our_won, pnl_val, extra
    except Exception as e:
        print(f"[PM] Sonuç hatası: {e}", file=sys.stderr)
        return None, 0.0, ""


def pm_sanal_quote(symbol: str, direction: str, amount_usd: float, now: datetime) -> dict | None:
    """1h PM gamma fiyatından sanal kotasyon (emir yok)."""
    et_hour = (now - timedelta(hours=4)).hour
    pm = pm_find_market(symbol, et_hour, now)
    if not pm or pm.get("closed"):
        return None
    op = pm.get("outcome_prices") or []
    if len(op) < 2:
        return None
    tp = float(op[0]) if direction == "UP" else float(op[1])
    if not (0.02 <= tp <= 0.98):
        return None
    size = round(amount_usd / tp, 2)
    spent = round(size * tp, 2)
    return {
        "pm_slug": pm["slug"],
        "pm_title": pm.get("title", ""),
        "pm_token_dir": direction,
        "pm_entry_price": tp,
        "pm_spent": spent,
        "pm_size": size,
        "to_win": size,
    }


def apply_pm_quote(pos: dict, symbol: str, direction: str, amount: float, now: datetime) -> dict:
    q = pm_sanal_quote(symbol, direction, amount, now)
    if q:
        pos.update(q)
    return pos


def pm_stake_fields(pos: dict) -> tuple[float, float, float]:
    """(harcama, to_win/pm_size, token_fiyat) — giriş kotasyonundan."""
    spent = float(pos.get("pm_spent") or pos.get("amount") or 0)
    entry_p = float(pos.get("pm_entry_price") or pos.get("token_price") or 0)
    size = float(pos.get("pm_size") or pos.get("to_win") or 0)
    if size <= 0 and spent > 0 and entry_p > 0:
        size = round(spent / entry_p, 2)
    return spent, size, entry_p


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
    for k in ("pm_spent", "pm_size", "pm_entry_price", "to_win", "token_price", "pm_slug", "pm_order_id", "tier"):
        if pos.get(k) is not None:
            extras[k] = pos[k]
    return extras


def sanal_pnl(pos: dict, win: bool) -> float:
    spent, size, _ = pm_stake_fields(pos)
    if size > 0 and spent > 0:
        return round(size - spent, 2) if win else round(-spent, 2)
    if not win:
        return round(-spent, 2) if spent > 0 else 0.0
    return 0.0


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
    for k in ("pm_spent", "pm_size", "pm_entry_price", "to_win", "token_price", "pm_slug", "pm_order_id"):
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
    pnl = sanal_pnl(pos, win)
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
