#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:-}:src"
python -m mpr_crosslocale.inference.processor_preflight "$@"
