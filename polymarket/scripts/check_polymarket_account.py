#!/usr/bin/env python3
"""
Polymarket CLOB hesap teyidi: .env ile botun kullandığı imzalayıcı ve funder adresleri
ve CLOB üzerinden collateral (USDC) bakiye/allowance özeti.

Çalıştırma (proje kökünden):
  PYTHONPATH=. .venv/bin/python scripts/check_polymarket_account.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eth_account import Account
from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

from src.config import Config
from src.trading.clob_orders import build_clob_client, funder_address, _normalize_key


def main() -> None:
    pk = _normalize_key(Config.POLYMARKET_PRIVATE_KEY)
    if not pk:
        print("POLYMARKET_PRIVATE_KEY .env'de yok veya boş.")
        sys.exit(1)

    signer_addr = Account.from_key("0x" + pk).address
    fund = funder_address()

    print("--- Bot ile aynı .env (adresler) ---")
    print(f"İmzalayan (private key adresi): {signer_addr}")
    print(f"Funder (bakiye/emir bu adrese bağlı): {fund}")
    print(f"CHAIN_ID: {Config.POLYMARKET_CHAIN_ID}")
    print(f"POLYMARKET_SIGNATURE_TYPE: {Config.POLYMARKET_SIGNATURE_TYPE}")
    if Config.POLYMARKET_FUNDER:
        print(f"POLYMARKET_FUNDER: {Config.POLYMARKET_FUNDER}")
    else:
        print("POLYMARKET_FUNDER: (boş → funder = imzalayan adresi)")

    print()
    print("--- CLOB API: collateral bakiye / allowance ---")
    try:
        client = build_clob_client()
        params = BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=-1,
        )
        bal = client.get_balance_allowance(params)
        if isinstance(bal, (dict, list)):
            print(json.dumps(bal, indent=2, ensure_ascii=False))
        else:
            print(bal)
    except Exception as e:
        print(f"Hata: {e}")
        sys.exit(1)

    print()
    print("--- Elle teyit ---")
    print("1) Polymarket arayüzünde bağlı gördüğünüz adres = 'Funder' ile birebir aynı mı?")
    print("2) polygonscan.com → Funder adresi → USDC.e token bakiyesi (Polygon).")
    print("3) Farklıysa: POLYMARKET_FUNDER + POLYMARKET_SIGNATURE_TYPE (proxy hesap) dokümana göre ayarlayın.")


if __name__ == "__main__":
    main()
