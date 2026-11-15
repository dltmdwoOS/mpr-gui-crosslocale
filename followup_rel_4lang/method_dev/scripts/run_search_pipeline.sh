#!/usr/bin/env bash
set -euo pipefail
TASK_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$TASK_REPO"
export XDG_CACHE_HOME=/home/jovyan/seungjae/.cache
export HF_HOME="$XDG_CACHE_HOME/huggingface"
export TORCH_HOME="$XDG_CACHE_HOME/torch"
export PIP_CACHE_DIR="$XDG_CACHE_HOME/pip"
export OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3
export TOKENIZERS_PARALLELISM=false HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PYTHONPATH="$TASK_REPO/01_code/src:$TASK_REPO${PYTHONPATH:+:$PYTHONPATH}"
exec "$TASK_REPO/.venv/bin/python" -u followup_rel_4lang/method_dev/scripts/search_pipeline.py "$@"
