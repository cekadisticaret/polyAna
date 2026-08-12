#!/usr/bin/env python3
"""Drift-nötr beceri denetimi — kripto sanal defterleri.

Neden gerekli: kazanma oranı (WR) ve toplam PnL, örneklem dönemindeki piyasa
yönünü ölçüyor, algoritmanın becerisini ölçmüyor. Örnek: ADAUSDT SHORT
t=8,68 ile mükemmel görünüyordu; LONG/SHORT ayrıştırıldığında
LONG −0,1409% / SHORT +0,1485% çıktı — yani simetrik, becerisi ~0.
ADA düşmüş, algoritma bilmiyordu.

Ayrıştırma:
    SKILL = (ort.LONG + ort.SHORT) / 2   → zamanlama becerisi
    DRIFT = (ort.SHORT − ort.LONG) / 2   → dönem içi fiyat eğilimi

Getiriler kaldıraçsız yüzde olarak hesaplanır, böylece teminat/kaldıraç
farkı olan defterler karşılaştırılabilir.

CLI:
  python3 AgustosKripto/skill_audit.py                 # özet
  python3 AgustosKripto/skill_audit.py --books         # defter sıralaması
  python3 AgustosKripto/skill_audit.py --coins --mfe
  python3 AgustosKripto/skill_audit.py --json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))

GROUPS = {
    "Test": os.path.join(_DIR, "Test", "data"),
    "Algoritmalar": os.path.join(_DIR, "Algoritmalar", "data"),
    "Analizler": os.path.join(_DIR, "Analizler", "data"),
}

# Binance USDⓈ-M gidiş-dönüş komisyonu (taker %0.05 ×2 / maker %0.02 ×2)
TAKER_ROUNDTRIP_PCT = 0.10
MAKER_ROUNDTRIP_PCT = 0.04

# Bir defterin/coin'in "kenarı var" sayılabilmesi için asgari şartlar.
# 5 günlük veriyle hiçbir şey doğrulanamaz; bu eşikler 60 günlük
# pencerede anlam kazanır.
MIN_TRADES = 100
MIN_T_STAT = 2.0
MIN_SKILL_PCT = 0.04  # maker maliyetini aşan asgari kenar


# ── veri yükleme ──────────────────────────────────────────────


def load_trades(groups: dict | None = None) -> list[dict]:
    """Tüm defterlerin kapanmış işlemlerini tek listede döndür."""
    out = []
    for group, ddir in (groups or GROUPS).items():
        for path in sorted(glob.glob(os.path.join(ddir, "*_history.json"))):
            book_file = os.path.basename(path).replace("_history.json", "")
            try:
                with open(path) as f:
                    rows = json.load(f)
            except Exception:
                continue
            if not isinstance(rows, list):
                continue
            for r in rows:
                if not isinstance(r, dict):
                    continue
                if r.get("pnl") is None or not r.get("exit_price"):
                    continue
                r["_group"] = group
                r["_bookfile"] = book_file
                out.append(r)
    return out


def ret_pct(trade: dict) -> float | None:
    """Kaldıraçsız yüzde getiri — yön düzeltmeli."""
    try:
        entry = float(trade["entry_price"])
        exit_ = float(trade["exit_price"])
    except (KeyError, TypeError, ValueError):
        return None
    if entry <= 0:
        return None
    move = (exit_ - entry) / entry * 100.0
    return move if trade.get("side") == "LONG" else -move


# ── istatistik ────────────────────────────────────────────────


def stats(values: list[float]) -> dict | None:
    n = len(values)
    if not n:
        return None
    mean = sum(values) / n
    if n > 1:
        var = sum((v - mean) ** 2 for v in values) / n
        sd = var ** 0.5
    else:
        sd = 0.0
    t = (mean / (sd / n ** 0.5)) if sd > 0 else 0.0
    wins = sum(1 for v in values if v > 0)
    return {
        "n": n,
        "mean": mean,
        "sd": sd,
        "t": t,
        "wr": 100.0 * wins / n,
    }


def skill_split(rows: list[dict]) -> dict | None:
    """LONG/SHORT ayrıştırmasıyla SKILL ve DRIFT."""
    longs, shorts = [], []
    for r in rows:
        v = ret_pct(r)
        if v is None:
            continue
        if r.get("side") == "LONG":
            longs.append(v)
        elif r.get("side") == "SHORT":
            shorts.append(v)
    if not longs or not shorts:
        return None
    sl, ss = stats(longs), stats(shorts)
    combined = stats(longs + shorts)
    skill = (sl["mean"] + ss["mean"]) / 2
    drift = (ss["mean"] - sl["mean"]) / 2
    return {
        "n": combined["n"],
        "n_long": sl["n"],
        "n_short": ss["n"],
        "mean_long": sl["mean"],
        "mean_short": ss["mean"],
        "skill": skill,
        "drift": drift,
        "t": combined["t"],
        "sd": combined["sd"],
        "wr": combined["wr"],
        "both_positive": sl["mean"] > 0 and ss["mean"] > 0,
        "net_pnl": sum(float(r.get("pnl") or 0) for r in rows),
        "gross_pnl": sum(float(r.get("pnl_gross") or 0) for r in rows),
        "commission": sum(float(r.get("commission") or 0) for r in rows),
    }


def qualifies(row: dict) -> bool:
    """Gerçek para için asgari kenar şartı."""
    return (
        row.get("n", 0) >= MIN_TRADES
        and row.get("skill", 0) >= MIN_SKILL_PCT
        and abs(row.get("t", 0)) >= MIN_T_STAT
        and row.get("skill", 0) > 0
    )


# ── raporlar ──────────────────────────────────────────────────


def overall(trades: list[dict]) -> dict:
    vals = [v for v in (ret_pct(t) for t in trades) if v is not None]
    s = stats(vals) or {"n": 0, "mean": 0, "sd": 0, "t": 0, "wr": 0}
    net = sum(float(t.get("pnl") or 0) for t in trades)
    gross = sum(float(t.get("pnl_gross") or 0) for t in trades)
    comm = sum(float(t.get("commission") or 0) for t in trades)
    notional = sum(float(t.get("notional") or 0) for t in trades)
    times = sorted(t for t in (x.get("entry_time_tr") for x in trades) if t)
    days = 0.0
    if len(times) >= 2:
        try:
            days = (
                datetime.fromisoformat(times[-1]) - datetime.fromisoformat(times[0])
            ).total_seconds() / 86400
        except ValueError:
            days = 0.0
    return {
        "trades": len(trades),
        "days": days,
        "first_entry": times[0] if times else None,
        "last_entry": times[-1] if times else None,
        "wr": s["wr"],
        "mean_ret_pct": s["mean"],
        "t": s["t"],
        "net_pnl": net,
        "gross_pnl": gross,
        "commission": comm,
        "notional": notional,
        "fee_rate_pct": (100.0 * comm / notional) if notional else 0.0,
        "gross_edge_pct": (100.0 * gross / notional) if notional else 0.0,
        "maker_net_pnl": gross - notional * MAKER_ROUNDTRIP_PCT / 100.0,
    }


def by_book(trades: list[dict], *, min_n: int = 25) -> list[dict]:
    buckets = defaultdict(list)
    for t in trades:
        key = t.get("algo") or t["_bookfile"]
        buckets[f"{t['_group']}·{key}"].append(t)
    out = []
    for name, rows in buckets.items():
        sp = skill_split(rows)
        if sp and sp["n"] >= min_n:
            sp["name"] = name
            sp["qualifies"] = qualifies(sp)
            out.append(sp)
    out.sort(key=lambda r: r["skill"], reverse=True)
    return out


def by_coin(trades: list[dict], *, min_n: int = 40) -> list[dict]:
    buckets = defaultdict(list)
    for t in trades:
        buckets[t.get("symbol") or "?"].append(t)
    out = []
    for sym, rows in buckets.items():
        sp = skill_split(rows)
        if sp and sp["n"] >= min_n:
            sp["name"] = sym
            sp["qualifies"] = qualifies(sp)
            out.append(sp)
    out.sort(key=lambda r: r["skill"], reverse=True)
    return out


def coin_book_leaders(trades: list[dict], *, min_n: int = 20) -> list[dict]:
    """Coin başına en yüksek SKILL'li defter — dashboard lider tablosu için.

    WR bazlı sıralama 2-3 işlemli %100'leri lider gösteriyordu; burada
    asgari işlem sayısı ve t-istatistiği şartı var.
    """
    buckets = defaultdict(list)
    for t in trades:
        sym = t.get("symbol")
        book = t.get("algo") or t["_bookfile"]
        if sym and book:
            buckets[(sym, book)].append(t)
    per_coin = defaultdict(list)
    for (sym, book), rows in buckets.items():
        sp = skill_split(rows)
        if sp and sp["n"] >= min_n:
            sp["symbol"] = sym
            sp["book"] = book
            sp["qualifies"] = qualifies(sp)
            per_coin[sym].append(sp)
    out = []
    for sym, rows in per_coin.items():
        rows.sort(key=lambda r: r["skill"], reverse=True)
        best = dict(rows[0])
        best["runner_up"] = rows[1]["book"] if len(rows) > 1 else None
        best["candidates"] = len(rows)
        out.append(best)
    out.sort(key=lambda r: r["skill"], reverse=True)
    return out


def mfe_distribution(trades: list[dict]) -> list[dict]:
    """peak_upnl / atr_usd bandına göre dağılım — giriş ayrım gücü ölçüsü."""
    bands = [
        (0.0, 0.5), (0.5, 1.0), (1.0, 1.4), (1.4, 1.7),
        (1.7, 2.5), (2.5, 4.0), (4.0, float("inf")),
    ]
    rows_with = []
    for t in trades:
        au = float(t.get("atr_usd") or 0)
        if au > 0:
            rows_with.append((float(t.get("peak_upnl") or 0) / au, t))
    total = len(rows_with)
    out = []
    for lo, hi in bands:
        sel = [t for v, t in rows_with if lo <= v < hi]
        if not sel:
            continue
        vals = [v for v in (ret_pct(t) for t in sel) if v is not None]
        pnl = sum(float(t.get("pnl") or 0) for t in sel)
        wins = sum(1 for t in sel if t.get("win"))
        out.append({
            "band": f"{lo:g}-{hi:g}" if hi != float("inf") else f"{lo:g}+",
            "n": len(sel),
            "share_pct": 100.0 * len(sel) / total if total else 0.0,
            "avg_net": pnl / len(sel),
            "total_net": pnl,
            "wr": 100.0 * wins / len(sel),
            "mean_ret_pct": sum(vals) / len(vals) if vals else 0.0,
        })
    return out


def consensus(trades: list[dict], *, min_books: int = 5) -> list[dict]:
    """Uzlaşı seviyesine göre SKILL — çoğunluk oyu işe yarıyor mu?"""
    slots = defaultdict(list)
    for t in trades:
        slot = t.get("slot")
        if slot and t.get("side") in ("LONG", "SHORT"):
            slots[(slot, t.get("symbol"))].append(t)
    levels = defaultdict(list)
    for rows in slots.values():
        n_long = sum(1 for r in rows if r["side"] == "LONG")
        total = len(rows)
        if total < min_books:
            continue
        n_short = total - n_long
        ratio = max(n_long, n_short) / total
        side = "LONG" if n_long >= n_short else "SHORT"
        if ratio >= 0.95:
            key = "tam uzlaşı ≥95%"
        elif ratio >= 0.80:
            key = "güçlü 80-95%"
        elif ratio >= 0.65:
            key = "orta 65-80%"
        else:
            key = "bölünmüş <65%"
        levels[key].extend(r for r in rows if r["side"] == side)
    out = []
    for key, rows in levels.items():
        sp = skill_split(rows)
        if sp:
            sp["name"] = key
            out.append(sp)
    order = ["tam uzlaşı ≥95%", "güçlü 80-95%", "orta 65-80%", "bölünmüş <65%"]
    out.sort(key=lambda r: order.index(r["name"]) if r["name"] in order else 9)
    return out


def _score_percentiles(trades: list[dict]) -> None:
    """Skoru algo içinde yüzdeliğe çevir — `_score_pct` alanı ekler.

    Algolar farklı ölçekte skor üretiyor (biri 0-100, biri 0-5), bu yüzden
    ham skor kovalanamaz; her algo kendi dağılımında sıralanır.
    """
    by_algo = defaultdict(list)
    for t in trades:
        try:
            t["_score_abs"] = abs(float(t.get("score")))
        except (TypeError, ValueError):
            t["_score_abs"] = None
            continue
        by_algo[t.get("algo") or t.get("_bookfile")].append(t["_score_abs"])
    ranked = {a: sorted(v) for a, v in by_algo.items()}
    for t in trades:
        v = t.get("_score_abs")
        arr = ranked.get(t.get("algo") or t.get("_bookfile"))
        if v is None or not arr or len(arr) < 5:
            t["_score_pct"] = None
            continue
        t["_score_pct"] = 100.0 * bisect_left(arr, v) / len(arr)


CONVICTION_BANDS = [
    ("üst %20 (>80)", 80, 100.01),
    ("60-80", 60, 80),
    ("40-60", 40, 60),
    ("20-40", 20, 40),
    ("alt %20 (≤20)", -0.01, 20),
]


def conviction(trades: list[dict], *, folds: int = 5) -> dict:
    """Güven arttıkça kenar ne oluyor? + zaman dilimi tutarlılığı.

    Ölçülen: üst %20 kovası SKILL negatif ve bu drift değil (DRIFT ayrı
    raporlanıyor). `folds` zaman dilimine bölünüp her dilimde işaret
    kontrol edilir — tek dilime yığılmış bulgular böyle ayıklanır.
    """
    _score_percentiles(trades)
    rows = [t for t in trades if t.get("_score_pct") is not None]
    rows.sort(key=lambda t: t.get("entry_time_tr") or "")

    bands = []
    for name, lo, hi in CONVICTION_BANDS:
        sel = [t for t in rows if lo < t["_score_pct"] <= hi]
        sp = skill_split(sel)
        if sp:
            sp["name"] = name
            bands.append(sp)

    top = [t for t in rows if t["_score_pct"] > 80]
    size = max(1, len(rows) // folds)
    fold_rows = []
    for i in range(folds):
        part = rows[i * size:(i + 1) * size] if i < folds - 1 else rows[i * size:]
        sel = [t for t in part if t["_score_pct"] > 80]
        sp = skill_split(sel)
        if not sp:
            continue
        sp["name"] = f"dilim {i + 1}"
        sp["span"] = (
            f"{(part[0].get('entry_time_tr') or '')[5:16]}"
            f"→{(part[-1].get('entry_time_tr') or '')[5:16]}"
        )
        fold_rows.append(sp)

    top_sp = skill_split(top)
    kept_sp = skill_split([t for t in rows if t["_score_pct"] <= 80])
    inv_edge = None
    if top_sp:
        inv_edge = -top_sp["skill"] - MAKER_ROUNDTRIP_PCT
    return {
        "bands": bands,
        "folds": fold_rows,
        "negative_folds": sum(1 for f in fold_rows if f["skill"] < 0),
        "fold_count": len(fold_rows),
        "top": top_sp,
        "kept": kept_sp,
        "invert_net_edge_pct": inv_edge,
        "maker_cost_pct": MAKER_ROUNDTRIP_PCT,
    }


def audit(groups: dict | None = None) -> dict:
    trades = load_trades(groups)
    return {
        "generated_at": datetime.now().isoformat(),
        "thresholds": {
            "min_trades": MIN_TRADES,
            "min_t_stat": MIN_T_STAT,
            "min_skill_pct": MIN_SKILL_PCT,
            "taker_roundtrip_pct": TAKER_ROUNDTRIP_PCT,
            "maker_roundtrip_pct": MAKER_ROUNDTRIP_PCT,
        },
        "overall": overall(trades),
        "books": by_book(trades),
        "coins": by_coin(trades),
        "coin_leaders": coin_book_leaders(trades),
        "mfe": mfe_distribution(trades),
        "consensus": consensus(trades),
        "conviction": conviction(trades),
    }


# ── yazdırma ──────────────────────────────────────────────────


def _skill_table(title: str, rows: list[dict], limit: int | None = None) -> None:
    print()
    print("=" * 104)
    print(title)
    print("=" * 104)
    print(
        f"{'ad':<30} {'n':>6} {'nL':>5} {'nS':>5} {'ortL%':>9} {'ortS%':>9} "
        f"{'SKILL%':>9} {'DRIFT%':>9} {'t':>7} {'ok':>3}"
    )
    print("-" * 104)
    for r in (rows[:limit] if limit else rows):
        print(
            f"{r['name'][:30]:<30} {r['n']:>6} {r['n_long']:>5} {r['n_short']:>5} "
            f"{r['mean_long']:>9.4f} {r['mean_short']:>9.4f} "
            f"{r['skill']:>9.4f} {r['drift']:>9.4f} {r['t']:>7.2f} "
            f"{'✓' if r.get('qualifies') else '':>3}"
        )


def print_report(res: dict, *, books=False, coins=False, mfe=False,
                 cons=False, leaders=False, conv=False) -> None:
    o = res["overall"]
    th = res["thresholds"]
    print("=" * 104)
    print("KRIPTO BECERİ DENETİMİ (drift-nötr)")
    print("=" * 104)
    print(f"İşlem      : {o['trades']:,}")
    print(f"Dönem      : {o['days']:.2f} gün  ({str(o['first_entry'])[:16]} → {str(o['last_entry'])[:16]})")
    print(f"Kazanma    : {o['wr']:.2f}%")
    print(f"Brüt PnL   : ${o['gross_pnl']:,.2f}")
    print(f"Komisyon   : ${o['commission']:,.2f}")
    print(f"Net PnL    : ${o['net_pnl']:,.2f}")
    print(f"Hacim      : ${o['notional']:,.0f}")
    print(f"Komisyon oranı : {o['fee_rate_pct']:.4f}% (gidiş-dönüş)")
    print(f"Brüt kenar     : {o['gross_edge_pct']:+.4f}% (hacme oranla)")
    print(f"Ort. getiri    : {o['mean_ret_pct']:+.4f}%  t={o['t']:+.2f}")
    print()
    print(f"Maker'a geçilse net PnL: ${o['maker_net_pnl']:,.2f} "
          f"(fark {o['maker_net_pnl'] - o['net_pnl']:+,.2f})")
    if o["days"] < 60:
        print()
        print(f"!! Dönem {o['days']:.1f} gün — istatistiksel doğrulama için 60 gün gerekir.")
        print("   Aşağıdaki sıralamalar bu yüzden bağlayıcı değil.")

    qual = [b for b in res["books"] if b.get("qualifies")]
    both = [b for b in res["books"] if b.get("both_positive")]
    print()
    print(f"Eşiği geçen defter (n≥{th['min_trades']}, SKILL≥{th['min_skill_pct']}%, "
          f"|t|≥{th['min_t_stat']}): {len(qual)}/{len(res['books'])}")
    print(f"Her iki yönde pozitif: {len(both)}/{len(res['books'])} "
          f"(şans eseri beklenen ~{len(res['books']) * 0.25:.0f})")
    if qual:
        for b in qual:
            print(f"   ✓ {b['name']}  SKILL {b['skill']:+.4f}%  t={b['t']:.2f}  n={b['n']}")
    else:
        print("   Gerçek para yön işlemi için uygun defter yok.")

    if books:
        _skill_table("DEFTER BAZINDA SKILL (azalan)", res["books"], limit=40)
    if coins:
        _skill_table("COİN BAZINDA SKILL (azalan)", res["coins"])
    if leaders:
        print()
        print("=" * 104)
        print("COİN LİDERLERİ — en yüksek SKILL'li defter")
        print("=" * 104)
        print(f"{'coin':<12} {'defter':<22} {'n':>5} {'SKILL%':>9} {'t':>7} "
              f"{'net$':>10} {'aday':>5} {'ok':>3}")
        print("-" * 104)
        for r in res["coin_leaders"]:
            print(
                f"{r['symbol']:<12} {str(r['book'])[:22]:<22} {r['n']:>5} "
                f"{r['skill']:>9.4f} {r['t']:>7.2f} {r['net_pnl']:>10.2f} "
                f"{r['candidates']:>5} {'✓' if r.get('qualifies') else '':>3}"
            )
    if mfe:
        print()
        print("=" * 104)
        print("MFE DAĞILIMI — peak_upnl / atr_usd")
        print("=" * 104)
        print(f"{'band (ATR)':<14} {'n':>7} {'pay%':>7} {'ort.net$':>10} "
              f"{'WR%':>7} {'ort.ret%':>10} {'toplam$':>12}")
        print("-" * 104)
        for r in res["mfe"]:
            print(
                f"{r['band']:<14} {r['n']:>7} {r['share_pct']:>7.1f} "
                f"{r['avg_net']:>10.3f} {r['wr']:>7.1f} "
                f"{r['mean_ret_pct']:>10.4f} {r['total_net']:>12.2f}"
            )
    if cons:
        _skill_table("KONSENSÜS SEVİYESİ — çoğunluk oyu işe yarıyor mu?",
                     res["consensus"])
    if conv:
        c = res["conviction"]
        _skill_table("GÜVEN KOVASI — skor yüzdeliğine göre SKILL", c["bands"])
        print()
        print("=" * 104)
        print("ÜST %20 KOVASI — zaman dilimi tutarlılığı")
        print("=" * 104)
        print(f"{'dilim':<10} {'aralık':<26} {'n':>6} {'SKILL%':>10} "
              f"{'DRIFT%':>10} {'t':>7}")
        print("-" * 104)
        for f in c["folds"]:
            print(f"{f['name']:<10} {f.get('span', ''):<26} {f['n']:>6} "
                  f"{f['skill']:>10.4f} {f['drift']:>10.4f} {f['t']:>7.2f}")
        print(f"\n  SKILL negatif: {c['negative_folds']}/{c['fold_count']} dilim")
        top, kept = c["top"], c["kept"]
        if top and kept:
            print()
            print(f"  üst %20 : n={top['n']:6}  SKILL={top['skill']:+.4f}%  "
                  f"DRIFT={top['drift']:+.4f}%  t={top['t']:+.2f}")
            print(f"  kalan   : n={kept['n']:6}  SKILL={kept['skill']:+.4f}%  "
                  f"t={kept['t']:+.2f}")
            print()
            print("  Üst kova atılırsa kalanın kenarı sıfıra yaklaşır — zarar durur,")
            print("  kâr başlamaz. Tersini açmanın maker sonrası beklentisi:")
            print(f"    {c['invert_net_edge_pct']:+.4f}%/işlem "
                  f"(= {-top['skill']:+.4f}% − {c['maker_cost_pct']:.2f}% maker)")
            se = top["sd"] / top["n"] ** 0.5 if top.get("sd") else None
            if se:
                lo = -top["skill"] - 1.96 * se - c["maker_cost_pct"]
                hi = -top["skill"] + 1.96 * se - c["maker_cost_pct"]
                verdict = ("KANIT YETERSİZ — aralık sıfırı kesiyor"
                           if lo <= 0 <= hi else "aralık sıfırın üstünde")
                print(f"    %95 aralık [{lo:+.4f}%, {hi:+.4f}%] → {verdict}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Drift-nötr kripto beceri denetimi")
    ap.add_argument("--books", action="store_true", help="defter sıralaması")
    ap.add_argument("--coins", action="store_true", help="coin sıralaması")
    ap.add_argument("--leaders", action="store_true", help="coin liderleri")
    ap.add_argument("--mfe", action="store_true", help="MFE dağılımı")
    ap.add_argument("--consensus", action="store_true", help="uzlaşı analizi")
    ap.add_argument("--conviction", action="store_true",
                    help="güven kovası + zaman dilimi tutarlılığı")
    ap.add_argument("--all", action="store_true", help="tüm bölümler")
    ap.add_argument("--json", action="store_true", help="JSON çıktı")
    ap.add_argument("--out", help="JSON'u dosyaya yaz")
    args = ap.parse_args()

    res = audit()
    if args.out:
        with open(args.out, "w") as f:
            json.dump(res, f, indent=2, ensure_ascii=False)
        print(f"yazıldı: {args.out}")
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return
    print_report(
        res,
        books=args.books or args.all,
        coins=args.coins or args.all,
        leaders=args.leaders or args.all,
        mfe=args.mfe or args.all,
        cons=args.consensus or args.all,
        conv=args.conviction or args.all,
    )


if __name__ == "__main__":
    main()
