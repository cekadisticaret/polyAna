"""
Telegram Bot — getUpdates ile uzun dinleme; özel sohbetlerdeki kullanıcıları DB’ye kaydeder.

Çalıştırma (sürekli): PYTHONPATH=. .venv/bin/python -m src.telegram_listener
Cron’dan bağımsız; systemd veya screen ile arka planda tutun.
"""
import logging
import sys
import time

import requests

from src.config import Config
from src.data.telegram_subscribers import upsert_subscriber

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
POLL_TIMEOUT = 50


def _welcome_text() -> str:
    return (
        "Polymarket Analyzer bildirimlerine kayıt oldunuz. "
        "Bu sohbetten saatlik analiz mesajları alacaksınız."
    )


def run_polling_loop() -> None:
    if not Config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN tanımlı değil")
        sys.exit(1)

    token = Config.TELEGRAM_BOT_TOKEN
    base = f"{TELEGRAM_API}/bot{token}"
    offset = 0

    logger.info("Telegram getUpdates dinleniyor (Ctrl+C ile çık)…")

    while True:
        try:
            resp = requests.get(
                f"{base}/getUpdates",
                params={"timeout": POLL_TIMEOUT, "offset": offset},
                timeout=POLL_TIMEOUT + 10,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("getUpdates hata: %s", data)
                time.sleep(5)
                continue

            for upd in data.get("result", []):
                offset = upd["update_id"] + 1

                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue

                chat = msg.get("chat") or {}
                if chat.get("type") != "private":
                    continue

                text = (msg.get("text") or "").strip()
                if not text.startswith("/start"):
                    continue

                chat_id = str(chat.get("id", ""))
                if not chat_id:
                    continue

                user = msg.get("from") or {}
                username = user.get("username")
                first_name = user.get("first_name")

                is_new = upsert_subscriber(chat_id, username, first_name)
                logger.info(
                    "Abone: chat_id=%s @%s (%s) yeni=%s",
                    chat_id,
                    username or "-",
                    first_name or "-",
                    is_new,
                )

                if is_new:
                    try:
                        r = requests.post(
                            f"{base}/sendMessage",
                            json={
                                "chat_id": chat_id,
                                "text": _welcome_text(),
                                "disable_web_page_preview": True,
                            },
                            timeout=30,
                        )
                        r.raise_for_status()
                    except requests.RequestException as e:
                        logger.warning("Karşılama mesajı gönderilemedi: %s", e)

        except requests.RequestException as e:
            logger.exception("Ağ hatası: %s", e)
            time.sleep(5)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    run_polling_loop()


if __name__ == "__main__":
    main()
