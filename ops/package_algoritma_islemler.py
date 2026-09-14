#!/usr/bin/env python3
"""Algoritma-islemler taşıma paketi — zip oluştur.

Kullanım:
  python3 ops/package_algoritma_islemler.py
  python3 ops/package_algoritma_islemler.py --out /tmp/algoritma-islemler-bundle.zip

Paket: dashboard + API + tüm sanal trader/sinyal modülleri + state + kurulum dosyaları.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import subprocess
import sys
import textwrap
import zipfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DIST = os.path.join(_ROOT, "dist")
_DEFAULT_OUT = os.path.join(_DIST, "algoritma-islemler-bundle.zip")

# ── Dahil edilecek yollar (göreli _ROOT) ───────────────────────
INCLUDE_DIRS = [
    "web",
    "temmuzPoly",
    "bahis",
    "ALGO3",
    "Sonnet",
    "ops",
]

INCLUDE_FILES = [
    "binance_fapi_guard.py",
    "binance_ws_marks.py",
    ".env.example",
]

# temmuzPoly içinde atlanacak desenler
SKIP_PATTERNS = [
    "_archive_*",
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".git",
]

# .env örneği (gerçek .env kopyalanmaz)
ENV_EXAMPLE = """# Algoritma-islemler — örnek ortam (.env olarak kopyala)
POLY_DRY_RUN=true
POLY_DASHBOARD_HOST=127.0.0.1
# Mirror API (dış sunucu poll edecekse)
# MIRROR_API_TOKEN=degistir
# REF amount API auth yok; mirror için token gerekli
# Telegram (opsiyonel)
# TELEGRAM_ANALIZ1_CHAT_ID=
# TELEGRAM_POLY_TRADERS_CHAT_ID=
# GLASSNODE_API_KEY=
"""

INSTALL_MD = """# Algoritma İşlemler — Kurulum

Bu paket `https://bursaapp.com/algoritma-islemler` sayfasının tam kopyasıdır:
84 sanal Poly defter, dashboard UI, API (mirror, ref-amount, a2-algoritmalar).

## Gereksinimler

- Ubuntu 22.04+ (veya benzeri Linux)
- Python 3.10+
- nginx + TLS (önerilir)

```bash
pip install flask numpy pandas werkzeug
```

## Kurulum

```bash
unzip algoritma-islemler-bundle.zip -d /opt/algo-islemler
cd /opt/algo-islemler
cp .env.example .env
# .env içinde POLY_DRY_RUN=true bırak (sanal, gerçek PM yok)
```

### 1. Dashboard

`web/poly_dashboard.py` içinde `_USERNAME` / `_PASSWORD` değiştir.

```bash
systemctl enable --now binance-ws-marks poly-dashboard
# veya elle:
python3 binance_ws_marks.py &   # saatlik yol
python3 web/poly_dashboard.py   # :5050
```

### 2. nginx

```nginx
location /algoritma {
    proxy_pass http://127.0.0.1:5050;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
location /poly { proxy_pass http://127.0.0.1:5050; ... }
location /site { proxy_pass http://127.0.0.1:5050; ... }
```

### 3. Cron

`ops/crontab-algo-islemler.txt` satırlarını `crontab -e` ile ekle.

### 4. Sıfırdan başlat (isteğe bağlı)

```bash
cd temmuzPoly
python3 algo_islemler_fresh_start.py --wipe-history
```

## API uçları

| Endpoint | Auth | Açıklama |
|----------|------|----------|
| `GET /poly/api/a2-algoritmalar` | session | Defter listesi |
| `GET /poly/api/a2-algoritmalar/<book>` | session | Detay |
| `POST /poly/api/a2-algoritmalar/<book>/amounts` | session | Kademe kaydet |
| `GET /poly/api/ref-amount?book=refsa&symbol=BTC` | yok | WR→amount |
| `GET /poly/api/mirror/<book>` | token | Dış ayna |
| `GET /poly/api/hourly-path` | session | Saatlik yol |
| `GET /poly/api/market-regime` | session | ADX/ATR tape |

Mirror token: `MIRROR_API_TOKEN` env veya header `X-Mirror-Token`.

## Sayfa rotaları

- `/algoritma-islemler` — ana liste
- `/algoritma-islemler/<book_id>` — detay
- `/algoritma-islemler/saatlik-yol` — yol grafiği
- `/poly/login` — giriş

## Dış bağımlılıklar

- Polymarket Gamma + CLOB (kotasyon)
- Binance (klines, WS marks)
- Telegram / Glassnode — opsiyonel
"""


def _should_skip(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    for pat in SKIP_PATTERNS:
        if any(fnmatch.fnmatch(p, pat) for p in parts):
            return True
        if fnmatch.fnmatch(os.path.basename(rel), pat):
            return True
    return False


def _collect_files() -> list[tuple[str, str]]:
    """(abs_src, arcname) listesi."""
    out: list[tuple[str, str]] = []
    for d in INCLUDE_DIRS:
        base = os.path.join(_ROOT, d)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if not _should_skip(x)]
            for f in files:
                abs_p = os.path.join(root, f)
                rel = os.path.relpath(abs_p, _ROOT)
                if _should_skip(rel):
                    continue
                out.append((abs_p, rel))
    for f in INCLUDE_FILES:
        if f == ".env.example":
            continue
        abs_p = os.path.join(_ROOT, f)
        if os.path.isfile(abs_p):
            out.append((abs_p, f))
    return out


def _write_generated(staging: str) -> list[tuple[str, str]]:
    with open(os.path.join(staging, ".env.example"), "w") as fh:
        fh.write(ENV_EXAMPLE)
    with open(os.path.join(staging, "INSTALL.md"), "w") as fh:
        fh.write(INSTALL_MD)

    # Crontab özeti
    cr_path = os.path.join(staging, "ops", "crontab-algo-islemler.txt")
    try:
        cr = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
        lines = cr.stdout.splitlines() if cr.returncode == 0 else []
        keys = (
            "algo_signals", "algo_signals_v2", "f1_signal", "poly_trader_a1",
            "poly_trader_a2", "poly_trader_f1", "slot_trader", "jarvis2026",
            "ref01", "refsa", "ref04", "ref05", "ref06", "ref07",
            "poly_trader_analiz", "poly_trader_b1", "poly_trader_c101",
            "poly_trader_e0", "poly_trader_f16", "poly_trader_x101",
            "a2_05_v2", "algo_consensus", "chart_algo_panel", "binance_ws_marks",
            "backtest_watch", "jarvis2026_evolve", "slot_data_archive",
        )
        picked = [ln for ln in lines if not ln.strip().startswith("#") and any(k in ln for k in keys)]
        os.makedirs(os.path.dirname(cr_path), exist_ok=True)
        with open(cr_path, "w") as fh:
            fh.write("# Algoritma-islemler cron — üretimden kopyalandı\n")
            fh.write(f"# {datetime.now(ZoneInfo('Europe/Istanbul')):%Y-%m-%d %H:%M} İST\n\n")
            fh.write("\n".join(picked) + "\n")
    except Exception as e:
        print(f"[warn] crontab çıkarılamadı: {e}")

    # systemd örnekleri
    svc_paths: list[tuple[str, str]] = []
    for svc in ("poly-dashboard", "binance-ws-marks"):
        src = f"/etc/systemd/system/{svc}.service"
        if os.path.isfile(src):
            dst = os.path.join(staging, "ops", f"{svc}.service")
            shutil.copy2(src, dst)
            svc_paths.append((dst, f"ops/{svc}.service"))

    manifest = os.path.join(staging, "MANIFEST.txt")
    files = _collect_files()
    with open(manifest, "w") as fh:
        fh.write(f"algoritma-islemler bundle\n")
        fh.write(f"created: {datetime.now(timezone.utc).isoformat()}\n")
        fh.write(f"files: {len(files) + 2}\n\n")
        for _, arc in sorted(files, key=lambda x: x[1]):
            fh.write(arc + "\n")
    extra: list[tuple[str, str]] = []
    if os.path.isfile(cr_path):
        extra.append((cr_path, "ops/crontab-algo-islemler.txt"))
    extra.extend(svc_paths)
    return extra


def build_zip(out_path: str) -> dict:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    staging = os.path.join(_DIST, "_staging_algo")
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)

    extra = _write_generated(staging)
    files = _collect_files()
    # staging generated files
    for name in (".env.example", "INSTALL.md", "MANIFEST.txt"):
        p = os.path.join(staging, name)
        if os.path.isfile(p):
            files.append((p, name))
    files.extend(extra)

    # arcname tekilleştir (staging systemd dosyaları ops/ altında çiftlenebilir)
    by_arc: dict[str, str] = {}
    for abs_p, arc in files:
        if os.path.isfile(abs_p):
            by_arc[arc] = abs_p

    total_bytes = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for arc, abs_p in sorted(by_arc.items()):
            zf.write(abs_p, arc)
            total_bytes += os.path.getsize(abs_p)
    files = list(by_arc.items())

    if os.path.exists(staging):
        shutil.rmtree(staging)

    zip_size = os.path.getsize(out_path)
    return {
        "path": out_path,
        "files": len(by_arc),
        "source_bytes": total_bytes,
        "zip_bytes": zip_size,
        "zip_mb": round(zip_size / 1024 / 1024, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Algoritma-islemler zip paketi")
    ap.add_argument("--out", default=_DEFAULT_OUT, help="çıktı zip yolu")
    args = ap.parse_args()
    info = build_zip(args.out)
    print(f"✓ Paket hazır: {info['path']}")
    print(f"  {info['files']} dosya · kaynak {info['source_bytes']//1024//1024} MB · zip {info['zip_mb']} MB")


if __name__ == "__main__":
    main()
