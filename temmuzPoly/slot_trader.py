#!/usr/bin/env python3
""":05 / :07 sanal kopyalar — aynı defterler (A1/A2/F1 + standalone), ayrı state/history.

Kullanım:
  python3 slot_trader.py close --slot 05
  python3 slot_trader.py open  --slot 07
  python3 slot_trader.py close --slot 05 --book c101

Mevcut :02 defterlere dokunmaz. Live ayna kapalı. Manuel open yok — cron açar.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import subprocess
import sys
from dataclasses import replace

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from poly_slot_paths import (  # noqa: E402
    COPY_SLOTS,
    SLOT_INIT_BAL,
    parse_slot,
    with_slot_tag,
)

# algo_islemler_fresh_start._STANDALONE_CLOSE + betik eşlemesi
_STANDALONE: dict[str, str] = {
    "analiz1": "poly_trader_analiz1",
    "analiz2": "poly_trader_analiz2",
    "analiz6": "poly_trader_analiz6",
    "analiz6_v2": "poly_trader_analiz6_v2",
    "analiz6_v3": "poly_trader_analiz6_v3",
    "analiz15": "poly_trader_analiz15",
    "b1_01": "poly_trader_b1_01",
    "b1_02": "poly_trader_b1_02",
    "b1_mum": "poly_trader_b1_mum",
    "b1_04": "poly_trader_b1_04",
    "b1_05": "poly_trader_b1_05",
    "melez": "poly_trader_analiz6_v4",
    "c101": "poly_trader_c101",
    "c101_v2": "poly_trader_c101_v2",
    "x101": "poly_trader_x101",
    "combo": "poly_trader_e01",
    "combo2": "poly_trader_e02",
    "a2_05_v2": "poly_trader_a2_05_v2",
}
_A1_BATCH = "a1"
_A2_BATCH = "a2"
_F1_BATCH = "f1"
_BOOK_ORDER = list(_STANDALONE) + [_A1_BATCH, _A2_BATCH, _F1_BATCH]


def _silence_telegram() -> None:
    """Kopya dilimler ölçüm defteri — :02 TG'yi ikiye katlamasın."""
    try:
        import telegram_poly_channels as tg
    except Exception:
        return

    def _empty() -> str:
        return ""

    for name in (
        "chat_analiz1", "chat_poly_traders", "chat_pm_live",
        "chat_analiz4", "chat_analiz9", "chat_analiz10",
    ):
        if hasattr(tg, name):
            setattr(tg, name, _empty)


def _remap_path_attr(obj, name: str, slot: int) -> None:
    val = getattr(obj, name, None)
    if isinstance(val, str) and val:
        setattr(obj, name, with_slot_tag(val, slot))


def _remap_module(mod, slot: int) -> None:
    for name in ("STATE_FILE", "HISTORY_FILE", "CALIB_FILE"):
        _remap_path_attr(mod, name, slot)
    if hasattr(mod, "INITIAL_BALANCE"):
        try:
            setattr(mod, "INITIAL_BALANCE", SLOT_INIT_BAL)
        except Exception:
            pass
    base = getattr(mod, "base", None)
    if base is not None and base is not mod:
        _remap_module(base, slot)


def _call_run(mod, mode: str) -> None:
    modes = getattr(mod, "_MODES", None)
    fn = None
    if isinstance(modes, dict):
        fn = modes.get(mode)
    if fn is None:
        fn = getattr(mod, f"run_{mode}", None)
    if fn is None:
        base = getattr(mod, "base", None)
        if base is not None:
            fn = getattr(base, f"run_{mode}", None)
    if fn is None:
        raise RuntimeError(f"{mod.__name__}: run_{mode} yok")
    if asyncio.iscoroutinefunction(fn):
        asyncio.run(fn())
    else:
        fn()


def _run_a1_batch(mode: str, slot: int) -> None:
    from poly_trader_a1 import ALL_CONFIGS, run_mode
    cfgs = [
        replace(
            c,
            state_file=with_slot_tag(c.state_file, slot),
            history_file=with_slot_tag(c.history_file, slot),
            live_mirror=False,
            init_balance=SLOT_INIT_BAL,
        )
        for c in ALL_CONFIGS
    ]
    asyncio.run(run_mode(mode, cfgs))


def _run_a2_batch(mode: str, slot: int) -> None:
    from poly_a2_algo_trader_core import ALL_CONFIGS, run_mode
    cfgs = [
        replace(
            c,
            state_file=with_slot_tag(c.state_file, slot),
            history_file=with_slot_tag(c.history_file, slot),
            live_mirror=False,
            init_balance=SLOT_INIT_BAL,
        )
        for c in ALL_CONFIGS
    ]
    asyncio.run(run_mode(mode, cfgs))


def _run_f1_batch(mode: str, slot: int) -> None:
    from poly_trader_f1 import ALL_CONFIGS, run_mode
    cfgs = [
        replace(
            c,
            state_file=with_slot_tag(c.state_file, slot),
            history_file=with_slot_tag(c.history_file, slot),
            live_mirror=False,
            init_balance=SLOT_INIT_BAL,
        )
        for c in ALL_CONFIGS
    ]
    asyncio.run(run_mode(mode, cfgs))


def _run_a2_05_v2(mode: str, slot: int) -> None:
    from poly_a2_algo_trader_core import run_mode
    import poly_trader_a2_05_v2 as mod
    cfg = replace(
        mod.CONFIG,
        state_file=with_slot_tag(mod.CONFIG.state_file, slot),
        history_file=with_slot_tag(mod.CONFIG.history_file, slot),
        shadow_log=with_slot_tag(mod.CONFIG.shadow_log, slot) if mod.CONFIG.shadow_log else None,
        live_mirror=False,
        init_balance=SLOT_INIT_BAL,
    )
    asyncio.run(run_mode(mode, [cfg]))


def run_book(book: str, mode: str, slot: int) -> None:
    _silence_telegram()
    if book == _A1_BATCH:
        print(f"[slot :{slot:02d}] A1 Top-34 {mode}", flush=True)
        _run_a1_batch(mode, slot)
        return
    if book == _A2_BATCH:
        print(f"[slot :{slot:02d}] A2 Top-17 {mode}", flush=True)
        _run_a2_batch(mode, slot)
        return
    if book == _F1_BATCH:
        print(f"[slot :{slot:02d}] F1-01…07 {mode}", flush=True)
        _run_f1_batch(mode, slot)
        return
    if book == "a2_05_v2":
        print(f"[slot :{slot:02d}] a2_05_v2 {mode}", flush=True)
        _run_a2_05_v2(mode, slot)
        return
    mod_name = _STANDALONE.get(book)
    if not mod_name:
        raise SystemExit(f"bilinmeyen defter: {book}")
    print(f"[slot :{slot:02d}] {book} {mode}", flush=True)
    mod = importlib.import_module(mod_name)
    _remap_module(mod, slot)
    _call_run(mod, mode)


def _run_all(mode: str, slot: int) -> int:
    """Her defter ayrı süreç — wrapper globalleri birbirini ezmesin (c101_v2)."""
    py = sys.executable
    script = os.path.abspath(__file__)
    rc = 0
    for book in _BOOK_ORDER:
        r = subprocess.run(
            [py, script, mode, "--slot", f"{slot:02d}", "--book", book],
            cwd=_DIR,
        )
        if r.returncode:
            rc = r.returncode
            print(f"[slot :{slot:02d}] {book} çıkış {r.returncode}", file=sys.stderr)
    return rc


def main() -> None:
    p = argparse.ArgumentParser(description=":05/:07 sanal kopya close/open")
    p.add_argument("mode", choices=("open", "close"))
    p.add_argument("--slot", required=True, help="05 veya 07")
    p.add_argument("--book", default=None, help="tek defter, a1 (Top-34) veya a2 (Top-17)")
    args = p.parse_args()
    slot = parse_slot(args.slot)
    if slot not in COPY_SLOTS:
        raise SystemExit("--slot yalnız 05 veya 07 (:02 mevcut cron)")
    os.chdir(_DIR)
    if args.book:
        run_book(args.book, args.mode, slot)
        return
    raise SystemExit(_run_all(args.mode, slot))


if __name__ == "__main__":
    main()
