"""X1#01 - 13Analiz — Poly saatlik BTC/ETH/SOL kontrol listesi.

Forex A2'nin stop/R:R motoru değil. Birim kenar: model P(UP) eksi gerçek ask,
eksi taker. C101 modelini `update_baseline=False` ile okur — C1 defterini kirletmez.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import c101_data as cd
from c101_signal import (
    SYMBOLS,
    evaluate as c101_evaluate,
    fair_probability,
    stake_for,
)

_TZ = ZoneInfo("Europe/Istanbul")
SCORE_MIN = 64.0
MTF_MIN = 2
EDGE_MIN = 0.03
OVERROUND_HARD = 0.06

_WEIGHTS = {
    1: 16.0, 2: 8.0, 3: 14.0, 4: 8.0, 5: 8.0, 6: 12.0,
    7: 14.0, 8: 6.0, 9: 4.0, 10: 2.0, 11: 4.0, 12: 0.0,
}


def _item(n: int, name: str, score: float, vote: str, reason: str,
          hard: bool = False, ok: bool | None = None) -> dict:
    sc = round(float(score), 1)
    passed = bool(ok) if ok is not None else sc >= 50.0
    return {
        "id": n, "name": name, "score": sc, "vote": vote,
        "ok": passed, "hard": hard, "reason": reason,
    }


def _ema_vote(kl: list[dict], fast: int = 20, slow: int = 50) -> tuple[str, float]:
    closes = [float(k["c"]) for k in kl if k.get("c")]
    if len(closes) < fast:
        return "NEUTRAL", 0.0
    def ema(span: int) -> float:
        k = 2.0 / (span + 1.0)
        v = closes[0]
        for x in closes[1:]:
            v = x * k + v * (1.0 - k)
        return v
    span_s = slow if len(closes) >= slow else fast
    f, s = ema(fast), ema(span_s)
    last = closes[-1]
    if s == 0:
        return "NEUTRAL", 0.0
    mag = min(100.0, abs(f - s) / abs(s) * 8000.0)
    if last > f > s:
        return "UP", mag
    if last < f < s:
        return "DOWN", mag
    if last > f:
        return "UP", max(28.0, mag * 0.45)
    if last < f:
        return "DOWN", max(28.0, mag * 0.45)
    return "NEUTRAL", 0.0


def _regime(kl: list[dict]) -> tuple[str, float, str]:
    bars = [k for k in kl[-24:] if k.get("h") and k.get("l") and k.get("c")]
    if len(bars) < 8:
        return "range", 45.0, "yetersiz mum"
    ranges = [(k["h"] - k["l"]) / k["c"] for k in bars if k["c"] > 0]
    last = ranges[-1]
    mid = sorted(ranges)[len(ranges) // 2]
    if mid <= 0:
        return "range", 45.0, "ATR yok"
    ratio = last / mid
    if ratio >= 1.8:
        return "volatile", 36.0, f"saat içi {ratio:.1f}× medyan"
    if ratio <= 0.55:
        return "range", 50.0, f"dar bant ({ratio:.1f}×)"
    return "trend", 76.0, f"normal volatilite ({ratio:.1f}×)"


def decide(
    symbol: str,
    now_tr: datetime | None = None,
    *,
    mkt: dict | None = None,
    history: list | None = None,
    open_syms: set[str] | None = None,
    balance: float = 300.0,
) -> dict:
    now_tr = now_tr or datetime.now(_TZ)
    items: list[dict] = []
    model = fair_probability(symbol, now_tr, update_baseline=False)
    if not model:
        return {
            "allow": False, "direction": "NEUTRAL", "score": 0.0,
            "verdict": "model yok", "checklist": [], "stake": 0.0,
        }

    ev = None
    if mkt:
        ev = c101_evaluate(model, mkt["up"], mkt["down"], edge_min=EDGE_MIN)

    # 1) Sinyal — model P(UP) vs 0.50
    p_up = float(model["p_up"])
    lean = "UP" if p_up >= 0.52 else "DOWN" if p_up <= 0.48 else "NEUTRAL"
    sig_sc = min(100.0, abs(p_up - 0.50) * 400.0)
    items.append(_item(1, "Sinyal", sig_sc, lean, f"model P(UP) {p_up:.3f} · z {model['z']:+.2f}"))

    # 2) Rejim
    kl1 = cd.klines(symbol, "1h", 80)
    regime, rsc, rwhy = _regime(kl1)
    items.append(_item(2, "Rejim", rsc, lean if regime == "trend" else "NEUTRAL", rwhy))

    # 3) MTF
    votes = {
        "5m": _ema_vote(cd.klines(symbol, "5m", 80)),
        "15m": _ema_vote(cd.klines(symbol, "15m", 80)),
        "1h": _ema_vote(kl1),
    }
    dirs = [v[0] for v in votes.values() if v[0] in ("UP", "DOWN")]
    up_n, dn_n = dirs.count("UP"), dirs.count("DOWN")
    if up_n >= 2 and up_n > dn_n:
        mtf_dir, mtf_sc = "UP", 50.0 + 18.0 * up_n
    elif dn_n >= 2 and dn_n > up_n:
        mtf_dir, mtf_sc = "DOWN", 50.0 + 18.0 * dn_n
    else:
        mtf_dir, mtf_sc = "NEUTRAL", 32.0
    items.append(_item(
        3, "MTF", min(100.0, mtf_sc), mtf_dir,
        f"M5 {votes['5m'][0]} · M15 {votes['15m'][0]} · H1 {votes['1h'][0]}",
    ))

    # 4) Yapı — spot vs PTB (saatlik bariyer)
    z = float(model["z"])
    if z >= 0.35:
        st_dir, st_sc, st_why = "UP", 72.0, f"spot PTB üstünde (z {z:+.2f})"
    elif z <= -0.35:
        st_dir, st_sc, st_why = "DOWN", 72.0, f"spot PTB altında (z {z:+.2f})"
    else:
        st_dir, st_sc, st_why = "NEUTRAL", 40.0, f"PTB'ye yapışık (z {z:+.2f})"
    items.append(_item(4, "Yapı", st_sc, st_dir, st_why))

    # 5) Likidite / akış
    tilt = float(model.get("tilt") or 0)
    flow = (model.get("tilt_parts") or {}).get("flow") or 0.0
    if tilt > 0.01:
        liq_dir, liq_sc = "UP", 68.0
    elif tilt < -0.01:
        liq_dir, liq_sc = "DOWN", 68.0
    else:
        liq_dir, liq_sc = "NEUTRAL", 48.0
    items.append(_item(5, "Likidite", liq_sc, liq_dir, f"eğim {tilt:+.3f} · akış {flow:+.3f}"))

    # 6) Filtreler (ask, bant, overround)
    filt_hard = False
    filt_sc = 70.0
    bits = []
    if not mkt:
        filt_hard, filt_sc = True, 15.0
        bits.append("PM kotasyonu yok")
    else:
        src = mkt.get("quote_src") or "?"
        bits.append(src)
        over = float(mkt.get("overround") or 0)
        bits.append(f"overround {over:+.3f}")
        if src != "ask":
            filt_sc = min(filt_sc, 42.0)
            bits.append("ask yok, mid")
        if over >= OVERROUND_HARD:
            filt_hard, filt_sc = True, 20.0
            bits.append("spread şişik")
        if ev and ev.get("skip_reason") and "güven bandı" in ev["skip_reason"]:
            filt_hard, filt_sc = True, 18.0
            bits.append(ev["skip_reason"])
    items.append(_item(6, "Filtreler", filt_sc, "NEUTRAL", " · ".join(bits) or "—",
                       hard=filt_hard, ok=not filt_hard and filt_sc >= 45))

    direction = (ev or {}).get("direction") or lean
    if direction not in ("UP", "DOWN"):
        if mtf_dir in ("UP", "DOWN"):
            direction = mtf_dir
        else:
            direction = "NEUTRAL"

    # 7) Risk — kenar (ask) + Kelly
    edge = float((ev or {}).get("edge") or 0)
    risk_ok = bool(ev and ev.get("tradable") and edge >= EDGE_MIN)
    if not ev:
        risk_sc, risk_why = 20.0, "kenar ölçülemedi"
    elif not ev.get("tradable"):
        risk_sc, risk_why = 24.0, ev.get("skip_reason") or "kenar yok"
    else:
        risk_sc = min(100.0, 50.0 + edge * 600.0)
        risk_why = f"kenar +{edge*100:.1f}p · ask {ev['pm_price']:.2f} · Kelly {ev['kelly_used']*100:.1f}%"
    items.append(_item(7, "Risk", risk_sc, direction if risk_ok else "NEUTRAL",
                       risk_why, hard=True, ok=risk_ok))

    # 8) Pozisyon — saatlik tek bilet / sembol
    busy = symbol in (open_syms or set())
    items.append(_item(
        8, "Pozisyon", 30.0 if busy else 75.0, "NEUTRAL",
        "bu saatte açık" if busy else "slot boş",
        hard=busy, ok=not busy,
    ))

    # 9) Performans
    hist = [t for t in (history or []) if t.get("symbol") == symbol]
    n = len(hist)
    if n < 8:
        perf_sc, perf_why = 55.0, f"{n} işlem — örneklem küçük"
    else:
        wr = 100.0 * sum(1 for t in hist if t.get("win")) / n
        perf_sc = 40.0 + min(40.0, max(0.0, wr - 40.0))
        perf_why = f"WR %{wr:.0f} · n={n}"
    items.append(_item(9, "Performans", perf_sc, "NEUTRAL", perf_why))

    # 10) Simülasyon — henüz yok
    items.append(_item(10, "Simülasyon", 50.0, "NEUTRAL", "walk-forward yok"))

    # 11) Altyapı — paper + ask
    live_ok = bool(mkt and mkt.get("up") and mkt.get("down"))
    items.append(_item(
        11, "Altyapı", 80.0 if live_ok else 15.0, "NEUTRAL",
        "paper · gerçek ask" if (mkt or {}).get("quote_src") == "ask" else "paper · kotasyon eksik",
        hard=True, ok=live_ok,
    ))

    # 12) Panel
    items.append(_item(12, "Panel", 100.0, "NEUTRAL", "/algoritma-islemler/x101", ok=True))

    num = sum(_WEIGHTS[it["id"]] * it["score"] for it in items if it["id"] in _WEIGHTS)
    den = sum(_WEIGHTS[it["id"]] for it in items if it["id"] in _WEIGHTS) or 1.0
    score = num / den
    vetoes = [it for it in items if it.get("hard") and not it["ok"]]
    mtf_agree = up_n if direction == "UP" else dn_n if direction == "DOWN" else 0
    if regime == "volatile" and mtf_agree < 3:
        vetoes.append({"name": "Rejim", "reason": "volatil + MTF 3/3 değil"})

    allow = (
        direction in ("UP", "DOWN")
        and score >= SCORE_MIN
        and not vetoes
        and mtf_agree >= MTF_MIN
        and risk_ok
    )
    if allow:
        verdict = f"{direction} AÇ — skor {score:.0f}, kenar +{edge*100:.1f}p, MTF {mtf_agree}/3"
    elif vetoes:
        verdict = "BEKLE — " + "; ".join(f"{v.get('name')}: {v.get('reason')}" for v in vetoes[:3])
    elif score < SCORE_MIN:
        verdict = f"{direction} zayıf — skor {score:.0f} < {SCORE_MIN:.0f}"
    elif mtf_agree < MTF_MIN:
        verdict = f"{direction} MTF {mtf_agree}/3"
    else:
        verdict = f"NÖTR — skor {score:.0f}"

    items.append(_item(13, "Karar", score, direction if allow else "NEUTRAL", verdict,
                       hard=True, ok=allow))

    kelly = float((ev or {}).get("kelly_used") or 0)
    return {
        "allow": allow,
        "direction": direction if allow else "NEUTRAL",
        "candidate": direction,
        "score": round(score, 1),
        "threshold": SCORE_MIN,
        "verdict": verdict,
        "checklist": items,
        "regime": regime,
        "edge": round(edge, 4),
        "p_model": (ev or {}).get("p_model"),
        "pm_price": (ev or {}).get("pm_price"),
        "kelly_used": kelly,
        "stake": stake_for(float(balance), kelly) if allow else 0.0,
        "model": model,
        "ev": ev,
        "mtf": {k: {"direction": v[0], "score": round(v[1], 1)} for k, v in votes.items()},
    }
