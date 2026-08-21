#!/usr/bin/env python3
"""KAITO kağıt defteri — Algoritmalar Live'ın (cr6) kararlarını gerçek para olmadan ölçer.

Neden var
─────────
Kripto Test'te 30 coinin 29'u zararda, tek pozitif olan KAITO (+$1.272). Bu
rakama bakıp canlıda KAITO açmak cazip görünüyor, ama ölçüm kenar olmadığını
söylüyor:

  · gün kümelenmiş t = +0,76 — sıfırdan ayırt edilemez (9 gün)
  · 13.08 tek günü +$1.348, yani toplam kârın tamamından fazla; 12.08 −$646
  · en iyi 5 işlem kârın %63'ü, en iyi 20 işlem %152 (gerisi eksi)
  · LONG −$1.897 (WR %34,2) · SHORT +$3.169 (WR %60,7)
  · KAITO aynı pencerede 0,91 → 0,35 (−%61,3), neredeyse her gün eksi

Yani "KAITO kârlı" değil, "çakılan bir coine çoğunlukla short kalınmış". Ayrıca
o rakam **Kripto Test** defterlerinden ($100×6x, 69 defter); canlı cr6 bambaşka
bir strateji (4 algo çoğunluk oyu, $7×20x). Test sonucu cr6'yı tahmin etmiyor.

Bu defter o boşluğu kapatır: cr6'nın KAITO'da **ne yapacağını** kaydeder,
sonucu ölçer, kasa riske girmez.

Ne kadar birebir
────────────────
cr6 ile aynı: 4 defterin oyu (`algo_05` · `algo_06` · `algo_07` · `algo1_11`),
`_combine_votes` (çakışmada NEUTRAL), `conviction_filter` vetosu (4/4 oy birliği
açılmaz), $7×20x, ATR kâr kilidi + `exit_policy` (24s tavan · 3×ATR stop),
Binance'ten çekilen gerçek taker komisyonu (giriş + çıkış).

Farklar (bilerek): tek pozisyon (cr6'da top_n paylaşımlı), emir defteri yok —
giriş/çıkış mum kapanışından, yani gerçek kayma (slippage) yok. Sonuç bu yüzden
**iyimser taraflı** okunmalı.

Güvenlik
────────
Bu dosyada **hiçbir kod yolu emir fonksiyonu çağırmaz** (`open_market` /
`open_maker` / `close_position` burada geçmez); tüm giriş-çıkış `_settle` ve
`run_open` içinde yalnız JSON'a yazılır. Ayrıca KAITO, cr6'nın canlı evreni
`FG_SYMBOLS`'te **yok** — cr6 yanlışlıkla açılsa bile bu sembole giremez.
Not: `crypto_futures_cr6` import edildiği için `crypto_futures_trader` da
dolaylı olarak yüklenir (oy mantığı tek kaynaktan gelsin diye bilerek); yüklü
olması çağrıldığı anlamına gelmez.

Modlar:  open (:05) · trail (*/2) · close (:02) · stats
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import crypto_futures_cr6 as CR6  # noqa: E402  (sys.path'i kendisi kurar)
import conviction_filter  # noqa: E402
from algo_signals import fetch_klines  # noqa: E402
from atr_profit_lock import (  # noqa: E402
    atr_from_klines,
    init_lock_fields,
    lock_summary,
    should_loss_stop,
    should_stop_out,
    update_lock,
)
from catalog import signal_for_book  # noqa: E402
from exit_policy import policy_for  # noqa: E402
from fee_utils import estimate_fee, get_taker_rate  # noqa: E402

_TZ_TR = ZoneInfo("Europe/Istanbul")
SYMBOL = "KAITOUSDT"
LABEL = "KAITO Kağıt"
GROUP = "Algoritmalar"
MARGIN_USD = CR6.MARGIN_USD
LEVERAGE = CR6.LEVERAGE
START_BALANCE = 300.0

STATE_FILE = os.path.join(_DIR, "kaito_paper_state.json")
HISTORY_FILE = os.path.join(_DIR, "kaito_paper_history.json")
SHADOW_FILE = os.path.join(_DIR, "kaito_paper_shadow.jsonl")


# ── durum ────────────────────────────────────────────────────────────
def _load(path: str, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _save(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _state() -> dict:
    st = _load(STATE_FILE, {})
    st.setdefault("balance", START_BALANCE)
    st.setdefault("init_balance", START_BALANCE)
    st.setdefault("position", None)
    st.setdefault("created_at_tr", datetime.now(_TZ_TR).isoformat())
    return st


def _shadow(row: dict) -> None:
    """Açılan ve açılmayan her turu kaydet — 'neden işlem yok' sorusu cevaplanabilsin."""
    try:
        with open(SHADOW_FILE, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[{LABEL}] gölge günlüğü yazılamadı: {e}", file=sys.stderr)


# ── sinyal ───────────────────────────────────────────────────────────
def _consensus(klines: list[dict]) -> dict:
    """cr6 ile birebir: 4 defterin oyu → tek yön."""
    kmap = {SYMBOL: klines}
    votes = []
    for book in CR6.LIVE_BOOKS:
        try:
            s = (signal_for_book(book, kmap) or {}).get(SYMBOL) or "NEUTRAL"
        except Exception as e:
            print(f"[{LABEL}] {book['book_key']} sinyal hatası: {e}", file=sys.stderr)
            s = "NEUTRAL"
        votes.append((book["book_key"], s))
    active = [(k, s) for k, s in votes if s in ("UP", "DOWN")]
    sig, agree, contrib = CR6._combine_votes(active)
    return {
        "symbol": SYMBOL,
        "signal": sig,
        "agree": agree,
        "contributors": contrib,
        "votes": dict(votes),
        "price": float(klines[-1]["c"]),
        "score": 1.0 + max(0, agree - 1) * 0.5 if sig != "NEUTRAL" else 0.0,
    }


def _upnl(pos: dict, mark: float) -> tuple[float, float]:
    """(brüt upnl, giriş komisyonu). Notional = margin × kaldıraç."""
    entry = float(pos["entry_price"])
    qty = float(pos["qty"])
    gross = (mark - entry) * qty if pos["side"] == "LONG" else (entry - mark) * qty
    return gross, float(pos.get("entry_fee") or 0)


# ── modlar ───────────────────────────────────────────────────────────
def run_open() -> None:
    st = _state()
    now = datetime.now(_TZ_TR)
    slot = now.strftime("%Y-%m-%d %H:00")

    if st["position"]:
        print(f"[{LABEL}] açık pozisyon var, yeni açılmaz")
        return

    kl = fetch_klines(SYMBOL, "1h", 80)
    if len(kl) < 30:
        print(f"[{LABEL}] yetersiz mum ({len(kl)})")
        return
    cand = _consensus(kl)
    base = {"ts_tr": now.isoformat(), "slot": slot, "price": cand["price"],
            "signal": cand["signal"], "agree": cand["agree"],
            "votes": cand["votes"]}

    if cand["signal"] == "NEUTRAL":
        print(f"[{LABEL}] {slot} — NEUTRAL (oylar: {cand['votes']}), işlem yok")
        _shadow({**base, "opened": False, "reason": "neutral"})
        return

    verdict = conviction_filter.evaluate(
        cand, total_books=len(CR6.LIVE_BOOKS), cfg=conviction_filter.load_config()
    )
    if verdict["veto"]:
        print(f"[{LABEL}] {slot} — VETO: {verdict['reason']}")
        _shadow({**base, "opened": False, "reason": f"veto: {verdict['reason']}"})
        return

    price = cand["price"]
    side = "LONG" if cand["signal"] == "UP" else "SHORT"
    notional = MARGIN_USD * LEVERAGE
    qty = notional / price
    rate = get_taker_rate(SYMBOL)
    entry_fee = estimate_fee(notional, rate)
    atr = atr_from_klines(kl)
    pol = policy_for(GROUP)

    pos = {
        "symbol": SYMBOL, "side": side,
        "entry_price": price, "qty": qty,
        "entry_time_tr": now.isoformat(), "entry_slot": slot,
        "margin_usd": MARGIN_USD, "leverage": LEVERAGE,
        "notional": notional, "entry_fee": entry_fee, "taker_rate": rate,
        "algo": "+".join(cand["contributors"]),
        "agree": cand["agree"], "votes": cand["votes"],
        "max_hold_h": pol.get("max_hold_h"),
    }
    if pol.get("loss_stop_atr") is not None:
        pos["loss_stop_atr"] = float(pol["loss_stop_atr"])
    pos = init_lock_fields(pos, atr=atr, margin_usd=MARGIN_USD,
                           leverage=LEVERAGE, price=price)
    st["position"] = pos
    _save(STATE_FILE, st)
    _shadow({**base, "opened": True, "side": side, "reason": "açıldı"})
    print(f"[{LABEL}] {slot} AÇILDI {side} @ {price:.4f} · {cand['agree']} oy "
          f"({pos['algo']}) · atr$ {pos['atr_usd']:.2f} · komisyon ${entry_fee:.4f}")


def _settle(st: dict, pos: dict, mark: float, reason: str) -> None:
    gross, entry_fee = _upnl(pos, mark)
    exit_fee = estimate_fee(float(pos["notional"]), float(pos.get("taker_rate") or 0))
    fee = entry_fee + exit_fee
    net = gross - fee
    now = datetime.now(_TZ_TR)
    hist = _load(HISTORY_FILE, [])
    hist.append({
        **{k: pos[k] for k in ("symbol", "side", "entry_price", "qty",
                               "entry_time_tr", "algo", "agree", "margin_usd",
                               "leverage")},
        "exit_price": mark, "exit_time_tr": now.isoformat(),
        "close_reason": reason,
        "pnl_gross": round(gross, 4), "fee_usd": round(fee, 4),
        "pnl": round(net, 4), "win": net > 0,
        "pnl_pct": round(100 * net / float(pos["margin_usd"]), 2),
        "hold_h": round(
            (now - datetime.fromisoformat(pos["entry_time_tr"])).total_seconds() / 3600, 2
        ),
        "stop_level": int(pos.get("stop_level") or 0),
    })
    _save(HISTORY_FILE, hist)
    st["balance"] = round(float(st["balance"]) + net, 4)
    st["position"] = None
    _save(STATE_FILE, st)
    print(f"[{LABEL}] KAPANDI {pos['side']} {pos['entry_price']:.4f} → {mark:.4f} "
          f"· {reason} · brüt ${gross:+.2f} komisyon ${fee:.2f} net ${net:+.2f} "
          f"· bakiye ${st['balance']:.2f}")


def run_trail() -> None:
    st = _state()
    pos = st["position"]
    if not pos:
        return
    kl = fetch_klines(SYMBOL, "1h", 3)
    if not kl:
        return
    mark = float(kl[-1]["c"])
    gross, entry_fee = _upnl(pos, mark)
    upnl_net = gross - entry_fee
    now = datetime.now(_TZ_TR)

    pos, changed = update_lock(pos, upnl_net, ts=now.isoformat(), mark=mark)
    if changed:
        st["position"] = pos
        _save(STATE_FILE, st)
        s = lock_summary(pos)
        print(f"[{LABEL}] kilit seviye {s['stop_level']} · stop ${s['stop_upnl']:.2f}")

    if should_stop_out(pos, upnl_net):
        _settle(st, pos, mark, "atr_stop")
        return
    if should_loss_stop(pos, upnl_net):
        _settle(st, pos, mark, "loss_stop")
        return

    mh = pos.get("max_hold_h")
    if mh:
        age = (now - datetime.fromisoformat(pos["entry_time_tr"])).total_seconds() / 3600
        if age >= float(mh):
            _settle(st, pos, mark, "max_hold")


def run_close() -> None:
    """Saatlik tur — yeni rejimde zaman kapanışı yok, yalnız süre tavanı ve stoplar."""
    run_trail()
    st = _state()
    if not st["position"]:
        print(f"[{LABEL}] close: açık yok")
    else:
        p = st["position"]
        kl = fetch_klines(SYMBOL, "1h", 2)
        mark = float(kl[-1]["c"]) if kl else float(p["entry_price"])
        gross, ef = _upnl(p, mark)
        print(f"[{LABEL}] close: tutuluyor {p['side']} @ {p['entry_price']:.4f} "
              f"· şu an {mark:.4f} · upnl ${gross - ef:+.2f}")


def run_stats() -> None:
    st = _state()
    hist = _load(HISTORY_FILE, [])
    blk = paper_status_block(refresh_price=False)
    print(f"{LABEL} — {SYMBOL} · ${MARGIN_USD:g}×{LEVERAGE}x · cr6 kararları, gerçek para yok")
    print(f"  bakiye ${blk['balance']:.2f} / ${blk['init_balance']:.2f}  "
          f"(kuruluş {blk['created_at_tr'][:16]})")
    if not hist:
        print("  henüz kapanmış işlem yok")
    else:
        n = blk["trade_count"]
        print(f"  {n} işlem · WR %{blk['win_rate']:.1f} · net ${blk['total_pnl']:+.2f} "
              f"· brüt ${blk['total_gross']:+.2f} · komisyon ${blk['total_fee']:.2f}")
        for side in ("LONG", "SHORT"):
            g = [t for t in hist if t["side"] == side]
            if g:
                gw = sum(1 for t in g if t["win"])
                print(f"    {side}: n={len(g)} WR %{100 * gw / len(g):.1f} "
                      f"net ${sum(t['pnl'] for t in g):+.2f}")
        reasons: dict[str, int] = {}
        for t in hist:
            reasons[t["close_reason"]] = reasons.get(t["close_reason"], 0) + 1
        print(f"    kapanış sebepleri: {reasons}")
    if st["position"]:
        p = st["position"]
        print(f"  AÇIK: {p['side']} @ {p['entry_price']:.4f} "
              f"({p['entry_time_tr'][:16]}) · {p['agree']} oy")
    if blk.get("shadow_skipped"):
        print(f"  gölge: {blk['shadow_count']} tur · açılmayanlar {blk['shadow_skipped']}")


def paper_status_block(*, refresh_price: bool = True) -> dict:
    """Dashboard / API için özet blok."""
    st = _state()
    hist = _load(HISTORY_FILE, [])
    net = sum(float(t.get("pnl") or 0) for t in hist)
    fee = sum(float(t.get("fee_usd") or 0) for t in hist)
    n = len(hist)
    wins = sum(1 for t in hist if t.get("win"))

    pos = st.get("position")
    card = None
    mark = None
    current_signal = None

    if refresh_price:
        try:
            kl = fetch_klines(SYMBOL, "1h", 80)
            if kl:
                mark = float(kl[-1]["c"])
                if len(kl) >= 30:
                    current_signal = _consensus(kl)
        except Exception:
            pass

    if pos and mark is not None:
        gross, entry_fee = _upnl(pos, mark)
        upnl_net = gross - entry_fee
        lock = lock_summary(pos)
        card = {
            "symbol": SYMBOL,
            "name": "KAITO",
            "side": pos.get("side"),
            "entry_price": float(pos.get("entry_price") or 0),
            "current": mark,
            "unrealized_pnl": round(upnl_net, 4),
            "unrealized_pnl_gross": round(gross, 4),
            "entry_time_tr": pos.get("entry_time_tr"),
            "algo": pos.get("algo"),
            "agree": pos.get("agree"),
            "atr_usd": pos.get("atr_usd"),
            "lock_armed": bool(lock.get("armed")),
            "stop_level": int(lock.get("stop_level") or 0),
            "stop_upnl": lock.get("stop_upnl"),
        }

    last_shadow = None
    shadow_count = 0
    shadow_skipped: dict[str, int] = {}
    if os.path.exists(SHADOW_FILE):
        try:
            rows = [json.loads(x) for x in open(SHADOW_FILE) if x.strip()]
            shadow_count = len(rows)
            for r in rows:
                if not r.get("opened"):
                    reason = str(r.get("reason") or "?")
                    shadow_skipped[reason] = shadow_skipped.get(reason, 0) + 1
            if rows:
                last_shadow = rows[-1]
        except Exception:
            pass

    recent = []
    for t in list(reversed(hist))[:8]:
        recent.append({
            "symbol": t.get("symbol"),
            "name": "KAITO",
            "side": t.get("side"),
            "algo": t.get("algo"),
            "pnl": t.get("pnl"),
            "pnl_gross": t.get("pnl_gross"),
            "fee_usd": t.get("fee_usd"),
            "exit_time_tr": t.get("exit_time_tr"),
            "close_reason": t.get("close_reason"),
            "win": t.get("win"),
        })

    return {
        "ok": True,
        "label": LABEL,
        "paper": True,
        "symbol": SYMBOL,
        "margin_usd": MARGIN_USD,
        "leverage": LEVERAGE,
        "balance": round(float(st.get("balance") or START_BALANCE), 4),
        "init_balance": round(float(st.get("init_balance") or START_BALANCE), 4),
        "total_pnl": round(net, 4),
        "total_fee": round(fee, 4),
        "total_gross": round(net + fee, 4),
        "trade_count": n,
        "win_rate": round(100 * wins / n, 1) if n else None,
        "open_count": 1 if pos else 0,
        "open_position": pos,
        "card": card,
        "current_price": mark,
        "current_signal": current_signal,
        "last_shadow": last_shadow,
        "shadow_count": shadow_count,
        "shadow_skipped": shadow_skipped,
        "recent_trades": recent,
        "created_at_tr": st.get("created_at_tr"),
        "updated_at_tr": datetime.now(_TZ_TR).isoformat(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{LABEL} — sanal, gerçek emir yok")
    ap.add_argument("cmd", choices=["open", "close", "trail", "stats"])
    args = ap.parse_args()
    {"open": run_open, "close": run_close,
     "trail": run_trail, "stats": run_stats}[args.cmd]()


if __name__ == "__main__":
    main()
