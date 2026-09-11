"""REF06 — saat başında coin bazında en yüksek WR'li defteri seç.

B1#05 ile aynı aday havuzu; fark: eşleme yalnız saat değiştiğinde yenilenir.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from b1_05_signal import (
    TARGET_SYMS,
    book_label,
    compute_best_mapping,
    resolve_from_book,
)

_DIR = os.path.dirname(os.path.abspath(__file__))
_PICK_FILE = os.path.join(_DIR, "ref06_wr_hour_pick.json")
_TZ_TR = ZoneInfo("Europe/Istanbul")


def hour_key(now_tr: datetime | None = None) -> str:
    t = now_tr or datetime.now(_TZ_TR)
    return t.strftime("%Y-%m-%d %H")


def _load_cache() -> dict:
    if not os.path.exists(_PICK_FILE):
        return {}
    try:
        with open(_PICK_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    try:
        with open(_PICK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[REF06] wr pick yazılamadı: {e}")


def ensure_hour_mapping(now_tr: datetime | None = None) -> dict[str, dict]:
    """Saat başında (ilk open turunda) WR en yüksek defteri coin bazında seç."""
    t = now_tr or datetime.now(_TZ_TR)
    hk = hour_key(t)
    cached = _load_cache()
    if cached.get("hour_key") == hk and isinstance(cached.get("mapping"), dict):
        return cached["mapping"]

    mapping = compute_best_mapping()
    _save_cache({
        "hour_key": hk,
        "picked_at_tr": t.isoformat(),
        "mapping": mapping,
        "symbols": TARGET_SYMS,
    })
    picks = ", ".join(
        f"{sym}←{mapping[sym]['label']} %{mapping[sym]['wr']}"
        for sym in TARGET_SYMS if sym in mapping
    )
    print(f"[REF06] saat {hk} İST WR seçimi: {picks or 'yok'}")
    return mapping


def pick_for_symbol(symbol: str, now_tr: datetime | None = None) -> dict | None:
    sym = symbol.replace("USDT", "")
    if sym not in TARGET_SYMS:
        return None
    return ensure_hour_mapping(now_tr).get(sym)


async def resolve_confirmation(
    symbol: str, now_tr: datetime | None = None,
) -> tuple[str | None, dict]:
    """Seçilen defterin canlı yönü — None = nötr / eşleme yok."""
    row = pick_for_symbol(symbol, now_tr)
    if not row:
        return None, {}
    direction, _, algo = await resolve_from_book(row["book"], symbol)
    meta = {
        "book": row["book"],
        "label": row.get("label") or book_label(row["book"]),
        "wr": row.get("wr"),
        "w": row.get("w"),
        "t": row.get("t"),
        "algo": algo,
        "hour_key": hour_key(now_tr),
    }
    return direction if direction in ("UP", "DOWN") else None, meta
