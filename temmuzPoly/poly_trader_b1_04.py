"""
B1#04 — Edge-ağırlıklı küme konsensüsü (algoritma-islemler birleşimi)

algoritma-islemler sayfasındaki birincil motorların yönlerini toplar, birbirinin
kopyası olan defterleri tek oya indirir ve oyları başabaş fiyata göre ölçülmüş
edge ile ağırlıklandırır. Karar mantığı `b1_04_signal.py` içinde.

Modlar: close / open / preview / weekly / stats
Cron: :02 close · :07 open (a2 sinyalleri :05'te üretildiği için)
"""
import asyncio
import json
import os
import sys
import urllib.request
import urllib.parse
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poly_predictor_analysis import _fetch_klines
from b1_04_signal import SYMBOLS, resolve_live_signal, engine_label
from pm_trader_helpers import (
    apply_pm_quote, slot_amount_log, sanal_pnl,
    symbol_wr_amount_for_book, pm_sanal_settle_trade, pm_sanal_slot_candle,
    SANAL_INITIAL_BALANCE, SANAL_TRADE_AMOUNT, SANAL_TRADE_AMOUNT_HIGH,
    SANAL_TRADE_AMOUNT_LOW, skip_if_weekend_pause, resolve_open_slot_gates,
)
from telegram_poly_channels import chat_analiz4

# ── Config (TG: 4. Analiz botu — B1 ailesiyle aynı kanal) ─────
BOT_TOKEN = os.getenv("TELEGRAM_ANALIZ4_BOT_TOKEN", "8630483764:AAFmAmG4nHAGb238wpavlWgMjJZDvIy4DzE")
CHAT_ID   = chat_analiz4()
_TZ_TR    = ZoneInfo("Europe/Istanbul")

_DIR         = os.path.dirname(os.path.abspath(__file__))
STATE_FILE   = os.path.join(_DIR, "poly_trader_b1_04_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_b1_04_history.json")
WEEKLY_IMG   = "/tmp/poly_b1_04_weekly_heatmap.png"
LABEL        = "B1#04"
BOOK_KEY     = "b1_04"
ALGO_NAME    = "Edge-ağırlıklı küme konsensüsü"

INITIAL_BALANCE   = SANAL_INITIAL_BALANCE
TRADE_AMOUNT      = SANAL_TRADE_AMOUNT
TRADE_AMOUNT_HIGH = SANAL_TRADE_AMOUNT_HIGH
TRADE_AMOUNT_LOW  = SANAL_TRADE_AMOUNT_LOW
_DAYS_TR      = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_DAYS_FULL_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


async def _resolve_signal(symbol: str) -> tuple[str | None, float | None, str]:
    return await resolve_live_signal(symbol)


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


# ── İstatistik yardımcıları ───────────────────────────────────
def _wr(wins: int, total: int) -> str:
    if total == 0:
        return "veri yok"
    return f"%{wins/total*100:.0f} ({wins}/{total})"


def get_stats(history: list, symbol: str, hour_tr: int, dow: int | None = None) -> tuple[int, int]:
    trades = [
        t for t in history
        if t["symbol"] == symbol
        and t.get("entry_hour_tr") == hour_tr
        and (dow is None or t.get("entry_dow") == dow)
    ]
    return sum(1 for t in trades if t["win"]), len(trades)


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol]
    return sum(1 for t in trades if t["win"]), len(trades)


# ── Telegram ─────────────────────────────────────────────────
def tg_send(text: str) -> None:
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"
        }).encode()
        req = urllib.request.Request(url, data=body)
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception as e:
        print(f"[TG] Hata: {e}")


def tg_send_photo(path: str, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(path, "rb") as f:
            img_data = f.read()
        boundary = "----PolyBoundary"
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


# ── CLOSE: :02 — önceki saatin sonuçlarını kapat ──────────────
async def run_close() -> None:
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")
    if skip_if_weekend_pause(LABEL, "close", now_tr):
        return

    state = load_state()
    history = load_history()

    if not state["open_positions"]:
        print(f"[{LABEL} close] {saat} İST — açık pozisyon yok")
        return

    lines = []
    toplam_pnl = 0.0
    failed_pos = []

    for pos in list(state["open_positions"]):
        candle = pm_sanal_slot_candle(pos["symbol"], pos["entry_time_tr"])
        if not candle:
            failed_pos.append(pos)
            continue
        hour_open, hour_close = candle
        settled = pm_sanal_settle_trade(pos, hour_open, hour_close)
        current_price = settled["exit_price"]
        entry = settled["entry_price"]
        pred = pos["predicted_dir"]
        amount = pos.get("amount", TRADE_AMOUNT)
        actual = settled["actual_dir"]
        win = settled["win"]
        pnl = settled["pnl"]
        toplam_pnl += pnl

        state["balance"] = round(state["balance"] + pnl, 2)
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

        rec = {
            "symbol":           pos["symbol"],
            "predicted_dir":    pred,
            "actual_dir":       actual,
            "win":              win,
            "entry_price":      entry,
            "exit_price":       current_price,
            "entry_time_tr":    pos["entry_time_tr"],
            "entry_hour_tr":    pos["entry_hour_tr"],
            "entry_dow":        pos["entry_dow"],
            "entry_is_weekend": pos["entry_is_weekend"],
            "amount":           amount,
            "exit_time_tr":     now_tr.isoformat(),
            "pnl":              pnl,
            "algo_signal":      pos.get("algo_signal"),
            "algo_name":        pos.get("algo_name", ALGO_NAME),
            "algo_ok":          (pos.get("algo_signal") == actual) if pos.get("algo_signal") else None,
            "consensus_net":    pos.get("consensus_net"),
        }
        for k in ("pm_spent", "pm_size", "pm_entry_price", "to_win", "pm_slug",
                  "pm_fee", "pm_quote_src", "pm_mid_price",
                  "hot_hour_boost", "cold_hour_cut"):
            if pos.get(k) is not None:
                rec[k] = pos[k]
        history.append(rec)

        icon = "✅" if win else "❌"
        name = pos["symbol"].replace("USDT", "")
        pct = (current_price - entry) / entry * 100
        pnl_str = f"+{pnl:.2f}$" if win else f"{pnl:.2f}$"
        lines.append(f"{icon} {name}  {pred}  {entry:.2f} → {current_price:.2f} ({pct:+.2f}%)  {pnl_str}")

    state["open_positions"] = failed_pos
    if failed_pos:
        names = ", ".join(p["symbol"].replace("USDT", "") for p in failed_pos)
        print(f"[{LABEL} close] {saat} — fiyat alınamadı: {names}")
    save_state(state)
    save_history(history)

    if not lines:
        return

    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon = "🟢" if total_pnl >= 0 else "🔴"
    closed_all = len(history)
    win_all = sum(1 for t in history if t["win"])
    genel = f"%{win_all/closed_all*100:.0f}" if closed_all else "—"
    saat_round = f"{int(saat[:2]):02d}:00"
    sep = "━" * 26

    tg_send(
        f"{sep}\n"
        f"🏁 <b>{LABEL} — {saat_round} Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+' if toplam_pnl >= 0 else ''}{toplam_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{pnl_icon} Toplam P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all} işlem)\n"
        f"{sep}"
    )
    print(f"[{LABEL} close] {saat} İST — {len(lines)} pozisyon kapatıldı")


# ── OPEN: :07 — konsensüs kararı + pozisyon aç ────────────────
async def run_open() -> None:
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")
    hour_tr = now_tr.hour
    dow = now_tr.weekday()
    is_weekend = dow >= 5

    state = load_state()
    history = load_history()

    if skip_if_weekend_pause(LABEL, "open", now_tr, history=history):
        return
    cold_skip, _, _, _, cold_note = resolve_open_slot_gates(history, hour_tr, 0)
    if cold_skip:
        print(f"[{LABEL} open] {saat} — {cold_note} · işlem yok")
        return

    candidates = []
    for sym in SYMBOLS:
        direction, price, detail = await _resolve_signal(sym)
        if direction is None:
            print(f"[{LABEL} open] {sym} — konsensüs yok ({detail})")
            continue
        candidates.append({"sym": sym, "direction": direction, "price": price, "detail": detail})

    if not candidates:
        print(f"[{LABEL} open] {saat} İST — eşiği geçen sembol yok, işlem açılmadı")
        return

    lines = []
    next_h = f"{(hour_tr + 1) % 24:02d}:00"
    for c in candidates:
        sym = c["sym"]
        direction = c["direction"]
        base_amt = symbol_wr_amount_for_book(history, sym, BOOK_KEY)
        _sk, dyn_amount, hot_boost, cold_cut, _note = resolve_open_slot_gates(
            history, hour_tr, base_amt
        )
        slot_amount_log(LABEL, hour_tr, base_amt, dyn_amount, hot_boost, cold_cut)

        try:
            klines = await _fetch_klines(sym, "1h", 3)
            entry_price = klines[-2]["close"] if klines and len(klines) >= 2 else c["price"]
        except Exception:
            entry_price = c["price"]
        if entry_price is None:
            print(f"[{LABEL} open] {sym} — giriş fiyatı alınamadı, atlandı")
            continue

        net = None
        if "net " in (c["detail"] or ""):
            try:
                net = float(c["detail"].split("net ")[1].split(" ")[0])
            except Exception:
                net = None

        pos = {
            "symbol":           sym,
            "predicted_dir":    direction,
            "entry_price":      entry_price,
            "entry_time_tr":    now_tr.isoformat(),
            "entry_hour_tr":    hour_tr,
            "entry_dow":        dow,
            "entry_is_weekend": is_weekend,
            "amount":           dyn_amount,
            "hot_hour_boost":   hot_boost,
            "cold_hour_cut":    cold_cut,
            "algo_signal":      direction,
            "algo_name":        ALGO_NAME,
            "consensus_net":    net,
        }
        apply_pm_quote(pos, sym, direction, dyn_amount, now)
        state["open_positions"].append(pos)

        name = sym.replace("USDT", "")
        dir_icon = "📈" if direction == "UP" else "📉"
        dir_tr = "YÜKSELİR" if direction == "UP" else "DÜŞER"
        hour_wins, hour_total = get_stats(history, sym, hour_tr)
        sym_wins, sym_total = get_symbol_stats(history, sym)
        lines.append(
            f"{dir_icon} <b>{name}</b>  {dir_tr}  giriş:{entry_price:.2f}  💵{dyn_amount:.0f}$\n"
            f"   🧮 {c['detail']}\n"
            f"   🕐 {hour_tr:02d}:00→{next_h} İST başarı: {_wr(hour_wins, hour_total)}"
            f"  |  genel: {_wr(sym_wins, sym_total)}"
        )

    save_state(state)

    if not lines:
        print(f"[{LABEL} open] {saat} İST — işlem yok")
        return

    sep = "━" * 26
    acik = sum(p.get("amount", TRADE_AMOUNT) for p in state["open_positions"])
    tg_send(
        f"{sep}\n"
        f"🆕 <b>{LABEL} — {saat} - {next_h} Yeni İşlemler</b>  🔶 SANAL  📊 {ALGO_NAME}\n"
        + "\n".join(lines) + "\n"
        f"{sep}\n"
        f"💰 Ana: ${state['balance'] - acik:.2f}  |  📂 Açık: {len(state['open_positions'])} poz ${acik:.0f}"
        f"  |  Toplam: ${state['balance']:.2f}\n"
        f"{sep}"
    )
    print(f"[{LABEL} open] {saat} İST — {len(lines)} yeni işlem açıldı")


# ── PREVIEW ───────────────────────────────────────────────────
def run_preview() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    next_hour = (now_tr.hour + 1) % 24
    dow = now_tr.weekday()
    gun_tr = _DAYS_FULL_TR[dow]
    history = load_history()

    lines = []
    for sym in SYMBOLS:
        name = sym.replace("USDT", "")
        dow_wins, dow_total = get_stats(history, sym, next_hour, dow)
        all_wins, all_total = get_stats(history, sym, next_hour)
        if all_total == 0:
            oran_str, icon = "henüz veri yok", "⚪"
        else:
            oran = all_wins / all_total * 100
            icon = "🟢" if oran >= 60 else "🟡" if oran >= 50 else "🔴"
            if dow_total >= 3:
                oran_str = f"%{dow_wins/dow_total*100:.0f} ({gun_tr})  |  genel %{oran:.0f}"
            else:
                oran_str = f"genel %{oran:.0f} ({all_total} işlem)"
        lines.append(f"{icon} <b>{name}</b>  {next_hour:02d}:00 İST  {oran_str}")

    sep = "━" * 26
    msg = (
        f"🔭 <b>{LABEL} — {now_tr.strftime('%d.%m.%Y')} {next_hour:02d}:00 İST ÖNİZLEME</b>\n{sep}\n"
        + "\n".join(lines) + f"\n{sep}"
    )
    print(msg.replace("<b>", "").replace("</b>", ""))


# ── WEEKLY ────────────────────────────────────────────────────
def run_weekly() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np

    history = load_history()
    state = load_state()
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)

    grid_w = [[0] * 24 for _ in range(7)]
    grid_n = [[0] * 24 for _ in range(7)]
    sym_names = [s.replace("USDT", "") for s in SYMBOLS]
    grid_sym = {s: {"w": [[0] * 24 for _ in range(7)], "n": [[0] * 24 for _ in range(7)]}
                for s in sym_names}
    for t in history:
        d, h = t.get("entry_dow"), t.get("entry_hour_tr")
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
        [(0.00, "#4a3000"), (0.20, "#f9a825"), (0.30, "#fff176"),
         (0.31, "#388e3c"), (0.65, "#1b5e20"), (1.00, "#00e676")],
        N=256,
    )
    cmap.set_bad(color="#141820")
    im = ax.imshow(np.ma.masked_invalid(rate), cmap=cmap, vmin=0.35, vmax=0.85, aspect="auto")

    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=7, color="#78909c")
    ax.set_yticks(range(7))
    ax.set_yticklabels(_DAYS_TR, fontsize=9, color="#b0bec5", fontweight="bold")
    ax.tick_params(length=0)

    for d in range(7):
        for h in range(24):
            if not np.isnan(rate[d][h]):
                pct = int(rate[d][h] * 100)
                clr = "white" if rate[d][h] >= 0.50 else "#1a1400"
                parts = []
                for sn in sym_names:
                    tot = grid_sym[sn]["n"][d][h]
                    if tot:
                        parts.append(f"{sn}:+{grid_sym[sn]['w'][d][h]}-{tot - grid_sym[sn]['w'][d][h]}")
                ax.text(h, d, f"%{pct}({grid_n[d][h]})\n" + "\n".join(parts),
                        ha="center", va="center", fontsize=5, color=clr,
                        fontweight="bold", linespacing=1.5)

    for x in range(25):
        ax.axvline(x - 0.5, color="#0a0e1a", linewidth=0.5)
    for y in range(8):
        ax.axhline(y - 0.5, color="#0a0e1a", linewidth=0.5)

    total = len(history)
    wins = sum(1 for t in history if t["win"])
    genel = f"%{wins/total*100:.0f}" if total else "—"
    total_pnl = state.get("total_pnl", 0.0)
    sym_stats = []
    for sym in SYMBOLS:
        s_hist = [t for t in history if t["symbol"] == sym]
        if s_hist:
            sw = sum(1 for t in s_hist if t["win"])
            sym_stats.append(f"{sym.replace('USDT','')}: {len(s_hist)} işlem / {sw} başarılı "
                             f"(%{sw/len(s_hist)*100:.0f})")

    ax.set_title(
        f"{LABEL} — Haftalık Başarı Haritası  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
        f"Toplam: {total} işlem  |  {genel}  |  Bakiye: ${state.get('balance', INITIAL_BALANCE):.2f}"
        f"  |  P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$\n"
        + "   |   ".join(sym_stats),
        color="#4fc3f7", fontsize=9, fontweight="bold", pad=10,
    )
    ax.set_xlabel("Saat (İST)", color="#546e7a", fontsize=8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
    cbar.set_label("Başarı Oranı", color="#546e7a", fontsize=8)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="#546e7a", fontsize=7)
    cbar.set_ticks([0.4, 0.5, 0.6, 0.7, 0.8])
    cbar.set_ticklabels(["%40", "%50", "%60", "%70", "%80"])
    plt.tight_layout(pad=1.2)
    plt.savefig(WEEKLY_IMG, dpi=150, bbox_inches="tight", facecolor="#0a0e1a", pad_inches=0.1)
    plt.close()

    tg_send_photo(
        WEEKLY_IMG,
        f"📊 {LABEL} Haftalık Rapor — {now_tr.strftime('%d.%m.%Y %H:%M İST')}\n"
        f"Toplam {total} işlem | {genel} başarı | ${state.get('balance', INITIAL_BALANCE):.2f}",
    )
    print(f"[{LABEL} weekly] haftalık görsel gönderildi — {total} işlem")


# ── STATS ─────────────────────────────────────────────────────
def run_stats() -> None:
    from b1_04_signal import compute_book_edges, compute_clusters, book_label
    history = load_history()
    state = load_state()
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)

    total = len(history)
    wins_all = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon = "🟢" if total_pnl >= 0 else "🔴"

    parts = [
        f"📊 <b>{LABEL} İSTATİSTİKLER</b>",
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        "━" * 26,
        f"Toplam: {total} işlem  |  {_wr(wins_all, total)}",
        f"{pnl_icon} P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}$"
        f"  |  Bakiye: ${state.get('balance', INITIAL_BALANCE):.2f}",
    ]

    edges = compute_book_edges()
    clusters = compute_clusters()
    groups: dict[str, list] = {}
    for key, root in clusters.items():
        groups.setdefault(root, []).append(key)

    parts.append("\n🧮 <b>Oy Ağırlıkları (küme başına tek oy)</b>")
    rows = []
    for root, members in groups.items():
        best = max(
            (edges[m] for m in members if m in edges),
            key=lambda x: x["edge"], default=None,
        )
        if not best or best["weight"] <= 0:
            continue
        names = ", ".join(sorted(book_label(m) for m in members))
        rows.append((best["weight"], best["label"], names, len(members)))
    for w, lead, names, cnt in sorted(rows, reverse=True)[:8]:
        extra = f" ({cnt} defter: {names})" if cnt > 1 else ""
        parts.append(f"  • {lead} ağırlık {w:.3f}{extra}")
    if not rows:
        parts.append("  ⚪ ağırlık taşıyan küme yok")

    for sym in SYMBOLS:
        s_hist = [t for t in history if t["symbol"] == sym]
        if not s_hist:
            continue
        sw = sum(1 for t in s_hist if t["win"])
        parts.append(f"\n📌 <b>{sym.replace('USDT','')}</b>  genel: {_wr(sw, len(s_hist))}")

    tg_send("\n".join(parts))
    print(f"[{LABEL} stats] gönderildi")


# ── Giriş noktası ─────────────────────────────────────────────
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode == "close":
        asyncio.run(run_close())
    elif mode == "preview":
        run_preview()
    elif mode == "weekly":
        run_weekly()
    elif mode == "stats":
        run_stats()
    else:
        asyncio.run(run_open())
