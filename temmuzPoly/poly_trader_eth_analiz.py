"""
ETH ANALİZ — A1+A2+A4 Konsensus (Sadece ETH)

Analiz 1, 2 ve 4'ün bu saat açtığı ETH pozisyonlarını okur.
En az 2 sistem aynı yönde ise ETH'e girer.

Konsensus → İşlem tutarı:
  3/3 sistem aynı yön  →  $25
  2/3 sistem aynı yön  →  $15

Mod: close / open / weekly
"""
import asyncio, json, os, sys, time, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")
_DIR      = os.path.dirname(os.path.abspath(__file__))

STATE_FILE      = os.path.join(_DIR, "poly_trader_eth_analiz_state.json")
HISTORY_FILE    = os.path.join(_DIR, "poly_trader_eth_analiz_history.json")

INITIAL_BALANCE = 300.0
SYMBOL          = "ETHUSDT"

AMOUNT_STRONG   = 25.0   # 3/3 konsensus
AMOUNT_WEAK     = 15.0   # 2/3 konsensus
MIN_STAT_COUNT  = 10

SOURCE_STATES = {
    "A1": os.path.join(_DIR, "poly_trader_analiz1_state.json"),
    "A2": os.path.join(_DIR, "poly_trader_analiz2_state.json"),
    "A4": os.path.join(_DIR, "poly_trader_analiz4_state.json"),
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
        print(f"[TG] Hata: {e}")

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
                print(f"[ETH ANALİZ] {symbol} fiyat hatası: {e}", file=sys.stderr)
    return None

# ── Konsensus ─────────────────────────────────────────────────
def find_eth_consensus(hour_tr: int) -> dict | None:
    """
    Kaynak sistemlerin bu saat açtığı ETH pozisyonuna bakar.
    En az 2 sistem hemfikirse konsensus döner.
    """
    up_data   = []
    down_data = []

    for name, path in SOURCE_STATES.items():
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                st = json.load(f)
        except Exception:
            continue
        for p in st.get("open_positions", []):
            if p.get("symbol") == SYMBOL and p.get("entry_hour_tr") == hour_tr:
                entry = {"system": name, "price": p.get("entry_price"), "dir": p["predicted_dir"]}
                if p["predicted_dir"] == "UP":
                    up_data.append(entry)
                else:
                    down_data.append(entry)
                break  # her sistemden 1 ETH pozisyonu yeter

    best   = up_data if len(up_data) >= len(down_data) else down_data
    best_d = "UP"    if len(up_data) >= len(down_data) else "DOWN"

    if len(best) < 2:
        return None

    prices    = [e["price"] for e in best if e.get("price")]
    avg_price = sum(prices) / len(prices) if prices else None
    amount    = AMOUNT_STRONG if len(best) == 3 else AMOUNT_WEAK

    return {
        "direction": best_d,
        "count":     len(best),
        "systems":   [e["system"] for e in best],
        "avg_price": avg_price,
        "amount":    amount,
    }

# ── İstatistik ────────────────────────────────────────────────
def _wr(wins: int, total: int, warn_low: bool = False) -> str:
    if total == 0: return "veri yok"
    low = " ⚠️" if warn_low and total < MIN_STAT_COUNT else ""
    return f"%{wins/total*100:.0f} ({wins}/{total}){low}"

def get_stats(history: list, hour_tr: int) -> tuple[int, int]:
    trades = [t for t in history if t.get("entry_hour_tr") == hour_tr]
    return sum(1 for t in trades if t["win"]), len(trades)

# ── CLOSE ─────────────────────────────────────────────────────
async def run_close() -> None:
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)
    saat    = now_tr.strftime("%H:%M")
    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        tg_send(f"⏸ <b>ETH ANALİZ — {saat} İST</b>\nKapatılacak açık pozisyon yok.")
        return

    lines      = []
    toplam_pnl = 0.0
    failed_pos = []

    for pos in state["open_positions"]:
        current_price = fetch_price_retry(SYMBOL)
        if current_price is None:
            failed_pos.append(pos)
            tg_send(f"⚠️ <b>ETH ANALİZ</b> — ETH fiyat alınamadı, pozisyon sonraki saate bırakıldı.")
            continue

        entry  = pos["entry_price"]
        pred   = pos["predicted_dir"]
        amount = pos["amount"]
        win    = (pred == "UP" and current_price >= entry) or \
                 (pred == "DOWN" and current_price <= entry)
        pnl    = amount if win else -amount

        toplam_pnl        += pnl
        state["balance"]  += pnl
        state["total_pnl"] += pnl
        actual = "UP" if current_price >= entry else "DOWN"
        pct    = (current_price - entry) / entry * 100

        icon    = "✅" if win else "❌"
        pnl_str = f"+{pnl:.0f}$" if win else f"{pnl:.0f}$"
        lines.append(
            f"{icon} ETH  {pred}  {entry:.2f}→{current_price:.2f} ({pct:+.2f}%)  "
            f"{pnl_str}  konsensus:{pos.get('count',2)}/3"
        )

        history.append({
            "symbol":        SYMBOL,
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
        })

    state["open_positions"] = failed_pos
    save_state(state)
    save_history(history)

    total_pnl  = state["total_pnl"]
    closed_all = len(history)
    win_all    = sum(1 for t in history if t["win"])
    genel      = f"%{win_all/closed_all*100:.0f}" if closed_all else "—"
    pnl_icon   = "📈" if total_pnl >= 0 else "📉"
    sep        = "━" * 26

    tg_send(
        f"{sep}\n"
        f"🏁 <b>ETH ANALİZ — {int(saat[:2]):02d}:00 Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+'if toplam_pnl>=0 else ''}{toplam_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{pnl_icon} Toplam P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all} işlem)\n"
        f"{sep}"
    )
    print(f"[ETH ANALİZ close] {saat} İST — {len(lines)} pozisyon kapatıldı")

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

    # Zaten ETH pozisyonu açıksa atla
    if any(p["symbol"] == SYMBOL for p in state["open_positions"]):
        print(f"[ETH ANALİZ open] {saat} — ETH zaten açık, atlandı")
        return

    consensus = find_eth_consensus(hour_tr)

    if consensus:
        price = consensus.get("avg_price") or fetch_price_retry(SYMBOL)
        if price is None:
            tg_send(f"⚠️ <b>ETH ANALİZ</b> — ETH fiyat alınamadı, işlem açılmadı.")
            return

        price_src = "📌ort" if consensus.get("avg_price") else "📡anlık"
        pos = {
            "symbol":        SYMBOL,
            "predicted_dir": consensus["direction"],
            "entry_price":   round(price, 4),
            "entry_time_tr": now_tr.isoformat(),
            "entry_hour_tr": hour_tr,
            "entry_dow":     dow,
            "amount":        consensus["amount"],
            "count":         consensus["count"],
            "systems":       consensus["systems"],
            "price_src":     price_src,
        }
        state["open_positions"].append(pos)
        save_state(state)

        dir_tr   = "YÜKSELİR" if consensus["direction"] == "UP" else "DÜŞER"
        dir_ico  = "📈" if consensus["direction"] == "UP" else "📉"
        sys_str  = "+".join(consensus["systems"])
        hw, ht   = get_stats(history, hour_tr)
        total_h  = len(history)
        total_w  = sum(1 for t in history if t["win"])
        at_risk  = sum(p["amount"] for p in state["open_positions"])

        tg_send(
            f"{sep}\n"
            f"🆕 <b>ETH ANALİZ — {saat} - {next_h} Yeni İşlem</b>\n"
            f"{dir_ico} <b>ETH</b>  {dir_tr}  ${consensus['amount']:.0f}  giriş:{price:.2f} {price_src}\n"
            f"   🤝 Konsensus: {consensus['count']}/3  [{sys_str}]\n"
            f"   🕐 {hour_tr:02d}:00→{next_h} başarı: {_wr(hw,ht,warn_low=ht<MIN_STAT_COUNT)} | genel: {_wr(total_w,total_h)}\n"
            f"💰 Bakiye: ${state['balance']:.2f}  |  📂 Risk: ${at_risk:.0f}\n"
            f"<i>Eşik: 3/3→25$  2/3→15$</i>\n"
            f"{sep}"
        )
        print(f"[ETH ANALİZ open] {saat} — ETH {consensus['direction']} ${consensus['amount']} ({sys_str})")
    else:
        tg_send(
            f"{sep}\n"
            f"⏸ <b>ETH ANALİZ — {saat} İST</b>\n"
            f"Bu saat ETH için konsensus sağlanamadı (≥2 sistem gerekli).\n"
            f"💰 Bakiye: ${state['balance']:.2f}\n"
            f"{sep}"
        )
        print(f"[ETH ANALİZ open] {saat} — konsensus yok")

# ── WEEKLY ────────────────────────────────────────────────────
def run_weekly() -> None:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from collections import defaultdict

    history = load_history()
    state   = load_state()
    if not history:
        tg_send("📊 <b>ETH ANALİZ HAFTALIK</b>\nHenüz veri yok.")
        return

    days  = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
    hours = list(range(0, 24))
    grid  = defaultdict(lambda: defaultdict(list))

    for t in history:
        h = t.get("entry_hour_tr"); d = t.get("entry_dow")
        if h is not None and d is not None:
            grid[d][h].append(1 if t["win"] else 0)

    data = np.full((7, 24), np.nan)
    for d in range(7):
        for h in range(24):
            vals = grid[d][h]
            if vals: data[d][h] = sum(vals) / len(vals) * 100

    fig, ax = plt.subplots(figsize=(16, 5))
    fig.patch.set_facecolor("#0d0d0d")
    ax.set_facecolor("#0d0d0d")

    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("rg", ["#7f1d1d","#fbbf24","#14532d"])
    masked = np.ma.masked_invalid(data)
    im = ax.imshow(masked, aspect="auto", cmap=cmap, vmin=0, vmax=100)

    for d in range(7):
        for h in range(24):
            v = data[d][h]
            if not np.isnan(v):
                total = len(grid[d][h])
                ax.text(h, d, f"{v:.0f}%\n({total})", ha="center", va="center",
                        fontsize=6, color="white", fontweight="bold")

    ax.set_xticks(range(24)); ax.set_xticklabels([f"{h:02d}" for h in range(24)], color="#aaa", fontsize=8)
    ax.set_yticks(range(7));  ax.set_yticklabels(days, color="#aaa", fontsize=9)

    total_h = len(history); win_h = sum(1 for t in history if t["win"])
    ax.set_title(f"ETH ANALİZ — Sıcaklık Haritası | {total_h} işlem, %{win_h/total_h*100:.0f} WR, Bakiye: ${state['balance']:.2f}",
                 color="white", fontsize=12, pad=12)
    plt.colorbar(im, ax=ax, label="Kazanma Oranı (%)")
    plt.tight_layout()

    img_path = "/tmp/eth_analiz_heatmap.png"
    plt.savefig(img_path, dpi=120, bbox_inches="tight", facecolor="#0d0d0d")
    plt.close()

    caption = (f"📊 ETH ANALİZ HAFTALIK\n"
               f"Toplam: {total_h} işlem | WR: %{win_h/total_h*100:.0f} | "
               f"Bakiye: ${state['balance']:.2f} | P&L: {'+' if state['total_pnl']>=0 else ''}{state['total_pnl']:.2f}$")
    tg_send_photo = lambda p, c: None  # placeholder
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        with open(img_path, "rb") as f: img_data = f.read()
        boundary = "----EthAnalizBoundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{CHAT_ID}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"heatmap.png\"\r\nContent-Type: image/png\r\n\r\n"
        ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=20) as r: r.read()
    except Exception as e:
        print(f"[ETH ANALİZ weekly] Resim gönderilemedi: {e}")

# ── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        asyncio.run(run_close())
    elif mode == "open":
        asyncio.run(run_open())
    elif mode == "weekly":
        run_weekly()
    else:
        print(f"Bilinmeyen mod: {mode}")
        sys.exit(1)
