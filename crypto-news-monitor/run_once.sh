#!/usr/bin/env bash
# Tek tarama — cron veya manuel test icin
set -euo pipefail
cd "$(dirname "$0")"
exec node index.js --once
