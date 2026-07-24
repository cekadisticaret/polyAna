#!/usr/bin/env bash
# Jesse upstream + venv kurulumu (ilk seferde bir kez calistir)
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ ! -f setup.py ]; then
  echo "jesse upstream klonlaniyor..."
  tmp="$(mktemp -d)"
  git clone --depth 1 https://github.com/jesse-ai/jesse.git "$tmp"
  shopt -s dotglob nullglob
  for item in "$tmp"/*; do
    name="$(basename "$item")"
    [ "$name" = ".git" ] && continue
    [ -e "$DIR/$name" ] && continue
    mv "$item" "$DIR/"
  done
  rm -rf "$tmp"
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip wheel setuptools
pip install -q -r requirements.txt
pip install -q -e .
pip install -q aiohttp
mkdir -p storage
echo "Kurulum tamam. Ornek: ./run_analiz8.sh stats"
