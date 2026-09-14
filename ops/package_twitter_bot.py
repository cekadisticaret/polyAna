#!/usr/bin/env python3
"""@tradecomio twitter_bot taşıma paketi — zip.

Kullanım:
  python3 ops/package_twitter_bot.py
  python3 ops/package_twitter_bot.py --out /tmp/twitter-bot-bundle.zip
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DIST = os.path.join(_ROOT, "dist")
_DEFAULT_OUT = os.path.join(_DIST, "twitter-bot-bundle.zip")
_BOT = os.path.join(_ROOT, "twitter_bot")

SKIP_NAMES = {"__pycache__"}
SKIP_PATTERNS = ["*.pyc", "*.pyo", ".DS_Store"]
# Üretilmiş kart PNG'leri — state json yeterli
SKIP_DATA_PATTERNS = ["trade_*.png", "*_latest.png"]

ENV_EXAMPLE = """# twitter_bot — .env (üst dizinde veya aiProject/.env)
TWITTER_API_KEY=
TWITTER_API_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_SECRET=
TWITTER_HANDLE=tradecomio
TWITTER_LANG=tr
TWITTER_MIN_PNL_PCT=5
# TWITTER_DEPRIORITIZE_SYMBOLS=KAITO
# TWITTER_EXCLUDE_SYMBOLS=
"""

INSTALL_MD = """# twitter_bot — Kurulum

@tradecomio otomatik tweet: kripto kazanan işlem kartı, coin liderleri, forex kazananları.

## Gereksinimler

```bash
pip install tweepy pillow numpy
apt install fonts-dejavu-core   # render_card DejaVu font
```

## Dosya yapısı

Betikler `aiProject/twitter_bot/` altında beklenir; üst dizinde:

- `AgustosKripto/` — `tweet_trade_card.py`, `tweet_coin_leaders.py` için (Test defter geçmişi)
- `EylulForex/data/forex_paper_history.json` — `tweet_forex_wins.py` için (opsiyonel; yoksa atlar)
- `.env` — Twitter API anahtarları

## Kurulum

```bash
unzip twitter-bot-bundle.zip -d /root/aiProject
cd /root/aiProject
cp twitter_bot/.env.example ../.env   # veya mevcut .env'e TWITTER_* ekle
```

## Cron

`ops/crontab-twitter-bot.txt` satırlarını `crontab -e` ile ekle.

## Betikler

| Dosya | Açıklama |
|-------|----------|
| `tweet_trade_card.py` | Saatlik: Test defterlerinden en iyi %kârlı işlem → görsel tweet |
| `tweet_coin_leaders.py` | Coin liderleri kartı |
| `tweet_forex_wins.py` | CEM01 forex kazananları (30 dk) |
| `post_tweet.py` | Tweepy v2 + medya yükleme |
| `render_card.py` | PNG kart üretimi |

## Test (tweet atmaz)

```bash
python3 twitter_bot/tweet_trade_card.py --dry-run
python3 twitter_bot/tweet_coin_leaders.py --dry-run
python3 twitter_bot/tweet_forex_wins.py --dry-run
```
"""


def _skip_data_file(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in SKIP_DATA_PATTERNS)


def _collect() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not os.path.isdir(_BOT):
        raise SystemExit(f"twitter_bot bulunamadı: {_BOT}")
    for root, dirs, files in os.walk(_BOT):
        dirs[:] = [d for d in dirs if d not in SKIP_NAMES]
        rel_root = os.path.relpath(root, _ROOT)
        for f in files:
            if any(fnmatch.fnmatch(f, p) for p in SKIP_PATTERNS):
                continue
            if rel_root.endswith("twitter_bot/data") and _skip_data_file(f):
                continue
            abs_p = os.path.join(root, f)
            arc = os.path.relpath(abs_p, _ROOT)
            out.append((abs_p, arc))
    return out


def _write_staging(staging: str) -> None:
    bot_staging = os.path.join(staging, "twitter_bot")
    os.makedirs(bot_staging, exist_ok=True)
    with open(os.path.join(bot_staging, ".env.example"), "w") as fh:
        fh.write(ENV_EXAMPLE)
    with open(os.path.join(staging, "INSTALL.md"), "w") as fh:
        fh.write(INSTALL_MD)

    cr_path = os.path.join(staging, "ops", "crontab-twitter-bot.txt")
    os.makedirs(os.path.dirname(cr_path), exist_ok=True)
    try:
        cr = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
        lines = cr.stdout.splitlines() if cr.returncode == 0 else []
        keys = ("twitter_bot/", "tweet_trade_card", "tweet_forex_wins", "tweet_coin_leaders")
        picked = [ln for ln in lines if not ln.strip().startswith("#") and any(k in ln for k in keys)]
        with open(cr_path, "w") as fh:
            fh.write("# twitter_bot cron\n")
            fh.write(f"# {datetime.now(ZoneInfo('Europe/Istanbul')):%Y-%m-%d %H:%M} İST\n\n")
            if picked:
                fh.write("\n".join(picked) + "\n")
            else:
                fh.write("20 * * * * cd /root/aiProject && python3 twitter_bot/tweet_trade_card.py >> /tmp/twitter_trade_card.log 2>&1\n")
    except Exception as exc:
        print(f"[warn] crontab: {exc}")


def build(out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    staging = os.path.join(_DIST, ".twitter_bot_staging")
    if os.path.isdir(staging):
        import shutil
        shutil.rmtree(staging)
    os.makedirs(staging, exist_ok=True)
    _write_staging(staging)

    files = _collect()
    staging_files = []
    for root, _, fnames in os.walk(staging):
        for f in fnames:
            abs_p = os.path.join(root, f)
            staging_files.append((abs_p, os.path.relpath(abs_p, staging)))

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for abs_p, arc in staging_files:
            zf.write(abs_p, arc)
        for abs_p, arc in files:
            zf.write(abs_p, arc)

    import shutil
    shutil.rmtree(staging, ignore_errors=True)

    mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"OK {out_path} ({mb:.2f} MB, {len(files) + len(staging_files)} dosya)")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="twitter_bot zip paketi")
    ap.add_argument("--out", default=_DEFAULT_OUT, help="çıktı zip yolu")
    args = ap.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
