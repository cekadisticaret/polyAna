#!/bin/bash
# Bota yazan kullanıcıların chat_id kaydı (getUpdates). Uzun süreli süreç — systemd/supervisor önerilir.
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"
if [ -f .venv/bin/python ]; then
  exec .venv/bin/python -m src.telegram_listener
else
  exec python3 -m src.telegram_listener
fi
