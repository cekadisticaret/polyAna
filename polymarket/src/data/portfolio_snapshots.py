"""
Gün özeti (resolve) anında cüzdan + açık pozisyon + portföy toplamı — tarih/saat ET.
"""
import logging
import sqlite3
from typing import Optional

from src.data.hourly_trades import get_connection

logger = logging.getLogger(__name__)


def init_portfolio_snapshots_table() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at_utc TEXT NOT NULL,
                captured_at_et TEXT NOT NULL,
                cycle_slot_et TEXT NOT NULL,
                trade_date_et TEXT,
                collateral_usdc REAL,
                positions_mark_usdc REAL,
                open_positions_count INTEGER,
                portfolio_total_usdc REAL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_ts "
            "ON portfolio_snapshots(recorded_at_utc)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_et "
            "ON portfolio_snapshots(captured_at_et)"
        )
        conn.commit()
    finally:
        conn.close()


def insert_portfolio_snapshot(
    *,
    recorded_at_utc: str,
    captured_at_et: str,
    cycle_slot_et: str,
    trade_date_et: str,
    collateral_usdc: Optional[float],
    positions_mark_usdc: Optional[float],
    open_positions_count: Optional[int],
    portfolio_total_usdc: Optional[float],
) -> None:
    init_portfolio_snapshots_table()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO portfolio_snapshots (
                recorded_at_utc, captured_at_et, cycle_slot_et, trade_date_et,
                collateral_usdc, positions_mark_usdc, open_positions_count,
                portfolio_total_usdc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recorded_at_utc,
                captured_at_et,
                cycle_slot_et,
                trade_date_et,
                collateral_usdc,
                positions_mark_usdc,
                open_positions_count,
                portfolio_total_usdc,
            ),
        )
        conn.commit()
    except Exception as e:
        logger.exception("portfolio_snapshots insert: %s", e)
    finally:
        conn.close()
