"""
Poly Sanal Trader — 31. Analiz (Multi-TF MR motoru)
Modlar:
  close   → saat başında  (0 * * * *): önceki saatin sonuçlarını kapatır, bildirir
  open    → 5 geçe        (5 * * * *): yeni tahmin, işlem açar
  preview → 45 geçe: bir sonraki saatin geçmiş başarı oranlarını loglar (TG yok)
  weekly  → Cumartesi 21:00: haftalık ısı haritası
  stats   → manuel detaylı rapor

Algoritma: Analiz31/ (multi-TF MR + HTF bias + kill zone)
Sanal bütçe: $300, işlem $12 / $16 / $20 (WR'ye göre)
"""
import asyncio
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_A31 = os.path.join(os.path.dirname(_DIR), "Analiz31")
sys.path.insert(0, _DIR)
sys.path.insert(0, _A31)

from predictor import analyze
from data_fetcher import fetch_klines
from pm_trader_helpers import apply_pm_quote, sanal_pnl

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")

STATE_FILE   = os.path.join(_DIR, "poly_trader_analiz31_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_analiz31_history.json")
WEEKLY_IMG   = "/tmp/poly_weekly_heatmap_analiz31.png"

INITIAL_BALANCE   = 300.0
TRADE_AMOUNT      = 16.0
TRADE_AMOUNT_HIGH = 20.0
TRADE_AMOUNT_LOW  = 12.0
SYMBOLS           = ["BTCUSDT", "SOLUSDT"]
_DAYS_TR          = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_DAYS_FULL_TR     = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
_LABEL            = "31. ANALİZ"


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


def get_stats(history: list, symbol: str, hour_tr: int, dow: int | None = None) -> tuple[int, int]:
    trades = [
        t for t in history
        if t["symbol"] == symbol
        and t.get("entry_hour_tr") == hour_tr
        and (dow is None or t.get("entry_dow") == dow)
    ]
    wins = sum(1 for t in trades if t["win"])
    return wins, len(trades)


def get_symbol_stats(history: list, symbol: str) -> tuple[int, int]:
    trades = [t for t in history if t["symbol"] == symbol]
    wins   = sum(1 for t in trades if t["win"])
    return wins, len(trades)


def _trade_amount(history: list, symbol: str) -> float:
    sw, st = get_symbol_stats(history, symbol)
    rate = sw / st if st else None
    if rate is not None and rate > 0.5:
        return TRADE_AMOUNT_HIGH
    if rate is not None and rate < 0.5:
        return TRADE_AMOUNT_LOW
    return TRADE_AMOUNT


def tg_send(text: str) -> None:
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
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


async def run_close() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")

    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        print(f"[{_LABEL} close] {saat} İST — açık pozisyon yok")
        return

    lines      = []
    toplam_pnl = 0.0
    failed_pos = []

    for pos in list(state["open_positions"]):
        klines = await fetch_klines(pos["symbol"], "1h", 2)
        if not klines:
            failed_pos.append(pos)
            continue
        current_price = klines[-1]["close"]
        entry  = pos["entry_price"]
        pred   = pos["predicted_dir"]
        amount = pos.get("amount", TRADE_AMOUNT)
        actual = "UP" if current_price >= entry else "DOWN"
        win    = (pred == actual)
        pnl    = sanal_pnl(pos, win)
        toplam_pnl += pnl

        state["balance"]   = round(state["balance"] + pnl, 2)
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
            "htf_bias":         pos.get("htf_bias"),
            "up_score":         pos.get("up_score"),
            "down_score":       pos.get("down_score"),
            "factors":          pos.get("factors"),
        }
        for k in ("pm_spent", "pm_size", "pm_entry_price", "to_win", "pm_slug"):
            if pos.get(k) is not None:
                rec[k] = pos[k]
        history.append(rec)

        icon    = "✅" if win else "❌"
        name    = pos["symbol"].replace("USDT", "")
        pct     = (current_price - entry) / entry * 100
        pnl_str = f"+{pnl:.2f}$" if win else f"{pnl:.2f}$"
        lines.append(f"{icon} {name}  {pred}  {entry:.2f} → {current_price:.2f} ({pct:+.2f}%)  {pnl_str}")

    state["open_positions"] = failed_pos
    save_state(state)
    save_history(history)

    if not lines:
        return

    total_pnl  = state.get("total_pnl", 0.0)
    pnl_icon   = "🟢" if total_pnl >= 0 else "🔴"
    closed_all = len(history)
    win_all    = sum(1 for t in history if t["win"])
    genel      = f"%{win_all/closed_all*100:.0f}" if closed_all else "—"
    saat_round = f"{int(saat[:2]):02d}:00"
    sep        = "━" * 26

    msg = (
        f"{sep}\n"
        f"🏁 <b>{_LABEL} — {saat_round} Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+'if toplam_pnl>=0 else ''}{toplam_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{pnl_icon} Toplam P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all} işlem)\n"
        f"{sep}"
    )
    tg_send(msg)
    print(f"[{_LABEL} close] {saat} İST — {len(lines)} pozisyon kapatıldı")


async def run_open() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    hour_tr    = now_tr.hour
    dow        = now_tr.weekday()
    is_weekend = dow >= 5
    saat       = now_tr.strftime("%H:%M")

    state   = load_state()
    history = load_history()

    opened = []
    for sym in SYMBOLS:
        if any(p["symbol"] == sym and p.get("entry_hour_tr") == hour_tr for p in state["open_positions"]):
            print(f"[{_LABEL} open] {sym} — bu saat zaten açık, atlandı")
            continue
        pred_obj = await analyze(sym)
        if pred_obj is None or not pred_obj.predicted_dir:
            print(f"[{_LABEL} open] {sym} — sinyal yok (BEKLE)")
            continue

        dyn_amount = _trade_amount(history, sym)
        try:
            klines = await fetch_klines(sym, "1h", 3)
            entry_price = klines[-2]["close"] if klines and len(klines) >= 2 else pred_obj.current_price
        except Exception:
            entry_price = pred_obj.current_price

        pos = {
            "symbol":           sym,
            "predicted_dir":    pred_obj.predicted_dir,
            "entry_price":      entry_price,
            "entry_time_tr":    now_tr.isoformat(),
            "entry_hour_tr":    hour_tr,
            "entry_dow":        dow,
            "entry_is_weekend": is_weekend,
            "amount":           dyn_amount,
            "htf_bias":         pred_obj.htf_bias,
            "up_score":         pred_obj.up_score,
            "down_score":       pred_obj.down_score,
            "factors":          pred_obj.factors[:6],
        }
        apply_pm_quote(pos, sym, pred_obj.predicted_dir, dyn_amount, now)
        state["open_positions"].append(pos)
        opened.append((sym, pred_obj, entry_price, dyn_amount))

    save_state(state)

    if not opened:
        print(f"[{_LABEL} open] {saat} İST — işlem yok")
        return

    next_h = f"{(hour_tr + 1) % 24:02d}:00"
    lines  = []
    for sym, pred_obj, entry_price, pos_amount in opened:
        name     = sym.replace("USDT", "")
        conf     = pred_obj.confidence * 100
        dir_icon = "📈" if pred_obj.predicted_dir == "UP" else "📉"
        dir_tr   = "YÜKSELİR" if pred_obj.predicted_dir == "UP" else "DÜŞER"
        hour_wins, hour_total = get_stats(history, sym, hour_tr)
        sym_wins,  sym_total  = get_symbol_stats(history, sym)
        factor_hint = pred_obj.factors[0] if pred_obj.factors else ""
        lines.append(
            f"{dir_icon} <b>{name}</b>  {dir_tr}  konf:%{conf:.0f}  giriş:{entry_price:.2f}  💵{pos_amount:.0f}$\n"
            f"   📊 {pred_obj.htf_bias}  |  skor UP={pred_obj.up_score} DOWN={pred_obj.down_score}\n"
            f"   🕐 {hour_tr:02d}:00→{next_h} İST başarı: {_wr(hour_wins, hour_total)}"
            f"  |  genel: {_wr(sym_wins, sym_total)}\n"
            f"   • {factor_hint}"
        )

    sep = "━" * 26
    msg = (
        f"{sep}\n"
        f"🆕 <b>{_LABEL} — {saat} - {next_h} Yeni İşlemler</b>\n"
        + "\n".join(lines) + "\n"
        f"{sep}\n"
        f"💰 Ana: ${state['balance'] - sum(p.get('amount', TRADE_AMOUNT) for p in state['open_positions']):.2f}  |  📂 Açık: {len(state['open_positions'])} poz ${sum(p.get('amount', TRADE_AMOUNT) for p in state['open_positions']):.0f}  |  Toplam: ${state['balance']:.2f}\n"
        f"{sep}"
    )
    tg_send(msg)
    print(f"[{_LABEL} open] {saat} İST — {len(opened)} yeni işlem açıldı")


def run_preview() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    next_hour = (now_tr.hour + 1) % 24
    dow       = now_tr.weekday()
    gun_tr    = _DAYS_FULL_TR[dow]
    history   = load_history()

    lines = []
    for sym in SYMBOLS:
        name = sym.replace("USDT", "")
        dow_wins, dow_total = get_stats(history, sym, next_hour, dow)
        all_wins, all_total = get_stats(history, sym, next_hour)
        if all_total == 0:
            oran_str = "henüz veri yok"
            icon = "⚪"
        else:
            oran = all_wins / all_total * 100
            icon = "🟢" if oran >= 60 else "🟡" if oran >= 50 else "🔴"
            if dow_total >= 3:
                dow_oran = dow_wins / dow_total * 100
                oran_str = f"%{dow_oran:.0f} ({gun_tr})  |  genel %{oran:.0f}"
            else:
                oran_str = f"genel %{oran:.0f} ({all_total} işlem)"
        lines.append(f"{icon} {name}  {next_hour:02d}:00 İST  {oran_str}")

    print(f"[{_LABEL} preview] {now_tr.strftime('%H:%M')} İST — {next_hour:02d}:00 önizleme (TG atlanıyor)")


def run_weekly() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np

    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)

    grid_w = [[0]*24 for _ in range(7)]
    grid_n = [[0]*24 for _ in range(7)]
    sym_names = [s.replace("USDT", "") for s in SYMBOLS]
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
        [(0.00, "#4a3000"), (0.20, "#f9a825"), (0.30, "#fff176"),
         (0.31, "#388e3c"), (0.65, "#1b5e20"), (1.00, "#00e676")],
        N=256,
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
                    sw = grid_sym[sn]["w"][d][h]
                    sn_total = grid_sym[sn]["n"][d][h]
                    if sn_total > 0:
                        sym_parts.append(f"{sn}:+{sw}-{sn_total - sw}")
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
    balance = state.get("balance", INITIAL_BALANCE)
    total_pnl = state.get("total_pnl", 0.0)
    sym_stats = []
    for sym in SYMBOLS:
        name = sym.replace("USDT", "")
        sym_trades = [t for t in history if t["symbol"] == sym]
        sym_wins   = sum(1 for t in sym_trades if t["win"])
        if sym_trades:
            sym_stats.append(f"{name}: {len(sym_trades)} işlem / {sym_wins} başarılı (%{sym_wins/len(sym_trades)*100:.0f})")
    sym_line = "   |   ".join(sym_stats)

    ax.set_title(
        f"{_LABEL} — Haftalık Başarı Haritası  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
        f"Toplam: {total} işlem  |  {genel}  |  Bakiye: ${balance:.2f}  |  P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$\n"
        f"{sym_line}",
        color="#4fc3f7", fontsize=9, fontweight="bold", pad=10,
    )
    ax.set_xlabel("Saat (İST)", color="#546e7a", fontsize=8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
    cbar.ax.yaxis.set_tick_params(color="#546e7a")
    cbar.set_label("Başarı Oranı", color="#546e7a", fontsize=8)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="#546e7a", fontsize=7)
    plt.tight_layout(pad=1.2)
    plt.savefig(WEEKLY_IMG, dpi=150, bbox_inches="tight", facecolor="#0a0e1a", pad_inches=0.1)
    plt.close()

    caption = (
        f"📊 {_LABEL} Haftalık Rapor — {now_tr.strftime('%d.%m.%Y %H:%M İST')}\n"
        f"Toplam {total} işlem | {genel} başarı | ${balance:.2f}"
    )
    tg_send_photo(WEEKLY_IMG, caption)
    pnl_icon = "🟢" if total_pnl >= 0 else "🔴"
    tg_send(
        f"📊 <b>{_LABEL} HAFTALIK İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {genel} başarı\n"
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${balance:.2f}"
    )
    print(f"[{_LABEL} weekly] haftalık görsel gönderildi — {total} işlem")


def run_stats() -> None:
    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)

    if not history:
        tg_send(f"📊 <b>{_LABEL} STATS</b>\nHenüz veri yok.")
        return

    total     = len(history)
    wins_all  = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    parts = [
        f"📊 <b>{_LABEL} İSTATİSTİKLER</b>",
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Toplam: {total} işlem  |  {_wr(wins_all, total)}",
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}",
    ]
    for sym in SYMBOLS:
        name   = sym.replace("USDT", "")
        s_hist = [t for t in history if t["symbol"] == sym]
        if not s_hist:
            continue
        sw, st = sum(1 for t in s_hist if t["win"]), len(s_hist)
        parts.append(f"\n📌 <b>{name}</b>  genel: {_wr(sw, st)}")
    tg_send("\n".join(parts))
    print(f"[{_LABEL} stats] gönderildi")


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
