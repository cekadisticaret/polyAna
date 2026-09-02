#!/usr/bin/env python3
"""5051 sağlıklı değilse BursaApp'i ayağa kaldırır. Cron: * * * * *

Önce `systemctl restart bursaapp` dener (asıl birim). Olmazsa tek orphan
süreç başlatır. Eski sürüm systemd PID'sini SIGKILL'layıp Popen açıyordu →
systemd crash-loop + nginx 502.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.request

APP = "/root/aiProject/BursaApp/app.py"
PY = "/usr/bin/python3"
LOG = "/tmp/bursaapp.log"
PORT = "5051"
UNIT = "bursaapp.service"


def _listening() -> bool:
    try:
        out = subprocess.check_output(["ss", "-ltn"], text=True)
    except Exception:
        return False
    return f":{PORT}" in out and "127.0.0.1" in out


def _healthy() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _app_pids() -> list[int]:
    pids = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            cmd = open(f"/proc/{name}/cmdline", "rb").read().replace(b"\0", b" ").decode("utf-8", "ignore").strip()
        except Exception:
            continue
        if cmd.startswith(f"{PY} {APP}") or cmd.startswith(f"python3 {APP}"):
            pids.append(int(name))
    return pids


def _listen_pid() -> int | None:
    try:
        out = subprocess.check_output(["ss", "-ltnp"], text=True)
    except Exception:
        return None
    for line in out.splitlines():
        if f":{PORT}" in line and "pid=" in line:
            try:
                return int(line.split("pid=")[1].split(",")[0])
            except ValueError:
                return None
    return None


def _systemctl(*args: str) -> int:
    try:
        return subprocess.call(
            ["systemctl", *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return 127


def _kill_orphans(keep: int | None) -> None:
    for pid in _app_pids():
        if keep and pid == keep:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def _start_orphan() -> None:
    """systemd yoksa / birim bozuksa son çare — tek süreç."""
    for pid in _app_pids():
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    time.sleep(0.8)
    if _listening():
        subprocess.call(["fuser", "-k", f"{PORT}/tcp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.8)
    log = open(LOG, "a")
    subprocess.Popen(
        [PY, APP],
        cwd="/root/aiProject/BursaApp",
        stdout=log,
        stderr=log,
        start_new_session=True,
        env={**os.environ, "BURSAAPP_HOST": "127.0.0.1", "BURSAAPP_PORT": PORT},
    )


def _purge_unverified_daily() -> None:
    """Günde bir: 7 gün onaysız üyeleri sil."""
    stamp = "/tmp/bursaapp_purge_unverified.day"
    day = time.strftime("%Y-%m-%d")
    try:
        if os.path.isfile(stamp) and open(stamp).read().strip() == day:
            return
    except Exception:
        pass
    try:
        sys.path.insert(0, "/root/aiProject/BursaApp")
        from mail_verify import purge_unverified_users
        from models import SessionLocal, init_db

        init_db()
        db = SessionLocal()
        try:
            n = purge_unverified_users(db)
            if n:
                print(f"bursaapp purge_unverified n={n} {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        finally:
            db.close()
        open(stamp, "w").write(day)
    except Exception as e:
        print(f"bursaapp purge_unverified err {e}", flush=True)


def main() -> None:
    _purge_unverified_daily()
    if _listening() and _healthy():
        _kill_orphans(_listen_pid())
        return

    # 1) systemd — asıl yol (cron host'ta çalışır)
    rc = _systemctl("restart", UNIT)
    if rc == 0:
        time.sleep(2)
        if _listening() and _healthy():
            print(f"bursaapp systemd-restarted {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
            return

    # 2) systemd yok / başarısız → orphan (önce sağlıklıysa öldürme)
    if _listening() and _healthy():
        print(f"bursaapp ok {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        return

    _start_orphan()
    time.sleep(2)
    if _listening() and _healthy():
        print(f"bursaapp orphan-started {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        return

    print(f"bursaapp ensure_up FAILED {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)


if __name__ == "__main__":
    main()
