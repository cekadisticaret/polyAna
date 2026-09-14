#!/usr/bin/env python3
"""bursaapp.com tam taşıma paketi — zip.

Kullanım:
  python3 ops/package_bursaapp_full.py
  python3 ops/package_bursaapp_full.py --out /tmp/bursaapp-full.zip

Dahil: BursaApp + panel (5050) + bahis + temmuzPoly + kripto + nginx + cron + systemd.
Hariç: backups/, .git/, dist/, _archive_* (eski arşivler).
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DIST = os.path.join(_ROOT, "dist")
_DEFAULT_OUT = os.path.join(_DIST, "bursaapp-full-bundle.zip")

INCLUDE_DIRS = [
    "BursaApp",
    "web",
    "bahis",
    "temmuzPoly",
    "AgustosKripto",
    "ALGO3",
    "Sonnet",
    "BistAnaliz",
    "ops",
    "scripts",
    "crypto-news-monitor",
    "twitter_bot",
]

INCLUDE_FILES = [
    "binance_fapi_guard.py",
    "binance_ws_marks.py",
    "telegram_config.py",
    "PROJECT.md",
]

SKIP_DIR_NAMES = {
    "__pycache__", ".git", "node_modules", "venv", ".venv",
    "backups", "dist", "aiProject",
}
SKIP_PATTERNS = ["_archive_*", "*.pyc", "*.pyo", ".DS_Store"]

INSTALL_MD = """# bursaapp.com — Tam sunucu taşıma

Bu paket `bursaapp.com` sitesinin tamamını içerir.

## İçerik

| Bileşen | Port | URL |
|---------|------|-----|
| BursaApp şehir rehberi | 5051 | `/` |
| Poly / Kripto / Bahis panel | 5050 | `/poly`, `/kripto`, `/bahis` |
| MATCHDAY site | 5050 | `/site` |
| Algoritma işlemler | 5050 | `/algoritma-islemler` |

## Gereksinimler

- Ubuntu 22.04+ · Python 3.10+
- nginx + certbot (TLS)
- `pip install flask numpy pandas werkzeug sqlalchemy`

## Kurulum (yeni sunucu)

```bash
# 1. Aç
unzip bursaapp-full-bundle.zip -d /root
mv /root/aiProject /root/aiProject   # veya istediğin yol

# 2. Ortam
cd /root/aiProject
# Pakette .env varsa kontrol et; yoksa .env.example → .env
chmod 600 .env

# 3. BursaApp DB (pakette geldi)
ls -la BursaApp/data/bursaapp.db

# 4. systemd
cp ops/bursaapp.service ops/poly-dashboard.service ops/binance-ws-marks.service /etc/systemd/system/
# Yolları yeni dizine göre düzenle (WorkingDirectory, ExecStart)
systemctl daemon-reload
systemctl enable --now bursaapp poly-dashboard binance-ws-marks

# 5. nginx
cp ops/nginx-bursaapp.conf /etc/nginx/sites-enabled/bursaapp
# server_name ve ssl_certificate yollarını güncelle
nginx -t && systemctl reload nginx

# 6. TLS (yeni sunucuda)
certbot certonly --nginx -d bursaapp.com -d www.bursaapp.com

# 7. Cron
crontab ops/crontab-full.txt

# 8. Güvenlik
# web/poly_dashboard.py → _USERNAME / _PASSWORD değiştir
# ufw allow 22,80,443 && ufw enable
```

## Servisler

- `bursaapp.service` — :5051 şehir rehberi
- `poly-dashboard.service` — :5051 panel (127.0.0.1:5050)
- `binance-ws-marks.service` — saatlik yol / mark cache

## Dış bağımlılıklar

- Polymarket Gamma + CLOB
- Binance (klines, futures, WS)
- Telegram (opsiyonel)
- **Forex CoptC** ayrı sunucuda — `FOREX_REMOTE_URL` .env'de

## DNS

`bursaapp.com` A kaydı → yeni sunucu IP

## Doğrulama

```bash
curl -sI https://bursaapp.com/
curl -sI https://bursaapp.com/site
curl -sI https://bursaapp.com/poly/login
systemctl status bursaapp poly-dashboard binance-ws-marks
```

## Notlar

- `backups/` ve `_archive_*` pakete alınmadı (boyut). Canlı state/history JSON dosyaları `temmuzPoly/` içinde.
- Eski sunucuyu kapatmadan önce DNS TTL düşür, yeni sunucuda test et.
"""


def _should_skip(rel: str, name: str, is_dir: bool) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if is_dir and name in SKIP_DIR_NAMES:
        return True
    for pat in SKIP_PATTERNS:
        if any(fnmatch.fnmatch(p, pat) for p in parts):
            return True
        if fnmatch.fnmatch(name, pat):
            return True
    return False


def _collect_files() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for d in INCLUDE_DIRS:
        base = os.path.join(_ROOT, d)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if not _should_skip(
                os.path.relpath(os.path.join(root, x), _ROOT), x, True)]
            for f in files:
                abs_p = os.path.join(root, f)
                rel = os.path.relpath(abs_p, _ROOT)
                if _should_skip(rel, f, False):
                    continue
                out.append((abs_p, rel))
    for f in INCLUDE_FILES:
        abs_p = os.path.join(_ROOT, f)
        if os.path.isfile(abs_p):
            out.append((abs_p, f))
    return out


def _write_generated(staging: str) -> list[tuple[str, str]]:
    os.makedirs(os.path.join(staging, "ops"), exist_ok=True)
    extra: list[tuple[str, str]] = []

    with open(os.path.join(staging, "INSTALL.md"), "w") as fh:
        fh.write(INSTALL_MD)
    extra.append((os.path.join(staging, "INSTALL.md"), "INSTALL.md"))

    # .env — taşıma için dahil (sadece zip indiren admin)
    env_src = os.path.join(_ROOT, ".env")
    if os.path.isfile(env_src):
        dst = os.path.join(staging, ".env")
        shutil.copy2(env_src, dst)
        extra.append((dst, ".env"))
        with open(os.path.join(staging, "SECRETS_README.txt"), "w") as fh:
            fh.write(
                ".env bu pakete dahil edildi.\n"
                "Yeni sunucuda: chmod 600 .env\n"
                "Gerekirse API anahtarlarını yenile.\n"
            )
        extra.append((os.path.join(staging, "SECRETS_README.txt"), "SECRETS_README.txt"))

    # nginx
    ngx_src = "/etc/nginx/sites-enabled/bursaapp"
    if os.path.isfile(ngx_src):
        dst = os.path.join(staging, "ops", "nginx-bursaapp.conf")
        shutil.copy2(ngx_src, dst)
        extra.append((dst, "ops/nginx-bursaapp.conf"))

    # systemd
    for svc in ("bursaapp", "poly-dashboard", "binance-ws-marks", "aiproject-file-watch"):
        src = f"/etc/systemd/system/{svc}.service"
        if os.path.isfile(src):
            dst = os.path.join(staging, "ops", f"{svc}.service")
            shutil.copy2(src, dst)
            extra.append((dst, f"ops/{svc}.service"))
        elif os.path.isfile(os.path.join(_ROOT, "ops", f"{svc}.service")):
            src2 = os.path.join(_ROOT, "ops", f"{svc}.service")
            dst = os.path.join(staging, "ops", f"{svc}.service")
            shutil.copy2(src2, dst)
            extra.append((dst, f"ops/{svc}.service"))

    # crontab tam
    try:
        cr = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
        cr_path = os.path.join(staging, "ops", "crontab-full.txt")
        with open(cr_path, "w") as fh:
            fh.write(f"# bursaapp.com tam crontab — {datetime.now(ZoneInfo('Europe/Istanbul')):%Y-%m-%d %H:%M} İST\n\n")
            if cr.returncode == 0:
                fh.write(cr.stdout)
            else:
                fh.write("# crontab okunamadı — eski sunucudan elle kopyala\n")
        extra.append((cr_path, "ops/crontab-full.txt"))
    except Exception:
        pass

    # requirements
    req = os.path.join(staging, "requirements.txt")
    with open(req, "w") as fh:
        fh.write("flask>=3.0\nwerkzeug>=3.0\nnumpy>=1.24\npandas>=2.0\nsqlalchemy>=2.0\nPyJWT>=2.8\n")
    extra.append((req, "requirements.txt"))

    manifest = os.path.join(staging, "MANIFEST.txt")
    files = _collect_files()
    with open(manifest, "w") as fh:
        fh.write(f"bursaapp.com full bundle\n")
        fh.write(f"created: {datetime.now(timezone.utc).isoformat()}\n")
        fh.write(f"source_root: {_ROOT}\n")
        fh.write(f"files: {len(files)}\n\n")
        for _, arc in sorted(files, key=lambda x: x[1]):
            fh.write(arc + "\n")
    extra.append((manifest, "MANIFEST.txt"))
    return extra


def build_zip(out_path: str) -> dict:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    staging = os.path.join(_DIST, "_staging_bursaapp")
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)

    extra = _write_generated(staging)
    files = _collect_files()
    for name in (".env.example",):
        p = os.path.join(_ROOT, name)
        if os.path.isfile(p):
            files.append((p, name))
    files.extend(extra)

    by_arc: dict[str, str] = {}
    for abs_p, arc in files:
        if os.path.isfile(abs_p):
            by_arc[arc] = abs_p

    total_bytes = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for arc, abs_p in sorted(by_arc.items()):
            zf.write(abs_p, arc)
            total_bytes += os.path.getsize(abs_p)

    if os.path.exists(staging):
        shutil.rmtree(staging)

    zip_size = os.path.getsize(out_path)
    return {
        "path": out_path,
        "files": len(by_arc),
        "source_bytes": total_bytes,
        "zip_mb": round(zip_size / 1024 / 1024, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="bursaapp.com tam taşıma zip")
    ap.add_argument("--out", default=_DEFAULT_OUT)
    args = ap.parse_args()
    info = build_zip(args.out)
    print(f"✓ Paket: {info['path']}")
    print(f"  {info['files']} dosya · kaynak ~{info['source_bytes']//1024//1024} MB · zip {info['zip_mb']} MB")
    print("  .env dahil — zip'i güvenli sakla, indirme sonrası chmod 600")


if __name__ == "__main__":
    main()
