"""Polymarket USDC bakiye + dashboard sistem anahtarı (açılış engeli)."""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

_PM_CLOB_HOST = "https://clob.polymarket.com"
_DIR = os.path.dirname(os.path.abspath(__file__))
_PM_CONTROL_FILE = os.path.join(_DIR, "pm_system_control.json")
_TZ_TR = timezone(timedelta(hours=3))

_LABEL_GROUPS = {
    "A1 LIVE": "analiz5",
    "5. ANALİZ": "analiz5",  # geriye uyumluluk
    "2. ANALİZ LIVE": "analiz2",
    "15M 210 SOL": "m15_210",
}
_VALID_GROUPS = frozenset({"analiz5", "analiz2", "m15_210"})


def _load_control() -> dict:
    defaults = {
        "analiz5_paused": False,
        "analiz2_paused": False,
        "m15_210_paused": False,
        "updated_at_tr": "",
        "updated_by": "",
    }
    if not os.path.exists(_PM_CONTROL_FILE):
        return defaults
    try:
        with open(_PM_CONTROL_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            # Eski tek anahtar
            if "pm_open_paused" in data and "analiz5_paused" not in data:
                legacy = bool(data.get("pm_open_paused"))
                data["analiz5_paused"] = legacy
                data["analiz2_paused"] = legacy
                data["m15_210_paused"] = legacy
            # hourly_paused → A1 Live + A2
            if "hourly_paused" in data and "analiz5_paused" not in data:
                h = bool(data.get("hourly_paused"))
                data["analiz5_paused"] = h
                data["analiz2_paused"] = h
            defaults.update(data)
    except Exception:
        pass
    return defaults


def _save_control(data: dict) -> None:
    for k in ("hourly_paused", "pm_open_paused"):
        data.pop(k, None)
    with open(_PM_CONTROL_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _label_group(label: str) -> str | None:
    return _LABEL_GROUPS.get(label)


def is_group_paused(group: str) -> bool:
    c = _load_control()
    key = f"{group}_paused"
    if key in c:
        return bool(c.get(key))
    return False


def is_pm_open_paused() -> bool:
    """Geriye uyumluluk — hepsi kapalıysa True."""
    c = _load_control()
    return bool(c.get("analiz5_paused")) and bool(c.get("analiz2_paused")) and bool(c.get("m15_210_paused"))


def get_pm_system_control() -> dict:
    c = _load_control()
    a5 = bool(c.get("analiz5_paused"))
    a2 = bool(c.get("analiz2_paused"))
    m15 = bool(c.get("m15_210_paused"))
    return {
        "analiz5_paused": a5,
        "analiz2_paused": a2,
        "m15_210_paused": m15,
        "hourly_paused": a5 and a2,
        "pm_open_paused": a5 and a2 and m15,
        "updated_at_tr": c.get("updated_at_tr") or "",
        "updated_by": c.get("updated_by") or "",
    }


def set_group_paused(group: str, paused: bool, *, source: str = "dashboard") -> dict:
    if group not in _VALID_GROUPS:
        raise ValueError(f"bilinmeyen grup: {group}")
    data = _load_control()
    data[f"{group}_paused"] = bool(paused)
    data["updated_at_tr"] = datetime.now(_TZ_TR).isoformat()
    data["updated_by"] = source
    _save_control(data)
    return get_pm_system_control()


def toggle_group_paused(group: str, *, source: str = "dashboard") -> dict:
    return set_group_paused(group, not is_group_paused(group), source=source)


def set_pm_open_paused(paused: bool, *, source: str = "dashboard") -> dict:
    """Geriye uyumluluk — üçünü birlikte ayarla."""
    data = {
        "analiz5_paused": bool(paused),
        "analiz2_paused": bool(paused),
        "m15_210_paused": bool(paused),
        "updated_at_tr": datetime.now(_TZ_TR).isoformat(),
        "updated_by": source,
    }
    _save_control(data)
    return get_pm_system_control()


def toggle_pm_open_paused(*, source: str = "dashboard") -> dict:
    all_paused = all(is_group_paused(g) for g in _VALID_GROUPS)
    return set_pm_open_paused(not all_paused, source=source)


def get_usdc_balance() -> float:
    """Polymarket USDC bakiyesi. Hata durumunda 9999 döner."""
    try:
        from py_clob_client_v2 import ClobClient
        from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
        pk     = os.getenv("POLY_PRIVATE_KEY", "")
        funder = os.getenv("POLY_FUNDER", "")
        temp   = ClobClient(host=_PM_CLOB_HOST, chain_id=137, key=pk)
        creds  = temp.create_or_derive_api_key()
        client = ClobClient(
            host=_PM_CLOB_HOST, chain_id=137, key=pk,
            creds=creds, signature_type=1, funder=funder,
        )
        result = client.get_balance_allowance(
            BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        )
        return int(result.get("balance", 0)) / 1_000_000
    except Exception as e:
        print(f"[PM BALANCE] Bakiye sorgulanamadı: {e}", file=sys.stderr)
        return 9999.0


def can_open_trade(label: str, tg_send=None) -> bool:
    """Yeni PM açılışı — dashboard grup anahtarı kapalıysa engelle."""
    group = _label_group(label)
    if group is None:
        return True
    if is_group_paused(group):
        print(f"[PM SYSTEM] {label} — açılış kapalı ({group})", file=sys.stderr)
        return False
    return True
