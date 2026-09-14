#!/usr/bin/env python3
from bootstrap import init

init()

from redeem import main

if __name__ == "__main__":
    raise SystemExit(main())
