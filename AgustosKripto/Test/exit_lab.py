#!/usr/bin/env python3
"""Çıkış rejimi laboratuvarı — girişler sabit, çıkış kuralları değişken.

Soru: "1 saatlik / 4 saatlik zorunlu kapanış zarar mı yazdırıyor?"
Kapanış-sebebi tablosu bunu cevaplayamaz çünkü ATR kâr kilidi kazananları
erken alıp götürür; saatlik kapanışa artık kaybedenler kalır (seçilim
yanlılığı). Tek dürüst cevap: aynı girişleri gerçek 1m fiyat verisiyle
farklı çıkış kurallarında yeniden oynatmak.

Her işlemin girişi (sembol/yön/fiyat/zaman/ATR) sabit tutulur, yalnız çıkış
değişir. `mevcut` rejimi kayıtlı sonucu yeniden üretmelidir — doğrulama budur.

    python3 AgustosKripto/Test/exit_lab.py --validate
    python3 AgustosKripto/Test/exit_lab.py --sweep
    python3 AgustosKripto/Test/exit_lab.py --sweep --group Test
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
_AGUSTOS = os.path.dirname(_DIR)
for _p in (_DIR, _AGUSTOS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import minute_data as md  # noqa: E402
import skill_audit as sa  # noqa: E402

HOUR_MS = 3_600_000
MIN_MS = 60_000
LOSS_MIN_AGE_MIN = 10

_CACHE: dict[str, dict | None] = {}


def minutes(sym: str) -> dict | None:
    if sym not in _CACHE:
        try:
            _CACHE[sym] = md.load_minutes(sym)
        except Exception:
            _CACHE[sym] = None
    return _CACHE[sym]


def _ms(ts: str) -> int | None:
    try:
        return int(datetime.fromisoformat(str(ts)).timestamp() * 1000)
    except Exception:
        return None


class Regime:
    """Bir çıkış rejimi.

    time_close_h : zorunlu mum kapanışı (saat). None = zaman kapanışı yok.
                   "auto" = pozisyonun kendi interval'ı (1h/4h).
    max_hold_h   : mutlak süre sınırı.
    arm/trail/lock_min : ATR kâr kilidi çarpanları (None = kilit yok).
    loss_mult    : ATR zarar stopu (None = yok).
    skip_when_locked : kilitli ve kârdayken zaman kapanışını atla (mevcut davranış).
    """

    def __init__(self, name, *, time_close_h="auto", max_hold_h=48.0,
                 arm=1.0, trail=1.0, lock_min=0.5, loss_mult=2.0,
                 skip_when_locked=True):
        self.name = name
        self.time_close_h = time_close_h
        self.max_hold_h = max_hold_h
        self.arm = arm
        self.trail = trail
        self.lock_min = lock_min
        self.loss_mult = loss_mult
        self.skip_when_locked = skip_when_locked


def _first_true(mask: np.ndarray, start: int = 0) -> int | None:
    if start >= mask.size:
        return None
    idx = np.flatnonzero(mask[start:])
    return int(idx[0] + start) if idx.size else None


def simulate(trade: dict, reg: Regime) -> dict | None:
    """Tek işlemi rejime göre yeniden oynat. Dönüş: net/brüt/komisyon/sebep."""
    sym = (trade.get("symbol") or "").upper()
    m = minutes(sym)
    if m is None:
        return None
    t_entry = _ms(trade.get("entry_time_tr"))
    if t_entry is None:
        return None

    tarr = m["t"]
    i0 = int(np.searchsorted(tarr, t_entry, side="left"))
    if i0 >= tarr.size - 2:
        return None

    horizon = int(reg.max_hold_h * 60) + 2
    i1 = min(tarr.size, i0 + horizon)
    if i1 - i0 < 3:
        return None

    px = m["close"][i0:i1].astype(np.float64)
    ts = tarr[i0:i1]

    entry = float(trade.get("entry_price") or 0)
    qty = float(trade.get("qty") or 0)
    if entry <= 0 or qty <= 0:
        return None
    sign = 1.0 if trade.get("side") == "LONG" else -1.0
    entry_fee = float(trade.get("entry_fee") or 0)
    notional = float(trade.get("notional") or entry * qty)
    rate = (entry_fee / notional) if notional > 0 else 0.0005
    au = float(trade.get("atr_usd") or 0)

    gross = sign * (px - entry) * qty
    exit_fee = px * qty * rate
    net_u = gross - entry_fee - exit_fee

    # ── ATR kâr kilidi (yol bağımlı ama monoton → vektörize edilebilir) ──
    armed_at: int | None = None
    stop_arr = None
    if reg.arm is not None and au > 0:
        peak = np.maximum.accumulate(net_u)
        armed_at = _first_true(peak >= reg.arm * au)
        if armed_at is not None:
            stop_arr = np.maximum(peak - reg.trail * au, reg.lock_min * au)

    cands: list[tuple[int, str]] = []

    if armed_at is not None and stop_arr is not None:
        hit = _first_true(net_u <= stop_arr, armed_at)
        if hit is not None:
            cands.append((hit, "atr_stop"))

    if reg.loss_mult and au > 0:
        age_ok = (ts - t_entry) >= LOSS_MIN_AGE_MIN * MIN_MS
        loss_mask = age_ok & (net_u <= -reg.loss_mult * au)
        if armed_at is not None:
            loss_mask[armed_at:] = False  # kilit devredeyse zarar stopu kapalı
        hit = _first_true(loss_mask)
        if hit is not None:
            cands.append((hit, "atr_loss"))

    if reg.time_close_h is not None:
        if reg.time_close_h == "auto":
            iv = trade.get("interval") or "1h"
            period_h = 4 if str(iv).startswith("4") else 1
        else:
            period_h = float(reg.time_close_h)
        period_ms = int(period_h * HOUR_MS)
        bnds = np.flatnonzero((ts % period_ms) == 0)
        for b in bnds:
            b = int(b)
            if b == 0:
                continue
            if (reg.skip_when_locked and armed_at is not None
                    and armed_at <= b and net_u[b - 1] > 0):
                continue
            cands.append((b - 1, f"{period_h:g}h_close"))
            break

    cands.append((net_u.size - 1, "max_hold"))

    i, reason = min(cands, key=lambda c: (c[0], c[1] != "atr_loss"))
    return {
        "net": float(net_u[i]),
        "brut": float(gross[i]),
        "kom": float(entry_fee + exit_fee[i]),
        "sebep": reason,
        "saat": float((ts[i] - t_entry) / HOUR_MS),
        "ret_pct": float(sign * (px[i] - entry) / entry * 100.0),
        "side": trade.get("side"),
    }


def run(trades: list[dict], reg: Regime) -> dict:
    net = brut = kom = 0.0
    n = wins = 0
    hours = 0.0
    longs: list[float] = []
    shorts: list[float] = []
    reasons: dict[str, int] = defaultdict(int)
    for t in trades:
        r = simulate(t, reg)
        if r is None:
            continue
        n += 1
        net += r["net"]
        brut += r["brut"]
        kom += r["kom"]
        hours += r["saat"]
        wins += 1 if r["net"] > 0 else 0
        reasons[r["sebep"]] += 1
        (longs if r["side"] == "LONG" else shorts).append(r["ret_pct"])
    if not n:
        return {}
    skill = ((sum(longs) / len(longs) if longs else 0.0)
             + (sum(shorts) / len(shorts) if shorts else 0.0)) / 2
    allr = longs + shorts
    mean = sum(allr) / len(allr)
    sd = (sum((v - mean) ** 2 for v in allr) / len(allr)) ** 0.5
    tstat = mean / (sd / len(allr) ** 0.5) if sd > 0 else 0.0
    return {
        "rejim": reg.name, "n": n, "net": net, "brut": brut, "kom": kom,
        "wr": 100.0 * wins / n, "saat": hours / n, "skill": skill, "t": tstat,
        "sebepler": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
    }


def _load(group: str | None) -> list[dict]:
    groups = {group: sa.GROUPS[group]} if group else None
    trades = sa.load_trades(groups)
    return [t for t in trades if minutes((t.get("symbol") or "").upper()) is not None]


def cmd_validate(trades: list[dict]) -> None:
    """Simülatör kayıtlı gerçeği yeniden üretiyor mu?"""
    base = Regime("mevcut")
    ok = [t for t in trades if t.get("close_reason") != "signal_reversal"]
    sim_net = rec_net = 0.0
    n = 0
    same_reason = 0
    diffs: list[float] = []
    for t in ok:
        r = simulate(t, base)
        if r is None:
            continue
        n += 1
        sim_net += r["net"]
        rec_net += float(t.get("pnl") or 0)
        diffs.append(abs(r["net"] - float(t.get("pnl") or 0)))
        if r["sebep"] == t.get("close_reason"):
            same_reason += 1
    diffs.sort()
    print(f"Doğrulama — {n:,} işlem (signal_reversal hariç)")
    print(f"  kayıtlı net  ${rec_net:+,.0f}")
    print(f"  simüle net   ${sim_net:+,.0f}   (sapma ${sim_net - rec_net:+,.0f})")
    print(f"  sebep örtüşmesi %{100.0 * same_reason / n:.1f}")
    print(f"  işlem başı mutlak sapma: medyan ${diffs[n // 2]:.3f} · "
          f"p90 ${diffs[int(n * 0.9)]:.3f}")


def cmd_sweep(trades: list[dict]) -> None:
    regimes = [
        Regime("mevcut (1h/4h zorunlu)"),
        Regime("zaman kapanışı YOK · 24s tavan", time_close_h=None, max_hold_h=24),
        Regime("zaman kapanışı YOK · 48s tavan", time_close_h=None, max_hold_h=48),
        Regime("zorunlu 2s", time_close_h=2),
        Regime("zorunlu 4s", time_close_h=4),
        Regime("zorunlu 8s", time_close_h=8),
        Regime("zorunlu 12s", time_close_h=12),
        Regime("zorunlu 24s", time_close_h=24),
        Regime("mevcut · zarar stopu YOK", loss_mult=None),
        Regime("mevcut · zarar stopu 1.0", loss_mult=1.0),
        Regime("mevcut · zarar stopu 3.0", loss_mult=3.0),
        Regime("kilit yok · sade 1h/4h", arm=None, loss_mult=None),
        Regime("kilit arm0.5/trail0.5", arm=0.5, trail=0.5, lock_min=0.25),
        Regime("kilit arm0.5/trail1.0", arm=0.5, trail=1.0, lock_min=0.25),
        Regime("kilit arm1.0/trail0.5", arm=1.0, trail=0.5, lock_min=0.5),
        Regime("kilit arm1.5/trail1.0", arm=1.5, trail=1.0, lock_min=0.75),
        Regime("zaman YOK + arm0.5/trail0.5 · 24s", time_close_h=None, max_hold_h=24,
               arm=0.5, trail=0.5, lock_min=0.25),
        Regime("zaman YOK + arm1.0/trail0.5 · 24s", time_close_h=None, max_hold_h=24,
               arm=1.0, trail=0.5, lock_min=0.5),
        Regime("zaman YOK + zarar stopu yok · 24s", time_close_h=None, max_hold_h=24,
               loss_mult=None),
    ]
    print(f"{'rejim':36} {'n':>6} {'net':>11} {'brüt':>11} {'kom':>10} "
          f"{'WR':>6} {'saat':>6} {'SKILL':>9} {'t':>7}")
    print("─" * 112)
    for reg in regimes:
        r = run(trades, reg)
        if not r:
            continue
        print(f"{r['rejim']:36} {r['n']:>6,} {r['net']:>+11,.0f} {r['brut']:>+11,.0f} "
              f"{r['kom']:>10,.0f} {r['wr']:>5.1f}% {r['saat']:>6.1f} "
              f"{r['skill']:>+9.4f} {r['t']:>+7.2f}")


def with_forward(trades: list[dict], hours: float) -> list[dict]:
    """Yalnız tam ileri veriye sahip işlemler.

    Kritik: bu filtre olmadan son günlerin işlemleri ufku dolduramaz ve
    "max_hold" çıkışı fiilen 'şu anki fiyattan değerle' olur. Bu, uzun
    ufukları açık pozisyon kâr/zararıyla kirletir.
    """
    need = int(hours * HOUR_MS)
    out = []
    for t in trades:
        m = minutes((t.get("symbol") or "").upper())
        if m is None:
            continue
        te = _ms(t.get("entry_time_tr"))
        if te is None:
            continue
        if te + need <= int(m["t"][-1]):
            out.append(t)
    return out


def day_cluster_t(rows: list[dict]) -> tuple[float, float, int]:
    """Gün bazlı kümelenmiş SKILL ortalaması ve t.

    İşlem düzeyi t-istatistiği sahte hassasiyet üretiyor: 118 defter aynı
    30 coinde aynı saatte işlem açıyor, yani gözlemler bağımsız değil.
    Bağımsız birim gün; t bu yüzden gün üzerinden hesaplanmalı.
    """
    per_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        per_day[r["gun"]].append(r)
    daily = []
    for g, rs in per_day.items():
        if len(rs) < 50:
            continue
        ln = [x["ret_pct"] for x in rs if x["side"] == "LONG"]
        sh = [x["ret_pct"] for x in rs if x["side"] == "SHORT"]
        if not ln or not sh:
            continue
        daily.append(((sum(ln) / len(ln)) + (sum(sh) / len(sh))) / 2)
    k = len(daily)
    if k < 2:
        return 0.0, 0.0, k
    mean = sum(daily) / k
    sd = (sum((v - mean) ** 2 for v in daily) / (k - 1)) ** 0.5
    return mean, (mean / (sd / k ** 0.5) if sd > 0 else 0.0), k


def detail(trades: list[dict], reg: Regime) -> dict:
    """Tek rejimin işlem düzeyi dökümü — kuyruk riski ve gün istikrarı için."""
    rows = []
    for t in trades:
        r = simulate(t, reg)
        if r is None:
            continue
        r["gun"] = str(t.get("entry_time_tr"))[:10]
        r["kitap"] = f"{t['_group']}·{t.get('algo') or t['_bookfile']}"
        r["notional"] = float(t.get("notional") or 0)
        rows.append(r)
    return {"rows": rows}


def _line(label: str, rows: list[dict]) -> None:
    if not rows:
        print(f"{label:34} —")
        return
    n = len(rows)
    brut = sum(r["brut"] for r in rows)
    net = sum(r["net"] for r in rows)
    notional = sum(r["notional"] for r in rows) or 1.0
    wr = 100.0 * sum(1 for r in rows if r["net"] > 0) / n
    sk, tc, k = day_cluster_t(rows)
    print(f"{label:34} {n:>6,} {net:>+10,.0f} {brut:>+10,.0f} {wr:>5.1f}% "
          f"{sum(r['saat'] for r in rows) / n:>5.1f} "
          f"{100.0 * brut / notional:>+8.4f} {sk:>+8.4f} {tc:>+6.2f} {k:>3}")


def _hdr() -> None:
    print(f"{'rejim':34} {'n':>6} {'net':>10} {'brüt':>10} {'WR':>6} {'saat':>5} "
          f"{'kenar%':>8} {'SKILL':>8} {'t_gün':>6} {'g':>3}")
    print("─" * 106)


def cmd_deep(trades: list[dict], horizon: float = 24.0) -> None:
    """Adil karşılaştırma — tüm rejimler aynı, tam ileri veriye sahip işlemlerde."""
    fair = with_forward(trades, horizon)
    print(f"Adil örneklem: {horizon:g} saat tam ileri veriye sahip {len(fair):,} işlem "
          f"({len(trades):,} işlemden)\n")

    print("── Zaman kapanışı ve zarar stopunun ayrı ayrı katkısı ──")
    _hdr()
    for label, reg in [
        ("mevcut (1h/4h + stop 2×ATR)", Regime("x", max_hold_h=horizon)),
        ("zaman kapanışı kaldırıldı", Regime("x", time_close_h=None, max_hold_h=horizon)),
        ("zarar stopu kaldırıldı", Regime("x", max_hold_h=horizon, loss_mult=None)),
        ("ikisi birden kaldırıldı", Regime("x", time_close_h=None, max_hold_h=horizon,
                                           loss_mult=None)),
        ("ikisi + kilit de yok (sade tut)", Regime("x", time_close_h=None,
                                                   max_hold_h=horizon, loss_mult=None,
                                                   arm=None)),
    ]:
        _line(label, detail(fair, reg)["rows"])

    print("\n── Süre tavanı (zaman kapanışı yok · zarar stopu yok) ──")
    _hdr()
    for h in (4, 6, 8, 12, 24, 48):
        sub = with_forward(trades, h)
        _line(f"{h}s tavan · n_adil={len(sub):,}",
              detail(sub, Regime("x", time_close_h=None, max_hold_h=h,
                                 loss_mult=None))["rows"])

    print("\n── Kuyruk riski (zarar stopu seviyeleri · tavan %gs) ──" % horizon)
    print(f"{'stop':>10} {'net':>10} {'brüt':>10} {'SKILL':>8} {'t_gün':>6} "
          f"{'en kötü':>9} {'p1':>8} {'p5':>8}")
    for ls in (None, 2.0, 3.0, 4.0, 6.0):
        rows = detail(fair, Regime("x", time_close_h=None, max_hold_h=horizon,
                                   loss_mult=ls))["rows"]
        if not rows:
            continue
        nets = sorted(r["net"] for r in rows)
        sk, tc, _ = day_cluster_t(rows)
        lbl = "yok" if ls is None else f"{ls:g}×ATR"
        print(f"{lbl:>10} {sum(nets):>+10,.0f} "
              f"{sum(r['brut'] for r in rows):>+10,.0f} {sk:>+8.4f} {tc:>+6.2f} "
              f"{nets[0]:>+9.1f} {nets[int(len(nets) * 0.01)]:>+8.1f} "
              f"{nets[int(len(nets) * 0.05)]:>+8.1f}")

    best = Regime("x", time_close_h=None, max_hold_h=horizon, loss_mult=None)
    rows = detail(fair, best)["rows"]

    print(f"\n── Gün gün istikrar ({horizon:g}s tavan · stop yok) ──")
    per_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        per_day[r["gun"]].append(r)
    print(f"{'gün':>12} {'n':>6} {'brüt':>10} {'SKILL':>9}")
    for g in sorted(per_day):
        rs = per_day[g]
        ln = [x["ret_pct"] for x in rs if x["side"] == "LONG"]
        sh = [x["ret_pct"] for x in rs if x["side"] == "SHORT"]
        sk = ((sum(ln) / len(ln) if ln else 0) + (sum(sh) / len(sh) if sh else 0)) / 2
        print(f"{g:>12} {len(rs):>6,} {sum(x['brut'] for x in rs):>+10,.0f} {sk:>+9.4f}")
    sk, tc, k = day_cluster_t(rows)
    print(f"{'KÜMELENMİŞ':>12} {len(rows):>6,} "
          f"{sum(r['brut'] for r in rows):>+10,.0f} {sk:>+9.4f}  t={tc:+.2f} (g={k})")

    print(f"\n── Maliyet duyarlılığı ({horizon:g}s tavan · stop yok) ──")
    notional = sum(r["notional"] for r in rows)
    brut = sum(r["brut"] for r in rows)
    print(f"  işlem {len(rows):,} · notional ${notional:,.0f} · brüt ${brut:+,.0f}")
    print(f"  brüt kenar %{100.0 * brut / notional:.4f} · gereken eşik = komisyon oranı")
    for name, pct in (("taker gidiş-dönüş %0.100", 0.100),
                      ("karma %0.070", 0.070),
                      ("maker gidiş-dönüş %0.040", 0.040)):
        cost = notional * pct / 100.0
        print(f"  {name:26} maliyet ${cost:>9,.0f} → net ${brut - cost:>+10,.0f}")


def realistic(trades: list[dict], reg: Regime) -> dict:
    """Gerçekçi replay — bir (defter, sembol) çiftinde aynı anda tek pozisyon.

    Yukarıdaki taramalar girişleri sabit tutar, yani uzun tutmanın komisyon
    tasarrufunu göremez. Gerçekte pozisyon 12 saat açıksa o defter o coinde
    11 saat yeni işlem açamaz — komisyon asıl orada düşer.
    """
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in trades:
        key = (t["_bookfile"], (t.get("symbol") or "").upper())
        by_key[key].append(t)

    rows: list[dict] = []
    skipped = 0
    for key, lst in by_key.items():
        lst.sort(key=lambda x: str(x.get("entry_time_tr")))
        busy_until = -1
        for t in lst:
            te = _ms(t.get("entry_time_tr"))
            if te is None:
                continue
            if te < busy_until:
                skipped += 1
                continue
            r = simulate(t, reg)
            if r is None:
                continue
            r["gun"] = str(t.get("entry_time_tr"))[:10]
            r["notional"] = float(t.get("notional") or 0)
            rows.append(r)
            busy_until = te + int(r["saat"] * HOUR_MS)
    return {"rows": rows, "atlanan": skipped}


def cmd_realistic(trades: list[dict]) -> None:
    print("── Gerçekçi replay: (defter, coin) başına tek pozisyon ──")
    print(f"{'rejim':34} {'işlem':>7} {'atlanan':>8} {'net':>10} {'brüt':>10} "
          f"{'kom':>9} {'saat':>5} {'kenar%':>8} {'t_gün':>6}")
    print("─" * 108)
    for label, reg in [
        ("mevcut (1h/4h + stop 2×ATR)", Regime("x", max_hold_h=24)),
        ("zaman yok · stop 2×ATR · 12s", Regime("x", time_close_h=None,
                                                max_hold_h=12)),
        ("zaman yok · stop yok · 8s", Regime("x", time_close_h=None,
                                             max_hold_h=8, loss_mult=None)),
        ("zaman yok · stop yok · 12s", Regime("x", time_close_h=None,
                                              max_hold_h=12, loss_mult=None)),
        ("zaman yok · stop yok · 24s", Regime("x", time_close_h=None,
                                              max_hold_h=24, loss_mult=None)),
        ("zaman yok · stop 6×ATR · 24s", Regime("x", time_close_h=None,
                                                max_hold_h=24, loss_mult=6.0)),
        ("zorunlu 4s · stop 6×ATR", Regime("x", time_close_h=4, loss_mult=6.0,
                                           max_hold_h=24)),
    ]:
        res = realistic(trades, reg)
        rows = res["rows"]
        if not rows:
            continue
        n = len(rows)
        net = sum(r["net"] for r in rows)
        brut = sum(r["brut"] for r in rows)
        kom = sum(r["kom"] for r in rows)
        notional = sum(r["notional"] for r in rows) or 1.0
        _sk, tc, _k = day_cluster_t(rows)
        print(f"{label:34} {n:>7,} {res['atlanan']:>8,} {net:>+10,.0f} "
              f"{brut:>+10,.0f} {kom:>9,.0f} "
              f"{sum(r['saat'] for r in rows) / n:>5.1f} "
              f"{100.0 * brut / notional:>+8.4f} {tc:>+6.2f}")


def cmd_walkforward(trades: list[dict], split: str) -> None:
    """Giriş filtresi kurtarır mı — eğitim/test ayrımıyla.

    Geçmişte en iyi defterleri seçip aynı geçmişte ölçmek her zaman kâr
    gösterir. Tek dürüst sınav: seçimi ilk yarıda yap, sonucu ikinci yarıda oku.
    """
    reg = Regime("x", time_close_h=None, max_hold_h=24, loss_mult=None)
    res = realistic(trades, reg)
    # realistic() işlem meta'sını düşürüyor; defter etiketi için yeniden eşle
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in trades:
        by_key[(t["_bookfile"], (t.get("symbol") or "").upper())].append(t)

    rows: list[dict] = []
    for key, lst in by_key.items():
        lst.sort(key=lambda x: str(x.get("entry_time_tr")))
        busy = -1
        for t in lst:
            te = _ms(t.get("entry_time_tr"))
            if te is None or te < busy:
                continue
            r = simulate(t, reg)
            if r is None:
                continue
            r["gun"] = str(t.get("entry_time_tr"))[:10]
            r["notional"] = float(t.get("notional") or 0)
            r["defter"] = t["_bookfile"]
            r["coin"] = key[1]
            rows.append(r)
            busy = te + int(r["saat"] * HOUR_MS)

    train = [r for r in rows if r["gun"] < split]
    test = [r for r in rows if r["gun"] >= split]
    print(f"Rejim: zaman kapanışı yok · 24s tavan · zarar stopu yok")
    print(f"Eğitim {len(train):,} işlem (< {split}) · Test {len(test):,} işlem (≥ {split})\n")

    def _skill(rs: list[dict]) -> float:
        ln = [x["ret_pct"] for x in rs if x["side"] == "LONG"]
        sh = [x["ret_pct"] for x in rs if x["side"] == "SHORT"]
        if not ln or not sh:
            return 0.0
        return ((sum(ln) / len(ln)) + (sum(sh) / len(sh))) / 2

    def _report(label: str, rs: list[dict]) -> None:
        if not rs:
            print(f"{label:38} —")
            return
        notional = sum(r["notional"] for r in rs) or 1.0
        brut = sum(r["brut"] for r in rs)
        print(f"{label:38} {len(rs):>6,} işlem  brüt ${brut:>+8,.0f}  "
              f"net ${sum(r['net'] for r in rs):>+8,.0f}  "
              f"kenar %{100.0 * brut / notional:>+7.4f}")

    for level, keyfn in (("defter", lambda r: r["defter"]),
                         ("defter×coin", lambda r: (r["defter"], r["coin"]))):
        tr: dict = defaultdict(list)
        for r in train:
            tr[keyfn(r)].append(r)
        for min_n in (20, 50):
            good = {k for k, rs in tr.items()
                    if len(rs) >= min_n and _skill(rs) > 0.10}
            sel = [r for r in test if keyfn(r) in good]
            _report(f"{level} · eğitimde SKILL>0.10 · n≥{min_n}", sel)
    print()
    _report("FİLTRESİZ (tüm test)", test)


def main() -> None:
    p = argparse.ArgumentParser(description="Çıkış rejimi laboratuvarı")
    p.add_argument("--group", choices=list(sa.GROUPS))
    p.add_argument("--validate", action="store_true")
    p.add_argument("--sweep", action="store_true")
    p.add_argument("--deep", action="store_true")
    p.add_argument("--horizon", type=float, default=24.0)
    p.add_argument("--realistic", action="store_true")
    p.add_argument("--walkforward", metavar="YYYY-MM-DD")
    args = p.parse_args()

    trades = _load(args.group)
    print(f"Kapsanan işlem: {len(trades):,}\n")
    if args.walkforward:
        cmd_walkforward(trades, args.walkforward)
        return
    if args.realistic:
        cmd_realistic(trades)
        return
    if args.validate or not (args.sweep or args.deep):
        cmd_validate(trades)
        print()
    if args.sweep:
        cmd_sweep(trades)
    if args.deep:
        cmd_deep(trades, args.horizon)


if __name__ == "__main__":
    main()
