"""
Saatlik ETH/SOL "up or down" marketleri — yalnızca Gamma GET /events (slug dizisi).

Örnek: .../events?slug=ethereum-up-or-down-...&slug=solana-up-or-down-...
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any

import requests

from src.config import Config

logger = logging.getLogger(__name__)

_MONTHS = [
    "",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]


def hour_ampm(h: int) -> str:
    if h == 0:
        return "12am"
    if h < 12:
        return f"{h}am"
    if h == 12:
        return "12pm"
    return f"{h - 12}pm"


def build_slug(coin: str, et_dt: datetime) -> str:
    """
    coin: 'ethereum' | 'solana'
    et_dt: America/New_York ile bilinçli datetime (saat başına hizalı).
    """
    month = _MONTHS[et_dt.month]
    return f"{coin}-up-or-down-{month}-{et_dt.day}-{et_dt.year}-{hour_ampm(et_dt.hour)}-et"


def _parse_prices(outcome_prices: str | list) -> tuple[float, float]:
    if isinstance(outcome_prices, list):
        yes_p = float(outcome_prices[0]) if outcome_prices else 0
        no_p = float(outcome_prices[1]) if len(outcome_prices) > 1 else 1 - yes_p
        return (yes_p, no_p)
    try:
        arr = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
        yes_p = float(arr[0]) if arr else 0
        no_p = float(arr[1]) if len(arr) > 1 else 1 - yes_p
        return (yes_p, no_p)
    except (json.JSONDecodeError, TypeError, IndexError):
        return (0.5, 0.5)


def fetch_events_by_slugs(slugs: list[str]) -> list[dict[str, Any]]:
    """
    GET /events — slug parametresi birden fazla verilebilir.
    """
    if not slugs:
        return []
    base = Config.GAMMA_API_BASE.rstrip("/")
    params = [("slug", s) for s in slugs]
    try:
        resp = requests.get(f"{base}/events", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.exception("Gamma /events hatası: %s", e)
        return []

    if not isinstance(data, list):
        return []
    return data


def _passes_event_filters(ev: dict, now: datetime) -> bool:
    """Kapalı/pasif ve süresi dolmuş eventleri ele; üst süre sınırı yok."""
    if ev.get("closed"):
        return False
    if not ev.get("active", True):
        return False
    end_str = ev.get("endDate") or ""
    if not end_str:
        return False
    try:
        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        if not (now < end_dt):
            return False
    except (ValueError, TypeError):
        return False
    return True


HOURLY_UP_DOWN_COINS = ("ethereum", "solana")


def fetch_hourly_up_down_markets(et_window: datetime) -> list[dict[str, Any]]:
    """
    Verilen saat dilimi için ethereum ve solana eventlerini tek istekte çeker,
    event düzeyinde (kapalı/pasif/süresi dolmuş) süzer; ilk marketi alır.
    """
    now = datetime.now(timezone.utc)

    slugs = [build_slug(coin, et_window) for coin in HOURLY_UP_DOWN_COINS]
    events = fetch_events_by_slugs(slugs)
    by_slug = {e.get("slug"): e for e in events if isinstance(e, dict) and e.get("slug")}

    out: list[dict[str, Any]] = []
    for coin, slug in zip(HOURLY_UP_DOWN_COINS, slugs):
        ev = by_slug.get(slug)
        if not ev or not isinstance(ev, dict):
            logger.warning("Event bulunamadı: %s", slug)
            continue
        if not _passes_event_filters(ev, now):
            logger.warning("Event filtreden geçmedi: %s", slug)
            continue

        markets = ev.get("markets") or []
        if not isinstance(markets, list):
            continue

        title = ev.get("title") or ev.get("slug") or ""
        picked = False
        for m in markets:
            if not isinstance(m, dict):
                continue
            enriched = dict(m)
            enriched["_coin"] = coin
            enriched["_event_title"] = title
            out.append(enriched)
            picked = True
            break
        if not picked:
            logger.warning("Event içinde market yok: %s", slug)

    return out


def format_for_llm(markets: list[dict]) -> list[dict[str, Any]]:
    """Gamma market objesini LLM input formatına dönüştür."""
    result = []
    for m in markets:
        yes_p, no_p = _parse_prices(m.get("outcomePrices", "[]"))
        spread = m.get("spread")
        spread_val = float(spread) if spread is not None else 0

        event_name = m.get("_event_title") or ""
        if not event_name and m.get("events") and isinstance(m["events"], list):
            event_name = m["events"][0].get("title", m["events"][0].get("slug", ""))
        elif not event_name and m.get("slug"):
            event_name = m["slug"]

        end_str = m.get("endDate") or m.get("endDateIso") or ""
        try:
            if end_str:
                if end_str.count("-") == 2 and "T" not in end_str:
                    end_str = f"{end_str}T23:59:59Z"
                end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                resolution_hours = (end_dt - datetime.now(timezone.utc)).total_seconds() / 3600
                resolution_hours = max(0, resolution_hours)
            else:
                resolution_hours = 0.0
        except (ValueError, TypeError):
            resolution_hours = 0.0

        result.append({
            "coin": m.get("_coin", ""),
            "condition_id": m.get("conditionId", ""),
            "question": m.get("question", "?"),
            "event_name": event_name,
            "yes_price": round(yes_p, 4),
            "no_price": round(no_p, 4),
            "volume": round(float(m.get("volumeNum") or m.get("volume") or 0), 2),
            "liquidity": round(float(m.get("liquidityNum") or m.get("liquidity") or 0), 2),
            "spread": round(spread_val, 4),
            "resolution_hours": round(resolution_hours, 1),
            "news": "",
        })
    return result


def fetch_single_event_by_slug(slug: str) -> dict[str, Any] | None:
    """Önceki saat çözümü gibi tek slug sorguları için."""
    events = fetch_events_by_slugs([slug])
    if not events:
        return None
    ev = events[0]
    return ev if isinstance(ev, dict) else None


def fetch_market_by_slug(slug: str) -> dict[str, Any] | None:
    """
    GET /markets/slug/{slug} — tek market objesi (outcomePrices, events[].eventMetadata)
    çözüm için /events'e göre genelde daha güncel.
    """
    base = Config.GAMMA_API_BASE.rstrip("/")
    try:
        resp = requests.get(f"{base}/markets/slug/{slug}", timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning("Gamma /markets/slug hatası slug=%s: %s", slug, e)
        return None
    return data if isinstance(data, dict) else None


def _parse_event_metadata_blob(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _extract_hourly_event_metadata(event: dict) -> dict[str, Any] | None:
    """
    Gamma: event veya gömülü market.events[].eventMetadata içinde finalPrice olabilir.
    /markets/slug cevabında tek market kökünde events[].eventMetadata da olabilir.
    finalPrice dolu bir metadata dict döndürür (yoksa None).
    """
    top = _parse_event_metadata_blob(event.get("eventMetadata"))
    if top is not None and top.get("finalPrice") is not None:
        return top
    for ev in event.get("events") or []:
        if not isinstance(ev, dict):
            continue
        meta = _parse_event_metadata_blob(ev.get("eventMetadata"))
        if meta is not None and meta.get("finalPrice") is not None:
            return meta
    for mkt in event.get("markets") or []:
        if not isinstance(mkt, dict):
            continue
        for nested in mkt.get("events") or []:
            if not isinstance(nested, dict):
                continue
            meta = _parse_event_metadata_blob(nested.get("eventMetadata"))
            if meta is not None and meta.get("finalPrice") is not None:
                return meta
        meta = _parse_event_metadata_blob(mkt.get("eventMetadata"))
        if meta is not None and meta.get("finalPrice") is not None:
            return meta
    return None


def _up_down_from_final_price_and_beat(metadata: dict[str, Any]) -> str | None:
    """
    Piyasa kuralları (Binance 1H mum): close >= open → Up, değilse Down.
    Gamma eventMetadata: finalPrice ≈ close, priceToBeat ≈ open.
    """
    fp = metadata.get("finalPrice")
    pb = metadata.get("priceToBeat")
    if fp is None or pb is None:
        return None
    try:
        close = float(fp)
        open_px = float(pb)
    except (TypeError, ValueError):
        return None
    return "UP" if close >= open_px else "DOWN"


def resolved_outcome_up_down_from_market(market: dict) -> str | None:
    """
    Up/Down saatlik market: outcomePrices sırası outcomes ile aynı (Up, Down).
    Bir taraf ~1.0 ise o taraf kazanmıştır.
    """
    prices_raw = market.get("outcomePrices", "[]")
    if isinstance(prices_raw, str):
        try:
            prices = json.loads(prices_raw)
        except json.JSONDecodeError:
            return None
    else:
        prices = prices_raw
    if not isinstance(prices, list) or len(prices) < 2:
        return None
    try:
        p0, p1 = float(prices[0]), float(prices[1])
        if p0 >= 0.99:
            return "UP"
        if p1 >= 0.99:
            return "DOWN"
    except (ValueError, TypeError, IndexError):
        pass
    return None


def _market_dict_for_outcome_prices(payload: dict) -> dict | None:
    """Gamma /events (event.markets[0]) veya /markets/slug (tek market kökü)."""
    mk = payload.get("markets") or []
    if mk and isinstance(mk[0], dict):
        return mk[0]
    if payload.get("outcomePrices") is not None or payload.get("conditionId"):
        return payload
    return None


def resolved_outcome_from_event(event: dict | None) -> str | None:
    """
    Gamma /events veya /markets/slug gövdesi: öncelik eventMetadata (finalPrice+priceToBeat);
    yoksa outcomePrices (≈0.99) yedeği.
    """
    if not event or not isinstance(event, dict):
        return None
    meta = _extract_hourly_event_metadata(event)
    if meta is not None:
        from_meta = _up_down_from_final_price_and_beat(meta)
        if from_meta is not None:
            return from_meta
    m = _market_dict_for_outcome_prices(event)
    if not m:
        return None
    return resolved_outcome_up_down_from_market(m)


def format_et_clock(et_dt: datetime) -> str:
    """Örn. 11:00 ET — saat dilimi etiketi."""
    return et_dt.strftime("%H:%M") + " ET"
