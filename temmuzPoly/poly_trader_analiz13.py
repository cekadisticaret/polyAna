"""
13. ANALİZ — Sembol Bazlı 3-Algo Konsensüs Sanal Trader

Her sembol kendi özel 3 algoritmasında oy birliğiyle karar verir:
  BTC → Stochastic RSI  + Bollinger Bands  + Mean Reversion
  ETH → OI Divergence   + Heikin Ashi      + EMA Crossover
  SOL → ADX Regime      + Stochastic RSI   + EMA Crossover

Oy sistemi (3/3 → $16 | 2/3 → $12 | 1/3 → $8 | 0 → işlem açılmaz)

Sanal bütçe: $400  |  DRY RUN
Cron: :05 open / :00 close
"""
import json
import math
import os
import sys
import urllib.request
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
BOT_TOKEN = "8630483764:AAFmAmG4nHAGb238wpavlWgMjJZDvIy4DzE"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")

_DIR         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(_DIR, "poly_trader_analiz13_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_analiz13_history.json")

INITIAL_BALANCE = 400.0
AMOUNT_HIGH     = 16.0   # 3/3 oy
AMOUNT_MID      = 12.0   # 2/3 oy
AMOUNT_LOW      =  8.0   # 1/3 oy

_BINANCE = "https://fapi.binance.com"
_PAIRS   = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT",
            "XRP": "XRPUSDT", "DOGE": "DOGEUSDT", "BNB": "BNBUSDT", "HYPE": "HYPEUSDT"}

# Her sembolün özel algoritma seti
_SYM_ALGOS = {
    "BTC":  ["stoch_rsi", "bb_squeeze",    "mean_reversion"],
    "ETH":  ["oi_div",    "heikin_ashi",   "ema_crossover"],
    "SOL":  ["adx_regime","stoch_rsi",     "ema_crossover"],
    "XRP":  ["stoch_rsi", "ema_crossover", "mean_reversion"],
    "DOGE": ["stoch_rsi", "bb_squeeze",    "ema_crossover"],
    "BNB":  ["adx_regime","ema_crossover", "mean_reversion"],
    "HYPE": ["stoch_rsi", "heikin_ashi",   "ema_crossover"],
}

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
        print(f"[13. ANALİZ] Telegram hata: {e}", file=sys.stderr)

# ── Binance Klines ────────────────────────────────────────────

def fetch_klines(pair: str, limit=200) -> list:
    url = (f"{_BINANCE}/fapi/v1/klines?symbol={pair}"
           f"&interval=1h&limit={limit}")
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.loads(r.read())
    return [{"o": float(x[1]), "h": float(x[2]), "l": float(x[3]),
             "c": float(x[4]), "v": float(x[5])} for x in data]

def fetch_oi(pair: str, limit=10) -> list:
    """Binance Futures Open Interest geçmişi"""
    url = (f"{_BINANCE}/futures/data/openInterestHist?symbol={pair}"
           f"&period=1h&limit={limit}")
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
        if isinstance(data, list):
            return [float(x["sumOpenInterestValue"]) for x in data]
    except Exception:
        pass
    return []

# ── Teknik Göstergeler ────────────────────────────────────────

def _ema(values: list, p: int) -> list:
    k, res = 2 / (p + 1), [None] * len(values)
    if len(values) < p:
        return res
    res[p - 1] = sum(values[:p]) / p
    for i in range(p, len(values)):
        res[i] = values[i] * k + res[i - 1] * (1 - k)
    return res

def _rsi(closes: list, p=14) -> list:
    res = [None] * len(closes)
    if len(closes) < p + 1:
        return res
    gains  = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
    ag = sum(gains[:p]) / p
    al = sum(losses[:p]) / p
    res[p] = 100 - 100 / (1 + ag / al) if al else 100.0
    for i in range(p + 1, len(closes)):
        ag = (ag * (p - 1) + gains[i - 1]) / p
        al = (al * (p - 1) + losses[i - 1]) / p
        res[i] = 100 - 100 / (1 + ag / al) if al else 100.0
    return res

def _atr(kl: list, p=14) -> list:
    trs = [max(kl[i]["h"] - kl[i]["l"],
               abs(kl[i]["h"] - kl[i-1]["c"]),
               abs(kl[i]["l"] - kl[i-1]["c"])) for i in range(1, len(kl))]
    res = [None] * len(kl)
    if len(trs) < p:
        return res
    res[p] = sum(trs[:p]) / p
    for i in range(p + 1, len(kl)):
        res[i] = (res[i-1] * (p-1) + trs[i-1]) / p
    return res

def _std_mean(vals: list):
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)), m

# ── Algoritma Fonksiyonları ───────────────────────────────────

def algo_stoch_rsi(kl: list) -> str:
    c  = [k["c"] for k in kl]
    rv = [x for x in _rsi(c, 14) if x is not None]
    if len(rv) < 14:
        return "NEUTRAL"
    w = rv[-14:]
    mn, mx = min(w), max(w)
    if mx == mn:
        return "NEUTRAL"
    st  = (rv[-1] - mn) / (mx - mn) * 100
    stp = (rv[-2] - mn) / (mx - mn) * 100 if len(rv) >= 2 else st
    if st < 20 and st > stp:  return "UP"
    if st > 80 and st < stp:  return "DOWN"
    return "UP" if st < 50 else "DOWN"

def algo_bb_squeeze(kl: list) -> str:
    c = [k["c"] for k in kl]
    if len(c) < 20:
        return "NEUTRAL"
    std20, m20 = _std_mean(c[-20:])
    upper = m20 + 2 * std20
    lower = m20 - 2 * std20
    pct   = (c[-1] - lower) / (upper - lower) if upper > lower else 0.5
    return "DOWN" if pct > 0.8 else "UP" if pct < 0.2 else \
           "UP" if pct > 0.5 else "DOWN"

def algo_mean_reversion(kl: list) -> str:
    c = [k["c"] for k in kl]
    if len(c) < 20:
        return "NEUTRAL"
    std, mean = _std_mean(c[-20:])
    if not std:
        return "NEUTRAL"
    z = (c[-1] - mean) / std
    return "UP" if z < -1.5 else "DOWN" if z > 1.5 else \
           "UP" if z < -0.5 else "DOWN" if z > 0.5 else "NEUTRAL"

def algo_oi_div(kl: list, pair: str) -> str:
    try:
        oi = fetch_oi(pair, 10)
        if len(oi) < 5:
            return "NEUTRAL"
        c  = [k["c"] for k in kl[-10:]]
        if len(c) < 5:
            return "NEUTRAL"
        pc = (c[-1] - c[-5]) / c[-5] if c[-5] else 0
        oc = (oi[-1] - oi[-5]) / oi[-5] if oi[-5] else 0
        if pc >  0.005 and oc >  0.005: return "UP"
        if pc < -0.005 and oc >  0.005: return "DOWN"
        if pc >  0.005 and oc < -0.005: return "DOWN"
        if pc < -0.005 and oc < -0.005: return "UP"
        return "NEUTRAL"
    except Exception:
        return "NEUTRAL"

def algo_heikin_ashi(kl: list) -> str:
    if len(kl) < 5:
        return "NEUTRAL"
    ha = []
    for k in kl:
        ha_c = (k["o"] + k["h"] + k["l"] + k["c"]) / 4
        ha_o = (ha[-1]["o"] + ha[-1]["c"]) / 2 if ha else (k["o"] + k["c"]) / 2
        ha_h = max(k["h"], ha_o, ha_c)
        ha_l = min(k["l"], ha_o, ha_c)
        ha.append({"o": ha_o, "h": ha_h, "l": ha_l, "c": ha_c})
    last3 = ha[-3:]
    bull  = sum(1 for x in last3 if x["c"] > x["o"] and x["l"] >= min(x["o"], x["c"]) * 0.9999)
    bear  = sum(1 for x in last3 if x["c"] < x["o"] and x["h"] <= max(x["o"], x["c"]) * 1.0001)
    if bull >= 2: return "UP"
    if bear >= 2: return "DOWN"
    return "UP" if ha[-1]["c"] > ha[-1]["o"] else "DOWN"

def algo_ema_crossover(kl: list) -> str:
    c = [k["c"] for k in kl]
    e9, e21, e50, e200 = _ema(c, 9), _ema(c, 21), _ema(c, 50), _ema(c, 200)
    if None in (e9[-1], e21[-1], e50[-1], e200[-1]):
        return "NEUTRAL"
    fb = e9[-1] > e21[-1]
    sb = e50[-1] > e200[-1]
    return "UP" if fb and sb else "DOWN" if not fb and not sb else "NEUTRAL"

def algo_adx_regime(kl: list, p=14) -> str:
    if len(kl) < p * 2 + 5:
        return "NEUTRAL"
    pdm, mdm, trs = [], [], []
    for i in range(1, len(kl)):
        up = kl[i]["h"] - kl[i-1]["h"]
        dn = kl[i-1]["l"] - kl[i]["l"]
        pdm.append(up if up > dn and up > 0 else 0)
        mdm.append(dn if dn > up and dn > 0 else 0)
        trs.append(max(kl[i]["h"] - kl[i]["l"],
                       abs(kl[i]["h"] - kl[i-1]["c"]),
                       abs(kl[i]["l"] - kl[i-1]["c"])))
    if len(trs) < p:
        return "NEUTRAL"
    atr_s = sum(trs[:p]); ps = sum(pdm[:p]); ms = sum(mdm[:p])
    dx_list = []
    for i in range(p, len(trs)):
        atr_s = atr_s - atr_s/p + trs[i]
        ps    = ps    - ps/p    + pdm[i]
        ms    = ms    - ms/p    + mdm[i]
        pdi   = 100 * ps / atr_s if atr_s else 0
        mdi   = 100 * ms / atr_s if atr_s else 0
        sm    = pdi + mdi
        dx_list.append(100 * abs(pdi - mdi) / sm if sm else 0)
    if len(dx_list) < p:
        return "NEUTRAL"
    adx = sum(dx_list[:p]) / p
    for v in dx_list[p:]:
        adx = (adx * (p-1) + v) / p
    atr_s = sum(trs[:p]); ps = sum(pdm[:p]); ms = sum(mdm[:p])
    for i in range(p, len(trs)):
        atr_s = atr_s - atr_s/p + trs[i]
        ps    = ps    - ps/p    + pdm[i]
        ms    = ms    - ms/p    + mdm[i]
    pdi = 100 * ps / atr_s if atr_s else 0
    mdi = 100 * ms / atr_s if atr_s else 0
    if adx < 20:
        return "NEUTRAL"
    return "UP" if pdi > mdi else "DOWN"

# ── Sinyal Üretici ────────────────────────────────────────────

_ALGO_NAMES = {
    "stoch_rsi":     "Stoch RSI",
    "bb_squeeze":    "Bol. Bands",
    "mean_reversion":"Mean Rev.",
    "oi_div":        "OI Div.",
    "heikin_ashi":   "Heikin Ashi",
    "ema_crossover": "EMA Cross",
    "adx_regime":    "ADX Regime",
}

def run_algos(sym: str, kl: list) -> dict:
    """
    Sembolün 3 algoritmasını çalıştırır.
    Döndürür: {algo_name: signal, ..., "votes": int, "direction": str, "amount": float}
    """
    pair = _PAIRS[sym]
    results = {}
    for algo in _SYM_ALGOS[sym]:
        try:
            if algo == "stoch_rsi":       s = algo_stoch_rsi(kl)
            elif algo == "bb_squeeze":    s = algo_bb_squeeze(kl)
            elif algo == "mean_reversion":s = algo_mean_reversion(kl)
            elif algo == "oi_div":        s = algo_oi_div(kl, pair)
            elif algo == "heikin_ashi":   s = algo_heikin_ashi(kl)
            elif algo == "ema_crossover": s = algo_ema_crossover(kl)
            elif algo == "adx_regime":    s = algo_adx_regime(kl)
            else:                         s = "NEUTRAL"
        except Exception as e:
            print(f"[13. ANALİZ] {sym} {algo} hata: {e}", file=sys.stderr)
            s = "NEUTRAL"
        results[algo] = s

    up_count   = sum(1 for v in results.values() if v == "UP")
    down_count = sum(1 for v in results.values() if v == "DOWN")

    if up_count > down_count:
        direction = "UP"
        votes = up_count
    elif down_count > up_count:
        direction = "DOWN"
        votes = down_count
    else:
        direction = "NEUTRAL"
        votes = 0

    if votes == 3:    amount = AMOUNT_HIGH
    elif votes == 2:  amount = AMOUNT_MID
    else:             amount = 0.0  # 1/3 veya 0/3 → işlem yok

    results["_direction"] = direction
    results["_votes"]     = votes
    results["_amount"]    = amount
    return results

# ── Yardımcılar ───────────────────────────────────────────────

def _wr(wins: int, total: int) -> str:
    if not total:
        return "veri yok"
    warn = " ⚠️" if total < 10 else ""
    return f"%{wins/total*100:.0f} ({wins}/{total}){warn}"

def get_stats(history: list) -> tuple[int, int]:
    wins  = sum(1 for t in history if t.get("win"))
    return wins, len(history)

def get_sym_stats(history: list, sym: str) -> tuple[int, int]:
    trades = [t for t in history if t.get("symbol") == sym]
    wins   = sum(1 for t in trades if t.get("win"))
    return wins, len(trades)

def get_hour_stats(history: list, sym: str, hour: int) -> tuple[int, int]:
    trades = [t for t in history if t.get("symbol") == sym and t.get("entry_hour_tr") == hour]
    wins   = sum(1 for t in trades if t.get("win"))
    return wins, len(trades)

# ── OPEN ──────────────────────────────────────────────────────

def run_open():
    now     = datetime.now(timezone.utc)
    now_tr  = now.astimezone(_TZ_TR)
    hour_tr = now_tr.hour
    saat    = now_tr.strftime("%H:%M")
    next_h  = f"{(hour_tr + 1) % 24:02d}:00"

    state   = load_state()
    history = load_history()

    # Zaten açık pozisyonu olan sembolleri atla
    open_syms = {p["symbol"] for p in state["open_positions"]}

    sep = "━" * 26
    sym_blocks  = []   # Bildirim blokları
    opened_cnt  = 0
    tur_bal_out = 0.0

    for sym, pair in _PAIRS.items():
        if sym + "USDT" in open_syms:
            sym_blocks.append(f"  ⏭ <b>{sym}</b>  zaten açık pozisyon var")
            continue

        # Klines çek
        try:
            kl = fetch_klines(pair, 200)
        except Exception as e:
            print(f"[13. ANALİZ] {sym} klines hata: {e}", file=sys.stderr)
            sym_blocks.append(f"  ⚠️ <b>{sym}</b>  veri çekilemedi")
            continue

        # Algoritmaları çalıştır
        res = run_algos(sym, kl)
        direction = res["_direction"]
        votes     = res["_votes"]
        amount    = res["_amount"]

        # Algo detay satırı (3 algo)
        algo_details = []
        for algo in _SYM_ALGOS[sym]:
            sig = res[algo]
            icon = "▲" if sig == "UP" else "▼" if sig == "DOWN" else "="
            algo_details.append(f"{_ALGO_NAMES[algo]}:{icon}")

        algo_str = "  ".join(algo_details)

        if direction == "NEUTRAL" or votes == 0:
            sym_blocks.append(
                f"  ➖ <b>{sym}</b>  {algo_str}\n"
                f"     {votes}/3 oy → konsensüs yok, işlem açılmadı"
            )
            continue

        # Giriş fiyatı: son kapanan mum
        entry_price = kl[-2]["c"]
        full_sym = sym + "USDT"
        hw, ht  = get_hour_stats(history, full_sym, hour_tr)
        sw, st  = get_sym_stats(history, full_sym)

        d_icon = "📈" if direction == "UP" else "📉"
        d_tr   = "YÜKSELİR" if direction == "UP" else "DÜŞER"

        sym_blocks.append(
            f"  {d_icon} <b>{sym}</b> {d_tr}  giriş:{entry_price:.2f}  {votes}/3 oy → ${amount:.0f}\n"
            f"     {algo_str}\n"
            f"     {hour_tr:02d}:00 başarı: {_wr(hw, ht)}  |  genel: {_wr(sw, st)}"
        )

        pos = {
            "symbol":        full_sym,
            "predicted_dir": direction,
            "entry_price":   entry_price,
            "amount":        amount,
            "votes":         votes,
            "algo_signals":  {k: v for k, v in res.items() if not k.startswith("_")},
            "entry_time_tr": now_tr.isoformat(),
            "entry_hour_tr": hour_tr,
            "entry_dow":     now_tr.weekday(),
        }
        state["open_positions"].append(pos)
        state["balance"] = round(state["balance"] - amount, 2)
        tur_bal_out += amount
        opened_cnt  += 1

    save_state(state)

    gw, gt   = get_stats(history)
    bal_icon = "🟢" if state["balance"] > 200 else "🟡" if state["balance"] > 100 else "🔴"

    parts = [
        sep,
        f"<b>🔬 13. ANALİZ — {saat} - {next_h}</b>",
        "",
    ]
    parts.extend(sym_blocks)
    parts += [
        "",
        f"{bal_icon} Sanal Bütçe: ${state['balance']:.2f}  ⛔ Bu tur: ${tur_bal_out:.0f} risk",
        f"Genel başarı: {_wr(gw, gt)}",
        sep,
    ]

    tg_send("\n".join(parts))
    print(f"[13. ANALİZ open] {saat} İST — {opened_cnt} işlem açıldı")

# ── CLOSE ─────────────────────────────────────────────────────

def run_close():
    now     = datetime.now(timezone.utc)
    now_tr  = now.astimezone(_TZ_TR)
    hour_tr = now_tr.hour
    saat    = now_tr.strftime("%H:%M")
    open_h  = f"{(hour_tr - 1) % 24:02d}:05"

    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        print(f"[13. ANALİZ close] {saat} İST — açık pozisyon yok")
        return

    sym_blocks = []
    tur_pnl    = 0.0
    bal_back   = 0.0

    for pos in state["open_positions"]:
        sym    = pos["symbol"]
        pair   = sym  # BTCUSDT vb.
        pred   = pos["predicted_dir"]
        entry  = pos["entry_price"]
        amount = pos["amount"]
        votes  = pos["votes"]

        try:
            kl = fetch_klines(pair, 3)
            current_price = kl[-1]["c"]
        except Exception as e:
            print(f"[13. ANALİZ] {sym} fiyat hatası: {e}", file=sys.stderr)
            current_price = entry

        actual = "UP" if current_price >= entry else "DOWN"
        win    = (actual == pred)
        pnl    = amount if win else -amount

        # Balance güncelleme: open'da çıkmıştı, WIN → 2×amount geri, LOSS → 0
        bal_back += (amount * 2) if win else 0.0
        tur_pnl  += pnl

        icon = "✅" if win else "❌"
        pct  = (current_price - entry) / entry * 100
        name = sym.replace("USDT", "")
        sym_blocks.append(
            f"  {icon} <b>{name}</b> {pred}  {entry:.2f}→{current_price:.2f} ({pct:+.2f}%)"
            f"  {'+'if pnl>=0 else ''}{pnl:.0f}$  ({votes}/3 oy)"
        )

        history.append({
            "symbol":        sym,
            "predicted_dir": pred,
            "actual_dir":    actual,
            "win":           win,
            "entry_price":   entry,
            "exit_price":    current_price,
            "entry_time_tr": pos["entry_time_tr"],
            "entry_hour_tr": pos["entry_hour_tr"],
            "entry_dow":     pos["entry_dow"],
            "amount":        amount,
            "votes":         votes,
            "algo_signals":  pos.get("algo_signals", {}),
            "exit_time_tr":  now_tr.isoformat(),
            "pnl":           round(pnl, 2),
        })

    state["open_positions"] = []
    state["balance"]  = round(state["balance"] + bal_back, 2)
    state["total_pnl"] = round(state.get("total_pnl", 0.0) + tur_pnl, 2)
    save_state(state)
    save_history(history)

    gw, gt    = get_stats(history)
    total_pnl = state["total_pnl"]
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    tur_str   = f"{'+'if tur_pnl>=0 else ''}{tur_pnl:.0f}$"
    sep = "━" * 26

    parts = [
        sep,
        f"<b>🏁 13. ANALİZ — {saat} Sonuçlar</b>  <i>({open_h} - {saat})</i>",
        "",
    ]
    parts.extend(sym_blocks)
    parts += [
        "",
        f"Bu tur: {tur_str}  |  Bakiye: ${state['balance']:.2f}",
        f"{pnl_icon} Toplam P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Genel: {_wr(gw, gt)}",
        sep,
    ]

    tg_send("\n".join(parts))
    print(f"[13. ANALİZ close] {saat} İST — {len(sym_blocks)} pozisyon kapatıldı")

# ── STATS ─────────────────────────────────────────────────────

def run_stats():
    state   = load_state()
    history = load_history()
    gw, gt  = get_stats(history)
    total_pnl = state.get("total_pnl", 0.0)

    print(f"13. ANALİZ — İstatistik")
    print(f"  Bakiye:    ${state['balance']:.2f} / ${INITIAL_BALANCE:.0f}")
    print(f"  Toplam P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$")
    print(f"  Genel:     {_wr(gw, gt)}")

    for sym in _PAIRS:
        sw, st = get_sym_stats(history, sym + "USDT")
        print(f"  {sym}: {_wr(sw, st)}")

    if history:
        print(f"\n  Son 5 işlem:")
        for h in history[-5:]:
            icon = "✅" if h["win"] else "❌"
            name = h["symbol"].replace("USDT", "")
            print(f"    {icon} {h['entry_time_tr'][:16]}  {name} {h['predicted_dir']}"
                  f"  {h['votes']}/3  pnl:{h['pnl']:+.2f}$")

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
