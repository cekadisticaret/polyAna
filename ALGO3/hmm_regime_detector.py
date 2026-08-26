"""
hmm_regime_detector.py
Hidden Markov Model ile 3-Regime Tespiti: Trend / Range / Volatil
Kalman filter mantığıyla birleştirilebilir.
"""
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from typing import Dict, Tuple, Optional
import warnings
warnings.filterwarnings("ignore")

class HMMRegimeDetector:
    def __init__(self, n_regimes: int = 3, lookback: int = 90):
        self.n_regimes = n_regimes
        self.lookback = lookback
        self.model = GaussianHMM(
            n_components=n_regimes,
            covariance_type="full",
            n_iter=100,
            random_state=42
        )
        self.regime_labels = {0: "UNKNOWN", 1: "UNKNOWN", 2: "UNKNOWN"}

    def prepare_features(self, prices: pd.Series) -> pd.DataFrame:
        """HMM için feature seti hazırlar: returns, volatility, log_range."""
        df = pd.DataFrame({"price": prices})
        df["returns"] = df["price"].pct_change()
        df["volatility"] = df["returns"].rolling(window=20).std()
        df["log_range"] = np.log(df["price"] / df["price"].shift(1)).abs()
        df = df.dropna()
        return df

    def fit(self, prices: pd.Series) -> "HMMRegimeDetector":
        """Modeli eğitir ve regime'leri etiketler."""
        df = self.prepare_features(prices)
        features = df[["returns", "volatility", "log_range"]].values

        self.model.fit(features)
        hidden_states = self.model.predict(features)
        df["regime"] = hidden_states

        # Regime'leri istatistiklerine göre etiketle
        stats = df.groupby("regime").agg({
            "returns": "mean",
            "volatility": "mean"
        })

        # En yüksek return = Bull/Trend, en düşük vol = Range, en yüksek vol = Volatile
        sorted_by_return = stats.sort_values("returns", ascending=False)
        sorted_by_vol = stats.sort_values("volatility", ascending=False)

        trend_regime = sorted_by_return.index[0]
        vol_regime = sorted_by_vol.index[-1]  # En yüksek vol

        # Range = ortada kalan
        remaining = [i for i in range(self.n_regimes) if i not in [trend_regime, vol_regime]]
        range_regime = remaining[0] if remaining else sorted_by_vol.index[0]

        self.regime_labels = {
            trend_regime: "TREND",
            range_regime: "RANGE", 
            vol_regime: "VOLATILE"
        }
        self.df_fitted = df
        return self

    def predict_current_regime(self, prices: pd.Series) -> Dict:
        """Son fiyatlara göre mevcut rejimi tahmin eder."""
        if not hasattr(self, "df_fitted"):
            self.fit(prices)

        latest_regime = int(self.df_fitted["regime"].iloc[-1])
        regime_name = self.regime_labels.get(latest_regime, "UNKNOWN")

        # Regime geçiş olasılıkları (transition matrix)
        trans_mat = self.model.transmat_

        return {
            "current_regime": regime_name,
            "regime_id": latest_regime,
            "regime_stats": {
                "mean_return": f"{self.df_fitted.groupby('regime')['returns'].mean().iloc[latest_regime]:.4%}",
                "mean_volatility": f"{self.df_fitted.groupby('regime')['volatility'].mean().iloc[latest_regime]:.4%}"
            },
            "regime_probability": self.model.predict_proba(
                self.df_fitted[["returns", "volatility", "log_range"]].values
            )[-1].tolist(),
            "recommendation": self._get_recommendation(regime_name)
        }

    def _get_recommendation(self, regime: str) -> str:
        rec = {
            "TREND": "Trend takip stratejileri aktif. KAMA/EMA crossover kullan. Stop mesafesini genişlet.",
            "RANGE": "Ortalama dönüş (mean reversion) stratejileri. RSI/Bollinger Bands kullan.",
            "VOLATILE": "Pozisyon büyüklüğünü %50 azalt. Chandelier Exit ile sıkı stop."
        }
        return rec.get(regime, "Bilinmeyen rejim.")

    def run(self, prices: pd.Series) -> Dict:
        self.fit(prices)
        return self.predict_current_regime(prices)


if __name__ == "__main__":
    # Örnek: rastgele walk verisi (gerçekte OHLCV verisi kullanılmalı)
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.02, 500)
    prices = pd.Series(100 * np.exp(np.cumsum(returns)))

    hmm = HMMRegimeDetector()
    print(hmm.run(prices))
