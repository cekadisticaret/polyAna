"""
Telegram — bota yazan /start atan kullanıcıların chat_id kaydı (SQLite).
"""
import logging
from datetime import datetime, timezone
from src.data.hourly_trades import get_connection

logger = logging.getLogger(__name__)


def init_telegram_subscribers_table() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_subscribers (
                chat_id TEXT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def upsert_subscriber(
    chat_id: str,
    username: str | None,
    first_name: str | None,
) -> bool:
    """Yeni kayıt veya last_seen güncelleme. True = yeni satır eklendi."""
    init_telegram_subscribers_table()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    is_new = False
    try:
        row = conn.execute(
            "SELECT chat_id FROM telegram_subscribers WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO telegram_subscribers (chat_id, username, first_name, created_at, last_seen)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, username or "", first_name or "", now, now),
            )
            is_new = True
        else:
            conn.execute(
                """
                UPDATE telegram_subscribers
                SET username = ?, first_name = ?, last_seen = ?
                WHERE chat_id = ?
                """,
                (username or "", first_name or "", now, chat_id),
            )
        conn.commit()
    finally:
        conn.close()
    return is_new


def all_chat_ids() -> list[str]:
    init_telegram_subscribers_table()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT chat_id FROM telegram_subscribers ORDER BY created_at"
        ).fetchall()
        return [str(r["chat_id"]) for r in rows]
    finally:
        conn.close()


def recipient_chat_ids(extra: str | None = None) -> list[str]:
    """
    Bildirim alıcıları: DB’deki tüm aboneler + .env TELEGRAM_CHAT_ID
    (virgülle birden fazla ID, tekrarsız).
    """
    from src.config import Config

    ids: list[str] = list(all_chat_ids())
    seen = set(ids)
    raw = (extra or Config.TELEGRAM_CHAT_ID or "").strip()
    for part in raw.split(","):
        manual = part.strip()
        if manual and manual not in seen:
            ids.append(manual)
            seen.add(manual)
    return ids
