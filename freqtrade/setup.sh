#!/usr/bin/env bash
# Freqtrade upstream + venv kurulumu (ilk seferde bir kez calistir)
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ ! -f pyproject.toml ]; then
  echo "freqtrade upstream klonlaniyor..."
  tmp="$(mktemp -d)"
  git clone --depth 1 https://github.com/freqtrade/freqtrade.git "$tmp"
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
freqtrade install-ui
echo "Kurulum tamam. Ornek: ./run_analiz3.sh stats"
