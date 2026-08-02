#!/usr/bin/env python3
"""Kritik kaynak dosyalarını inotify ile izle; silinmede olay kaydı yaz.

Loglar:
  /tmp/aiproject_file_watch.log          — sürekli izleme
  /root/aiProject/ops/incidents/         — silinme/eksik olay raporları (kalıcı)
  /tmp/aiproject_incidents/              — aynı raporun kopyası
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import select
import struct
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("/root/aiProject")
LOG_PATH = Path("/tmp/aiproject_file_watch.log")
INCIDENT_DIR = ROOT / "ops" / "incidents"
INCIDENT_TMP = Path("/tmp/aiproject_incidents")
TZ = ZoneInfo("Europe/Istanbul")
HEARTBEAT_SEC = 60
MY_PID = os.getpid()

WATCH_DIRS = [
    ROOT / "web",
    ROOT / "AgustosKripto",
    ROOT / "AgustosKripto" / "Algoritmalar",
    ROOT / "AgustosKripto" / "Analizler",
    ROOT / "temmuzPoly",
    ROOT / ".cursor" / "rules",
    ROOT,
]

CRITICAL = [
    ROOT / "web" / "poly_dashboard.py",
    ROOT / "PROJECT.md",
    ROOT / ".cursor" / "rules" / "cron-and-ops.mdc",
    ROOT / "AgustosKripto" / "virtual_book.py",
    ROOT / "AgustosKripto" / "crypto_futures_cr6.py",
    ROOT / "AgustosKripto" / "crypto_futures_trader.py",
    ROOT / "AgustosKripto" / "binance_futures_client.py",
    ROOT / "AgustosKripto" / "atr_profit_lock.py",
    ROOT / "AgustosKripto" / "fee_utils.py",
    ROOT / "AgustosKripto" / "Algoritmalar" / "runner.py",
    ROOT / "AgustosKripto" / "Algoritmalar" / "catalog.py",
    ROOT / "AgustosKripto" / "Analizler" / "runner.py",
    ROOT / "AgustosKripto" / "Analizler" / "signals.py",
    ROOT / "temmuzPoly" / "pm_balance_guard.py",
    ROOT / "temmuzPoly" / "pm_orphan_sync.py",
    ROOT / "temmuzPoly" / "pm_trader_helpers.py",
]
CRITICAL_SET = {str(p) for p in CRITICAL}

WATCH_SUFFIXES = {".py", ".md", ".mdc", ".sh", ".json"}
IGNORE_NAME_SUBSTR = (
    "_state.json",
    "_history.json",
    "_pending.json",
    ".pyc",
    "__pycache__",
)

IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_ONLYDIR = 0x01000000
MASK = IN_CREATE | IN_DELETE | IN_MOVED_FROM | IN_MOVED_TO | IN_DELETE_SELF | IN_MOVE_SELF

EVENT_FMT = "iIII"
EVENT_SIZE = struct.calcsize(EVENT_FMT)

libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
libc.inotify_init.restype = ctypes.c_int
libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
libc.inotify_add_watch.restype = ctypes.c_int

# aynı dosya için spam kes (30 sn)
_last_incident: dict[str, float] = {}


def now_tr() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")


def now_stamp() -> str:
    return datetime.now(TZ).strftime("%Y%m%d_%H%M%S")


def log(msg: str) -> None:
    line = f"[{now_tr()}] {msg}"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        print(line, flush=True)
        return
    print(line, flush=True)


def _run(cmd: list[str], timeout: float = 3.0) -> str:
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
        return out.strip()[:8000]
    except Exception as e:
        return f"(failed: {e})"


def _ignored(name: str) -> bool:
    if not name:
        return True
    if any(s in name for s in IGNORE_NAME_SUBSTR):
        return True
    suf = Path(name).suffix.lower()
    if suf and suf not in WATCH_SUFFIXES:
        return True
    if suf == ".json" and any(
        x in name for x in ("_state", "_history", "_pending", "accuracy", "snap")
    ):
        return True
    return False


def _proc_snapshot(limit: int = 40) -> list[dict]:
    """aiProject / cursor / git / python / rm ile ilgili process’ler."""
    rows: list[dict] = []
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return rows
    for pid in pids:
        try:
            ipid = int(pid)
            if ipid == MY_PID:
                continue
            cmdline = (
                Path(f"/proc/{pid}/cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode("utf-8", "replace")
                .strip()
            )
            if not cmdline:
                continue
            low = cmdline.lower()
            if not any(
                k in low
                for k in (
                    "aiproject",
                    "cursor",
                    "git",
                    "python",
                    "node",
                    "rm ",
                    "/rm",
                    "unlink",
                    "poly_dashboard",
                    "agent",
                )
            ):
                continue
            try:
                exe = os.readlink(f"/proc/{pid}/exe")
            except OSError:
                exe = "?"
            try:
                cwd = os.readlink(f"/proc/{pid}/cwd")
            except OSError:
                cwd = "?"
            try:
                status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="replace")
                ppid = next(
                    (ln.split()[1] for ln in status.splitlines() if ln.startswith("PPid:")),
                    "?",
                )
                uid = next(
                    (ln.split()[1] for ln in status.splitlines() if ln.startswith("Uid:")),
                    "?",
                )
            except OSError:
                ppid, uid = "?", "?"
            rows.append(
                {
                    "pid": ipid,
                    "ppid": ppid,
                    "uid": uid,
                    "exe": exe,
                    "cwd": cwd,
                    "cmd": cmdline[:240],
                }
            )
            if len(rows) >= limit:
                break
        except (OSError, PermissionError, ValueError):
            continue
    return rows


def _audit_hint(path: Path) -> str:
    """auditd varsa son unlink kayıtlarını çek."""
    if not Path("/usr/sbin/ausearch").is_file() and not Path("/sbin/ausearch").is_file():
        return "(ausearch yok — auditd kurulu değil)"
    # son 2 dk
    out = _run(
        ["ausearch", "-k", "aiproject_del", "-ts", "recent", "-i"],
        timeout=4.0,
    )
    if not out or "no matches" in out.lower():
        out2 = _run(
            ["ausearch", "-f", str(path), "-ts", "recent", "-i"],
            timeout=4.0,
        )
        return out2 or out or "(audit kaydı yok)"
    return out


def write_incident(
    *,
    kind: str,
    path: Path | None,
    paths: list[str] | None = None,
    extra: dict | None = None,
) -> Path | None:
    key = str(path) if path else ",".join(paths or [])
    now = time.monotonic()
    if key and now - _last_incident.get(key, 0) < 30:
        return None
    _last_incident[key] = now

    INCIDENT_DIR.mkdir(parents=True, exist_ok=True)
    INCIDENT_TMP.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    name = f"incident_{stamp}_{kind}.json"
    report = {
        "ts_tr": now_tr(),
        "kind": kind,
        "path": str(path) if path else None,
        "paths": paths or ([str(path)] if path else []),
        "watcher_pid": MY_PID,
        "processes": _proc_snapshot(),
        "git_status_short": _run(
            ["git", "-C", str(ROOT), "status", "--short"],
            timeout=5.0,
        ),
        "git_status_deleted": _run(
            ["bash", "-lc", f"cd {ROOT} && git status --short | rg '^ D |^D ' || true"],
            timeout=5.0,
        ),
        "audit": _audit_hint(path) if path else _run(["ausearch", "-k", "aiproject_del", "-ts", "recent", "-i"], 4.0),
        "w_who": _run(["who", "-a"], 2.0),
        "last_logins": _run(["last", "-n", "8"], 2.0),
        "dashboard_log_tail": _run(
            ["bash", "-lc", "tail -n 40 /tmp/poly_dashboard.log 2>/dev/null || true"],
            2.0,
        ),
        "extra": extra or {},
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    dest = INCIDENT_DIR / name
    dest_tmp = INCIDENT_TMP / name
    try:
        dest.write_text(text + "\n", encoding="utf-8")
        dest_tmp.write_text(text + "\n", encoding="utf-8")
    except OSError as e:
        log(f"WARN incident write failed: {e}")
        return None
    log(f"INCIDENT saved {dest}")
    # kısa insan okur özet
    summary = INCIDENT_DIR / f"incident_{stamp}_{kind}.txt"
    try:
        lines = [
            f"Zaman: {report['ts_tr']}",
            f"Tür: {kind}",
            f"Path: {path or paths}",
            "",
            "=== Process şüpheliler ===",
        ]
        for p in report["processes"][:15]:
            lines.append(
                f"pid={p['pid']} ppid={p['ppid']} uid={p['uid']} exe={p['exe']}\n  cmd={p['cmd']}\n  cwd={p['cwd']}"
            )
        lines += [
            "",
            "=== git status (D) ===",
            report["git_status_deleted"] or "(yok)",
            "",
            "=== audit ===",
            str(report["audit"])[:2000],
            "",
            f"Tam JSON: {dest}",
        ]
        summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass
    return dest


def check_critical(missing_only: bool = False) -> list[str]:
    missing = [str(p) for p in CRITICAL if not p.is_file()]
    if missing:
        log(f"ALERT MISSING critical files ({len(missing)}): {', '.join(missing)}")
        write_incident(kind="MISSING", path=None, paths=missing)
    elif not missing_only:
        log(f"OK heartbeat — {len(CRITICAL)} critical files present")
    return missing


def main() -> int:
    global MY_PID
    MY_PID = os.getpid()
    fd = libc.inotify_init()
    if fd < 0:
        log("FATAL inotify_init failed")
        return 1

    wd_map: dict[int, Path] = {}
    for d in WATCH_DIRS:
        if not d.is_dir():
            log(f"SKIP missing dir {d}")
            continue
        wd = libc.inotify_add_watch(fd, str(d).encode(), MASK | IN_ONLYDIR)
        if wd < 0:
            log(f"WARN add_watch failed {d} errno={ctypes.get_errno()}")
            continue
        wd_map[wd] = d
        log(f"WATCH {d}")

    log(f"STARTED pid={MY_PID} critical={len(CRITICAL)} dirs={len(wd_map)}")
    log(f"INCIDENT_DIR={INCIDENT_DIR}")
    check_critical(missing_only=False)

    buf = b""
    last_hb = time.monotonic()
    try:
        while True:
            timeout = max(1.0, HEARTBEAT_SEC - (time.monotonic() - last_hb))
            r, _, _ = select.select([fd], [], [], timeout)
            if time.monotonic() - last_hb >= HEARTBEAT_SEC:
                check_critical(missing_only=True)
                last_hb = time.monotonic()
            if not r:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                continue
            buf += chunk
            while len(buf) >= EVENT_SIZE:
                wd, mask, _cookie, name_len = struct.unpack_from(EVENT_FMT, buf, 0)
                total = EVENT_SIZE + name_len
                if len(buf) < total:
                    break
                raw_name = buf[EVENT_SIZE:total]
                buf = buf[total:]
                name = raw_name.rstrip(b"\0").decode("utf-8", "replace")
                base = wd_map.get(wd, Path("?"))
                full = base / name if name else base

                if name and _ignored(name):
                    continue

                kinds = []
                if mask & IN_DELETE:
                    kinds.append("DELETE")
                if mask & IN_MOVED_FROM:
                    kinds.append("MOVED_FROM")
                if mask & IN_MOVED_TO:
                    kinds.append("MOVED_TO")
                if mask & IN_CREATE:
                    kinds.append("CREATE")
                if mask & IN_DELETE_SELF:
                    kinds.append("DELETE_SELF")
                if mask & IN_MOVE_SELF:
                    kinds.append("MOVE_SELF")
                if not kinds:
                    continue

                is_alarm = bool(
                    mask & (IN_DELETE | IN_MOVED_FROM | IN_DELETE_SELF | IN_MOVE_SELF)
                )
                level = "ALERT" if is_alarm else "INFO"
                log(f"{level} {'|'.join(kinds)} {full}")

                # kritik veya herhangi .py/.md silinmesi → olay kaydı
                is_crit = str(full) in CRITICAL_SET
                if is_alarm and (is_crit or full.suffix.lower() in {".py", ".md", ".mdc", ".sh"}):
                    write_incident(
                        kind="DELETE" if "DELETE" in kinds else kinds[0],
                        path=full,
                        extra={"kinds": kinds, "critical": is_crit},
                    )
                if is_alarm and is_crit:
                    check_critical(missing_only=True)
    except KeyboardInterrupt:
        log("STOPPED KeyboardInterrupt")
    except Exception:
        log("FATAL " + traceback.format_exc())
        return 1
    finally:
        os.close(fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
