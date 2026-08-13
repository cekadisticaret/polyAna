"""
candle_pattern_engine.py
=========================
Mum (candlestick) pattern tanima + destek/direnc seviye tespiti + confluence
skorlama motoru.

Tasarim felsefesi (mevcut adapter pattern'inle uyumlu):
- Bu dosya CORE degildir, bagimsiz bir modul olarak calisir.
- Diger core dosyalarina (poly_predictor, Analiz32 vb.) DOKUNMAZ.
- Disariya sadece fonksiyonlar/siniflar export eder; adapter'in bunlari
  import edip kendi feature vektorune ekleyecegi sekilde tasarlandi.
- TA-Lib GEREKTIRMEZ (kurulumu can sikici oldugu icin saf Python/NumPy
  ile ayni mantigi implement ettik). Istersen TA-Lib entegrasyonunu en
  alta ayri bir opsiyonel fonksiyon olarak ekledim.

Kullanim ozeti:
    engine = CandleEngine(open_, high, low, close)
    patterns = engine.detect_patterns()          # her mum icin pattern skorlari
    levels   = engine.detect_levels()             # destek/direnc seviyeleri
    signal   = engine.confluence_score()           # -100..+100 yon skoru

Author: (Cem icin) - poly_predictor / Analiz32 entegrasyonuna uygun
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple


# =============================================================================
# 1) TEMEL VERI YAPISI
# =============================================================================

@dataclass
class Candle:
    """Tek bir mum. Piksel-> fiyat kalibrasyonundan veya API'den gelen ham veri."""
    open: float
    high: float
    low: float
    close: float
    timestamp: Optional[float] = None
    volume: Optional[float] = None

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        r = self.high - self.low
        return r if r > 0 else 1e-9  # sifira bolme koruması

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def is_bull(self) -> bool:
        return self.close > self.open

    @property
    def is_bear(self) -> bool:
        return self.close < self.open

    @property
    def body_ratio(self) -> float:
        """Govde / toplam range orani. 1.0 = marubozu, 0.0 = doji."""
        return self.body / self.range


@dataclass
class Level:
    """Tespit edilen destek/direnc seviyesi."""
    price: float
    kind: str            # "support" | "resistance"
    touches: int          # kac kez dokunulmus
    strength: float        # 0-100 arasi normalize güç skoru
    last_touch_idx: int    # en son dokunulan mum indexi


# =============================================================================
# 2) YARDIMCI FONKSIYONLAR
# =============================================================================

def candles_from_arrays(open_: np.ndarray, high: np.ndarray,
                         low: np.ndarray, close: np.ndarray,
                         timestamps: Optional[np.ndarray] = None,
                         volume: Optional[np.ndarray] = None) -> List[Candle]:
    """OHLC(V) numpy dizilerinden Candle listesi uretir."""
    n = len(open_)
    ts = timestamps if timestamps is not None else [None] * n
    vol = volume if volume is not None else [None] * n
    return [
        Candle(open=float(open_[i]), high=float(high[i]),
               low=float(low[i]), close=float(close[i]),
               timestamp=ts[i], volume=vol[i])
        for i in range(n)
    ]


# =============================================================================
# 3) CANDLESTICK PATTERN TANIMA (saf Python, TA-Lib mantigina yakin esikler)
# =============================================================================

class PatternDetector:
    """
    Her fonksiyon +100 (bullish), -100 (bearish) ya da 0 (yok) doner.
    TA-Lib'in CDL* fonksiyonlariyla ayni konvansiyonu kullaniyoruz ki
    ileride TA-Lib'e gecmek istersen kod tarafinda degisiklik gerekmesin.
    """

    DOJI_THRESHOLD = 0.1          # govde/range < %10 ise doji
    MARUBOZU_THRESHOLD = 0.95      # govde/range > %95 ise marubozu
    LONG_WICK_RATIO = 2.0          # fitil, govdenin en az 2 kati ise "uzun"

    @staticmethod
    def doji(c: Candle) -> int:
        # 1 = tespit (kararsizlik); agirlikli skora katilmaz (pattern_net_score atlar)
        return 1 if c.body_ratio < PatternDetector.DOJI_THRESHOLD else 0

    @staticmethod
    def marubozu(c: Candle) -> int:
        if c.body_ratio > PatternDetector.MARUBOZU_THRESHOLD:
            return 100 if c.is_bull else -100
        return 0

    @staticmethod
    def hammer(c: Candle) -> int:
        """Kucuk govde, uzun alt fitil, kisa/yok ust fitil -> bullish reversal adayi."""
        if c.body == 0:
            return 0
        if (c.lower_wick > PatternDetector.LONG_WICK_RATIO * c.body
                and c.upper_wick < c.body * 0.5):
            return 100
        return 0

    @staticmethod
    def shooting_star(c: Candle) -> int:
        """Kucuk govde, uzun ust fitil, kisa/yok alt fitil -> bearish reversal adayi."""
        if c.body == 0:
            return 0
        if (c.upper_wick > PatternDetector.LONG_WICK_RATIO * c.body
                and c.lower_wick < c.body * 0.5):
            return -100
        return 0

    @staticmethod
    def engulfing(prev: Candle, cur: Candle) -> int:
        """Onceki mumu govde olarak tamamen yutan mum -> guclu reversal sinyali."""
        if prev.body == 0:
            return 0
        bull_engulf = (cur.is_bull and prev.is_bear
                       and cur.close >= prev.open and cur.open <= prev.close)
        bear_engulf = (cur.is_bear and prev.is_bull
                       and cur.open >= prev.close and cur.close <= prev.open)
        if bull_engulf:
            return 100
        if bear_engulf:
            return -100
        return 0

    @staticmethod
    def piercing_or_darkcloud(prev: Candle, cur: Candle) -> int:
        """Piercing line (bullish) / Dark cloud cover (bearish) - govdenin %50+'sini geri alma."""
        mid = (prev.open + prev.close) / 2
        if prev.is_bear and cur.is_bull and cur.open < prev.close and cur.close > mid:
            return 100  # piercing line
        if prev.is_bull and cur.is_bear and cur.open > prev.close and cur.close < mid:
            return -100  # dark cloud cover
        return 0

    @staticmethod
    def morning_or_evening_star(c1: Candle, c2: Candle, c3: Candle) -> int:
        """3 mumluk yildiz formasyonu: buyuk mum -> kucuk govde (kararsizlik) -> ters yonlu buyuk mum."""
        small_middle = c2.body_ratio < 0.3
        if not small_middle:
            return 0
        # Morning star: dusus -> kararsizlik -> yukselis
        if c1.is_bear and c1.body_ratio > 0.5 and c3.is_bull \
                and c3.close > (c1.open + c1.close) / 2:
            return 100
        # Evening star: yukselis -> kararsizlik -> dusus
        if c1.is_bull and c1.body_ratio > 0.5 and c3.is_bear \
                and c3.close < (c1.open + c1.close) / 2:
            return -100
        return 0

    @staticmethod
    def three_soldiers_or_crows(c1: Candle, c2: Candle, c3: Candle) -> int:
        """3 ardisik guclu ayni yonlu mum -> momentum devam sinyali."""
        all_bull = c1.is_bull and c2.is_bull and c3.is_bull
        all_bear = c1.is_bear and c2.is_bear and c3.is_bear
        increasing_closes = c1.close < c2.close < c3.close
        decreasing_closes = c1.close > c2.close > c3.close
        strong_bodies = all(c.body_ratio > 0.6 for c in (c1, c2, c3))
        if all_bull and increasing_closes and strong_bodies:
            return 100
        if all_bear and decreasing_closes and strong_bodies:
            return -100
        return 0


def detect_all_patterns(candles: List[Candle]) -> List[Dict[str, int]]:
    """
    Her mum indexi icin tespit edilen tum pattern skorlarini dondurur.
    Cok mumluk pattern'ler (engulfing, star, soldiers) o mumun index'ine yazilir
    (yani pattern'i TAMAMLAYAN son muma).
    """
    n = len(candles)
    results: List[Dict[str, int]] = [dict() for _ in range(n)]

    for i, c in enumerate(candles):
        d = results[i]
        d["doji"] = PatternDetector.doji(c)
        d["marubozu"] = PatternDetector.marubozu(c)
        d["hammer"] = PatternDetector.hammer(c)
        d["shooting_star"] = PatternDetector.shooting_star(c)

        if i >= 1:
            d["engulfing"] = PatternDetector.engulfing(candles[i - 1], c)
            d["piercing_darkcloud"] = PatternDetector.piercing_or_darkcloud(candles[i - 1], c)

        if i >= 2:
            d["star"] = PatternDetector.morning_or_evening_star(
                candles[i - 2], candles[i - 1], c)
            d["three_soldiers_crows"] = PatternDetector.three_soldiers_or_crows(
                candles[i - 2], candles[i - 1], c)

    return results


def pattern_net_score(pattern_dict: Dict[str, int], weights: Optional[Dict[str, float]] = None) -> float:
    """
    Bir mumun tum pattern skorlarini agirlikli ortalayarak tek bir net skora indirger.
    Varsayilan agirliklar: cok mumluk / guclu formasyonlar daha agirlikli.
    """
    default_weights = {
        "doji": 0.3,               # tek basina zayif sinyal, sadece kararsizlik gostergesi
        "marubozu": 0.6,
        "hammer": 0.8,
        "shooting_star": 0.8,
        "engulfing": 1.0,
        "piercing_darkcloud": 0.9,
        "star": 1.2,                # 3 mumluk formasyon, en guclu
        "three_soldiers_crows": 1.1,
    }
    w = weights or default_weights
    total_w = 0.0
    total_score = 0.0
    for key, val in pattern_dict.items():
        if val == 0 or key == "doji":
            continue
        weight = w.get(key, 0.5)
        total_score += val * weight
        total_w += weight
    if total_w == 0:
        return 0.0
    return total_score / total_w  # -100..+100 araliginda agirlikli ortalama


# =============================================================================
# 4) DESTEK / DIRENC SEVIYE TESPITI
# =============================================================================

def find_pivots(candles: List[Candle], left: int = 3, right: int = 3) -> Tuple[List[int], List[int]]:
    """
    Local pivot high / pivot low indexlerini bulur.
    left/right: pivotun soldan/sagdan kac mum tarafindan 'onaylanmasi' gerektigi.
    Senin chartindaki gibi swing high/low noktalarini yakalar.
    """
    highs = np.array([c.high for c in candles])
    lows = np.array([c.low for c in candles])
    n = len(candles)

    pivot_highs, pivot_lows = [], []
    for i in range(left, n - right):
        window_h = highs[i - left:i + right + 1]
        window_l = lows[i - left:i + right + 1]
        if highs[i] == window_h.max() and np.argmax(window_h) == left:
            pivot_highs.append(i)
        if lows[i] == window_l.min() and np.argmin(window_l) == left:
            pivot_lows.append(i)

    return pivot_highs, pivot_lows


def cluster_levels(candles: List[Candle], pivot_indices: List[int],
                    kind: str, price_tolerance_pct: float = 0.15) -> List[Level]:
    """
    Pivot noktalarini fiyat yakinligina gore kumeler (cluster) ve her kumeyi
    tek bir seviyeye indirger. Ayni bolgeye kac kez dokunulmus -> 'strength'.

    price_tolerance_pct: seviyeleri ayni kabul etmek icin fiyat farki yuzdesi
    (orn 0.15 -> fiyatin %0.15'i icindeki pivotlar ayni seviye sayilir)
    """
    if not pivot_indices:
        return []

    prices = [(idx, candles[idx].high if kind == "resistance" else candles[idx].low)
              for idx in pivot_indices]
    prices.sort(key=lambda x: x[1])

    clusters: List[List[Tuple[int, float]]] = []
    current_cluster = [prices[0]]

    for idx, price in prices[1:]:
        cluster_avg = np.mean([p for _, p in current_cluster])
        tolerance = cluster_avg * (price_tolerance_pct / 100)
        if abs(price - cluster_avg) <= tolerance:
            current_cluster.append((idx, price))
        else:
            clusters.append(current_cluster)
            current_cluster = [(idx, price)]
    clusters.append(current_cluster)

    levels = []
    max_touches = max(len(c) for c in clusters) if clusters else 1
    for cluster in clusters:
        avg_price = float(np.mean([p for _, p in cluster]))
        touches = len(cluster)
        last_idx = max(idx for idx, _ in cluster)
        # strength: dokunma sayisi (normalize) - basit ama etkili bir gucl metrigi
        strength = min(100.0, (touches / max_touches) * 100.0 * (1 + 0.1 * touches))
        levels.append(Level(price=avg_price, kind=kind, touches=touches,
                             strength=round(strength, 1), last_touch_idx=last_idx))

    return sorted(levels, key=lambda lv: -lv.strength)


def detect_levels(candles: List[Candle], left: int = 3, right: int = 3,
                   price_tolerance_pct: float = 0.15) -> Dict[str, List[Level]]:
    """Tum destek ve direnc seviyelerini gucluluk sirasina gore doner."""
    pivot_highs, pivot_lows = find_pivots(candles, left, right)
    resistances = cluster_levels(candles, pivot_highs, "resistance", price_tolerance_pct)
    supports = cluster_levels(candles, pivot_lows, "support", price_tolerance_pct)
    return {"support": supports, "resistance": resistances}


def distance_to_nearest_level(current_price: float, levels: Dict[str, List[Level]]) -> Dict[str, Optional[Tuple[Level, float]]]:
    """
    Guncel fiyata en yakin destek ve direnci, aradaki yuzde mesafeyle birlikte doner.
    Confluence skorlamada 'fiyat seviyeye ne kadar yakin' bilgisini kullanmak icin.
    """
    result = {"nearest_support": None, "nearest_resistance": None}

    supports_below = [lv for lv in levels["support"] if lv.price <= current_price]
    resistances_above = [lv for lv in levels["resistance"] if lv.price >= current_price]

    if supports_below:
        nearest = max(supports_below, key=lambda lv: lv.price)
        dist_pct = (current_price - nearest.price) / current_price * 100
        result["nearest_support"] = (nearest, round(dist_pct, 3))

    if resistances_above:
        nearest = min(resistances_above, key=lambda lv: lv.price)
        dist_pct = (nearest.price - current_price) / current_price * 100
        result["nearest_resistance"] = (nearest, round(dist_pct, 3))

    return result


# =============================================================================
# 5) CONFLUENCE SKORLAMA - pattern + seviye + trend'i tek skora birlestirir
# =============================================================================

def simple_trend(candles: List[Candle], lookback: int = 10) -> float:
    """
    Basit trend yonu: son N mumun kapanislari arasindaki lineer egim, normalize.
    +1 = guclu yukselis, -1 = guclu dusus, 0 = yatay.
    """
    if len(candles) < lookback:
        lookback = len(candles)
    closes = np.array([c.close for c in candles[-lookback:]])
    if len(closes) < 2:
        return 0.0
    x = np.arange(len(closes))
    slope = np.polyfit(x, closes, 1)[0]
    normalized = slope / (np.mean(closes) + 1e-9) * len(closes)
    return float(np.clip(normalized * 10, -1, 1))


@dataclass
class ConfluenceResult:
    score: float                     # -100 (guclu bearish) .. +100 (guclu bullish)
    pattern_component: float
    level_component: float
    trend_component: float
    nearest_support: Optional[Tuple[Level, float]]
    nearest_resistance: Optional[Tuple[Level, float]]
    explanation: str


def confluence_score(candles: List[Candle],
                      pattern_weight: float = 0.4,
                      level_weight: float = 0.35,
                      trend_weight: float = 0.25,
                      level_proximity_threshold_pct: float = 0.5) -> ConfluenceResult:
    """
    Pattern + seviye yakinligi + trend'i birlestirip -100..+100 arasi tek bir
    yon/guc skoru uretir. Bu skoru senin 111-series gate/trend/momentum
    filtrelerine EK bir confluence katmani olarak besleyebilirsin.
    """
    if len(candles) < 3:
        raise ValueError("Confluence skoru icin en az 3 mum gerekli.")

    patterns = detect_all_patterns(candles)
    last_pattern_score = pattern_net_score(patterns[-1])

    levels = detect_levels(candles)
    current_price = candles[-1].close
    proximity = distance_to_nearest_level(current_price, levels)

    level_score = 0.0
    explanation_parts = []

    ns = proximity["nearest_support"]
    nr = proximity["nearest_resistance"]

    if ns and ns[1] <= level_proximity_threshold_pct:
        # Fiyat guclu bir destege yakin -> bullish bias (tutma ihtimali)
        level_score += ns[0].strength * (1 - ns[1] / level_proximity_threshold_pct)
        explanation_parts.append(
            f"Fiyat {ns[1]:.2f}% mesafede guclu destege yakin (strength={ns[0].strength})")

    if nr and nr[1] <= level_proximity_threshold_pct:
        # Fiyat guclu bir dirence yakin -> bearish bias (red ihtimali)
        level_score -= nr[0].strength * (1 - nr[1] / level_proximity_threshold_pct)
        explanation_parts.append(
            f"Fiyat {nr[1]:.2f}% mesafede guclu dirence yakin (strength={nr[0].strength})")

    level_score = float(np.clip(level_score, -100, 100))

    trend = simple_trend(candles) * 100

    final_score = (last_pattern_score * pattern_weight
                   + level_score * level_weight
                   + trend * trend_weight)
    final_score = float(np.clip(final_score, -100, 100))

    if not explanation_parts:
        explanation_parts.append("Yakin bir destek/direnc seviyesi yok.")

    return ConfluenceResult(
        score=round(final_score, 1),
        pattern_component=round(last_pattern_score, 1),
        level_component=round(level_score, 1),
        trend_component=round(trend, 1),
        nearest_support=ns,
        nearest_resistance=nr,
        explanation=" | ".join(explanation_parts),
    )


# =============================================================================
# 6) YUKSEK SEVIYE WRAPPER - Adapter'inin cagiracagi tek fonksiyon
# =============================================================================

class CandleEngine:
    """
    poly_predictor / Analiz32 adapter'inin dogrudan cagirabilecegi ana sinif.
    Core dosyalara dokunmadan, disaridan import edilip kullanilir:

        from candle_pattern_engine import CandleEngine
        engine = CandleEngine(open_arr, high_arr, low_arr, close_arr)
        result = engine.confluence_score()
        if result.score > 50:
            ... bullish bias, mevcut gate/trend filtrenle birlestir ...
    """

    def __init__(self, open_: np.ndarray, high: np.ndarray,
                 low: np.ndarray, close: np.ndarray,
                 timestamps: Optional[np.ndarray] = None,
                 volume: Optional[np.ndarray] = None):
        self.candles = candles_from_arrays(open_, high, low, close, timestamps, volume)

    def detect_patterns(self) -> List[Dict[str, int]]:
        return detect_all_patterns(self.candles)

    def detect_levels(self, left: int = 3, right: int = 3,
                       price_tolerance_pct: float = 0.15) -> Dict[str, List[Level]]:
        return detect_levels(self.candles, left, right, price_tolerance_pct)

    def confluence_score(self, **kwargs) -> ConfluenceResult:
        return confluence_score(self.candles, **kwargs)

    def generate_report(self, **kwargs) -> str:
        """Chart'i insan diliyle yorumlayan okunabilir bir rapor uretir (asil amac budur)."""
        return generate_analysis_report(self.candles, **kwargs)

    def to_feature_dict(self) -> Dict[str, float]:
        """
        Analiz32 feature vektorune EKLEME yapmak icin duz bir dict.
        Adapter bunu kendi feature setine merge edebilir.
        """
        result = self.confluence_score()
        last_pattern = pattern_net_score(self.detect_patterns()[-1])
        levels = self.detect_levels()
        return {
            "candle_confluence_score": result.score,
            "candle_pattern_score": last_pattern,
            "candle_level_score": result.level_component,
            "candle_trend_score": result.trend_component,
            "candle_support_count": len(levels["support"]),
            "candle_resistance_count": len(levels["resistance"]),
        }


# =============================================================================
# 7) CHART RAPORLAMA - insan diliyle okunabilir analiz raporu
# =============================================================================

PATTERN_TR_NAMES = {
    "doji": "Doji (kararsizlik)",
    "marubozu": "Marubozu (guclu tek yonlu mum)",
    "hammer": "Hammer (dip donus adayi)",
    "shooting_star": "Shooting Star (tepe donus adayi)",
    "engulfing": "Engulfing (yutan mum - donus sinyali)",
    "piercing_darkcloud": "Piercing/Dark Cloud (govde geri alma)",
    "star": "Morning/Evening Star (3 mumluk donus formasyonu)",
    "three_soldiers_crows": "Three Soldiers/Crows (momentum devami)",
}


def _pattern_label(name: str, value: int) -> str:
    base = PATTERN_TR_NAMES.get(name, name)
    if name == "doji" and value != 0:
        return f"{base} (yon sinyali degil)"
    yon = "BULLISH" if value > 0 else "BEARISH"
    return f"{base} -> {yon}"


def _describe_trend(trend_value: float) -> str:
    """trend_value: -1..+1 arasi (simple_trend ciktisi)."""
    if trend_value > 0.5:
        return "guclu yukselis trendi"
    if trend_value > 0.15:
        return "hafif yukselis egilimi"
    if trend_value < -0.5:
        return "guclu dusus trendi"
    if trend_value < -0.15:
        return "hafif dusus egilimi"
    return "yatay / kararsiz seyir"


def _describe_score(score: float) -> str:
    if score > 60:
        return "GUCLU YUKSELIS sinyali"
    if score > 25:
        return "hafif yukselis egilimli"
    if score < -60:
        return "GUCLU DUSUS sinyali"
    if score < -25:
        return "hafif dusus egilimli"
    return "NET BIR YON YOK - kararsiz/range bolgesi"


def generate_analysis_report(candles: List[Candle],
                              recent_pattern_window: int = 5,
                              level_left_right: int = 3,
                              level_tolerance_pct: float = 0.15) -> str:
    """
    Chart'i baştan sona okuyup insan diliyle bir analiz raporu uretir.
    Amac: kod ciktisini yorumlamak degil, dogrudan okunabilir bir "chart yorumu"
    almak. poly_predictor pipeline'ina feature basmiyor, sadece raporluyor.
    """
    if len(candles) < 5:
        return "Rapor icin en az 5 mum gerekli."

    lines = []
    n = len(candles)
    current_price = candles[-1].close

    # ---- 1) Genel ozet basligi ----
    trend_val = simple_trend(candles, lookback=min(20, n))
    lines.append("=" * 60)
    lines.append("CHART ANALIZ RAPORU")
    lines.append("=" * 60)
    lines.append(f"Toplam mum sayisi : {n}")
    lines.append(f"Guncel fiyat      : {current_price:.4f}")
    lines.append(f"Genel egilim      : {_describe_trend(trend_val)} (trend katsayisi: {trend_val:+.2f})")
    lines.append("")

    # ---- 2) Son mumlarda tespit edilen pattern'ler ----
    lines.append("-" * 60)
    lines.append(f"SON {recent_pattern_window} MUMDA TESPIT EDILEN FORMASYONLAR")
    lines.append("-" * 60)
    all_patterns = detect_all_patterns(candles)
    found_any = False
    for i in range(max(0, n - recent_pattern_window), n):
        active = {k: v for k, v in all_patterns[i].items() if v != 0}
        if not active:
            continue
        found_any = True
        offset = n - i  # kac mum once (1 = son mum)
        label = "SON MUM" if offset == 1 else f"{offset} mum once"
        for pat_name, pat_val in active.items():
            lines.append(f"  [{label}] {_pattern_label(pat_name, pat_val)}")
    if not found_any:
        lines.append("  Belirgin bir formasyon tespit edilmedi (govdeler/fitiller net sinyal esigin altinda).")
    lines.append("")

    # ---- 3) Destek / Direnc seviyeleri ----
    lines.append("-" * 60)
    lines.append("DESTEK / DIRENC SEVIYELERI")
    lines.append("-" * 60)
    levels = detect_levels(candles, left=level_left_right, right=level_left_right,
                            price_tolerance_pct=level_tolerance_pct)

    top_resistances = levels["resistance"][:3]
    top_supports = levels["support"][:3]

    if top_resistances:
        lines.append("  Direnc bolgeleri (guclulukten en yuksege):")
        for lv in top_resistances:
            lines.append(f"    - {lv.price:.4f}  | {lv.touches} kez test edilmis | guc={lv.strength}/100")
    else:
        lines.append("  Belirgin bir direnc bolgesi bulunamadi.")

    if top_supports:
        lines.append("  Destek bolgeleri (guclulukten en yuksege):")
        for lv in top_supports:
            lines.append(f"    - {lv.price:.4f}  | {lv.touches} kez test edilmis | guc={lv.strength}/100")
    else:
        lines.append("  Belirgin bir destek bolgesi bulunamadi.")
    lines.append("")

    # ---- 4) Guncel fiyatin en yakin seviyelere gore konumu ----
    lines.append("-" * 60)
    lines.append("GUNCEL FIYATIN SEVIYELERE GORE KONUMU")
    lines.append("-" * 60)
    proximity = distance_to_nearest_level(current_price, levels)
    ns, nr = proximity["nearest_support"], proximity["nearest_resistance"]

    if ns:
        lv, dist = ns
        lines.append(f"  En yakin DESTEK : {lv.price:.4f}  (fiyatin %{dist:.2f} altinda, guc={lv.strength}/100)")
    else:
        lines.append("  Altta belirgin bir destek seviyesi yok.")

    if nr:
        lv, dist = nr
        lines.append(f"  En yakin DIRENC : {lv.price:.4f}  (fiyatin %{dist:.2f} ustunde, guc={lv.strength}/100)")
    else:
        lines.append("  Ustte belirgin bir direnc seviyesi yok.")
    lines.append("")

    # ---- 5) Nihai yorum / confluence sonucu ----
    lines.append("-" * 60)
    lines.append("NIHAI YORUM")
    lines.append("-" * 60)
    result = confluence_score(candles)
    lines.append(f"  Confluence skoru : {result.score:+.1f}  ({_describe_score(result.score)})")
    lines.append(f"    - Pattern katkisi : {result.pattern_component:+.1f}")
    lines.append(f"    - Seviye katkisi  : {result.level_component:+.1f}")
    lines.append(f"    - Trend katkisi   : {result.trend_component:+.1f}")
    lines.append(f"  Gerekce: {result.explanation}")
    lines.append("")
    lines.append("=" * 60)
    lines.append("NOT: Bu rapor bir yatirim tavsiyesi degildir, sadece mevcut")
    lines.append("chart verisinin kural-tabanli yorumudur.")
    lines.append("=" * 60)

    return "\n".join(lines)


# =============================================================================
# 8) (OPSIYONEL) TA-Lib versiyonu - kuruluysa daha zengin pattern seti icin
# =============================================================================

def detect_patterns_talib(open_: np.ndarray, high: np.ndarray,
                           low: np.ndarray, close: np.ndarray) -> Dict[str, np.ndarray]:
    """
    TA-Lib kuruluysa (pip install TA-Lib + sistem kutuphanesi gerekir)
    60+ pattern fonksiyonunu toplu calistirir. Kurulu degilse ImportError firlatir,
    o durumda yukaridaki saf-Python PatternDetector'i kullan.
    """
    try:
        import talib
    except ImportError as e:
        raise ImportError(
            "TA-Lib kurulu degil. Saf-Python PatternDetector / detect_all_patterns "
            "fonksiyonlarini kullanabilirsin (bu dosyada zaten mevcut)."
        ) from e

    pattern_names = [name for name in dir(talib) if name.startswith("CDL")]
    results = {}
    for name in pattern_names:
        func = getattr(talib, name)
        results[name] = func(open_, high, low, close)
    return results


# =============================================================================
# 8) TEST / DEMO - sentetik veriyle calisir, kendi verinle degistirmen yeterli
# =============================================================================

if __name__ == "__main__":
    # --- Daha gercekci sentetik veri: trend + tekrar test edilen seviyeler ---
    # (Kendi verinle degistirmek icin: open_, high, low, close dizilerini
    #  poly_predictor'daki OHLC cikisindan doldurman yeterli.)
    np.random.seed(7)
    n = 60
    base = np.linspace(100, 92, n)               # genel hafif dusus egilimi
    noise = np.cumsum(np.random.randn(n) * 0.6)   # gurultu
    close = base + noise
    # Bazi seviyelere fiyati bilerek defalarca yaklastiriyoruz (destek testi)
    for bounce_idx in [15, 28, 41, 55]:
        if bounce_idx < n:
            close[bounce_idx] = 95.0 + np.random.randn() * 0.1

    open_ = close + np.random.randn(n) * 0.5
    high = np.maximum(open_, close) + np.abs(np.random.randn(n)) * 0.9
    low = np.minimum(open_, close) - np.abs(np.random.randn(n)) * 0.9

    # Son muma belirgin bir hammer pattern enjekte edelim (demo amacli)
    close[-1] = open_[-1] + 0.3
    low[-1] = min(open_[-1], close[-1]) - 3.5
    high[-1] = max(open_[-1], close[-1]) + 0.2

    engine = CandleEngine(open_, high, low, close)

    report = engine.generate_report()
    print(report)
