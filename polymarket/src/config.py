"""
Güvenli konfigürasyon yönetimi.
Tüm hassas anahtarlar ortam değişkenlerinden okunur, kod içinde saklanmaz.
"""
import os

try:
    from dotenv import load_dotenv
    from pathlib import Path

    _pkg = Path(__file__).resolve().parent.parent  # polymarket/
    _repo = _pkg.parent  # aiProject kökü
    if (_repo / ".env").is_file():
        load_dotenv(_repo / ".env")
    if (_pkg / ".env").is_file():
        load_dotenv(_pkg / ".env", override=True)
except ImportError:
    pass  # python-dotenv yoksa sadece os.environ kullan


class Config:
    """Ortam değişkenlerinden güvenli config yükleme."""

    # Polymarket — otomatik emir ana anahtarı (false iken tahmin/bildirim devam, emir yok)
    POLYMARKET_BOT_ENABLED = os.getenv("POLYMARKET_BOT_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )

    # Polymarket — CLOB gerçek işlem (POLYMARKET_PRIVATE_KEY + USDC.e + POL gerekir)
    POLYMARKET_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "") or os.getenv("POLY_PRIVATE_KEY", "")
    POLYMARKET_CHAIN_ID = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))  # Polygon mainnet
    POLYMARKET_FUNDER = (
        os.getenv("POLYMARKET_FUNDER", "").strip() or os.getenv("POLY_FUNDER", "").strip()
    )  # Boşsa private key adresi
    POLYMARKET_SIGNATURE_TYPE = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0"))  # 0=EOA
    # Saatlik emir hedef nominali (USDC) — tek kaynak: .env
    POLYMARKET_ORDER_USDC = max(
        0.01,
        float(os.getenv("POLYMARKET_ORDER_USDC") or os.getenv("POLY_BET_SIZE") or "5"),
    )
    POLYMARKET_TRADING_ENABLED = os.getenv("POLYMARKET_TRADING_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )

    # Polymarket Gamma (okuma)
    GAMMA_API_BASE = "https://gamma-api.polymarket.com"

    # Telegram (bildirimler)
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    # İsteğe bağlı: sabit alıcı(lar), virgülle ayrılmış; DB aboneleriyle birleşir
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    @classmethod
    def validate(cls) -> list[str]:
        """Eksik/geçersiz config'leri raporla."""
        issues = []
        if not cls.TELEGRAM_BOT_TOKEN:
            issues.append("TELEGRAM_BOT_TOKEN .env'de tanımlanmalı")
        return issues
