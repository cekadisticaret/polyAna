"""
oi_liquidation_analyzer.py
Açık Pozisyon (OI), Funding Rate ve Likidasyon Analizi.
Kaldıraç yapısını ölçer, squeeze riskini tespit eder.
"""
import os
import requests
import pandas as pd
import numpy as np
from typing import Dict, Optional, List
from datetime import datetime

class OILiquidationAnalyzer:
    def __init__(self, coinglass_api_key: Optional[str] = None):
        self.api_key = coinglass_api_key or os.getenv("COINGLASS_API_KEY")
        self.base_url = "https://open-api.coinglass.com/public/v2"
        self.headers = {"coinglassSecret": self.api_key} if self.api_key else {}

    def fetch_oi_funding_longshort(self, symbol: str = "BTC") -> Optional[Dict]:
        """Coinglass'tan OI, Funding ve Long/Short ratio çeker."""
        try:
            # Open Interest
            oi_url = f"{self.base_url}/open_interest"
            params = {"symbol": symbol, "time_type": "h24"}
            resp = requests.get(oi_url, headers=self.headers, params=params, timeout=15)
            oi_data = resp.json() if resp.status_code == 200 else {}

            # Funding Rate
            funding_url = f"{self.base_url}/funding"
            resp2 = requests.get(funding_url, headers=self.headers, params=params, timeout=15)
            funding_data = resp2.json() if resp2.status_code == 200 else {}

            # Long/Short Ratio
            ls_url = f"{self.base_url}/long_short"
            resp3 = requests.get(ls_url, headers=self.headers, params=params, timeout=15)
            ls_data = resp3.json() if resp3.status_code == 200 else {}

            return {
                "oi": oi_data,
                "funding": funding_data,
                "long_short": ls_data
            }
        except Exception as e:
            print(f"Veri çekme hatası: {e}")
            return None

    def analyze_sentiment(self, data: Dict) -> Dict:
        """OI, funding ve long/short verisinden sinyal üretir."""
        if not data:
            return {"signal": "NO_DATA"}

        # Basit parsing (Coinglass API response yapısına göre ayarlanmalı)
        # Gerçek API response'una göre bu kısım güncellenmeli

        # Mock değerler - gerçek entegrasyonda API response'dan çekilmeli
        funding_rate = 0.0001  # %0.01
        long_ratio = 0.65
        oi_change = 0.05  # %5 artış

        signals = []

        # Funding analizi
        if funding_rate > 0.0001:  # %0.01 üzeri
            signals.append("HIGH_FUNDING")
        elif funding_rate < -0.0001:
            signals.append("NEGATIVE_FUNDING")

        # Long/Short analizi
        if long_ratio > 0.70:
            signals.append("EXTREME_LONG_BIAS")
        elif long_ratio < 0.30:
            signals.append("EXTREME_SHORT_BIAS")

        # OI analizi
        if oi_change > 0.10:
            signals.append("OI_SURGE")

        # Squeeze riski değerlendirmesi
        if "EXTREME_LONG_BIAS" in signals and "HIGH_FUNDING" in signals:
            signal = "SHORT_SQUEEZE_RISK"
            desc = "Long'lar aşırı kalabalık ve funding yüksek. Short squeeze riski yüksek."
        elif "EXTREME_SHORT_BIAS" in signals and "NEGATIVE_FUNDING" in signals:
            signal = "LONG_SQUEEZE_RISK"
            desc = "Short'lar aşırı kalabalık. Long squeeze riski var."
        elif "OI_SURGE" in signals and "HIGH_FUNDING" in signals:
            signal = "LEVERAGE_BUILDUP"
            desc = "Yüksek kaldıraç birikimi. Düşüşte cascade likidasyon riski."
        else:
            signal = "NEUTRAL"
            desc = "Kaldıraç yapısı dengeli."

        return {
            "signal": signal,
            "description": desc,
            "funding_rate": f"{funding_rate:.4%}",
            "long_ratio": f"{long_ratio:.1%}",
            "oi_change": f"{oi_change:.1%}",
            "raw_signals": signals
        }

    def liquidation_heatmap_zones(self, symbol: str = "BTC") -> Dict:
        """
        Likidasyon yoğunluk bölgelerini tespit eder.
        Gerçek uygulamada Coinglass liquidation heatmap API'si kullanılmalı.
        """
        # Bu fonksiyon mock data ile çalışır
        # Gerçek entegrasyon için Coinglass Liquidation Heatmap API gerekir
        current_price = 65000  # Mock

        # Tipik likidasyon cluster'ları (fiyatın üstünde short, altında long likidasyonları)
        zones = {
            "short_liquidation_cluster": [current_price * 1.05, current_price * 1.10],
            "long_liquidation_cluster": [current_price * 0.95, current_price * 0.90],
            "max_leverage_zone": f"{current_price * 0.92:.0f} - {current_price * 1.08:.0f}"
        }

        return {
            "current_price": current_price,
            "liquidation_zones": zones,
            "note": "Gerçek uygulamada Coinglass API'den heatmap verisi çekilmeli"
        }

    def run(self, symbol: str = "BTC") -> Dict:
        data = self.fetch_oi_funding_longshort(symbol)
        sentiment = self.analyze_sentiment(data)
        heatmap = self.liquidation_heatmap_zones(symbol)
        return {
            "symbol": symbol,
            "sentiment": sentiment,
            "liquidation_map": heatmap,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }


if __name__ == "__main__":
    analyzer = OILiquidationAnalyzer()
    print(analyzer.run("BTC"))
