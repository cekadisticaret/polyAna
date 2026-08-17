"""
confluence_signal_engine.py
----------------------------
Anlik fiyat grafigi icin "kararli" yon tahmini ureten sinyal motoru.

Amac: Tek bir gostergeye (RSI, MACD vs.) degil, coklu onaya (confluence)
dayanarak YUKSELIS / DUSUS / NOTR sinyali uretmek. Ham M1 gurultusunu
elemek icin iki mekanizma var:
  1) Esik (threshold): Toplam confluence skoru belli bir esigi gecmeden
     sinyal "gecerli" sayilmaz.
  2) Debounce (kararlilik): Esik gecilse bile ayni yon N ardisik hesaplamada
     tekrar etmeden ekrana/UI'a basilmaz.

Mimari (poly_predictor / 111-series adapter mantigina benzer):
  - Katman 1: TrendFilter        -> ust zaman dilimi (H1/H4) yon filtresi
  - Katman 2: MomentumVolumeFilter -> RSI + MACD + ATR (volatilite) onayi
  - Katman 3: ConfluenceEngine   -> katmanlari agirlikli skorlayip birlestirir
  - Katman 4: SignalStabilizer   -> debounce / kararlilik katmani
  - Katman 5: ShadowLogger       -> esik altinda kalan (gosterilmeyen)
                                     sinyalleri de loglar (sonradan kalibrasyon icin)

Kullanim (asagida __main__ ornegi de var):
    engine = SignalEngine(config=EngineConfig())
    result = engine.process_candle(m1_candle, htf_candles=h1_df)
    # result.direction: "UP" | "DOWN" | "NEUTRAL"
    # result.confidence: 0-100
    # result.is_stable: bool  (UI'da sadece bu True iken goster)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from collections import deque
from typing import Optional, Deque, List

import pandas as pd
import numpy as np


# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------

@dataclass
class EngineConfig:
    # Katman agirliklari (toplami 100 olmak zorunda degil, orantisal calisir)
    weight_trend: float = 40.0
    weight_momentum: float = 30.0
    weight_pattern: float = 30.0

    # Confluence esigi: bu skorun altinda sinyal "NOTR" sayilir
    signal_threshold: float = 55.0

    # Kararlilik (debounce): ayni yonun kac ardisik hesaplamada
    # tekrar etmesi gerektigi
    stability_window: int = 3

    # Momentum parametreleri
    rsi_period: int = 14
    rsi_overbought: float = 65.0
    rsi_oversold: float = 35.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # Volatilite rejimi (ATR) - dusuk volatilitede sinyal agirligini kirp
    atr_period: int = 14
    atr_low_vol_percentile: float = 20.0  # bu yuzdelik altindaysa "sakin piyasa"
    low_vol_dampening: float = 0.5        # sakin piyasada skor carpani

    # Basit mum-formasyonu / fiyat aksiyonu agirligi icin lookback
    pattern_lookback: int = 5

    # Shadow log dosyasi (esik altindaki sinyaller dahil hepsini yazar)
    shadow_log_path: str = "shadow_signals.jsonl"


# ----------------------------------------------------------------------------
# ORTAK YARDIMCI GOSTERGELER (dis bagimlilik yok - pandas/numpy yeterli)
# ----------------------------------------------------------------------------

def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def _macd(close: pd.Series, fast: int, slow: int, signal: int):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period).mean()


# ----------------------------------------------------------------------------
# KATMAN 1: TREND FILTRESI (ust zaman dilimi)
# ----------------------------------------------------------------------------

class TrendFilter:
    """H1/H4 gibi ust zaman diliminin yonunu belirler.
    M1 sinyali trendin tersineyse skoru zayiflatir."""

    def __init__(self, config: EngineConfig):
        self.cfg = config

    def score(self, htf_df: pd.DataFrame) -> float:
        """Donus: -100 (guclu dusus trendi) .. +100 (guclu yukselis trendi)"""
        if htf_df is None or len(htf_df) < 20:
            return 0.0  # yeterli veri yoksa notr, filtre devre disi kalir

        close = htf_df["close"]
        ema_fast = close.ewm(span=20, adjust=False).mean()
        ema_slow = close.ewm(span=50, adjust=False).mean() if len(close) >= 50 else close.ewm(span=20).mean()

        last_fast, last_slow = ema_fast.iloc[-1], ema_slow.iloc[-1]
        spread_pct = (last_fast - last_slow) / last_slow * 100

        # spread yuzdesini -100..100 araligina sikistir (ampirik olcek, kalibre edilebilir)
        score = float(np.clip(spread_pct * 500, -100, 100))
        return score


# ----------------------------------------------------------------------------
# KATMAN 2: MOMENTUM + VOLUM (ATR ile volatilite rejimi) ONAYI
# ----------------------------------------------------------------------------

class MomentumVolumeFilter:
    def __init__(self, config: EngineConfig):
        self.cfg = config
        self._atr_history: Deque[float] = deque(maxlen=500)

    def score(self, df: pd.DataFrame) -> float:
        """Donus: -100 .. +100. Dusuk volatilitede otomatik sonumlenir."""
        if len(df) < max(self.cfg.rsi_period, self.cfg.macd_slow) + 5:
            return 0.0

        rsi = _rsi(df["close"], self.cfg.rsi_period).iloc[-1]
        macd_line, signal_line, hist = _macd(
            df["close"], self.cfg.macd_fast, self.cfg.macd_slow, self.cfg.macd_signal
        )
        macd_hist_last = hist.iloc[-1]
        macd_hist_prev = hist.iloc[-2] if len(hist) > 1 else 0.0

        # RSI bileseni: asiri alim/satim bolgesinden donus sinyali
        if rsi >= self.cfg.rsi_overbought:
            rsi_score = -min((rsi - self.cfg.rsi_overbought) * 4, 100)
        elif rsi <= self.cfg.rsi_oversold:
            rsi_score = min((self.cfg.rsi_oversold - rsi) * 4, 100)
        else:
            rsi_score = (rsi - 50) * 1.5  # notr bolgede hafif egilim

        # MACD bileseni: histogramin yonu ve ivmesi
        macd_score = float(np.clip((macd_hist_last - macd_hist_prev) * 800
                                    + np.sign(macd_hist_last) * 20, -100, 100))

        raw_score = (rsi_score * 0.5) + (macd_score * 0.5)

        # ATR volatilite rejimi: sakin piyasada skoru sonumle
        atr = _atr(df, self.cfg.atr_period)
        atr_last = atr.iloc[-1]
        if not np.isnan(atr_last):
            self._atr_history.append(float(atr_last))

        if len(self._atr_history) >= 20:
            percentile = float(
                (np.array(self._atr_history) < atr_last).mean() * 100
            )
            if percentile < self.cfg.atr_low_vol_percentile:
                raw_score *= self.cfg.low_vol_dampening

        return float(np.clip(raw_score, -100, 100))


# ----------------------------------------------------------------------------
# KATMAN 3: BASIT FIYAT AKSIYONU / PATTERN SKORU
# ----------------------------------------------------------------------------

class PatternFilter:
    """Son N mumun govde/golge oranlarina bakarak basit bir yon egilimi
    cikarir. Kendi candle_pattern_engine.py'deki formasyon tanima mantigini
    buraya tasiyip genisletebilirsin."""

    def __init__(self, config: EngineConfig):
        self.cfg = config

    def score(self, df: pd.DataFrame) -> float:
        n = self.cfg.pattern_lookback
        if len(df) < n:
            return 0.0

        recent = df.tail(n)
        bodies = recent["close"] - recent["open"]
        bullish_ratio = (bodies > 0).sum() / n

        # ardisik govde buyuklugu agirlikli yon
        weighted = (bodies / recent["close"]).sum() * 10000  # baz puan (pip benzeri olcek)

        directional_bias = (bullish_ratio - 0.5) * 200  # -100..100
        momentum_component = float(np.clip(weighted, -60, 60))

        score = (directional_bias * 0.6) + (momentum_component * 0.4)
        return float(np.clip(score, -100, 100))


# ----------------------------------------------------------------------------
# KATMAN 4: CONFLUENCE + KARARLILIK (DEBOUNCE)
# ----------------------------------------------------------------------------

@dataclass
class SignalResult:
    timestamp: float
    raw_score: float          # -100..100, agirlikli toplam
    confidence: float         # 0..100, abs(raw_score)
    direction: str            # "UP" | "DOWN" | "NEUTRAL"
    is_stable: bool           # debounce gecti mi -> UI'da gosterilmeli mi
    layer_scores: dict = field(default_factory=dict)


class SignalStabilizer:
    """Esik gecilmis yon N ardisik hesaplamada tekrar etmeden
    'kararli' sayilmaz. Bu, anlik flip-flop sinyalleri engeller."""

    def __init__(self, config: EngineConfig):
        self.cfg = config
        self._history: Deque[str] = deque(maxlen=config.stability_window)

    def update(self, direction: str) -> bool:
        self._history.append(direction)
        if len(self._history) < self.cfg.stability_window:
            return False
        return len(set(self._history)) == 1 and direction != "NEUTRAL"


class ConfluenceEngine:
    def __init__(self, config: EngineConfig):
        self.cfg = config
        self.trend = TrendFilter(config)
        self.momentum = MomentumVolumeFilter(config)
        self.pattern = PatternFilter(config)

    def compute(self, m1_df: pd.DataFrame, htf_df: Optional[pd.DataFrame]) -> SignalResult:
        trend_score = self.trend.score(htf_df)
        momentum_score = self.momentum.score(m1_df)
        pattern_score = self.pattern.score(m1_df)

        cfg = self.cfg
        total_weight = cfg.weight_trend + cfg.weight_momentum + cfg.weight_pattern
        raw = (
            trend_score * cfg.weight_trend
            + momentum_score * cfg.weight_momentum
            + pattern_score * cfg.weight_pattern
        ) / total_weight

        confidence = abs(raw)
        if confidence < cfg.signal_threshold:
            direction = "NEUTRAL"
        else:
            direction = "UP" if raw > 0 else "DOWN"

        return SignalResult(
            timestamp=time.time(),
            raw_score=raw,
            confidence=confidence,
            direction=direction,
            is_stable=False,  # SignalEngine tarafinda set edilecek
            layer_scores={
                "trend": trend_score,
                "momentum": momentum_score,
                "pattern": pattern_score,
            },
        )


# ----------------------------------------------------------------------------
# KATMAN 5: SHADOW LOGGER (esik altindaki sinyaller dahil hepsi loglanir)
# ----------------------------------------------------------------------------

class ShadowLogger:
    """Gosterilmeyen (NEUTRAL / kararsiz) sinyalleri de dahil her hesaplamayi
    diske yazar. Amac: sonradan esik/agirlik kalibrasyonu yapabilmek -
    poly_predictor'daki shadow log mantiginin aynisi."""

    def __init__(self, config: EngineConfig):
        self.path = config.shadow_log_path

    def log(self, result: SignalResult):
        record = {
            "ts": result.timestamp,
            "raw_score": round(result.raw_score, 2),
            "confidence": round(result.confidence, 2),
            "direction": result.direction,
            "is_stable": result.is_stable,
            "layers": {k: round(v, 2) for k, v in result.layer_scores.items()},
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ----------------------------------------------------------------------------
# ORKESTRATOR: dis dunyanin gordugu tek arayuz
# ----------------------------------------------------------------------------

class SignalEngine:
    def __init__(self, config: Optional[EngineConfig] = None):
        self.cfg = config or EngineConfig()
        self.confluence = ConfluenceEngine(self.cfg)
        self.stabilizer = SignalStabilizer(self.cfg)
        self.shadow_logger = ShadowLogger(self.cfg)

    def process_candle(self, m1_df: pd.DataFrame, htf_df: Optional[pd.DataFrame] = None) -> SignalResult:
        """
        m1_df: en azindan ['open','high','low','close'] kolonlarini iceren,
               zaman sirali M1 mum verisi (son satir en guncel mum).
        htf_df: ayni formatta H1/H4 veri (trend filtresi icin). None ise
                trend katmani notr kalir.
        """
        result = self.confluence.compute(m1_df, htf_df)
        result.is_stable = self.stabilizer.update(result.direction)
        self.shadow_logger.log(result)
        return result


# ----------------------------------------------------------------------------
# ORNEK KULLANIM
# ----------------------------------------------------------------------------

if __name__ == "__main__":
    # Rastgele ornek veri ile hizli test
    rng = np.random.default_rng(42)
    n = 200
    prices = 4470 + np.cumsum(rng.normal(0, 0.3, n))
    m1 = pd.DataFrame({
        "open": prices + rng.normal(0, 0.05, n),
        "high": prices + rng.uniform(0.1, 0.4, n),
        "low": prices - rng.uniform(0.1, 0.4, n),
        "close": prices,
    })

    htf_prices = 4470 + np.cumsum(rng.normal(0.05, 0.5, 80))
    htf = pd.DataFrame({
        "open": htf_prices,
        "high": htf_prices + 1,
        "low": htf_prices - 1,
        "close": htf_prices,
    })

    engine = SignalEngine()
    for i in range(60, n):
        window = m1.iloc[:i]
        res = engine.process_candle(window, htf)
        if res.is_stable:
            print(
                f"[{i}] YON: {res.direction:7s} | guven: {res.confidence:5.1f} | "
                f"katmanlar: {res.layer_scores}"
            )
