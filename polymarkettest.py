"""
Polymarket Bahis Botu
CLOB API üzerinden Polymarket'e gerçek bahis girer.

Gereksinimler:
  .env dosyasında şunlar olmalı:
    POLY_PRIVATE_KEY   = 0x...  (Polygon cüzdan private key)
    POLY_FUNDER        = 0x...  (Polymarket.com'da görünen cüzdan adresi)
    POLY_API_KEY       = ...    (ilk çalıştırmada otomatik türetilir)
    POLY_API_SECRET    = ...
    POLY_API_PASSPHRASE= ...

Akış:
  1. python3 polymarkettest.py --setup          → API key türet, .env'e yaz
  2. python3 polymarkettest.py --predict btc    → BTC/ETH saatlik yön tahmini
  3. python3 polymarkettest.py --markets        → Açık marketleri listele
  4. python3 polymarkettest.py --balance        → USDC bakiyeni gör
  5. python3 polymarkettest.py --bet <token_id> <yes|no> <fiyat> <miktar>
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

HOST       = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"
CHAIN_ID   = 137  # Polygon mainnet

# ========== YARDIMCI ==========

def _now_str():
    now = datetime.now(timezone.utc)
    return f"{now.strftime('%d.%m.%Y')} {(now.hour+3)%24:02d}:{now.strftime('%M')} İST"

def _get(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  ❌ GET hatası: {e}")
        return None

def _env_set(key, value):
    """Mevcut .env dosyasına anahtar=değer yazar ya da günceller."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}\n")
    with open(env_path, "w") as f:
        f.writelines(new_lines)

# ========== SAATLIK YÖN TAHMİN SİSTEMİ ==========

def _get_klines(symbol, interval="1h", limit=200):
    """OKX önce, Binance yedek."""
    base       = symbol.upper().replace("USDT", "")
    okx_symbol = f"{base}-USDT-SWAP"
    okx_url    = (f"https://www.okx.com/api/v5/market/candles"
                  f"?instId={okx_symbol}&bar=1H&limit={limit}")
    try:
        req = urllib.request.Request(okx_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data.get("code") == "0" and data.get("data"):
            candles = list(reversed(data["data"]))
            return {
                "closes":  [float(d[4]) for d in candles],
                "highs":   [float(d[2]) for d in candles],
                "lows":    [float(d[3]) for d in candles],
                "volumes": [float(d[5]) for d in candles],
                "source":  "OKX",
            }
    except Exception:
        pass
    url = (f"https://api.binance.com/api/v3/klines"
           f"?symbol={symbol.upper()}USDT&interval=1h&limit={limit}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        return {
            "closes":  [float(d[4]) for d in data],
            "highs":   [float(d[2]) for d in data],
            "lows":    [float(d[3]) for d in data],
            "volumes": [float(d[5]) for d in data],
            "source":  "Binance",
        }
    except Exception:
        return None

def _ema(series, n):
    if len(series) < n:
        return []
    k      = 2 / (n + 1)
    result = [sum(series[:n]) / n]
    for v in series[n:]:
        result.append(v * k + result[-1] * (1 - k))
    return result

def _rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    deltas   = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    gains    = [max(d, 0)      for d in deltas]
    losses   = [abs(min(d, 0)) for d in deltas]
    ag = sum(gains[-n:]) / n
    al = sum(losses[-n:]) / n
    return round(100 - 100 / (1 + ag / al), 2) if al else 100.0

def _macd(closes, fast=12, slow=26, sig=9):
    ef = _ema(closes, fast)
    es = _ema(closes, slow)
    ml = min(len(ef), len(es))
    line   = [ef[-(ml-i)] - es[-(ml-i)] for i in range(ml)]
    signal = _ema(line, sig)
    if not signal:
        return None, None, None
    hist = line[-1] - signal[-1]
    return round(line[-1], 4), round(signal[-1], 4), round(hist, 4)

def _adx(highs, lows, closes, n=14):
    if len(closes) < n * 2:
        return None
    trs, dmp, dmm = [], [], []
    for i in range(1, len(closes)):
        tr  = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        up  = highs[i] - highs[i-1]
        dn  = lows[i-1] - lows[i]
        trs.append(tr)
        dmp.append(up if up > dn and up > 0 else 0)
        dmm.append(dn if dn > up and dn > 0 else 0)
    def _smooth(arr):
        s = sum(arr[:n])
        r = [s]
        for v in arr[n:]:
            r.append(r[-1] - r[-1]/n + v)
        return r
    atr_s = _smooth(trs)
    dmp_s = _smooth(dmp)
    dmm_s = _smooth(dmm)
    dx = []
    for i in range(len(atr_s)):
        dip = 100 * dmp_s[i] / atr_s[i] if atr_s[i] else 0
        dim = 100 * dmm_s[i] / atr_s[i] if atr_s[i] else 0
        den = dip + dim
        dx.append(100 * abs(dip - dim) / den if den else 0)
    adx_list = _ema(dx, n)
    return round(adx_list[-1], 2) if adx_list else None

def _atr(highs, lows, closes, n=14):
    trs = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
           for i in range(1, len(closes))]
    vals = _ema(trs, n)
    return vals[-1] if vals else None

def _bb(closes, n=20, mult=2.0):
    """Bollinger Bands — %B değeri döner (0=alt band, 1=üst band)."""
    if len(closes) < n:
        return None
    window = closes[-n:]
    mid    = sum(window) / n
    std    = (sum((v - mid)**2 for v in window) / n) ** 0.5
    upper  = mid + mult * std
    lower  = mid - mult * std
    price  = closes[-2]
    if upper == lower:
        return 0.5
    return round((price - lower) / (upper - lower), 3)


def predict(coin="btc"):
    """
    BTC veya ETH için saatlik yön tahmini yapar.
    EMA 9/21/50/200, RSI 14, MACD 12/26/9, ADX 14, BB %B,
    Hacim trendi, Momentum skoru hesaplar.
    Döner: dict (direction, score, confidence, ...)
    """
    symbol = coin.upper()
    if not symbol.endswith("USDT"):
        symbol = symbol + "USDT"

    raw = _get_klines(symbol)
    if not raw:
        print(f"  ❌ {symbol} verisi alınamadı.")
        return None

    closes  = raw["closes"]
    highs   = raw["highs"]
    lows    = raw["lows"]
    volumes = raw["volumes"]

    price = closes[-2]

    # İndikatörler
    ema9   = _ema(closes, 9)[-1]   if len(closes) >= 9   else None
    ema21  = _ema(closes, 21)[-1]  if len(closes) >= 21  else None
    ema50  = _ema(closes, 50)[-1]  if len(closes) >= 50  else None
    ema200 = _ema(closes, 200)[-1] if len(closes) >= 200 else None
    rsi    = _rsi(closes[-30:])
    rsi_prev = _rsi(closes[-31:-1])
    macd_val, macd_sig, macd_hist = _macd(closes)
    adx    = _adx(highs, lows, closes)
    atr    = _atr(highs, lows, closes)
    bb_pct = _bb(closes)

    vol_avg   = sum(volumes[-20:]) / 20
    vol_ratio = round(volumes[-2] / vol_avg, 2) if vol_avg else 1.0

    # ── Skor sistemi ──
    # Her sinyal -2 ile +2 arası puan verir (+ = UP, - = DOWN)
    signals = {}

    # EMA sıralaması
    if ema9 and ema21 and ema50:
        if price > ema9 > ema21 > ema50:
            signals["EMA_stack"] = (+2, "fiyat > EMA9 > EMA21 > EMA50 (güçlü yükseliş dizisi)")
        elif price < ema9 < ema21 < ema50:
            signals["EMA_stack"] = (-2, "fiyat < EMA9 < EMA21 < EMA50 (güçlü düşüş dizisi)")
        elif price > ema21 > ema50:
            signals["EMA_stack"] = (+1, "fiyat > EMA21 > EMA50 (trend üstünde)")
        elif price < ema21 < ema50:
            signals["EMA_stack"] = (-1, "fiyat < EMA21 < EMA50 (trend altında)")
        else:
            signals["EMA_stack"] = (0, "EMA'lar karışık (konsolidasyon)")

    # EMA200 makro trend
    if ema200:
        if price > ema200:
            signals["EMA200"] = (+1, f"fiyat > EMA200 ({round(ema200,0)}) — boğa bölgesi")
        else:
            signals["EMA200"] = (-1, f"fiyat < EMA200 ({round(ema200,0)}) — ayı bölgesi")

    # RSI
    if rsi is not None:
        if rsi > 65:
            signals["RSI"] = (+1, f"RSI {rsi} — güçlü momentum")
        elif rsi > 55:
            signals["RSI"] = (+1, f"RSI {rsi} — yükselen momentum")
        elif rsi < 35:
            signals["RSI"] = (-1, f"RSI {rsi} — güçlü baskı")
        elif rsi < 45:
            signals["RSI"] = (-1, f"RSI {rsi} — düşen momentum")
        else:
            signals["RSI"] = (0,  f"RSI {rsi} — nötr bölge")

    # RSI yönü
    if rsi is not None and rsi_prev is not None:
        if rsi > rsi_prev + 2:
            signals["RSI_dir"] = (+1, f"RSI yükseliyor (+{round(rsi-rsi_prev,1)})")
        elif rsi < rsi_prev - 2:
            signals["RSI_dir"] = (-1, f"RSI düşüyor ({round(rsi-rsi_prev,1)})")
        else:
            signals["RSI_dir"] = (0, "RSI yatay")

    # MACD
    if macd_val is not None:
        if macd_val > macd_sig and macd_hist > 0:
            signals["MACD"] = (+2 if macd_hist > abs(macd_val)*0.1 else +1,
                               f"MACD bull (hist:{macd_hist:+.4f})")
        elif macd_val < macd_sig and macd_hist < 0:
            signals["MACD"] = (-2 if abs(macd_hist) > abs(macd_val)*0.1 else -1,
                               f"MACD bear (hist:{macd_hist:+.4f})")
        else:
            signals["MACD"] = (0, "MACD nötr")

    # ADX — trend gücü
    if adx is not None:
        trend_str = "çok güçlü" if adx >= 40 else "güçlü" if adx >= 25 else "zayıf"
        signals["ADX"] = (0, f"ADX {adx} — {trend_str} trend (yön vermez, güç ölçer)")

    # Bollinger %B
    if bb_pct is not None:
        if bb_pct > 0.8:
            signals["BB"] = (-1, f"BB %B={bb_pct} — üst banda yakın, aşırı alım")
        elif bb_pct < 0.2:
            signals["BB"] = (+1, f"BB %B={bb_pct} — alt banda yakın, aşırı satım")
        else:
            signals["BB"] = (0, f"BB %B={bb_pct} — orta bölge")

    # Hacim
    if vol_ratio >= 1.5:
        signals["Volume"] = (0, f"Hacim patlaması x{vol_ratio} (yön belirsiz ama güçlü)")
    elif vol_ratio >= 1.2:
        signals["Volume"] = (0, f"Hacim artışı x{vol_ratio}")
    else:
        signals["Volume"] = (0, f"Normal hacim x{vol_ratio}")

    # ── Toplam skor ──
    total_score = sum(v for v, _ in signals.values())
    max_possible = sum(abs(v) for v, _ in signals.values() if v != 0) or 1

    if total_score >= 4:
        direction, d_emoji = "UP 🟢", "🟢"
    elif total_score >= 2:
        direction, d_emoji = "UP (zayıf) 🟡", "🟡"
    elif total_score <= -4:
        direction, d_emoji = "DOWN 🔴", "🔴"
    elif total_score <= -2:
        direction, d_emoji = "DOWN (zayıf) 🟡", "🟡"
    else:
        direction, d_emoji = "NEUTRAL ⚪", "⚪"

    confidence = min(round(abs(total_score) / max_possible * 100), 95)

    # ── Yazdır ──
    print(f"\n{'='*58}")
    print(f"  📊 {symbol} — SAATLİK YÖN TAHMİNİ  |  {_now_str()}")
    print(f"  📡 Kaynak: {raw['source']}")
    print(f"{'='*58}")
    print(f"  💵 Fiyat  : ${price:,.2f}")
    if ema9:  print(f"  EMA9      : ${ema9:,.2f}  {'✅' if price>ema9 else '❌'}")
    if ema21: print(f"  EMA21     : ${ema21:,.2f}  {'✅' if price>ema21 else '❌'}")
    if ema50: print(f"  EMA50     : ${ema50:,.2f}  {'✅' if price>ema50 else '❌'}")
    if ema200:print(f"  EMA200    : ${ema200:,.2f}  {'✅' if price>ema200 else '❌'}")
    if rsi:   print(f"  RSI 14    : {rsi}")
    if macd_val: print(f"  MACD      : {macd_val:+.4f}  |  Sig: {macd_sig:+.4f}  |  Hist: {macd_hist:+.4f}")
    if adx:   print(f"  ADX       : {adx}")
    if atr:   print(f"  ATR (1h)  : ${atr:,.2f}  (%{round(atr/price*100,2)})")
    if bb_pct is not None: print(f"  BB %%B   : {bb_pct}")
    print(f"  Hacim     : x{vol_ratio} (20bar ort.)")
    print(f"{'─'*58}")
    print(f"  SİNYALLER:")
    for name, (score, desc) in signals.items():
        arrow = "▲" if score > 0 else "▼" if score < 0 else "─"
        print(f"  {arrow} [{score:+d}]  {name:<10}  {desc}")
    print(f"{'─'*58}")
    print(f"  TOPLAM SKOR  : {total_score:+d} / maks±{max_possible}")
    print(f"  YÖN TAHMİNİ : {direction}")
    print(f"  GÜVEN        : %{confidence}")
    print(f"{'='*58}\n")

    return {
        "symbol":     symbol,
        "price":      price,
        "direction":  direction,
        "score":      total_score,
        "confidence": confidence,
        "rsi":        rsi,
        "adx":        adx,
        "macd_bull":  macd_val > macd_sig if macd_val else None,
    }


# ========== SETUP: API KEY TÜRET ==========

def setup():
    """
    Private key'den L2 API credentials türetir ve .env'e kaydeder.
    Sadece bir kere çalıştırılır.
    """
    private_key = os.getenv("POLY_PRIVATE_KEY")
    funder      = os.getenv("POLY_FUNDER")

    if not private_key or not funder:
        print("❌ .env içinde POLY_PRIVATE_KEY ve POLY_FUNDER gerekli.")
        print("   Örnek:")
        print("   POLY_PRIVATE_KEY=0xabc123...")
        print("   POLY_FUNDER=0xYourPolymarketWalletAddress")
        return

    try:
        from py_clob_client.client import ClobClient
        client = ClobClient(host=HOST, chain_id=CHAIN_ID, key=private_key)
        creds  = client.create_or_derive_api_creds()
        print("✅ API credentials türetildi:")
        print(f"   API Key    : {creds.api_key}")
        print(f"   Secret     : {creds.api_secret[:8]}...")
        print(f"   Passphrase : {creds.api_passphrase[:8]}...")
        _env_set("POLY_API_KEY",        creds.api_key)
        _env_set("POLY_API_SECRET",     creds.api_secret)
        _env_set("POLY_API_PASSPHRASE", creds.api_passphrase)
        print("✅ .env dosyasına kaydedildi. Artık işlem yapabilirsin.")
    except Exception as e:
        print(f"❌ Setup hatası: {e}")

# ========== MARKETLERİ LİSTELE ==========

def list_markets(query="", limit=10):
    """
    Gamma API'den açık marketleri çeker.
    query: arama terimi (ör: 'trump', 'bitcoin', 'election')
    """
    url = f"{GAMMA_HOST}/markets?active=true&closed=false&limit={limit}"
    if query:
        url += f"&_textSearch={urllib.parse.quote(query)}"

    data = _get(url)
    if not data:
        return

    markets = data if isinstance(data, list) else data.get("markets", [])
    print(f"\n{'='*60}")
    print(f"  POLYMARKET — Açık Marketler ({len(markets)})")
    print(f"{'='*60}")
    for m in markets:
        question = m.get("question", "?")[:55]
        volume   = m.get("volumeNum", 0)
        outcomes = m.get("outcomes", [])
        prices   = m.get("outcomePrices", [])
        tokens   = m.get("tokens", [])

        print(f"\n  📋 {question}")
        print(f"     Hacim: ${volume:,.0f}")
        for i, outcome in enumerate(outcomes):
            price     = float(prices[i]) if i < len(prices) else 0
            token_id  = tokens[i].get("token_id", "?") if i < len(tokens) else "?"
            print(f"     {'✅' if i==0 else '❌'} {outcome:<8} → %{price*100:.0f}  |  token_id: {token_id[:20]}...")
    print(f"\n{'='*60}\n")

# ========== BAKİYE ==========

def get_balance():
    private_key = os.getenv("POLY_PRIVATE_KEY")
    api_key     = os.getenv("POLY_API_KEY")
    api_secret  = os.getenv("POLY_API_SECRET")
    api_pass    = os.getenv("POLY_API_PASSPHRASE")
    funder      = os.getenv("POLY_FUNDER")

    if not all([private_key, api_key, api_secret, api_pass, funder]):
        print("❌ .env eksik. Önce --setup çalıştır.")
        return

    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
        creds  = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_pass)
        client = ClobClient(host=HOST, chain_id=CHAIN_ID, key=private_key,
                            creds=creds, signature_type=1, funder=funder)
        bal = client.get_balance_allowance()
        print(f"\n  💰 USDC Bakiye   : ${float(bal.get('balance', 0)):,.2f}")
        print(f"  🔓 İzin (allowance): ${float(bal.get('allowance', 0)):,.2f}\n")
    except Exception as e:
        print(f"❌ Bakiye hatası: {e}")

# ========== BAHİS GİR ==========

def place_bet(token_id, side, price, size):
    """
    token_id : Outcome token ID (list_markets'tan alınır)
    side     : 'yes' / 'no' → BUY / SELL
    price    : 0.01 – 0.99 (kaçta 1 pay → örn: 0.65 = %65 ihtimal)
    size     : kaç USDC değerinde pay alacaksın
    """
    private_key = os.getenv("POLY_PRIVATE_KEY")
    api_key     = os.getenv("POLY_API_KEY")
    api_secret  = os.getenv("POLY_API_SECRET")
    api_pass    = os.getenv("POLY_API_PASSPHRASE")
    funder      = os.getenv("POLY_FUNDER")

    if not all([private_key, api_key, api_secret, api_pass, funder]):
        print("❌ .env eksik. Önce --setup çalıştır.")
        return

    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY, SELL

    direction = BUY if side.lower() == "yes" else SELL
    price_f   = float(price)
    size_f    = float(size)

    if not (0.01 <= price_f <= 0.99):
        print("❌ Fiyat 0.01 ile 0.99 arasında olmalı.")
        return
    if size_f < 1:
        print("❌ Minimum bahis 1 USDC.")
        return

    try:
        creds  = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_pass)
        client = ClobClient(host=HOST, chain_id=CHAIN_ID, key=private_key,
                            creds=creds, signature_type=1, funder=funder)

        order_args = OrderArgs(
            token_id=token_id,
            price=price_f,
            size=size_f,
            side=direction,
        )
        signed   = client.create_order(order_args)
        response = client.post_order(signed, OrderType.GTC)

        print(f"\n  ✅ BAHİS GİRİLDİ!")
        print(f"     Token    : {token_id[:30]}...")
        print(f"     Yön      : {'YES (BUY)' if direction==BUY else 'NO (SELL)'}")
        print(f"     Fiyat    : {price_f} (%{price_f*100:.0f} ihtimal)")
        print(f"     Miktar   : {size_f} USDC")
        print(f"     Order ID : {response.get('orderID', '?')}")
        print(f"     Durum    : {response.get('status', '?')}\n")
        return response

    except Exception as e:
        print(f"❌ Bahis hatası: {e}")

# ========== AÇIK POZİSYONLAR ==========

def open_orders():
    private_key = os.getenv("POLY_PRIVATE_KEY")
    api_key     = os.getenv("POLY_API_KEY")
    api_secret  = os.getenv("POLY_API_SECRET")
    api_pass    = os.getenv("POLY_API_PASSPHRASE")
    funder      = os.getenv("POLY_FUNDER")

    if not all([private_key, api_key, api_secret, api_pass, funder]):
        print("❌ .env eksik.")
        return

    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
        creds  = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_pass)
        client = ClobClient(host=HOST, chain_id=CHAIN_ID, key=private_key,
                            creds=creds, signature_type=1, funder=funder)
        orders = client.get_orders()
        if not orders:
            print("\n  ℹ️  Açık emir yok.\n")
            return
        print(f"\n{'='*60}")
        print(f"  Açık Emirler ({len(orders)})")
        print(f"{'='*60}")
        for o in orders:
            print(f"  {o.get('side','?'):5} | fiyat:{o.get('price','?')} | "
                  f"miktar:{o.get('size','?')} | durum:{o.get('status','?')}")
        print()
    except Exception as e:
        print(f"❌ Emir listesi hatası: {e}")

# ========== CLI ==========

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] == "--help":
        print(__doc__)
    elif args[0] == "--predict":
        coin = args[1] if len(args) > 1 else "btc"
        predict(coin)
    elif args[0] == "--setup":
        setup()
    elif args[0] == "--markets":
        query = args[1] if len(args) > 1 else ""
        list_markets(query)
    elif args[0] == "--balance":
        get_balance()
    elif args[0] == "--orders":
        open_orders()
    elif args[0] == "--bet":
        if len(args) < 5:
            print("Kullanım: --bet <token_id> <yes|no> <fiyat 0.01-0.99> <usdc_miktar>")
        else:
            place_bet(args[1], args[2], args[3], args[4])
    else:
        print(f"Bilinmeyen komut: {args[0]}")
        print("--help ile komutları gör.")
