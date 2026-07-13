"""
5M 105 BTC — Volume Profile (POC) Sanal Trader
================================================
Algo #10: Son 50 mum hacim profili → POC vs fiyat sinyali.
Sadece BTCUSDT, 5 dakikalık periyot, $500 sanal bütçe.
Telegram: 5M 101 ile aynı kanal.

Modlar: open / weekly / stats
Cron:   */5 * * * *
"""

import json
import os
import sys
import time
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
BOT_TOKEN = "8256912678:AAFWEoRWO7Z0siK_c4Dm5XjgtBKmh-wmF8E"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")

_DIR         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(_DIR, "poly_trader_5m_btc_105_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_5m_btc_105_history.json")
WEEKLY_IMG   = "/tmp/poly_5m_btc_105_weekly.png"

SYMBOL          = "BTCUSDT"
INITIAL_BALANCE = 500.0
TRADE_AMOUNT    = 10.0
_PERIOD_SECS    = 300
_DAYS_TR        = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

_PM_GAMMA_URL = "https://gamma-api.polymarket.com/events"
_PM_HEADERS   = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
_PM_DRY_RUN   = True

LABEL = "5M 105 BTC"


# ── State / History ───────────────────────────────────────────

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


def _wr(wins: int, total: int) -> str:
    if total == 0:
        return "veri yok"
    return f"%{wins/total*100:.0f} ({wins}/{total})"


def get_stats(history: list, period_min: int, dow: int | None = None) -> tuple[int, int]:
    trades = [
        t for t in history
        if t.get("entry_period_min") == period_min
        and (dow is None or t.get("entry_dow") == dow)
    ]
    return sum(1 for t in trades if t["win"]), len(trades)


def get_all_stats(history: list) -> tuple[int, int]:
    return sum(1 for t in history if t["win"]), len(history)


# ── Telegram ──────────────────────────────────────────────────

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
        boundary = "----105Boundary"
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


# ── Binance ───────────────────────────────────────────────────

def _binance_get(path: str, params: dict | None = None) -> dict | list:
    base = "https://fapi.binance.com"
    qs   = urllib.parse.urlencode(params or {})
    url  = f"{base}{path}?{qs}" if qs else f"{base}{path}"
    req  = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def fetch_klines_5m(symbol: str, limit: int = 150) -> list[dict]:
    raw = _binance_get("/fapi/v1/klines", {"symbol": symbol, "interval": "5m", "limit": limit})
    return [{"open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
             "close": float(k[4]), "volume": float(k[5])} for k in raw]


# ── Algo #10: Volume Profile (POC) ────────────────────────────

def volume_profile_signal(klines: list[dict]) -> tuple[str, float | None, str]:
    """Returns: (UP/DOWN/NEUTRAL, poc_price, detail_label)"""
    if len(klines) < 50:
        return "NEUTRAL", None, "veri yetersiz"

    w = klines[-50:]
    pmin = min(k["low"] for k in w)
    pmax = max(k["high"] for k in w)
    if pmax == pmin:
        return "NEUTRAL", None, "fiyat aralığı yok"

    bins = [0.0] * 20
    bs   = (pmax - pmin) / 20
    for k in w:
        mid = (k["high"] + k["low"] + k["close"]) / 3
        bins[min(int((mid - pmin) / bs), 19)] += k["volume"]

    poc_idx = bins.index(max(bins))
    poc     = pmin + (poc_idx + 0.5) * bs
    price   = klines[-1]["close"]
    poc_pct = (poc - price) / price * 100

    if poc > price * 1.01:
        signal = "DOWN"
        detail = f"POC {poc:,.0f} fiyatın üstünde ({poc_pct:+.1f}%) → düşüş baskısı"
    elif poc < price * 0.99:
        signal = "UP"
        detail = f"POC {poc:,.0f} fiyatın altında ({poc_pct:+.1f}%) → yükseliş baskısı"
    else:
        signal = "NEUTRAL"
        detail = f"POC {poc:,.0f} ≈ fiyat ({poc_pct:+.1f}%) → nötr"

    return signal, round(poc, 2), detail


def analyze() -> dict | None:
    try:
        klines = fetch_klines_5m(SYMBOL, 150)
    except Exception as e:
        print(f"[{LABEL}] Veri hatası: {e}", file=sys.stderr)
        return None

    signal, poc, detail = volume_profile_signal(klines)
    entry_price = klines[-1]["open"]

    if signal == "NEUTRAL":
        return {
            "direction": None,
            "consensus": 0,
            "signal": signal,
            "poc": poc,
            "detail": detail,
            "entry_price": entry_price,
            "amount": 0.0,
        }

    vote = +1 if signal == "UP" else -1
    return {
        "direction": signal,
        "consensus": 1,
        "signal": signal,
        "poc": poc,
        "detail": detail,
        "entry_price": entry_price,
        "amount": TRADE_AMOUNT,
        "vote": vote,
    }


# ── Polymarket 5m Market ──────────────────────────────────────

def _current_5m_ts() -> int:
    now = int(time.time())
    return now - (now % _PERIOD_SECS)


def _pm_find_5m_market(ts_5m: int) -> dict | None:
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
            "slug":       slug,
            "up_price":   float(op[0]) if len(op) >= 2 else 0.5,
            "down_price": float(op[1]) if len(op) >= 2 else 0.5,
        }
    except Exception as e:
        print(f"[{LABEL}] Gamma hatası ({slug}): {e}", file=sys.stderr)
    return None


# ── Ana Çalışma ───────────────────────────────────────────────

def run() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    dow    = now_tr.weekday()
    saat   = now_tr.strftime("%H:%M")

    cur_min    = now_tr.hour * 60 + now_tr.minute
    period_min = (cur_min // 5) * 5
    ts_5m      = _current_5m_ts()

    state   = load_state()
    history = load_history()

    # ── 1. KAPAT ──
    closed_lines = []
    tur_pnl = 0.0

    if state["open_positions"]:
        time.sleep(3)
        try:
            klines     = fetch_klines_5m(SYMBOL, 10)
            prev_close = klines[-2]["close"]
            ref_open   = klines[-2]["open"]
        except Exception as e:
            print(f"[{LABEL}] Kapanış fiyatı alınamadı: {e}")
            prev_close = None
            ref_open   = None

        for pos in list(state["open_positions"]):
            if prev_close is None:
                continue
            pred   = pos["predicted_dir"]
            amount = pos.get("amount", TRADE_AMOUNT)
            to_win = pos.get("to_win", amount * 2)
            actual = "UP" if prev_close >= ref_open else "DOWN"
            win    = (pred == actual)

            if win:
                state["balance"] = round(state["balance"] + to_win, 2)
                pnl = round(to_win - amount, 2)
            else:
                pnl = -amount

            tur_pnl += pnl
            state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

            history.append({
                "symbol":           SYMBOL,
                "predicted_dir":    pred,
                "actual_dir":       actual,
                "win":              win,
                "entry_price":      pos["entry_price"],
                "exit_price":       prev_close,
                "amount":           amount,
                "to_win":           to_win,
                "pnl":              pnl,
                "entry_time_tr":    pos["entry_time_tr"],
                "entry_period_min": pos.get("entry_period_min"),
                "entry_dow":        pos.get("entry_dow"),
                "exit_time_tr":     now_tr.isoformat(),
                "signal":           pos.get("signal"),
                "poc":              pos.get("poc"),
                "pm_slug":          pos.get("pm_slug"),
                "pm_dry_run":       _PM_DRY_RUN,
            })

            icon = "✅" if win else "❌"
            pct  = (prev_close - ref_open) / ref_open * 100
            dir_tr = "YÜKSELİR" if pred == "UP" else "DÜŞER"
            closed_lines.append(
                f"{icon} BTC {dir_tr}  {ref_open:,.0f}→{prev_close:,.0f} ({pct:+.1f}%)"
                f"  {'kazandı +$'+f'{to_win:.2f}' if win else 'kaybetti -$'+f'{amount:.0f}'}"
            )

        state["open_positions"] = []
        save_state(state)
        save_history(history)

    if closed_lines:
        win_all, tot_all = get_all_stats(history)
        pnl_icon = "🟢" if state["total_pnl"] >= 0 else "🔴"
        tur_icon = "🟢" if tur_pnl >= 0 else "🔴"
        sep = "━" * 26
        tg_send(
            f"{sep}\n"
            f"🏁 <b>{LABEL} — {saat} Sonuçlar</b>\n"
            + "\n".join(closed_lines) + "\n"
            f"{tur_icon} Bu tur: {'+'if tur_pnl>=0 else ''}{tur_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
            f"{pnl_icon} Toplam P&amp;L: {'+'if state['total_pnl']>=0 else ''}{state['total_pnl']:.2f}$  |  Genel: {_wr(win_all, tot_all)}\n"
            f"{sep}"
        )
        print(f"[{LABEL}] {saat} — {len(closed_lines)} pozisyon kapatıldı")

    # ── 2. AÇ ──
    result = analyze()
    from pm_signal_sync import save_signal
    save_signal("105", ts_5m, result)

    if result is None:
        tg_send(f"⚠️ <b>{LABEL}</b> — {saat} veri alınamadı")
        return

    direction = result["direction"]
    amount    = result["amount"]
    entry_p   = result["entry_price"]
    poc       = result.get("poc")
    detail    = result.get("detail", "")
    next_saat = (now_tr + timedelta(minutes=5)).strftime("%H:%M")

    prev_wins, prev_total = get_stats(history, period_min)
    all_wins, all_total   = get_all_stats(history)
    sep = "━" * 26

    if direction is None:
        tg_send(
            f"{sep}\n"
            f"⏸ <b>{LABEL} — {saat} İST</b>\n"
            f"Volume Profile nötr → işlem açılmadı\n"
            f"{detail}\n"
            f"💰 Bakiye: ${state['balance']:.2f}\n"
            f"{sep}"
        )
        print(f"[{LABEL}] {saat} — nötr")
        return

    pm_info     = _pm_find_5m_market(ts_5m)
    pm_slug     = pm_info["slug"] if pm_info else None
    token_price = None
    if pm_info and not pm_info.get("closed"):
        token_price = pm_info["up_price"] if direction == "UP" else pm_info["down_price"]

    to_win = round(amount / token_price, 2) if token_price and token_price > 0 else round(amount * 2, 2)

    state["balance"] = round(state["balance"] - amount, 2)
    state["open_positions"].append({
        "symbol":           SYMBOL,
        "predicted_dir":    direction,
        "entry_price":      entry_p,
        "amount":           amount,
        "to_win":           to_win,
        "token_price":      token_price,
        "signal":           result.get("signal"),
        "poc":              poc,
        "entry_time_tr":    now_tr.isoformat(),
        "entry_period_min": period_min,
        "entry_dow":        dow,
        "pm_slug":          pm_slug,
        "ts_5m":            ts_5m,
    })
    save_state(state)

    dir_tr   = "YÜKSELİR" if direction == "UP" else "DÜŞER"
    dir_icon = "📈" if direction == "UP" else "📉"
    price_str = f"@{token_price:.2f}" if token_price else ""

    tg_send(
        f"{sep}\n"
        f"🆕 <b>{LABEL} — {saat} → {next_saat}</b>  🔶 SANAL\n"
        f"{dir_icon} <b>BTC {dir_tr}</b>  (Vol Profile)  💵 ${amount:.0f} {price_str} → 🏆 ${to_win:.2f}\n"
        f"Giriş: {entry_p:,.2f} USDT\n"
        f"📊 {detail}\n"
        f"🕐 Bu periyot: {_wr(prev_wins, prev_total)}  |  Genel: {_wr(all_wins, all_total)}\n"
        f"💰 Bakiye: ${state['balance']:.2f}  |  🔴 ${amount:.0f} riskte\n"
        f"{sep}"
    )
    print(f"[{LABEL}] {saat} — {dir_tr}  ${amount:.0f}→${to_win:.2f}  entry:{entry_p:,.2f}  POC:{poc}")


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

    grid_w_h = [[0] * 24 for _ in range(7)]
    grid_n_h = [[0] * 24 for _ in range(7)]
    for t in history:
        d = t.get("entry_dow")
        p = t.get("entry_period_min")
        if d is None or p is None:
            continue
        h = (p // 5) // 12
        if 0 <= h < 24:
            grid_n_h[d][h] += 1
            if t["win"]:
                grid_w_h[d][h] += 1

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
    im = ax.imshow(np.ma.masked_invalid(rate), cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")
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
        f"{LABEL} — Haftalık Isı Haritası  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
        f"Toplam: {total} işlem  |  {genel}  |  Bakiye: ${balance:.2f}  |  P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$",
        color="#4fc3f7", fontsize=9, fontweight="bold", pad=8
    )
    fig.colorbar(im, ax=ax, fraction=0.01, pad=0.01)
    plt.tight_layout(pad=1.0)
    plt.savefig(WEEKLY_IMG, dpi=130, bbox_inches="tight", facecolor="#0a0e1a", pad_inches=0.1)
    plt.close()
    tg_send_photo(WEEKLY_IMG, f"📊 {LABEL} Haftalık  {now_tr.strftime('%d.%m.%Y')}  {total} işlem | {genel}")


def run_stats() -> None:
    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)
    total   = len(history)
    wins    = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    tg_send(
        f"📊 <b>{LABEL} İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {_wr(wins, total)}\n"
        f"{pnl_icon} P&amp;L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"Başlangıç: ${INITIAL_BALANCE:.2f}"
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        run()
