#!/usr/bin/env bash
set -euo pipefail
TASK_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$TASK_REPO"
export XDG_CACHE_HOME=/home/jovyan/seungjae/.cache
export HF_HOME="$XDG_CACHE_HOME/huggingface" TORCH_HOME="$XDG_CACHE_HOME/torch" PIP_CACHE_DIR="$XDG_CACHE_HOME/pip"
export OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 NUMEXPR_NUM_THREADS=3
exec "$TASK_REPO/.venv/bin/python" -u followup_rel_4lang/method_dev/scripts/run_editor_matrix.py --run "$@"
