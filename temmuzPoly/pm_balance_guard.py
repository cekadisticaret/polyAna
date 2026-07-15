"""Polymarket USDC bakiye sorgusu (işlem engeli yok)."""
import os
import sys

_PM_CLOB_HOST = "https://clob.polymarket.com"


def get_usdc_balance() -> float:
    """Polymarket USDC bakiyesi. Hata durumunda 9999 döner."""
    try:
        from py_clob_client_v2 import ClobClient
        from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
        pk     = os.getenv("POLY_PRIVATE_KEY", "")
        funder = os.getenv("POLY_FUNDER", "")
        temp   = ClobClient(host=_PM_CLOB_HOST, chain_id=137, key=pk)
        creds  = temp.create_or_derive_api_key()
        client = ClobClient(
            host=_PM_CLOB_HOST, chain_id=137, key=pk,
            creds=creds, signature_type=1, funder=funder,
        )
        result = client.get_balance_allowance(
            BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        )
        return int(result.get("balance", 0)) / 1_000_000
    except Exception as e:
        print(f"[PM BALANCE] Bakiye sorgulanamadı: {e}", file=sys.stderr)
        return 9999.0


def can_open_trade(label: str, tg_send=None) -> bool:
    """Bakiye kontrolü kaldırıldı — her zaman True."""
    return True
