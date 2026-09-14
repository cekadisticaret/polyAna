"""A2#05 Mean Reversion — uygulama bootstrap."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
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


def _ensure_paths() -> None:
    for sub in ("algo", "trading"):
        p = str(SRC / sub)
        if p not in sys.path:
            sys.path.insert(0, p)
    src = str(SRC)
    if src not in sys.path:
        sys.path.insert(0, src)


def init() -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    DATA.mkdir(parents=True, exist_ok=True)
    CONFIG.mkdir(parents=True, exist_ok=True)
    _load_dotenv(ROOT / ".env")
    _load_dotenv(CONFIG / ".env")
    _load_dotenv(CONFIG / "secrets.env")
    _ensure_paths()

    if os.getenv("TG_ENABLED", os.getenv("POLY2_TG_ENABLED", "false")).lower() not in ("1", "true", "yes"):
        from paper_trader import disable_telegram

        disable_telegram()


def paper_config():
    init()
    from paper_trader import PaperConfig

    return PaperConfig(
        algo_num=5,
        key="a2_05",
        label="A2#05 Mean Reversion",
        algo_name="Mean Reversion (Z-Score)",
        state_file=str(DATA / "paper_state.json"),
        history_file=str(DATA / "paper_history.json"),
    )


def live_spec():
    init()
    from live_trader import LiveSpec

    return LiveSpec(
        algo_num=5,
        algo_name="Mean Reversion (Z-Score)",
        label="A2#05 Mean Rev Live",
        amount_system="a2_05",
        env_flag="PM_A2_05_LIVE_ENABLED",
        default_amount=5.0,
    )
