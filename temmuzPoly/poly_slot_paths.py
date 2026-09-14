"""Açılış dakikası dilimleri — :02 (mevcut) · :05 / :07 (kopya defterler).

Dosya kuralı: `poly_trader_c101_state.json` → `poly_trader_c101_t05_state.json`.
:02 yolları değişmez. Ayna API seçimi `mirror_slot.json`.
"""
from __future__ import annotations

import json
import os
import re
import tempfile

_DIR = os.path.dirname(os.path.abspath(__file__))

SLOT_MINUTES = (2, 5, 7)
COPY_SLOTS = (5, 7)
DEFAULT_MIRROR_SLOT = 5
SLOT_INIT_BAL = 1000.0
MIRROR_SLOT_FILE = os.path.join(_DIR, "mirror_slot.json")

_SLOT_KEY_RE = re.compile(r"_t0[57]$")


def parse_slot(raw) -> int:
    """'05' / 5 / ':07' → 2 | 5 | 7."""
    s = str(raw or "").strip().lstrip(":")
    if s in ("02", "2"):
        return 2
    if s in ("05", "5"):
        return 5
    if s in ("07", "7"):
        return 7
    raise ValueError(f"geçersiz dilim: {raw!r} (02/05/07)")


def slot_tag(slot: int) -> str:
    n = parse_slot(slot)
    return "" if n == 2 else f"t{n:02d}"


def with_slot_tag(path: str, slot: int) -> str:
    """`…_state.json` / `…_history.json` arasına `_t05` ekle. :02 = aynı yol."""
    n = parse_slot(slot)
    if n == 2 or not path:
        return path
    tag = f"_t{n:02d}"
    for suffix in ("_state.json", "_history.json"):
        if path.endswith(suffix):
            stem = path[: -len(suffix)]
            if stem.endswith(tag):
                return path
            return stem + tag + suffix
    root, ext = os.path.splitext(path)
    if root.endswith(tag):
        return path
    return f"{root}{tag}{ext}"


def is_slot_copy_key(key: str) -> bool:
    """Keşif listelerine `c101_t05` karışmasın."""
    return bool(_SLOT_KEY_RE.search(key or ""))


def _atomic_write(path: str, data: dict) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".mirror_slot.", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def default_mirror_cfg() -> dict:
    return {"default": DEFAULT_MIRROR_SLOT, "books": {}}


def load_mirror_slot_cfg() -> dict:
    cfg = default_mirror_cfg()
    if not os.path.exists(MIRROR_SLOT_FILE):
        return cfg
    try:
        with open(MIRROR_SLOT_FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return cfg
    if not isinstance(raw, dict):
        return cfg
    try:
        cfg["default"] = parse_slot(raw.get("default", DEFAULT_MIRROR_SLOT))
    except ValueError:
        cfg["default"] = DEFAULT_MIRROR_SLOT
    books = raw.get("books") or {}
    if isinstance(books, dict):
        out = {}
        for k, v in books.items():
            try:
                out[str(k)] = parse_slot(v)
            except ValueError:
                continue
        cfg["books"] = out
    return cfg


def get_mirror_slot(book: str | None = None) -> int:
    cfg = load_mirror_slot_cfg()
    if book:
        keyed = (cfg.get("books") or {}).get(book)
        if keyed in SLOT_MINUTES:
            return int(keyed)
    return int(cfg.get("default") or DEFAULT_MIRROR_SLOT)


def save_mirror_slot(*, default: int | None = None, book: str | None = None,
                     slot: int | None = None) -> dict:
    cfg = load_mirror_slot_cfg()
    if default is not None:
        cfg["default"] = parse_slot(default)
    if book is not None:
        if slot is None:
            raise ValueError("defter için slot gerekli")
        cfg.setdefault("books", {})[book] = parse_slot(slot)
    _atomic_write(MIRROR_SLOT_FILE, cfg)
    return cfg


def ensure_mirror_slot_file() -> dict:
    if not os.path.exists(MIRROR_SLOT_FILE):
        cfg = default_mirror_cfg()
        _atomic_write(MIRROR_SLOT_FILE, cfg)
        return cfg
    return load_mirror_slot_cfg()
