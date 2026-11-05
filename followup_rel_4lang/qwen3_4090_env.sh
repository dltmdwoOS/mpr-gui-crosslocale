#!/usr/bin/env bash
# Source from any directory. No credentials or machine-specific cache is saved.
QWEN3_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HF_HOME="${HF_HOME:-/workspace/.hf_home}"
export OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3
export TOKENIZERS_PARALLELISM=false
export PYTHON_BIN="${QWEN3_REPO_ROOT}/.venv/bin/python"
export QWEN3_REVISION=0c351dd01ed87e9c1b53cbc748cba10e6187ff3b
export MODEL_SNAPSHOT="${HF_HOME}/hub/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/${QWEN3_REVISION}"
