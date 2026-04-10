"""
ET saat dilimine göre CLOB gerçek işlem (isteğe bağlı) yalnızca izin verilen saatlerde.

Geçmiş analiz seti: 00, 01, 07, 08, 11 ET — `TRADING_HOUR_RESTRICTION_ENABLED=True` iken geçerli.
Şu an kısıt kapalı: her ET saatinde (diğer koşullar uygunsa) emir denenebilir.
"""

# False → her saat izinli | True → yalnızca TRADING_ALLOWED_HOURS_ET içindeki saatler
TRADING_HOUR_RESTRICTION_ENABLED: bool = False

TRADING_ALLOWED_HOURS_ET: frozenset[int] = frozenset({0, 1, 7, 8, 11})


def is_trading_hour_allowed(hour: int) -> bool:
    """True ise bu ET saatinde (diğer koşullar uygunsa) gerçek CLOB emri gönderilebilir."""
    if not TRADING_HOUR_RESTRICTION_ENABLED:
        return True
    return hour in TRADING_ALLOWED_HOURS_ET
