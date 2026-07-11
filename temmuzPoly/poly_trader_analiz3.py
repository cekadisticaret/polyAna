"""
3. ANALİZ — Stochastic RSI / ETH-Only Sanal Trader

Sadece ETHUSDT için Stochastic RSI sinyali üretir:
  - StochRSI < 20 ve yükseliyorsa → UP
  - StochRSI > 80 ve düşüyorsa   → DOWN
  - StochRSI < 50 → hafif UP, > 50 → hafif DOWN

Sanal bütçe: $300  |  İşlem başına: $10  |  DRY RUN

Modlar: open / close / weekly / stats
"""
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")

_DIR         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(_DIR, "poly_trader_analiz3_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_analiz3_history.json")

INITIAL_BALANCE = 300.0
SYMBOL          = "ETHUSDT"
TRADE_AMOUNT    = 10.0
_DAYS_TR        = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_BINANCE        = "https://fapi.binance.com"

# ── State / History ───────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE))
        except Exception:
            pass
    return {"balance": INITIAL_BALANCE, "open_positions": [], "total_pnl": 0.0}

def save_state(s: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)

def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            return json.load(open(HISTORY_FILE))
        except Exception:
            pass
    return []

def save_history(h: list):
    with open(HISTORY_FILE, "w") as f:
        json.dump(h, f, indent=2, ensure_ascii=False)

# ── Telegram ──────────────────────────────────────────────────

def tg_send(text: str):
    try:
        payload = json.dumps({"chat_id": CHAT_ID, "text": text,
                              "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[3. ANALİZ] Telegram hata: {e}", file=sys.stderr)

# ── Binance Klines ────────────────────────────────────────────

def fetch_klines(limit=100) -> list[dict]:
    url = (f"{_BINANCE}/fapi/v1/klines?symbol={SYMBOL}"
           f"&interval=1h&limit={limit}")
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.loads(r.read())
    return [{"o": float(x[1]), "h": float(x[2]), "l": float(x[3]),
             "c": float(x[4]), "v": float(x[5])} for x in data]

# ── Teknik Göstergeler ────────────────────────────────────────

def _rsi(closes: list[float], period=14) -> list:
    res = [None] * len(closes)
    if len(closes) < period + 1:
        return res
    gains  = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    res[period] = 100 - 100 / (1 + ag / al) if al else 100.0
    for i in range(period + 1, len(closes)):
        ag = (ag * (period - 1) + gains[i - 1]) / period
        al = (al * (period - 1) + losses[i - 1]) / period
        res[i] = 100 - 100 / (1 + ag / al) if al else 100.0
    return res

def stoch_rsi_signal(klines: list[dict]) -> tuple[str, float, float]:
    """
    Stochastic RSI hesapla.
    Returns: (signal: UP/DOWN/NEUTRAL, stoch_val, rsi_val)
    """
    closes = [k["c"] for k in klines]
    rv = _rsi(closes, 14)
    rsi_list = [x for x in rv if x is not None]
    if len(rsi_list) < 14:
        return "NEUTRAL", 50.0, 50.0

    rsi_val = rsi_list[-1]
    window  = rsi_list[-14:]
    mn, mx  = min(window), max(window)
    if mx == mn:
        return "NEUTRAL", 50.0, rsi_val

    st  = (rsi_list[-1] - mn) / (mx - mn) * 100
    stp = (rsi_list[-2] - mn) / (mx - mn) * 100 if len(rsi_list) >= 2 else st

    if st < 20 and st > stp:
        signal = "UP"    # Aşırı satım + toparlanıyor
    elif st > 80 and st < stp:
        signal = "DOWN"  # Aşırı alım + geri çekiliyor
    elif st < 35:
        signal = "UP"
    elif st > 65:
        signal = "DOWN"
    else:
        signal = "NEUTRAL"

    return signal, round(st, 1), round(rsi_val, 1)

# ── Yardımcılar ───────────────────────────────────────────────

def _wr(wins: int, total: int) -> str:
    if not total:
        return "veri yok"
    warn = " ⚠️" if total < 10 else ""
    return f"%{wins/total*100:.0f} ({wins}/{total}){warn}"

def get_stats(history: list) -> tuple[int, int]:
    trades = [t for t in history if t.get("symbol") == SYMBOL]
    wins   = sum(1 for t in trades if t.get("win"))
    return wins, len(trades)

def get_hour_stats(history: list, hour: int) -> tuple[int, int]:
    trades = [t for t in history if t.get("symbol") == SYMBOL
              and t.get("entry_hour_tr") == hour]
    wins   = sum(1 for t in trades if t.get("win"))
    return wins, len(trades)

# ── OPEN ──────────────────────────────────────────────────────

def run_open():
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    hour_tr    = now_tr.hour
    dow        = now_tr.weekday()
    is_weekend = dow >= 5
    saat       = now_tr.strftime("%H:%M")
    next_h     = f"{(hour_tr + 1) % 24:02d}:00"

    state   = load_state()
    history = load_history()

    # Zaten açık pozisyon varsa atla
    if state["open_positions"]:
        print(f"[3. ANALİZ open] {saat} İST — zaten açık pozisyon var, atlandı")
        return

    # Klines çek
    try:
        klines = fetch_klines(100)
    except Exception as e:
        print(f"[3. ANALİZ] klines çekme hatası: {e}", file=sys.stderr)
        return

    # Stochastic RSI sinyali
    signal, stoch_val, rsi_val = stoch_rsi_signal(klines)

    if signal == "NEUTRAL":
        print(f"[3. ANALİZ open] {saat} İST — ETH nötr, işlem açılmadı")
        tg_send(
            f"⏸ <b>3. ANALİZ (Stoch RSI / ETH)</b> — {saat} İST\n"
            f"ETH nötr → işlem açılmadı\n"
            f"StochRSI: {stoch_val} | RSI: {rsi_val}\n"
            f"💰 Sanal Bütçe: ${state['balance']:.2f}"
        )
        return

    # Giriş fiyatı: son kapanan mumun kapanışı (Polymarket Price to Beat)
    entry_price = klines[-2]["c"]

    # Dinamik miktar (sabit $10)
    amount = TRADE_AMOUNT

    # Pozisyon aç
    pos = {
        "symbol":        SYMBOL,
        "predicted_dir": signal,
        "entry_price":   entry_price,
        "amount":        amount,
        "entry_time_tr": now_tr.isoformat(),
        "entry_hour_tr": hour_tr,
        "entry_dow":     dow,
        "entry_is_weekend": is_weekend,
        "stoch_val":     stoch_val,
        "rsi_val":       rsi_val,
    }
    state["open_positions"].append(pos)
    state["balance"] -= amount
    save_state(state)

    # İstatistik
    hw, ht = get_hour_stats(history, hour_tr)
    gw, gt = get_stats(history)

    dir_icon = "📈" if signal == "UP" else "📉"
    dir_tr   = "YÜKSELİR" if signal == "UP" else "DÜŞER"
    sep = "━" * 26

    tg_send(
        f"{sep}\n"
        f"🆕 <b>3. ANALİZ (Stoch RSI / ETH)</b> — {saat} - {next_h}\n"
        f"{dir_icon} <b>ETH</b> {dir_tr}  giriş:{entry_price:.2f}\n"
        f"   StochRSI: {stoch_val} | RSI: {rsi_val}\n"
        f"   🕐 {hour_tr:02d}:00→{next_h} başarı: {_wr(hw, ht)}"
        f"  |  genel: {_wr(gw, gt)}\n"
        f"   🔶 DRY RUN: ${amount:.0f}\n"
        f"💰 Sanal Bütçe: ${state['balance']:.2f}  |  📂 Açık: 1 poz\n"
        f"{sep}"
    )
    print(f"[3. ANALİZ open] {saat} İST — ETH {signal} @{entry_price:.2f} StochRSI:{stoch_val}")

# ── CLOSE ─────────────────────────────────────────────────────

def run_close():
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    hour_tr = now_tr.hour
    saat    = now_tr.strftime("%H:%M")
    open_h  = f"{(hour_tr - 1) % 24:02d}:05"

    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        print(f"[3. ANALİZ close] {saat} İST — açık pozisyon yok")
        return

    # Güncel fiyat
    try:
        klines = fetch_klines(3)
        current_price = klines[-1]["c"]
    except Exception as e:
        print(f"[3. ANALİZ] fiyat çekme hatası: {e}", file=sys.stderr)
        return

    lines = []
    tur_pnl = 0.0
    for pos in state["open_positions"]:
        pred       = pos["predicted_dir"]
        entry      = pos["entry_price"]
        pm_spent   = pos["amount"]
        actual     = "UP" if current_price >= entry else "DOWN"
        win        = (actual == pred)
        pnl        = pm_spent if win else -pm_spent
        tur_pnl   += pnl

        icon = "✅" if win else "❌"
        pct  = (current_price - entry) / entry * 100
        lines.append(
            f"{icon} <b>ETH</b> {pred}  {entry:.2f}→{current_price:.2f} ({pct:+.2f}%)"
            f"  {'+'if pnl>=0 else ''}{pnl:.0f}$"
        )
        history.append({
            "symbol":        SYMBOL,
            "predicted_dir": pred,
            "actual_dir":    actual,
            "win":           win,
            "entry_price":   entry,
            "exit_price":    current_price,
            "entry_time_tr": pos["entry_time_tr"],
            "entry_hour_tr": pos["entry_hour_tr"],
            "entry_dow":     pos["entry_dow"],
            "entry_is_weekend": pos["entry_is_weekend"],
            "amount":        pm_spent,
            "stoch_val":     pos.get("stoch_val"),
            "rsi_val":       pos.get("rsi_val"),
            "exit_time_tr":  now_tr.isoformat(),
            "pnl":           round(pnl, 2),
        })

    state["open_positions"] = []
    state["balance"]   += tur_pnl
    state["total_pnl"]  = state.get("total_pnl", 0.0) + tur_pnl
    save_state(state)
    save_history(history)

    gw, gt    = get_stats(history)
    total_pnl = state["total_pnl"]
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    tur_str   = f"{'+'if tur_pnl>=0 else ''}{tur_pnl:.0f}$"
    sep = "━" * 26

    tg_send(
        f"{sep}\n"
        f"🏁 <b>3. ANALİZ (Stoch RSI / ETH)</b> — {saat} Sonuçlar\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {tur_str}  |  Bakiye: ${state['balance']:.2f}\n"
        f"{pnl_icon} Toplam P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Genel: {_wr(gw, gt)}\n"
        f"{sep}"
    )
    print(f"[3. ANALİZ close] {saat} İST — {len(lines)} pozisyon kapatıldı")

# ── STATS ─────────────────────────────────────────────────────

def run_stats():
    history = load_history()
    state   = load_state()
    gw, gt  = get_stats(history)
    total_pnl = state.get("total_pnl", 0.0)

    print(f"3. ANALİZ (Stoch RSI / ETH) — İstatistik")
    print(f"  Bakiye: ${state['balance']:.2f} (başlangıç: ${INITIAL_BALANCE:.0f})")
    print(f"  Toplam P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$")
    print(f"  Genel: {_wr(gw, gt)}")

    if history:
        print(f"\n  Son 5 işlem:")
        for h in history[-5:]:
            icon = "✅" if h["win"] else "❌"
            print(f"    {icon} {h['entry_time_tr'][:16]}  "
                  f"{h['predicted_dir']}  {h['entry_price']:.2f}→{h['exit_price']:.2f}  "
                  f"pnl: {h['pnl']:+.2f}$")

# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "open":
        run_open()
    elif mode == "close":
        run_close()
    elif mode == "stats":
        run_stats()
    else:
        print(f"Bilinmeyen mod: {mode}")
