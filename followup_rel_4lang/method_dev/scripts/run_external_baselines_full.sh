#!/usr/bin/env bash
set -euo pipefail
TASK_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$TASK_REPO"
bash followup_rel_4lang/method_dev/scripts/run_external_baselines.sh --run
export OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3
"$TASK_REPO/.venv/bin/python" -u followup_rel_4lang/method_dev/scripts/report_external_baselines.py
