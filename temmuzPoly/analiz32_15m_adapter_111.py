# path: temmuzPoly/analiz32_15m_adapter_111.py
"""
15M sinyal adaptörü — 111 (güçlendirilmiş sürüm)
==================================================
Analiz32/predictor.py ve Analiz32/features/*'a DOKUNULMAZ.
Bu dosya, mevcut analiz32_15m_adapter.py'nin üstüne iki ek filtre koyar:

  1) SKOR KALİTESİ EŞİĞİ
     predictor.py içindeki gate zaten ±15'te devreye giriyor, ama geçmiş
     kayıplarda composite skor 16-23 bandındaydı, kazançlarda 28-30.
     Burada adapter seviyesinde daha sıkı bir eşik uyguluyoruz (varsayılan 20).
     predictor.py'nin kendi gate'ine (15) hiç dokunmuyoruz — sadece onun
     ÜSTÜNE ek bir süzgeç koyuyoruz.

  2) TREND / MOMENTUM UYUM KONTROLÜ
     composite_signal = trend*0.3 + momentum*0.3 + volume_pressure*0.2 + (50-vol)*0.2
     Trend ve momentum birbirine ters işaretteyken (örn. trend negatif ama
     momentum pozitif) toplam yine de gate'i geçebiliyor — bu "yanıltıcı"
     sinyallerin sebebiydi (4 kayıplı örnekte 00:45 ve 03:15 tam bu paterndi).
     UP için trend_score > 0, DOWN için trend_score < 0 şartı aranır;
     aksi halde sinyal iptal edilir (skip).

Not: trend/momentum değerleri predictor.Prediction.factors listesinden
     ayrıştırılır (predictor.py zaten "trend:+12.3" "momentum:-5.0" formatında
     yazıyor) — böylece predictor.py'nin dataclass'ına yeni alan eklemeye
     gerek kalmadan, o dosya hiç değiştirilmeden okunabiliyor.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

_DIR = os.path.dirname(os.path.abspath(__file__))
_A32 = os.path.join(os.path.dirname(_DIR), "Analiz32")
sys.path.insert(0, _DIR)
sys.path.insert(0, _A32)

from btc_5m_105_algo import fetch_klines_15m
from predictor import predict_from_klines  # değişmiyor, sadece çağırıyoruz

SYMBOL_DEFAULT = "SOLUSDT"
KLINES_LIMIT = 150

# ── 111 ayarları ──────────────────────────────────────────────
SCORE_GATE_111 = 20      # predictor'ın kendi gate'i (15) üstüne ek eşik
TREND_AGREEMENT_REQUIRED = True   # trend/momentum uyum kontrolü açık/kapalı


@dataclass
class Signal15m:
    symbol: str
    direction: Optional[str]
    entry_price: float
    confidence: float
    up_score: int
    down_score: int
    factors: list
    htf_bias: str
    skip_reason: str = ""
    # 111: predictor'ın kendi gate'ini (±15) geçip GEÇTİĞİ ama 111 filtrelerinden
    # (skor eşiği / trend uyumu) elendiği durumlarda, elenmeden önceki ham yön.
    # "filtre olmasaydı ne olurdu" analizi için — predictor'ın kendi gate'inde
    # zaten hiç sinyal üretmediği durumlarda None kalır (o zaman analiz edilecek
    # bir "gölge işlem" yok, çünkü orijinal algoritma da zaten pas geçmiş olurdu).
    raw_direction: Optional[str] = None


def _parse_factor(factors: list, key: str) -> float:
    """factors listesinden 'trend:+12.3' gibi bir alanı okur."""
    prefix = key + ":"
    for f in factors or []:
        if f.startswith(prefix):
            try:
                return float(f[len(prefix):])
            except ValueError:
                return 0.0
    return 0.0


def analyze_15m(symbol: str = SYMBOL_DEFAULT) -> Optional[Signal15m]:
    try:
        klines = fetch_klines_15m(symbol, KLINES_LIMIT)
    except Exception as e:
        print(f"[A32-15M-111] kline hata {symbol}: {e}")
        return None

    if not klines or len(klines) < 80:
        return Signal15m(
            symbol=symbol, direction=None, entry_price=0.0,
            confidence=0.0, up_score=0, down_score=0,
            factors=[], htf_bias="", skip_reason="yetersiz 15m veri",
        )

    pred = predict_from_klines(symbol, klines)
    if pred is None:
        return Signal15m(
            symbol=symbol, direction=None, entry_price=float(klines[-2]["close"]),
            confidence=0.0, up_score=0, down_score=0,
            factors=[], htf_bias="", skip_reason="predict yok",
        )

    if not pred.predicted_dir:
        # predictor zaten kendi gate'inde (±15) elemiş
        return Signal15m(
            symbol=symbol, direction=None, entry_price=pred.current_price,
            confidence=0.0, up_score=pred.up_score, down_score=pred.down_score,
            factors=pred.factors, htf_bias=pred.htf_bias,
            skip_reason=f"gate (UP={pred.up_score} DOWN={pred.down_score})",
        )

    direction = pred.predicted_dir
    composite_mag = max(pred.up_score, pred.down_score)
    trend = _parse_factor(pred.factors, "trend")
    momentum = _parse_factor(pred.factors, "momentum")

    # ── 1) Skor kalitesi eşiği ───────────────────────────────
    if composite_mag < SCORE_GATE_111:
        return Signal15m(
            symbol=symbol, direction=None, entry_price=pred.current_price,
            confidence=0.0, up_score=pred.up_score, down_score=pred.down_score,
            factors=pred.factors, htf_bias=pred.htf_bias,
            skip_reason=(
                f"111: skor zayıf ({composite_mag}<{SCORE_GATE_111:.0f}) "
                f"[trend:{trend:+.1f} mom:{momentum:+.1f}]"
            ),
            raw_direction=direction,
        )

    # ── 2) Trend/momentum uyum kontrolü ──────────────────────
    if TREND_AGREEMENT_REQUIRED:
        if direction == "UP" and trend <= 0:
            return Signal15m(
                symbol=symbol, direction=None, entry_price=pred.current_price,
                confidence=0.0, up_score=pred.up_score, down_score=pred.down_score,
                factors=pred.factors, htf_bias=pred.htf_bias,
                skip_reason=(
                    f"111: trend/momentum çelişkisi — UP ama trend={trend:+.1f} "
                    f"(mom:{momentum:+.1f})"
                ),
                raw_direction=direction,
            )
        if direction == "DOWN" and trend >= 0:
            return Signal15m(
                symbol=symbol, direction=None, entry_price=pred.current_price,
                confidence=0.0, up_score=pred.up_score, down_score=pred.down_score,
                factors=pred.factors, htf_bias=pred.htf_bias,
                skip_reason=(
                    f"111: trend/momentum çelişkisi — DOWN ama trend={trend:+.1f} "
                    f"(mom:{momentum:+.1f})"
                ),
                raw_direction=direction,
            )

    # ── Her iki filtreyi de geçti ─────────────────────────────
    return Signal15m(
        symbol=symbol,
        direction=direction,
        entry_price=pred.current_price,
        confidence=pred.confidence,
        up_score=pred.up_score,
        down_score=pred.down_score,
        factors=pred.factors,
        htf_bias=pred.htf_bias,
    )
