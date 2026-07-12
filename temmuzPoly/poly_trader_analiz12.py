"""
12. ANALİZ — Meta Konsensus Trader
====================================
A1, A4, A5 ve A9'un açtığı pozisyonlarda yön birliği arar.
En az 2 sistem aynı yönde seçtiğinde sanal işlem açar.

Konsensus eşiği:
  ≥2 sistem aynı yön  →  $20 sanal işlem
  <2                  →  işlem açılmaz

Mod: close / open / weekly / stats
"""
import asyncio, json, math, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import matplotlib
import matplotlib.colors as mcolors
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN       = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID         = "830754964"
_TZ_TR          = ZoneInfo("Europe/Istanbul")
_DIR            = os.path.dirname(os.path.abspath(__file__))
_DAYS_TR        = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

STATE_FILE      = os.path.join(_DIR, "poly_trader_analiz12_state.json")
HISTORY_FILE    = os.path.join(_DIR, "poly_trader_analiz12_history.json")

INITIAL_BALANCE = 400.0
TRADE_AMOUNT    = 20.0
SYMBOLS         = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT", "HYPEUSDT"]
MIN_STAT_COUNT  = 10

# Kaynak sistemlerin state dosyaları
SOURCE_STATES = {
    "A1": os.path.join(_DIR, "poly_trader_analiz1_state.json"),
    "A4": os.path.join(_DIR, "poly_trader_analiz4_state.json"),
    "A5": os.path.join(_DIR, "poly_trader_analiz5_state.json"),
    "A9": os.path.join(_DIR, "poly_trader_analiz9_state.json"),
}


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


# ── Telegram ─────────────────────────────────────────────────
def tg_send(text: str) -> None:
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception as e:
        print(f"[12. ANALİZ TG] Hata: {e}", file=sys.stderr)


def tg_send_photo(path: str, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(path, "rb") as f:
            img_data = f.read()
        boundary = "----Analiz12Boundary"
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
        print(f"[12. ANALİZ TG photo] Hata: {e}", file=sys.stderr)


# ── Binance fiyat ─────────────────────────────────────────────
def fetch_price(symbol: str) -> float:
    url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return float(json.loads(r.read())["price"])


def fetch_price_retry(symbol: str, retries: int = 3) -> float | None:
    for i in range(retries):
        try:
            return fetch_price(symbol)
        except Exception as e:
            if i < retries - 1:
                time.sleep(2)
            else:
                print(f"[12. ANALİZ] {symbol} fiyat hatası: {e}", file=sys.stderr)
    return None


# ── İstatistik ────────────────────────────────────────────────
def _wr(wins: int, total: int, warn_low: bool = False) -> str:
    if total == 0:
        return "veri yok"
    low = " ⚠️" if warn_low and total < MIN_STAT_COUNT else ""
    return f"%{wins/total*100:.0f} ({wins}/{total}){low}"


def get_stats(history: list, symbol: str, hour_tr: int) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol and t.get("entry_hour_tr") == hour_tr]
    return sum(1 for t in trades if t["win"]), len(trades)


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol]
    return sum(1 for t in trades if t["win"]), len(trades)


# ── Konsensus ─────────────────────────────────────────────────
def find_consensus(hour_tr: int) -> list[dict]:
    """A1, A4, A5, A9 state'lerini okur. Bu saatte aynı yönde ≥2 sistem varsa sinyal üretir.
    Giriş fiyatı olarak kaynak sistemlerin ortalama entry_price'ı kullanılır."""
    per_system: dict[str, dict[str, dict]] = {}  # {sistem: {symbol: {dir, price}}}

    for name, path in SOURCE_STATES.items():
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                st = json.load(f)
        except Exception:
            continue
        positions = {}
        for p in st.get("open_positions", []):
            if p.get("entry_hour_tr") == hour_tr and p.get("predicted_dir"):
                positions[p["symbol"]] = {
                    "dir":   p["predicted_dir"],
                    "price": p.get("entry_price"),
                }
        per_system[name] = positions

    if not per_system:
        return []

    consensus = []
    for symbol in SYMBOLS:
        up_data   = [(n, d) for n, pos in per_system.items()
                     if (d := pos.get(symbol)) and d["dir"] == "UP"]
        down_data = [(n, d) for n, pos in per_system.items()
                     if (d := pos.get(symbol)) and d["dir"] == "DOWN"]

        best_dir  = "UP" if len(up_data) >= len(down_data) else "DOWN"
        best_data = up_data if best_dir == "UP" else down_data
        best_count = len(best_data)

        if best_count < 2:
            continue

        # Kaynak sistemlerin ortalama giriş fiyatı
        prices = [d["price"] for _, d in best_data if d.get("price")]
        avg_price = sum(prices) / len(prices) if prices else None

        consensus.append({
            "symbol":    symbol,
            "direction": best_dir,
            "count":     best_count,
            "systems":   [n for n, _ in best_data],
            "amount":    TRADE_AMOUNT,
            "avg_price": avg_price,
        })

    return sorted(consensus, key=lambda x: x["count"], reverse=True)


# ── CLOSE ─────────────────────────────────────────────────────
async def run_close() -> None:
    now_tr     = datetime.now(timezone.utc).astimezone(_TZ_TR)
    saat       = now_tr.strftime("%H:%M")
    saat_round = f"{int(saat[:2]):02d}:00"
    state      = load_state()
    history    = load_history()
    sep        = "━" * 26

    if not state["open_positions"]:
        tg_send(f"⏸ <b>12. ANALİZ — {saat} İST</b>\nKapatılacak açık pozisyon yok.")
        print(f"[12. ANALİZ close] {saat} İST — açık pozisyon yok")
        return

    lines      = []
    toplam_pnl = 0.0
    failed_pos = []

    for pos in state["open_positions"]:
        symbol = pos["symbol"]
        entry  = pos["entry_price"]
        pred   = pos["predicted_dir"]
        amount = pos.get("amount", TRADE_AMOUNT)

        current_price = fetch_price_retry(symbol)
        if current_price is None:
            failed_pos.append(pos)
            tg_send(f"⚠️ <b>12. ANALİZ</b> — {symbol} fiyat alınamadı, pozisyon sonraki saate bırakıldı.")
            continue

        win = (current_price >= entry) if pred == "UP" else (current_price <= entry)
        pnl = amount if win else -amount

        toplam_pnl          += pnl
        state["balance"]    += pnl
        state["total_pnl"]  += pnl

        actual  = "UP" if current_price >= entry else "DOWN"
        pct     = (current_price - entry) / entry * 100
        icon    = "✅" if win else "❌"
        name    = symbol.replace("USDT", "")
        sys_str = "+".join(pos.get("systems", []))
        lines.append(
            f"{icon} {name}  {pred}  {entry:.2f}→{current_price:.2f} ({pct:+.2f}%)  "
            f"{'+'if pnl>=0 else ''}{pnl:.0f}$  [{sys_str}]"
        )

        history.append({
            "symbol":        symbol,
            "predicted_dir": pred,
            "actual_dir":    actual,
            "entry_price":   entry,
            "exit_price":    current_price,
            "entry_hour_tr": pos.get("entry_hour_tr"),
            "entry_dow":     pos.get("entry_dow"),
            "amount":        amount,
            "pnl":           pnl,
            "win":           win,
            "count":         pos.get("count", 2),
            "systems":       pos.get("systems", []),
        })

    state["open_positions"] = failed_pos
    save_state(state)
    save_history(history)

    total_pnl  = state["total_pnl"]
    closed_all = len(history)
    win_all    = sum(1 for t in history if t["win"])
    genel      = f"%{win_all/closed_all*100:.0f}" if closed_all else "—"
    pnl_icon   = "📈" if total_pnl >= 0 else "📉"

    tg_send(
        f"{sep}\n"
        f"🏁 <b>12. ANALİZ — {saat_round} Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+'if toplam_pnl>=0 else ''}{toplam_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{pnl_icon} Toplam P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all} işlem)\n"
        f"{sep}"
    )
    print(f"[12. ANALİZ close] {saat} İST — {len(lines)} pozisyon kapatıldı")


# ── OPEN ──────────────────────────────────────────────────────
async def run_open() -> None:
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)
    hour_tr = now_tr.hour
    dow     = now_tr.weekday()
    saat    = now_tr.strftime("%H:%M")
    next_h  = f"{(hour_tr+1)%24:02d}:00"
    sep     = "━" * 26
    state   = load_state()
    history = load_history()

    consensus = find_consensus(hour_tr)

    # Zaten açık olan sembolleri atla
    open_syms = {p["symbol"] for p in state["open_positions"]}
    new_pos   = [c for c in consensus if c["symbol"] not in open_syms]

    opened = []
    for c in new_pos:
        # Kaynak sistemlerin ortalama giriş fiyatını kullan, yoksa anlık fiyat çek
        price = c.get("avg_price") or fetch_price_retry(c["symbol"])
        if price is None:
            continue
        price_src = "kaynak-ort" if c.get("avg_price") else "anlık"
        pos = {
            "symbol":        c["symbol"],
            "predicted_dir": c["direction"],
            "entry_price":   round(price, 4),
            "entry_time_tr": now_tr.isoformat(),
            "entry_hour_tr": hour_tr,
            "entry_dow":     dow,
            "amount":        TRADE_AMOUNT,
            "count":         c["count"],
            "systems":       c["systems"],
            "price_src":     price_src,
        }
        state["open_positions"].append(pos)
        opened.append({**c, "price": price, "price_src": price_src})

    save_state(state)

    at_risk = sum(p.get("amount", TRADE_AMOUNT) for p in state["open_positions"])
    lines   = [sep, f"🆕 <b>12. ANALİZ ✦ Konsensus — {saat} - {next_h}</b>"]

    if opened:
        for o in opened:
            name    = o["symbol"].replace("USDT", "")
            dir_tr  = "YÜKSELİR" if o["direction"] == "UP" else "DÜŞER"
            dir_ico = "📈" if o["direction"] == "UP" else "📉"
            sys_str = "+".join(o["systems"])
            sw, st  = get_symbol_stats(history, o["symbol"])
            hw, ht  = get_stats(history, o["symbol"], hour_tr)
            low     = ht < MIN_STAT_COUNT

            konsensus_bar = "🟢🟢🟢🟢" if o["count"] == 4 else \
                            "🟢🟢🟢⚪" if o["count"] == 3 else "🟢🟢⚪⚪"

            price_note = "📌ort" if o.get("price_src") == "kaynak-ort" else "📡anlık"
            lines.append(
                f"{dir_ico} <b>{name}</b>  {dir_tr}  {TRADE_AMOUNT:.0f}$  giriş:{o['price']:.2f} {price_note}\n"
                f"   {konsensus_bar} {o['count']}/4  [{sys_str}]\n"
                f"   🕐 {hour_tr:02d}:00→{next_h} başarı: {_wr(hw,ht,warn_low=low)} | genel: {_wr(sw,st)}"
            )
    else:
        lines.append("⏸ <i>Bu saat konsensus sağlanamadı (≥2 sistem gerekli).</i>")

    lines.append(
        f"💰 Sanal: ${state['balance']-at_risk:.2f}  |  📂 Açık: {len(state['open_positions'])} poz ${at_risk:.0f}  |  Toplam: ${state['balance']:.2f}"
    )
    lines.append(f"<i>Kaynak: A1+A4+A5+A9 | Min 2/4 konsensus | Sabit {TRADE_AMOUNT:.0f}$</i>")
    lines.append(sep)

    tg_send("\n".join(lines))
    print(f"[12. ANALİZ open] {saat} İST — {len(opened)} işlem açıldı")


# ── WEEKLY ────────────────────────────────────────────────────
def run_weekly() -> None:
    history = load_history()
    state   = load_state()

    if not history:
        tg_send("📊 <b>12. ANALİZ HAFTALIK</b>\nHenüz veri yok.")
        return

    sym_names = [s.replace("USDT", "") for s in SYMBOLS]
    grid_w    = [[0]*24 for _ in range(7)]
    grid_n    = [[0]*24 for _ in range(7)]
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

    masked = np.ma.masked_invalid(rate)
    im = ax.imshow(masked, cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")

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
                    sw       = grid_sym[sn]["w"][d][h]
                    sn_total = grid_sym[sn]["n"][d][h]
                    if sn_total > 0:
                        sym_parts.append(f"{sn}:+{sw}-{sn_total-sw}")
                sym_str = "\n".join(sym_parts)
                ax.text(h, d, f"%{pct}({n})\n{sym_str}", ha="center", va="center",
                        fontsize=5, color=clr, fontweight="bold", linespacing=1.5)

    for x in range(25):
        ax.axvline(x - 0.5, color="#0a0e1a", linewidth=0.5)
    for y in range(8):
        ax.axhline(y - 0.5, color="#0a0e1a", linewidth=0.5)

    total = len(history)
    wins  = sum(1 for t in history if t["win"])
    genel = f"%{wins/total*100:.0f}" if total else "—"

    ax.set_title(
        f"12. ANALİZ (A1+A4+A5+A9 Konsensus) — {total} işlem  |  Genel: {genel}  |  Bakiye: ${state['balance']:.2f}",
        color="#eceff1", fontsize=11, fontweight="bold", pad=10
    )
    plt.colorbar(im, ax=ax).ax.yaxis.set_tick_params(color="#78909c")

    img_path = "/tmp/analiz12_weekly.png"
    plt.savefig(img_path, dpi=120, bbox_inches="tight", facecolor="#0a0e1a")
    plt.close()

    caption = (
        f"12. ANALİZ Haftalık\n"
        f"Bakiye: ${state['balance']:.2f} | P&L: {state['total_pnl']:+.2f}$\n"
        f"Toplam: {wins}/{total} ({genel})"
    )
    tg_send_photo(img_path, caption)

    # Sembol bazlı istatistik
    pnl_icon  = "🟢" if state["total_pnl"] >= 0 else "🔴"
    sym_lines = []
    for sym in SYMBOLS:
        name = sym.replace("USDT", "")
        st = [t for t in history if t["symbol"] == sym]
        sw = sum(1 for t in st if t["win"])
        if st:
            sym_lines.append(f"  {name}: {len(st)} işlem / {sw} başarılı (%{sw/len(st)*100:.0f})")

    # Konsensus seviyesine göre performans
    for cnt in [4, 3, 2]:
        ct = [t for t in history if t.get("count") == cnt]
        cw = sum(1 for t in ct if t["win"])
        if ct:
            sym_lines.append(f"  {cnt}/4 konsensus: {_wr(cw, len(ct))} ({len(ct)} işlem)")

    tg_send(
        f"📊 <b>12. ANALİZ HAFTALIK İSTATİSTİKLER</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {genel} başarı\n"
        f"{pnl_icon} P&L: {'+'if state['total_pnl']>=0 else ''}{state['total_pnl']:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"\n📈 <b>Sembol & Konsensus Dağılımı</b>\n" + "\n".join(sym_lines)
    )
    print(f"[12. ANALİZ weekly] görsel gönderildi — {total} işlem")


# ── STATS ─────────────────────────────────────────────────────
def run_stats() -> None:
    history = load_history()
    state   = load_state()
    total   = len(history)
    if total == 0:
        tg_send("📊 <b>12. ANALİZ STATS</b>\nHenüz veri yok.")
        return

    wins  = sum(1 for t in history if t["win"])
    pnl_icon = "🟢" if state["total_pnl"] >= 0 else "🔴"
    tg_send(
        f"📊 <b>12. ANALİZ İstatistikler</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {_wr(wins, total)}\n"
        f"{pnl_icon} P&L: {'+'if state['total_pnl']>=0 else ''}{state['total_pnl']:.2f}$  |  Bakiye: ${state['balance']:.2f}"
    )


# ── Entry ─────────────────────────────────────────────────────
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
