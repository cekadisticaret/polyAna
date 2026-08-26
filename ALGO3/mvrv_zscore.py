"""
mvrv_zscore.py
MVRV Z-Score: Market Value to Realized Value with statistical normalization.
Tarihsel olarak MVRV > 3.5 zirve, < 0 dip bölgeleri ile korelasyon gösterir.
"""
import os
import requests
import pandas as pd
import numpy as np
from typing import Optional, Dict
from datetime import datetime, timedelta

class MVRVZScore:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GLASSNODE_API_KEY")
        self.base_url = "https://api.glassnode.com/v1/metrics"
        if not self.api_key:
            raise ValueError("Glassnode API key gerekli. GLASSNODE_API_KEY env variable'ını ayarlayın.")

    def fetch_mvrv(self, asset: str = "BTC", days: int = 1825) -> pd.DataFrame:
        """Glassnode'dan MVRV verisi çeker."""
        endpoint = f"{self.base_url}/market/mvrv"
        params = {
            "a": asset,
            "api_key": self.api_key,
            "s": int((datetime.now() - timedelta(days=days)).timestamp()),
            "i": "24h"
        }
        resp = requests.get(endpoint, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        df["t"] = pd.to_datetime(df["t"], unit="s")
        df.rename(columns={"t": "timestamp", "v": "mvrv"}, inplace=True)
        df.set_index("timestamp", inplace=True)
        return df

    def calculate_zscore(self, df: pd.DataFrame, lookback: int = 365) -> pd.DataFrame:
        """Rolling Z-Score hesaplar."""
        df["mvrv_mean"] = df["mvrv"].rolling(window=lookback).mean()
        df["mvrv_std"] = df["mvrv"].rolling(window=lookback).std()
        df["zscore"] = (df["mvrv"] - df["mvrv_mean"]) / df["mvrv_std"]
        return df

    def generate_signal(self, df: pd.DataFrame) -> Dict:
        """Son değere göre sinyal üretir."""
        latest = df.iloc[-1]
        z = latest["zscore"]
        mvrv = latest["mvrv"]

        if pd.isna(z):
            return {"signal": "N/A", "reason": "Yetersiz veri"}

        if z > 3.5 or mvrv > 3.5:
            signal = "EXTREME_RISK"
            desc = "MVRV tarihsel zirve bölgesinde. Büyük düzeltme riski yüksek."
        elif z > 1.5:
            signal = "OVERVALUED"
            desc = "Piyasa değerleme yüksek. Dikkatli olumlu."
        elif z < -1.0 or mvrv < 1.0:
            signal = "ACCUMULATION"
            desc = "MVRV dip bölgesi / kapitülasyon. Uzun vadeli birikim fırsatı."
        else:
            signal = "NEUTRAL"
            desc = "Değerleme tarafsız bölgede."

        return {
            "signal": signal,
            "mvrv": round(float(mvrv), 3),
            "zscore": round(float(z), 3),
            "description": desc,
            "timestamp": df.index[-1].strftime("%Y-%m-%d %H:%M")
        }

    def run(self, asset: str = "BTC") -> Dict:
        df = self.fetch_mvrv(asset)
        df = self.calculate_zscore(df)
        return self.generate_signal(df)


if __name__ == "__main__":
    mvrv = MVRVZScore()
    result = mvrv.run("BTC")
    print(result)
