"""Sanal → gerçek 5M BTC sinyal senkronu (102→202)."""
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_TZ_TR = ZoneInfo("Europe/Istanbul")


def _path(key: str) -> str:
    return os.path.join(_DIR, f"poly_trader_5m_sync_{key}.json")


def save_signal(key: str, ts_5m: int, result: dict | None) -> None:
    payload = {
        "ts_5m": ts_5m,
        "saved_at_tr": datetime.now(timezone.utc).astimezone(_TZ_TR).isoformat(),
        "result": result,
    }
    with open(_path(key), "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load_signal(key: str, ts_5m: int, retries: int = 5, wait_sec: float = 2.0) -> dict | None:
    """Sanal trader sinyalini yükle; yoksa kısa süre bekleyip tekrar dene."""
    import time
    for attempt in range(retries):
        path = _path(key)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                if data.get("ts_5m") == ts_5m and data.get("result") is not None:
                    return data["result"]
            except Exception:
                pass
        if attempt < retries - 1:
            time.sleep(wait_sec)
    return None
