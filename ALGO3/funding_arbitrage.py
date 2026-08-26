"""
funding_arbitrage.py
Spot-Perp Cash & Carry Arbitrage: Spot al, perp sat, funding rate'i topla.
Cross-exchange funding farklarını da izler.
"""
import os
import ccxt
import pandas as pd
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class ArbitrageOpportunity:
    exchange: str
    symbol: str
    funding_rate: float
    spot_price: float
    perp_price: float
    basis: float
    est_apr: float
    action: str

class FundingArbitrage:
    def __init__(self):
        # API key'ler opsiyonel - public data için gerekmez
        self.exchanges = {
            "binance": ccxt.binance({"enableRateLimit": True}),
            "bybit": ccxt.bybit({"enableRateLimit": True}),
            "okx": ccxt.okx({"enableRateLimit": True}),
        }
        self.min_apr_threshold = 0.08  # %8 APR altındakileri görmezden gel

    def fetch_funding_and_prices(self, exchange_name: str, symbol: str = "BTC/USDT") -> Optional[Dict]:
        """Bir borsadan funding rate, spot ve perp fiyat çeker."""
        try:
            ex = self.exchanges[exchange_name]

            # Funding rate (perp)
            perp_symbol = symbol.replace("/", "")
            if exchange_name == "binance":
                perp_symbol += "_PERP"  # Binance futures sembol formatı

            # Perp funding rate
            funding = ex.fetchFundingRate(symbol)
            funding_rate = funding.get("fundingRate", 0) if funding else 0

            # Spot fiyat
            spot_ticker = ex.fetch_ticker(symbol)
            spot_price = spot_ticker["last"]

            # Perp fiyat (futures ticker)
            perp_ticker = ex.fetch_ticker(symbol, params={"type": "swap"})
            perp_price = perp_ticker["last"]

            basis = (perp_price - spot_price) / spot_price

            # Funding 8 saatte bir, yıllıklandırma: rate * 3 * 365
            est_apr = funding_rate * 3 * 365

            return {
                "exchange": exchange_name,
                "symbol": symbol,
                "funding_rate": funding_rate,
                "spot_price": spot_price,
                "perp_price": perp_price,
                "basis": basis,
                "est_apr": est_apr
            }
        except Exception as e:
            print(f"{exchange_name} veri çekme hatası: {e}")
            return None

    def scan_opportunities(self, symbol: str = "BTC/USDT") -> List[ArbitrageOpportunity]:
        """Tüm borsalarda funding arbitrage fırsatlarını tarar."""
        opportunities = []

        for ex_name in self.exchanges:
            data = self.fetch_funding_and_prices(ex_name, symbol)
            if not data:
                continue

            # Cash & Carry: Spot al, perp sat (funding pozitifse)
            if data["funding_rate"] > 0 and data["est_apr"] >= self.min_apr_threshold:
                opp = ArbitrageOpportunity(
                    exchange=ex_name,
                    symbol=symbol,
                    funding_rate=data["funding_rate"],
                    spot_price=data["spot_price"],
                    perp_price=data["perp_price"],
                    basis=data["basis"],
                    est_apr=data["est_apr"],
                    action="BUY_SPOT_SELL_PERP"
                )
                opportunities.append(opp)

            # Tersi: funding negatifse perp al, spot sat
            elif data["funding_rate"] < 0 and abs(data["est_apr"]) >= self.min_apr_threshold:
                opp = ArbitrageOpportunity(
                    exchange=ex_name,
                    symbol=symbol,
                    funding_rate=data["funding_rate"],
                    spot_price=data["spot_price"],
                    perp_price=data["perp_price"],
                    basis=data["basis"],
                    est_apr=abs(data["est_apr"]),
                    action="BUY_PERP_SELL_SPOT"
                )
                opportunities.append(opp)

        # Cross-exchange funding farkı
        cross_opps = self._check_cross_exchange(symbol)
        opportunities.extend(cross_opps)

        return sorted(opportunities, key=lambda x: x.est_apr, reverse=True)

    def _check_cross_exchange(self, symbol: str) -> List[ArbitrageOpportunity]:
        """Borsalar arası funding farkı kontrolü."""
        opps = []
        rates = {}

        for ex_name in self.exchanges:
            data = self.fetch_funding_and_prices(ex_name, symbol)
            if data:
                rates[ex_name] = data

        # En yüksek ve en düşük funding arasındaki fark
        if len(rates) >= 2:
            sorted_rates = sorted(rates.items(), key=lambda x: x[1]["funding_rate"])
            low_ex, low_data = sorted_rates[0]
            high_ex, high_data = sorted_rates[-1]

            diff = high_data["funding_rate"] - low_data["funding_rate"]
            if diff > 0.0001:  # %0.01'den büyük fark
                opp = ArbitrageOpportunity(
                    exchange=f"{low_ex}->{high_ex}",
                    symbol=symbol,
                    funding_rate=diff,
                    spot_price=low_data["spot_price"],
                    perp_price=high_data["perp_price"],
                    basis=high_data["basis"] - low_data["basis"],
                    est_apr=diff * 3 * 365,
                    action=f"SHORT_{high_ex}_LONG_{low_ex}"
                )
                opps.append(opp)

        return opps

    def run(self, symbol: str = "BTC/USDT") -> Dict:
        opps = self.scan_opportunities(symbol)
        return {
            "symbol": symbol,
            "opportunities_count": len(opps),
            "best_opportunity": {
                "exchange": opps[0].exchange,
                "est_apr": f"{opps[0].est_apr:.2%}",
                "action": opps[0].action,
                "funding_rate": f"{opps[0].funding_rate:.4%}"
            } if opps else None,
            "all_opportunities": [
                {
                    "exchange": o.exchange,
                    "est_apr": f"{o.est_apr:.2%}",
                    "action": o.action,
                    "basis": f"{o.basis:.4%}"
                } for o in opps
            ]
        }


if __name__ == "__main__":
    arb = FundingArbitrage()
    print(arb.run("BTC/USDT"))
