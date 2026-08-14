#!/usr/bin/env python3
"""Ölçülen kenar kapısı — kripto tarafında hangi (defter, coin) işlem açabilir.

## Neden bu kapı var

Poly'de kâr eden defterler Binance Futures'ta kaybediyordu. Sebep ölçüldü ve
komisyon oranı **değil**, iki farklı eşik:

  Poly başabaş WR   = piyasa fiyatı           ≈ %49,8   (binary, 1:1 ödeme)
  Kripto başabaş WR = komisyon + ödeme şekli  ≈ %61,7   (A2#05 · taker)
                                              ≈ %70,4   (A6V3)
                                              ≈ %44,6   (B1#03 — tek sağlıklı)

Yani aynı sinyalin kriptoda kâr etmesi için Poly'dekinden ~12 puan daha isabetli
olması gerekiyor. 1 yıllık ölçüm (181 bin sinyal, 7 ufuk, drift-nötr SKILL) bu
4 defterin hiçbirinde komisyonu aşan yön kenarı bulamadı:

  A2#05  1–48h SKILL −%0,024 … +%0,027   |t| ≤ 0,58
  A6V3   1–24h negatif (8h'te t=−2,84) · 48h +%0,109 t=+2,65
  B1#03  1h +%0,016 t=+2,08 (anlamlı ama komisyonun altında)
  MELEZ  1–48h SKILL −%0,031 … +%0,020   |t| ≤ 1,63

Sonuç: kenar yokken çıkış kuralını iyileştirmek kaybı küçültür ama kâra
çeviremez. Bu yüzden çözüm "daha iyi ayar" değil, **kanıt şartı**: bir defter
bir coin'de yalnızca ölçülmüş SKILL komisyonu aşıyorsa ve t eşiği geçiyorsa
pozisyon açar. Geçmiyorsa hiç açmaz — kasa erimez.

## Kademeler

  KANITLI (proven)   SKILL ≥ komisyon · t ≥ 3,0  → tam kademe
  ADAY    (candidate) SKILL ≥ komisyon · t ≥ 2,0  → çeyrek kademe (ileri doğrulama)
  KAPALI  (blocked)   diğer                        → işlem yok

t eşiği çoklu-test yüzünden yüksek: 4 defter × 30 coin × 7 ufuk = 840 test,
α=%5'te ~42 tanesi şansa |t|≥2 verir. t≥3,0 bu gürültünün büyük kısmını atar
(tam Bonferroni t≈4,0 olurdu; ADAY kademesi çeyrek kademeyle risk alarak
ileriye dönük doğrulamaya izin verir).

## Kullanım

  python3 AgustosKripto/Test/edge_gate.py --build     # tabloyu üret (uzun)
  python3 AgustosKripto/Test/edge_gate.py --show      # tabloyu özetle
"""
from __future__ import annotations

import argparse
import json
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_DIR, "data")
TABLE_PATH = os.path.join(DATA, "edge_table.json")
CONFIG_PATH = os.path.join(DATA, "edge_gate_config.json")

# Kapı açıkken PRO defterleri kenar filtresi olmadan tüm sinyalleri alır.
# Varsayılan kapalı (ölçüm yoksa işlem açmaz). edge_gate_config.json → {"open": true}

# Gerçekleşen komisyon: $600 notional, Binance USDⓈ-M
TAKER_ROUND_TRIP = 0.10   # % — taker %0,05 × 2 yön (sistemin varsayımı)
MAKER_ROUND_TRIP = 0.04   # % — limit emir %0,02 × 2 yön

# t eşikleri seçim yanlılığını karşılıyor: her (defter, coin) için 7 ufuğun en
# iyisi seçiliyor (Bonferroni 7 → t≈2,45) ve 30 coin × 7 ufuk taranıyor
# (Bonferroni 210 → t≈3,5). Ölçüm ayrıca ufuk boyunda bloklara kümeleniyor,
# yani t örtüşen pencerelerden şişmiş değil.
T_PROVEN = 3.5
T_CANDIDATE = 2.5
MIN_SIGNALS = 200         # coin başına asgari sinyal — ince dilimde t güvenilmez

# Kademe başına marj çarpanı
TIER_SIZE = {"proven": 1.0, "candidate": 0.25, "blocked": 0.0}

# Eşik **taker**: `maker_sim.py` 88 günlük ölçümde limit emirlerde ters seçilim
# buldu (dolan emirler kötü, kaçanlar brüt +%0,13…+%0,76) — yani maker
# komisyonunu garanti saymak kendini kandırmak olur. Maker eşiğine geçmek için
# bu satır MAKER_ROUND_TRIP yapılır, ama önce fill oranı doğrulanmalı.
FEE_THRESHOLD_PCT = TAKER_ROUND_TRIP

_CACHE: dict | None = None


def gate_open() -> bool:
    """True = kenar filtresi kapalı, PRO defterleri normal sinyalleri alır."""
    env = os.environ.get("TEST_EDGE_GATE", "").strip().lower()
    if env in ("open", "1", "true", "on", "yes"):
        return True
    if env in ("closed", "0", "false", "off", "no"):
        return False
    try:
        with open(CONFIG_PATH) as f:
            return bool(json.load(f).get("open", False))
    except Exception:
        return False


# ── Tablo üretimi ─────────────────────────────────────────────
def build_table(sweep_files: list[str], *, out: str = TABLE_PATH) -> dict:
    """horizon_sweep --per-symbol çıktılarından (defter, coin) kenar tablosu.

    Her (defter, coin) için tüm ufuklar arasından en yüksek t'li ve komisyonu
    aşan ufuk seçilir; hiçbiri aşmıyorsa en iyisi 'blocked' olarak kaydedilir
    (şeffaflık — neden kapalı olduğu görünsün).
    """
    pairs: dict[str, dict] = {}
    sources: list[str] = []
    for path in sweep_files:
        if not os.path.exists(path):
            print(f"  atlandı (yok): {path}")
            continue
        with open(path) as f:
            payload = json.load(f)
        sources.append(os.path.basename(path))
        for res in payload.get("results") or []:
            uid = res.get("uid")
            by_sym = res.get("by_symbol") or {}
            if not uid or not by_sym:
                continue
            for sym, rows in by_sym.items():
                usable = [r for r in rows
                          if (r.get("n_long", 0) + r.get("n_short", 0)) >= MIN_SIGNALS]
                if not usable:
                    continue
                qualified = [r for r in usable if r["skill_pct"] >= FEE_THRESHOLD_PCT]
                pick = (max(qualified, key=lambda r: r["skill_t"]) if qualified
                        else max(usable, key=lambda r: r["skill_t"]))
                tier = _tier(pick["skill_pct"], pick["skill_t"])
                key = f"{uid}|{sym}"
                prev = pairs.get(key)
                # aynı çift iki dosyada varsa (30 coin + majör) daha çok
                # sinyalli ölçümü tut
                n_now = pick.get("n_long", 0) + pick.get("n_short", 0)
                if prev and prev["n"] >= n_now:
                    continue
                pairs[key] = {
                    "uid": uid, "symbol": sym, "book": res.get("book"),
                    "hours": pick["hours"], "skill_pct": pick["skill_pct"],
                    "skill_se_pct": pick["skill_se_pct"], "skill_t": pick["skill_t"],
                    "drift_pct": pick["drift_pct"], "n": n_now,
                    "tier": tier, "size_mult": TIER_SIZE[tier],
                }
    table = {
        "ok": True,
        "fee_threshold_pct": FEE_THRESHOLD_PCT,
        "t_proven": T_PROVEN, "t_candidate": T_CANDIDATE,
        "min_signals": MIN_SIGNALS,
        "sources": sources,
        "pairs": pairs,
        "counts": {
            t: sum(1 for v in pairs.values() if v["tier"] == t)
            for t in ("proven", "candidate", "blocked")
        },
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(table, f, indent=2, ensure_ascii=False)
    return table


def _tier(skill_pct: float, t: float) -> str:
    if skill_pct < FEE_THRESHOLD_PCT:
        return "blocked"
    if t >= T_PROVEN:
        return "proven"
    if t >= T_CANDIDATE:
        return "candidate"
    return "blocked"


# ── Karar ─────────────────────────────────────────────────────
def load_table(*, force: bool = False) -> dict:
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    if os.path.exists(TABLE_PATH):
        try:
            with open(TABLE_PATH) as f:
                _CACHE = json.load(f)
        except Exception as e:
            print(f"[edge_gate] tablo okunamadı: {e}")
            _CACHE = {"pairs": {}}
    else:
        _CACHE = {"pairs": {}}
    return _CACHE


def decision(book_uid: str, symbol: str) -> dict:
    """(defter, coin) için kapı kararı.

    Tablo yoksa **kapalı** döner: ölçüm olmadan gerçek/sanal kasa riske girmez.
    """
    uid = str(book_uid or "").replace("pro_", "", 1)
    row = load_table().get("pairs", {}).get(f"{uid}|{str(symbol).upper()}")
    if not row:
        return {"allowed": False, "tier": "blocked", "size_mult": 0.0,
                "hours": None, "reason": "ölçüm yok"}
    return {
        "allowed": row["tier"] in ("proven", "candidate"),
        "tier": row["tier"],
        "size_mult": row["size_mult"],
        "hours": row["hours"],
        "skill_pct": row["skill_pct"],
        "skill_t": row["skill_t"],
        "n": row["n"],
        "reason": (f"SKILL %{row['skill_pct']:+.4f} · t={row['skill_t']:+.2f} · "
                   f"{row['hours']}h · n={row['n']}"),
    }


def allowed_pairs(*, tiers: tuple[str, ...] = ("proven", "candidate")) -> list[dict]:
    return sorted(
        (v for v in load_table().get("pairs", {}).values() if v["tier"] in tiers),
        key=lambda r: -r["skill_t"],
    )


def summary() -> dict:
    t = load_table()
    return {
        "open": gate_open(),
        "fee_threshold_pct": t.get("fee_threshold_pct", FEE_THRESHOLD_PCT),
        "counts": t.get("counts") or {},
        "pairs_total": len(t.get("pairs") or {}),
        "allowed": allowed_pairs(),
        "sources": t.get("sources") or [],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--build", action="store_true")
    p.add_argument("--show", action="store_true")
    p.add_argument("--sweeps", default=",".join([
        os.path.join(DATA, "horizon_sweep_poly4_persym.json"),
        os.path.join(DATA, "horizon_sweep_poly4_majors_persym.json"),
    ]))
    args = p.parse_args()

    if args.build:
        files = [x.strip() for x in args.sweeps.split(",") if x.strip()]
        t = build_table(files)
        print(f"Kenar tablosu → {TABLE_PATH}")
        print(f"  eşik: SKILL ≥ %{t['fee_threshold_pct']:.2f} · "
              f"t ≥ {T_CANDIDATE} (aday) / {T_PROVEN} (kanıtlı)")
        print(f"  çift: {len(t['pairs'])} · {t['counts']}")

    if args.build or args.show:
        s = summary()
        rows = s["allowed"]
        print(f"\nİŞLEME İZİNLİ ÇİFTLER — {len(rows)}")
        if not rows:
            print("  yok — hiçbir (defter, coin) ölçülen kenarla komisyonu aşmıyor.")
            print("  PRO defterleri işlem açmaz; kasa erimez.")
        for r in rows:
            print(f"  {r['book']:<8} {r['symbol']:<10} {r['hours']:>3}h  "
                  f"SKILL %{r['skill_pct']:+.4f}  t={r['skill_t']:+.2f}  "
                  f"n={r['n']:>6}  {r['tier']} ×{r['size_mult']}")


if __name__ == "__main__":
    main()
