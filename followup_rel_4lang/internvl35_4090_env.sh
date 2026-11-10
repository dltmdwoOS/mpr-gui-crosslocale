#!/usr/bin/env bash
# Source from any directory. No credentials or machine-specific cache is saved.
INTERNVL35_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Same cache as run_full_internvl35.sh (repo-local), so download and run share one copy.
export XDG_CACHE_HOME="${INTERNVL35_REPO_ROOT}/.cache"
export HF_HOME="${INTERNVL35_REPO_ROOT}/.cache/huggingface"
export OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3
export TOKENIZERS_PARALLELISM=false
export PYTHON_BIN="${INTERNVL35_REPO_ROOT}/.venv/bin/python"
export INTERNVL35_MODEL_ID=OpenGVLab/InternVL3_5-8B
export INTERNVL35_REVISION=9bb6a56ad9cc69db95e2d4eeb15a52bbcac4ef79
export MODEL_CONFIG="${MODEL_CONFIG:-01_code/configs/models/internvl3_5_8b_4090.yaml}"
export OUT="${OUT:-followup_rel_4lang/results/internvl35_single4090}"
export DESCRIPTORS="${DESCRIPTORS:-followup_rel_4lang/grounding_eval/rtx4090_20261105/main_descriptors_draft_v2.json}"
