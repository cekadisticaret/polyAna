"""
Cüzdan (CLOB collateral USDC) + Data API açık pozisyonların işaretli değeri (currentValue toplamı).

- Collateral: py-clob-client get_balance_allowance (L2), balance 1e6 USDC.
- Pozisyonlar: GET https://data-api.polymarket.com/positions?user=0x...
  (Polymarket Data API — docs: Get current positions for a user)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from src.config import Config
from src.trading.clob_orders import build_clob_client, funder_address

logger = logging.getLogger(__name__)

DATA_API_BASE = "https://data-api.polymarket.com"


def _usdc_from_balance_allowance(resp: Any) -> Optional[float]:
    if not isinstance(resp, dict):
        return None
    bal = resp.get("balance")
    if bal is None:
        return None
    try:
        return int(str(bal)) / 1_000_000.0
    except (TypeError, ValueError):
        return None


def fetch_collateral_usdc() -> Optional[float]:
    """CLOB’da kullanılabilir USDC (collateral). Anahtar yoksa None."""
    if not (Config.POLYMARKET_PRIVATE_KEY or "").strip():
        return None
    try:
        from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

        client = build_clob_client()
        params = BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=-1,
        )
        resp = client.get_balance_allowance(params)
        out = _usdc_from_balance_allowance(resp)
        if out is None:
            logger.warning("Collateral yanıtı beklenen formatta değil: %s", resp)
        return out
    except Exception as e:
        logger.warning("Collateral bakiye okunamadı: %s", e)
        return None


def fetch_positions_mark_value_and_count() -> tuple[Optional[float], Optional[int]]:
    """
    Data API: açık pozisyonların currentValue toplamı ve pozisyon sayısı (currentValue > 0).
    Funder adresi .env’den; anahtar yoksa (None, None).
    """
    try:
        addr = funder_address()
    except ValueError:
        return None, None
    addr = addr.strip()
    if not addr.startswith("0x"):
        addr = "0x" + addr
    try:
        r = requests.get(
            f"{DATA_API_BASE.rstrip('/')}/positions",
            params={
                "user": addr,
                "limit": 500,
                "sizeThreshold": 0,
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        logger.warning("Data API positions hatası: %s", e)
        return None, None
    if not isinstance(data, list):
        return None, None
    total = 0.0
    n_open = 0
    for p in data:
        if not isinstance(p, dict):
            continue
        cv = p.get("currentValue")
        if cv is None:
            continue
        try:
            v = float(cv)
        except (TypeError, ValueError):
            continue
        total += v
        if v > 0:
            n_open += 1
    return total, n_open


def fetch_positions_mark_value_total() -> Optional[float]:
    """Geriye dönük uyumluluk — yalnızca toplam değer."""
    t, _ = fetch_positions_mark_value_and_count()
    return t


def portfolio_snapshot_values() -> dict[str, Any]:
    """
    Gün özeti + DB snapshot için tek tur: cüzdan USDC, açık pozisyon değeri, adet, toplam.
    """
    col = fetch_collateral_usdc()
    pos, npos = fetch_positions_mark_value_and_count()
    total: Optional[float] = None
    if col is not None and pos is not None:
        total = col + pos
    elif col is not None:
        total = col
    elif pos is not None:
        total = pos
    return {
        "collateral_usdc": col,
        "positions_mark_usdc": pos,
        "open_positions_count": npos,
        "portfolio_total_usdc": total,
    }


def portfolio_summary_lines_from_values(v: dict[str, Any]) -> list[str]:
    """Önceden okunmuş snapshot sözlüğü ile Telegram satırları."""
    col = v.get("collateral_usdc")
    pos = v.get("positions_mark_usdc")
    if col is None and pos is None:
        return []
    lines: list[str] = []
    if col is not None:
        lines.append(f"Kullanılabilir USDC: {col:.2f}")
    else:
        lines.append("Kullanılabilir USDC: —")
    if pos is not None:
        lines.append(f"Açık hisse değeri: {pos:.2f}")
    else:
        lines.append("Açık hisse değeri: —")
    if col is not None and pos is not None:
        lines.append(f"Toplam: {col + pos:.2f}")
    return lines


def portfolio_summary_lines() -> list[str]:
    """
    Gün özeti altına eklenecek satırlar. Veri yoksa boş liste.
    """
    return portfolio_summary_lines_from_values(portfolio_snapshot_values())
