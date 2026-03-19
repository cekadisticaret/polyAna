#!/usr/bin/env python3
"""
Günlük Yedekleme — aiProject
Her gün 23:59'da çalışır. Son 7 yedek tutulur, eskiler silinir.
Yedek konumu: /root/aiProject/backups/
"""

import os
import tarfile
from datetime import datetime, timezone

PROJECT_DIR  = "/root/aiProject"
BACKUP_DIR   = os.path.join(PROJECT_DIR, "backups")
LOG_FILE     = "/tmp/backup.log"

EXCLUDE_DIRS  = {"backups", "__pycache__", ".git", ".cursor"}
EXCLUDE_FILES = {".env"}

def log(msg):
    ts = datetime.now().strftime("%d.%m.%Y %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def should_exclude(path):
    parts = path.replace(PROJECT_DIR, "").strip("/").split("/")
    if parts[0] in EXCLUDE_DIRS:
        return True
    if os.path.basename(path) in EXCLUDE_FILES:
        return True
    return False

def create_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)

    ts       = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"aiProject_{ts}.tar.gz"
    filepath = os.path.join(BACKUP_DIR, filename)

    file_count = 0
    with tarfile.open(filepath, "w:gz") as tar:
        for root, dirs, files in os.walk(PROJECT_DIR):
            dirs[:] = [d for d in dirs if os.path.join(root, d).replace(PROJECT_DIR, "").strip("/").split("/")[0] not in EXCLUDE_DIRS]
            for fname in files:
                fpath = os.path.join(root, fname)
                if not should_exclude(fpath):
                    arcname = os.path.relpath(fpath, os.path.dirname(PROJECT_DIR))
                    tar.add(fpath, arcname=arcname)
                    file_count += 1

    size_kb = round(os.path.getsize(filepath) / 1024, 1)
    log(f"✅ Yedek oluşturuldu: {filename} ({file_count} dosya, {size_kb} KB)")
    return filename

if __name__ == "__main__":
    log("─── Yedekleme başladı ───")
    create_backup()
    total = len([f for f in os.listdir(BACKUP_DIR) if f.endswith(".tar.gz")])
    log(f"📦 Toplam yedek: {total}")
    log("─── Yedekleme tamamlandı ───")
