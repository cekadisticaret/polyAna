"""
2. ANALİZ — Filtreli Poly Sanal Trader
Aynı algoritma (poly_predictor_analysis.py), üstüne 3 ek filtre:

  FİLTRE 1 — Min Güven: conf < %68 ise işlem açılmaz
  FİLTRE 2 — Korelasyon: 3 coin de aynı yöndeyse sadece en yüksek konf'lu al
  FİLTRE 3 — İstatistik Güveni: 10'dan az veri olan saatlerde ⚠️ uyarısı

1. Analiz vs 2. Analiz → hangi yaklaşım daha iyi, veri biriktikçe görülür.

Modlar: close / open / preview / weekly / stats
"""
import asyncio
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from poly_predictor_analysis import predict, _fetch_klines

# ── Config ────────────────────────────────────────────────────
BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")

_DIR          = os.path.dirname(os.path.abspath(__file__))
STATE_FILE    = os.path.join(_DIR, "poly_trader_analiz2_state.json")
HISTORY_FILE  = os.path.join(_DIR, "poly_trader_analiz2_history.json")
WEEKLY_IMG    = "/tmp/poly_v2_weekly_heatmap.png"

INITIAL_BALANCE    = 300.0
TRADE_AMOUNT       = 15.0   # sabit işlem miktarı
TRADE_AMOUNT_HIGH  = 15.0
TRADE_AMOUNT_LOW   = 15.0
SYMBOLS          = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
_DAYS_TR         = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
_DAYS_FULL_TR    = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

# ── 2. ANALİZ FİLTRE PARAMETRELERİ ──────────────────────────
MIN_CONF       = 0.68   # Filtre 1: minimum güven eşiği
MIN_STAT_COUNT = 10     # Filtre 3: istatistik güveni için min işlem sayısı


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
def _wr(wins: int, total: int, warn_low: bool = False) -> str:
    if total == 0:
        return "veri yok"
    pct = wins / total * 100
    low = f" ⚠️" if warn_low and total < MIN_STAT_COUNT else ""
    return f"%{pct:.0f} ({wins}/{total}){low}"


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


# ── Telegram ─────────────────────────────────────────────────
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
        boundary = "----V2Boundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{CHAT_ID}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"v2_heatmap.png\"\r\nContent-Type: image/png\r\n\r\n"
        ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
    except Exception as e:
        print(f"[TG photo] Hata: {e}")


# ── FİLTRELEME MANTIĞI ───────────────────────────────────────
def apply_filters(candidates: list[dict]) -> tuple[list[dict], list[str]]:
    """
    candidates: [{"sym": ..., "pred_obj": ..., "conf": ...}, ...]
    Filtre 1: conf < MIN_CONF olanları elek
    Filtre 2: tümü aynı yöndeyse sadece max-conf'u al
    Döner: (geçenler, elenen_acıklamalar)
    """
    logs = []

    # Filtre 1: min güven
    passed = []
    for c in candidates:
        if c["conf"] >= MIN_CONF:
            passed.append(c)
        else:
            logs.append(
                f"⛔ {c['sym'].replace('USDT','')} elendi — "
                f"konf %{c['conf']*100:.0f} < %{MIN_CONF*100:.0f}"
            )

    if not passed:
        return [], logs

    # Filtre 2: korelasyon — hepsi aynı yöndeyse sadece birini al
    dirs = set(c["pred_obj"].predicted_dir for c in passed)
    if len(dirs) == 1 and len(passed) > 1:
        best = max(passed, key=lambda c: c["conf"])
        removed = [c for c in passed if c != best]
        for c in removed:
            logs.append(
                f"⛔ {c['sym'].replace('USDT','')} elendi — "
                f"3 coin korelasyonlu, sadece en yüksek konf alındı"
            )
        passed = [best]

    return passed, logs


# ── CLOSE ─────────────────────────────────────────────────────
async def run_close() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat   = now_tr.strftime("%H:%M")
    tarih  = now_tr.strftime("%d.%m.%Y")

    state   = load_state()
    history = load_history()

    if not state["open_positions"]:
        tg_send(
            f"🤖 <b>2. ANALİZ</b> — {tarih} {saat} İST\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏸ Kapatılacak açık pozisyon yok."
        )
        print(f"[2. ANALİZ close] {saat} İST — açık pozisyon yok")
        return

    lines      = []
    toplam_pnl = 0.0
    failed_pos = []

    for pos in list(state["open_positions"]):
        klines = await _fetch_klines(pos["symbol"], "1h", 2)
        if not klines:
            failed_pos.append(pos)
            continue
        current_price = klines[-1]["close"]

        entry  = pos["entry_price"]
        pred   = pos["predicted_dir"]
        amount = pos.get("amount", TRADE_AMOUNT)
        actual = "UP" if current_price >= entry else "DOWN"
        win    = (pred == actual)
        pnl    = amount if win else -amount
        toplam_pnl += pnl

        state["balance"]   = round(state["balance"] + pnl, 2)
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

        history.append({
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
            "entry_conf":       pos.get("entry_conf", 0),
            "exit_time_tr":     now_tr.isoformat(),
            "pnl":              pnl,
            "ind_rsi_vote":     pos.get("ind_rsi_vote"),
            "ind_rsi_ok":       (pos.get("ind_rsi_vote") == actual) if pos.get("ind_rsi_vote") else None,
            "ind_macd_vote":    pos.get("ind_macd_vote"),
            "ind_macd_ok":      (pos.get("ind_macd_vote") == actual) if pos.get("ind_macd_vote") else None,
            "ind_ema_vote":     pos.get("ind_ema_vote"),
            "ind_ema_ok":       ((pos.get("ind_ema_vote") == actual)
                                 if pos.get("ind_ema_vote") and pos.get("ind_ema_vote") != "NEUTRAL"
                                 else None),
        })

        icon    = "✅" if win else "❌"
        name    = pos["symbol"].replace("USDT", "")
        pct     = (current_price - entry) / entry * 100
        pnl_str = f"+{pnl:.0f}$" if win else f"{pnl:.0f}$"
        lines.append(f"{icon} {name}  {pred}  {entry:.2f} → {current_price:.2f} ({pct:+.2f}%)  {pnl_str}")

    state["open_positions"] = failed_pos

    if failed_pos:
        names = ", ".join(p["symbol"].replace("USDT", "") for p in failed_pos)
        tg_send(f"⚠️ <b>2. ANALİZ</b> — {names} fiyatı alınamadı, bir sonraki saate bırakıldı.")
    save_state(state)
    save_history(history)

    total_pnl  = state.get("total_pnl", 0.0)
    pnl_icon   = "🟢" if total_pnl >= 0 else "🔴"
    closed_all = len(history)
    win_all    = sum(1 for t in history if t["win"])
    genel      = f"%{win_all/closed_all*100:.0f}" if closed_all else "—"
    saat_round = f"{int(saat[:2]):02d}:00"
    sep        = "━" * 26

    msg = (
        f"{sep}\n"
        f"🏁 <b>2. ANALİZ — {saat_round} Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+'if toplam_pnl>=0 else ''}{toplam_pnl:.0f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{pnl_icon} Toplam P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Genel: {genel} ({closed_all} işlem)\n"
        f"{sep}"
    )
    tg_send(msg)
    print(f"[2. ANALİZ close] {saat} İST — {len(lines)} pozisyon kapatıldı")


# ── OPEN ──────────────────────────────────────────────────────
async def run_open() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    hour_tr    = now_tr.hour
    dow        = now_tr.weekday()
    is_weekend = dow >= 5
    saat       = now_tr.strftime("%H:%M")
    tarih      = now_tr.strftime("%d.%m.%Y")

    state   = load_state()
    history = load_history()

    # Tüm sinyalleri topla
    candidates = []
    for sym in SYMBOLS:
        pred_obj = await predict(sym)
        if pred_obj is None:
            continue
        conf = max(pred_obj.prob_up, pred_obj.prob_down)
        candidates.append({"sym": sym, "pred_obj": pred_obj, "conf": conf})

    # Filtreleri uygula
    passed, filter_logs = apply_filters(candidates)
    passed_syms = {c["sym"] for c in passed}

    # Sadece filtreden geçenler için pozisyon aç
    for c in passed:
        sym         = c["sym"]
        pred_obj    = c["pred_obj"]
        conf        = c["conf"]
        ind_ema_raw = pred_obj.trend.upper()
        sw2, st2    = get_symbol_stats(history, sym)
        rate2       = sw2 / st2 if st2 else None
        dyn_amount2 = (TRADE_AMOUNT_HIGH if (rate2 is not None and rate2 > 0.5)
                       else TRADE_AMOUNT_LOW if (rate2 is not None and rate2 < 0.5)
                       else TRADE_AMOUNT)
        state["open_positions"].append({
            "symbol":           sym,
            "predicted_dir":    pred_obj.predicted_dir,
            "entry_price":      klines[-2]["close"],  # son kapanan mum = Polymarket Price to Beat
            "entry_time_tr":    now_tr.isoformat(),
            "entry_hour_tr":    hour_tr,
            "entry_dow":        dow,
            "entry_is_weekend": is_weekend,
            "entry_conf":       conf,
            "amount":           dyn_amount2,
            "ind_rsi_vote":     "UP" if pred_obj.rsi < 50 else "DOWN",
            "ind_rsi_val":      round(pred_obj.rsi, 1),
            "ind_macd_vote":    "UP" if pred_obj.macd_bull else "DOWN",
            "ind_ema_vote":     ("UP" if "YUKARI" in ind_ema_raw
                                 else "DOWN" if "AŞAĞI" in ind_ema_raw
                                 else "NEUTRAL"),
        })

    save_state(state)

    # Sadece filtreden geçen sinyalleri göster
    next_h = f"{(hour_tr + 1) % 24:02d}:00"
    lines  = []
    for c in passed:
        sym      = c["sym"]
        pred_obj = c["pred_obj"]
        conf     = c["conf"]
        name     = sym.replace("USDT", "")
        dir_icon = "📈" if pred_obj.predicted_dir == "UP" else "📉"
        dir_tr   = "YÜKSELİR" if pred_obj.predicted_dir == "UP" else "DÜŞER"
        hour_wins, hour_total = get_stats(history, sym, hour_tr)
        sym_wins,  sym_total  = get_symbol_stats(history, sym)
        low_data   = hour_total < MIN_STAT_COUNT
        sym_rate2  = sym_wins / sym_total if sym_total else None
        disp_amt2  = (TRADE_AMOUNT_HIGH if (sym_rate2 is not None and sym_rate2 > 0.5)
                      else TRADE_AMOUNT_LOW if (sym_rate2 is not None and sym_rate2 < 0.5)
                      else TRADE_AMOUNT)
        lines.append(
            f"{dir_icon} <b>{name}</b>  {dir_tr}  konf:%{conf*100:.0f}  giriş:{klines[-2]['close']:.2f}  💵{disp_amt2:.0f}$\n"
            f"   🕐 {hour_tr:02d}:00→{next_h} İST başarı: "
            f"{_wr(hour_wins, hour_total, warn_low=low_data)}"
            f"  |  genel: {_wr(sym_wins, sym_total)}"
        )

    sep      = "━" * 26
    mini_sep = "━" * 10
    parts    = [f"{sep}", f"🆕 <b>2. ANALİZ — {saat} - {next_h} Yeni İşlemler</b>"]

    if lines:
        parts.extend(lines)
    else:
        parts.append("⏸ <i>Bu saat sinyal yok.</i>")

    if filter_logs:
        parts.append(mini_sep)
        parts.append("🔎 Filtre Raporu")
        parts.extend(filter_logs)
        parts.append(mini_sep)

    _at_risk2 = sum(p.get("amount", TRADE_AMOUNT) for p in state["open_positions"])
    parts.append(f"💰 Ana: ${state['balance'] - _at_risk2:.2f}  |  📂 Açık: {len(state['open_positions'])} poz ${_at_risk2:.0f}  |  Toplam: ${state['balance']:.2f}")
    parts.append(sep)

    tg_send("\n".join(parts))
    print(f"[2. ANALİZ open] {saat} İST — {len(passed)} işlem açıldı ({len(filter_logs)} elendi)")


# ── PREVIEW ───────────────────────────────────────────────────
def run_preview() -> None:
    now    = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    next_hour = (now_tr.hour + 1) % 24
    dow       = now_tr.weekday()
    gun_tr    = _DAYS_FULL_TR[dow]
    tarih     = now_tr.strftime("%d.%m.%Y")
    history   = load_history()

    lines = []
    for sym in SYMBOLS:
        name = sym.replace("USDT", "")
        dow_wins, dow_total = get_stats(history, sym, next_hour, dow)
        all_wins, all_total = get_stats(history, sym, next_hour)
        low_data = all_total < MIN_STAT_COUNT

        if all_total == 0:
            oran_str = "henüz veri yok"
            icon = "⚪"
        else:
            oran = all_wins / all_total * 100
            icon = "🟢" if oran >= 60 else "🟡" if oran >= 50 else "🔴"
            warn = " ⚠️" if low_data else ""
            if dow_total >= 3:
                dow_oran = dow_wins / dow_total * 100
                oran_str = f"%{dow_oran:.0f} ({gun_tr})  |  genel %{oran:.0f}{warn}"
            else:
                oran_str = f"genel %{oran:.0f} ({all_total} işlem){warn}"

        lines.append(f"{icon} <b>{name}</b>  {next_hour:02d}:00 İST  {oran_str}")

    sep = "━" * 26
    msg = (
        f"🔭 <b>2. ANALİZ — {tarih} {next_hour:02d}:00 İST ÖNİZLEME</b>\n{sep}\n"
        + "\n".join(lines) +
        f"\n{sep}\n"
        f"<i>Min konf eşiği: %{MIN_CONF*100:.0f}  |  Min istatistik: {MIN_STAT_COUNT} işlem</i>"
    )
    tg_send(msg)
    print(f"[2. ANALİZ preview] {now_tr.strftime('%H:%M')} İST — {next_hour:02d}:00 önizleme gönderildi")


# ── WEEKLY ────────────────────────────────────────────────────
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
                pct  = int(rate[d][h]*100)
                n    = grid_n[d][h]
                warn = "⚠" if n < MIN_STAT_COUNT else ""
                clr  = "white" if rate[d][h] >= 0.50 else "#1a1400"
                sym_parts = []
                for sn in sym_names:
                    sw = grid_sym[sn]["w"][d][h]
                    sn_total = grid_sym[sn]["n"][d][h]
                    if sn_total > 0:
                        sym_parts.append(f"{sn}:+{sw}-{sn_total-sw}")
                sym_str = "\n".join(sym_parts)
                ax.text(h, d, f"%{pct}{warn}({n})\n{sym_str}", ha="center", va="center",
                        fontsize=5, color=clr, fontweight="bold", linespacing=1.5)

    for x in range(25):
        ax.axvline(x - 0.5, color="#0a0e1a", linewidth=0.5)
    for y in range(8):
        ax.axhline(y - 0.5, color="#0a0e1a", linewidth=0.5)

    total = len(history)
    wins  = sum(1 for t in history if t["win"])
    genel = f"%{wins/total*100:.0f}" if total else "—"
    balance   = state.get("balance", INITIAL_BALANCE)
    total_pnl = state.get("total_pnl", 0.0)

    ax.set_title(
        f"2. ANALİZ — Haftalık Başarı Haritası  ({now_tr.strftime('%d.%m.%Y %H:%M İST')})\n"
        f"Toplam: {total} işlem  |  {genel}  |  Bakiye: ${balance:.2f}  |  P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  "
        f"|  Min konf: %{MIN_CONF*100:.0f}",
        color="#ffa726", fontsize=10, fontweight="bold", pad=10
    )
    ax.set_xlabel("Saat (İST)", color="#546e7a", fontsize=8)

    cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
    cbar.ax.yaxis.set_tick_params(color="#546e7a")
    cbar.set_label("Başarı Oranı", color="#546e7a", fontsize=8)
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color="#546e7a", fontsize=7)
    cbar.set_ticks([0.4, 0.5, 0.6, 0.7, 0.8])
    cbar.set_ticklabels(["%40", "%50", "%60", "%70", "%80"])

    plt.tight_layout(pad=1.2)
    plt.savefig(WEEKLY_IMG, dpi=150, bbox_inches="tight",
                facecolor="#0a0e1a", pad_inches=0.1)
    plt.close()

    caption = (
        f"📊 2. ANALİZ Haftalık Rapor — {now_tr.strftime('%d.%m.%Y %H:%M İST')}\n"
        f"Toplam {total} işlem | {genel} başarı | ${balance:.2f}"
    )
    tg_send_photo(WEEKLY_IMG, caption)

    ind_lines = _ind_stats_lines(history)
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"
    tg_send(
        f"📊 <b>2. ANALİZ HAFTALIK İSTATİSTİKLER</b>\n"
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Toplam: {total} işlem  |  {genel} başarı\n"
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${balance:.2f}\n"
        f"\n🔬 <b>Algoritma İsabet Oranı</b>\n" + "\n".join(ind_lines)
    )
    print(f"[2. ANALİZ weekly] haftalık görsel gönderildi — {total} işlem")


# ── İndikatör isabet yardımcısı ───────────────────────────────
def _ind_stats_lines(history: list) -> list[str]:
    checks = [("RSI", "ind_rsi_ok"), ("MACD", "ind_macd_ok"), ("EMA", "ind_ema_ok")]
    lines = []
    for label, key in checks:
        vals = [t[key] for t in history if t.get(key) is not None]
        if vals:
            w   = sum(1 for v in vals if v)
            n   = len(vals)
            bar = "🟢" if w / n >= 0.6 else "🟡" if w / n >= 0.5 else "🔴"
            lines.append(f"  {bar} {label}: {_wr(w, n)}")
        else:
            lines.append(f"  ⚪ {label}: veri yok")
    return lines


# ── STATS ─────────────────────────────────────────────────────
def run_stats() -> None:
    history = load_history()
    state   = load_state()
    now_tr  = datetime.now(timezone.utc).astimezone(_TZ_TR)

    if not history:
        tg_send("📊 <b>2. ANALİZ STATS</b>\nHenüz veri yok.")
        return

    total    = len(history)
    wins_all = sum(1 for t in history if t["win"])
    total_pnl = state.get("total_pnl", 0.0)
    pnl_icon  = "🟢" if total_pnl >= 0 else "🔴"

    parts = [
        f"📊 <b>2. ANALİZ İSTATİSTİKLER</b>",
        f"{now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Toplam: {total} işlem  |  {_wr(wins_all, total)}",
        f"{pnl_icon} P&L: {'+'if total_pnl>=0 else ''}{total_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}",
        f"Filtre: min konf %{MIN_CONF*100:.0f}  |  ⚠️ = {MIN_STAT_COUNT} altı veri",
        f"\n🔬 <b>İndikatör İsabet Oranı</b>",
        *_ind_stats_lines(history),
    ]

    wd = [t for t in history if not t.get("entry_is_weekend")]
    we = [t for t in history if t.get("entry_is_weekend")]
    if wd or we:
        parts.append(f"\n📅 <b>Hafta İçi vs Hafta Sonu</b>")
        if wd:
            parts.append(f"  Hafta içi : {_wr(sum(1 for t in wd if t['win']), len(wd))}")
        if we:
            parts.append(f"  Hafta sonu: {_wr(sum(1 for t in we if t['win']), len(we))}")

    for sym in SYMBOLS:
        name   = sym.replace("USDT", "")
        s_hist = [t for t in history if t["symbol"] == sym]
        if not s_hist:
            continue
        sw, st = sum(1 for t in s_hist if t["win"]), len(s_hist)
        parts.append(f"\n📌 <b>{name}</b>  genel: {_wr(sw, st)}")

        hour_data: dict[int, list] = {}
        for t in s_hist:
            h = t.get("entry_hour_tr")
            if h is None:
                continue
            hour_data.setdefault(h, [0, 0])
            hour_data[h][1] += 1
            if t["win"]:
                hour_data[h][0] += 1

        rows = [(h, w, n) for h, (w, n) in hour_data.items() if n >= 3]
        rows.sort(key=lambda x: x[1]/x[2], reverse=True)
        for h, w, n in rows[:5]:
            bar      = "🟢" if w/n >= 0.6 else "🟡" if w/n >= 0.5 else "🔴"
            low_warn = " ⚠️" if n < MIN_STAT_COUNT else ""
            parts.append(f"  {bar} {h:02d}:00 İST  {_wr(w, n)}{low_warn}")

    parts.append(f"\n📆 <b>Gün Bazlı</b>")
    dow_data: dict[int, list] = {}
    for t in history:
        d = t.get("entry_dow")
        if d is None:
            continue
        dow_data.setdefault(d, [0, 0])
        dow_data[d][1] += 1
        if t["win"]:
            dow_data[d][0] += 1

    for d in range(7):
        if d not in dow_data:
            continue
        w, n = dow_data[d]
        bar = "🟢" if w/n >= 0.6 else "🟡" if w/n >= 0.5 else "🔴"
        wk  = "📅" if d < 5 else "🏖"
        parts.append(f"  {wk}{bar} {_DAYS_TR[d]}  {_wr(w, n)}")

    tg_send("\n".join(parts))
    print("[2. ANALİZ stats] gönderildi")


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
