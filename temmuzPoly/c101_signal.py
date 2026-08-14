"""
C101 — PTB + volatilite olasılık modeli

Diğer 53 defter "fiyat hangi yöne gider" diye soruyor. Bu defter farklı bir soru
soruyor: **"Polymarket'in istediği 0.70 adil mi?"**

Polymarket saatlik piyasası yön bahsi değil, bariyer bahsi: saat kapanışı saat
açılışının (price-to-beat) üstünde mi? Bu, kapalı formda fiyatlanabilir:

    z      = ln(S / PTB) / (σ · √T_kalan)
    P(UP)  = Φ(z)

S anlık fiyat, PTB saatin açılışı, T_kalan saatin kalan kesri. Sürüklenme
(drift) bilerek sıfır alınır — 1 saatlik ufukta yön öngörülemez, ölçülen tek
şey volatilitedir.

σ nereden geliyor (OHLCV + OHLCV dışı harman):
  • Parkinson tahmincisi (H/L) — kapanış-kapanış'tan ~5× verimli  [OHLCV]
  • Emir defteri derinliği — ince defter aynı akışta daha çok oynar  [OHLCV dışı]
  • Saat içi gerçekleşen aralık — ilk dakikalar sakin mi hareketli mi  [OHLCV]

Yöne küçük bir eğim (tilt) eklenir, toplamı ±0.05 ile sınırlı:
  • Taker alış oranı (CVD vekili) · emir defteri dengesizliği · funding z · OI

Karar: |P_model − P_piyasa| ≥ EDGE_MIN ise ucuz tarafı al, değilse işlem yok.
Kademe çeyrek Kelly. Yön tahmini değil, yanlış fiyatlama avı.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone

import c101_data as cd

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

_DIR = os.path.dirname(os.path.abspath(__file__))
_BASELINE_FILE = os.path.join(_DIR, "c101_depth_baseline.json")

# ── Model parametreleri ───────────────────────────────────────
EDGE_MIN = 0.05          # model ile piyasa arasında en az 5 puan fark (C1#01 varsayılanı)
PRICE_FLOOR = 0.10       # bu bandın dışında normal dağılım varsayımı kırılır
PRICE_CEIL = 0.90
TILT_CAP = 0.05          # yön eğiminin toplam üst sınırı
VOL_SHORT_H = 12         # kısa vade Parkinson penceresi (saat)
VOL_LONG_H = 72          # uzun vade Parkinson penceresi (saat)
VOL_SHORT_W = 0.6        # kısa vadenin harmandaki ağırlığı
KELLY_FRACTION = 0.25    # çeyrek Kelly
MIN_STAKE = 3.0
MAX_STAKE = 25.0
_MIN_T_REMAIN = 1.0 / 60  # son dakikada σ·√T sıfıra gitmesin


def _phi(x: float) -> float:
    """Standart normal kümülatif dağılım."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ── Volatilite ────────────────────────────────────────────────
def parkinson_sigma(kl: list[dict], window: int) -> float | None:
    """Parkinson H/L volatilite tahmincisi — bar başına (saatlik) σ.

    Kapanış-kapanış'ın aksine saat içi salınımı görür; aynı örneklem
    büyüklüğünde ~5 kat daha verimli.
    """
    bars = [k for k in kl[-(window + 1):-1] if k["h"] > 0 and k["l"] > 0]
    if len(bars) < max(5, window // 3):
        return None
    acc = 0.0
    for k in bars:
        acc += math.log(k["h"] / k["l"]) ** 2
    return math.sqrt(acc / len(bars) / (4.0 * math.log(2.0)))


def _load_baseline() -> dict:
    if os.path.exists(_BASELINE_FILE):
        try:
            with open(_BASELINE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_baseline(data: dict) -> None:
    try:
        with open(_BASELINE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[C101] derinlik referansı yazılamadı: {e}")


def depth_vol_multiplier(symbol: str, bundle: dict, *, update: bool = True) -> tuple[float, dict]:
    """Emir defteri derinliği → volatilite çarpanı.

    Likidite oranı = defter derinliği / saatlik işlem hacmi. Bu oran kendi
    geçmiş ortalamasının (EWMA) altındaysa defter normalden ince demektir;
    aynı akış daha çok fiyat oynatır → σ yukarı.

    Geçmiş derinlik verisi satın alınamadığı için referans çalıştıkça kendi
    kendine kurulur; ilk turlarda çarpan 1.0 (etkisiz) döner.
    """
    depth = bundle.get("depth")
    kl = bundle.get("klines") or []
    info = {"depth_mult": 1.0, "liq_ratio": None, "liq_baseline": None}
    if not depth or len(kl) < 13:
        return 1.0, info
    recent = kl[-13:-1]
    notional = [k["v"] * k["c"] for k in recent if k["v"] > 0 and k["c"] > 0]
    if not notional:
        return 1.0, info
    avg_hourly = sum(notional) / len(notional)
    if avg_hourly <= 0:
        return 1.0, info
    liq_ratio = depth["depth_notional"] / avg_hourly
    info["liq_ratio"] = round(liq_ratio, 4)

    base = _load_baseline()
    rec = base.get(symbol) or {}
    prev = rec.get("ewma")
    n = int(rec.get("n") or 0)
    if update:
        alpha = 0.15
        new_ewma = liq_ratio if prev is None else (alpha * liq_ratio + (1 - alpha) * prev)
        base[symbol] = {
            "ewma": round(new_ewma, 6),
            "n": n + 1,
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _save_baseline(base)
    if prev is None or n < 20:
        # Referans henüz oturmadı — çarpan uygulanmaz
        info["liq_baseline"] = round(prev, 4) if prev else None
        return 1.0, info
    info["liq_baseline"] = round(prev, 4)
    mult = (prev / liq_ratio) ** 0.25 if liq_ratio > 0 else 1.0
    mult = max(0.85, min(1.20, mult))
    info["depth_mult"] = round(mult, 4)
    return mult, info


def intrahour_multiplier(kl: list[dict], elapsed_frac: float, sigma: float) -> float:
    """Saat içi gerçekleşen aralık beklenenin üstündeyse σ'yı yukarı çeker."""
    if not kl or sigma <= 0 or elapsed_frac <= 0.02:
        return 1.0
    cur = kl[-1]
    if cur["h"] <= 0 or cur["l"] <= 0:
        return 1.0
    realized = math.log(cur["h"] / cur["l"]) / (2.0 * math.sqrt(math.log(2.0)))
    expected = sigma * math.sqrt(elapsed_frac)
    if expected <= 0:
        return 1.0
    return max(0.80, min(1.35, (realized / expected) ** 0.35))


# ── Yön eğimi ─────────────────────────────────────────────────
def direction_tilt(bundle: dict, hour_return: float) -> tuple[float, dict]:
    """OHLCV dışı kaynaklardan küçük, sınırlı yön eğimi.

    Araştırma bu sinyallerin tek başına yön vermediğini gösteriyor; bu yüzden
    toplam katkı TILT_CAP ile kırpılıyor. Ana karar volatilite modelinde.
    """
    parts = {}
    tilt = 0.0

    flow = bundle.get("flow_tilt") or 0.0
    parts["flow"] = round(flow * 0.020, 5)
    tilt += parts["flow"]

    depth = bundle.get("depth")
    if depth:
        imb = max(-1.0, min(1.0, depth["imbalance"]))
        parts["book"] = round(imb * 0.015, 5)
        tilt += parts["book"]

    fn = bundle.get("funding")
    if fn:
        # Aşırı funding = kalabalık tek tarafta; kontra yönde küçük eğim
        z = max(-3.0, min(3.0, fn.get("z") or 0.0))
        parts["funding"] = round(-z / 3.0 * 0.010, 5)
        tilt += parts["funding"]

    oi = bundle.get("oi")
    if oi:
        # Artan OI mevcut hareketi teyit eder, azalan OI kapanış (geri dönüş) sinyali
        chg = max(-0.05, min(0.05, oi.get("change_1h") or 0.0)) / 0.05
        confirm = chg * (1.0 if hour_return >= 0 else -1.0)
        parts["oi"] = round(confirm * 0.010, 5)
        tilt += parts["oi"]

    tilt = max(-TILT_CAP, min(TILT_CAP, tilt))
    parts["total"] = round(tilt, 5)
    return tilt, parts


# ── Ana model ─────────────────────────────────────────────────
def fair_probability(symbol: str, now_tr: datetime, *, update_baseline: bool = True) -> dict | None:
    """Sembol için P(UP) ve tüm ara değerler. Karar defterde verilir."""
    bundle = cd.collect(symbol)
    kl = bundle.get("klines") or []
    if len(kl) < VOL_SHORT_H + 2:
        print(f"[C101] {symbol} — yetersiz mum ({len(kl)})")
        return None

    cur = kl[-1]
    ptb = cur["o"]           # saatin açılışı = price to beat
    spot = cur["c"]
    if ptb <= 0 or spot <= 0:
        return None

    elapsed_frac = max(0.0, min(0.99, (now_tr.minute * 60 + now_tr.second) / 3600.0))
    t_remain = max(_MIN_T_REMAIN, 1.0 - elapsed_frac)

    sig_s = parkinson_sigma(kl, VOL_SHORT_H)
    sig_l = parkinson_sigma(kl, VOL_LONG_H)
    if sig_s is None and sig_l is None:
        print(f"[C101] {symbol} — volatilite hesaplanamadı")
        return None
    if sig_s is None:
        sigma_base = sig_l
    elif sig_l is None:
        sigma_base = sig_s
    else:
        sigma_base = VOL_SHORT_W * sig_s + (1 - VOL_SHORT_W) * sig_l
    if not sigma_base or sigma_base <= 0:
        return None

    d_mult, d_info = depth_vol_multiplier(symbol, bundle, update=update_baseline)
    ih_mult = intrahour_multiplier(kl, elapsed_frac, sigma_base)
    sigma_eff = sigma_base * d_mult * ih_mult

    denom = sigma_eff * math.sqrt(t_remain)
    if denom <= 0:
        return None
    z = math.log(spot / ptb) / denom
    p_base = _phi(z)

    hour_return = (spot - ptb) / ptb
    tilt, tilt_parts = direction_tilt(bundle, hour_return)
    p_up = max(0.01, min(0.99, p_base + tilt))

    return {
        "symbol": symbol,
        "ptb": ptb,
        "spot": spot,
        "hour_return_pct": round(hour_return * 100, 4),
        "t_remain": round(t_remain, 4),
        "sigma_base": round(sigma_base, 6),
        "sigma_short": round(sig_s, 6) if sig_s else None,
        "sigma_long": round(sig_l, 6) if sig_l else None,
        "depth_mult": round(d_mult, 4),
        "intrahour_mult": round(ih_mult, 4),
        "sigma_eff": round(sigma_eff, 6),
        "z": round(z, 4),
        "p_base": round(p_base, 4),
        "tilt": round(tilt, 4),
        "tilt_parts": tilt_parts,
        "p_up": round(p_up, 4),
        "liq_ratio": d_info.get("liq_ratio"),
        "liq_baseline": d_info.get("liq_baseline"),
        "spread_bps": round(bundle["depth"]["spread_bps"], 3) if bundle.get("depth") else None,
        "funding_pct": round(bundle["funding"]["last"] * 100, 5) if bundle.get("funding") else None,
        "oi_change_1h_pct": round(bundle["oi"]["change_1h"] * 100, 3) if bundle.get("oi") else None,
    }


def evaluate(model: dict, pm_up_price: float, pm_down_price: float,
             *, edge_min: float | None = None) -> dict:
    """Model olasılığını piyasa fiyatıyla karşılaştır → yön, kenar, Kelly oranı.

    `edge_min` verilmezse modül varsayılanı (C1#01) kullanılır. C1#01 V2 kendi
    eşiğini geçer; iki defter aynı motoru paylaşıp farklı kapı uygular.
    """
    edge_min = EDGE_MIN if edge_min is None else edge_min
    p_up = model["p_up"]
    edge_up = p_up - pm_up_price
    edge_down = (1.0 - p_up) - pm_down_price

    if edge_up >= edge_down:
        direction, edge, price, p_model = "UP", edge_up, pm_up_price, p_up
    else:
        direction, edge, price, p_model = "DOWN", edge_down, pm_down_price, 1.0 - p_up

    reason = ""
    if not (PRICE_FLOOR <= price <= PRICE_CEIL):
        reason = f"fiyat {price:.2f} güven bandı dışında [{PRICE_FLOOR}-{PRICE_CEIL}]"
    elif edge < edge_min:
        reason = f"kenar {edge*100:+.1f} puan < {edge_min*100:.0f} puan eşiği"

    # Binary Kelly: f = (P − p) / (1 − p)
    kelly = (edge / (1.0 - price)) if price < 1.0 else 0.0
    kelly = max(0.0, min(1.0, kelly))

    return {
        "direction": direction,
        "edge": round(edge, 4),
        "pm_price": round(price, 4),
        "p_model": round(p_model, 4),
        "kelly_full": round(kelly, 4),
        "kelly_used": round(kelly * KELLY_FRACTION, 4),
        "tradable": not reason,
        "skip_reason": reason,
    }


def stake_for(balance: float, kelly_used: float) -> float:
    """Çeyrek Kelly kademesi — bakiyeye oranlı, tabanı/tavanı sabit."""
    raw = balance * kelly_used
    return round(max(MIN_STAKE, min(MAX_STAKE, raw)), 2)


if __name__ == "__main__":
    import sys
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    print(f"C101 model — {now:%d.%m.%Y %H:%M} İST\n" + "═" * 60)
    for s in (sys.argv[1:] or SYMBOLS):
        m = fair_probability(s, now, update_baseline=False)
        if not m:
            continue
        print(f"\n{s}")
        print(f"  PTB {m['ptb']:.2f} → spot {m['spot']:.2f}  ({m['hour_return_pct']:+.3f}%)"
              f"  kalan {m['t_remain']*60:.0f} dk")
        print(f"  σ: temel {m['sigma_base']*100:.3f}%  × derinlik {m['depth_mult']}"
              f"  × saat içi {m['intrahour_mult']}  = {m['sigma_eff']*100:.3f}%")
        print(f"  z={m['z']:+.3f}  P(UP) temel {m['p_base']:.3f}  eğim {m['tilt']:+.4f}"
              f"  → {m['p_up']:.3f}")
        print(f"  eğim bileşenleri: {m['tilt_parts']}")
