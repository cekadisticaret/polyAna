"""REF04 — saatlik yol UÇ NOKTA DÖNÜŞÜ.

Mantık:
  O saat içinde oluşan en büyük bps sapması (ekstrem) tespit edilir.
  Fiyat ekstremden PULLBACK_BPS kadar geri çekilirse ters yöne girilir.
  Örnek: BTC −35 bps'e düşüp +8 bps geri çekildiyse → UP sinyali.

F16 filtresi trader'da uygulanır (bu modül sadece yol verisine bakar).

Kaynak: ref01_signal.path_series (hourly_path). Emir yok.
"""
from __future__ import annotations

import ref01_signal as _r1

SYMBOLS = _r1.SYMBOLS

# ── Parametreler ───────────────────────────────────────────────
EXTREME_BPS   = 33.0   # Saatte oluşan sapma en az bu kadar büyük olmalı (bps)  [25→33, 2026-09-12]
PULLBACK_BPS  = 10.0   # Ekstremden bu kadar geri çekilmiş olmalı (bps)
ENTRY_AFTER   = 10     # Bu dakikadan önce sinyal yok (ekstrem oluşmaya vakit)
ENTRY_BEFORE  = 50     # Bu dakikadan sonra sinyal yok
ASK_MIN       = 0.25   # Alt sınır — 0.20-0.24 bandı %0 WR gösterdi  [0.20→0.25, 2026-09-12]
ASK_MAX       = 0.30   # Üst sınır — altın dilim 0.25-0.29 → %62 WR  [0.35→0.30, 2026-09-12]
# Hedef bant 0.25-0.30: 0.30-0.35 bandı %17 WR gösterdi (6 işlem, teyit için bekleniyor)
EXCLUDED_SYMBOLS = frozenset({"ETHUSDT"})  # ETH: 0/5 kayıp (-$42), geçici dışlama [2026-09-12]


def _deny(sym: str, reason: str, detail: str, **extra) -> dict:
    return {
        "allow": False,
        "symbol": sym,
        "direction": None,
        "mode": None,
        "reason": reason,
        "detail": detail,
        "ask_min": ASK_MIN,
        "ask_max": ASK_MAX,
        "extreme_bps": extra.get("extreme_bps"),
        "pullback_bps": extra.get("pullback_bps"),
        "path_bps": extra.get("path_bps"),
    }


def decide(symbol: str, minute: int | None = None, hour_key: str | None = None) -> dict:
    """Uç nokta dönüş sinyali döndürür.

    Returns dict with keys:
        allow (bool), direction ("UP"|"DOWN"|None), mode, detail,
        extreme_bps, pullback_bps, path_bps, extreme_mn, ask_max
    """
    sym = _r1.norm_symbol(symbol)

    # Hariç tutulan semboller
    if sym in EXCLUDED_SYMBOLS:
        return _deny(sym, "hariç", f"{sym} geçici olarak devre dışı (WR %0)")

    # Dakika penceresi
    if minute is not None:
        if minute < ENTRY_AFTER or minute > ENTRY_BEFORE:
            return _deny(sym, "dakika", f"dk {minute} pencere dışı [{ENTRY_AFTER}-{ENTRY_BEFORE}]")

    path = _r1.path_series(sym, hour_key)
    pts: list[tuple[int, float]] = path.get("pts") or []
    now_bps = path.get("bps")

    if len(pts) < ENTRY_AFTER:
        return _deny(sym, "yetersiz veri", f"yalnız {len(pts)} dakika kaydı var")

    # Ekstrem: mutlak değer en büyük nokta
    if not pts:
        return _deny(sym, "veri yok", "dakika noktası yok")

    extreme_mn, extreme_bps = max(pts, key=lambda p: abs(p[1]))

    if abs(extreme_bps) < EXTREME_BPS:
        return _deny(
            sym, "ekstrem yok",
            f"|ekstrem| {abs(extreme_bps):.1f} < {EXTREME_BPS:.0f} bps",
            extreme_bps=extreme_bps, path_bps=now_bps,
        )

    if now_bps is None:
        return _deny(sym, "bps yok", "güncel bps alınamadı", extreme_bps=extreme_bps)

    # Geri çekilme miktarı
    pullback = abs(extreme_bps - now_bps)

    if pullback < PULLBACK_BPS:
        return _deny(
            sym, "geri çekilme yok",
            f"pullback {pullback:.1f} < {PULLBACK_BPS:.0f} bps · ekstrem {extreme_bps:+.1f}",
            extreme_bps=extreme_bps, pullback_bps=pullback, path_bps=now_bps,
        )

    # Hâlâ aynı tarafta olmalı — tam dönüş yaşanmamış, henüz ucuz taraf
    same_sign = (extreme_bps > 0 and now_bps > 0) or (extreme_bps < 0 and now_bps < 0)
    if not same_sign:
        return _deny(
            sym, "tam döndü",
            f"ekstrem {extreme_bps:+.1f} iken şimdi {now_bps:+.1f} — token artık pahalı",
            extreme_bps=extreme_bps, pullback_bps=pullback, path_bps=now_bps,
        )

    # Sinyal: ekstremin tersine git
    extreme_side = "UP" if extreme_bps > 0 else "DOWN"
    signal_dir   = "DOWN" if extreme_side == "UP" else "UP"

    return {
        "allow":       True,
        "symbol":      sym,
        "direction":   signal_dir,
        "mode":        "extreme_reversal",
        "ask_min":     ASK_MIN,
        "ask_max":     ASK_MAX,
        "path_bps":    now_bps,
        "extreme_bps": round(extreme_bps, 2),
        "extreme_mn":  extreme_mn,
        "pullback_bps": round(pullback, 2),
        "reason":      "extreme_reversal",
        "detail": (
            f"uç {extreme_side} @:{extreme_mn:02d} {extreme_bps:+.1f}bps"
            f" → {signal_dir} · geri {pullback:.1f}bps · şimdi {now_bps:+.1f}bps"
        ),
    }
