"""
Telegram bildirimleri — kayıtlı abonelere (DB) ve isteğe bağlı TELEGRAM_CHAT_ID’ye gönderim.
"""
import logging
from typing import Optional

import requests

from src.config import Config
from src.data.telegram_subscribers import init_telegram_subscribers_table, recipient_chat_ids

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 4096


def _send_one(chat_id: str, text: str) -> bool:
    url = f"{TELEGRAM_API}/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.error("Telegram gönderim hatası (chat_id=%s): %s", chat_id, e)
        if hasattr(e, "response") and e.response is not None:
            try:
                err_body = e.response.json()
                logger.debug("Telegram API yanıtı: %s", err_body)
            except Exception:
                pass
        return False


def send_telegram(message: str, chat_id: Optional[str] = None) -> bool:
    """
    Telegram Bot API ile mesaj gönder.
    chat_id verilirse yalnızca o chat; verilmezse DB’deki aboneler + .env TELEGRAM_CHAT_ID.
    """
    if not Config.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN tanımlı değil")
        return False

    text = message[:MAX_MESSAGE_LENGTH] if len(message) > MAX_MESSAGE_LENGTH else message

    if chat_id:
        targets = [chat_id]
    else:
        init_telegram_subscribers_table()
        targets = recipient_chat_ids()
        if not targets:
            logger.warning(
                "Alıcı yok: Telegram’da bota yazın veya TELEGRAM_CHAT_ID tanımlayın; "
                "listener için: python -m src.telegram_listener"
            )
            return False

    ok_any = False
    for target in targets:
        if _send_one(target, text):
            ok_any = True
    if ok_any:
        logger.info("Telegram mesajı gönderildi (%s alıcı)", len(targets))
    return ok_any
