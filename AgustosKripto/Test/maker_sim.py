#!/usr/bin/env python3
"""Maker fill simülasyonu — limit emirle giriş gerçekten kârlı mı.

Analog sinyal ürettiği anda piyasadan `offset` kadar uzağa limit emir konur.
1 dakikalık OHLC ile emrin `window` dakika içinde dolup dolmadığı ölçülür.
Dolan işlemler daha iyi fiyattan ve maker komisyonuyla girer — ama yalnızca
fiyat aleyhe döndüğünde dolar (ters seçilim). Bu iki etkinin net bakiyesi
ölçülür; kaçan (dolmayan) işlemlerin brüt edge'i ayrıca raporlanır.

  python3 AgustosKripto/Test/maker_sim.py --days 60 --sel 0.10
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from analog import AnalogIndex, load_bars, shape_vector, HOUR_MS  # noqa: E402
from minute_data import load_minutes  # noqa: E402

MAKER_FEE = 0.0002   # Binance USDⓈ-M maker
TAKER_FEE = 0.0005   # taker
OFFSETS = (0.0002, 0.0005, 0.0010, 0.0020)   # limit emrin piyasadan uzaklığı
WINDOWS = (5, 15, 30, 60)                    # fill bekleme süresi (dk)


def build_events(
    index: AnalogIndex,
    *,
    days: int,
    step: int,
    k: int,
    horizon: int,
    symbols: list[str] | None = None,
    require_minutes: bool = True,
) -> list[dict]:
    """Analog sorgularını walk-forward üret (sızıntısız).

    `require_minutes=False` yalnızca brüt edge ölçümü içindir — 1m cache'in
    kapsamadığı eski dönemlere de bakılabilsin diye.
    """
    hi = list(index.horizons).index(horizon)
    maxh = max(index.horizons)
    start = int(index.end_ts.max()) - days * 24 * HOUR_MS
    out: list[dict] = []

    for sym in (symbols or index.symbols):
        bars = load_bars(sym)
        mins = load_minutes(sym) if require_minutes else None
        if not bars or (require_minutes and (mins is None or len(mins["t"]) == 0)):
            continue
        cl = np.array([b["close"] for b in bars], dtype=np.float64)
        tm = np.array([b["open_time"] for b in bars], dtype=np.int64)
        sid = index.symbols.index(sym)
        # 1m cache'in kapsadığı aralıkla kesiş
        m_lo, m_hi = (int(mins["t"][0]), int(mins["t"][-1])) if mins is not None else (0, 1 << 62)
        lo = max(index.window - 1, int(np.searchsorted(tm, max(start, m_lo))))

        for i in range(lo, len(cl) - horizon, step):
            t_decision = int(tm[i]) + HOUR_MS          # kapanış anı = karar anı
            if t_decision < m_lo or t_decision > m_hi:
                continue
            v = shape_vector(cl[i - index.window + 1 : i + 1])
            if v is None:
                continue
            cut = int(np.searchsorted(
                index.end_ts, int(tm[i]) - (index.window + maxh) * HOUR_MS, side="right"
            ))
            if cut < k:
                continue
            corr = (index.shapes[:cut] @ v) / float(index.window)
            corr = np.where(index.sym_ids[:cut] != sid, corr, -np.inf)
            base_ret, _ = index.baseline(cut)
            sel = np.argpartition(-corr, k - 1)[:k]
            pred = float(index.fwd[sel, hi].mean()) - float(base_ret[hi])
            if pred == 0:
                continue
            out.append({
                "sym": sym,
                "t": t_decision,
                "p0": float(cl[i]),
                "exit": float(cl[i + horizon]),
                "long": pred > 0,
                "pred": pred,
            })
    return out


def _fill(
    mins: dict, t0: int, window_min: int, limit: float, is_long: bool, pen: float,
) -> tuple[bool, float | None]:
    """(doldu mu, pencere sonundaki fiyat).

    `pen` kuyruk önceliği payıdır: fiyatın limite dokunması yetmez, `pen` oranı
    kadar seviyeyi geçmesi istenir. 1m OHLC emrin sırada nerede olduğunu
    göstermediği için dokunuş fill saymak iyimserdir.
    """
    t = mins["t"]
    a = int(np.searchsorted(t, t0, side="left"))
    b = int(np.searchsorted(t, t0 + window_min * 60_000, side="left"))
    if b <= a:
        return False, None
    last = float(mins["close"][b - 1])
    if is_long:
        return bool(mins["low"][a:b].min() <= limit * (1 - pen)), last
    return bool(mins["high"][a:b].max() >= limit * (1 + pen)), last


def _cluster_se(pnl: np.ndarray, ts: np.ndarray) -> tuple[float, float]:
    """Zaman kümesine dayanıklı ortalama + standart hata."""
    if pnl.size == 0:
        return 0.0, 0.0
    grp = np.array([pnl[ts == u].mean() for u in np.unique(ts)])
    if grp.size < 2:
        return float(grp.mean()), 0.0
    return float(grp.mean()), float(grp.std(ddof=1) / np.sqrt(grp.size))


def simulate(events: list[dict], *, sel: float, pen: float = 0.0) -> dict:
    """Taker baseline vs maker varyantları."""
    if not events:
        return {"ok": False, "error": "olay yok"}

    pred = np.array([e["pred"] for e in events])
    thr = np.quantile(np.abs(pred), 1 - sel)
    ev = [e for e in events if abs(e["pred"]) >= thr]
    mins_cache = {s: load_minutes(s) for s in {e["sym"] for e in ev}}

    ts_all = np.array([e["t"] for e in ev])
    # Taker referansı: piyasa fiyatından gir, saatlik kapanışta çık
    gross_t = np.array([
        (e["exit"] - e["p0"]) / e["p0"] * (1 if e["long"] else -1) for e in ev
    ])
    mu_t, se_t = _cluster_se(gross_t - 2 * TAKER_FEE, ts_all)

    rows = []
    for off in OFFSETS:
        for win in WINDOWS:
            filled_pnl, filled_ts = [], []
            chase_pnl, chase_ts, missed_gross = [], [], []
            for e, g in zip(ev, gross_t):
                mins = mins_cache.get(e["sym"])
                if mins is None:
                    continue
                sign = 1 if e["long"] else -1
                limit = e["p0"] * (1 - off * sign)
                ok, last = _fill(mins, e["t"], win, limit, e["long"], pen)
                if ok:
                    r = (e["exit"] - limit) / limit * sign
                    filled_pnl.append(r - MAKER_FEE - TAKER_FEE)
                    filled_ts.append(e["t"])
                    continue
                missed_gross.append(g)
                if last:  # dolmadı → pencere sonunda piyasadan gir
                    chase_pnl.append((e["exit"] - last) / last * sign - 2 * TAKER_FEE)
                    chase_ts.append(e["t"])
            n = len(filled_pnl)
            if n < 20:
                continue
            mu_f, se_f = _cluster_se(np.array(filled_pnl), np.array(filled_ts))
            mu_c, _ = _cluster_se(np.array(chase_pnl), np.array(chase_ts))
            fr = n / len(ev)
            rows.append({
                "offset_pct": round(off * 100, 3),
                "window_min": win,
                "fill_rate": round(fr * 100, 1),
                "n_filled": n,
                "net_per_fill_pct": round(mu_f * 100, 4),
                "se_pct": round(se_f * 100, 4),
                "t": round(mu_f / se_f, 2) if se_f > 0 else None,
                # Dolmayan sinyal işlem açmaz → fırsat başına fill_rate ile ölçekli
                "net_per_signal_pct": round(mu_f * fr * 100, 4),
                # Dolmayanı pencere sonunda taker olarak kovala → her sinyal işlem olur
                "net_chase_pct": round((mu_f * fr + mu_c * (1 - fr)) * 100, 4),
                # Kaçanların brüt edge'i dolanlarınkinden yüksekse ters seçilim var
                "missed_gross_pct": round(float(np.mean(missed_gross)) * 100, 4) if missed_gross else None,
            })

    rows.sort(key=lambda r: -r["net_per_signal_pct"])
    return {
        "ok": True,
        "selectivity": sel,
        "penetration": pen,
        "signals": len(ev),
        "taker_net_per_signal_pct": round(mu_t * 100, 4),
        "taker_se_pct": round(se_t * 100, 4),
        "variants": rows,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Maker fill simülasyonu")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--step", type=int, default=6)
    p.add_argument("--k", type=int, default=5000)
    p.add_argument("--horizon", type=int, default=1)
    p.add_argument("--sel", type=float, default=0.10)
    p.add_argument("--pen", type=float, default=0.0,
                   help="kuyruk payı: fill için limitin bu oran kadar ötesine geçilmeli")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    cache = os.path.join(
        _DIR, "data",
        f"maker_events_d{args.days}_s{args.step}_k{args.k}_h{args.horizon}.json",
    )
    if os.path.exists(cache):
        with open(cache) as f:
            ev = json.load(f)
        print(f"olay cache: {len(ev)}", flush=True)
    else:
        idx = AnalogIndex.load()
        print(f"sinyal üretiliyor… ({args.days}g, adım {args.step}h, k={args.k})", flush=True)
        ev = build_events(idx, days=args.days, step=args.step, k=args.k, horizon=args.horizon)
        with open(cache, "w") as f:
            json.dump(ev, f)
    print(f"{len(ev)} olay · üst %{args.sel*100:.0f} seçilecek\n", flush=True)

    res = simulate(ev, sel=args.sel, pen=args.pen)
    if not res.get("ok"):
        print(res)
        return

    print(f"sinyal={res['signals']}  TAKER net/sinyal={res['taker_net_per_signal_pct']}% "
          f"(SE {res['taker_se_pct']}%)  ·  kuyruk payı={args.pen*100:.3f}%\n")
    print(f"{'offset':>8} {'pencere':>8} {'fill':>7} {'n':>6} {'net/fill':>10} {'t':>6} "
          f"{'net/sinyal':>11} {'kovala':>9} {'kaçan brüt':>12}")
    for r in res["variants"]:
        print(f"{r['offset_pct']:7.3f}% {r['window_min']:6}dk {r['fill_rate']:6.1f}% {r['n_filled']:6} "
              f"{r['net_per_fill_pct']:9.4f}% {str(r['t']):>6} {r['net_per_signal_pct']:10.4f}% "
              f"{r['net_chase_pct']:8.4f}% {str(r['missed_gross_pct']):>11}%")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(res, f, indent=2, ensure_ascii=False)
        print(f"\n→ {args.out}")


if __name__ == "__main__":
    main()
