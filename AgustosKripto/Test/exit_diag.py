#!/usr/bin/env python3
"""Çıkış rejimi teşhisi — kapanış sebebi tablosu neden yanıltıcı.

`jarvis_audit` çıkış tablosu "1h_close −$5.855" diyor; bu tek başına
"saatlik kapanış zarar ettiriyor" anlamına gelmez. ATR kâr kilidi
kazananları erken alıp götürdüğü için saatlik kapanışa artık kaybedenler
kalıyor olabilir (seçilim yanlılığı). Bu betik ayrımı ölçer.

    python3 AgustosKripto/Test/exit_diag.py
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
_AGUSTOS = os.path.dirname(_DIR)
if _AGUSTOS not in sys.path:
    sys.path.insert(0, _AGUSTOS)

import skill_audit as sa  # noqa: E402


def mfe_atr(t: dict) -> float | None:
    """Kaydedilmiş MFE — ATR katı cinsinden."""
    au = float(t.get("atr_usd") or 0)
    if au <= 0:
        return None
    return float(t.get("peak_upnl") or 0) / au


def hold_hours(t: dict) -> float | None:
    a, b = t.get("entry_time_tr"), t.get("exit_time_tr")
    if not a or not b:
        return None
    try:
        return (datetime.fromisoformat(str(b)) - datetime.fromisoformat(str(a))).total_seconds() / 3600
    except Exception:
        return None


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def by_reason(trades: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        buckets[t.get("close_reason") or "?"].append(t)
    out = []
    for name, rows in buckets.items():
        sp = sa.skill_split(rows)
        mfes = [m for m in (mfe_atr(t) for t in rows) if m is not None]
        holds = [h for h in (hold_hours(t) for t in rows) if h is not None]
        armed = sum(1 for t in rows if int(t.get("stop_level") or 0) >= 1)
        gross_pos = sum(1 for t in rows if float(t.get("pnl_gross") or 0) > 0)
        out.append({
            "sebep": name,
            "n": len(rows),
            "wr": 100.0 * sum(1 for t in rows if float(t.get("pnl") or 0) > 0) / len(rows),
            "wr_brut": 100.0 * gross_pos / len(rows),
            "net": sum(float(t.get("pnl") or 0) for t in rows),
            "brut": sum(float(t.get("pnl_gross") or 0) for t in rows),
            "kom": sum(float(t.get("commission") or 0) for t in rows),
            "mfe_ort": _mean(mfes),
            "mfe_medyan": sorted(mfes)[len(mfes) // 2] if mfes else 0.0,
            "mfe_0_5_alti_pct": 100.0 * sum(1 for m in mfes if m < 0.5) / len(mfes) if mfes else 0.0,
            "sure_ort": _mean(holds),
            "silahlanan_pct": 100.0 * armed / len(rows),
            "skill": sp["skill"] if sp else 0.0,
            "t": sp["t"] if sp else 0.0,
        })
    out.sort(key=lambda r: -r["n"])
    return out


def mfe_bands(trades: list[dict]) -> list[dict]:
    edges = [(0, 0.5), (0.5, 1.0), (1.0, 1.4), (1.4, 1.7), (1.7, 2.5), (2.5, 4.0), (4.0, 1e9)]
    out = []
    for lo, hi in edges:
        rows = [t for t in trades if (m := mfe_atr(t)) is not None and lo <= m < hi]
        if not rows:
            continue
        reasons: dict[str, int] = defaultdict(int)
        for t in rows:
            reasons[t.get("close_reason") or "?"] += 1
        out.append({
            "band": f"{lo}-{'∞' if hi > 100 else hi}",
            "n": len(rows),
            "net": sum(float(t.get("pnl") or 0) for t in rows),
            "brut": sum(float(t.get("pnl_gross") or 0) for t in rows),
            "kom": sum(float(t.get("commission") or 0) for t in rows),
            "wr": 100.0 * sum(1 for t in rows if float(t.get("pnl") or 0) > 0) / len(rows),
            "sebepler": dict(sorted(reasons.items(), key=lambda kv: -kv[1])[:3]),
        })
    return out


def commission_kill(trades: list[dict]) -> dict:
    """Brütte kazanan ama komisyondan sonra kaybeden işlemler."""
    killed = [t for t in trades
              if float(t.get("pnl_gross") or 0) > 0 and float(t.get("pnl") or 0) <= 0]
    gross_pos = [t for t in trades if float(t.get("pnl_gross") or 0) > 0]
    return {
        "brut_kazanan": len(gross_pos),
        "komisyonda_olen": len(killed),
        "oran": 100.0 * len(killed) / len(gross_pos) if gross_pos else 0.0,
        "kayip": sum(float(t.get("pnl") or 0) for t in killed),
    }


def main() -> None:
    groups = None
    if "--test" in sys.argv:
        groups = {"Test": sa.GROUPS["Test"]}
    trades = sa.load_trades(groups)
    print(f"İşlem: {len(trades):,}\n")

    print("── Kapanış sebebi (MFE ve silahlanma dahil) ──")
    hdr = (f"{'sebep':16} {'n':>6} {'WR':>6} {'WRbrüt':>7} {'net':>11} {'brüt':>10} "
           f"{'kom':>9} {'MFEort':>7} {'MFE<0.5':>8} {'silah%':>7} {'saat':>6} {'SKILL':>8}")
    print(hdr)
    for r in by_reason(trades):
        print(f"{r['sebep']:16} {r['n']:>6,} {r['wr']:>5.1f}% {r['wr_brut']:>6.1f}% "
              f"{r['net']:>+11,.0f} {r['brut']:>+10,.0f} {r['kom']:>9,.0f} "
              f"{r['mfe_ort']:>7.2f} {r['mfe_0_5_alti_pct']:>7.1f}% {r['silahlanan_pct']:>6.1f}% "
              f"{r['sure_ort']:>6.1f} {r['skill']:>+8.4f}")

    print("\n── MFE bandı → hangi sebeple kapandı ──")
    for b in mfe_bands(trades):
        print(f"{b['band']:>10} n={b['n']:>6,} net={b['net']:>+10,.0f} "
              f"brüt={b['brut']:>+10,.0f} kom={b['kom']:>8,.0f} WR={b['wr']:>5.1f}%  {b['sebepler']}")

    ck = commission_kill(trades)
    print(f"\n── Komisyon kıyımı ──\nBrütte kazanan {ck['brut_kazanan']:,} işlemin "
          f"{ck['komisyonda_olen']:,}'i (%{ck['oran']:.1f}) komisyondan sonra kaybediyor; "
          f"bu grubun neti ${ck['kayip']:+,.0f}")


if __name__ == "__main__":
    main()
