"""
5M 104 BTC TRADER — Stochastic RSI K/D (Sanal)
==============================================
Stochastic RSI (14, 3, 3) K/D crossover — tek algoritma.

Sinyal:
  Oversold + K>D cross  → UP
  Overbought + K<D cross → DOWN
  Aksi halde → işlem yok

Miktar: $10 sabit (sinyal varsa)
Market: btc-updown-5m-{unix_timestamp}
Bütçe:  $500 sanal
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
STATE_FILE   = os.path.join(_DIR, "poly_trader_5m_btc_104_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_5m_btc_104_history.json")
WEEKLY_IMG   = "/tmp/poly_5m_btc_104_weekly.png"

SYMBOL           = "BTCUSDT"
INITIAL_BALANCE  = 500.0
AMOUNT_SIGNAL    = 10.0   # Stoch RSI sinyali varsa sabit
_PERIOD_SECS     = 300    # 5 dakika = 300 saniye
_DAYS_TR         = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_DAYS_FULL_TR    = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

# Polymarket
_PM_GAMMA_URL = "https://gamma-api.polymarket.com/events"
_PM_CLOB_HOST = "https://clob.polymarket.com"
_PM_HEADERS   = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_PM_DRY_RUN   = True   # Sanal: gerçek işlem açmaz

LABEL = "5M 104 BTC"


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


def _stoch_rsi(closes: list[float], period: int = 14, k_period: int = 3, d_period: int = 3):
    """Stochastic RSI — K ve D çizgilerini döndür."""
    if len(closes) < period * 2:
        return 50.0, 50.0
    rsi_vals = []
    for i in range(period, len(closes)):
        rsi_vals.append(_rsi(closes[:i + 1], period))
    if not rsi_vals:
        return 50.0, 50.0
    k_raw = []
    for i in range(period - 1, len(rsi_vals)):
        window = rsi_vals[i - period + 1: i + 1]
        lo = min(window); hi = max(window)
        k_raw.append((rsi_vals[i] - lo) / (hi - lo) * 100 if hi != lo else 50.0)
    if not k_raw:
        return 50.0, 50.0
    k_smooth = _ema(k_raw, k_period)
    d_smooth = _ema(k_smooth, d_period)
    return k_smooth[-1], d_smooth[-1]


# ── Stochastic RSI K/D (14, 3, 3) ───────────────────────────

def algo_stoch_rsi_kd(klines: list[dict]) -> tuple[int, str, float, float]:
    """Stochastic RSI K/D crossover — aşırı alım/satım bölgesinde sinyal."""
    closes = [k["close"] for k in klines]
    k_val, d_val = _stoch_rsi(closes, 14, 3, 3)

    oversold   = k_val < 25 and d_val < 25
    overbought = k_val > 75 and d_val > 75
    k_above_d  = k_val > d_val

    if oversold and k_above_d:
        vote = +1
    elif overbought and not k_above_d:
        vote = -1
    else:
        vote = 0

    arr = "↑" if vote > 0 else "↓" if vote < 0 else "→"
    zone = "oversold" if oversold else "overbought" if overbought else "nötr"
    lbl = f"StochRSI {arr}  K:{k_val:.0f}  D:{d_val:.0f}  ({zone})"
    return vote, lbl, k_val, d_val


# ── Analiz ────────────────────────────────────────────────────
def analyze() -> dict | None:
    """5M 104: Stoch RSI K/D sinyali varsa işlem aç."""
    try:
        klines = fetch_klines_5m(SYMBOL, 150)
    except Exception as e:
        print(f"[{LABEL}] Veri hatası: {e}", file=sys.stderr)
        return None

    entry_price = klines[-1]["open"]   # PM price-to-beat
    vote, label, k_val, d_val = algo_stoch_rsi_kd(klines)

    if vote > 0:
        direction = "UP"
    elif vote < 0:
        direction = "DOWN"
    else:
        direction = None

    if direction:
        return {
            "direction":   direction,
            "consensus":   1,
            "vote":        vote,
            "label":       label,
            "k_val":       k_val,
            "d_val":       d_val,
            "entry_price": entry_price,
            "amount":      AMOUNT_SIGNAL,
        }

    return {
        "direction":   None,
        "consensus":   0,
        "vote":        vote,
        "label":       label,
        "k_val":       k_val,
        "d_val":       d_val,
        "entry_price": entry_price,
        "amount":      0.0,
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
            if prev_close is None:
                continue
            entry  = pos["entry_price"]
            pred   = pos["predicted_dir"]
            amount = pos.get("amount", AMOUNT_SIGNAL)
            to_win = pos.get("to_win", amount * 2)

            ref_open = prev_open if prev_open is not None else entry
            actual = "UP" if prev_close >= ref_open else "DOWN"
            win    = (pred == actual)

            # Açılışta amount düşülmüştü → kazanınca to_win eklenir, kaybedince sıfır
            if win:
                state["balance"] = round(state["balance"] + to_win, 2)
                pnl = round(to_win - amount, 2)      # net kar
            else:
                pnl = -amount                         # zaten düşülmüştü

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
                "to_win":           to_win,
                "pnl":              pnl,
                "entry_time_tr":    pos["entry_time_tr"],
                "entry_period_min": pos.get("entry_period_min"),
                "entry_dow":        pos.get("entry_dow"),
                "exit_time_tr":     now_tr.isoformat(),
                "consensus":        pos.get("consensus"),
                "vote":             pos.get("vote"),
                "label":            pos.get("label"),
                "pm_slug":          pos.get("pm_slug"),
                "pm_dry_run":       _PM_DRY_RUN,
            })

            icon    = "✅" if win else "❌"
            pct     = (prev_close - ref_open) / ref_open * 100
            pnl_str = f"+${pnl:.2f}" if win else f"-${amount:.0f}"
            dir_tr  = "YÜKSELİR" if pred == "UP" else "DÜŞER"
            closed_lines.append(
                f"{icon} BTC {dir_tr}  {ref_open:,.0f}→{prev_close:,.0f} ({pct:+.1f}%)"
                f"  {'kazandı +$'+f'{to_win:.2f}' if win else 'kaybetti -$'+f'{amount:.0f}'}"
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
    label     = result.get("label", "")
    k_val     = result.get("k_val", 0)
    d_val     = result.get("d_val", 0)
    vote      = result.get("vote", 0)
    entry_p   = result["entry_price"]
    next_time = now_tr + timedelta(minutes=5)
    next_saat = next_time.strftime("%H:%M")

    # Geçmiş istatistik
    prev_wins, prev_total = get_stats(history, period_min)
    all_wins, all_total   = get_all_stats(history)

    sep = "━" * 26

    if direction is None:
        msg = (
            f"{sep}\n"
            f"⏸ <b>{LABEL} — {saat} İST</b>\n"
            f"Sinyal yok → işlem açılmadı\n"
            f"💰 Bakiye: ${state['balance']:.2f}\n"
            f"{sep}"
        )
        tg_send(msg)
        print(f"[{LABEL}] {saat} — sinyal yok (K:{k_val:.0f} D:{d_val:.0f})")
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

    if not _PM_DRY_RUN and pm_info and not pm_info.get("closed"):
        token_id = pm_info["up_token"] if direction == "UP" else pm_info["down_token"]
        _pm_place_order(token_id, amount, pm_info["tick_size"], pm_info["neg_risk"])

    # Bakiyeden giriş miktarını düş
    state["balance"] = round(state["balance"] - amount, 2)

    # Pozisyonu state'e kaydet
    state["open_positions"].append({
        "symbol":           SYMBOL,
        "predicted_dir":    direction,
        "entry_price":      entry_p,
        "amount":           amount,
        "to_win":           to_win,
        "token_price":      token_price,
        "consensus":        consensus,
        "vote":             vote,
        "label":            label,
        "k_val":            k_val,
        "d_val":            d_val,
        "entry_time_tr":    now_tr.isoformat(),
        "entry_period_min": period_min,
        "entry_dow":        dow,
        "pm_slug":          pm_slug,
        "ts_5m":            ts_5m,
    })
    save_state(state)

    # Bildirim
    dir_tr    = "YÜKSELİR" if direction == "UP" else "DÜŞER"
    dir_icon  = "📈" if direction == "UP" else "📉"
    sig_icon  = "🟢" if vote > 0 else "🔴"
    price_str = f"@{token_price:.2f}" if token_price else ""
    dry_str   = "  🔶 SANAL" if _PM_DRY_RUN else ""

    msg = (
        f"{sep}\n"
        f"🆕 <b>{LABEL} — {saat} → {next_saat}</b>{dry_str}\n"
        f"{dir_icon} <b>BTC {dir_tr}</b>  StochRSI K/D  💵 ${amount:.0f} {price_str} → 🏆 ${to_win:.2f}\n"
        f"Giriş: {entry_p:,.2f} USDT\n"
        f"  {sig_icon} {label}\n"
        f"🕐 Bu periyot: {_wr(prev_wins, prev_total)}  |  Genel: {_wr(all_wins, all_total)}\n"
        f"💰 Bakiye: ${state['balance']:.2f}  |  🔴 ${amount:.0f} riskte\n"
        f"{sep}"
    )
    tg_send(msg)
    print(f"[{LABEL}] {saat} — {dir_tr} StochRSI  ${amount:.0f}→${to_win:.2f}  entry:{entry_p:,.2f}")


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

        # Stoch RSI sinyal başarısı
        sig_hist = [t for t in history if t.get("consensus") == 1]
        if sig_hist:
            sw = sum(1 for t in sig_hist if t["win"])
            bar = "🟢" if sw/len(sig_hist) >= 0.6 else "🟡" if sw/len(sig_hist) >= 0.5 else "🔴"
            parts.append(f"\n🎯 <b>Stoch RSI K/D</b>: {bar} {_wr(sw, len(sig_hist))}")

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
