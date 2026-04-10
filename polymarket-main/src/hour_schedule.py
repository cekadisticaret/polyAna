"""
ET saat dilimine göre CLOB gerçek işlem yalnızca izin verilen saatlerde.

Geçmiş performans analizine göre: 00, 01, 07, 08, 11 ET.
Diğer saatlerde tahmin `hourly_trades` tablosuna `trade_opened=0` ile yazılır; CLOB emri yok.
"""

TRADING_ALLOWED_HOURS_ET: frozenset[int] = frozenset({0, 1, 7, 8, 11})


def is_trading_hour_allowed(hour: int) -> bool:
    """True ise bu ET saatinde (diğer koşullar uygunsa) gerçek CLOB emri gönderilebilir."""
    return hour in TRADING_ALLOWED_HOURS_ET
