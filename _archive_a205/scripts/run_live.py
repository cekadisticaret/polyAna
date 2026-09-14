#!/usr/bin/env python3
"""A2#05 gerçek PM — open | close (paper mirror)."""
from __future__ import annotations

import sys

from bootstrap import init, live_spec


def main() -> None:
    init()
    from live_trader import main as live_main

    mode = sys.argv[1] if len(sys.argv) > 1 else "open"
    if mode not in ("open", "close"):
        print("Kullanım: run_live.py open|close")
        sys.exit(1)
    sys.argv = [sys.argv[0], mode]
    live_main(live_spec())


if __name__ == "__main__":
    main()
