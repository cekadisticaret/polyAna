#!/usr/bin/env python3
"""A2#05 sanal trader — open | close"""
from __future__ import annotations

import asyncio
import sys

from bootstrap import init, sanal_config


def main() -> None:
    init()
    from sanal_core import run_close, run_open

    mode = (sys.argv[1] if len(sys.argv) > 1 else "open").lower()
    cfg = sanal_config()
    if mode == "close":
        asyncio.run(run_close(cfg))
    elif mode == "open":
        asyncio.run(run_open(cfg))
    else:
        print("Kullanım: run_sanal.py open|close")
        sys.exit(1)


if __name__ == "__main__":
    main()
