#!/usr/bin/env python3
"""ATR kâr kilidi (trailing lock) + zarar stop.

Kâr: peak ≥ arm×ATR$ olunca stop zirveyi takip eder (asla düşmez).
Zarar: stop_level=0 iken net uPnL ≤ −loss_stop×ATR$ ise kapat (trail */2).
Saatlik close: kârda ve stop_level>=1 ise atlanır; kapanış stop geri çekilişinde.
"""
from __future__ import annotations

import os
from typing import Any

# Varsayılan çarpanlar (env ile override)
ATR_PERIOD = int(os.environ.get("ATR_LOCK_PERIOD", "14"))
# 1.7x çok geç silahlanıyordu: 20.816 işlemin sadece 265'i kilide ulaşıyordu.
# Kayıtlı peak_upnl/atr_usd (MFE) dağılımı üzerinde eşik taraması:
#   ARM 1.7 → 265 kilit, ARM 1.4 → 564, ARM 1.2 → 811, ARM 1.0 → 1348.
# MFE 0.5 ATR'yi geçen işlemlerin kazanma oranı %23.5'ten %88.7'ye çıkıyor,
# yani erken silahlanma doğru taraf.
ARM_ATR = float(os.environ.get("ATR_LOCK_ARM", "0.5"))
TRAIL_ATR = float(os.environ.get("ATR_LOCK_TRAIL", "1.0"))
# ARM ile eşit olmamalı: stop = max(peak - TRAIL, LOCK_MIN) olduğu için
# LOCK_MIN == ARM iken kilit tam zirveye kurulur ve pozisyon silahlandığı anda
# kapanır (sabit TP'ye dönüşür, runner kalmaz). 0.5 ile kâr kilitlenir ama
# MFE 4+ bandındaki uzun kuyruk (n=54, ort. +$13.9) açık kalır.
LOCK1_MIN_ATR = float(os.environ.get("ATR_LOCK_MIN", "0.5"))
# stop_level artışı için minimum stop_upnl yükselişi (atr_$ çarpanı)
LEVEL_STEP_ATR = float(os.environ.get("ATR_LOCK_LEVEL_STEP", "0.5"))
# Zarar stop — net uPnL bu kadar ATR$ altına inince kapat (kâr kilidi yokken)
# 1.0x çok sıkıydı: normal saatlik/4h gürültüsünü de kesip ortalama kaybı büyütüyordu
# (veri: 1.0x ile tetiklenen işlemler ortalama -$2.77 net, doğal kapanan işlemler -$0.07).
LOSS_STOP_ATR = float(os.environ.get("ATR_LOSS_STOP", "2.0"))
# Açılıştan hemen sonraki gürültü/spread sıçramasıyla tetiklenmesin
LOSS_STOP_MIN_AGE_MIN = float(os.environ.get("ATR_LOSS_STOP_MIN_AGE", "10"))
# Bir defterde tutulacak maksimum ATR seviye geçmişi kaydı
LOCK_HISTORY_MAX = int(os.environ.get("ATR_LOCK_HISTORY_MAX", "20"))


def atr_from_klines(klines: list[dict], period: int | None = None) -> float | None:
    """Son bar ATR (Wilder). kline: h/l/c veya high/low/close."""
    p = ATR_PERIOD if period is None else int(period)
    if not klines or len(klines) < p + 1:
        return None

    def _h(k: dict) -> float:
        return float(k.get("h") if k.get("h") is not None else k.get("high") or 0)

    def _l(k: dict) -> float:
        return float(k.get("l") if k.get("l") is not None else k.get("low") or 0)

    def _c(k: dict) -> float:
        return float(k.get("c") if k.get("c") is not None else k.get("close") or 0)

    trs: list[float] = []
    for i in range(1, len(klines)):
        h, l, pc = _h(klines[i]), _l(klines[i]), _c(klines[i - 1])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < p:
        return None
    atr = sum(trs[:p]) / p
    for i in range(p, len(trs)):
        atr = (atr * (p - 1) + trs[i]) / p
    return float(atr) if atr > 0 else None


def atr_usd(
    margin_usd: float,
    leverage: float,
    price: float,
    atr: float,
) -> float:
    """1 ATR'nin pozisyon üzerindeki dolar etkisi ≈ notional × (ATR/price)."""
    if price <= 0 or atr <= 0:
        return 0.0
    notional = float(margin_usd) * float(leverage)
    return round(notional * (float(atr) / float(price)), 6)


def init_lock_fields(
    pos: dict,
    *,
    atr: float | None,
    atr_usd_val: float | None = None,
    margin_usd: float | None = None,
    leverage: float | None = None,
    price: float | None = None,
) -> dict:
    """Open anında ATR kilit alanlarını ekle."""
    out = dict(pos)
    margin = float(
        margin_usd
        if margin_usd is not None
        else out.get("margin_usd") or 0
    )
    lev = float(
        leverage if leverage is not None else out.get("leverage") or 1
    )
    px = float(
        price
        if price is not None
        else out.get("entry_price") or 0
    )
    a = float(atr) if atr and atr > 0 else 0.0
    au = (
        float(atr_usd_val)
        if atr_usd_val is not None
        else (atr_usd(margin, lev, px, a) if a > 0 and px > 0 else 0.0)
    )
    out["atr"] = round(a, 8) if a else 0.0
    out["atr_usd"] = round(au, 6)
    out["atr_period"] = ATR_PERIOD
    out["peak_upnl"] = float(out.get("peak_upnl") or 0)
    out["stop_upnl"] = out.get("stop_upnl")  # None until armed
    out["stop_level"] = int(out.get("stop_level") or 0)
    out["lock_armed"] = bool(out.get("lock_armed") or False)
    out.setdefault("lock_history", [])
    return out


def _cfg_from_pos(pos: dict) -> tuple[float, float, float, float]:
    arm = float(pos.get("arm_atr") or ARM_ATR)
    trail = float(pos.get("trail_atr") or TRAIL_ATR)
    lock1 = float(pos.get("lock1_min_atr") or LOCK1_MIN_ATR)
    step = float(pos.get("level_step_atr") or LEVEL_STEP_ATR)
    return arm, trail, lock1, step


def update_lock(
    pos: dict,
    upnl_net: float,
    *,
    ts: str | None = None,
    mark: float | None = None,
) -> tuple[dict, bool]:
    """peak/stop güncelle. Dönüş: (pos, changed).

    stop_level: 1 = ilk silahlanma; sonra stop_upnl her ~0.5 atr_$ yükselişte +1.
    ts/mark verilirse ve seviye artarsa lock_history'e {level, ts, stop_upnl, price}
    eklenir (yalnızca son ulaşılan seviye kaydedilir — ara seviyeler atlanır).
    """
    out = dict(pos)
    au = float(out.get("atr_usd") or 0)
    if au <= 0:
        return out, False

    arm, trail, lock1, step = _cfg_from_pos(out)
    upnl = float(upnl_net)
    peak = max(float(out.get("peak_upnl") or 0), upnl)
    out["peak_upnl"] = round(peak, 6)
    changed = False
    prev_level = int(out.get("stop_level") or 0)
    prev_stop = out.get("stop_upnl")
    prev_stop_f = float(prev_stop) if prev_stop is not None else None
    new_level = prev_level

    if prev_level == 0:
        if peak >= arm * au:
            raw = peak - trail * au
            stop = max(raw, lock1 * au)
            out["stop_upnl"] = round(stop, 6)
            out["stop_level"] = 1
            out["lock_armed"] = True
            changed = True
            new_level = 1
    else:
        raw = peak - trail * au
        stop = max(raw, lock1 * au)
        if prev_stop_f is None or stop > prev_stop_f + 1e-9:
            out["stop_upnl"] = round(stop, 6)
            # Anlamlı yükselişte seviye artır
            base = prev_stop_f if prev_stop_f is not None else 0.0
            gained = stop - base
            if gained >= step * au - 1e-9:
                bumps = int(gained / (step * au)) if step * au > 0 else 1
                new_level = prev_level + max(1, bumps)
                out["stop_level"] = new_level
            out["lock_armed"] = True
            changed = True

    if changed and new_level > prev_level:
        hist = list(out.get("lock_history") or [])
        hist.append({
            "level": new_level,
            "ts": ts,
            "stop_upnl": out.get("stop_upnl"),
            "price": mark,
        })
        out["lock_history"] = hist[-LOCK_HISTORY_MAX:]

    return out, changed


def should_stop_out(pos: dict, upnl_net: float) -> bool:
    """Equity/uPnL aktif stop seviyesine geri düştü mü?"""
    level = int(pos.get("stop_level") or 0)
    stop = pos.get("stop_upnl")
    if level < 1 or stop is None:
        return False
    return float(upnl_net) <= float(stop)


def loss_stop_threshold(pos: dict) -> float | None:
    """Zarar stop eşiği (negatif uPnL). Kâr kilidi aktifken devre dışı."""
    if int(pos.get("stop_level") or 0) >= 1:
        return None
    au = float(pos.get("atr_usd") or 0)
    if au <= 0:
        return None
    mult = float(pos.get("loss_stop_atr") or LOSS_STOP_ATR)
    if mult <= 0:
        return None
    return round(-mult * au, 6)


def should_loss_stop(pos: dict, upnl_net: float) -> bool:
    """Kâr kilidi yokken ATR zarar stop'u."""
    lim = loss_stop_threshold(pos)
    if lim is None:
        return False
    return float(upnl_net) <= lim


def should_skip_hourly_close(pos: dict, upnl_net: float) -> bool:
    """:02 close — kârda ve en az 1. stop kayıtlıysa hold."""
    if int(pos.get("stop_level") or 0) < 1:
        return False
    return float(upnl_net) > 0


def lock_equity(pos: dict) -> float | None:
    """Stop kilit equity = margin + stop_upnl."""
    stop = pos.get("stop_upnl")
    if stop is None or int(pos.get("stop_level") or 0) < 1:
        return None
    margin = float(pos.get("margin_usd") or 0)
    return round(margin + float(stop), 4)


def lock_summary(pos: dict) -> dict[str, Any]:
    """UI / log için özet alanlar."""
    level = int(pos.get("stop_level") or 0)
    lst = loss_stop_threshold(pos)
    return {
        "atr": pos.get("atr"),
        "atr_usd": pos.get("atr_usd"),
        "arm_atr": float(pos.get("arm_atr") or ARM_ATR),
        "loss_stop_atr": float(pos.get("loss_stop_atr") or LOSS_STOP_ATR),
        "peak_upnl": pos.get("peak_upnl"),
        "stop_upnl": pos.get("stop_upnl"),
        "stop_level": level,
        "lock_armed": bool(pos.get("lock_armed") or level >= 1),
        "lock_equity": lock_equity(pos),
        "runner": level >= 1,
        "loss_stop_usd": lst,
        "lock_history": pos.get("lock_history") or [],
    }
