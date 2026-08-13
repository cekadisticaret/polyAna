"""B1#05 — coin başına en iyi motor; aday havuzunda B1#03 MUM ve MELEZ de var.

B1#01 ile aynı fikir (her sembol için en yüksek WR'li defterin sinyalini al),
iki farkla:

1. Aday havuzuna **b1_mum** ve **melez** eklendi. Dashboard'daki "Sembol Başarı
   Oranı · coin başına en iyi" kartı bu geniş havuzu kullanıyor; B1#01'in havuzu
   B1 defterlerini dışarıda bıraktığı için kart ETH'de B1#03 MUM derken B1#01 A6
   diyordu. B1#05 kartla aynı sonucu üretir.

2. Türev defterler havuza girmez: b1_01 / b1_02 / b1_04 / b1_05 başka
   defterlerin sinyalini aynalar, analiz2 ise analiz1 ile aynı `predict()`
   tabanını kullanır (çift sayma). Kendi kendini kovalayan bir defter olmasın.

Eşleme her `open` turunda geçmişten yeniden hesaplanır, `b1_05_mapping.json`'a
yazılır — yani en iyi motor değiştikçe B1#05 de takip eder.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict

from algo_signals_v2 import ALGO_V2_META

_DIR = os.path.dirname(os.path.abspath(__file__))
_MAPPING_FILE = os.path.join(_DIR, "b1_05_mapping.json")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TARGET_SYMS = ["BTC", "ETH", "SOL"]

# Bir defterin bir coin'de aday olabilmesi için asgari kapanmış işlem.
# Kart da 5 kullanıyor (poly_dashboard._best_analiz_by_symbol min_trades=5).
_MIN_TRADES = 5

# Türev / çift sayan defterler — havuz dışı
EXCLUDED_KEYS = ("b1_01", "b1_02", "b1_04", "b1_05", "analiz2")

# history dosyası defter anahtarıyla aynı olmayanlar
_HISTORY_ALIASES = {"melez": "analiz6_v4"}

_LABELS = {
    "analiz1": "A1",
    "analiz6": "A6",
    "analiz6_v2": "A6V2",
    "analiz6_v3": "A6V3",
    "analiz15": "A15",
    "melez": "MELEZ",
    "b1_mum": "B1#03 MUM",
}


def source_keys() -> list[str]:
    """B1#05'in bakacağı defterler — birincil motorlar."""
    keys = ["analiz1", "analiz6", "analiz6_v2", "analiz6_v3", "analiz15", "melez", "b1_mum"]
    keys.extend(f"a2_{num:02d}" for num, *_ in ALGO_V2_META)
    return [k for k in keys if k not in EXCLUDED_KEYS]


def book_label(key: str) -> str:
    if m := re.match(r"^a2_(\d+)$", key):
        return f"A2#{int(m.group(1)):02d}"
    return _LABELS.get(key, key)


def _history_path(key: str) -> str:
    return os.path.join(_DIR, f"poly_trader_{_HISTORY_ALIASES.get(key, key)}_history.json")


def _load_history(key: str) -> list:
    path = _history_path(key)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def compute_best_mapping(min_trades: int = _MIN_TRADES) -> dict[str, dict]:
    """{BTC: {book, label, wr, w, t}, ...} — coin başına en yüksek WR."""
    best: dict[str, dict] = {}
    for key in source_keys():
        hist = _load_history(key)
        if not hist:
            continue
        buckets: dict[str, dict] = defaultdict(lambda: {"w": 0, "t": 0})
        for t in hist:
            sym = (t.get("symbol") or "").replace("USDT", "")
            if sym not in TARGET_SYMS or t.get("win") is None:
                continue
            buckets[sym]["t"] += 1
            if t.get("win"):
                buckets[sym]["w"] += 1
        for sym, v in buckets.items():
            if v["t"] < min_trades:
                continue
            wr = round(v["w"] / v["t"] * 100, 1)
            prev = best.get(sym)
            # eşitlikte daha çok işlem görmüş defter kazanır
            if prev is None or wr > prev["wr"] or (wr == prev["wr"] and v["t"] > prev["t"]):
                best[sym] = {"book": key, "label": book_label(key),
                             "wr": wr, "w": v["w"], "t": v["t"]}
    return best


def save_mapping(mapping: dict[str, dict]) -> None:
    try:
        with open(_MAPPING_FILE, "w", encoding="utf-8") as f:
            json.dump({"mapping": mapping, "min_trades": _MIN_TRADES,
                       "keys": source_keys()}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[B1#05] mapping yazılamadı: {e}")


def load_mapping(refresh: bool = True) -> dict[str, dict]:
    if refresh or not os.path.exists(_MAPPING_FILE):
        mapping = compute_best_mapping()
        save_mapping(mapping)
        return mapping
    try:
        with open(_MAPPING_FILE, encoding="utf-8") as f:
            return (json.load(f).get("mapping")) or {}
    except Exception:
        return compute_best_mapping()


async def resolve_from_book(book: str, symbol: str) -> tuple[str | None, float | None, str]:
    """Defterin şu anki canlı yönü — mevcut sinyal modülleri değiştirilmeden."""
    if book == "melez":
        from analiz6_v4_signal import resolve_live_signal as melez_resolve
        return await melez_resolve(symbol)
    # b1_mum / analiz1 / analiz6* / analiz15 / a2_xx hepsi burada çözülür
    from b1_04_signal import _signal_from_book
    return await _signal_from_book(book, symbol)


def engine_label(symbol: str = "") -> str:
    row = load_mapping(refresh=False).get(symbol.replace("USDT", ""))
    return f"B1#05←{row['label']}" if row else "B1#05"


async def resolve_live_signal(symbol: str) -> tuple[str | None, float | None, str]:
    mapping = load_mapping(refresh=True)
    row = mapping.get(symbol.replace("USDT", ""))
    if not row:
        print(f"[B1#05] {symbol} — yeterli geçmişi olan defter yok, işlem yok")
        return None, None, "eşleme yok"
    sig, price, algo_name = await resolve_from_book(row["book"], symbol)
    return sig, price, f"B1#05←{row['label']} · {algo_name}"
