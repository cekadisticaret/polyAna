"""B1#01 — algoritma-islemler defterlerinden sembol bazlı en iyi motor birleşimi."""
from __future__ import annotations

import asyncio
import json
import os
import re
from collections import defaultdict

from algo_signals import fetch_klines as _algo_fetch_klines
from algo_signals_v2 import ALGO_V2_META
from analiz15_signal import resolve_live_signal as a15_resolve
from analiz6_v3_signal import resolve_live_signal as a6v3_resolve

_DIR = os.path.dirname(os.path.abspath(__file__))
_MAPPING_FILE = os.path.join(_DIR, "b1_01_mapping.json")
_MIN_TRADES = 5
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

_A2_BY_KEY = {f"a2_{num:02d}": num for num, *_ in ALGO_V2_META}


def algo_islemler_source_keys() -> list[str]:
    keys = ["analiz6", "analiz6_v2", "analiz6_v3", "analiz15"]
    keys.extend(sorted(_A2_BY_KEY))
    return keys


def _history_path(key: str) -> str:
    return os.path.join(_DIR, f"poly_trader_{key}_history.json")


def _load_history(key: str) -> list:
    path = _history_path(key)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def compute_best_mapping(min_trades: int = _MIN_TRADES) -> dict[str, dict]:
    """{BTC: {book, wr, w, t, label}, ...}"""
    target_syms = ["BTC", "ETH", "SOL"]
    best: dict[str, dict] = {}
    for key in algo_islemler_source_keys():
        hist = _load_history(key)
        if not hist:
            continue
        buckets: dict[str, dict] = defaultdict(lambda: {"w": 0, "t": 0})
        for t in hist:
            sym = (t.get("symbol") or "").replace("USDT", "")
            if sym not in target_syms:
                continue
            buckets[sym]["t"] += 1
            if t.get("win"):
                buckets[sym]["w"] += 1
        label = key
        if m := re.match(r"^a2_(\d+)$", key):
            label = f"A2#{int(m.group(1)):02d}"
        elif key == "analiz6":
            label = "A6"
        elif key == "analiz6_v2":
            label = "A6V2"
        elif key == "analiz6_v3":
            label = "A6V3"
        elif key == "analiz15":
            label = "A15"
        for sym, v in buckets.items():
            if v["t"] < min_trades:
                continue
            wr = round(v["w"] / v["t"] * 100, 1)
            prev = best.get(sym)
            if prev is None or wr > prev["wr"] or (wr == prev["wr"] and v["t"] > prev["t"]):
                best[sym] = {
                    "book": key,
                    "label": label,
                    "wr": wr,
                    "w": v["w"],
                    "t": v["t"],
                }
    return best


def save_mapping(mapping: dict[str, dict]) -> None:
    with open(_MAPPING_FILE, "w", encoding="utf-8") as f:
        json.dump({"mapping": mapping, "keys": algo_islemler_source_keys()}, f, indent=2, ensure_ascii=False)


def load_mapping(refresh: bool = True) -> dict[str, dict]:
    if refresh or not os.path.exists(_MAPPING_FILE):
        mapping = compute_best_mapping()
        save_mapping(mapping)
        return mapping
    try:
        with open(_MAPPING_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("mapping") or {}
    except Exception:
        return compute_best_mapping()


async def _resolve_from_book(book: str, symbol: str) -> tuple[str | None, float | None, str]:
    if book == "analiz15":
        return await a15_resolve(symbol)
    if book == "analiz6_v3":
        return await a6v3_resolve(symbol)
    if book == "analiz6_v2":
        from poly_trader_analiz6_v2 import _resolve_signal
        return await _resolve_signal(symbol)
    if book == "analiz6":
        from poly_trader_analiz6 import _resolve_signal
        return await _resolve_signal(symbol)
    m = re.match(r"^a2_(\d+)$", book)
    if m:
        algo_num = int(m.group(1))
        sig_path = "/tmp/algo_signals_v2.json"
        sym_short = symbol.replace("USDT", "")
        algo_name = f"A2#{algo_num:02d}"
        if os.path.exists(sig_path):
            try:
                with open(sig_path, encoding="utf-8") as f:
                    data = json.load(f)
                entry = (data.get("signals") or {}).get(str(algo_num)) or {}
                sig = entry.get(sym_short)
                if sig in ("UP", "DOWN"):
                    kl = await asyncio.to_thread(_algo_fetch_klines, symbol, "1h", 5)
                    price = float(kl[-1]["c"]) if kl else None
                    for num, name, *_ in ALGO_V2_META:
                        if num == algo_num:
                            algo_name = name
                            break
                    return sig, price, algo_name
            except Exception:
                pass
        for num, name, _cat, kind, fn in ALGO_V2_META:
            if num != algo_num or kind != "fn" or not fn:
                continue
            kl = await asyncio.to_thread(_algo_fetch_klines, symbol, "1h", 80)
            if len(kl) < 30:
                return None, None, name
            sig = fn(kl)
            price = float(kl[-1]["c"])
            if sig in ("UP", "DOWN"):
                return sig, price, name
            return None, price, name
    return None, None, book


def engine_label(symbol: str) -> str:
    mapping = load_mapping(refresh=False)
    sym = symbol.replace("USDT", "")
    row = mapping.get(sym)
    if row:
        return f"B1←{row.get('label', row.get('book', '?'))}"
    return "B1#01"


async def resolve_live_signal(symbol: str) -> tuple[str | None, float | None, str]:
    mapping = load_mapping(refresh=True)
    sym = symbol.replace("USDT", "")
    row = mapping.get(sym)
    if not row:
        return await a6v3_resolve(symbol)
    book = row["book"]
    sig, price, algo_name = await _resolve_from_book(book, symbol)
    src = row.get("label") or book
    return sig, price, f"B1←{src} · {algo_name}"
