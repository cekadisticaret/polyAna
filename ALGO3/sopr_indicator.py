"""
sopr_indicator.py
SOPR (Spent Output Profit Ratio): Satılan coin'lerin ortalama kâr/zarar oranı.
STH-SOPR (Short Term Holder) < 1.0 = kısa vadeli holder'lar zararda, dip sinyali.
"""
import os
import requests
import pandas as pd
import numpy as np
from typing import Optional, Dict
from datetime import datetime, timedelta

class SOPRIndicator:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GLASSNODE_API_KEY")
        self.base_url = "https://api.glassnode.com/v1/metrics"
        if not self.api_key:
            raise ValueError("Glassnode API key gerekli.")

    def fetch_sopr(self, asset: str = "BTC", sopr_type: str = "sth", days: int = 730) -> pd.DataFrame:
        """
        sopr_type: 'sth' (Short Term Holder), 'lth' (Long Term Holder), 'all'
        """
        endpoint_map = {
            "sth": "sopr_sth",
            "lth": "sopr_lth", 
            "all": "sopr"
        }
        metric = endpoint_map.get(sopr_type, "sopr")
        endpoint = f"{self.base_url}/indicators/{metric}"

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
        df.rename(columns={"t": "timestamp", "v": "sopr"}, inplace=True)
        df.set_index("timestamp", inplace=True)
        return df

    def generate_signal(self, df: pd.DataFrame, ma_window: int = 7) -> Dict:
        """SOPR sinyali üretir."""
        df["sopr_ma"] = df["sopr"].rolling(window=ma_window).mean()
        latest = df.iloc[-1]
        sopr = latest["sopr"]
        sopr_ma = latest["sopr_ma"]

        if pd.isna(sopr):
            return {"signal": "N/A"}

        # SOPR < 1.0 ve MA da 1.0 altında = kapitülasyon
        if sopr < 1.0 and sopr_ma < 1.0:
            signal = "CAPITULATION_BUY"
            desc = "STH-SOPR 1.0 altında. Kısa vadeli holder'lar zararda satıyor. Dip bölgesi."
        elif sopr > 1.05 and sopr_ma > 1.05:
            signal = "PROFIT_TAKING"
            desc = "SOPR 1.05 üzerinde. Kâr realizasyonu baskısı yüksek."
        else:
            signal = "NEUTRAL"
            desc = "SOPR tarafsız bölgede."

        return {
            "signal": signal,
            "sopr": round(float(sopr), 4),
            "sopr_ma": round(float(sopr_ma), 4) if not pd.isna(sopr_ma) else None,
            "description": desc,
            "timestamp": df.index[-1].strftime("%Y-%m-%d %H:%M")
        }

    def run(self, asset: str = "BTC", sopr_type: str = "sth") -> Dict:
        df = self.fetch_sopr(asset, sopr_type)
        return self.generate_signal(df)


if __name__ == "__main__":
    sopr = SOPRIndicator()
    print(sopr.run("BTC", "sth"))
