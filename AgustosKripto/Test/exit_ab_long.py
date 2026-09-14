#!/usr/bin/env python3
"""Uzun pencere 1h/4h A/B/C — yalnız backtest. Canlı dosyaya dokunmaz.

Run A: 1h_close + 4h_close (eski zaman çıkışı)
Run B: 1h_close kapalı, 4h_close açık
Run C: zaman kapanışı yok — 4h_close ATR trailing'e (mevcut kilit) bırakılır

Girişler: Mayıs–Ağu 1s sinyali (seçilmiş 1s defterler) + Ağustos canlı Test
geçmişi. 1m cache şart.

    python3 AgustosKripto/Test/exit_ab_long.py
    python3 AgustosKripto/Test/exit_ab_long.py --entries-only
    python3 AgustosKripto/Test/exit_ab_long.py --skip-entries
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
_AGUSTOS = os.path.dirname(_DIR)
_ROOT = os.path.dirname(_AGUSTOS)
for _p in (_DIR, _AGUSTOS, os.path.join(_ROOT, "temmuzPoly")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import exit_1h_close_ab as ab  # noqa: E402
import exit_lab as el  # noqa: E402
import minute_data as md  # noqa: E402
import skill_audit as sa  # noqa: E402
from atr_profit_lock import atr_from_klines, atr_usd  # noqa: E402
from catalog import ALL_BOOKS, TEST_SYMBOLS  # noqa: E402
from signals import signal_for_book  # noqa: E402

TR = timezone(timedelta(hours=3))
OUT = os.path.join(_DIR, "out_1h_close_ab_long")
ENTRY_FILE = os.path.join(OUT, "hist_entries.jsonl")

MARGIN, LEV, FEE = 100.0, 6.0, 0.0005
WARMUP = 80
HOUR_MS = 3_600_000

# 1s OHLCV defterleri — B1 türev / C101 / JARVIS / CEBU / PRO yok
ENTRY_UIDS = (
    "a2_05", "a2_04", "a2_08", "a2_10", "a2_12", "a2_14",
    "a1_10", "a1_21", "a1_09", "a1_11", "a1_39", "a1_07",
    "analiz1", "analiz6",
)

WINDOWS = (
    ("2026-05-18", "2026-05-26", "mayis"),
    ("2026-06-15", "2026-06-23", "haziran"),
    ("2026-07-13", "2026-07-21", "temmuz"),
    ("2026-08-07", "2026-08-15", "agustos_1h"),
    ("2026-08-15", "2026-08-24", "agustos_sonra"),
)


def _books() -> list[dict]:
    by = {b["uid"]: b for b in ALL_BOOKS}
    out = []
    for uid in ENTRY_UIDS:
        if uid in by:
            out.append(by[uid])
    return out


def _bar10(o, h, l, c, v, t) -> dict:
    return {
        "o": o, "h": h, "l": l, "c": c, "v": v, "t": int(t),
        "open": o, "high": h, "low": l, "close": c, "volume": v, "open_time": int(t),
    }


def resample_1h(sym: str) -> list[dict] | None:
    m = md.load_minutes(sym)
    if m is None or len(m["t"]) < 120:
        return None
    t = m["t"]
    hour = t - (t % HOUR_MS)
    cuts = np.concatenate(([0], np.flatnonzero(np.diff(hour)) + 1, [len(t)]))
    out = []
    hi, lo, cl = m["high"], m["low"], m["close"]
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b - a < 1:
            continue
        out.append(_bar10(
            float(cl[a]), float(np.max(hi[a:b])), float(np.min(lo[a:b])),
            float(cl[b - 1]), float(b - a), int(hour[a]),
        ))
    return out


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=TR).isoformat(timespec="seconds")


def generate_entries() -> list[dict]:
    books = _books()
    print(f"1s resample {len(TEST_SYMBOLS)} coin · {len(books)} defter", flush=True)
    series: dict[str, list[dict]] = {}
    for sym in TEST_SYMBOLS:
        bars = resample_1h(sym)
        if bars:
            series[sym] = bars
            print(f"  {sym:12} {len(bars):5} 1s  {_iso(bars[0]['t'])[:10]} → {_iso(bars[-1]['t'])[:10]}", flush=True)
    if not series:
        return []

    # ortak saat ızgarası
    all_t = sorted({b["t"] for bars in series.values() for b in bars})
    index = {sym: {b["t"]: i for i, b in enumerate(bars)} for sym, bars in series.items()}
    t0 = time.time()
    rows: list[dict] = []
    n_hours = 0
    for ti, ts in enumerate(all_t):
        if ti < WARMUP:
            continue
        kl: dict[str, list] = {}
        for sym, bars in series.items():
            bi = index[sym].get(ts)
            if bi is None or bi < 30:
                continue
            kl[sym] = bars[max(0, bi + 1 - 260):bi + 1]
        if len(kl) < 8:
            continue
        n_hours += 1
        day = _iso(ts)[:10]
        for book in books:
            try:
                sigs = signal_for_book(book, kl)
            except Exception:
                continue
            uid = book.get("uid") or "?"
            opened = 0
            for sym in TEST_SYMBOLS:
                d = sigs.get(sym)
                if d not in ("UP", "DOWN"):
                    continue
                bars = series.get(sym)
                bi = index.get(sym, {}).get(ts)
                if bars is None or bi is None:
                    continue
                px = float(bars[bi]["close"])
                if px <= 0:
                    continue
                atr = atr_from_klines(kl.get(sym) or [])
                notional = MARGIN * LEV
                qty = notional / px
                au = atr_usd(MARGIN, LEV, px, atr) if atr else 0.0
                side = "LONG" if d == "UP" else "SHORT"
                rows.append({
                    "symbol": sym,
                    "side": side,
                    "entry_price": px,
                    "entry_time_tr": _iso(ts),
                    "interval": "1h",
                    "qty": qty,
                    "notional": notional,
                    "entry_fee": notional * FEE,
                    "atr_usd": au,
                    "_bookfile": f"hist_{uid}",
                    "_group": "Hist",
                    "uid": uid,
                    "src": "hist",
                    "gun": day,
                })
                opened += 1
                if opened >= 4:
                    break
        if n_hours % 200 == 0:
            print(f"  saat {n_hours}  giriş {len(rows):,}  ({time.time()-t0:.0f}s)", flush=True)
    print(f"tarihsel giriş {len(rows):,}  {n_hours} saat  ({time.time()-t0:.0f}s)", flush=True)
    return rows


def live_entries() -> list[dict]:
    raw = sa.load_trades({"Test": sa.GROUPS["Test"]})
    out = []
    for t in raw:
        t = dict(t)
        t["src"] = "live"
        t["gun"] = str(t.get("entry_time_tr") or "")[:10]
        t["uid"] = (t.get("_bookfile") or "").replace("test_", "")
        out.append(t)
    return out


def simulate_regimes(trade: dict) -> dict[str, dict] | None:
    """Tek yürüyüş → A (1h+4h) · B (yalnız 4h) · C (zaman yok, ATR trail)."""
    pair = None
    # A/B mevcut sarmalayıcıdan; C için zaman adaylarını düş.
    # Ortak yürüyüşü burada bir kez kur — exit_1h_close_ab.simulate_pair A/B verir.
    ab_pair = ab.simulate_pair(trade)
    if ab_pair is None:
        return None
    a, b = ab_pair

    # C: A/B ile aynı ATR adayları, zaman yok. simulate_pair common'ı dışarı
    # vermediği için C'yi aynı fiyat yoluyla tekrar seçmek yerine
    # enable_1h=False + enable_4h=False ile ikinci bir yürüyüş.
    c = _simulate_no_time(trade)
    if c is None:
        return None
    return {"A": a, "B": b, "C": c}


def _simulate_no_time(trade: dict) -> dict | None:
    """Run C — 1h/4h yok, ATR kilit + zarar + max_hold."""
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
    horizon = int(ab._MAX_HOLD_H * 60) + 2
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
    cands: list[tuple[int, str]] = []
    armed_at = None
    if au > 0:
        peak = np.maximum.accumulate(net_u)
        armed_at = el._first_true(peak >= ab._ARM * au)
        if armed_at is not None:
            stop_arr = np.maximum(peak - ab._TRAIL * au, ab._LOCK_MIN * au)
            hit = el._first_true(net_u <= stop_arr, armed_at)
            if hit is not None:
                cands.append((hit, "atr_stop"))
        age_ok = (ts - t_entry) >= el.LOSS_MIN_AGE_MIN * el.MIN_MS
        loss_mask = age_ok & (net_u <= -ab._LOSS_MULT * au)
        if armed_at is not None:
            loss_mask[armed_at:] = False
        hit = el._first_true(loss_mask)
        if hit is not None:
            cands.append((hit, "atr_loss"))
    cands.append((net_u.size - 1, "max_hold"))
    i, reason = min(cands, key=lambda x: (x[0], x[1] != "atr_loss"))
    return {
        "net": float(net_u[i]),
        "brut": float(gross[i]),
        "kom": float(entry_fee + exit_fee[i]),
        "sebep": reason,
        "saat": float((ts[i] - t_entry) / el.HOUR_MS),
        "ret_pct": float(sign * (px[i] - entry) / entry * 100.0),
        "side": trade.get("side"),
    }


def _totals(rows: list[dict]) -> dict:
    return ab._totals(rows)


def _agg(rows: list[dict]) -> dict:
    return ab._agg(rows)


def sol_regime(lo: str, hi: str) -> dict:
    bars = resample_1h("SOLUSDT") or []
    win = [b for b in bars if lo <= _iso(b["t"])[:10] < hi]
    if len(win) < 10:
        return {"etiket": "yetersiz", "ret": 0.0, "vol": 0.0, "n": 0}
    rets = []
    for a, b in zip(win, win[1:]):
        if a["c"] > 0:
            rets.append((b["c"] - a["c"]) / a["c"])
    ret = 100.0 * (win[-1]["c"] / win[0]["o"] - 1.0) if win[0]["o"] else 0.0
    vol = 100.0 * float(np.std(rets) * np.sqrt(24)) if rets else 0.0
    if vol >= 4.5:
        tag = "yuksek_vol"
    elif abs(ret) >= 8:
        tag = "trend"
    else:
        tag = "range"
    return {"etiket": tag, "ret": ret, "vol": vol, "n": len(win)}


def _window_of(gun: str) -> str:
    for lo, hi, name in WINDOWS:
        if lo <= gun < hi:
            return name
    return "diger"


def run(entries: list[dict]) -> dict:
    paired = []
    skip = 0
    for t in entries:
        r = simulate_regimes(t)
        if r is None:
            skip += 1
            continue
        gun = t.get("gun") or str(t.get("entry_time_tr") or "")[:10]
        paired.append({
            "gun": gun,
            "pencere": _window_of(gun),
            "src": t.get("src"),
            "uid": t.get("uid"),
            "symbol": (t.get("symbol") or "").upper(),
            "A": r["A"], "B": r["B"], "C": r["C"],
        })

    def pack(subset: list[dict], label: str) -> dict:
        out = {"label": label, "n": len(subset)}
        for key in ("A", "B", "C"):
            rows = [p[key] for p in subset]
            tot = _totals(rows)
            out[key] = {"totals": tot, "by_exit": _agg(rows)}
        out["d_BA"] = out["B"]["totals"]["net"] - out["A"]["totals"]["net"]
        out["d_CA"] = out["C"]["totals"]["net"] - out["A"]["totals"]["net"]
        out["d_CB"] = out["C"]["totals"]["net"] - out["B"]["totals"]["net"]
        cohort = [p for p in subset if p["A"]["sebep"] == "1h_close"]
        dest: dict[str, list] = defaultdict(list)
        dest4: dict[str, list] = defaultdict(list)
        for p in cohort:
            dest[p["B"]["sebep"]].append(p["B"])
        for p in subset:
            if p["B"]["sebep"] == "4h_close":
                dest4[p["C"]["sebep"]].append(p["C"])
        out["kohort_1h"] = {
            "n": len(cohort),
            "A_net": sum(p["A"]["net"] for p in cohort),
            "B_net": sum(p["B"]["net"] for p in cohort),
            "C_net": sum(p["C"]["net"] for p in cohort),
            "B_dagilim": _agg([{"sebep": k, **x} for k, rs in dest.items() for x in rs]),
        }
        out["kohort_4h"] = {
            "n": sum(len(v) for v in dest4.values()),
            "B_net": sum(p["B"]["net"] for p in subset if p["B"]["sebep"] == "4h_close"),
            "C_net": sum(sum(x["net"] for x in rs) for rs in dest4.values()),
            "C_dagilim": _agg([{"sebep": k, **x} for k, rs in dest4.items() for x in rs]),
        }
        return out

    report = {
        "olusturma": datetime.now(TR).isoformat(timespec="seconds"),
        "orneklem": {
            "giris": len(entries),
            "simule": len(paired),
            "atlanan": skip,
            "ilk": min((p["gun"] for p in paired), default=""),
            "son": max((p["gun"] for p in paired), default=""),
        },
        "tam": pack(paired, "tam"),
        "pencereler": {},
    }
    for lo, hi, name in WINDOWS:
        sub = [p for p in paired if p["pencere"] == name]
        rg = sol_regime(lo, hi)
        blk = pack(sub, name)
        blk["rejim"] = rg
        blk["tarih"] = f"{lo} → {hi}"
        report["pencereler"][name] = blk
    diger = [p for p in paired if p["pencere"] == "diger"]
    if diger:
        report["pencereler"]["diger"] = pack(diger, "diger")
    return report


def _write_csvs(report: dict) -> None:
    os.makedirs(OUT, exist_ok=True)

    def money(v):
        return f"{float(v):.2f}"

    # tam A/B/C by exit
    rows = []
    tam = report["tam"]
    names = sorted({
        *tam["A"]["by_exit"], *tam["B"]["by_exit"], *tam["C"]["by_exit"]
    }, key=lambda n: -tam["A"]["by_exit"].get(n, {}).get("n", 0))
    for name in names + ["TOPLAM"]:
        rec = [name]
        for key in ("A", "B", "C"):
            if name == "TOPLAM":
                s = tam[key]["totals"]
            else:
                s = tam[key]["by_exit"].get(name, {"n": 0, "wr": 0, "net": 0, "avg": 0})
            rec += [s["n"], f"{s['wr']:.1f}", money(s["net"]), money(s["avg"])]
        rows.append(rec)
    ab._write_csv(
        os.path.join(OUT, "abc_by_exit.csv"),
        ["exit",
         "n_A", "wr_A", "net_A", "avg_A",
         "n_B", "wr_B", "net_B", "avg_B",
         "n_C", "wr_C", "net_C", "avg_C"],
        rows,
    )

    wrows = []
    for name, blk in report["pencereler"].items():
        rg = blk.get("rejim") or {}
        wrows.append([
            name, blk.get("tarih", ""), rg.get("etiket", ""),
            f"{rg.get('ret', 0):.1f}", f"{rg.get('vol', 0):.2f}",
            blk["n"],
            money(blk["A"]["totals"]["net"]),
            money(blk["B"]["totals"]["net"]),
            money(blk["C"]["totals"]["net"]),
            money(blk["d_BA"]), money(blk["d_CA"]), money(blk["d_CB"]),
            blk["kohort_1h"]["n"], money(blk["kohort_1h"]["A_net"]),
            money(blk["kohort_1h"]["B_net"]), money(blk["kohort_1h"]["C_net"]),
            blk["kohort_4h"]["n"], money(blk["kohort_4h"]["B_net"]),
            money(blk["kohort_4h"]["C_net"]),
        ])
    ab._write_csv(
        os.path.join(OUT, "windows.csv"),
        ["pencere", "tarih", "rejim", "sol_ret_pct", "sol_vol",
         "n", "net_A", "net_B", "net_C", "d_BA", "d_CA", "d_CB",
         "kohort_1h_n", "kohort_1h_A", "kohort_1h_B", "kohort_1h_C",
         "kohort_4h_n", "kohort_4h_B", "kohort_4h_C"],
        wrows,
    )

    k1 = tam["kohort_1h"]
    drows = []
    for name, s in k1["B_dagilim"].items():
        drows.append([name, s["n"], f"{s['wr']:.1f}", money(s["net"]), money(s["avg"])])
    ab._write_csv(os.path.join(OUT, "cohort_1h_to_B.csv"),
                  ["B_exit", "n", "wr", "net", "avg"], drows)

    k4 = tam["kohort_4h"]
    d4 = []
    for name, s in k4["C_dagilim"].items():
        d4.append([name, s["n"], f"{s['wr']:.1f}", money(s["net"]), money(s["avg"])])
    ab._write_csv(os.path.join(OUT, "cohort_4h_to_C.csv"),
                  ["C_exit", "n", "wr", "net", "avg"], d4)

    def _rnd(o):
        if isinstance(o, float):
            return round(o, 4)
        if isinstance(o, dict):
            return {k: _rnd(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_rnd(v) for v in o]
        return o

    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(_rnd(report), fh, ensure_ascii=False, indent=2)


def _print(report: dict) -> None:
    o = report["orneklem"]
    print(f"\nÖrneklem {o['simule']:,} / {o['giris']:,}  {o['ilk']} → {o['son']}  "
          f"atlanan {o['atlanan']:,}")
    tam = report["tam"]
    print(f"\n{'run':6} {'n':>7} {'WR':>7} {'net':>12} {'ort':>8}")
    for key, title in (("A", "A 1h+4h"), ("B", "B 4h"), ("C", "C ATR")):
        t = tam[key]["totals"]
        print(f"{title:6} {t['n']:>7,} {t['wr']:>6.1f}% {t['net']:>+12,.2f} {t['avg']:>+8.2f}")
        for name, s in tam[key]["by_exit"].items():
            print(f"   {name:12} {s['n']:>7,} {s['wr']:>6.1f}% {s['net']:>+12,.2f} {s['avg']:>+8.2f}")
    print(f"\nΔ B−A ${tam['d_BA']:+,.2f}   Δ C−A ${tam['d_CA']:+,.2f}   "
          f"Δ C−B ${tam['d_CB']:+,.2f}")

    print("\n── Pencereler (işaret tutarlı mı) ──")
    print(f"{'pencere':10} {'rejim':12} {'n':>6} {'A':>10} {'B':>10} {'C':>10} "
          f"{'B−A':>9} {'C−A':>9}")
    for name, blk in report["pencereler"].items():
        rg = (blk.get("rejim") or {}).get("etiket", "")
        print(f"{name:10} {rg:12} {blk['n']:>6,} "
              f"{blk['A']['totals']['net']:>+10,.0f} "
              f"{blk['B']['totals']['net']:>+10,.0f} "
              f"{blk['C']['totals']['net']:>+10,.0f} "
              f"{blk['d_BA']:>+9,.0f} {blk['d_CA']:>+9,.0f}")

    k4 = tam["kohort_4h"]
    print(f"\n── B'de 4h_close olan {k4['n']:,} işlem C'de ──")
    print(f"  B net ${k4['B_net']:+,.2f}  →  C net ${k4['C_net']:+,.2f}  "
          f"Δ ${k4['C_net'] - k4['B_net']:+,.2f}")
    for name, s in k4["C_dagilim"].items():
        print(f"   {name:12} {s['n']:>7,} {s['wr']:>6.1f}% {s['net']:>+12,.2f}")
    print(f"\nCSV → {OUT}")


def save_entries(rows: list[dict]) -> None:
    os.makedirs(OUT, exist_ok=True)
    with open(ENTRY_FILE, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"yazıldı {ENTRY_FILE}  {len(rows):,}")


def load_entries() -> list[dict]:
    if not os.path.exists(ENTRY_FILE):
        return []
    out = []
    with open(ENTRY_FILE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--entries-only", action="store_true")
    p.add_argument("--skip-entries", action="store_true")
    p.add_argument("--no-live", action="store_true")
    args = p.parse_args()

    if args.skip_entries:
        hist = load_entries()
        print(f"kayıtlı tarihsel giriş {len(hist):,}")
    else:
        hist = generate_entries()
        save_entries(hist)
        if args.entries_only:
            return

    live = [] if args.no_live else live_entries()
    # canlı Ağustos + tarihsel (canlıyı çift saymamak için hist'i mayıs-temmuz + ağustos hist)
    # Ağustos canlı zaten var; hist ağustos'u da üretir → ağustos hist'i düş, canlı kalsın
    hist_keep = [t for t in hist if (t.get("gun") or "") < "2026-08-07"]
    entries = hist_keep + live
    print(f"giriş havuzu  hist {len(hist_keep):,} + canlı {len(live):,} = {len(entries):,}")
    report = run(entries)
    _write_csvs(report)
    _print(report)


if __name__ == "__main__":
    main()
