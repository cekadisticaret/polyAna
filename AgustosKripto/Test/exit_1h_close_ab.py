#!/usr/bin/env python3
"""1h_close A/B — yalnız backtest. Canlı / cron / virtual_book / exit_policy.json dokunulmaz.

111-series kalıbı: çekirdek `exit_lab.simulate` / `virtual_book.close_all_positions`
değişmez. Bu dosya onları sarmalar; `ENABLE_1H_CLOSE_EXIT` yalnız burada okunur.

Soru: 1h_close (~12k işlem, kayıtlı −$9.090, WR %34) kalkınca bu girişler
4h_close / atr_stop / atr_loss / max_hold hangisine düşer, toplam net büyür mü?

    python3 AgustosKripto/Test/exit_1h_close_ab.py
    python3 AgustosKripto/Test/exit_1h_close_ab.py --group Test

signal_reversal 1m fiyat yolundan üretilemez (sinyal motoru gerekir) — aday değil.
"""
from __future__ import annotations

import argparse
import csv
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

import exit_lab as el  # noqa: E402
import skill_audit as sa  # noqa: E402

# Test bayrağı — production okumaz. CLI her iki değeri de koşturur.
ENABLE_1H_CLOSE_EXIT = True

OUT_DIR = os.path.join(_DIR, "out_1h_close_ab")

# Eski rejim (1h_close'un yazıldığı dönem). Canlı MEASURED (zaman yok · 3×ATR) değil.
_ARM = 1.0
_TRAIL = 1.0
_LOCK_MIN = 0.5
_LOSS_MULT = 2.0
_MAX_HOLD_H = 48.0


def _is_4h(trade: dict) -> bool:
    return str(trade.get("interval") or "1h").startswith("4")


def simulate_pair(trade: dict) -> tuple[dict, dict] | None:
    """Tek fiyat yürüyüşü → Run A (1h açık) ve Run B (1h kapalı) çıkışı.

    Run A: 1h defter → 1h_close; 4h defter → 4h_close.
    Run B: 1h_close yok; bir sonraki zaman çıkışı 4h_close (1h defter dahil).
    Ortak: atr_stop · atr_loss · max_hold. signal_reversal yok.
    """
    sym = (trade.get("symbol") or "").upper()
    m = el.minutes(sym)
    if m is None:
        return None
    t_entry = el._ms(trade.get("entry_time_tr"))
    if t_entry is None:
        return None

    tarr = m["t"]
    i0 = int(np.searchsorted(tarr, t_entry, side="left"))
    if i0 >= tarr.size - 2:
        return None

    horizon = int(_MAX_HOLD_H * 60) + 2
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

    armed_at: int | None = None
    stop_arr = None
    if au > 0:
        peak = np.maximum.accumulate(net_u)
        armed_at = el._first_true(peak >= _ARM * au)
        if armed_at is not None:
            stop_arr = np.maximum(peak - _TRAIL * au, _LOCK_MIN * au)

    common: list[tuple[int, str]] = []

    if armed_at is not None and stop_arr is not None:
        hit = el._first_true(net_u <= stop_arr, armed_at)
        if hit is not None:
            common.append((hit, "atr_stop"))

    if au > 0:
        age_ok = (ts - t_entry) >= el.LOSS_MIN_AGE_MIN * el.MIN_MS
        loss_mask = age_ok & (net_u <= -_LOSS_MULT * au)
        if armed_at is not None:
            loss_mask[armed_at:] = False
        hit = el._first_true(loss_mask)
        if hit is not None:
            common.append((hit, "atr_loss"))

    def _first_boundary(period_h: float) -> int | None:
        period_ms = int(period_h * el.HOUR_MS)
        bnds = np.flatnonzero((ts % period_ms) == 0)
        for b in bnds:
            b = int(b)
            if b == 0:
                continue
            if (armed_at is not None and armed_at <= b and net_u[b - 1] > 0):
                continue
            return b - 1
        return None

    i_1h = _first_boundary(1.0)
    i_4h = _first_boundary(4.0)
    i_max = net_u.size - 1

    def _pick(cands: list[tuple[int, str]]) -> dict:
        i, reason = min(cands, key=lambda c: (c[0], c[1] != "atr_loss"))
        return {
            "net": float(net_u[i]),
            "brut": float(gross[i]),
            "kom": float(entry_fee + exit_fee[i]),
            "sebep": reason,
            "saat": float((ts[i] - t_entry) / el.HOUR_MS),
            "ret_pct": float(sign * (px[i] - entry) / entry * 100.0),
            "side": trade.get("side"),
        }

    common.append((i_max, "max_hold"))

    cands_a = list(common)
    cands_b = list(common)
    if _is_4h(trade):
        if i_4h is not None:
            cands_a.append((i_4h, "4h_close"))
            cands_b.append((i_4h, "4h_close"))
    else:
        if i_1h is not None:
            cands_a.append((i_1h, "1h_close"))
        if i_4h is not None:
            cands_b.append((i_4h, "4h_close"))

    return _pick(cands_a), _pick(cands_b)


def _tid(t: dict) -> str:
    return "|".join((
        t.get("_bookfile") or "",
        (t.get("symbol") or "").upper(),
        str(t.get("entry_time_tr") or ""),
        str(t.get("side") or ""),
    ))


def _agg(rows: list[dict], reason_key: str = "sebep") -> dict[str, dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        buckets[r[reason_key]].append(r)
    out = {}
    for name, rs in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        n = len(rs)
        net = sum(x["net"] for x in rs)
        wins = sum(1 for x in rs if x["net"] > 0)
        out[name] = {
            "n": n,
            "wr": 100.0 * wins / n if n else 0.0,
            "net": net,
            "avg": net / n if n else 0.0,
        }
    return out


def _totals(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0, "wr": 0.0, "net": 0.0, "avg": 0.0, "brut": 0.0, "kom": 0.0}
    net = sum(r["net"] for r in rows)
    wins = sum(1 for r in rows if r["net"] > 0)
    return {
        "n": n,
        "wr": 100.0 * wins / n,
        "net": net,
        "avg": net / n,
        "brut": sum(r["brut"] for r in rows),
        "kom": sum(r["kom"] for r in rows),
    }


def _write_csv(path: str, headers: list[str], rows: list[list]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        w.writerows(rows)


def _row_exit_table(agg: dict[str, dict], totals: dict) -> list[list]:
    rows = []
    for name, s in agg.items():
        rows.append([name, s["n"], f"{s['wr']:.1f}", f"{s['net']:.2f}", f"{s['avg']:.2f}"])
    rows.append(["TOPLAM", totals["n"], f"{totals['wr']:.1f}",
                 f"{totals['net']:.2f}", f"{totals['avg']:.2f}"])
    return rows


def _split_days(rows: list[dict]) -> tuple[str, list[dict], list[dict]]:
    days = sorted({r["gun"] for r in rows if r.get("gun")})
    if len(days) < 4:
        mid = days[len(days) // 2] if days else ""
        return mid, rows, []
    mid = days[len(days) // 2]
    early = [r for r in rows if r["gun"] < mid]
    late = [r for r in rows if r["gun"] >= mid]
    return mid, early, late


def run(group: str | None) -> dict:
    groups = {group: sa.GROUPS[group]} if group else {"Test": sa.GROUPS["Test"]}
    raw = sa.load_trades(groups)
    recorded_1h = [t for t in raw if t.get("close_reason") == "1h_close"]
    rec_1h_net = sum(float(t.get("pnl") or 0) for t in recorded_1h)
    rec_1h_wr = (100.0 * sum(1 for t in recorded_1h if t.get("win") is True)
                 / len(recorded_1h)) if recorded_1h else 0.0

    paired: list[dict] = []
    skipped = 0
    for t in raw:
        pair = simulate_pair(t)
        if pair is None:
            skipped += 1
            continue
        a, b = pair
        gun = str(t.get("entry_time_tr") or "")[:10]
        paired.append({
            "id": _tid(t),
            "gun": gun,
            "group": t.get("_group"),
            "book": t.get("_bookfile"),
            "symbol": (t.get("symbol") or "").upper(),
            "side": t.get("side"),
            "interval": t.get("interval") or "1h",
            "recorded": t.get("close_reason") or "?",
            "rec_net": float(t.get("pnl") or 0),
            "a": a,
            "b": b,
        })

    a_rows = [{**p["a"], "gun": p["gun"], "id": p["id"]} for p in paired]
    b_rows = [{**p["b"], "gun": p["gun"], "id": p["id"]} for p in paired]
    tot_a = _totals(a_rows)
    tot_b = _totals(b_rows)
    agg_a = _agg(a_rows)
    agg_b = _agg(b_rows)

    cohort = [p for p in paired if p["a"]["sebep"] == "1h_close"]
    dest: dict[str, list[dict]] = defaultdict(list)
    for p in cohort:
        dest[p["b"]["sebep"]].append(p["b"])
    dest_agg = {}
    for name, rs in sorted(dest.items(), key=lambda kv: -len(kv[1])):
        n = len(rs)
        net = sum(x["net"] for x in rs)
        wins = sum(1 for x in rs if x["net"] > 0)
        dest_agg[name] = {
            "n": n,
            "wr": 100.0 * wins / n if n else 0.0,
            "net": net,
            "avg": net / n if n else 0.0,
            "share": 100.0 * n / len(cohort) if cohort else 0.0,
        }

    def _reason_delta(name: str) -> dict:
        sa_ = agg_a.get(name, {"n": 0, "wr": 0.0, "net": 0.0, "avg": 0.0})
        sb = agg_b.get(name, {"n": 0, "wr": 0.0, "net": 0.0, "avg": 0.0})
        return {
            "A": sa_,
            "B": sb,
            "dn": sb["n"] - sa_["n"],
            "dnet": sb["net"] - sa_["net"],
            "dwr": sb["wr"] - sa_["wr"],
        }

    mid, early, late = _split_days(paired)

    def _window(subset: list[dict]) -> dict:
        if not subset:
            return {}
        ar = [p["a"] for p in subset]
        br = [p["b"] for p in subset]
        ta, tb = _totals(ar), _totals(br)
        ca = [p for p in subset if p["a"]["sebep"] == "1h_close"]
        return {
            "n": len(subset),
            "A": ta,
            "B": tb,
            "d_net": tb["net"] - ta["net"],
            "cohort_1h": len(ca),
            "cohort_B_net": sum(p["b"]["net"] for p in ca),
            "cohort_A_net": sum(p["a"]["net"] for p in ca),
        }

    # Run A vs kayıtlı (signal_reversal hariç) — simülatör tutarlılığı
    chk_n = chk_same = 0
    chk_diffs: list[float] = []
    for p in paired:
        if p["recorded"] == "signal_reversal":
            continue
        chk_n += 1
        if p["a"]["sebep"] == p["recorded"]:
            chk_same += 1
        chk_diffs.append(abs(p["a"]["net"] - p["rec_net"]))
    chk_diffs.sort()

    report = {
        "olusturma": datetime.now().isoformat(timespec="seconds"),
        "grup": group or "Test",
        "kaynak": "AgustosKripto/Test/data *_history.json + 1m cache",
        "rejim": (
            f"eski kilit arm{_ARM:g}/trail{_TRAIL:g} · "
            f"zarar {_LOSS_MULT:g}×ATR · tavan {_MAX_HOLD_H:g}s"
        ),
        "not": (
            "signal_reversal aday değil (sinyal motoru yok). "
            "Canlı exit_policy.json / runner değişmedi."
        ),
        "kayitli_1h_close": {
            "n": len(recorded_1h),
            "wr": round(rec_1h_wr, 1),
            "net": round(rec_1h_net, 2),
            "avg": round(rec_1h_net / len(recorded_1h), 2) if recorded_1h else 0.0,
        },
        "orneklem": {
            "ham": len(raw),
            "simule": len(paired),
            "atlanan": skipped,
            "ilk": min((p["gun"] for p in paired), default=""),
            "son": max((p["gun"] for p in paired), default=""),
        },
        "dogrulama_A": {
            "n": chk_n,
            "sebep_ortusme_pct": round(100.0 * chk_same / chk_n, 1) if chk_n else 0.0,
            "medyan_sapma": round(chk_diffs[chk_n // 2], 3) if chk_diffs else 0.0,
            "p90_sapma": round(chk_diffs[int(chk_n * 0.9)], 3) if chk_diffs else 0.0,
        },
        "A": {"totals": tot_a, "by_exit": agg_a},
        "B": {"totals": tot_b, "by_exit": agg_b},
        "delta": {
            "n": tot_b["n"] - tot_a["n"],
            "net": tot_b["net"] - tot_a["net"],
            "wr": tot_b["wr"] - tot_a["wr"],
            "avg": tot_b["avg"] - tot_a["avg"],
            "atr_loss": _reason_delta("atr_loss"),
            "4h_close": _reason_delta("4h_close"),
            "atr_stop": _reason_delta("atr_stop"),
            "max_hold": _reason_delta("max_hold"),
            "1h_close": _reason_delta("1h_close"),
        },
        "kohort_1h": {
            "n": len(cohort),
            "A_net": sum(p["a"]["net"] for p in cohort),
            "B_net": sum(p["b"]["net"] for p in cohort),
            "d_net": sum(p["b"]["net"] - p["a"]["net"] for p in cohort),
            "dagilim": dest_agg,
        },
        "walkforward": {
            "split": mid,
            "erken": _window(early),
            "gec": _window(late),
        },
    }

    os.makedirs(OUT_DIR, exist_ok=True)

    _write_csv(
        os.path.join(OUT_DIR, "run_a_by_exit.csv"),
        ["exit", "n", "wr_pct", "net_pnl", "avg_pnl"],
        _row_exit_table(agg_a, tot_a),
    )
    _write_csv(
        os.path.join(OUT_DIR, "run_b_by_exit.csv"),
        ["exit", "n", "wr_pct", "net_pnl", "avg_pnl"],
        _row_exit_table(agg_b, tot_b),
    )

    cmp_rows = []
    names = sorted(set(agg_a) | set(agg_b), key=lambda n: -(agg_a.get(n, {}).get("n", 0)))
    for name in names:
        sa_ = agg_a.get(name, {"n": 0, "wr": 0.0, "net": 0.0, "avg": 0.0})
        sb = agg_b.get(name, {"n": 0, "wr": 0.0, "net": 0.0, "avg": 0.0})
        cmp_rows.append([
            name, sa_["n"], sb["n"], sb["n"] - sa_["n"],
            f"{sa_['wr']:.1f}", f"{sb['wr']:.1f}", f"{sb['wr'] - sa_['wr']:+.1f}",
            f"{sa_['net']:.2f}", f"{sb['net']:.2f}", f"{sb['net'] - sa_['net']:.2f}",
            f"{sa_['avg']:.2f}", f"{sb['avg']:.2f}",
        ])
    cmp_rows.append([
        "TOPLAM", tot_a["n"], tot_b["n"], tot_b["n"] - tot_a["n"],
        f"{tot_a['wr']:.1f}", f"{tot_b['wr']:.1f}", f"{tot_b['wr'] - tot_a['wr']:+.1f}",
        f"{tot_a['net']:.2f}", f"{tot_b['net']:.2f}", f"{tot_b['net'] - tot_a['net']:.2f}",
        f"{tot_a['avg']:.2f}", f"{tot_b['avg']:.2f}",
    ])
    _write_csv(
        os.path.join(OUT_DIR, "comparison.csv"),
        ["exit", "n_A", "n_B", "dn", "wr_A", "wr_B", "dwr",
         "net_A", "net_B", "dnet", "avg_A", "avg_B"],
        cmp_rows,
    )

    dest_rows = []
    for name, s in dest_agg.items():
        dest_rows.append([
            name, s["n"], f"{s['share']:.1f}", f"{s['wr']:.1f}",
            f"{s['net']:.2f}", f"{s['avg']:.2f}",
        ])
    dest_rows.append([
        "KOHORT TOPLAM", len(cohort), "100.0",
        f"{(100.0 * sum(1 for p in cohort if p['b']['net'] > 0) / len(cohort)) if cohort else 0:.1f}",
        f"{sum(p['b']['net'] for p in cohort):.2f}",
        f"{(sum(p['b']['net'] for p in cohort) / len(cohort)) if cohort else 0:.2f}",
    ])
    _write_csv(
        os.path.join(OUT_DIR, "cohort_1h_redistribution.csv"),
        ["B_exit", "n", "share_pct", "wr_pct", "net_pnl", "avg_pnl"],
        dest_rows,
    )

    wf = report["walkforward"]
    wf_rows = []
    for label, w in (("erken", wf["erken"]), ("gec", wf["gec"])):
        if not w:
            continue
        wf_rows.append([
            label, w["n"], w["cohort_1h"],
            f"{w['A']['net']:.2f}", f"{w['B']['net']:.2f}", f"{w['d_net']:.2f}",
            f"{w['cohort_A_net']:.2f}", f"{w['cohort_B_net']:.2f}",
            f"{w['cohort_B_net'] - w['cohort_A_net']:.2f}",
        ])
    _write_csv(
        os.path.join(OUT_DIR, "walkforward.csv"),
        ["pencere", "n", "kohort_1h", "net_A", "net_B", "d_net",
         "kohort_A_net", "kohort_B_net", "kohort_d_net"],
        wf_rows,
    )

    # yuvarlanmış JSON
    def _round_obj(o):
        if isinstance(o, float):
            return round(o, 4)
        if isinstance(o, dict):
            return {k: _round_obj(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_round_obj(v) for v in o]
        return o

    with open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(_round_obj(report), fh, ensure_ascii=False, indent=2)

    return report


def _print_report(r: dict) -> None:
    print(f"Örneklem {r['orneklem']['simule']:,} / {r['orneklem']['ham']:,} "
          f"({r['orneklem']['ilk']} → {r['orneklem']['son']})  "
          f"atlanan {r['orneklem']['atlanan']:,}")
    print(f"Kayıtlı 1h_close  n={r['kayitli_1h_close']['n']:,}  "
          f"WR %{r['kayitli_1h_close']['wr']:.1f}  "
          f"net ${r['kayitli_1h_close']['net']:+,.2f}")
    d = r["dogrulama_A"]
    print(f"Run A doğrulama  sebep %{d['sebep_ortusme_pct']:.1f}  "
          f"medyan sapma ${d['medyan_sapma']:.3f}  p90 ${d['p90_sapma']:.3f}")
    print()

    def _blk(title: str, totals: dict, by_exit: dict) -> None:
        print(f"── {title} ──")
        print(f"{'exit':16} {'n':>7} {'WR':>7} {'net':>12} {'ort':>8}")
        for name, s in by_exit.items():
            print(f"{name:16} {s['n']:>7,} {s['wr']:>6.1f}% "
                  f"{s['net']:>+12,.2f} {s['avg']:>+8.2f}")
        print(f"{'TOPLAM':16} {totals['n']:>7,} {totals['wr']:>6.1f}% "
              f"{totals['net']:>+12,.2f} {totals['avg']:>+8.2f}")
        print()

    _blk("Run A  ENABLE_1H_CLOSE_EXIT=True", r["A"]["totals"], r["A"]["by_exit"])
    _blk("Run B  ENABLE_1H_CLOSE_EXIT=False", r["B"]["totals"], r["B"]["by_exit"])

    dl = r["delta"]
    print("── A → B ──")
    print(f"  toplam net  ${r['A']['totals']['net']:+,.2f} → "
          f"${r['B']['totals']['net']:+,.2f}   fark ${dl['net']:+,.2f}")
    al, bl = dl["atr_loss"]["A"], dl["atr_loss"]["B"]
    print(f"  atr_loss    {al['n']:,} → {bl['n']:,}  "
          f"({dl['atr_loss']['dn']:+,})   "
          f"net ${al['net']:+,.2f} → ${bl['net']:+,.2f}  "
          f"({dl['atr_loss']['dnet']:+,.2f})")
    a4, b4 = dl["4h_close"]["A"], dl["4h_close"]["B"]
    print(f"  4h_close    {a4['n']:,} → {b4['n']:,}  "
          f"WR %{a4['wr']:.1f} → %{b4['wr']:.1f}  "
          f"net ${a4['net']:+,.2f} → ${b4['net']:+,.2f}")
    print()

    k = r["kohort_1h"]
    print(f"── Kohort: Run A'da 1h_close olan {k['n']:,} işlem ──")
    print(f"  A net ${k['A_net']:+,.2f}  →  B net ${k['B_net']:+,.2f}  "
          f"fark ${k['d_net']:+,.2f}")
    print(f"{'B exit':16} {'n':>7} {'pay':>7} {'WR':>7} {'net':>12} {'ort':>8}")
    for name, s in k["dagilim"].items():
        print(f"{name:16} {s['n']:>7,} {s['share']:>6.1f}% {s['wr']:>6.1f}% "
              f"{s['net']:>+12,.2f} {s['avg']:>+8.2f}")
    print()

    wf = r["walkforward"]
    print(f"── Walk-forward  split {wf['split']} (örneklem günlerinin ortası) ──")
    for label in ("erken", "gec"):
        w = wf[label]
        if not w:
            print(f"  {label}: yok")
            continue
        print(f"  {label:6} n={w['n']:,}  kohort={w['cohort_1h']:,}  "
              f"net A ${w['A']['net']:+,.2f} → B ${w['B']['net']:+,.2f}  "
              f"Δ ${w['d_net']:+,.2f}")
    print()
    print(f"CSV → {OUT_DIR}")


def main() -> None:
    p = argparse.ArgumentParser(description="1h_close A/B backtest (canlıya dokunmaz)")
    p.add_argument("--group", choices=list(sa.GROUPS), default="Test")
    args = p.parse_args()
    # Bayrak her iki değerde de koşar; sabit sadece dokümantasyon.
    global ENABLE_1H_CLOSE_EXIT
    ENABLE_1H_CLOSE_EXIT = True
    report = run(args.group)
    _print_report(report)


if __name__ == "__main__":
    main()
