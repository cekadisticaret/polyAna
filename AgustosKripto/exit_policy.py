#!/usr/bin/env python3
"""Sanal defterlerin çıkış rejimi — ölçülmüş tek kaynak.

Neden var: eski rejim (her saat/4 saat zorunlu kapanış + 2×ATR zarar stopu)
kapanış-sebebi tablosunda masum görünüyordu, çünkü ATR kâr kilidi kazananları
erken alıp götürünce zorunlu kapanışa artık kaybedenler kalıyordu. Seçilim
yanlılığı temizlenince rejimin kendisi zarar üretiyor çıktı.

Ölçüm (`Test/exit_lab.py`, 50.892 gerçek işlem 06–14 Ağustos 2026, girişler
sabit, gerçek 1m fiyat verisiyle yeniden oynatıldı; simülatör kayıtlı sonucu
işlem başına medyan $0,000 sapmayla yeniden üretiyor):

  (defter,coin) başına tek pozisyon kısıtıyla gerçekçi replay
  ────────────────────────────────────────────────────────────
  eski: 1h/4h zorunlu + 2×ATR stop   46.305 işlem  net −$20.255  kom $19.052
  yeni: zaman kapanışı yok · 24s tavan ·
        6×ATR stop                    9.542 işlem  net  −$1.916  kom  $4.378
  (2026-08-15 gece canlı ince ayar: ARM 0.5 · zarar stop 3×ATR)

Gün bazlı kümelenmiş t (bağımsız birim gün — 118 defter aynı 30 coinde aynı
saatte işlem açtığı için işlem düzeyi t sahte hassasiyet üretiyor):
  eski rejim SKILL −0,0126 · t −3,42  → zarar istatistiksel olarak gerçek
  yeni rejim SKILL +0,0609 · t +1,38  → sıfırdan ayırt edilemez

Dürüst özet: yeni rejim sistemi kâra geçirmiyor, **zararın %90'ını siliyor**.
Kalan açık, brüt kenarın (%0,059) taker komisyonunun (%0,100) altında
kalmasıdır. Bunu kapatmak çıkış değil giriş/maliyet meselesi.

Denenip ELENEN yollar (aynı veriyle):
  · Zorunlu kapanışı 2/4/8/12 saate uzatmak — hepsi negatif kalıyor
  · Zarar stopunu sıkılaştırmak (1×ATR) — daha da kötü
  · ATR kâr kilidi parametrelerini oynatmak — fark gürültü seviyesinde
  · Geçmiş başarıya göre defter seçmek — walk-forward'da TERS çalışıyor
    (eğitimde SKILL>0,10 seçilen defterler testte %0,062 kenar; filtresiz %0,084)

Geri alma: `exit_policy.json` içine {"enabled": false} yaz — kod değişikliği
gerekmez, bir sonraki cron turunda eski davranışa döner.
"""
from __future__ import annotations

import json
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_DIR, "exit_policy.json")

# Ölçülen rejim. `force_time_close=False` saatlik/4 saatlik zorunlu settle'ı
# kaldırır; pozisyon ters sinyale, ATR kâr kilidine, geniş zarar stopuna veya
# süre tavanına kadar tutulur.
MEASURED = {
    "force_time_close": False,
    "max_hold_h": 24.0,
    # 2×ATR gürültü seviyesindeydi (950 işlem, %0 kazanma, −$6.004).
    # 6×ATR canlıda fiilen devreye girmiyordu; 4× hâlâ genişti.
    # 3× daha sıkı zarar kesici (~%9 teminat @6x).
    "loss_stop_atr": 3.0,
}

# Eski davranış — geri alma ve karşılaştırma için.
LEGACY = {
    "force_time_close": True,
    "max_hold_h": None,
    "loss_stop_atr": None,  # atr_profit_lock varsayılanı (2.0)
}


def _config() -> dict:
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def policy_for(group: str) -> dict:
    """Grup için çıkış rejimi. group: Test | Algoritmalar | Analizler."""
    cfg = _config()
    if cfg.get("enabled") is False:
        return dict(LEGACY)
    pol = dict(MEASURED)
    pol.update(cfg.get("default") or {})
    pol.update((cfg.get("groups") or {}).get(group) or {})
    return pol


def describe(group: str) -> str:
    p = policy_for(group)
    zaman = "1h/4h zorunlu" if p.get("force_time_close") else "zaman kapanışı yok"
    tavan = f"{p['max_hold_h']:g}s tavan" if p.get("max_hold_h") else "tavan yok"
    stop = f"{p['loss_stop_atr']:g}×ATR stop" if p.get("loss_stop_atr") else "varsayılan stop"
    return f"{zaman} · {tavan} · {stop}"


if __name__ == "__main__":
    for g in ("Test", "Algoritmalar", "Analizler"):
        print(f"{g:14} {describe(g)}")
