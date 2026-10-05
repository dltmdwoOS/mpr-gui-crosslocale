#!/usr/bin/env bash
# Source this file before running the pinned InternVL2.5 model on this server.
INTERNVL_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export XDG_CACHE_HOME=/home/jovyan/seungjae/.cache
export HF_HOME=/home/jovyan/seungjae/.cache/huggingface
export HF_HUB_CACHE="$HF_HOME/hub"
export TORCH_HOME=/home/jovyan/seungjae/.cache/torch
export PIP_CACHE_DIR=/home/jovyan/seungjae/.cache/pip
export PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=3
export MKL_NUM_THREADS=3
export OPENBLAS_NUM_THREADS=3
export NUMEXPR_NUM_THREADS=3
export TOKENIZERS_PARALLELISM=false

# The pinned InternVL2.5 revision is stored in this user's personal cache.
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

source "$INTERNVL_REPO_ROOT/.venv/bin/activate"
export PYTHON_BIN="$INTERNVL_REPO_ROOT/.venv/bin/python"
