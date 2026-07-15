"""
11. ANALİZ (A1+A4) — Meta Konsensus Trader

Analiz 1 ve 4'ün bu saat açtığı pozisyonları okur.
Her iki sistemin aynı yönde seçtiği kriptolara girer.

Konsensus → İşlem tutarı:
  2/2 sistem aynı yön  →  $20
  <2                   →  işlem açılmaz

Mod: close / open / weekly
"""
import asyncio, json, os, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pm_trader_helpers import apply_pm_quote, sanal_close_balance, pm_tg_stake, pm_history_extras, pm_stake_fields

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")
_DIR      = os.path.dirname(os.path.abspath(__file__))

STATE_FILE   = os.path.join(_DIR, "poly_trader_karisim1_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_karisim1_history.json")

INITIAL_BALANCE = 300.0
SYMBOLS         = ["BTCUSDT", "SOLUSDT"]

AMOUNT_STRONG   = 20.0   # 2/2 konsensus
AMOUNT_MODERATE = 12.0   # kullanılmıyor (A2 kaldırıldı)
MIN_CONSENSUS   = 2
MIN_STAT_COUNT  = 10

# Kaynak analiz sistem state dosyaları
SOURCE_STATES = {
    "A1": os.path.join(_DIR, "poly_trader_analiz1_state.json"),
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


def tg_send_photo(path: str, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(path, "rb") as f:
            img_data = f.read()
        boundary = "----Karisim1Boundary"
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
                print(f"[11. ANALİZ (A1+A4)] {symbol} fiyat hatası: {e}", file=sys.stderr)
    return None


# ── Konsensus ─────────────────────────────────────────────────
def find_consensus(hour_tr: int) -> list[dict]:
    """
    Kaynak analiz sistemlerinin state'lerini okur.
    Bu saat (hour_tr) açılan pozisyonlarda yön birliği arar.
    Giriş fiyatı olarak kaynak sistemlerin ortalama entry_price'ı kullanılır.
    """
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

        if best_count < MIN_CONSENSUS:
            continue

        prices    = [d["price"] for _, d in best_data if d.get("price")]
        avg_price = sum(prices) / len(prices) if prices else None

        amount = AMOUNT_STRONG

        consensus.append({
            "symbol":    symbol,
            "direction": best_dir,
            "count":     best_count,
            "systems":   [n for n, _ in best_data],
            "amount":    amount,
            "avg_price": avg_price,
        })

    return sorted(consensus, key=lambda x: x["count"], reverse=True)


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


# ── CLOSE ─────────────────────────────────────────────────────
async def run_close() -> None:
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)
    saat    = now_tr.strftime("%H:%M")
    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        print(f"[11. ANALİZ (A1+A4) close] {saat} İST — açık pozisyon yok")
        return

    lines      = []
    toplam_pnl = 0.0
    failed_pos = []

    for pos in state["open_positions"]:
        symbol = pos["symbol"]
        entry  = pos["entry_price"]
        pred   = pos["predicted_dir"]
        amount = pos["amount"]

        current_price = fetch_price_retry(symbol)
        if current_price is None:
            failed_pos.append(pos)
            print(f"[11. ANALİZ (A1+A4) close] {symbol} fiyat alınamadı")
            continue

        if pred == "UP":
            win = current_price >= entry
        else:
            win = current_price <= entry

        pnl = sanal_close_balance(state, pos, win)
        toplam_pnl += pnl
        actual = "UP" if current_price >= entry else "DOWN"
        pct    = (current_price - entry) / entry * 100

        icon    = "✅" if win else "❌"
        name    = symbol.replace("USDT", "")
        pnl_str = f"+${pnl:.2f} ({pm_tg_stake(pos)})" if win else f"-${abs(pnl):.2f}"
        lines.append(
            f"{icon} {name}  {pred}  {entry:.2f}→{current_price:.2f} ({pct:+.2f}%)  "
            f"{pnl_str}  konsensus:{pos.get('count',2)}/2"
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
            **pm_history_extras(pos),
        })

    state["open_positions"] = failed_pos
    save_state(state)
    save_history(history)

    if not lines:
        print(f"[11. ANALİZ (A1+A4) close] {saat} İST — kapatılan pozisyon yok")
        return

    total_pnl    = state["total_pnl"]
    closed_all   = len(history)
    win_all      = sum(1 for t in history if t["win"])
    genel        = f"%{win_all/closed_all*100:.0f}" if closed_all else "—"
    pnl_icon     = "📈" if total_pnl >= 0 else "📉"
    sep          = "━" * 26

    tg_send(
        f"{sep}\n"
        f"🏁 <b>11. ANALİZ (A1+A4) — {int(saat[:2]):02d}:00 Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+'if toplam_pnl>=0 else ''}{toplam_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{pnl_icon} Toplam P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all} işlem)\n"
        f"{sep}"
    )
    print(f"[11. ANALİZ (A1+A4) close] {saat} İST — {len(lines)} pozisyon kapatıldı")


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

    # Konsensus bul
    consensus = find_consensus(hour_tr)

    # Zaten açık olan sembolleri atla
    open_syms = {p["symbol"] for p in state["open_positions"]}
    new_pos   = [c for c in consensus if c["symbol"] not in open_syms]

    opened   = []
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
            "amount":        c["amount"],
            "count":         c["count"],
            "systems":       c["systems"],
            "price_src":     price_src,
        }
        apply_pm_quote(pos, c["symbol"], c["direction"], c["amount"], datetime.now(timezone.utc))
        risk = pos.get("pm_spent", c["amount"])
        if state["balance"] < risk:
            continue
        state["balance"] = round(state["balance"] - risk, 2)
        state["open_positions"].append(pos)
        opened.append({**c, "price": price, "price_src": price_src, "pm_pos": pos})

    save_state(state)

    if not opened:
        print(f"[11. ANALİZ (A1+A4) open] {saat} İST — işlem yok")
        return

    # Bildirim
    at_risk = sum(p.get("amount", AMOUNT_MODERATE) for p in state["open_positions"])
    lines   = [sep, f"🤝 <b>11. ANALİZ (A1+A4) — {saat} - {next_h} Yeni İşlemler</b>"]

    for o in opened:
            name    = o["symbol"].replace("USDT", "")
            dir_tr  = "YÜKSELİR" if o["direction"] == "UP" else "DÜŞER"
            dir_ico = "📈" if o["direction"] == "UP" else "📉"
            sys_str = "+".join(o["systems"])

            sw, st  = get_symbol_stats(history, o["symbol"])
            hw, ht  = get_stats(history, o["symbol"], hour_tr)
            low     = ht < MIN_STAT_COUNT

            price_note = "📌ort" if o.get("price_src") == "kaynak-ort" else "📡anlık"
            lines.append(
                f"{dir_ico} <b>{name}</b>  {dir_tr}  {pm_tg_stake(o.get('pm_pos', o))}  giriş:{o['price']:.2f} {price_note}\n"
                f"   🤝 Konsensus: {o['count']}/2  [{sys_str}]\n"
            f"   🕐 {hour_tr:02d}:00→{next_h} başarı: {_wr(hw,ht,warn_low=low)} | genel: {_wr(sw,st)}"
        )

    lines.append(
        f"💰 Ana: ${state['balance']-at_risk:.2f}  |  📂 Açık: {len(state['open_positions'])} poz ${at_risk:.0f}  |  Toplam: ${state['balance']:.2f}"
    )
    lines.append(f"<i>Eşik: 4→20$  3→12$  2→8$</i>")
    lines.append(sep)

    tg_send("\n".join(lines))
    print(f"[11. ANALİZ (A1+A4) open] {saat} İST — {len(opened)} işlem açıldı")


# ── WEEKLY ────────────────────────────────────────────────────
def run_weekly() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from collections import defaultdict

    history = load_history()
    state   = load_state()
    if not history:
        tg_send("📊 <b>11. ANALİZ (A1+A4) HAFTALIK</b>\nHenüz veri yok.")
        return

    days   = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
    hours  = list(range(0, 24))
    grid   = defaultdict(lambda: defaultdict(list))

    for t in history:
        h = t.get("entry_hour_tr")
        d = t.get("entry_dow")
        if h is not None and d is not None:
            grid[d][h].append(1 if t["win"] else 0)

    data = np.full((7, 24), np.nan)
    for d in range(7):
        for h in range(24):
            vals = grid[d][h]
            if vals:
                data[d][h] = sum(vals) / len(vals) * 100

    fig, ax = plt.subplots(figsize=(14, 5))
    im = ax.imshow(data, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in hours], fontsize=7)
    ax.set_yticks(range(7))
    ax.set_yticklabels(days, fontsize=9)
    plt.colorbar(im, ax=ax, label="Başarı %")
    ax.set_title("11. ANALİZ (A1+A4) — Haftalık Başarı Haritası")
    plt.tight_layout()

    img_path = "/tmp/karisim1_weekly.png"
    plt.savefig(img_path, dpi=110, bbox_inches="tight")
    plt.close()

    total  = len(history)
    wins   = sum(1 for t in history if t["win"])
    sep    = "━" * 26
    caption = (
        f"11. ANALİZ (A1+A4) Haftalık\n"
        f"Bakiye: ${state['balance']:.2f} | P&L: {state['total_pnl']:+.2f}$\n"
        f"Toplam: {wins}/{total} (%{wins/total*100:.0f})"
    )
    tg_send_photo(img_path, caption)

    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    sym_lines = []
    for sym in SYMBOLS:
        name = sym.replace("USDT", "")
        st = [t for t in history if t["symbol"] == sym]
        sw = sum(1 for t in st if t["win"])
        if st:
            sym_lines.append(f"  {name}: {len(st)} işlem / {sw} başarılı (%{sw/len(st)*100:.0f})")
    tg_send(
        f"📊 <b>11. ANALİZ (A1+A4) HAFTALIK İSTATİSTİKLER</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  %{wins/total*100:.0f} başarı\n"
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"\n📈 <b>Sembol Dağılımı</b>\n" + "\n".join(sym_lines)
    )
    print("[11. ANALİZ (A1+A4) weekly] görsel gönderildi")


# ── Entry ─────────────────────────────────────────────────────
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        asyncio.run(run_close())
    elif mode == "weekly":
        run_weekly()
    else:
        asyncio.run(run_open())
