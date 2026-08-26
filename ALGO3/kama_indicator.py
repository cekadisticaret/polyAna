"""
kama_indicator.py
Kaufman Adaptive Moving Average (KAMA): Volatiliteye göre hızını ayarlayan akıllı MA.
Düşük volatilitede hızlı, yüksek volatilitede yavaş tepki verir.
"""
import pandas as pd
import numpy as np
from typing import Dict, Union

class KAMAIndicator:
    def __init__(self, n: int = 10, fast_ema: int = 2, slow_ema: int = 30):
        """
        Args:
            n: Efficiency Ratio periyodu
            fast_ema: Hızlı EMA sabiti
            slow_ema: Yavaş EMA sabiti
        """
        self.n = n
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema

    def calculate(self, prices: pd.Series) -> pd.Series:
        """KAMA hesaplar."""
        # 1. Change (Net price movement over n periods)
        change = (prices - prices.shift(self.n)).abs()

        # 2. Volatility (Sum of absolute price changes)
        volatility = prices.diff().abs().rolling(window=self.n).sum()

        # 3. Efficiency Ratio (ER)
        er = change / volatility
        er = er.fillna(0)

        # 4. Smoothing Constants
        fastest = 2 / (self.fast_ema + 1)
        slowest = 2 / (self.slow_ema + 1)

        sc = (er * (fastest - slowest) + slowest) ** 2

        # 5. KAMA calculation
        kama = pd.Series(index=prices.index, dtype=float)
        kama.iloc[:self.n] = prices.iloc[:self.n]

        for i in range(self.n, len(prices)):
            kama.iloc[i] = kama.iloc[i-1] + sc.iloc[i] * (prices.iloc[i] - kama.iloc[i-1])

        return kama

    def generate_signal(self, prices: pd.Series) -> Dict:
        """KAMA sinyali üretir."""
        kama = self.calculate(prices)

        # KAMA eğimi
        kama_slope = kama.diff()

        # Fiyat KAMA'ya göre pozisyon
        price_vs_kama = prices.iloc[-1] / kama.iloc[-1] - 1

        latest_slope = kama_slope.iloc[-1]

        if price_vs_kama > 0.02 and latest_slope > 0:
            signal = "STRONG_BUY"
            desc = "Fiyat KAMA üzerinde ve eğim pozitif. Trend güçlü."
        elif price_vs_kama > 0 and latest_slope > 0:
            signal = "BUY"
            desc = "Fiyat KAMA üzerinde, yükseliş trendi."
        elif price_vs_kama < -0.02 and latest_slope < 0:
            signal = "STRONG_SELL"
            desc = "Fiyat KAMA altında ve eğim negatif. Düşüş trendi güçlü."
        elif price_vs_kama < 0 and latest_slope < 0:
            signal = "SELL"
            desc = "Fiyat KAMA altında, düşüş trendi."
        else:
            signal = "NEUTRAL"
            desc = "KAMA tarafsız bölgede."

        return {
            "signal": signal,
            "kama": round(float(kama.iloc[-1]), 2),
            "price": round(float(prices.iloc[-1]), 2),
            "price_vs_kama": f"{price_vs_kama:.2%}",
            "kama_slope": round(float(latest_slope), 4) if not pd.isna(latest_slope) else None,
            "description": desc
        }

    def run(self, prices: pd.Series) -> Dict:
        return self.generate_signal(prices)


if __name__ == "__main__":
    # Örnek veri
    np.random.seed(42)
    prices = pd.Series(100 + np.cumsum(np.random.randn(200) * 2))

    kama = KAMAIndicator(n=10)
    print(kama.run(prices))
