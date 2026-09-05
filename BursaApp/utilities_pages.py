"""Su / elektrik / doğalgaz ve teleferik JSON yükleyicileri."""
from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any

_DIR = os.path.dirname(os.path.abspath(__file__))


def _read(path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    try:
        return json.loads(open(path, encoding="utf-8").read())
    except Exception:
        return {}


def load_utilities() -> dict[str, Any]:
    path = os.path.join(_DIR, "data", "utilities.json")
    if not os.path.isfile(path):
        seed = os.path.join(_DIR, "data", "utilities_seed.json")
        return _read(seed)
    return _read(path)


def load_teleferik() -> dict[str, Any]:
    path = os.path.join(_DIR, "data", "teleferik.json")
    if not os.path.isfile(path):
        seed = os.path.join(_DIR, "data", "teleferik_seed.json")
        return _read(seed)
    return _read(path)


def branches_by_ilce(branches: list[dict] | None) -> list[dict]:
    groups: dict[str, list] = defaultdict(list)
    for b in branches or []:
        ilce = (b.get("ilce") or "Diğer").strip()
        groups[ilce].append(b)
    return [{"ilce": k, "rows": v} for k, v in sorted(groups.items(), key=lambda x: x[0])]


def fmt_tl(val: float | int | None) -> str:
    if val is None:
        return "—"
    if isinstance(val, float) and val == int(val):
        val = int(val)
    s = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if s.endswith(",00"):
        s = s[:-3]
    return s
