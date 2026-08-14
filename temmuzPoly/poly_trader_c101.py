"""
C1#01 · OPUS-OHLCV — Adil Fiyat defteri (PTB + volatilite olasılık modeli)

Projedeki ilk "yön tahmin etmeyen" defter. Diğer 53 defter mumdan yön çıkarıp
piyasa fiyatına bakmadan alıyor; C101 önce adil olasılığı hesaplıyor, sonra
Polymarket'in istediği fiyatla karşılaştırıyor ve yalnız **piyasa yanlış
fiyatlamışsa** giriyor. Kademe çeyrek Kelly — kenar büyükse büyük, küçükse küçük.

Veri harmanı: OHLCV (Parkinson volatilite) + emir defteri derinliği + taker
akışı + funding + open interest. Ayrıntı: c101_signal.py

Gölge defter: sanal $500, gerçek para emri YOK. Amaç A2#05 ile aynı slotlarda
karşılaştırma. Modeli ölçen asıl çıktı kalibrasyon günlüğü — açılmayan slotlar
da kaydedilir, çünkü "0.70 dedim, gerçekte %70 mi çıktı" sorusu ancak öyle
yanıtlanır.

Modlar: close / open / preview / stats / calib / compare
Cron: :02 close · :05 open
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_FILE = os.path.join(_DIR, "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, _DIR)

from c101_signal import SYMBOLS, evaluate, fair_probability, stake_for  # noqa: E402
from pm_trader_helpers import (  # noqa: E402
    pm_best_ask, pm_find_market, pm_sanal_settle_trade, pm_sanal_slot_candle,
    pm_taker_fee, skip_if_weekend_pause,
)
from telegram_poly_channels import chat_analiz4  # noqa: E402

BOT_TOKEN = os.getenv("TELEGRAM_ANALIZ4_BOT_TOKEN", "8630483764:AAFmAmG4nHAGb238wpavlWgMjJZDvIy4DzE")
CHAT_ID = chat_analiz4()
_TZ_TR = ZoneInfo("Europe/Istanbul")

STATE_FILE = os.path.join(_DIR, "poly_trader_c101_state.json")
HISTORY_FILE = os.path.join(_DIR, "poly_trader_c101_history.json")
CALIB_FILE = os.path.join(_DIR, "c101_calibration.jsonl")
LABEL = "C1#01"
BOOK_KEY = "c101"
ALGO_NAME = "OPUS-OHLCV · PTB + volatilite adil fiyat"
# Diğer sanal defterler $300; bu defter Kelly kademelendirmesi için $500 ile başlar
INITIAL_BALANCE = 500.0
COMPARE_KEY = "a2_05"


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


def calib_append(rec: dict) -> None:
    """Her değerlendirme (açılan + açılmayan) kalibrasyon günlüğüne yazılır."""
    try:
        with open(CALIB_FILE, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[{LABEL}] kalibrasyon yazılamadı: {e}")


def calib_load() -> list[dict]:
    if not os.path.exists(CALIB_FILE):
        return []
    out = []
    with open(CALIB_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def calib_rewrite(rows: list[dict]) -> None:
    with open(CALIB_FILE, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def tg_send(text: str) -> None:
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        body = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=15).read()
    except Exception as e:
        print(f"[{LABEL}] TG hatası: {e}")


def _wr(wins: int, total: int) -> str:
    return f"%{wins/total*100:.0f} ({wins}/{total})" if total else "veri yok"


# ── PM kotasyonu ──────────────────────────────────────────────
def pm_prices(symbol: str, now_utc: datetime) -> dict | None:
    """Saatlik PM piyasasının iki taraf fiyatı — modelin karşılaştırma hedefi.

    Kenar ancak **gerçekten ödenecek fiyata** karşı ölçülürse anlamlı, o yüzden
    her iki tarafın CLOB best_ask'i kullanılır. Gamma `outcomePrices` son işlem
    fiyatı; saat başında bayat kalıp ask'ten 10+ puan sapabiliyor ve modele
    olmayan bir kenar gösteriyor. Defter okunamazsa mid'e düşülür.
    """
    et_hour = (now_utc - timedelta(hours=4)).hour
    pm = pm_find_market(symbol, et_hour, now_utc)
    if not pm or pm.get("closed"):
        return None
    op = pm.get("outcome_prices") or []
    if len(op) < 2:
        return None
    try:
        up_mid, down_mid = float(op[0]), float(op[1])
    except (ValueError, TypeError):
        return None
    up_ask = pm_best_ask(pm["up_token"])
    down_ask = pm_best_ask(pm["down_token"])
    up_p = up_ask if up_ask is not None else up_mid
    down_p = down_ask if down_ask is not None else down_mid
    if not (0.01 < up_p < 0.99 and 0.01 < down_p < 0.99):
        return None
    return {
        "slug": pm["slug"],
        "title": pm.get("title", ""),
        "up": up_p,
        "down": down_p,
        "quote_src": "ask" if (up_ask is not None and down_ask is not None) else "mid",
        "up_mid": round(up_mid, 4),
        "down_mid": round(down_mid, 4),
        "overround": round(up_p + down_p - 1.0, 4),
    }


# ── OPEN ──────────────────────────────────────────────────────
def run_open() -> None:
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")
    if skip_if_weekend_pause(LABEL, "open", now_tr):
        return

    state = load_state()
    history = load_history()
    balance = float(state.get("balance") or INITIAL_BALANCE)

    opened, skipped = [], []

    for sym in SYMBOLS:
        model = fair_probability(sym, now_tr)
        if not model:
            skipped.append((sym, "model üretilemedi", None))
            continue
        mkt = pm_prices(sym, now)
        if not mkt:
            skipped.append((sym, "PM kotasyonu yok", None))
            continue

        ev = evaluate(model, mkt["up"], mkt["down"])

        calib = {
            "ts_tr": now_tr.isoformat(timespec="seconds"),
            "entry_hour_tr": now_tr.hour,
            "symbol": sym,
            "ptb": model["ptb"],
            "spot": model["spot"],
            "sigma_eff": model["sigma_eff"],
            "depth_mult": model["depth_mult"],
            "intrahour_mult": model["intrahour_mult"],
            "z": model["z"],
            "p_base": model["p_base"],
            "tilt": model["tilt"],
            "p_up_model": model["p_up"],
            "pm_up": mkt["up"],
            "pm_down": mkt["down"],
            "overround": mkt["overround"],
            "direction": ev["direction"],
            "edge": ev["edge"],
            "traded": ev["tradable"],
            "skip_reason": ev["skip_reason"],
            "slug": mkt["slug"],
            "outcome": None,
        }

        if not ev["tradable"]:
            calib_append(calib)
            skipped.append((sym, ev["skip_reason"], ev))
            continue

        stake = stake_for(balance, ev["kelly_used"])
        if stake > balance:
            calib["traded"] = False
            calib["skip_reason"] = "bakiye yetersiz"
            calib_append(calib)
            skipped.append((sym, "bakiye yetersiz", ev))
            continue

        price = ev["pm_price"]
        size = round(stake / price, 2)
        pos = {
            "symbol": sym,
            "predicted_dir": ev["direction"],
            "entry_price": model["ptb"],
            "entry_time_tr": now_tr.isoformat(),
            "entry_hour_tr": now_tr.hour,
            "entry_dow": now_tr.weekday(),
            "entry_is_weekend": now_tr.weekday() >= 5,
            "amount": stake,
            "algo_signal": ev["direction"],
            "algo_name": ALGO_NAME,
            # PM sanal kotasyonu — pm_stake_fields / sanal_pnl bu alanları okur
            "pm_slug": mkt["slug"],
            "pm_title": mkt["title"],
            "pm_token_dir": ev["direction"],
            "pm_entry_price": price,
            "pm_spent": round(size * price, 2),
            "pm_size": size,
            "to_win": size,
            "pm_fee": pm_taker_fee(size, price),
            "pm_quote_src": mkt.get("quote_src", "mid"),
            "pm_mid_price": mkt.get("up_mid") if ev["direction"] == "UP" else mkt.get("down_mid"),
            # C101'e özgü teşhis alanları
            "c101_p_model": ev["p_model"],
            "c101_pm_price": price,
            "c101_edge": ev["edge"],
            "c101_kelly": ev["kelly_used"],
            "c101_sigma_eff": model["sigma_eff"],
            "c101_z": model["z"],
            "c101_spot": model["spot"],
            "c101_tilt": model["tilt"],
            "c101_depth_mult": model["depth_mult"],
        }
        state["open_positions"].append(pos)
        balance_note = f"{stake:.2f}"
        opened.append((sym, ev, model, stake))
        calib_append(calib)
        print(f"[{LABEL} open] {sym} {ev['direction']} @{price:.2f} "
              f"model {ev['p_model']:.3f} kenar +{ev['edge']*100:.1f}p stake ${balance_note}")

    save_state(state)

    for sym, reason, _ev in skipped:
        print(f"[{LABEL} open] {sym} — {reason}")

    if not opened:
        print(f"[{LABEL} open] {saat} İST — kenar yok, işlem açılmadı")
        return

    sep = "━" * 26
    lines = []
    for sym, ev, model, stake in opened:
        name = sym.replace("USDT", "")
        icon = "📈" if ev["direction"] == "UP" else "📉"
        dir_tr = "YÜKSELİR" if ev["direction"] == "UP" else "DÜŞER"
        h_wins = sum(1 for t in history if t["symbol"] == sym and t["win"])
        h_tot = sum(1 for t in history if t["symbol"] == sym)
        lines.append(
            f"{icon} <b>{name}</b>  {dir_tr}  💵{stake:.2f}$\n"
            f"   🎯 model {ev['p_model']*100:.1f}%  vs  piyasa {ev['pm_price']*100:.0f}%"
            f"  →  kenar <b>+{ev['edge']*100:.1f} puan</b>\n"
            f"   📏 PTB {model['ptb']:.2f} · spot {model['spot']:.2f}"
            f" · σ {model['sigma_eff']*100:.3f}%/s · z {model['z']:+.2f}\n"
            f"   📊 genel: {_wr(h_wins, h_tot)}"
        )
    next_h = f"{(now_tr.hour + 1) % 24:02d}:00"
    msg = (
        f"{sep}\n"
        f"🧪 <b>{LABEL} · OPUS-OHLCV</b>  {now_tr:%d.%m.%Y} {now_tr.hour:02d}:00→{next_h}\n"
        f"<i>yön tahmini değil, yanlış fiyatlama avı · çeyrek Kelly</i>\n"
        + "\n".join(lines) + "\n"
        f"💰 Bakiye: ${state['balance']:.2f}\n{sep}"
    )
    tg_send(msg)
    print(f"[{LABEL} open] {saat} İST — {len(opened)} pozisyon açıldı")


# ── CLOSE ─────────────────────────────────────────────────────
def _settle_calibration(pos: dict, actual: str, win: bool) -> None:
    """Kalibrasyon satırına gerçekleşen sonucu işle (aynı slot + sembol)."""
    rows = calib_load()
    if not rows:
        return
    et = (pos.get("entry_time_tr") or "")[:13]
    hit = False
    for r in rows:
        if r.get("symbol") == pos.get("symbol") and str(r.get("ts_tr", ""))[:13] == et:
            r["outcome"] = actual
            r["won"] = win
            hit = True
    if hit:
        calib_rewrite(rows)


def run_close() -> None:
    now_tr = datetime.now(timezone.utc).astimezone(_TZ_TR)
    saat = now_tr.strftime("%H:%M")

    state = load_state()
    history = load_history()
    if not state.get("open_positions"):
        print(f"[{LABEL} close] {saat} İST — açık pozisyon yok")
        return

    lines, failed = [], []
    tur_pnl = 0.0

    for pos in list(state["open_positions"]):
        candle = pm_sanal_slot_candle(pos["symbol"], pos["entry_time_tr"])
        if not candle:
            failed.append(pos)
            continue
        hour_open, hour_close = candle
        s = pm_sanal_settle_trade(pos, hour_open, hour_close)
        win, pnl, actual = s["win"], s["pnl"], s["actual_dir"]
        tur_pnl += pnl
        state["balance"] = round(state["balance"] + pnl, 2)
        state["total_pnl"] = round(state.get("total_pnl", 0.0) + pnl, 2)

        rec = {
            "symbol": pos["symbol"],
            "predicted_dir": pos["predicted_dir"],
            "actual_dir": actual,
            "win": win,
            "entry_price": s["entry_price"],
            "exit_price": s["exit_price"],
            "entry_time_tr": pos["entry_time_tr"],
            "entry_hour_tr": pos["entry_hour_tr"],
            "entry_dow": pos["entry_dow"],
            "entry_is_weekend": pos["entry_is_weekend"],
            "amount": pos.get("amount"),
            "exit_time_tr": now_tr.isoformat(),
            "pnl": pnl,
            "algo_signal": pos.get("algo_signal"),
            "algo_name": pos.get("algo_name", ALGO_NAME),
            "algo_ok": (pos.get("algo_signal") == actual) if pos.get("algo_signal") else None,
        }
        for k in ("pm_spent", "pm_size", "pm_entry_price", "to_win", "pm_slug",
                  "pm_fee", "pm_quote_src", "pm_mid_price"):
            if pos.get(k) is not None:
                rec[k] = pos[k]
        for k in list(pos):
            if k.startswith("c101_"):
                rec[k] = pos[k]
        history.append(rec)
        _settle_calibration(pos, actual, win)

        icon = "✅" if win else "❌"
        name = pos["symbol"].replace("USDT", "")
        pct = (s["exit_price"] - s["entry_price"]) / s["entry_price"] * 100
        lines.append(
            f"{icon} {name}  {pos['predicted_dir']}  @{pos.get('c101_pm_price', 0):.2f}"
            f"  (model {float(pos.get('c101_p_model') or 0)*100:.0f}%)"
            f"  {pct:+.2f}%  {'+' if pnl >= 0 else ''}{pnl:.2f}$"
        )

    state["open_positions"] = failed
    save_state(state)
    save_history(history)

    if not lines:
        print(f"[{LABEL} close] {saat} — kapatılan pozisyon yok")
        return

    total = state.get("total_pnl", 0.0)
    closed_all = len(history)
    win_all = sum(1 for t in history if t["win"])
    sep = "━" * 26
    msg = (
        f"{sep}\n"
        f"🏁 <b>{LABEL} — {int(saat[:2]):02d}:00 Sonuçlar</b>\n"
        + "\n".join(lines) + "\n"
        f"Bu tur: {'+' if tur_pnl >= 0 else ''}{tur_pnl:.2f}$  |  Bakiye: ${state['balance']:.2f}\n"
        f"{'🟢' if total >= 0 else '🔴'} Toplam: {'+' if total >= 0 else ''}{total:.2f}$"
        f"  |  Genel: {_wr(win_all, closed_all)}\n{sep}"
    )
    tg_send(msg)
    print(f"[{LABEL} close] {saat} İST — {len(lines)} pozisyon kapatıldı")


# ── PREVIEW ───────────────────────────────────────────────────
def run_preview() -> None:
    now = datetime.now(timezone.utc)
    now_tr = now.astimezone(_TZ_TR)
    print(f"{LABEL} önizleme — {now_tr:%d.%m.%Y %H:%M} İST (kayıt yok)")
    print("═" * 74)
    for sym in SYMBOLS:
        model = fair_probability(sym, now_tr, update_baseline=False)
        if not model:
            print(f"{sym}: model yok")
            continue
        mkt = pm_prices(sym, now)
        if not mkt:
            print(f"{sym}: PM kotasyonu yok  (model P(UP)={model['p_up']:.3f})")
            continue
        ev = evaluate(model, mkt["up"], mkt["down"])
        verdict = "AÇ" if ev["tradable"] else f"atla — {ev['skip_reason']}"
        print(f"\n{sym}  PTB {model['ptb']:.2f} → spot {model['spot']:.2f}"
              f"  kalan {model['t_remain']*60:.0f} dk")
        print(f"  σ_etkin {model['sigma_eff']*100:.3f}%/saat  (derinlik ×{model['depth_mult']}"
              f" · saat içi ×{model['intrahour_mult']})   z={model['z']:+.3f}")
        print(f"  model  P(UP)={model['p_up']:.3f}  P(DOWN)={1-model['p_up']:.3f}")
        print(f"  piyasa P(UP)={mkt['up']:.3f}  P(DOWN)={mkt['down']:.3f}"
              f"  (overround {mkt['overround']:+.3f})")
        print(f"  → {ev['direction']}  kenar {ev['edge']*100:+.1f} puan"
              f"  Kelly {ev['kelly_used']*100:.1f}%  ⇒ {verdict}")


# ── STATS ─────────────────────────────────────────────────────
def run_stats() -> None:
    history = load_history()
    state = load_state()
    if not history:
        print(f"{LABEL} — kapanmış işlem yok")
        return
    wins = sum(1 for t in history if t["win"])
    n = len(history)
    print(f"\n{LABEL} — {n} işlem · WR {_wr(wins, n)} · bakiye ${state.get('balance', 0):.2f}"
          f" · toplam {state.get('total_pnl', 0):+.2f}$")
    print("─" * 70)
    by_sym: dict[str, list] = defaultdict(list)
    for t in history:
        by_sym[t["symbol"]].append(t)
    for sym, rows in sorted(by_sym.items()):
        w = sum(1 for t in rows if t["win"])
        pnl = sum(t["pnl"] for t in rows)
        avg_edge = sum(float(t.get("c101_edge") or 0) for t in rows) / len(rows)
        print(f"  {sym:9s} {_wr(w, len(rows)):>16s}  {pnl:+8.2f}$"
              f"  ort. kenar +{avg_edge*100:.1f}p")

    print("\nKenar dilimine göre (model haklı çıkıyor mu?)")
    buckets = [(0.05, 0.08), (0.08, 0.12), (0.12, 0.20), (0.20, 1.0)]
    for lo, hi in buckets:
        rows = [t for t in history if lo <= float(t.get("c101_edge") or 0) < hi]
        if not rows:
            continue
        w = sum(1 for t in rows if t["win"])
        exp = sum(float(t.get("c101_p_model") or 0) for t in rows) / len(rows)
        pnl = sum(t["pnl"] for t in rows)
        print(f"  kenar {lo*100:.0f}-{hi*100:.0f}p: beklenen %{exp*100:.1f}"
              f" · gerçek {_wr(w, len(rows))} · {pnl:+.2f}$")


# ── CALIB — modelin asıl sınavı ───────────────────────────────
def run_calib() -> None:
    """Model 0.70 dediğinde gerçekten %70 mi çıkıyor? Piyasadan iyi mi?

    Sonucu bilinen tüm değerlendirmeler (açılmayanlar dahil) kullanılır;
    örneklem böylece 3-4 kat büyür.
    """
    rows = [r for r in calib_load() if r.get("outcome") in ("UP", "DOWN")]
    if not rows:
        print(f"{LABEL} — sonucu bilinen kalibrasyon kaydı yok")
        print("     (close turları çalıştıkça dolar; açılmayan slotlar için")
        print("      `python3 poly_trader_c101.py backfill` gerekir)")
        return

    print(f"\n{LABEL} kalibrasyon — {len(rows)} değerlendirme")
    print("═" * 74)
    print(f"{'P(UP) dilimi':>14s} {'n':>5s} {'model':>8s} {'gerçek':>8s} "
          f"{'piyasa':>8s} {'model hata':>11s} {'piyasa hata':>12s}")
    print("─" * 74)

    edges = [(0.0, 0.2), (0.2, 0.35), (0.35, 0.5), (0.5, 0.65), (0.65, 0.8), (0.8, 1.01)]
    m_brier_all, p_brier_all = [], []
    for lo, hi in edges:
        sel = [r for r in rows if lo <= float(r["p_up_model"]) < hi]
        if not sel:
            continue
        up_real = sum(1 for r in sel if r["outcome"] == "UP") / len(sel)
        m_avg = sum(float(r["p_up_model"]) for r in sel) / len(sel)
        p_avg = sum(float(r["pm_up"]) for r in sel) / len(sel)
        print(f"{lo:.2f}-{hi:.2f}".rjust(14)
              + f" {len(sel):5d} {m_avg:8.3f} {up_real:8.3f} {p_avg:8.3f}"
              + f" {m_avg-up_real:+11.3f} {p_avg-up_real:+12.3f}")

    for r in rows:
        y = 1.0 if r["outcome"] == "UP" else 0.0
        m_brier_all.append((float(r["p_up_model"]) - y) ** 2)
        p_brier_all.append((float(r["pm_up"]) - y) ** 2)
    mb = sum(m_brier_all) / len(m_brier_all)
    pb = sum(p_brier_all) / len(p_brier_all)
    print("─" * 74)
    print(f"Brier skoru (düşük iyi):  model {mb:.4f}   piyasa {pb:.4f}"
          f"   fark {mb-pb:+.4f}")
    if mb < pb:
        print(f"✅ Model piyasadan {(pb-mb)/pb*100:.1f}% daha iyi kalibre — kenar var.")
    else:
        print(f"❌ Model piyasadan kötü. Bu haliyle gerçek paraya geçilmez.")

    traded = [r for r in rows if r.get("traded")]
    if traded:
        w = sum(1 for r in traded if r.get("won"))
        exp = sum(float(r["p_up_model"] if r["direction"] == "UP" else 1 - r["p_up_model"])
                  for r in traded) / len(traded)
        print(f"\nAçılan {len(traded)} işlem: beklenen WR %{exp*100:.1f}"
              f" · gerçek {_wr(w, len(traded))}")


# ── BACKFILL — açılmayan slotların sonucunu doldur ────────────
def run_backfill() -> None:
    """Kalibrasyon günlüğündeki sonucu boş satırları Binance mumundan tamamla."""
    rows = calib_load()
    if not rows:
        print(f"{LABEL} — kalibrasyon günlüğü boş")
        return
    now_tr = datetime.now(_TZ_TR)
    cache: dict[tuple[str, str], tuple[float, float] | None] = {}
    filled = 0
    for r in rows:
        if r.get("outcome"):
            continue
        ts = r.get("ts_tr") or ""
        try:
            slot = datetime.fromisoformat(ts).astimezone(_TZ_TR)
        except Exception:
            continue
        if (now_tr - slot).total_seconds() < 3660:
            continue  # saat henüz kapanmadı
        key = (r["symbol"], ts[:13])
        if key not in cache:
            cache[key] = pm_sanal_slot_candle(r["symbol"], ts)
        candle = cache[key]
        if not candle:
            continue
        hour_open, hour_close = candle
        actual = "UP" if hour_close >= hour_open else "DOWN"
        r["outcome"] = actual
        r["won"] = (r.get("direction") == actual)
        filled += 1
    if filled:
        calib_rewrite(rows)
    print(f"{LABEL} backfill — {filled} kayıt tamamlandı "
          f"({sum(1 for r in rows if r.get('outcome'))}/{len(rows)} sonuçlu)")


# ── COMPARE — A2#05 ile aynı slotlarda ────────────────────────
def run_compare() -> None:
    """Aynı slotlarda C101 vs A2#05: kim daha çok kazandı, nerede ayrıştılar?"""
    c_hist = load_history()
    a_path = os.path.join(_DIR, f"poly_trader_{COMPARE_KEY}_history.json")
    if not os.path.exists(a_path):
        print(f"{COMPARE_KEY} geçmişi bulunamadı: {a_path}")
        return
    with open(a_path) as f:
        a_hist = json.load(f)
    if not c_hist:
        print(f"{LABEL} — henüz kapanmış işlem yok, karşılaştırma için veri lazım")
        return

    def slot(t: dict) -> tuple[str, str]:
        return t.get("symbol", ""), str(t.get("entry_time_tr", ""))[:13]

    a_by = {slot(t): t for t in a_hist}
    common = [(c, a_by[slot(c)]) for c in c_hist if slot(c) in a_by]
    if not common:
        print("Ortak slot yok — C101 birkaç tur daha çalışsın.")
        return

    c_w = sum(1 for c, _ in common if c["win"])
    a_w = sum(1 for _, a in common if a["win"])
    c_p = sum(c["pnl"] for c, _ in common)
    a_p = sum(a["pnl"] for _, a in common)
    agree = [(c, a) for c, a in common if c["predicted_dir"] == a["predicted_dir"]]
    diff = [(c, a) for c, a in common if c["predicted_dir"] != a["predicted_dir"]]

    print(f"\n{LABEL} vs A2#05 — {len(common)} ortak slot")
    print("═" * 62)
    print(f"  {LABEL:8s}  WR {_wr(c_w, len(common)):>16s}   P&L {c_p:+8.2f}$")
    print(f"  {'A2#05':8s}  WR {_wr(a_w, len(common)):>16s}   P&L {a_p:+8.2f}$")
    print(f"\n  Aynı yön : {len(agree)} slot ({len(agree)/len(common)*100:.0f}%)")
    if diff:
        cd_w = sum(1 for c, _ in diff if c["win"])
        ad_w = sum(1 for _, a in diff if a["win"])
        print(f"  Ayrışma  : {len(diff)} slot → {LABEL} {cd_w}/{len(diff)}"
              f" · A2#05 {ad_w}/{len(diff)}")
    only_c = [c for c in c_hist if slot(c) not in a_by]
    if only_c:
        w = sum(1 for c in only_c if c["win"])
        p = sum(c["pnl"] for c in only_c)
        print(f"\n  Yalnız {LABEL}: {len(only_c)} slot · {_wr(w, len(only_c))} · {p:+.2f}$")


_MODES = {
    "open": run_open, "close": run_close, "preview": run_preview,
    "stats": run_stats, "calib": run_calib, "compare": run_compare,
    "backfill": run_backfill,
}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    fn = _MODES.get(mode)
    if not fn:
        print(f"Bilinmeyen mod: {mode}\nKullanım: {' | '.join(_MODES)}")
        sys.exit(1)
    fn()
