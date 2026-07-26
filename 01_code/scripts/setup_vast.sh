#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python}"

"${PYTHON_BIN}" -m pip install --upgrade pip setuptools wheel
"${PYTHON_BIN}" -m pip install -e .
"${PYTHON_BIN}" -m pip install -r requirements-vast.txt

"${PYTHON_BIN}" - <<'PY'
import accelerate
import qwen_vl_utils
import torch
import transformers
from transformers import Qwen3VLForConditionalGeneration

print("Environment ready")
print("Transformers:", transformers.__version__)
print("Accelerate:", accelerate.__version__)
print("CUDA available:", torch.cuda.is_available())
print("Qwen3-VL class:", Qwen3VLForConditionalGeneration.__name__)
PY
