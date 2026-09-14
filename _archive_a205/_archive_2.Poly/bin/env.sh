#!/usr/bin/env bash
# 2.Poly ortak ortam — temmuzPoly YOK
set -euo pipefail
POLY2_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${POLY2_ROOT}/lib${PYTHONPATH:+:$PYTHONPATH}"
cd "$POLY2_ROOT"
if [[ -f "$POLY2_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$POLY2_ROOT/.venv/bin/activate"
fi
if [[ -f "$POLY2_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$POLY2_ROOT/.env"
  set +a
fi
