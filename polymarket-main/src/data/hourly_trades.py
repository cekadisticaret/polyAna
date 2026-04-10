"""
Saatlik Polymarket gerçek işlemler — SQLite (data/trades.db, tablo hourly_trades).

trade_date_et: iş günü (YYYY-MM-DD); kesim her gün 16:00 Europe/Istanbul (pipeline ile uyumlu).
"""
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "trades.db"
HOURLY_TRADES_FULL_MD = DB_PATH.parent / "hourly_trades_full.md"


def _ensure_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def write_hourly_trades_full_md() -> None:
    """
    data/hourly_trades_full.md — tablonun tam dökümü (özet + gün×ET + tüm satırlar).
    Kayıt eklendiğinde / çözüm güncellendiğinde çağrılır; hata insert/update'i bozmaz.
    """
    init_hourly_table()
    conn = get_connection()
    try:
        rows = list(
            conn.execute(
                """
                SELECT id, coin, trade_date_et, et_clock_label, predicted_at,
                       success, trade_opened, slug, error
                FROM hourly_trades ORDER BY id
                """
            )
        )
    finally:
        conn.close()

    def durum(s: Any) -> str:
        if s is None:
            return "Beklemede"
        return "Başarılı" if s == 1 else "Başarısız"

    def opened(o: Any) -> str:
        return "Evet" if o else "Hayır"

    n = len(rows)
    ok = sum(1 for r in rows if r["success"] == 1)
    fail = sum(1 for r in rows if r["success"] == 0)
    pend = sum(1 for r in rows if r["success"] is None)
    err_n = sum(1 for r in rows if r["error"])
    oy = sum(1 for r in rows if r["trade_opened"] == 1)
    on = sum(1 for r in rows if r["trade_opened"] == 0)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    by_day_hour: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0, 0])
    )
    for r in rows:
        d = r["trade_date_et"]
        h = r["et_clock_label"]
        s = r["success"]
        if s == 1:
            by_day_hour[d][h][0] += 1
        elif s == 0:
            by_day_hour[d][h][1] += 1
        else:
            by_day_hour[d][h][2] += 1

    def hour_sort_key(label: str) -> int:
        try:
            part = label.replace(" ET", "").split(":")[0]
            return int(part)
        except Exception:
            return 99

    lines: list[str] = []
    lines.append("# hourly_trades — tam liste")
    lines.append("")
    lines.append(f"Kaynak: `data/trades.db`, tablo `hourly_trades`. Oluşturulma: {now}.")
    lines.append("")
    lines.append("## Özet")
    lines.append("")
    lines.append(f"- Toplam kayıt: **{n}**")
    lines.append(
        f"- Başarılı: {ok} | Başarısız: {fail} | Beklemede: {pend} | Emir/işlem hatası: {err_n}"
    )
    lines.append("")
    lines.append(
        f"- İşlem açıldı (CLOB): **{oy}** Evet | **{on}** Hayır (`trade_opened`; "
        "hayır = CLOB emri olmadan yazılan tahmin satırı)"
    )
    lines.append("")
    lines.append(
        "- `işlem açıldı`: CLOB üzerinden emir gönderilip `hourly_trades` satırına yazıldıysa "
        "Evet (`trade_opened=1`); yalnızca tahmin/çözüm takibi için kayıt varsa Hayır."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Gün ve ET saati özeti (`trade_date_et` × `et_clock_label`)")
    lines.append("")
    lines.append("Sütunlar: kazanç (+) / kayıp (−) / beklemede (?) sayıları.")
    lines.append("")

    for d in sorted(by_day_hour.keys()):
        lines.append(f"### {d} (ET iş günü)")
        lines.append("")
        lines.append("| ET saati | + kazanç | − kayıp | ? beklemede |")
        lines.append("|----------|----------|---------|-------------|")
        hours = sorted(by_day_hour[d].keys(), key=hour_sort_key)
        for h in hours:
            w, loss, p = by_day_hour[d][h]
            lines.append(f"| {h} | {w} | {loss} | {p} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Tüm kayıtlar (sıra: `id`)")
    lines.append("")
    lines.append(
        "| # | coin | `trade_date_et` | ET saat | `predicted_at` (UTC) | durum | "
        "işlem açıldı | market (`slug`) |"
    )
    lines.append("|---|------|-----------------|---------|----------------------|-------|--------------|-----------------|")
    for r in rows:
        pa = r["predicted_at"] or ""
        if pa and not (pa.startswith("`") and pa.endswith("`")):
            pa = f"`{pa}`"
        lines.append(
            f"| {r['id']} | {r['coin']} | {r['trade_date_et']} | {r['et_clock_label']} | {pa} | "
            f"{durum(r['success'])} | {opened(r['trade_opened'])} | `{r['slug']}` |"
        )

    out = "\n".join(lines) + "\n"
    try:
        HOURLY_TRADES_FULL_MD.write_text(out, encoding="utf-8")
    except OSError as e:
        logger.warning("hourly_trades_full.md yazılamadı: %s", e)


def init_hourly_table() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hourly_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coin TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                prediction TEXT NOT NULL,
                success INTEGER,
                predicted_at TEXT NOT NULL,
                trade_date_et TEXT NOT NULL,
                et_clock_label TEXT NOT NULL,
                order_id TEXT,
                order_response TEXT,
                error TEXT,
                trade_opened INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hourly_trades_date ON hourly_trades(trade_date_et)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hourly_trades_coin ON hourly_trades(coin)")
        # Migration: mevcut tabloya trade_opened kolonu ekle (yoksa)
        try:
            conn.execute(
                "ALTER TABLE hourly_trades ADD COLUMN trade_opened INTEGER NOT NULL DEFAULT 1"
            )
            logger.info("hourly_trades: trade_opened kolonu eklendi (migration).")
        except Exception:
            pass  # Kolon zaten var
        conn.commit()
    finally:
        conn.close()


def fetch_pending_trades() -> list[dict[str, Any]]:
    """error IS NULL ve success IS NULL — Gamma çözümü bekleyen satırlar (id sırası)."""
    init_hourly_table()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM hourly_trades
            WHERE error IS NULL AND success IS NULL
            ORDER BY id ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_by_slug(slug: str) -> dict[str, Any] | None:
    init_hourly_table()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM hourly_trades WHERE slug = ?",
            (slug,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_trade(
    *,
    coin: str,
    slug: str,
    prediction: str,
    predicted_at: str,
    trade_date_et: str,
    et_clock_label: str,
    order_id: str | None,
    order_response: str | None,
    error: str | None = None,
    trade_opened: bool = True,
) -> int | None:
    init_hourly_table()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO hourly_trades (
                coin, slug, prediction, success, predicted_at,
                trade_date_et, et_clock_label, order_id, order_response, error,
                trade_opened
            ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                coin,
                slug,
                prediction,
                predicted_at,
                trade_date_et,
                et_clock_label,
                order_id,
                order_response,
                error,
                1 if trade_opened else 0,
            ),
        )
        conn.commit()
        row_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        write_hourly_trades_full_md()
        return row_id
    except sqlite3.IntegrityError:
        logger.warning("hourly_trades slug zaten var: %s", slug)
        return None
    except Exception as e:
        logger.exception("hourly_trades insert: %s", e)
        return None
    finally:
        conn.close()


def update_success(slug: str, success: bool) -> None:
    init_hourly_table()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE hourly_trades SET success = ? WHERE slug = ?",
            (1 if success else 0, slug),
        )
        conn.commit()
        write_hourly_trades_full_md()
    finally:
        conn.close()


def daily_stats_for_day(trade_date_et: str) -> dict[str, dict[str, int]]:
    """
    coin -> opened, resolved_ok, resolved_fail, pending
    """
    init_hourly_table()
    conn = get_connection()
    out: dict[str, dict[str, int]] = {
        "ethereum": {"opened": 0, "resolved_ok": 0, "resolved_fail": 0, "pending": 0},
        "solana": {"opened": 0, "resolved_ok": 0, "resolved_fail": 0, "pending": 0},
    }
    try:
        for c in ("ethereum", "solana"):
            opened = conn.execute(
                """
                SELECT COUNT(*) FROM hourly_trades
                WHERE trade_date_et = ? AND coin = ? AND error IS NULL
                """,
                (trade_date_et, c),
            ).fetchone()
            ok = conn.execute(
                """
                SELECT COUNT(*) FROM hourly_trades
                WHERE trade_date_et = ? AND coin = ? AND error IS NULL AND success = 1
                """,
                (trade_date_et, c),
            ).fetchone()
            fail = conn.execute(
                """
                SELECT COUNT(*) FROM hourly_trades
                WHERE trade_date_et = ? AND coin = ? AND error IS NULL AND success = 0
                """,
                (trade_date_et, c),
            ).fetchone()
            pend = conn.execute(
                """
                SELECT COUNT(*) FROM hourly_trades
                WHERE trade_date_et = ? AND coin = ? AND error IS NULL AND success IS NULL
                """,
                (trade_date_et, c),
            ).fetchone()
            out[c]["opened"] = int(opened[0]) if opened else 0
            out[c]["resolved_ok"] = int(ok[0]) if ok else 0
            out[c]["resolved_fail"] = int(fail[0]) if fail else 0
            out[c]["pending"] = int(pend[0]) if pend else 0
    finally:
        conn.close()
    return out
