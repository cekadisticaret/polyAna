"""
BTC ANALİZ — 27 saatlik yön oylaması (24 algo + 3 trader)

Zayıf performanslı 15 algo + A4/A9 trader hariç.
Her saat :01'de analiz + Telegram; Analiz 509 sanal işlem :02'de açılır ($400, $10–20, girişte bakiyeden düşülür).
"""
import asyncio
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from algo_signals import collect_btc_algo_votes, fetch_klines
from poly_predictor_analysis import predict
from poly_trader_analiz5 import analyze as analyze5
from poly_trader_analiz10 import analyze as analyze10

BOT_TOKEN = "8727030715:AAEjjvUzAuw2GR-sVlZXUHknI0gT9mkz4WA"
CHAT_ID   = "830754964"
_TZ_TR    = ZoneInfo("Europe/Istanbul")
SYMBOL    = "BTCUSDT"
_ORIG_TOTAL = 44
# Son 15 saat ~%33 ve altı — oylamadan çıkarıldı
EXCLUDED_VOTES: set[int | str] = {
    2, 4, 8, 9, 10, 16, 19, 21, 25, 28, 30, 31, 32, 37, 39,
    "A4", "A9",
}
TOTAL     = _ORIG_TOTAL - len(EXCLUDED_VOTES)  # 27
LABEL     = "509. ANALİZ BTC"
INITIAL_BALANCE = 400.0

STATE_FILE    = os.path.join(_DIR, "btc_analiz_hourly_state.json")
TRADER_STATE  = os.path.join(_DIR, "btc_analiz_509_state.json")
TRADER_HIST   = os.path.join(_DIR, "btc_analiz_509_history.json")


def tg_send(text: str) -> None:
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
        req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
    except Exception as e:
        print(f"[TG] Hata: {e}")


def _norm_dir(val) -> str:
    if val in ("UP", "DOWN"):
        return val
    return "NEUTRAL"


def _trader_dir(result: dict | None, *keys: str) -> str:
    if not result:
        return "NEUTRAL"
    for key in keys:
        d = result.get(key)
        if d in ("UP", "DOWN"):
            return d
    return "NEUTRAL"


def _scale_threshold(orig: int) -> int:
    return max(1, round(orig * TOTAL / _ORIG_TOTAL))


MIN_TRADE_VOTES = _scale_threshold(23)


def _filter_votes(votes: list[dict]) -> list[dict]:
    return [v for v in votes if v["id"] not in EXCLUDED_VOTES]


async def _collect_trader_votes() -> list[dict]:
    votes = []

    try:
        p1 = await predict(SYMBOL)
        votes.append({
            "id": "A1", "name": "1. Analiz (Predictor)",
            "signal": _norm_dir(p1.predicted_dir if p1 else None), "group": "trader",
        })
    except Exception as e:
        print(f"[A1] hata: {e}")
        votes.append({"id": "A1", "name": "1. Analiz (Predictor)", "signal": "NEUTRAL", "group": "trader"})

    try:
        r5 = await analyze5(SYMBOL)
        votes.append({
            "id": "A5", "name": "5. Analiz (Predictor + momentum)",
            "signal": _trader_dir(r5, "predicted_dir", "raw_direction"), "group": "trader",
        })
    except Exception as e:
        print(f"[A5] hata: {e}")
        votes.append({"id": "A5", "name": "5. Analiz (Predictor + momentum)", "signal": "NEUTRAL", "group": "trader"})

    try:
        r10 = await analyze10(SYMBOL)
        votes.append({
            "id": "A10", "name": "10. Analiz (A1+A9 konsensüs)",
            "signal": _trader_dir(r10, "direction", "raw_direction"), "group": "trader",
        })
    except Exception as e:
        print(f"[A10] hata: {e}")
        votes.append({"id": "A10", "name": "10. Analiz (A1+A9 konsensüs)", "signal": "NEUTRAL", "group": "trader"})

    return votes


def _consensus_dir(n_up: int, n_down: int) -> str | None:
    if n_up > n_down:
        return "UP"
    if n_down > n_up:
        return "DOWN"
    return None


def _calc_amount(n_win: int) -> float:
    """Konsensüs gücüne göre lot (27 oy ölçeğinde)."""
    if n_win >= _scale_threshold(29):
        return 20.0
    if n_win >= _scale_threshold(25):
        return 15.0
    if n_win >= _scale_threshold(23):
        return 10.0
    return 0.0


def _fmt_price(p: float) -> str:
    return f"${p:,.0f}" if p >= 1000 else f"${p:,.2f}"


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"pending": None, "history": [], "algo_stats": {}, "votes_log": []}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _load_trader() -> dict:
    if os.path.exists(TRADER_STATE):
        try:
            with open(TRADER_STATE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": INITIAL_BALANCE, "open_positions": [], "total_pnl": 0.0}


def _save_trader(state: dict) -> None:
    with open(TRADER_STATE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _load_trader_hist() -> list:
    if os.path.exists(TRADER_HIST):
        try:
            with open(TRADER_HIST) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_trader_hist(history: list) -> None:
    with open(TRADER_HIST, "w") as f:
        json.dump(history[-500:], f, indent=2, ensure_ascii=False)


def _hour_entry_price() -> float | None:
    try:
        kl = fetch_klines(SYMBOL, "1h", 5)
        if len(kl) >= 2:
            return kl[-2]["c"]
    except Exception as e:
        print(f"[BTC ANALİZ] entry price hatası: {e}")
    return None


def _hour_exit_price() -> float | None:
    try:
        kl = fetch_klines(SYMBOL, "1h", 5)
        if len(kl) >= 2:
            return kl[-2]["c"]
    except Exception as e:
        print(f"[BTC ANALİZ] exit price hatası: {e}")
    return None


def _update_algo_stats(state: dict, votes: list[dict], actual: str) -> None:
    stats = state.setdefault("algo_stats", {})
    for v in votes:
        sig = v.get("signal")
        if sig not in ("UP", "DOWN"):
            continue
        vid = str(v["id"])
        if vid not in stats:
            stats[vid] = {"name": v.get("name", vid), "total": 0, "correct": 0}
        stats[vid]["total"] += 1
        if sig == actual:
            stats[vid]["correct"] += 1
        if v.get("name"):
            stats[vid]["name"] = v["name"]


def _verify_previous(state: dict) -> dict | None:
    pending = state.get("pending")
    if not pending:
        return None

    exit_price = _hour_exit_price()
    entry = pending.get("entry_price")
    if exit_price is None or entry is None:
        return None

    if exit_price > entry:
        actual = "UP"
    elif exit_price < entry:
        actual = "DOWN"
    else:
        actual = "FLAT"

    pct = (exit_price - entry) / entry * 100 if entry else 0.0
    predicted = pending.get("predicted")
    correct = predicted is not None and predicted == actual

    if pending.get("votes"):
        _update_algo_stats(state, pending["votes"], actual)

    result = {**pending, "exit_price": exit_price, "actual": actual, "pct": pct,
              "correct": correct if predicted else None}

    history = state.setdefault("history", [])
    history.append({
        "hour_start": pending.get("hour_start"),
        "hour_end": pending.get("hour_end"),
        "predicted": predicted,
        "n_up": pending.get("n_up"),
        "n_down": pending.get("n_down"),
        "entry_price": entry,
        "exit_price": exit_price,
        "actual": actual,
        "pct": round(pct, 3),
        "correct": result["correct"],
        "verified_at": datetime.now(_TZ_TR).isoformat(),
    })
    state["history"] = history[-168:]

    log = state.setdefault("votes_log", [])
    log.append({
        "hour_key": pending.get("hour_key"),
        "hour_start": pending.get("hour_start"),
        "hour_end": pending.get("hour_end"),
        "actual": actual,
        "votes": pending.get("votes", []),
        "verified_at": datetime.now(_TZ_TR).isoformat(),
    })
    state["votes_log"] = log[-168:]

    state["pending"] = None
    _save_state(state)
    return result


def _close_trader(exit_price: float, actual: str, hour_label: str) -> dict | None:
    """Önceki saatin sanal pozisyonunu kapat."""
    trader = _load_trader()
    hist   = _load_trader_hist()
    if not trader["open_positions"]:
        return None

    pos = trader["open_positions"].pop(0)
    pred = pos["predicted_dir"]
    amount = pos.get("amount", 10.0)
    win = pred == actual and actual != "FLAT"
    pnl = amount if win else -amount

    if win:
        trader["balance"] = round(trader["balance"] + amount * 2, 2)
    trader["total_pnl"] = round(trader.get("total_pnl", 0.0) + pnl, 2)

    record = {
        "symbol": SYMBOL,
        "predicted_dir": pred,
        "actual_dir": actual,
        "win": win,
        "entry_price": pos["entry_price"],
        "exit_price": exit_price,
        "entry_time_tr": pos.get("entry_time_tr"),
        "exit_time_tr": datetime.now(_TZ_TR).isoformat(),
        "hour_label": hour_label,
        "amount": amount,
        "n_win": pos.get("n_win"),
        "pnl": pnl,
    }
    hist.append(record)
    _save_trader(trader)
    _save_trader_hist(hist)
    return record


def _open_trader(predicted: str, n_win: int, entry_price: float,
                 hour_start: datetime, hour_end: datetime) -> dict | None:
    amount = _calc_amount(n_win)
    if amount <= 0 or entry_price is None:
        return None

    trader = _load_trader()
    if trader["balance"] < amount:
        print(f"[509] Yetersiz bakiye: ${trader['balance']:.2f} < ${amount:.0f}")
        return None
    if trader["open_positions"]:
        print("[509] Zaten açık pozisyon var, yeni açılmadı")
        return None

    now_tr = datetime.now(_TZ_TR)
    pos = {
        "symbol": SYMBOL,
        "predicted_dir": predicted,
        "entry_price": entry_price,
        "amount": amount,
        "n_win": n_win,
        "entry_time_tr": now_tr.isoformat(),
        "hour_start": hour_start.strftime("%H:%M"),
        "hour_end": hour_end.strftime("%H:%M"),
    }
    trader["open_positions"].append(pos)
    trader["balance"] = round(trader["balance"] - amount, 2)
    _save_trader(trader)
    return pos


def _format_prev_result(prev: dict | None, trade_close: dict | None) -> list[str]:
    if not prev:
        return []

    h0 = prev.get("hour_start", "??:??")
    h1 = prev.get("hour_end", "??:??")
    n_up = prev.get("n_up", 0)
    n_down = prev.get("n_down", 0)
    predicted = prev.get("predicted")
    actual = prev.get("actual", "?")
    entry = prev.get("entry_price")
    exit_p = prev.get("exit_price")
    pct = prev.get("pct", 0.0)

    if predicted == "UP":
        pred_txt = f"{n_up}/{TOTAL} ARTAR"
    elif predicted == "DOWN":
        pred_txt = f"{n_down}/{TOTAL} DÜŞER"
    else:
        pred_txt = f"{n_up}/{TOTAL} ARTAR = {n_down}/{TOTAL} DÜŞER"

    actual_txt = {"UP": "ARTAR", "DOWN": "DÜŞER", "FLAT": "YATAY"}.get(actual, actual)
    sign = "+" if pct >= 0 else ""

    lines = [f"⏪ <b>Önceki saat ({h0}–{h1})</b> → {pred_txt}"]

    if predicted is None:
        lines.append(f"   Gerçek: {actual_txt} ({sign}{pct:.2f}%)")
    elif actual == "FLAT":
        lines.append("   ⚪ YATAY")
    elif prev.get("correct"):
        lines.append(f"   ✅ <b>DOĞRU</b> — BTC {actual_txt}")
    else:
        lines.append(f"   ❌ <b>YANLIŞ</b> — BTC {actual_txt} oldu")

    if entry and exit_p:
        lines.append(f"   {_fmt_price(entry)} → {_fmt_price(exit_p)} ({sign}{pct:.2f}%)")

    scored = [h for h in _load_state().get("history", []) if h.get("correct") is not None]
    if scored:
        wins = sum(1 for h in scored if h["correct"])
        lines.append(f"   📈 Konsensüs: {wins}/{len(scored)} doğru")

    if trade_close:
        icon = "✅" if trade_close["win"] else "❌"
        pnl  = trade_close["pnl"]
        pnl_s = f"+${pnl:.0f}" if pnl >= 0 else f"-${abs(pnl):.0f}"
        trader = _load_trader()
        lines.append(f"   🤖 <b>{LABEL}</b>: {icon} {pnl_s}  |  Bakiye ${trader['balance']:,.0f}")

    lines.append("")
    return lines


def build_message(votes: list[dict], prev_result: dict | None,
                  trade_close: dict | None) -> str:
    now_tr = datetime.now(_TZ_TR)
    n_up   = sum(1 for v in votes if v["signal"] == "UP")
    n_down = sum(1 for v in votes if v["signal"] == "DOWN")
    n_neut = TOTAL - n_up - n_down
    predicted = _consensus_dir(n_up, n_down)

    if predicted == "UP":
        headline = f"🟢 <b>{n_up}/{TOTAL} BTC ARTAR</b>"
        n_win = n_up
    elif predicted == "DOWN":
        headline = f"🔴 <b>{n_down}/{TOTAL} BTC DÜŞER</b>"
        n_win = n_down
    else:
        headline = f"⚖️ <b>{n_up}/{TOTAL} ARTAR — {n_down}/{TOTAL} DÜŞER</b>"
        n_win = 0

    lines = [
        f"📊 <b>BTC ANALİZ</b> — {now_tr.strftime('%d.%m.%Y %H:%M')} İST",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    lines += _format_prev_result(prev_result, trade_close)
    lines.append("🔮 <b>Bu saat tahmini</b>")
    lines.append(headline)
    lines.append(f"🟢 {n_up}/{TOTAL} ARTAR  |  🔴 {n_down}/{TOTAL} DÜŞER  |  ⚪ {n_neut}/{TOTAL} NÖTR")

    trader = _load_trader()
    if predicted and n_win >= MIN_TRADE_VOTES:
        amt = _calc_amount(n_win)
        d = "ARTAR" if predicted == "UP" else "DÜŞER"
        lines.append(f"🤖 <b>{LABEL}</b>: {d} ${amt:.0f} — :02 sanal açılış")
    elif not predicted:
        lines.append(f"🤖 <b>{LABEL}</b>: berabere — işlem yok")

    total_pnl = trader.get("total_pnl", 0.0)
    pnl_icon = "🟢" if total_pnl >= 0 else "🔴"
    at_risk = sum(p.get("amount", 0) for p in trader.get("open_positions", []))
    lines.append(
        f"💰 Bakiye: ${trader['balance']:,.0f}  |  "
        f"Açık: ${at_risk:.0f}  |  {pnl_icon} P&L: {'+' if total_pnl >= 0 else ''}{total_pnl:.0f}$"
    )

    return "\n".join(lines)


def print_algo_stats(min_total: int = 1) -> None:
    """Kayıtlı algo/trader başarı sıralaması."""
    state = _load_state()
    stats = state.get("algo_stats", {})
    if not stats:
        print("Henüz algo istatistiği yok.")
        return

    rows = []
    for vid, s in stats.items():
        if s.get("total", 0) < min_total:
            continue
        wr = s["correct"] / s["total"] * 100
        rows.append((wr, s["correct"], s["total"], vid, s.get("name", vid)))

    rows.sort(reverse=True)
    print(f"\n{'ID':<6} {'İsim':<40} {'Doğru':>8} {'WR':>8}")
    print("-" * 66)
    for wr, c, t, vid, name in rows:
        print(f"{vid:<6} {name[:40]:<40} {c}/{t:<5} %{wr:.0f}")


async def run_async(*, send_tg: bool = True) -> list[dict]:
    state = _load_state()
    prev_result = _verify_previous(state)

    trade_close = None
    if prev_result and prev_result.get("exit_price") is not None:
        hour_label = f"{prev_result.get('hour_start')}–{prev_result.get('hour_end')}"
        trade_close = _close_trader(
            prev_result["exit_price"],
            prev_result.get("actual", "FLAT"),
            hour_label,
        )

    print(f"[BTC ANALİZ] {TOTAL} aktif oy hesaplanıyor...")
    algo_votes = collect_btc_algo_votes()
    print("[BTC ANALİZ] trader oyları...")
    trader_votes = await _collect_trader_votes()
    votes = _filter_votes(algo_votes + trader_votes)

    if len(votes) != TOTAL:
        print(f"[BTC ANALİZ] UYARI: {len(votes)} oy (beklenen {TOTAL})")

    n_up = sum(1 for v in votes if v["signal"] == "UP")
    n_down = sum(1 for v in votes if v["signal"] == "DOWN")
    now_tr = datetime.now(_TZ_TR)
    hour_start = now_tr.replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)
    entry_price = _hour_entry_price()
    predicted = _consensus_dir(n_up, n_down)
    n_win = n_up if predicted == "UP" else n_down if predicted == "DOWN" else 0

    state = _load_state()
    state["pending"] = {
        "hour_start": hour_start.strftime("%H:%M"),
        "hour_end": hour_end.strftime("%H:%M"),
        "hour_key": hour_start.strftime("%Y-%m-%dT%H:%M"),
        "predicted": predicted,
        "n_up": n_up,
        "n_down": n_down,
        "n_neut": TOTAL - n_up - n_down,
        "entry_price": entry_price,
        "votes": votes,
        "saved_at": now_tr.isoformat(),
    }
    if predicted and n_win >= MIN_TRADE_VOTES:
        state["trade_pending"] = {
            "predicted": predicted,
            "n_win": n_win,
            "hour_start": hour_start.strftime("%H:%M"),
            "hour_end": hour_end.strftime("%H:%M"),
            "hour_key": hour_start.strftime("%Y-%m-%dT%H:%M"),
        }
    else:
        state["trade_pending"] = None
    _save_state(state)

    msg = build_message(votes, prev_result, trade_close)
    print(msg.replace("<b>", "").replace("</b>", ""))

    if send_tg:
        tg_send(msg)
        print("[BTC ANALİZ] Telegram gönderildi.")
    return votes


def run_open(*, send_tg: bool = True) -> dict | None:
    """:02 — kayıtlı sinyale göre sanal işlem aç."""
    state = _load_state()
    tp = state.get("trade_pending")
    if not tp:
        print("[509] Açılacak sinyal yok")
        return None

    hour_key = tp.get("hour_key")
    if state.get("trade_opened_key") == hour_key:
        print(f"[509] {hour_key} zaten açılmış")
        return None

    now_tr = datetime.now(_TZ_TR)
    hour_start = now_tr.replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)
    entry_price = _hour_entry_price()

    pos = _open_trader(
        tp["predicted"], tp["n_win"], entry_price, hour_start, hour_end,
    )
    if pos:
        state["trade_opened_key"] = hour_key
        state["trade_pending"] = None
        _save_state(state)
        d = "ARTAR" if pos["predicted_dir"] == "UP" else "DÜŞER"
        trader = _load_trader()
        msg = (
            f"🤖 <b>{LABEL}</b> — {now_tr.strftime('%H:%M')} İST\n"
            f"{d} ${pos['amount']:.0f} sanal açıldı\n"
            f"💰 Bakiye: ${trader['balance']:,.0f}  |  Açık: ${pos['amount']:.0f}"
        )
        print(msg.replace("<b>", "").replace("</b>", ""))
        if send_tg:
            tg_send(msg)
    else:
        print("[509] İşlem açılamadı")
    return pos


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        min_t = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        print_algo_stats(min_t)
        return
    send = "--no-tg" not in sys.argv
    if len(sys.argv) > 1 and sys.argv[1] == "open":
        run_open(send_tg=send)
        return
    asyncio.run(run_async(send_tg=send))


if __name__ == "__main__":
    main()
