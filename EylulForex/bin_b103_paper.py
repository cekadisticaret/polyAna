"""BIN_XAUUSDT cron — seçilen algoritma-islemler motoru, Isolated $50×50x sanal $180.

  python3 EylulForex/bin_b103_paper.py close|open|trail|scan|status

GPSUSDT / fx_algo_runner / CEM01 dokunulmaz. Manuel open yok — cron :05 / */10.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bin_b103_book import close_expired, close_if_reverse, open_position, snapshot, trail
from bin_b103_data import live_quote, signal_klines
from bin_b103_signal import resolve, side_of
from night_window import is_quiet as _night_quiet, label as _night_label


def _quote() -> dict:
    return live_quote()


def _ba(q: dict | None = None) -> tuple[float, float]:
    q = q or _quote()
    return float(q.get("bid") or 0), float(q.get("ask") or 0)


def run_close() -> dict:
    bid, ask = _ba()
    kl = signal_klines("1h", 80)
    if bid <= 0 or ask <= 0:
        return {"ok": False, "error": "no_quote"}
    r = close_expired(bid, ask, kl)
    print(f"[bin_b103 close] kapanan={r.get('closed')} açık={r.get('held')}")
    return r


def run_trail() -> dict:
    bid, ask = _ba()
    kl = signal_klines("1h", 80)
    if bid <= 0 or ask <= 0:
        return {"ok": False, "error": "no_quote"}
    r = trail(bid, ask, kl)
    print(f"[bin_b103 trail] kapanan={r.get('closed')} kilit={r.get('updated')}")
    return r


def run_open() -> dict:
    if _night_quiet("binb103"):
        print(f"[bin_b103 open] gece penceresi {_night_label()} — skip")
        return {"ok": True, "opened": 0, "skip": "gece_penceresi"}
    bid, ask = _ba()
    kl1 = signal_klines("1h", 180)
    kl4 = signal_klines("4h", 120)
    if bid <= 0 or ask <= 0 or len(kl1) < 30:
        print("[bin_b103 open] mum/fiyat yok")
        return {"ok": False, "error": "no_data"}
    sig = resolve(kl1, kl4)
    side = side_of(sig.get("direction") or "")
    if not side:
        print(f"[bin_b103 open] nötr 1h={sig.get('sig_1h')} 4h={sig.get('sig_4h')}")
        return {"ok": True, "opened": 0, "signal": sig}
    kl = kl1 if sig.get("tf") == "1h" else kl4
    pos = open_position(side, bid, ask, signal=sig["direction"], tf=sig["tf"], kl=kl)
    print(f"[bin_b103 open] {side} {sig.get('tf')} opened={bool(pos)}")
    return {"ok": True, "opened": 1 if pos else 0, "signal": sig, "pos": bool(pos)}


def run_scan() -> dict:
    bid, ask = _ba()
    kl1 = signal_klines("1h", 180)
    kl4 = signal_klines("4h", 120)
    if bid <= 0 or ask <= 0:
        return {"ok": False, "error": "no_quote"}
    sig = resolve(kl1, kl4)
    side = side_of(sig.get("direction") or "")
    closed = 0
    opened = 0
    if side:
        r = close_if_reverse(side, bid, ask, kl1)
        closed = int(r.get("closed") or 0)
        if _night_quiet("binb103"):
            print(f"[bin_b103 scan] gece penceresi {_night_label()} — open skip")
        else:
            kl = kl1 if sig.get("tf") == "1h" else kl4
            pos = open_position(side, bid, ask, signal=sig["direction"], tf=sig["tf"], kl=kl)
            opened = 1 if pos else 0
    trail(bid, ask, kl1)
    print(f"[bin_b103 scan] reverse={closed} open={opened} dir={sig.get('direction')}")
    return {"ok": True, "closed": closed, "opened": opened, "signal": sig}


def run_status() -> dict:
    bid, ask = _ba()
    return snapshot(bid, ask)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["close", "open", "trail", "scan", "status"])
    args = p.parse_args()
    fn = {
        "close": run_close,
        "open": run_open,
        "trail": run_trail,
        "scan": run_scan,
        "status": run_status,
    }[args.cmd]
    out = fn()
    print(json.dumps({k: v for k, v in out.items() if k not in ("history", "positions", "pos")}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
