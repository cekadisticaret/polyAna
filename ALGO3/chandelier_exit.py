"""
chandelier_exit.py
Chandelier Exit: ATR bazlı dinamik stop-loss seviyeleri.
Long ve short pozisyonlar için ayrı exit seviyeleri hesaplar.
"""
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class ChandelierLevels:
    long_exit: float
    short_exit: float
    atr: float
    highest_high: float
    lowest_low: float

class ChandelierExit:
    def __init__(self, atr_period: int = 22, multiplier: float = 3.0):
        """
        Args:
            atr_period: ATR hesaplama periyodu (varsayılan 22)
            multiplier: ATR çarpanı (varsayılan 3.0)
        """
        self.atr_period = atr_period
        self.multiplier = multiplier

    def calculate_atr(self, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
        """Average True Range hesaplar."""
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=self.atr_period).mean()
        return atr

    def calculate(self, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.DataFrame:
        """Chandelier Exit seviyelerini hesaplar."""
        atr = self.calculate_atr(high, low, close)

        # Long exit: Son N periyodun en yükseği - (ATR * multiplier)
        highest_high = high.rolling(window=self.atr_period).max()
        long_exit = highest_high - (atr * self.multiplier)

        # Short exit: Son N periyodun en düşüğü + (ATR * multiplier)
        lowest_low = low.rolling(window=self.atr_period).min()
        short_exit = lowest_low + (atr * self.multiplier)

        df = pd.DataFrame({
            "close": close,
            "atr": atr,
            "highest_high": highest_high,
            "lowest_low": lowest_low,
            "long_exit": long_exit,
            "short_exit": short_exit
        })
        return df

    def generate_signal(self, high: pd.Series, low: pd.Series, close: pd.Series, 
                       current_position: Optional[str] = None) -> Dict:
        """
        Mevcut pozisyona göre exit sinyali üretir.

        Args:
            current_position: "LONG", "SHORT", veya None
        """
        df = self.calculate(high, low, close)
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        price = latest["close"]
        long_exit = latest["long_exit"]
        short_exit = latest["short_exit"]

        # Trend yönü belirleme (Chandelier Exit cross)
        # Fiyat long_exit üzerindeyse uptrend, altındaysa downtrend
        trend = "UP" if price > long_exit else "DOWN"

        signal = "HOLD"
        action = None

        if current_position == "LONG":
            if price < long_exit:
                signal = "EXIT_LONG"
                action = f"Long stop çalıştı. Fiyat {price:.2f}, Chandelier Exit: {long_exit:.2f}"
            else:
                action = f"Long aktif. Stop: {long_exit:.2f} ({(price/long_exit-1):.2%} mesafe)"

        elif current_position == "SHORT":
            if price > short_exit:
                signal = "EXIT_SHORT"
                action = f"Short stop çalıştı. Fiyat {price:.2f}, Chandelier Exit: {short_exit:.2f}"
            else:
                action = f"Short aktif. Stop: {short_exit:.2f} ({(short_exit/price-1):.2%} mesafe)"

        else:  # No position
            if trend == "UP":
                signal = "SETUP_LONG"
                action = f"Long setup. Giriş: {price:.2f}, Stop: {long_exit:.2f}"
            else:
                signal = "SETUP_SHORT"
                action = f"Short setup. Giriş: {price:.2f}, Stop: {short_exit:.2f}"

        return {
            "signal": signal,
            "trend": trend,
            "current_price": round(float(price), 2),
            "long_exit": round(float(long_exit), 2),
            "short_exit": round(float(short_exit), 2),
            "atr": round(float(latest["atr"]), 2),
            "action": action,
            "risk_reward_suggestion": self._suggest_risk_reward(price, long_exit, short_exit, trend)
        }

    def _suggest_risk_reward(self, price: float, long_exit: float, 
                            short_exit: float, trend: str) -> str:
        if trend == "UP":
            risk = price - long_exit
            target = price + (risk * 2)  # 1:2 R/R
            return f"Long için Risk: {risk:.2f}, Hedef: {target:.2f} (1:2 R/R)"
        else:
            risk = short_exit - price
            target = price - (risk * 2)
            return f"Short için Risk: {risk:.2f}, Hedef: {target:.2f} (1:2 R/R)"

    def run(self, high: pd.Series, low: pd.Series, close: pd.Series, 
            position: Optional[str] = None) -> Dict:
        return self.generate_signal(high, low, close, position)


if __name__ == "__main__":
    # Örnek OHLCV verisi
    np.random.seed(42)
    n = 100
    close = pd.Series(100 + np.cumsum(np.random.randn(n) * 2))
    high = close + np.abs(np.random.randn(n)) * 2
    low = close - np.abs(np.random.randn(n)) * 2

    ce = ChandelierExit(atr_period=22, multiplier=3.0)
    print(ce.run(high, low, close, position="LONG"))
