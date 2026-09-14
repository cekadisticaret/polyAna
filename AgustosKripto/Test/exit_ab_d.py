#!/usr/bin/env python3
"""Run D — rejim filtreli melez. Canlı runner / exit_policy dokunulmaz.

Trend'de ATR trail (C), chop/range'de 4h_close (B).
Eşik Mayıs–Temmuz'da kalibre, Ağustos hiç görülmez (OOS).

    python3 AgustosKripto/Test/exit_ab_d.py
"""
from __future__ import annotations

import json
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

import exit_ab_long as L  # noqa: E402
import exit_lab as el  # noqa: E402

OUT = L.OUT
TRAIN_END = "2026-08-07"  # Ağustos OOS

# Önceden sabit hipotez (ekrandaki not) — train'de optimize edilmez
HYP = {"lookback": 48, "abs_ret": 8.0, "vol": 3.0, "adx": 0.0}


def _adx(bars: list[dict], period: int = 14) -> np.ndarray:
    n = len(bars)
    out = np.full(n, np.nan)
    if n < period * 2 + 2:
        return out
    h = np.array([b["h"] for b in bars], dtype=np.float64)
    l = np.array([b["l"] for b in bars], dtype=np.float64)
    c = np.array([b["c"] for b in bars], dtype=np.float64)
    up = np.diff(h)
    dn = -np.diff(l)
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    atr = np.zeros_like(tr)
    pdm = np.zeros_like(tr)
    mdm = np.zeros_like(tr)
    atr[period - 1] = tr[:period].sum()
    pdm[period - 1] = plus[:period].sum()
    mdm[period - 1] = minus[:period].sum()
    for i in range(period, len(tr)):
        atr[i] = atr[i - 1] - atr[i - 1] / period + tr[i]
        pdm[i] = pdm[i - 1] - pdm[i - 1] / period + plus[i]
        mdm[i] = mdm[i - 1] - mdm[i - 1] / period + minus[i]
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100.0 * pdm / atr
        mdi = 100.0 * mdm / atr
        dx = 100.0 * np.abs(pdi - mdi) / (pdi + mdi)
    adx = np.zeros_like(dx)
    start = 2 * period - 2
    if start >= len(dx):
        return out
    adx[start] = np.nanmean(dx[period - 1:start + 1])
    for i in range(start + 1, len(dx)):
        adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period
    out[1:] = adx
    return out


def _sol_features() -> dict:
    bars = L.resample_1h("SOLUSDT") or []
    if len(bars) < 80:
        return {"t": np.array([]), "ret": {}, "vol": {}, "adx": {}}
    t = np.array([b["t"] for b in bars], dtype=np.int64)
    c = np.array([b["c"] for b in bars], dtype=np.float64)
    rets = np.zeros(len(c))
    rets[1:] = np.where(c[:-1] > 0, (c[1:] - c[:-1]) / c[:-1], 0.0)
    adx = _adx(bars)
    feat = {"t": t, "ret": {}, "vol": {}, "adx": {}}
    for lb in (24, 48, 72):
        ret = np.full(len(c), np.nan)
        vol = np.full(len(c), np.nan)
        for i in range(lb, len(c)):
            if c[i - lb] <= 0:
                continue
            ret[i] = 100.0 * (c[i] / c[i - lb] - 1.0)
            vol[i] = 100.0 * float(np.std(rets[i - lb + 1:i + 1]) * np.sqrt(24))
        feat["ret"][lb] = ret
        feat["vol"][lb] = vol
    feat["adx_arr"] = adx
    return feat


def _feat_at(feat: dict, ms: int, lb: int) -> tuple[float, float, float] | None:
    t = feat["t"]
    if t.size == 0:
        return None
    i = int(np.searchsorted(t, ms, side="right") - 1)
    if i < 0:
        return None
    r = feat["ret"][lb][i]
    v = feat["vol"][lb][i]
    a = feat["adx_arr"][i]
    if np.isnan(r) or np.isnan(v):
        return None
    adx = 0.0 if np.isnan(a) else float(a)
    return float(r), float(v), adx


def _is_trend(r: float, v: float, a: float, spec: dict) -> bool:
    if spec["abs_ret"] and abs(r) >= spec["abs_ret"]:
        return True
    if spec["vol"] and v >= spec["vol"]:
        return True
    if spec["adx"] and a >= spec["adx"]:
        return True
    return False


def _simulate_all(entries: list[dict]) -> list[dict]:
    paired = []
    skip = 0
    for t in entries:
        r = L.simulate_regimes(t)
        if r is None:
            skip += 1
            continue
        te = el._ms(t.get("entry_time_tr"))
        paired.append({
            "gun": t.get("gun") or str(t.get("entry_time_tr") or "")[:10],
            "src": t.get("src"),
            "ms": te,
            "A": r["A"], "B": r["B"], "C": r["C"],
        })
    print(f"simüle {len(paired):,}  atlanan {skip:,}")
    return paired


def _apply_d(rows: list[dict], feat: dict, spec: dict) -> list[dict]:
    out = []
    for p in rows:
        fx = _feat_at(feat, p["ms"] or 0, spec["lookback"]) if p["ms"] else None
        trend = bool(fx and _is_trend(*fx, spec))
        chosen = p["C"] if trend else p["B"]
        q = dict(p)
        q["D"] = {**chosen, "rejim": "trend" if trend else "chop",
                  "ret": fx[0] if fx else None, "vol": fx[1] if fx else None,
                  "adx": fx[2] if fx else None}
        out.append(q)
    return out


def _score(rows: list[dict], key: str) -> dict:
    xs = [p[key] for p in rows]
    tot = L._totals(xs)
    if key == "D":
        n_tr = sum(1 for p in rows if p["D"].get("rejim") == "trend")
        tot["trend_n"] = n_tr
        tot["trend_pct"] = 100.0 * n_tr / len(rows) if rows else 0.0
        tot["by_rejim"] = L._agg([
            {"sebep": p["D"]["rejim"], "net": p["D"]["net"]} for p in rows
        ])
    return tot


def _grid() -> list[dict]:
    specs = [dict(HYP)]
    for lb in (24, 48, 72):
        for ar in (0.0, 5.0, 8.0, 12.0):
            for vo in (0.0, 2.5, 3.0, 3.5):
                for adx in (0.0, 25.0):
                    if ar == 0 and vo == 0 and adx == 0:
                        continue
                    specs.append({"lookback": lb, "abs_ret": ar, "vol": vo, "adx": adx})
    # tekilleştir
    seen = set()
    uniq = []
    for s in specs:
        k = (s["lookback"], s["abs_ret"], s["vol"], s["adx"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(s)
    return uniq


def _pick(train: list[dict], feat: dict) -> tuple[dict, dict, list[dict]]:
    """Train'de en iyi D. İki kazanan: serbest + %15–60 trend zorunlu."""
    grid = _grid()
    ranked = []
    for spec in grid:
        applied = _apply_d(train, feat, spec)
        d = _score(applied, "D")
        b = _score(applied, "B")
        ranked.append({
            "spec": spec,
            "d_net": d["net"],
            "vs_b": d["net"] - b["net"],
            "trend_pct": d.get("trend_pct", 0),
            "n": d["n"],
        })
    ranked.sort(key=lambda x: -x["d_net"])
    free = ranked[0]
    hyb_pool = [x for x in ranked if 15.0 <= x["trend_pct"] <= 60.0]
    hyb = hyb_pool[0] if hyb_pool else free
    return free, hyb, ranked[:8]


def _blk(name: str, rows: list[dict], feat: dict, spec: dict) -> dict:
    applied = _apply_d(rows, feat, spec)
    out = {"n": len(applied), "spec": spec}
    for k in ("A", "B", "C", "D"):
        out[k] = _score(applied, k)
    out["d_DA"] = out["D"]["net"] - out["A"]["net"]
    out["d_DB"] = out["D"]["net"] - out["B"]["net"]
    out["d_DC"] = out["D"]["net"] - out["C"]["net"]
    return out


def main() -> None:
    hist = L.load_entries()
    hist_keep = [t for t in hist if (t.get("gun") or "") < TRAIN_END]
    live = L.live_entries()
    entries = hist_keep + live
    print(f"havuz hist {len(hist_keep):,} + canlı {len(live):,} = {len(entries):,}")

    feat = _sol_features()
    paired = _simulate_all(entries)
    train = [p for p in paired if p["gun"] < TRAIN_END]
    test = [p for p in paired if p["gun"] >= TRAIN_END]
    print(f"train {len(train):,} (< {TRAIN_END})  test {len(test):,}")

    free, hyb, top = _pick(train, feat)
    print("train serbest", free)
    print("train hibrit ", hyb)

    report = {
        "olusturma": datetime.now().isoformat(timespec="seconds"),
        "kural": "trend → C (ATR trail) · chop → B (4h_close)",
        "train_end": TRAIN_END,
        "hipotez": HYP,
        "cal_serbest": free,
        "cal_hibrit": hyb,
        "train_top": top,
        "train": {
            "hipotez": _blk("h", train, feat, HYP),
            "serbest": _blk("s", train, feat, free["spec"]),
            "hibrit": _blk("y", train, feat, hyb["spec"]),
        },
        "test_agustos": {
            "hipotez": _blk("h", test, feat, HYP),
            "serbest": _blk("s", test, feat, free["spec"]),
            "hibrit": _blk("y", test, feat, hyb["spec"]),
        },
    }
    a1 = [p for p in test if p["gun"] < "2026-08-15"]
    a2 = [p for p in test if p["gun"] >= "2026-08-15"]
    report["test_agustos_1h"] = _blk("a1", a1, feat, hyb["spec"])
    report["test_agustos_sonra"] = _blk("a2", a2, feat, hyb["spec"])

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "run_d_summary.json")

    def rnd(o):
        if isinstance(o, float):
            return round(o, 4)
        if isinstance(o, dict):
            return {k: rnd(v) for k, v in o.items()}
        if isinstance(o, list):
            return [rnd(v) for v in o]
        return o

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rnd(report), fh, ensure_ascii=False, indent=2)

    rows = []
    for split, blk in (
        ("train_hipotez", report["train"]["hipotez"]),
        ("train_serbest", report["train"]["serbest"]),
        ("train_hibrit", report["train"]["hibrit"]),
        ("oos_hipotez", report["test_agustos"]["hipotez"]),
        ("oos_serbest", report["test_agustos"]["serbest"]),
        ("oos_hibrit", report["test_agustos"]["hibrit"]),
        ("oos_7_14", report["test_agustos_1h"]),
        ("oos_15_23", report["test_agustos_sonra"]),
    ):
        rows.append([
            split, blk["n"],
            f"{blk['A']['net']:.2f}", f"{blk['B']['net']:.2f}",
            f"{blk['C']['net']:.2f}", f"{blk['D']['net']:.2f}",
            f"{blk['d_DA']:.2f}", f"{blk['d_DB']:.2f}", f"{blk['d_DC']:.2f}",
            f"{blk['D'].get('trend_pct', 0):.1f}",
            json.dumps(blk.get("spec") or {}),
        ])
    L.ab._write_csv(
        os.path.join(OUT, "run_d.csv"),
        ["split", "n", "net_A", "net_B", "net_C", "net_D",
         "D-A", "D-B", "D-C", "trend_pct", "spec"],
        rows,
    )

    def show(title: str, blk: dict) -> None:
        print(f"\n── {title}  n={blk['n']:,}  spec={blk.get('spec')} ──")
        for k in ("A", "B", "C", "D"):
            t = blk[k]
            extra = ""
            if k == "D":
                extra = f"  trend %{t.get('trend_pct', 0):.1f}"
            print(f"  {k}  ${t['net']:+,.2f}  WR %{t['wr']:.1f}{extra}")
        print(f"  D−A ${blk['d_DA']:+,.2f}  D−B ${blk['d_DB']:+,.2f}  "
              f"D−C ${blk['d_DC']:+,.2f}")

    show("TRAIN hipotez (vol≥3 | |ret48|≥8)", report["train"]["hipotez"])
    show("TRAIN serbest (May–Tem en iyi)", report["train"]["serbest"])
    show("TRAIN hibrit (%15–60 trend)", report["train"]["hibrit"])
    show("OOS Ağustos hipotez", report["test_agustos"]["hipotez"])
    show("OOS Ağustos serbest", report["test_agustos"]["serbest"])
    show("OOS Ağustos hibrit", report["test_agustos"]["hibrit"])
    show("OOS 7–14 Ağu hibrit", report["test_agustos_1h"])
    show("OOS 15–23 Ağu hibrit", report["test_agustos_sonra"])
    print(f"\nCSV → {os.path.join(OUT, 'run_d.csv')}")


if __name__ == "__main__":
    main()
