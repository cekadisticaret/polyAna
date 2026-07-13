"""
301. ANALİZ — MACD Histogram Diverjansı Sanal Trader

Algo #26 (MACD Histogram Diverjansı) ile BTC / ETH / SOL için saatlik sinyal:
  - Yükselen fiyat + düşen histogram → DOWN
  - Düşen fiyat + yükselen histogram → UP
  - Histogram trendi → UP / DOWN / NEUTRAL

Sanal bütçe: $300  |  İşlem: $10 / $15 / $20 (sembol başarısına göre)
Telegram: 3. ANALİZ (Stoch RSI / ETH) ile aynı kanal

Modlar: open / close / stats
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
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
STATE_FILE   = os.path.join(_DIR, "poly_trader_301_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_301_history.json")

INITIAL_BALANCE = 300.0
SYMBOLS         = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TRADE_AMOUNT    = 15.0
TRADE_AMOUNT_HIGH = 20.0
TRADE_AMOUNT_LOW  = 10.0
_BINANCE        = "https://fapi.binance.com"
_LABEL          = "301. ANALİZ (MACD Hist Div)"


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
        print(f"[301] Telegram hata: {e}", file=sys.stderr)


# ── Binance ───────────────────────────────────────────────────

def fetch_klines(symbol: str, limit=100) -> list[dict]:
    url = (f"{_BINANCE}/fapi/v1/klines?symbol={symbol}"
           f"&interval=1h&limit={limit}")
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.loads(r.read())
    return [{"o": float(x[1]), "h": float(x[2]), "l": float(x[3]),
             "c": float(x[4]), "v": float(x[5])} for x in data]


def fetch_price(symbol: str) -> float:
    url = f"{_BINANCE}/fapi/v1/ticker/price?symbol={symbol}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return float(json.loads(r.read())["price"])


# ── Algo #26: MACD Histogram Diverjansı ───────────────────────

def _ema(values: list[float], p: int) -> list:
    k, res = 2 / (p + 1), [None] * len(values)
    if len(values) < p:
        return res
    res[p - 1] = sum(values[:p]) / p
    for i in range(p, len(values)):
        res[i] = values[i] * k + res[i - 1] * (1 - k)
    return res


def macd_histogram_div(kl: list[dict]) -> str:
    c = [k["c"] for k in kl]
    e12, e26 = _ema(c, 12), _ema(c, 26)
    ml = [e12[i] - e26[i] if e12[i] and e26[i] else None for i in range(len(c))]
    valid = [x for x in ml if x is not None]
    if len(valid) < 12:
        return "NEUTRAL"
    sl = _ema(valid, 9)
    hist = [valid[i] - sl[i] for i in range(len(sl)) if sl[i] is not None]
    if len(hist) < 5:
        return "NEUTRAL"
    if c[-1] > c[-5] and hist[-1] < hist[-5] and hist[-1] > 0:
        return "DOWN"
    if c[-1] < c[-5] and hist[-1] > hist[-5] and hist[-1] < 0:
        return "UP"
    if hist[-1] > 0 and hist[-1] > hist[-2]:
        return "UP"
    if hist[-1] < 0 and hist[-1] < hist[-2]:
        return "DOWN"
    return "NEUTRAL"


# ── Yardımcılar ───────────────────────────────────────────────

def _wr(wins: int, total: int) -> str:
    if not total:
        return "veri yok"
    warn = " ⚠️" if total < 10 else ""
    return f"%{wins/total*100:.0f} ({wins}/{total}){warn}"


def get_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t.get("symbol") == symbol]
    wins   = sum(1 for t in trades if t.get("win"))
    return wins, len(trades)


def get_hour_stats(history: list, symbol: str, hour: int) -> tuple[int, int]:
    trades = [t for t in history if t.get("symbol") == symbol
              and t.get("entry_hour_tr") == hour]
    wins   = sum(1 for t in trades if t.get("win"))
    return wins, len(trades)


def pick_amount(history: list, symbol: str) -> float:
    wins, total = get_stats(history, symbol)
    if not total:
        return TRADE_AMOUNT
    rate = wins / total
    if rate > 0.5:
        return TRADE_AMOUNT_HIGH
    if rate < 0.5:
        return TRADE_AMOUNT_LOW
    return TRADE_AMOUNT


def _open_symbols(state: dict) -> set[str]:
    return {p["symbol"] for p in state.get("open_positions", [])}


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
    opened  = _open_symbols(state)

    lines       = []
    skip_lines  = []
    total_stake = 0.0

    for symbol in SYMBOLS:
        if symbol in opened:
            skip_lines.append(f"⏭ <b>{symbol.replace('USDT', '')}</b> zaten açık")
            continue

        try:
            klines = fetch_klines(symbol, 100)
        except Exception as e:
            print(f"[301] {symbol} klines hatası: {e}", file=sys.stderr)
            continue

        signal = macd_histogram_div(klines)
        name   = symbol.replace("USDT", "")

        if signal == "NEUTRAL":
            skip_lines.append(f"⏸ <b>{name}</b> nötr")
            continue

        amount = pick_amount(history, symbol)
        if state["balance"] - total_stake < amount:
            skip_lines.append(f"💸 <b>{name}</b> bakiye yetersiz (${amount:.0f})")
            continue

        entry_price = klines[-2]["c"]
        pos = {
            "symbol":           symbol,
            "predicted_dir":    signal,
            "entry_price":      entry_price,
            "amount":           amount,
            "entry_time_tr":    now_tr.isoformat(),
            "entry_hour_tr":    hour_tr,
            "entry_dow":        dow,
            "entry_is_weekend": is_weekend,
        }
        state["open_positions"].append(pos)
        total_stake += amount

        hw, ht = get_hour_stats(history, symbol, hour_tr)
        gw, gt = get_stats(history, symbol)
        dir_icon = "📈" if signal == "UP" else "📉"
        dir_tr   = "YÜKSELİR" if signal == "UP" else "DÜŞER"
        lines.append(
            f"{dir_icon} <b>{name}</b> {dir_tr}  giriş:{entry_price:.2f}\n"
            f"   🕐 {hour_tr:02d}:00→{next_h} başarı: {_wr(hw, ht)}"
            f"  |  genel: {_wr(gw, gt)}\n"
            f"   🔶 DRY RUN: ${amount:.0f}"
        )
        print(f"[301 open] {saat} İST — {name} {signal} @{entry_price:.2f} ${amount:.0f}")

    if total_stake:
        state["balance"] = round(state["balance"] - total_stake, 2)
        save_state(state)

    sep = "━" * 26
    open_cnt = len(state["open_positions"])

    if lines:
        tg_send(
            f"{sep}\n"
            f"🆕 <b>{_LABEL}</b> — {saat} - {next_h}\n"
            + "\n".join(lines) + "\n"
            f"💰 Sanal Bütçe: ${state['balance']:.2f}  |  📂 Açık: {open_cnt} poz\n"
            f"{sep}"
        )
    elif skip_lines:
        tg_send(
            f"⏸ <b>{_LABEL}</b> — {saat} İST\n"
            + "\n".join(skip_lines) + "\n"
            f"💰 Sanal Bütçe: ${state['balance']:.2f}"
        )
    else:
        print(f"[301 open] {saat} İST — sinyal yok")


# ── CLOSE ─────────────────────────────────────────────────────

def run_close():
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")

    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        print(f"[301 close] {saat} İST — açık pozisyon yok")
        return

    lines        = []
    tur_pnl      = 0.0
    tur_bal_back = 0.0
    failed       = []

    for pos in list(state["open_positions"]):
        symbol = pos["symbol"]
        try:
            klines = fetch_klines(symbol, 3)
            current_price = klines[-1]["c"]
        except Exception as e:
            print(f"[301] {symbol} fiyat hatası: {e}", file=sys.stderr)
            failed.append(pos)
            continue

        pred     = pos["predicted_dir"]
        entry    = pos["entry_price"]
        pm_spent = pos["amount"]
        actual   = "UP" if current_price >= entry else "DOWN"
        win      = (actual == pred)
        pnl      = pm_spent if win else -pm_spent
        bal_back = (pm_spent * 2) if win else 0.0
        tur_pnl      += pnl
        tur_bal_back += bal_back

        name = symbol.replace("USDT", "")
        icon = "✅" if win else "❌"
        pct  = (current_price - entry) / entry * 100
        lines.append(
            f"{icon} <b>{name}</b> {pred}  {entry:.2f}→{current_price:.2f} ({pct:+.2f}%)"
            f"  {'+'if pnl>=0 else ''}{pnl:.0f}$"
        )
        history.append({
            "symbol":           symbol,
            "predicted_dir":    pred,
            "actual_dir":       actual,
            "win":              win,
            "entry_price":      entry,
            "exit_price":       current_price,
            "entry_time_tr":    pos["entry_time_tr"],
            "entry_hour_tr":    pos["entry_hour_tr"],
            "entry_dow":        pos["entry_dow"],
            "entry_is_weekend": pos["entry_is_weekend"],
            "amount":           pm_spent,
            "exit_time_tr":     now_tr.isoformat(),
            "pnl":              round(pnl, 2),
        })

    state["open_positions"] = failed
    state["balance"]   = round(state["balance"] + tur_bal_back, 2)
    state["total_pnl"] = round(state.get("total_pnl", 0.0) + tur_pnl, 2)
    save_state(state)
    save_history(history)

    wins_all  = sum(1 for t in history if t.get("win"))
    total_all = len(history)
    genel_wr  = _wr(wins_all, total_all) if total_all else "veri yok"

    total_pnl = state["total_pnl"]
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    tur_str   = f"{'+'if tur_pnl>=0 else ''}{tur_pnl:.0f}$"
    sep       = "━" * 26

    tg_send(
        f"{sep}\n"
        f"🏁 <b>{_LABEL}</b> — {saat} Sonuçlar\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {tur_str}  |  Bakiye: ${state['balance']:.2f}\n"
        f"{pnl_icon} Toplam P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Genel: {genel_wr}\n"
        f"{sep}"
    )
    print(f"[301 close] {saat} İST — {len(lines)} pozisyon kapatıldı")


# ── STATS ─────────────────────────────────────────────────────

def run_stats():
    history = load_history()
    state   = load_state()
    total_pnl = state.get("total_pnl", 0.0)

    print(f"{_LABEL} — İstatistik")
    print(f"  Bakiye: ${state['balance']:.2f} (başlangıç: ${INITIAL_BALANCE:.0f})")
    print(f"  Toplam P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$")
    print(f"  Açık pozisyon: {len(state.get('open_positions', []))}")

    for symbol in SYMBOLS:
        gw, gt = get_stats(history, symbol)
        print(f"  {symbol.replace('USDT', '')}: {_wr(gw, gt)}")

    if history:
        print("\n  Son 5 işlem:")
        for h in history[-5:]:
            icon = "✅" if h["win"] else "❌"
            sym  = h["symbol"].replace("USDT", "")
            print(f"    {icon} {h['entry_time_tr'][:16]}  {sym} {h['predicted_dir']}  "
                  f"{h['entry_price']:.2f}→{h['exit_price']:.2f}  pnl: {h['pnl']:+.2f}$")


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
