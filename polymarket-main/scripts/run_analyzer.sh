#!/bin/bash
# Polymarket analiz döngüsünü çalıştır
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"

# venv varsa kullan
if [ -f .venv/bin/python ]; then
  exec .venv/bin/python -m src.main "$@"
else
  exec python3 -m src.main "$@"
fi
