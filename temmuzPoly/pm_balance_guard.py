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
    "10. ANALİZ LIVE": "analiz10",
    "6. ANALİZ LIVE": "analiz6_live",
    "15M 309 LIVE": "15m_309_live",
    "A2#16 Supertrend Live": "a2_16_live",
    "A2#02 RSI Div Live": "a2_02_live",
    "A2#08 Williams Live": "a2_08_live",
    "A2#03 Stoch RSI Live": "a2_03_live",
    "A2#04 Schaff Live": "a2_04_live",
    "15. ANALİZ LIVE": "analiz15_live",
}
_VALID_GROUPS = frozenset({
    "analiz5", "analiz2", "analiz10", "analiz6_live", "15m_309_live",
    "a2_16_live", "a2_02_live", "a2_08_live", "a2_03_live", "a2_04_live", "analiz15_live",
})
# 15M 309 Live hafta sonu da çalışır — weekend cron bunu kapatmaz
_WEEKEND_GROUPS = (
    "analiz5", "analiz2", "analiz10", "analiz6_live",
    "a2_16_live", "a2_02_live", "a2_08_live", "a2_03_live", "a2_04_live", "analiz15_live",
)


def _load_control() -> dict:
    defaults = {
        "analiz5_paused": False,
        "analiz2_paused": False,
        "analiz10_paused": False,
        "analiz6_live_paused": True,
        "15m_309_live_paused": False,
        "a2_16_live_paused": True,
        "a2_02_live_paused": True,
        "a2_08_live_paused": True,
        "a2_03_live_paused": True,
        "a2_04_live_paused": True,
        "analiz15_live_paused": True,
        "a3a8_signal_strict": True,
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
    for k in ("hourly_paused", "pm_open_paused", "m15_210_paused", "pm_partial_tp_enabled",
              "pm_partial_tp_traders", "pm_partial_tp_profit_pct", "pm_partial_tp_sell_ratio"):
        data.pop(k, None)
    with open(_PM_CONTROL_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _label_group(label: str) -> str | None:
    if label in _LABEL_GROUPS:
        return _LABEL_GROUPS[label]
    up = (label or "").upper()
    for k, v in _LABEL_GROUPS.items():
        if k.upper() == up:
            return v
    return None


def is_live_pm_label(label: str) -> bool:
    """Dashboard anahtarı + hafta sonu duraklaması yalnızca bu label'lar için."""
    return _label_group(label) is not None


def is_group_paused(group: str) -> bool:
    c = _load_control()
    key = f"{group}_paused"
    if key in c:
        return bool(c.get(key))
    return False


def is_pm_open_paused() -> bool:
    """Geriye uyumluluk — tüm gruplar kapalıysa True."""
    return all(is_group_paused(g) for g in _VALID_GROUPS)


def get_pm_system_control() -> dict:
    c = _load_control()
    a5 = bool(c.get("analiz5_paused"))
    a2 = bool(c.get("analiz2_paused"))
    a10 = bool(c.get("analiz10_paused"))
    a6l = bool(c.get("analiz6_live_paused", True))
    m309 = bool(c.get("15m_309_live_paused", False))
    a2_16l = bool(c.get("a2_16_live_paused", True))
    a2_02l = bool(c.get("a2_02_live_paused", True))
    a2_08l = bool(c.get("a2_08_live_paused", True))
    a2_03l = bool(c.get("a2_03_live_paused", True))
    a2_04l = bool(c.get("a2_04_live_paused", True))
    a15l = bool(c.get("analiz15_live_paused", True))
    strict = bool(c.get("a3a8_signal_strict", True))
    all_paused = a5 and a2 and a10 and a6l and m309 and a2_16l and a2_02l and a2_08l and a2_03l and a2_04l and a15l
    return {
        "analiz5_paused": a5,
        "analiz2_paused": a2,
        "analiz10_paused": a10,
        "analiz6_live_paused": a6l,
        "15m_309_live_paused": m309,
        "a2_16_live_paused": a2_16l,
        "a2_02_live_paused": a2_02l,
        "a2_08_live_paused": a2_08l,
        "a2_03_live_paused": a2_03l,
        "a2_04_live_paused": a2_04l,
        "analiz15_live_paused": a15l,
        "a3a8_signal_strict": strict,
        "a3a8_signal_mode": "strict" if strict else "loose",
        "a3a8_signal_mode_label": "sıkı (filtreli)" if strict else "gevşek (her saat)",
        "hourly_paused": all_paused,
        "pm_open_paused": all_paused,
        "updated_at_tr": c.get("updated_at_tr") or "",
        "updated_by": c.get("updated_by") or "",
    }


def set_a3a8_signal_strict(strict: bool, *, source: str = "dashboard") -> dict:
    data = _load_control()
    data["a3a8_signal_strict"] = bool(strict)
    data["updated_at_tr"] = datetime.now(_TZ_TR).isoformat()
    data["updated_by"] = source
    _save_control(data)
    return get_pm_system_control()


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
    data = _load_control()
    for g in _WEEKEND_GROUPS:
        data[f"{g}_paused"] = bool(paused)
    data["updated_at_tr"] = datetime.now(_TZ_TR).isoformat()
    data["updated_by"] = source
    _save_control(data)
    return get_pm_system_control()


_WEEKEND_EARLY_GROUPS = ("analiz6_live", "a2_16_live", "analiz15_live")  # Pzt 11:00
_WEEKEND_LATE_GROUPS = ("analiz5", "analiz2", "analiz10")  # A1/A2/A10 — Pzt 12:00


def weekend_pause_all(*, source: str = "weekend_cron") -> dict:
    """Cuma 22:00 — dashboard anahtarlarını kapat (A1+A2+A10 + diğerleri)."""
    return set_pm_open_paused(True, source=source)


def weekend_resume_early(*, source: str = "weekend_cron") -> dict:
    """Pazartesi 11:00 — A1/A2/A10 hariç weekend gruplarını aç."""
    data = _load_control()
    for g in _WEEKEND_EARLY_GROUPS:
        data[f"{g}_paused"] = False
    data["updated_at_tr"] = datetime.now(_TZ_TR).isoformat()
    data["updated_by"] = source
    _save_control(data)
    return get_pm_system_control()


def weekend_resume_a1a2a10(*, source: str = "weekend_cron") -> dict:
    """Pazartesi 12:00 — A1 Live + A2 Live + A10 Live aç."""
    data = _load_control()
    for g in _WEEKEND_LATE_GROUPS:
        data[f"{g}_paused"] = False
    data["updated_at_tr"] = datetime.now(_TZ_TR).isoformat()
    data["updated_by"] = source
    _save_control(data)
    return get_pm_system_control()


def weekend_resume_all(*, source: str = "weekend_cron") -> dict:
    """Tüm weekend gruplarını aç (manuel / geriye uyumluluk)."""
    return set_pm_open_paused(False, source=source)


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
