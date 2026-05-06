"""
Saatlik pipeline karar geçmişi — trades.db içinde pipeline_cycle_log tablosu.
İşlem açılmadığında nedenini skip_reason_code / skip_reason_detail ile izler.
"""
import logging
import sqlite3
from typing import Any

from src.data.hourly_trades import get_connection

logger = logging.getLogger(__name__)


def init_pipeline_cycle_log_table() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_cycle_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                cycle_slot_et TEXT NOT NULL,
                trade_date_et TEXT NOT NULL,
                et_clock_label TEXT NOT NULL,
                coin TEXT NOT NULL,
                slug TEXT NOT NULL,
                market_found INTEGER NOT NULL DEFAULT 0,
                pred_direction TEXT,
                pred_confidence TEXT,
                pred_probability REAL,
                pred_reasoning_snippet TEXT,
                direction_up_down TEXT,
                gate_yuksek_confidence INTEGER,
                gate_trading_configured INTEGER,
                outcome TEXT NOT NULL,
                skip_reason_code TEXT,
                skip_reason_detail TEXT,
                order_id TEXT,
                order_response TEXT,
                error_detail TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pipeline_cycle_log_created "
            "ON pipeline_cycle_log(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pipeline_cycle_log_slug "
            "ON pipeline_cycle_log(slug)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pipeline_cycle_log_coin_created "
            "ON pipeline_cycle_log(coin, created_at)"
        )
        conn.commit()
    finally:
        conn.close()


def insert_pipeline_cycle_log(row: dict[str, Any]) -> None:
    """Tek saatlik döngüde bir coin için karar satırı ekler."""
    init_pipeline_cycle_log_table()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO pipeline_cycle_log (
                created_at, cycle_slot_et, trade_date_et, et_clock_label,
                coin, slug, market_found,
                pred_direction, pred_confidence, pred_probability, pred_reasoning_snippet,
                direction_up_down, gate_yuksek_confidence, gate_trading_configured,
                outcome, skip_reason_code, skip_reason_detail,
                order_id, order_response, error_detail
            ) VALUES (
                :created_at, :cycle_slot_et, :trade_date_et, :et_clock_label,
                :coin, :slug, :market_found,
                :pred_direction, :pred_confidence, :pred_probability, :pred_reasoning_snippet,
                :direction_up_down, :gate_yuksek_confidence, :gate_trading_configured,
                :outcome, :skip_reason_code, :skip_reason_detail,
                :order_id, :order_response, :error_detail
            )
            """,
            row,
        )
        conn.commit()
    except sqlite3.Error as e:
        logger.exception("pipeline_cycle_log insert: %s", e)
    finally:
        conn.close()
