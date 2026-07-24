#!/usr/bin/env bash
# ALFA — freqtrade venv (talib) + jesse site-packages (indicators)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/freqtrade/.venv/bin/python"
JESSE_SITE="$ROOT/jesse/.venv/lib/python$( "$ROOT/jesse/.venv/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' )/site-packages"

if [ ! -x "$PY" ]; then
  echo "freqtrade venv yok — once: cd $ROOT/freqtrade && ./setup.sh" >&2
  exit 1
fi
if [ ! -d "$ROOT/jesse/.venv" ]; then
  echo "jesse venv yok — once: cd $ROOT/jesse && ./setup.sh" >&2
  exit 1
fi

export PYTHONPATH="$ROOT/temmuzPoly:$ROOT/freqtrade:$ROOT/jesse:$JESSE_SITE"
exec "$PY" "$ROOT/temmuzPoly/poly_trader_alfa.py" "$@"
