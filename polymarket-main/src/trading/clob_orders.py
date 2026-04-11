"""
Polymarket CLOB — outcome token üzerinden alım.
"""
import json
import logging
import time
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from typing import Any

from eth_account import Account
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType, PartialCreateOrderOptions
from py_clob_client.exceptions import PolyApiException
from py_clob_client.order_builder.constants import BUY

from src.config import Config

logger = logging.getLogger(__name__)

CLOB_HOST = "https://clob.polymarket.com"

# FAK "no orders found to match" — kitap anlık değişince; kısa gecikmeyle yeniden dene
MAX_FAK_NO_MATCH_ATTEMPTS = 3
FAK_RETRY_DELAY_SEC = 0.35


def _is_fak_no_match_error(exc: BaseException) -> bool:
    if not isinstance(exc, PolyApiException):
        return False
    em = exc.error_msg
    if isinstance(em, dict):
        err = str(em.get("error", ""))
    else:
        err = str(em)
    return "no orders found to match with fak order" in err.lower()


def _normalize_key(key: str) -> str:
    k = (key or "").strip()
    if k.startswith("0x"):
        return k[2:]
    return k


def funder_address() -> str:
    if Config.POLYMARKET_FUNDER:
        return Config.POLYMARKET_FUNDER.strip()
    pk = _normalize_key(Config.POLYMARKET_PRIVATE_KEY)
    if not pk:
        raise ValueError("POLYMARKET_PRIVATE_KEY veya POLYMARKET_FUNDER gerekli")
    return Account.from_key("0x" + pk).address


def build_clob_client() -> ClobClient:
    pk = _normalize_key(Config.POLYMARKET_PRIVATE_KEY)
    if not pk:
        raise ValueError("POLYMARKET_PRIVATE_KEY tanımlı değil")
    key_hex = "0x" + pk
    fund = funder_address()
    temp = ClobClient(CLOB_HOST, chain_id=Config.POLYMARKET_CHAIN_ID, key=key_hex)
    creds: ApiCreds | None = temp.create_or_derive_api_creds()
    if creds is None:
        raise RuntimeError("CLOB API anahtarı türetilemedi")
    return ClobClient(
        CLOB_HOST,
        chain_id=Config.POLYMARKET_CHAIN_ID,
        key=key_hex,
        creds=creds,
        signature_type=Config.POLYMARKET_SIGNATURE_TYPE,
        funder=fund,
    )


def parse_clob_token_ids(market: dict) -> tuple[str, str]:
    raw = market.get("clobTokenIds") or "[]"
    if isinstance(raw, str):
        ids = json.loads(raw)
    else:
        ids = raw
    if not isinstance(ids, list) or len(ids) < 2:
        raise ValueError("clobTokenIds eksik veya geçersiz")
    return str(ids[0]), str(ids[1])


def _marketable_buy_limit_price(
    client: ClobClient,
    token_id: str,
    usdc_target: float,
) -> float:
    """
    Alımda anında eşleşme için limit fiyat: kitaptaki ask tarafına göre (SDK
    calculate_market_price). Midpoint spread içinde kalır; FAK ile uyumsuzdu.
    """
    if usdc_target <= 0:
        raise ValueError("usdc_target pozitif olmalı")
    p = client.calculate_market_price(token_id, "BUY", float(usdc_target), OrderType.FAK)
    return min(0.99, max(0.01, float(p)))


def _decimal_from_float(x: float) -> Decimal:
    """Binary float gürültüsünü azaltmak için önce yuvarla, sonra Decimal."""
    return Decimal(str(round(float(x), 8)))


def _to_clob_buy_floats(size_d: Decimal, price_d: Decimal) -> tuple[float, float]:
    """
    py-clob-client get_order_amounts: pay (taker) round_down(size, 2) — en fazla 2 ondalık.
    Fiyat tick 0.01 için 2 ondalık; string ile float gürültüsünü kes.
    """
    sq = size_d.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    pq = price_d.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    return float(f"{sq:.2f}"), float(f"{pq:.2f}")


def _maker_usdc_is_whole_cents(m: Decimal) -> bool:
    """BUY maker (USDC): kesirli sent olmamalı (API + py-clob-client #121)."""
    cents = m * 100
    return cents == cents.quantize(Decimal("1"), rounding=ROUND_DOWN)


def _fit_buy_limit_for_clob(
    size: float,
    price: float,
    min_shares: float = 0.0,
) -> tuple[float, float]:
    """
    CLOB limit BUY + py-clob-client uyumu:
    - SDK payı round_down(size, **2**) uygular; pay en fazla **2** ondalık olmalı.
    - Maker (USDC, pay×fiyat): tam sent.
    - Arama adımı 0.01 (SDK ile aynı grid). Fiyat tick 0.01 ile 2 ondalık hizalı.
    """
    p_raw = _decimal_from_float(price).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
    p = p_raw.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    if p <= 0:
        return float(size), float(price)

    min_s = Decimal(str(max(0.0, float(min_shares))))
    min_s = min_s.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    if min_s < Decimal(str(min_shares)):
        min_s = Decimal(str(min_shares)).quantize(Decimal("0.01"), rounding=ROUND_UP)

    s = _decimal_from_float(size).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    if s <= 0:
        s = Decimal("0.01")

    if s < min_s:
        s = min_s

    step = Decimal("0.01")
    max_steps = 50_000
    initial_s = s

    def try_s(candidate: Decimal) -> tuple[float, float] | None:
        c = candidate.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        m = c * p
        if not _maker_usdc_is_whole_cents(m):
            return None
        sf, pf = _to_clob_buy_floats(c, p)
        mq = m.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        logger.info(
            "CLOB maker tam sent (pay 2 ondalık): pay=%.2f fiyat=%.2f → USDC≈%s",
            sf,
            pf,
            mq,
        )
        return sf, pf

    for _ in range(max_steps):
        if s < min_s:
            break
        out = try_s(s)
        if out is not None:
            return out
        s -= step

    s = min_s
    while s <= initial_s:
        out = try_s(s)
        if out is not None:
            return out
        s += step

    raise RuntimeError(
        "CLOB BUY: maker tam sent + min_shares ile uygun pay bulunamadı "
        f"(min_shares={min_shares}, price={price}, size_hint={size})"
    )


def place_buy_fak(
    client: ClobClient,
    token_id: str,
    size: float,
    limit_price: float,
    *,
    min_shares: float = 0.0,
) -> dict[str, Any]:
    """
    FAK limit emir: limit_price marketable (ask'e uygun) olmalı.
    """
    price = min(0.99, max(0.01, float(limit_price)))
    size_q, price_q = _fit_buy_limit_for_clob(size, price, min_shares=min_shares)
    if (size_q, price_q) != (float(size), price):
        logger.info(
            "CLOB pay/fiyat ayarı: size %.6f→%.2f, price %.6f→%.2f (min_shares=%s)",
            float(size),
            size_q,
            float(limit_price),
            price_q,
            min_shares,
        )
    args = OrderArgs(token_id=token_id, price=price_q, size=size_q, side=BUY)
    signed = client.create_order(args, PartialCreateOrderOptions())
    out = client.post_order(signed, orderType=OrderType.FAK)
    if not isinstance(out, dict):
        logger.warning(
            "CLOB post_order beklenmeyen tip=%s değer=%s",
            type(out).__name__,
            repr(out)[:800],
        )
    return out


def place_buy_for_up_down(
    market: dict,
    *,
    up_or_down: str,
    notional_usdc: float,
) -> dict[str, Any]:
    """
    up_or_down: UP|DOWN — Up/Down outcome sırası Gamma ile uyumlu (ilk token Up).
    Hedef ~notional_usdc USDC: pay = max(orderMinSize, nominal / marketable fiyat).
    """
    slug = market.get("slug") or market.get("eventSlug") or "?"
    up_id, down_id = parse_clob_token_ids(market)
    token_id = up_id if up_or_down.upper() == "UP" else down_id
    logger.info(
        "CLOB emir hazırlanıyor slug=%s yön=%s ~%.2f USDC",
        slug,
        up_or_down.upper(),
        notional_usdc,
    )
    try:
        client = build_clob_client()
    except Exception:
        logger.exception("CLOB istemci oluşturulamadı slug=%s", slug)
        raise
    try:
        min_shares = float(market.get("orderMinSize") or 5)
    except (TypeError, ValueError):
        min_shares = 5.0
    for attempt in range(1, MAX_FAK_NO_MATCH_ATTEMPTS + 1):
        try:
            p1 = _marketable_buy_limit_price(client, token_id, notional_usdc)
            raw_shares = notional_usdc / p1
            size = max(min_shares, raw_shares)
            size = float(
                _decimal_from_float(size).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            )
            usdc_target = max(notional_usdc, size * p1)
            limit_price = _marketable_buy_limit_price(client, token_id, usdc_target)
            if attempt == 1:
                logger.info(
                    "Emir boyutu: hedef ~%.2f USDC, marketable_limit=%.4f, min_shares=%s, size=%s, usdc_target=%.2f",
                    notional_usdc,
                    limit_price,
                    min_shares,
                    size,
                    usdc_target,
                )
            else:
                logger.info(
                    "FAK tekrar deneme %s/%s slug=%s marketable_limit=%.4f size=%s usdc_target=%.2f",
                    attempt,
                    MAX_FAK_NO_MATCH_ATTEMPTS,
                    slug,
                    limit_price,
                    size,
                    usdc_target,
                )
            order = place_buy_fak(
                client, token_id, size, limit_price, min_shares=min_shares
            )
            return {
                "order":           order,
                "execution_price": limit_price,
                "shares":          size,
            }
        except Exception as e:
            if (
                _is_fak_no_match_error(e)
                and attempt < MAX_FAK_NO_MATCH_ATTEMPTS
            ):
                logger.warning(
                    "FAK eşleşme yok (deneme %s/%s), %.2fs sonra kitapla yeniden hesaplanıyor slug=%s",
                    attempt,
                    MAX_FAK_NO_MATCH_ATTEMPTS,
                    FAK_RETRY_DELAY_SEC,
                    slug,
                )
                time.sleep(FAK_RETRY_DELAY_SEC)
                continue
            logger.exception(
                "CLOB place_buy_fak başarısız slug=%s token_id=%s...",
                slug,
                token_id[:16],
            )
            raise
