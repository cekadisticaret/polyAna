"""
Saatlik ETH/SOL tahmin + Polymarket CLOB gerçek işlem (POLYMARKET_BOT_ENABLED açıksa).

POLYMARKET_TRADING_ENABLED=false veya izin verilmeyen ET saatinde CLOB emri gönderilmez; YÜKSEK güven
ve bot açıkken tahmin yine hourly_trades + pipeline_cycle_log'a yazılır (trade_opened=0), resolve ile success güncellenir.

Gerçek emir: `hour_schedule.TRADING_HOUR_RESTRICTION_ENABLED` açıksa yalnızca belirli ET saatleri; kapalıysa her saat (diğer koşullar uygunsa).

Cron (iki satır):
  - X:10 — python -m src.main open  → tahmin + (bot açıksa emir) + «Saatlik Tahminler» Telegram
  - X:15 — python -m src.main resolve → önceki saat DB çözümü + gün özeti Telegram

Slug: {coin}-up-or-down-{month}-{day}-{year}-{hour}am/pm-et

İş günü (hourly_trades.trade_date_et): TR kesimi 16:00; ET saatlik slot / emirler aynı.
Telegram gün özeti: 16:00-16:59 TR bir önceki iş günü; 17:00'ten itibaren mevcut gün (sıfırlanmış sayılar).
"""
import json
import logging
from datetime import date, datetime, timezone, timedelta
from types import SimpleNamespace
from typing import Any, Optional
from zoneinfo import ZoneInfo

from src.analyzer.poly_bridge import run_poly_hourly_predictions
from src.analyzer.poly_predictor import Prediction
from src.config import Config
from src.data.hourly_trades import (
    daily_stats_for_day,
    fetch_pending_trades,
    init_hourly_table,
    update_success,
)
from src.data.portfolio_snapshots import insert_portfolio_snapshot
from src.data.pipeline_decision_log import insert_pipeline_cycle_log
from src.data.market_fetcher import (
    build_slug,
    fetch_market_by_slug,
    fetch_single_event_by_slug,
    format_et_clock,
    resolved_outcome_from_event,
)
from src.notifications import send_telegram
from src.trading.portfolio_snapshot import (
    portfolio_snapshot_values,
    portfolio_summary_lines_from_values,
)

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
TR = ZoneInfo("Europe/Istanbul")
COINS = {"ethereum": "ETH", "solana": "SOL"}
SYMBOL_FOR_COIN = {
    "ethereum": "ETHUSDT",
    "solana": "SOLUSDT",
}


def _business_day_date_tr(slot_at: datetime) -> str:
    """
    DB / gün özeti için iş günü tarihi (YYYY-MM-DD).
    TR'de gün 16:00'da değişir: saat < 16 → bir önceki takvim günü; aksi halde bugün.
    (tr - timedelta(hours=16) kullanılmaz; 16:00–23:59 arası bir gün kayması yapıyordu.)
    slot_at: mevcut saat dilimi slotu (timezone-aware).
    """
    tr = slot_at.astimezone(TR)
    d = tr.date()
    if tr.hour < 16:
        d = d - timedelta(days=1)
    return d.isoformat()


def _telegram_summary_trade_date(tr_now: datetime, db_trade_date_et: str) -> str:
    """
    Gün özeti Telegram metni için hangi trade_date_et satırına bakılacağı.
    DB iş günü 16:00'da değişir; 16:00-16:59 TR arası özet hâlâ kapanan günü gösterir,
    böylece 16:05 bildirimi boş/sıfırlanmış görünmez. 17:00 ve sonrası yeni iş günü sayılır.
    """
    if 16 <= tr_now.hour < 17:
        d = date.fromisoformat(db_trade_date_et)
        return (d - timedelta(days=1)).isoformat()
    return db_trade_date_et


def _slot_context(now_utc: Optional[datetime] = None) -> SimpleNamespace:
    """O anki saat dilimi (ET) ve bir önceki saat — open/resolve aynı slotu kullanır."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(ET)
    cur_et = now_et.replace(minute=0, second=0, microsecond=0)
    prev_et = cur_et - timedelta(hours=1)
    trade_date_et = _business_day_date_tr(cur_et)
    return SimpleNamespace(
        now_utc=now_utc,
        cur_et=cur_et,
        prev_et=prev_et,
        trade_date_et=trade_date_et,
        cur_clock=format_et_clock(cur_et),
        prev_clock=format_et_clock(prev_et),
    )


def _poly_direction_to_up_down(direction: str) -> Optional[str]:
    if direction == "YUKARI":
        return "UP"
    if direction == "AŞAĞI":
        return "DOWN"
    return None


def _format_poly_block(coin: str, pred: Optional[Prediction]) -> str:
    if pred is None:
        return f"   • {coin.upper()}: Tahmin üretilemedi (veri yetersiz veya fiyat yok)."
    d_en = _poly_direction_to_up_down(pred.direction) or "—"
    reason = (pred.reasoning or "")[:400]
    return (
        f"   • {coin.upper()}: {pred.direction} ({d_en}) | "
        f"~%{pred.probability * 100:.0f} | güven {pred.confidence} | hedef {pred.target_time}\n"
        f"     {reason}"
    )


def _coin_telegram_label(coin: str) -> str:
    return COINS.get(coin, coin.upper())


def _forecast_direction_line(pred: Optional[Prediction]) -> str:
    if pred is None:
        return "—"
    d = _poly_direction_to_up_down(pred.direction)
    return d if d else "—"


def _forecast_confidence_line(pred: Optional[Prediction]) -> str:
    if pred is None:
        return "GÜVEN SKORU —"
    return f"GÜVEN SKORU {pred.confidence}"


def _format_hourly_forecast_block(
    coin: str,
    cur_clock: str,
    pred: Optional[Prediction],
    trade_confirmed: bool,
) -> str:
    """İŞLEM AÇILDI: CLOB yanıtı başarılı ve hourly_trades kaydı yazıldı."""
    return "\n".join(
        [
            _coin_telegram_label(coin),
            cur_clock,
            _forecast_direction_line(pred),
            _forecast_confidence_line(pred),
            "İŞLEM AÇILDI" if trade_confirmed else "İŞLEM AÇILMADI",
        ]
    )


def _safe_order_response_repr(resp: Any) -> str:
    """CLOB yanıtını log/DB için güvenli metin yap (dict değilse repr)."""
    try:
        if isinstance(resp, dict):
            return json.dumps(resp, ensure_ascii=False)[:2000]
        return repr(resp)[:2000]
    except Exception:
        return repr(resp)[:2000]


def _order_success(resp: Any) -> bool:
    if not isinstance(resp, dict):
        return False
    if resp.get("error"):
        return False
    oid = resp.get("orderID") or resp.get("orderId") or resp.get("id")
    err = (resp.get("status") or "").lower()
    if err in ("rejected", "failed"):
        return False
    return oid is not None or err in ("matched", "live", "submitted", "pending")


def _opt_bool_int(v: Optional[bool]) -> Optional[int]:
    if v is None:
        return None
    return 1 if v else 0


def _log_pipeline_decision(
    *,
    now_utc: datetime,
    cur_et: datetime,
    trade_date_et: str,
    cur_clock: str,
    coin: str,
    slug: str,
    market_found: bool,
    pred: Optional[Prediction],
    direction_up_down: Optional[str],
    gate_yuksek: Optional[bool],
    gate_trading: Optional[bool],
    outcome: str,
    skip_reason_code: Optional[str] = None,
    skip_reason_detail: Optional[str] = None,
    order_id: Optional[str] = None,
    order_response: Optional[str] = None,
    error_detail: Optional[str] = None,
) -> None:
    insert_pipeline_cycle_log(
        {
            "created_at": now_utc.isoformat(),
            "cycle_slot_et": cur_et.isoformat(),
            "trade_date_et": trade_date_et,
            "et_clock_label": cur_clock,
            "coin": coin,
            "slug": slug,
            "market_found": 1 if market_found else 0,
            "pred_direction": pred.direction if pred else None,
            "pred_confidence": pred.confidence if pred else None,
            "pred_probability": float(pred.probability) if pred else None,
            "pred_reasoning_snippet": ((pred.reasoning or "")[:600] if pred else None),
            "direction_up_down": direction_up_down,
            "gate_yuksek_confidence": _opt_bool_int(gate_yuksek),
            "gate_trading_configured": _opt_bool_int(gate_trading),
            "outcome": outcome,
            "skip_reason_code": skip_reason_code,
            "skip_reason_detail": skip_reason_detail,
            "order_id": order_id,
            "order_response": order_response,
            "error_detail": error_detail,
        }
    )


def run_hourly_cycle_resolve_summary() -> None:
    """Cron :15 — önceki saat Gamma çözümünü DB'ye yaz; gün özeti Telegram."""
    init_hourly_table()
    ctx = _slot_context()
    trade_date_et = ctx.trade_date_et
    tr_now = ctx.now_utc.astimezone(TR)
    summary_trade_date = _telegram_summary_trade_date(tr_now, trade_date_et)

    # Tüm pending satırlar (tüm coin'ler): eski bitcoin satırları da DB'de; COINS ile
    # filtrelemek bu satırları hiç resolve etmediği için pending birikiyordu.
    for row in fetch_pending_trades():
        coin = row.get("coin") or ""
        slug = row["slug"]
        gamma = fetch_market_by_slug(slug) or fetch_single_event_by_slug(slug)
        actual = resolved_outcome_from_event(gamma)
        if not actual:
            logger.info(
                "Çözüm henüz yok veya fiyatlar kesin değil (Gamma): %s",
                slug,
            )
            continue
        pred = row["prediction"]
        ok = pred == actual
        update_success(slug, ok)
        logger.info(
            "Çözüm %s %s tahmin=%s gerçek=%s -> %s",
            coin,
            slug,
            pred,
            actual,
            "ok" if ok else "fail",
        )

    stats = daily_stats_for_day(summary_trade_date)
    summary_lines: list[str] = []
    for coin in COINS:
        st = stats[coin]
        opened = st["opened"]
        ok_c = st["resolved_ok"]
        fail_c = st["resolved_fail"]
        pend_c = st["pending"]
        summary_lines.append(
            f"{_coin_telegram_label(coin)} - {opened}/24"
        )
        summary_lines.append(f"{ok_c} BAŞARILI")
        summary_lines.append(f"{fail_c} BAŞARISIZ")
        summary_lines.append(f"{pend_c} DEVAM EDİYOR")
        summary_lines.append("----------------")
    if summary_lines and summary_lines[-1] == "----------------":
        summary_lines.pop()
    msg_summary = "\n".join(summary_lines)
    snap = portfolio_snapshot_values()
    extra = portfolio_summary_lines_from_values(snap)
    if extra:
        msg_summary = msg_summary + "\n\n" + "\n".join(extra)

    send_telegram(f"📊 Gün özeti ({summary_trade_date})\n\n{msg_summary}")

    now_et = ctx.now_utc.astimezone(ET)
    insert_portfolio_snapshot(
        recorded_at_utc=ctx.now_utc.isoformat(),
        captured_at_et=now_et.isoformat(),
        cycle_slot_et=ctx.cur_clock,
        trade_date_et=summary_trade_date,
        collateral_usdc=snap.get("collateral_usdc"),
        positions_mark_usdc=snap.get("positions_mark_usdc"),
        open_positions_count=snap.get("open_positions_count"),
        portfolio_total_usdc=snap.get("portfolio_total_usdc"),
    )

    logger.info("Gün özeti gönderildi — slot %s", ctx.cur_clock)


def run_hourly_cycle_open() -> None:
    """Cron :10 — tahmin + «Saatlik Tahminler» Telegram (çözüm / gün özeti yok).

    NOT: CLOB işlem açma poly_predictor.py'ye devredildi (WebSocket verileri daha güvenilir).
    Pipeline yalnızca pipeline_cycle_log'a kaydeder ve Telegram bildirimi gönderir.
    """
    init_hourly_table()
    ctx = _slot_context()
    now_utc = ctx.now_utc
    cur_et = ctx.cur_et
    trade_date_et = ctx.trade_date_et
    cur_clock = ctx.cur_clock

    preds_fetch_error = False
    try:
        preds_by_symbol = run_poly_hourly_predictions()
    except Exception:
        preds_fetch_error = True
        logger.exception("poly_predictor veri/tahmin hatasi")
        preds_by_symbol = {}

    hourly_forecast_blocks: list[str] = []
    detail_lines: list[str] = []

    for coin, _sym in COINS.items():
        slug_cur = build_slug(coin, cur_et)
        sym = SYMBOL_FOR_COIN[coin]
        pred = preds_by_symbol.get(sym)

        detail_lines.append(_format_poly_block(coin, pred))
        direction = _poly_direction_to_up_down(pred.direction) if pred else None

        if not direction:
            skip_code = (
                "PREDICTOR_CRASH" if preds_fetch_error
                else ("NO_PREDICTION" if pred is None else "NO_DIRECTION")
            )
            detail_s = (
                "run_poly_hourly_predictions() istisna" if preds_fetch_error
                else ("Tahmin None" if pred is None else f"Yon: {pred.direction if pred else '?'}")
            )
        else:
            skip_code = "DELEGATED_TO_PREDICTOR"
            detail_s = "Islem acma poly_predictor.py surecine devredildi"
            detail_lines.append(
                f"   \u2022 {coin.upper()}: {direction} ({pred.confidence if pred else '?'}) \u2014 "
                "islem poly_predictor.py tarafindan acilir."
            )

        _log_pipeline_decision(
            now_utc=now_utc,
            cur_et=cur_et,
            trade_date_et=trade_date_et,
            cur_clock=cur_clock,
            coin=coin,
            slug=slug_cur,
            market_found=True,
            pred=pred,
            direction_up_down=direction,
            gate_yuksek=None,
            gate_trading=None,
            outcome="pipeline_no_trade",
            skip_reason_code=skip_code,
            skip_reason_detail=detail_s,
        )

        hourly_forecast_blocks.append(
            _format_hourly_forecast_block(coin, cur_clock, pred, False)
        )

    msg_hourly = "Saatlik Tahminler\n\n" + "\n\n".join(hourly_forecast_blocks)
    send_telegram(msg_hourly)

    if detail_lines:
        logger.info("Tahmin ozeti:\n%s", "\n".join(detail_lines))

    logger.info("Acilis dongusu tamamlandi — slot %s ET", cur_clock)
