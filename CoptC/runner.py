#!/usr/bin/env python3
"""CoptC — B1#03 MUM + B1#05 + A1 tek giriş noktası.

Her defter ayrı süreçte koşar: `poly_trader_b1_05.py` içe aktarıldığında
`poly_trader_b1_01` iskeletinin globallerini kendine yönlendiriyor, aynı
süreçte başka defter çalıştırmak o yönlendirmeyi bozardı.

A1 Live (`poly_trader_analiz5.py`) diğer iki Live defterinden farklı: sanalı
aynalamaz, kendi sinyalini çözer. Bu yüzden :06:30'u beklemez, :05'te sanalla
birlikte koşar — beklemek sadece giriş fiyatını kötüleştirirdi.

Modlar
    close       :02   live kapat → sanal kapat
    open        :05   a2 sinyalleri → sanal aç → A1 Live → havuz kaydı
    live-open   :06:30 sanal state'i gerçek PM'e aynala (mirror defterler)
    settle      :12   live kapanış tekrarı (PM sonucu geciktiğinde)
    status             defterlerin özeti
"""
from __future__ import annotations

import contextlib
import fcntl
import os
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
_POLY = os.path.join(_DIR, "poly")
_TZ = ZoneInfo("Europe/Istanbul")
_LOCK = os.path.join(_POLY, ".coptc_open.lock")

# a2 sinyal dosyasını bekleyenler
SANAL_A2 = ["poly_trader_b1_mum.py", "poly_trader_b1_05.py"]
# kendi motorunu çalıştıran, sinyal dosyasına ihtiyacı olmayan sanal defter
SANAL_SOLO = ["poly_trader_analiz1.py"]
SANAL = SANAL_SOLO + SANAL_A2
# Sanal state'i aynalayanlar — sanal turu bittikten sonra koşmalı
LIVE_MIRROR = ["poly_trader_b1_mum_live.py", "poly_trader_b1_05_live.py"]
# Kendi sinyalini çözen gerçek PM defteri; aynalamadığı için sanalı beklemez
LIVE_SOLO = ["poly_trader_analiz5.py"]
LIVE = LIVE_MIRROR + LIVE_SOLO


def _run(script: str, *args: str, timeout: int = 600) -> int:
    """Tek betiği ayrı süreçte çalıştır; çıktısını olduğu gibi aktar."""
    cmd = [sys.executable, os.path.join(_POLY, script), *args]
    try:
        r = subprocess.run(cmd, cwd=_POLY, timeout=timeout)
        return r.returncode
    except subprocess.TimeoutExpired:
        print(f"[CoptC] {script} {' '.join(args)} — zaman aşımı ({timeout}s)")
        return 1
    except Exception as e:
        print(f"[CoptC] {script} {' '.join(args)} — hata: {e}")
        return 1


@contextlib.contextmanager
def _open_gate(wait: int = 0):
    """:05 açılış turu ile :06 aynalama turunu sıraya sokar.

    Açılış turu 60 sn'yi aşarsa aynalama yarım sanal state'i kopyalardı.
    wait=0 (açılış) kilidi bekletmeden alır; wait>0 (aynalama) açılış bitene
    kadar bekler, süre dolarsa yine de devam eder — beklemek atlamaktan iyidir.
    """
    f = open(_LOCK, "w")
    try:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    print(f"[CoptC] açılış turu {wait}s içinde bitmedi — yine de devam",
                          flush=True)
                    break
                time.sleep(1)
        yield
    finally:
        with contextlib.suppress(Exception):
            fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def _stamp(mode: str) -> None:
    # alt süreçler doğrudan stdout'a yazıyor; tamponda kalırsa başlık sona düşer
    print(f"\n[CoptC {mode}] {datetime.now(_TZ):%Y-%m-%d %H:%M:%S} İST", flush=True)


def run_close() -> None:
    _stamp("close")
    for s in LIVE:      # önce gerçek PM settle
        _run(s, "close")
    for s in SANAL:
        _run(s, "close")
    _run("pool_tracker.py", "grade")


def run_open() -> None:
    _stamp("open")
    with _open_gate():
        # A1 başta: gerçek para açıyor, en taze fiyatı almalı ve a2 sinyallerini
        # beklemesi gerekmiyor. Sanalı hemen önünde koşuyor ki ikisi aynı veriyi görsün.
        for s in SANAL_SOLO:
            _run(s, "open")
        for s in LIVE_SOLO:
            _run(s, "open")
        _run("algo_signals_v2.py", timeout=300)   # a2 sinyalleri → /tmp/coptc_*
        for s in SANAL_A2:
            _run(s, "open")
        _run("pool_tracker.py", "record")


def run_live_open() -> None:
    _stamp("live-open")
    with _open_gate(wait=45):   # :05 turu bitmeden aynalama
        for s in LIVE_MIRROR:
            _run(s, "open")


def run_settle() -> None:
    _stamp("settle")
    for s in LIVE:
        _run(s, "close")


def run_status() -> None:
    import json

    _stamp("status")
    rows = [
        ("B1#03 MUM", "b1_mum"), ("B1#03 MUM Live", "b1_mum_live"),
        ("B1#05", "b1_05"), ("B1#05 Live", "b1_05_live"),
        ("A1", "analiz1"), ("A1 Live", "analiz5"),
    ]
    for label, key in rows:
        sp = os.path.join(_POLY, f"poly_trader_{key}_state.json")
        hp = os.path.join(_POLY, f"poly_trader_{key}_history.json")
        st = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
        hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
        wins = sum(1 for t in hist if t.get("win"))
        wr = f"%{wins / len(hist) * 100:.1f}" if hist else "—"
        print(f"  {label:<16} bakiye ${st.get('balance', 0):>8.2f} · "
              f"açık {len(st.get('open_positions') or []):>2} · "
              f"{len(hist):>3} işlem · WR {wr}")

    sys.path.insert(0, _POLY)
    from pm_balance_guard import is_group_paused
    for label, grp in (("B1#03 MUM Live", "b1_mum_live"), ("B1#05 Live", "b1_05_live"),
                       ("A1 Live", "analiz5")):
        print(f"  {label:<16} gerçek PM: {'KAPALI' if is_group_paused(grp) else 'AÇIK'}")


MODES = {
    "close": run_close, "open": run_open, "live-open": run_live_open,
    "settle": run_settle, "status": run_status,
}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    fn = MODES.get(mode)
    if not fn:
        print(f"Geçersiz mod: {mode}\nKullanım: runner.py [{' | '.join(MODES)}]")
        sys.exit(2)
    fn()
