#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate
exec freqtrade trade --config user_data/config.json --strategy SampleStrategy
