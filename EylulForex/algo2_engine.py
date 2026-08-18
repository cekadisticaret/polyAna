"""Algoritma 2 — 13 katmanlı XAUUSD karar motoru (sanal).

Grafik 1 Kalman/tick yolundan bağımsız. Aynı kotasyon, ayrı defter (`book=a2`).
Gerçek broker emri yok — yalnız paper `apply_signal`.
"""
from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from confluence_signal_engine import ConfluenceEngine, EngineConfig, _atr

_DIR = Path(__file__).resolve().parent
_DATA = _DIR / "data"
_STAB = _DATA / "algo2_stab.json"
_JOURNAL = _DATA / "algo2_journal.jsonl"
_BACKTEST = _DATA / "algo2_backtest.json"
_TZ = ZoneInfo("Europe/Istanbul")

SCORE_MIN = 64.0
MTF_MIN = 2
SPREAD_HARD = 0.80
SPREAD_SOFT = 0.50
VOLATILE_ATR_PCT = 80.0
RANGE_ATR_PCT = 25.0
STAB_N = 2

_SIG_CFG = EngineConfig(
    shadow_log_path="/dev/null",
    weight_trend=40.0,
    weight_momentum=40.0,
    weight_pattern=20.0,
    weight_tick=0.0,
    signal_threshold=50.0,
    stability_window=1,
)

_WEIGHTS = {
    1: 18.0, 2: 8.0, 3: 16.0, 4: 12.0, 5: 8.0, 6: 12.0,
    7: 12.0, 8: 6.0, 9: 4.0, 10: 2.0, 11: 2.0, 12: 0.0,
}

_live_cache: tuple[float, dict] | None = None
_LIVE_TTL = 2.5


def _clip(x: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, x)))


def rows_to_df(rows: list[dict] | None) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return pd.DataFrame({
        "open": [float(c["open"]) for c in rows],
        "high": [float(c["high"]) for c in rows],
        "low": [float(c["low"]) for c in rows],
        "close": [float(c["close"]) for c in rows],
        "volume": [float(c.get("volume") or 0) for c in rows],
    })


def _now() -> datetime:
    return datetime.now(_TZ)


def _item(n: int, name: str, score: float, vote: str, reason: str,
          hard: bool = False, ok: bool | None = None) -> dict:
    sc = round(float(score), 1)
    passed = bool(ok) if ok is not None else sc >= 50.0
    return {
        "id": n,
        "name": name,
        "score": sc,
        "vote": vote,
        "ok": passed,
        "hard": hard,
        "reason": reason,
    }


def _ema_vote(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> tuple[str, float]:
    if df is None or len(df) < 20:
        return "NEUTRAL", 0.0
    close = df["close"]
    ema_f = close.ewm(span=fast, adjust=False).mean()
    span_s = slow if len(close) >= slow else fast
    ema_s = close.ewm(span=span_s, adjust=False).mean()
    last = float(close.iloc[-1])
    f, s = float(ema_f.iloc[-1]), float(ema_s.iloc[-1])
    if s == 0:
        return "NEUTRAL", 0.0
    spread = (f - s) / abs(s) * 100.0
    mag = _clip(abs(spread) * 500.0, 0, 100)
    if last > f > s:
        return "UP", mag
    if last < f < s:
        return "DOWN", mag
    if last > f:
        return "UP", max(28.0, mag * 0.45)
    if last < f:
        return "DOWN", max(28.0, mag * 0.45)
    return "NEUTRAL", 0.0


def _structure(df: pd.DataFrame) -> tuple[str, str]:
    """Son salınımlar: HH/HL = UP, LH/LL = DOWN."""
    if df is None or len(df) < 16:
        return "NEUTRAL", "yetersiz mum"
    hi = df["high"].to_numpy(dtype=float)
    lo = df["low"].to_numpy(dtype=float)
    w = 3
    swings_h, swings_l = [], []
    for i in range(w, len(hi) - w):
        if hi[i] == max(hi[i - w:i + w + 1]):
            swings_h.append(hi[i])
        if lo[i] == min(lo[i - w:i + w + 1]):
            swings_l.append(lo[i])
    if len(swings_h) < 2 or len(swings_l) < 2:
        return "NEUTRAL", "salınım yok"
    hh = swings_h[-1] > swings_h[-2]
    hl = swings_l[-1] > swings_l[-2]
    lh = swings_h[-1] < swings_h[-2]
    ll = swings_l[-1] < swings_l[-2]
    if hh and hl:
        return "UP", "HH + HL"
    if lh and ll:
        return "DOWN", "LH + LL"
    if hh or hl:
        return "UP", "karışık yükseliş"
    if lh or ll:
        return "DOWN", "karışık düşüş"
    return "NEUTRAL", "yatay yapı"


def _sweep(df: pd.DataFrame) -> tuple[str, str, float]:
    if df is None or len(df) < 12:
        return "NEUTRAL", "süpürme yok", 40.0
    look = df.tail(21)
    prev_hi = float(look["high"].iloc[:-1].max())
    prev_lo = float(look["low"].iloc[:-1].min())
    last = look.iloc[-1]
    hi, lo, cl = float(last["high"]), float(last["low"]), float(last["close"])
    atr = _atr(df, 14)
    pad = float(atr.iloc[-1]) * 0.15 if len(atr) and not np.isnan(atr.iloc[-1]) else 0.20
    if hi > prev_hi + pad and cl < prev_hi:
        return "DOWN", f"üst likidite süpürüldü ({hi:.2f}→kapanış {cl:.2f})", 78.0
    if lo < prev_lo - pad and cl > prev_lo:
        return "UP", f"alt likidite süpürüldü ({lo:.2f}→kapanış {cl:.2f})", 78.0
    return "NEUTRAL", "tuzak yok", 48.0


def _session(now: datetime | None = None) -> tuple[str, float, str, bool]:
    """Seans skoru. COMEX molası (00:00–01:00 İST) sert kapı."""
    t = now or _now()
    h, m = t.hour, t.minute
    hm = h * 60 + m
    if 0 <= hm < 60:
        return "comex_break", 18.0, "COMEX molası — kotasyon donabilir", True
    if 60 <= hm < 8 * 60:
        return "asia", 55.0, "Asya seansı", False
    if 8 * 60 <= hm < 12 * 60:
        return "london", 82.0, "Londra", False
    if 12 * 60 <= hm < 16 * 60:
        return "overlap", 94.0, "Londra/NY örtüşmesi", False
    if 16 * 60 <= hm < 21 * 60:
        return "ny", 80.0, "New York", False
    return "after", 42.0, "seans sonrası", False


def _news_window(now: datetime | None = None) -> tuple[bool, str]:
    """Haber akışı yok — bilinen altın saatlerinde yumuşak uyarı."""
    t = now or _now()
    hm = t.hour * 60 + t.minute
    windows = (
        (10 * 60, 10 * 60 + 20, "AB veri penceresi"),
        (15 * 60 + 25, 16 * 60 + 5, "ABD 08:30 ET penceresi"),
    )
    for a, b, lab in windows:
        if a <= hm <= b:
            return True, lab
    return False, "haber bandı dışı"


def _atr_pct(df: pd.DataFrame) -> tuple[float, float]:
    if df is None or len(df) < 20:
        return 0.0, 50.0
    atr = _atr(df, 14).dropna()
    if atr.empty:
        return 0.0, 50.0
    last = float(atr.iloc[-1])
    hist = atr.tail(80).to_numpy(dtype=float)
    pct = float((hist < last).mean() * 100.0)
    return last, pct


def _load_stab() -> deque:
    try:
        raw = json.loads(_STAB.read_text(encoding="utf-8"))
        dirs = [d for d in (raw.get("dirs") or []) if d in ("UP", "DOWN", "NEUTRAL")]
        return deque(dirs[-STAB_N:], maxlen=STAB_N)
    except (OSError, json.JSONDecodeError, TypeError):
        return deque(maxlen=STAB_N)


def _save_stab(hist: deque) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    _STAB.write_text(json.dumps({"dirs": list(hist), "ts": time.time()}), encoding="utf-8")


def _perf_stats() -> dict:
    try:
        from forex_book import snapshot
        book = snapshot(book="a2")
    except Exception:
        return {"n": 0, "wr": None, "pnl": 0.0}
    hist = book.get("history") or []
    n = len(hist)
    if not n:
        return {"n": 0, "wr": None, "pnl": float(book.get("total_pnl") or 0)}
    wins = sum(1 for t in hist if float(t.get("pnl") or 0) > 0)
    return {
        "n": n,
        "wr": round(100.0 * wins / n, 1),
        "pnl": float(book.get("total_pnl") or 0),
        "open": int(book.get("open_count") or 0),
        "balance": float(book.get("balance") or 0),
    }


def _backtest_stats() -> dict:
    if not _BACKTEST.exists():
        return {"ok": False, "n": 0}
    try:
        return json.loads(_BACKTEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "n": 0}


def _journal(rec: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    rec = dict(rec)
    rec["ts"] = _now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        if _JOURNAL.exists():
            last = _JOURNAL.read_text(encoding="utf-8").splitlines()
            if last:
                prev = json.loads(last[-1])
                if prev.get("ts", "")[:16] == rec["ts"][:16] and prev.get("direction") == rec.get("direction"):
                    return
        with _JOURNAL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def evaluate(
    m1: pd.DataFrame,
    m5: pd.DataFrame,
    m15: pd.DataFrame,
    h1: pd.DataFrame,
    quote: dict | None = None,
    levels: dict | None = None,
    persist: bool = False,
    now: datetime | None = None,
    stab_hist: deque | None = None,
) -> dict:
    quote = quote or {}
    now = now or _now()
    items: list[dict] = []

    # 1) Sinyal — trend / momentum / formasyon (Kalman+VWAP, tick yok)
    sig_engine = ConfluenceEngine(_SIG_CFG)
    raw = sig_engine.compute(m5 if len(m5) >= 20 else m1, h1 if len(h1) >= 20 else m15)
    layers = raw.layer_scores or {}
    sig_dir = raw.direction if raw.direction in ("UP", "DOWN") else (
        "UP" if raw.raw_score > 8 else "DOWN" if raw.raw_score < -8 else "NEUTRAL"
    )
    items.append(_item(
        1, "Sinyal", min(100.0, abs(raw.raw_score)), sig_dir,
        f"trend {layers.get('trend', 0):+.0f} · Kalman {layers.get('momentum', 0):+.0f} · formasyon {layers.get('pattern', 0):+.0f}",
    ))

    # 2) Rejim
    atr_last, atr_pct = _atr_pct(m5 if len(m5) >= 20 else m1)
    h1_vote, _ = _ema_vote(h1)
    if atr_pct >= VOLATILE_ATR_PCT:
        regime, rscore, rwhy = "volatile", 35.0, f"ATR %{atr_pct:.0f} — aşırı volatil"
    elif atr_pct <= RANGE_ATR_PCT:
        regime, rscore, rwhy = "range", 48.0, f"ATR %{atr_pct:.0f} — dar bant"
    elif h1_vote in ("UP", "DOWN"):
        regime, rscore, rwhy = "trend", 78.0, f"H1 {h1_vote} · ATR %{atr_pct:.0f}"
    else:
        regime, rscore, rwhy = "range", 52.0, f"H1 nötr · ATR %{atr_pct:.0f}"
    items.append(_item(2, "Rejim", rscore, h1_vote if regime == "trend" else "NEUTRAL", rwhy))

    # 3) Çoklu zaman dilimi
    votes = {}
    for tf, df in (("5m", m5), ("15m", m15), ("1h", h1)):
        votes[tf] = _ema_vote(df)
    dirs = [v[0] for v in votes.values() if v[0] in ("UP", "DOWN")]
    up_n = dirs.count("UP")
    dn_n = dirs.count("DOWN")
    if up_n >= 2 and up_n > dn_n:
        mtf_dir, mtf_sc = "UP", 50.0 + 20.0 * up_n
    elif dn_n >= 2 and dn_n > up_n:
        mtf_dir, mtf_sc = "DOWN", 50.0 + 20.0 * dn_n
    else:
        mtf_dir, mtf_sc = "NEUTRAL", 30.0
    items.append(_item(
        3, "MTF", min(100.0, mtf_sc), mtf_dir,
        f"M5 {votes['5m'][0]} · M15 {votes['15m'][0]} · H1 {votes['1h'][0]}",
    ))

    # 4) Destek / direnç + yapı
    struct_dir, struct_why = _structure(m5 if len(m5) >= 16 else m1)
    mid = float(quote.get("mid") or (m1["close"].iloc[-1] if len(m1) else 0) or 0)
    sup = ((levels or {}).get("nearest_support") or {}).get("price")
    res = ((levels or {}).get("nearest_resistance") or {}).get("price")
    sr_vote, sr_sc, sr_why = struct_dir, 45.0, struct_why
    if mid and sup and res:
        band = max(float(res) - float(sup), 0.01)
        dist_s = (mid - float(sup)) / band
        dist_r = (float(res) - mid) / band
        if dist_s <= 0.22:
            sr_vote, sr_sc, sr_why = "UP", 76.0, f"desteğe yakın ({sup:.2f}) · {struct_why}"
        elif dist_r <= 0.22:
            sr_vote, sr_sc, sr_why = "DOWN", 76.0, f"dirence yakın ({res:.2f}) · {struct_why}"
        else:
            sr_sc, sr_why = 42.0, f"orta bant · {struct_why}"
    elif not (sup and res):
        sr_sc, sr_why = 28.0, "seviye yok"
    items.append(_item(4, "S/R + yapı", sr_sc, sr_vote, sr_why))

    # 5) Likidite süpürmesi
    sw_dir, sw_why, sw_sc = _sweep(m5 if len(m5) >= 12 else m1)
    items.append(_item(5, "Likidite", sw_sc, sw_dir, sw_why))

    # 6) Filtreler
    spread = float(quote.get("spread") or 0.30)
    sess, sess_sc, sess_why, sess_hard = _session(now)
    news, news_lab = _news_window(now)
    filt_hard = False
    filt_bits = [sess_why, f"spread {spread:.2f}"]
    filt_sc = sess_sc
    if spread >= SPREAD_HARD:
        filt_hard = True
        filt_sc = min(filt_sc, 20.0)
        filt_bits.append("spread sert kapı")
    elif spread >= SPREAD_SOFT:
        filt_sc = min(filt_sc, 48.0)
        filt_bits.append("spread geniş")
    if news:
        filt_sc = min(filt_sc, 40.0)
        filt_bits.append(news_lab)
    if sess_hard:
        filt_hard = True
    if atr_last and atr_last < 0.35:
        filt_sc = min(filt_sc, 44.0)
        filt_bits.append(f"ATR düşük ({atr_last:.2f})")
    items.append(_item(6, "Filtreler", filt_sc, "NEUTRAL", " · ".join(filt_bits), hard=filt_hard, ok=not filt_hard and filt_sc >= 45))

    # yön adayı — sinyal + MTF + süpürme + S/R
    tally = {"UP": 0.0, "DOWN": 0.0}
    for it, w in ((items[0], 1.4), (items[2], 1.6), (items[3], 1.1), (items[4], 0.9)):
        if it["vote"] in tally:
            tally[it["vote"]] += w * (it["score"] / 100.0)
    if tally["UP"] > tally["DOWN"] + 0.15:
        direction = "UP"
    elif tally["DOWN"] > tally["UP"] + 0.15:
        direction = "DOWN"
    else:
        direction = "NEUTRAL"

    # 7) Risk
    plan = None
    risk_ok = False
    risk_why = "yön yok"
    risk_sc = 30.0
    if direction in ("UP", "DOWN") and mid:
        try:
            from forex_book import _open_px, _plan, _plan_reject
            side = "buy" if direction == "UP" else "sell"
            bid = float(quote.get("bid") or mid)
            ask = float(quote.get("ask") or mid)
            plan = _plan(side, _open_px(side, bid, ask), levels)
            why = _plan_reject(plan)
            if why:
                risk_why = why
                risk_sc = 22.0
            else:
                risk_ok = True
                risk_sc = min(100.0, 55.0 + float(plan["rr"]) * 12.0)
                risk_why = f"R:R {plan['rr']} · risk ${plan['risk_usd']} · TP {plan['target']}"
        except Exception as e:
            risk_why = str(e)[:80]
            risk_sc = 20.0
    items.append(_item(7, "Risk", risk_sc, direction if risk_ok else "NEUTRAL", risk_why, hard=True, ok=risk_ok))

    # 8) Pozisyon
    pos_sc, pos_ok, pos_why = 70.0, True, "slot boş"
    try:
        from forex_book import snapshot
        book = snapshot(quote.get("bid"), quote.get("ask"), book="a2")
        want = "buy" if direction == "UP" else "sell" if direction == "DOWN" else None
        sides = {p.get("side") for p in (book.get("positions") or [])}
        if want and want in sides:
            pos_sc, pos_ok, pos_why = 55.0, True, f"{want} zaten açık — yönetim"
        elif len(sides) >= 2:
            pos_sc, pos_ok, pos_why = 25.0, False, "1+1 dolu"
        cd = (book.get("last_reject") or {})
        if cd.get("reason") == "bekleme":
            pos_sc, pos_why = 40.0, f"bekleme {cd.get('wait')}s"
    except Exception:
        book = {}
    items.append(_item(8, "Pozisyon", pos_sc, "NEUTRAL", pos_why, hard=not pos_ok, ok=pos_ok))

    # 9) Performans
    perf = _perf_stats()
    if perf["n"] < 8:
        perf_sc, perf_why = 55.0, f"{perf['n']} işlem — örneklem küçük"
    elif (perf.get("wr") or 0) >= 50:
        perf_sc, perf_why = 72.0, f"WR %{perf['wr']} · n={perf['n']}"
    elif (perf.get("wr") or 0) >= 40:
        perf_sc, perf_why = 50.0, f"WR %{perf['wr']} · n={perf['n']}"
    else:
        perf_sc, perf_why = 32.0, f"WR %{perf['wr']} zayıf · n={perf['n']}"
    items.append(_item(9, "Performans", perf_sc, "NEUTRAL", perf_why))

    # 10) Backtest
    bt = _backtest_stats()
    if not bt.get("ok"):
        bt_sc, bt_why = 50.0, "simülasyon henüz yok — `algo2_backtest.py`"
    else:
        wr = float(bt.get("wr") or 0)
        bt_sc = 40.0 + min(40.0, max(0.0, wr - 40.0))
        bt_why = f"sim WR %{wr:.0f} · n={bt.get('n')} · {bt.get('note') or ''}".strip()
    items.append(_item(10, "Simülasyon", bt_sc, "NEUTRAL", bt_why))

    # 11) Canlı altyapı (paper)
    stale = quote.get("stale_sec")
    src = quote.get("src") or "?"
    live_ok = bool(quote.get("bid") and quote.get("ask"))
    live_sc = 80.0 if live_ok else 15.0
    live_why = f"paper · {src}"
    if stale is not None and stale > 25:
        live_sc = min(live_sc, 40.0)
        live_why += f" · kotasyon {int(stale)}s bayat"
    items.append(_item(11, "Altyapı", live_sc, "NEUTRAL", live_why, hard=True, ok=live_ok))

    # 12) Panel — görüntü katmanı, skora girmez
    items.append(_item(12, "Panel", 100.0, "NEUTRAL", "/forex/algo2 KARAR sekmesi", ok=True))

    # 13) Kontrol listesi + gerekçeli karar
    num = sum(_WEIGHTS[it["id"]] * it["score"] for it in items if it["id"] in _WEIGHTS)
    den = sum(_WEIGHTS[it["id"]] for it in items if it["id"] in _WEIGHTS) or 1.0
    score = num / den
    vetoes = [it for it in items if it.get("hard") and not it["ok"]]
    mtf_agree = up_n if direction == "UP" else dn_n if direction == "DOWN" else 0
    if regime == "volatile" and mtf_agree < 3:
        vetoes.append({"name": "Rejim", "reason": "volatil + MTF 3/3 değil"})

    stab = stab_hist if stab_hist is not None else _load_stab()
    if direction in ("UP", "DOWN", "NEUTRAL"):
        stab.append(direction)
        if persist and stab_hist is None:
            _save_stab(stab)
    is_stable = (
        direction in ("UP", "DOWN")
        and len(stab) >= STAB_N
        and all(d == direction for d in list(stab)[-STAB_N:])
    )

    allow = (
        direction in ("UP", "DOWN")
        and score >= SCORE_MIN
        and not vetoes
        and mtf_agree >= MTF_MIN
        and is_stable
        and risk_ok
    )

    if allow:
        verdict = f"{direction} AÇ — skor {score:.0f}, MTF {mtf_agree}/3, {risk_why}"
    elif vetoes:
        verdict = "BEKLE — " + "; ".join(f"{v.get('name')}: {v.get('reason')}" for v in vetoes[:3])
        direction_out = "NEUTRAL"
    elif direction in ("UP", "DOWN") and not is_stable:
        verdict = f"{direction} eğilim — ikinci teyit bekleniyor (skor {score:.0f})"
        direction_out = "NEUTRAL"
    elif direction in ("UP", "DOWN") and score < SCORE_MIN:
        verdict = f"{direction} zayıf — skor {score:.0f} < {SCORE_MIN:.0f}"
        direction_out = "NEUTRAL"
    elif direction in ("UP", "DOWN") and mtf_agree < MTF_MIN:
        verdict = f"{direction} MTF {mtf_agree}/3 — onay yok"
        direction_out = "NEUTRAL"
    else:
        verdict = f"NÖTR — skor {score:.0f}"
        direction_out = "NEUTRAL"

    if allow:
        direction_out = direction

    items.append(_item(
        13, "Karar", score, direction_out, verdict,
        hard=True, ok=allow,
    ))

    conf = score if direction_out in ("UP", "DOWN") else min(score, 49.0)
    rail = {}
    from forex_data import bar_remaining
    for tf, key in (("5m", "5m"), ("15m", "15m")):
        vdir, vmag = votes[tf]
        rail[key] = {
            "direction": vdir if vmag >= 50 else "NEUTRAL",
            "lean": vdir if vdir in ("UP", "DOWN") else "FLAT",
            "confidence": round(vmag, 1),
            "raw_score": round(vmag if vdir == "UP" else -vmag if vdir == "DOWN" else 0.0, 1),
            "fill": round(min(100.0, vmag), 1),
            "is_stable": vdir == direction_out and allow,
            "layers": {
                "trend": layers.get("trend", 0.0) if tf == "5m" else votes["1h"][1] * (1 if votes["1h"][0] == "UP" else -1 if votes["1h"][0] == "DOWN" else 0),
                "momentum": layers.get("momentum", 0.0),
                "pattern": layers.get("pattern", 0.0),
            },
            "bar_left": bar_remaining(tf),
            "bar_sec": 300 if tf == "5m" else 900,
            "engine": "algo2",
        }

    packed = {
        "direction": direction_out,
        "lean": direction if direction in ("UP", "DOWN") else "FLAT",
        "confidence": round(conf, 1),
        "raw_score": round(raw.raw_score, 1),
        "is_stable": bool(allow),
        "allow_entry": bool(allow),
        "score": round(score, 1),
        "threshold": SCORE_MIN,
        "fill": round(min(100.0, score / SCORE_MIN * 100.0), 1),
        "layers": {k: round(float(v), 1) for k, v in layers.items()},
        "engine": "algo2",
        "regime": regime,
        "atr": round(atr_last, 3),
        "verdict": verdict,
        "checklist": items,
        "plan": plan,
        "perf": perf,
        "rail": rail,
        "candidate": direction,
        "mtf": {k: {"direction": v[0], "score": round(v[1], 1)} for k, v in votes.items()},
    }
    if persist:
        _journal({
            "direction": direction_out,
            "candidate": direction,
            "score": packed["score"],
            "allow": allow,
            "regime": regime,
            "verdict": verdict,
        })
    return packed


def live_decision(persist: bool = True) -> dict:
    global _live_cache
    now = time.time()
    if _live_cache and now - _live_cache[0] < _LIVE_TTL:
        return dict(_live_cache[1])
    from forex_data import forex_quote, get_xau_klines
    from forex_signal import sr_levels

    q = forex_quote()
    m1, _ = get_xau_klines("1m", 120)
    m5, _ = get_xau_klines("5m", 120)
    m15, _ = get_xau_klines("15m", 80)
    h1, _ = get_xau_klines("1h", 80)
    try:
        levels = sr_levels(m5)
    except Exception:
        levels = {}
    packed = evaluate(
        rows_to_df(m1), rows_to_df(m5), rows_to_df(m15), rows_to_df(h1),
        quote=q, levels=levels, persist=persist,
    )
    packed["levels"] = levels
    packed["quote"] = {k: q.get(k) for k in ("mid", "bid", "ask", "spread", "src", "stale_sec")}
    _live_cache = (now, packed)
    return dict(packed)


def overlay_markers(tf: str, candles: list[dict]) -> tuple[dict, list[dict]]:
    """Grafik harfleri — son ~36 bar, HTF sabit (overlay)."""
    live = live_decision(persist=False)
    if len(candles) < 30:
        return live, []
    from forex_data import get_xau_klines
    from forex_signal import sr_levels

    m5, _ = get_xau_klines("5m", 120)
    m15, _ = get_xau_klines("15m", 80)
    h1, _ = get_xau_klines("1h", 80)
    levels = sr_levels(m5)
    q = live.get("quote") or {}
    m5d, m15d, h1d = rows_to_df(m5), rows_to_df(m15), rows_to_df(h1)
    start = max(26, len(candles) - 20)
    marks: list[dict] = []
    last_dir = None
    walk = deque(maxlen=STAB_N)
    for i in range(start, len(candles)):
        df = rows_to_df(candles[: i + 1])
        if tf in ("5m", "15m", "1h"):
            packed = evaluate(
                df, df if tf == "5m" else m5d, df if tf == "15m" else m15d,
                df if tf == "1h" else h1d, quote=q, levels=levels, persist=False,
                stab_hist=walk,
            )
        else:
            packed = evaluate(df, m5d, m15d, h1d, quote=q, levels=levels, persist=False, stab_hist=walk)
        d = packed.get("direction")
        if packed.get("allow_entry") and d in ("UP", "DOWN") and d != last_dir:
            last_dir = d
            marks.append({
                "time": int(candles[i]["time"]),
                "direction": d,
                "confidence": packed.get("score"),
            })
    return live, marks[-48:]
