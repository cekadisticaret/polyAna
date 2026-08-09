#!/usr/bin/env python3
"""Analog eşleştirme — son N mumun şekli geçmişte nerede görüldü, sonra ne oldu.

Mum kapanışları pencere içinde z-score'a çevrilir (fiyat seviyesinden ve
oynaklıktan bağımsız saf şekil). Tüm geçmiş pencereler tek matriste tutulur;
sorgu, korelasyona indirgenen tek matris-vektör çarpımıyla çözülür.

Çıktı yön değil dağılımdır: "en benzer 100 durumun 73'ü yükselmiş, medyan +%0.4".
Bu, mevcut sinyallere güven filtresi olarak takılmak içindir.

  python3 AgustosKripto/Test/analog.py build
  python3 AgustosKripto/Test/analog.py query BTCUSDT
  python3 AgustosKripto/Test/analog.py eval --days 90
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

CACHE_DIR = os.path.join(_DIR, "data", "backtest_cache")
INDEX_PATH = os.path.join(_DIR, "data", "analog_index.npz")

WINDOW = 48          # sorgu penceresi (saat)
HORIZONS = (1, 4, 8)  # ileri bakış (saat)
TOP_K = 100
HOUR_MS = 3_600_000


def _symbols() -> list[str]:
    import importlib.util as ilu

    spec = ilu.spec_from_file_location("kripto_test_catalog", os.path.join(_DIR, "catalog.py"))
    mod = ilu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return list(mod.TEST_SYMBOLS)


def load_bars(sym: str) -> list[dict] | None:
    path = os.path.join(CACHE_DIR, f"{sym}_1h.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def shape_vector(closes: np.ndarray) -> np.ndarray | None:
    """Pencere kapanışları → z-score şekil vektörü (ortalama 0, std 1)."""
    sd = closes.std()
    if not np.isfinite(sd) or sd <= 0:
        return None
    return ((closes - closes.mean()) / sd).astype(np.float32)


class AnalogIndex:
    """Tüm coinlerin geçmiş pencereleri + ileri getirileri."""

    def __init__(
        self,
        shapes: np.ndarray,
        fwd: np.ndarray,
        sym_ids: np.ndarray,
        end_ts: np.ndarray,
        vols: np.ndarray,
        symbols: list[str],
        window: int,
        horizons: tuple[int, ...],
    ) -> None:
        self.shapes = shapes      # (N, W) float32, z-score
        self.fwd = fwd            # (N, H) float32, ileri getiri oranı
        self.sym_ids = sym_ids    # (N,) int16
        self.end_ts = end_ts      # (N,) int64 — pencerenin son mumunun open_time
        self.vols = vols          # (N,) float32 — pencere içi getiri std
        self.symbols = symbols
        self.window = window
        self.horizons = tuple(horizons)
        # Baz oran O(1) okunsun — sorgu diliminin koşulsuz dağılımı
        f64 = self.fwd.astype(np.float64)
        z = np.zeros((1, f64.shape[1]))
        self._cum_ret = np.vstack([z, np.cumsum(f64, axis=0)])
        self._cum_up = np.vstack([z, np.cumsum(f64 > 0, axis=0)])

    def baseline(self, cut: int) -> tuple[np.ndarray, np.ndarray]:
        """İlk `cut` pencerenin koşulsuz (ort. getiri, yukarı oranı) değerleri."""
        c = max(int(cut), 1)
        return self._cum_ret[c] / c, self._cum_up[c] / c

    def __len__(self) -> int:
        return int(self.shapes.shape[0])

    def save(self, path: str = INDEX_PATH) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        np.savez_compressed(
            path,
            shapes=self.shapes,
            fwd=self.fwd,
            sym_ids=self.sym_ids,
            end_ts=self.end_ts,
            vols=self.vols,
            symbols=np.array(self.symbols),
            window=self.window,
            horizons=np.array(self.horizons),
        )

    @classmethod
    def load(cls, path: str = INDEX_PATH) -> "AnalogIndex":
        d = np.load(path, allow_pickle=False)
        return cls(
            shapes=d["shapes"],
            fwd=d["fwd"],
            sym_ids=d["sym_ids"],
            end_ts=d["end_ts"],
            vols=d["vols"],
            symbols=[str(s) for s in d["symbols"]],
            window=int(d["window"]),
            horizons=tuple(int(h) for h in d["horizons"]),
        )

    def query(
        self,
        q_shape: np.ndarray,
        *,
        k: int = TOP_K,
        before_ts: int | None = None,
        exclude_sym: str | None = None,
        min_corr: float = 0.0,
    ) -> dict | None:
        """En benzer k pencereyi bul, ileri getiri dağılımını döndür.

        before_ts verilirse yalnızca sonucu o ana kadar bilinen pencereler
        eşleşir (pencere boyu + en uzun ufuk kadar geriden) — sızıntı önlenir.
        """
        n = len(self)
        if n == 0:
            return None
        # end_ts artan sıralı → zaman filtresi bitişik dilime iner
        cut = n
        if before_ts is not None:
            cutoff = int(before_ts) - (self.window + max(self.horizons)) * HOUR_MS
            cut = int(np.searchsorted(self.end_ts, cutoff, side="right"))
        if cut < k:
            return None

        # Satırlar z-score olduğu için nokta çarpım / W = korelasyon
        corr = (self.shapes[:cut] @ q_shape.astype(np.float32)) / float(self.window)
        if exclude_sym and exclude_sym in self.symbols:
            sid = self.symbols.index(exclude_sym)
            corr = np.where(self.sym_ids[:cut] != sid, corr, -np.inf)

        valid = int(np.isfinite(corr).sum())
        if valid == 0:
            return None
        k = min(k, valid)
        idx = np.argpartition(-corr, k - 1)[:k]
        idx = idx[np.argsort(-corr[idx])]
        c = corr[idx]
        if min_corr > 0:
            keep = c >= min_corr
            idx, c = idx[keep], c[keep]
            if idx.size == 0:
                return None

        base_ret, base_up = self.baseline(cut)
        out: dict = {
            "matched": int(idx.size),
            "mean_corr": round(float(c.mean()), 4),
            "min_corr": round(float(c.min()), 4),
        }
        for hi, h in enumerate(self.horizons):
            r = self.fwd[idx, hi].astype(np.float64)
            up = float((r > 0).mean())
            # Kripto saatlik baz yukarı oranı %50 değil (~%48.5) — edge baza göre
            out[f"h{h}"] = {
                "up_pct": round(up * 100, 1),
                "base_up_pct": round(float(base_up[hi]) * 100, 1),
                "up_edge": round((up - float(base_up[hi])) * 100, 2),
                "median": round(float(np.median(r)) * 100, 4),
                "mean": round(float(r.mean()) * 100, 4),
                "mean_edge": round((float(r.mean()) - float(base_ret[hi])) * 100, 4),
                "std": round(float(r.std()) * 100, 4),
            }
        h1 = out[f"h{self.horizons[0]}"]
        edge = h1["up_edge"]
        out["signal"] = "UP" if edge > 0 else "DOWN" if edge < 0 else "NEUTRAL"
        # Baz orandan sapma; %10 puan sapma → 1.0 güven
        out["conviction"] = round(min(abs(edge) / 10.0, 1.0), 4)
        return out


def build_index(
    symbols: list[str] | None = None,
    *,
    window: int = WINDOW,
    horizons: tuple[int, ...] = HORIZONS,
    verbose: bool = True,
) -> AnalogIndex:
    symbols = symbols or _symbols()
    max_h = max(horizons)
    shapes_l, fwd_l, sym_l, ts_l, vol_l = [], [], [], [], []
    used: list[str] = []

    for sym in symbols:
        bars = load_bars(sym)
        if not bars or len(bars) < window + max_h + 1:
            if verbose:
                print(f"  {sym}: cache yok/kısa — atlandı")
            continue
        sid = len(used)
        used.append(sym)
        closes = np.array([b["close"] for b in bars], dtype=np.float64)
        times = np.array([b["open_time"] for b in bars], dtype=np.int64)
        rets = np.diff(closes) / closes[:-1]

        n_ok = 0
        for i in range(window - 1, len(closes) - max_h):
            w = closes[i - window + 1 : i + 1]
            v = shape_vector(w)
            if v is None:
                continue
            entry = closes[i]
            shapes_l.append(v)
            fwd_l.append([(closes[i + h] - entry) / entry for h in horizons])
            sym_l.append(sid)
            ts_l.append(times[i])
            vol_l.append(rets[i - window + 1 : i].std())
            n_ok += 1
        if verbose:
            print(f"  {sym}: {n_ok} pencere")

    if not shapes_l:
        raise SystemExit("cache boş — önce backtest_1y.py ile veri çek")

    # Zaman sıralı tut — sorguda sızıntı filtresi searchsorted dilimine iner
    order = np.argsort(np.array(ts_l, dtype=np.int64), kind="stable")
    idx = AnalogIndex(
        shapes=np.vstack(shapes_l)[order],
        fwd=np.array(fwd_l, dtype=np.float32)[order],
        sym_ids=np.array(sym_l, dtype=np.int16)[order],
        end_ts=np.array(ts_l, dtype=np.int64)[order],
        vols=np.array(vol_l, dtype=np.float32)[order],
        symbols=used,
        window=window,
        horizons=horizons,
    )
    if verbose:
        mb = idx.shapes.nbytes / 1e6
        print(f"\ntoplam {len(idx):,} pencere · {len(used)} coin · {mb:.0f} MB")
    return idx


def query_symbol(
    sym: str,
    index: AnalogIndex | None = None,
    *,
    bars: list[dict] | None = None,
    k: int = TOP_K,
    exclude_self: bool = False,
) -> dict | None:
    """Bir coinin son penceresi için analog sorgusu."""
    index = index or AnalogIndex.load()
    bars = bars or load_bars(sym)
    if not bars or len(bars) < index.window:
        return None
    closes = np.array([b["close"] for b in bars[-index.window :]], dtype=np.float64)
    v = shape_vector(closes)
    if v is None:
        return None
    res = index.query(
        v, k=k,
        before_ts=int(bars[-1]["open_time"]),
        exclude_sym=sym if exclude_self else None,
    )
    if res:
        res["symbol"] = sym
        res["as_of"] = int(bars[-1]["open_time"])
    return res


def evaluate(
    *,
    days: int = 90,
    k: int = TOP_K,
    horizon: int = 1,
    symbols: list[str] | None = None,
    index: AnalogIndex | None = None,
    step: int = 1,
) -> dict:
    """Walk-forward doğrulama — güven skoru gerçekten isabetle ilişkili mi?

    Her sorgu yalnızca kendinden önce sonucu belli olmuş pencerelerle eşleşir.
    """
    index = index or AnalogIndex.load()
    symbols = symbols or index.symbols
    hi = index.horizons.index(horizon)
    max_ts = int(index.end_ts.max())
    start_ts = max_ts - days * 24 * HOUR_MS

    rows: list[tuple[float, bool, float, int, float]] = []
    for sym in symbols:
        bars = load_bars(sym)
        if not bars:
            continue
        closes = np.array([b["close"] for b in bars], dtype=np.float64)
        times = np.array([b["open_time"] for b in bars], dtype=np.int64)
        lo = max(index.window - 1, int(np.searchsorted(times, start_ts)))
        for i in range(lo, len(closes) - horizon, step):
            v = shape_vector(closes[i - index.window + 1 : i + 1])
            if v is None:
                continue
            res = index.query(v, k=k, before_ts=int(times[i]), exclude_sym=sym)
            if not res or res["signal"] == "NEUTRAL":
                continue
            actual = (closes[i + horizon] - closes[i]) / closes[i]
            up = res["signal"] == "UP"
            hit = (actual > 0) if up else (actual < 0)
            signed = actual if up else -actual
            rows.append((res["conviction"], hit, signed, 1 if up else 0, actual))

    if not rows:
        return {"ok": False, "error": "örnek yok"}

    conv = np.array([r[0] for r in rows])
    hits = np.array([r[1] for r in rows], dtype=bool)
    sret = np.array([r[2] for r in rows])
    is_up = np.array([r[3] for r in rows], dtype=bool)
    actual = np.array([r[4] for r in rows])

    # Referans: örneklemde gerçek yukarı oranı — tek yöne basan aptal tahminci
    base_up = float((actual > 0).mean())
    naive = max(base_up, 1 - base_up)

    buckets = []
    edges = [0.0, 0.1, 0.2, 0.3, 0.4, 1.01]
    for a, b in zip(edges[:-1], edges[1:]):
        m = (conv >= a) & (conv < b)
        if not m.any():
            continue
        buckets.append({
            "conviction": f"{a:.1f}-{min(b,1.0):.1f}",
            "n": int(m.sum()),
            "hit_rate": round(float(hits[m].mean()) * 100, 1),
            "avg_move_pct": round(float(sret[m].mean()) * 100, 4),
            "up_signals_pct": round(float(is_up[m].mean()) * 100, 1),
        })

    return {
        "ok": True,
        "days": days,
        "horizon_h": horizon,
        "k": k,
        "window": index.window,
        "samples": len(rows),
        "sample_up_rate": round(base_up * 100, 2),
        "naive_baseline": round(naive * 100, 2),
        "overall_hit_rate": round(float(hits.mean()) * 100, 1),
        "overall_avg_move_pct": round(float(sret.mean()) * 100, 4),
        "up_signals_pct": round(float(is_up.mean()) * 100, 1),
        "buckets": buckets,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Analog pencere eşleştirme")
    p.add_argument("cmd", choices=["build", "query", "eval"])
    p.add_argument("symbol", nargs="?", default="BTCUSDT")
    p.add_argument("--window", type=int, default=WINDOW)
    p.add_argument("--k", type=int, default=TOP_K)
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--horizon", type=int, default=1)
    p.add_argument("--step", type=int, default=1)
    args = p.parse_args()

    if args.cmd == "build":
        idx = build_index(window=args.window)
        idx.save()
        print(f"kaydedildi → {INDEX_PATH}")
        return

    if args.cmd == "query":
        res = query_symbol(args.symbol, k=args.k, exclude_self=False)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    res = evaluate(days=args.days, k=args.k, horizon=args.horizon, step=args.step)
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
