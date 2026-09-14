"""2.Poly bootstrap — tamamen bağımsız (temmuzPoly yok)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "lib"
DATA = ROOT / "data"
CONFIG = ROOT / "config"

_initialized = False


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def init() -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    DATA.mkdir(parents=True, exist_ok=True)
    CONFIG.mkdir(parents=True, exist_ok=True)
    _load_dotenv(ROOT / ".env")

    lib = str(LIB)
    if lib not in sys.path:
        sys.path.insert(0, lib)

    # Telegram sanal bildirimleri varsayılan kapalı
    if os.getenv("POLY2_TG_ENABLED", "false").lower() not in ("1", "true", "yes"):
        import sanal_core

        sanal_core.tg_send_for_cfg = lambda _cfg, _text: None  # type: ignore[method-assign]
        sanal_core.tg_send = lambda _text: None  # type: ignore[method-assign]


def sanal_config():
    init()
    from sanal_core import A2Config

    return A2Config(
        algo_num=5,
        key="a2_05",
        label="A2#05 Mean Reversion (2.Poly)",
        algo_name="Mean Reversion (Z-Score)",
        state_file=str(DATA / "poly_trader_a2_05_state.json"),
        history_file=str(DATA / "poly_trader_a2_05_history.json"),
    )


def live_spec():
    init()
    from live_core import A2LiveSpec

    return A2LiveSpec(
        algo_num=5,
        algo_name="Mean Reversion (Z-Score)",
        label="A2#05 Mean Rev Live",
        amount_system="a2_05",
        env_flag="PM_A2_05_LIVE_ENABLED",
        default_amount=5.0,
    )
