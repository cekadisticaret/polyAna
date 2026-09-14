"""Gerçek PM — zincirde açık ama bot state'te kayıtsız (ghost) pozisyonları senkronlar."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from pm_poly_history import _fetch_activity, _group_activity
from pm_trader_helpers import pm_conditional_shares

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_DIR, "..")
_TZ_TR = ZoneInfo("Europe/Istanbul")

# Binance spot makul aralık — yanlış sibling kopyasını yakala
_ENTRY_SANE = {
    "BTCUSDT": (10_000.0, 250_000.0),
    "ETHUSDT": (500.0, 15_000.0),
    "SOLUSDT": (10.0, 500.0),
}

_TRADER_STATE = {
    "analiz5": os.path.join(_DIR, "poly_trader_analiz5_state.json"),
    "analiz2_live": os.path.join(_DIR, "poly_trader_analiz2_live_state.json"),
    "analiz6_live": os.path.join(_DIR, "poly_trader_analiz6_live_state.json"),
    "manual": os.path.join(_DIR, "poly_trader_manual_state.json"),
}

# Orphan atamasında izinli semboller (None = hepsi)
_TRADER_SYMBOLS: dict[str, frozenset[str] | None] = {
    "analiz5": frozenset({"BTCUSDT", "SOLUSDT"}),
    "analiz2_live": frozenset({"SOLUSDT"}),
    "analiz6_live": frozenset({"BTCUSDT", "SOLUSDT", "ETHUSDT"}),
    "manual": None,
}

_SYM_MAP = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
_HOURLY_SLOT = re.compile(r"-(\d{1,2}(?:am|pm)-et)$")


def _hour_slot(slug: str) -> str:
    m = _HOURLY_SLOT.search(slug or "")
    return m.group(1) if m else ""


def _load_state(path: str) -> dict:
    if not os.path.isfile(path):
        return {"open_positions": [], "total_pnl": 0.0}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _hour_open_price(symbol: str) -> float:
    """Saatlik slot girişi — tamamlanmış önceki 1h mum kapanışı."""
    import asyncio
    try:
        from poly_predictor_analysis import _fetch_klines

        async def _go() -> float:
            klines = await _fetch_klines(symbol, "1h", 3)
            if klines and len(klines) >= 2:
                return float(klines[-2]["close"])
            return 0.0

        return asyncio.run(_go())
    except Exception:
        return 0.0


def _entry_sane(symbol: str, entry: float) -> bool:
    lo, hi = _ENTRY_SANE.get(symbol.upper(), (0.0, 1e12))
    return lo <= entry <= hi


def _resolve_entry_price(symbol: str, sibling: dict | None) -> float:
    if sibling and (sibling.get("symbol") or "").upper() == symbol.upper():
        ep = float(sibling.get("entry_price") or 0)
        if _entry_sane(symbol, ep):
            return ep
    ep = _hour_open_price(symbol)
    if ep > 0 and _entry_sane(symbol, ep):
        return ep
    return 0.0


def _repair_open_entries(states: dict[str, dict]) -> set[str]:
    """State'teki bariz yanlış giriş fiyatlarını düzelt. Dönen: değişen trader key'leri."""
    dirty: set[str] = set()
    for key, st in states.items():
        for p in st.get("open_positions") or []:
            sym = (p.get("symbol") or "").upper()
            ep = float(p.get("entry_price") or 0)
            if _entry_sane(sym, ep):
                continue
            new_ep = _hour_open_price(sym)
            if new_ep > 0 and _entry_sane(sym, new_ep):
                p["entry_price"] = round(new_ep, 4 if sym != "BTCUSDT" else 2)
                dirty.add(key)
    return dirty


def _pos_key(pos: dict) -> tuple[str, str]:
    slug = (pos.get("pm_slug") or "").lower()
    sym = (pos.get("symbol") or "").upper()
    return slug, sym


def _known_keys(states: dict[str, dict]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for st in states.values():
        for p in st.get("open_positions") or []:
            keys.add(_pos_key(p))
    return keys


def _known_token_ids(states: dict[str, dict]) -> set[str]:
    """Başka bot state'inde kayıtlı PM token — çift orphan yazmayı engelle."""
    ids: set[str] = set()
    for st in states.values():
        for p in st.get("open_positions") or []:
            tid = str(p.get("pm_token_id") or "").strip()
            if tid:
                ids.add(tid)
    return ids


_15M_TS = re.compile(r"-15m-(\d{8,})$")


def _15m_period_ts(slug: str) -> int | None:
    m = _15M_TS.search((slug or "").lower())
    return int(m.group(1)) if m else None


def _15m_period_open(slug: str, now_ts: float | None = None) -> bool:
    """15m slot hâlâ açık mı (period start + 15dk)."""
    ts = _15m_period_ts(slug)
    if ts is None:
        return True
    now = time.time() if now_ts is None else now_ts
    return now < ts + 15 * 60


def _guess_trader(slug: str, states: dict[str, dict]) -> str | None:
    slug_l = (slug or "").lower()
    # 15m updown — saatlik ET slot yok ve 15M defterleri kaldırıldı (2026-08-14);
    # sahibi belirlenemez, atanmadan bırakılır.
    if "updown-15m" in slug_l or _15M_TS.search(slug_l):
        return None
    slot = _hour_slot(slug)
    if not slot:
        return None
    counts: dict[str, int] = {}
    for key, st in states.items():
        if key == "manual":
            continue
        for p in st.get("open_positions") or []:
            ps = p.get("pm_slug") or ""
            if _hour_slot(ps) == slot:
                counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _buys_for_slug(acts: list[dict], slug: str) -> list[dict]:
    rows = [
        a for a in acts
        if a.get("type") == "TRADE"
        and a.get("side") == "BUY"
        and (a.get("slug") or a.get("eventSlug")) == slug
    ]
    rows.sort(key=lambda x: x.get("timestamp", 0))
    return rows


def _round_to_pos(open_round: dict, acts: list[dict], sibling: dict | None) -> dict | None:
    slug = open_round.get("slug") or ""
    sym = open_round.get("sym") or "?"
    direction = open_round.get("dir") or "?"
    buys = _buys_for_slug(acts, slug)
    if not buys:
        return None

    token_id = str(buys[-1].get("asset") or "")
    if not token_id:
        return None

    total_size = round(sum(float(b.get("size") or 0) for b in buys), 4)
    chain_size = pm_conditional_shares(token_id)
    if chain_size > 0:
        total_size = chain_size
    elif total_size <= 0:
        total_size = round(sum(float(b.get("size") or 0) for b in buys), 4)

    spent = round(float(open_round.get("spent") or 0), 2)
    avg_price = round(spent / total_size, 4) if total_size > 0 else float(buys[-1].get("price") or 0)
    ts = int(buys[-1].get("timestamp") or time.time())
    entry_tr = datetime.fromtimestamp(ts, _TZ_TR)

    pos = {
        "symbol": _SYM_MAP.get(sym, f"{sym}USDT"),
        "predicted_dir": direction,
        "entry_price": _resolve_entry_price(_SYM_MAP.get(sym, f"{sym}USDT"), sibling),
        "entry_time_tr": entry_tr.isoformat(),
        "entry_hour_tr": entry_tr.hour,
        "entry_dow": entry_tr.weekday(),
        "entry_is_weekend": entry_tr.weekday() >= 5,
        "amount": spent,
        "pm_spent": spent,
        "pm_slug": slug,
        "pm_token_dir": direction,
        "pm_token_id": token_id,
        "pm_size": round(total_size, 2),
        "pm_entry_price": round(avg_price, 4),
        "pm_order_id": str(buys[-1].get("transactionHash") or ""),
        "pm_live": True,
        "synced_from_chain": True,
    }
    if sibling and (sibling.get("symbol") or "").upper() == pos["symbol"]:
        for k in ("signal_engine", "ind_rsi_val", "ema_fast", "ema_slow", "golden_cross"):
            if sibling.get(k) is not None:
                pos[k] = sibling[k]
    return pos


def _symbol_allowed(trader: str, symbol: str) -> bool:
    allowed = _TRADER_SYMBOLS.get(trader)
    if allowed is None:
        return True
    return symbol.upper() in allowed


def sync_live_orphan_positions(
    *,
    trader_keys: tuple[str, ...] | None = None,
    max_age_hours: int = 6,
    activity_limit: int = 200,
) -> dict:
    """Zincirde açık, state'te yok — uygun bot state'ine yazar."""
    keys = trader_keys or tuple(k for k in _TRADER_STATE if k != "manual")
    # Bilinen pozisyonlar TÜM live trader state'lerinden (çift yazmayı engelle)
    all_states = {k: _load_state(p) for k, p in _TRADER_STATE.items()}
    paths = {k: _TRADER_STATE[k] for k in keys if k in _TRADER_STATE}
    states = {k: all_states[k] for k in keys if k in all_states}
    known = _known_keys(all_states)
    known_tokens = _known_token_ids(all_states)

    acts = _fetch_activity(limit=activity_limit)
    _, open_rounds = _group_activity(acts)
    cutoff = time.time() - max_age_hours * 3600
    added: list[dict] = []

    for rnd in open_rounds:
        slug = rnd.get("slug") or ""
        sym = rnd.get("sym") or "?"
        symbol = _SYM_MAP.get(sym, f"{sym}USDT")
        key_tuple = (slug.lower(), symbol)
        if key_tuple in known:
            continue
        act_ts = int(rnd.get("act_ts") or 0)
        if act_ts < cutoff:
            continue
        # Bitmiş 15m slotları orphan diye ekleme
        if _15m_period_ts(slug) is not None and not _15m_period_open(slug):
            continue

        trader = _guess_trader(slug, all_states)
        if not trader or trader not in states:
            continue
        if not _symbol_allowed(trader, symbol):
            continue

        sibling = None
        slot = _hour_slot(slug)
        ts15 = _15m_period_ts(slug)
        for p in states[trader].get("open_positions") or []:
            ps = p.get("pm_slug") or ""
            if slot and _hour_slot(ps) == slot:
                sibling = p
                break
            if ts15 and _15m_period_ts(ps) == ts15:
                sibling = p
                break

        pos = _round_to_pos(rnd, acts, sibling)
        if not pos:
            continue
        if ts15:
            pos["ts_period"] = ts15
            pos["entry_period_min"] = (datetime.fromtimestamp(ts15, _TZ_TR).hour * 60
                                       + datetime.fromtimestamp(ts15, _TZ_TR).minute)

        tid = str(pos.get("pm_token_id") or "").strip()
        if tid and tid in known_tokens:
            continue

        states[trader].setdefault("open_positions", []).append(pos)
        known.add(key_tuple)
        if tid:
            known_tokens.add(tid)
        added.append({
            "trader": trader,
            "symbol": symbol,
            "dir": pos.get("predicted_dir"),
            "spent": pos.get("pm_spent"),
            "slug": slug[:48],
        })

    # Sadece değişen trader state'lerini yaz — stale full-rewrite mirror open
    # ile yarışınca (BTC açıkken SOL eklenmiş state'i ezer) pozisyon kaybolur.
    dirty: set[str] = {a["trader"] for a in added if a.get("trader")}
    repaired_keys = _repair_open_entries(states)
    dirty |= repaired_keys

    for key in dirty:
        path = paths.get(key) or _TRADER_STATE.get(key)
        if path and key in states:
            _save_state(path, states[key])

    return {
        "ok": True,
        "added": added,
        "added_count": len(added),
        "repaired_entries": len(repaired_keys),
    }


if __name__ == "__main__":
    import sys
    print(json.dumps(sync_live_orphan_positions(), ensure_ascii=False, indent=2))
